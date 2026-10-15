package main

import (
	"fmt"
	"net/http"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
)

// Metrics is a minimal Prometheus text-format exporter (no external libraries).
type Metrics struct {
	mu        sync.Mutex
	requests  map[string]uint64  // key: route|method|status
	durSum    map[string]float64 // key: route
	durCount  map[string]uint64
	durBucket map[string][]uint64
	limited   atomic.Uint64
	upErrors  map[string]uint64 // key: upstream
	inFlight  atomic.Int64
}

var buckets = []float64{0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5}

func NewMetrics() *Metrics {
	return &Metrics{
		requests:  map[string]uint64{},
		durSum:    map[string]float64{},
		durCount:  map[string]uint64{},
		durBucket: map[string][]uint64{},
		upErrors:  map[string]uint64{},
	}
}

func (m *Metrics) Observe(route, method string, status int, seconds float64) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.requests[fmt.Sprintf("%s|%s|%d", route, method, status)]++
	m.durSum[route] += seconds
	m.durCount[route]++
	b, ok := m.durBucket[route]
	if !ok {
		b = make([]uint64, len(buckets))
		m.durBucket[route] = b
	}
	for i, le := range buckets {
		if seconds <= le {
			b[i]++
		}
	}
}

func (m *Metrics) UpstreamError(name string) {
	m.mu.Lock()
	m.upErrors[name]++
	m.mu.Unlock()
}

func sortedKeys[V any](in map[string]V) []string {
	keys := make([]string, 0, len(in))
	for k := range in {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func (m *Metrics) ServeHTTP(w http.ResponseWriter, _ *http.Request) {
	m.mu.Lock()
	defer m.mu.Unlock()
	var b strings.Builder
	b.WriteString("# HELP http_requests_total HTTP requests handled\n# TYPE http_requests_total counter\n")
	for _, k := range sortedKeys(m.requests) {
		p := strings.SplitN(k, "|", 3)
		fmt.Fprintf(&b, "http_requests_total{service=\"gateway\",route=%q,method=%q,status=%q} %d\n",
			p[0], p[1], p[2], m.requests[k])
	}
	b.WriteString("# HELP http_request_duration_seconds HTTP request latency\n# TYPE http_request_duration_seconds histogram\n")
	for _, route := range sortedKeys(m.durCount) {
		for i, le := range buckets {
			fmt.Fprintf(&b, "http_request_duration_seconds_bucket{service=\"gateway\",route=%q,le=\"%g\"} %d\n",
				route, le, m.durBucket[route][i])
		}
		fmt.Fprintf(&b, "http_request_duration_seconds_bucket{service=\"gateway\",route=%q,le=\"+Inf\"} %d\n", route, m.durCount[route])
		fmt.Fprintf(&b, "http_request_duration_seconds_sum{service=\"gateway\",route=%q} %g\n", route, m.durSum[route])
		fmt.Fprintf(&b, "http_request_duration_seconds_count{service=\"gateway\",route=%q} %d\n", route, m.durCount[route])
	}
	b.WriteString("# HELP gateway_rate_limited_total Requests rejected by the rate limiter\n# TYPE gateway_rate_limited_total counter\n")
	fmt.Fprintf(&b, "gateway_rate_limited_total %d\n", m.limited.Load())
	b.WriteString("# HELP gateway_upstream_errors_total Failed calls to backend services\n# TYPE gateway_upstream_errors_total counter\n")
	for _, k := range sortedKeys(m.upErrors) {
		fmt.Fprintf(&b, "gateway_upstream_errors_total{upstream=%q} %d\n", k, m.upErrors[k])
	}
	b.WriteString("# HELP http_requests_in_flight Requests being processed\n# TYPE http_requests_in_flight gauge\n")
	fmt.Fprintf(&b, "http_requests_in_flight{service=\"gateway\"} %d\n", m.inFlight.Load())
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	w.Write([]byte(b.String()))
}
