package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"
)

func testServer(t *testing.T, backend http.Handler, rps float64, burst int) *httptest.Server {
	t.Helper()
	be := httptest.NewServer(backend)
	t.Cleanup(be.Close)
	u, _ := url.Parse(be.URL)
	cfg := &Config{
		Version: "test", StaticDir: t.TempDir(), CatalogURL: u, InventoryURL: u, OrdersURL: u,
		UpstreamTimeout: time.Second, RateLimitRPS: rps, RateLimitBurst: burst, LogLevel: "error",
	}
	gw := httptest.NewServer(NewServer(cfg, NewLogger("error", "test")))
	t.Cleanup(gw.Close)
	return gw
}

func echoPath() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, r.URL.Path+"|"+r.Header.Get("X-Request-ID"))
	})
}

func TestHealth(t *testing.T) {
	gw := testServer(t, echoPath(), 0, 0)
	resp, err := http.Get(gw.URL + "/health")
	if err != nil || resp.StatusCode != 200 {
		t.Fatalf("health failed: %v %v", err, resp)
	}
}

func TestProxyStripsPrefixAndForwardsRequestID(t *testing.T) {
	gw := testServer(t, echoPath(), 0, 0)
	req, _ := http.NewRequest("GET", gw.URL+"/api/catalog/products/by-sku/EL-1001", nil)
	req.Header.Set("X-Request-ID", "abc123")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	body, _ := io.ReadAll(resp.Body)
	if string(body) != "/products/by-sku/EL-1001|abc123" {
		t.Fatalf("unexpected upstream view: %q", body)
	}
}

func TestInternalRoutesAreBlocked(t *testing.T) {
	gw := testServer(t, echoPath(), 0, 0)
	resp, _ := http.Get(gw.URL + "/api/orders/internal/orders/x/status")
	if resp.StatusCode != http.StatusNotFound {
		t.Fatalf("internal route reachable: %d", resp.StatusCode)
	}
}

func TestRateLimit(t *testing.T) {
	gw := testServer(t, echoPath(), 1, 2)
	codes := []int{}
	for i := 0; i < 4; i++ {
		resp, _ := http.Get(gw.URL + "/api/catalog/products")
		codes = append(codes, resp.StatusCode)
	}
	if codes[0] != 200 || codes[3] != http.StatusTooManyRequests {
		t.Fatalf("rate limit not applied: %v", codes)
	}
}

func TestBackendDownGives502(t *testing.T) {
	gw := testServer(t, echoPath(), 0, 0)
	cfgDead, _ := url.Parse("http://127.0.0.1:1")
	s := NewServer(&Config{Version: "t", StaticDir: t.TempDir(), CatalogURL: cfgDead, InventoryURL: cfgDead,
		OrdersURL: cfgDead, UpstreamTimeout: time.Second}, NewLogger("error", "t"))
	_ = gw
	rec := httptest.NewRecorder()
	s.ServeHTTP(rec, httptest.NewRequest("GET", "/api/catalog/products", nil))
	if rec.Code != http.StatusBadGateway || !strings.Contains(rec.Body.String(), "catalog") {
		t.Fatalf("expected 502 mentioning catalog, got %d %s", rec.Code, rec.Body.String())
	}
}

func TestMetricsEndpoint(t *testing.T) {
	gw := testServer(t, echoPath(), 0, 0)
	http.Get(gw.URL + "/api/catalog/products")
	resp, _ := http.Get(gw.URL + "/metrics")
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), `http_requests_total{service="gateway",route="/api/catalog"`) {
		t.Fatalf("metrics missing: %s", body)
	}
}
