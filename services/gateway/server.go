package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"sync"
	"time"
)

// Server wires routes, middleware and reverse proxies together.
type Server struct {
	cfg     *Config
	log     *Logger
	metrics *Metrics
	limiter *RateLimiter
	mux     *http.ServeMux
	client  *http.Client
}

type upstream struct {
	name   string
	prefix string
	target *url.URL
}

func NewServer(cfg *Config, log *Logger) *Server {
	s := &Server{
		cfg:     cfg,
		log:     log,
		metrics: NewMetrics(),
		limiter: NewRateLimiter(cfg.RateLimitRPS, cfg.RateLimitBurst),
		mux:     http.NewServeMux(),
		client:  &http.Client{Timeout: 2 * time.Second},
	}
	s.routes()
	return s
}

func (s *Server) upstreams() []upstream {
	return []upstream{
		{"catalog", "/api/catalog", s.cfg.CatalogURL},
		{"inventory", "/api/inventory", s.cfg.InventoryURL},
		{"orders", "/api/orders", s.cfg.OrdersURL},
	}
}

func (s *Server) routes() {
	s.mux.HandleFunc("GET /health", s.health)
	s.mux.HandleFunc("GET /ready", s.ready)
	s.mux.Handle("GET /metrics", s.metrics)
	for _, u := range s.upstreams() {
		s.mux.Handle(u.prefix+"/", s.proxy(u))
	}
	s.mux.Handle("/", http.FileServer(http.Dir(s.cfg.StaticDir)))
}

func (s *Server) proxy(u upstream) http.Handler {
	rp := &httputil.ReverseProxy{
		Rewrite: func(pr *httputil.ProxyRequest) {
			pr.SetURL(u.target)
			pr.Out.URL.Path = strings.TrimPrefix(pr.In.URL.Path, u.prefix)
			if pr.Out.URL.Path == "" {
				pr.Out.URL.Path = "/"
			}
			pr.Out.URL.RawPath = ""
			pr.SetXForwarded()
			pr.Out.Header.Set("X-Request-ID", pr.In.Header.Get("X-Request-ID"))
		},
		Transport: &http.Transport{
			Proxy:                 http.ProxyFromEnvironment,
			DialContext:           (&net.Dialer{Timeout: 2 * time.Second, KeepAlive: 30 * time.Second}).DialContext,
			ResponseHeaderTimeout: s.cfg.UpstreamTimeout,
			MaxIdleConnsPerHost:   50,
			IdleConnTimeout:       90 * time.Second,
		},
		ErrorHandler: func(w http.ResponseWriter, r *http.Request, err error) {
			s.metrics.UpstreamError(u.name)
			status, detail := http.StatusBadGateway, u.name+" service unavailable"
			var netErr net.Error
			if errors.As(err, &netErr) && netErr.Timeout() || errors.Is(err, context.DeadlineExceeded) {
				status, detail = http.StatusGatewayTimeout, u.name+" service timed out"
			}
			s.log.Error("upstream error", map[string]any{
				"upstream": u.name, "target": u.target.String(), "path": r.URL.Path,
				"error": err.Error(), "request_id": r.Header.Get("X-Request-ID"),
			})
			writeJSON(w, status, map[string]any{"detail": detail, "request_id": r.Header.Get("X-Request-ID")})
		},
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// internal endpoints must never be reachable from the internet
		if strings.HasPrefix(strings.TrimPrefix(r.URL.Path, u.prefix), "/internal") {
			writeJSON(w, http.StatusNotFound, map[string]string{"detail": "not found"})
			return
		}
		rp.ServeHTTP(w, r)
	})
}

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "service": "gateway", "version": s.cfg.Version})
}

// ready reports which backends answer /health. The gateway itself stays ready
// even when one backend is down, so the rest of the shop keeps working.
func (s *Server) ready(w http.ResponseWriter, r *http.Request) {
	checks := map[string]string{}
	var mu sync.Mutex
	var wg sync.WaitGroup
	for _, u := range s.upstreams() {
		wg.Add(1)
		go func(u upstream) {
			defer wg.Done()
			state := "ok"
			req, _ := http.NewRequestWithContext(r.Context(), http.MethodGet, u.target.String()+"/health", nil)
			resp, err := s.client.Do(req)
			if err != nil {
				state = "unreachable"
			} else {
				resp.Body.Close()
				if resp.StatusCode != http.StatusOK {
					state = "unhealthy"
				}
			}
			mu.Lock()
			checks[u.name] = state
			mu.Unlock()
		}(u)
	}
	wg.Wait()
	writeJSON(w, http.StatusOK, map[string]any{"status": "ready", "upstreams": checks})
}

// statusRecorder captures the status code written by the next handler.
type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(code int) {
	r.status = code
	r.ResponseWriter.WriteHeader(code)
}

func newRequestID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return "unknown"
	}
	return hex.EncodeToString(b)
}

func routeLabel(path string) string {
	switch {
	case strings.HasPrefix(path, "/api/catalog"):
		return "/api/catalog"
	case strings.HasPrefix(path, "/api/inventory"):
		return "/api/inventory"
	case strings.HasPrefix(path, "/api/orders"):
		return "/api/orders"
	case path == "/health" || path == "/ready" || path == "/metrics":
		return path
	default:
		return "static"
	}
}

// ServeHTTP applies request ID, rate limit, metrics and access logging around the mux.
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	start := time.Now()
	reqID := r.Header.Get("X-Request-ID")
	if reqID == "" {
		reqID = newRequestID()
		r.Header.Set("X-Request-ID", reqID)
	}
	w.Header().Set("X-Request-ID", reqID)
	rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
	route := routeLabel(r.URL.Path)
	s.metrics.inFlight.Add(1)
	defer func() {
		s.metrics.inFlight.Add(-1)
		elapsed := time.Since(start).Seconds()
		s.metrics.Observe(route, r.Method, rec.status, elapsed)
		if route != "/health" && route != "/ready" && route != "/metrics" {
			s.log.Info("request", map[string]any{
				"request_id": reqID, "method": r.Method, "path": r.URL.Path, "status": rec.status,
				"duration_ms": float64(int(elapsed*10000)) / 10, "client": clientIP(r),
			})
		}
	}()

	if strings.HasPrefix(r.URL.Path, "/api/") && !s.limiter.Allow(clientIP(r)) {
		s.metrics.limited.Add(1)
		rec.Header().Set("Retry-After", "1")
		writeJSON(rec, http.StatusTooManyRequests, map[string]string{"detail": "rate limit exceeded"})
		return
	}
	s.mux.ServeHTTP(rec, r)
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}
