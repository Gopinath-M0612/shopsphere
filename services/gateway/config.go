package main

import (
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

// Config holds every setting; all values come from environment variables.
type Config struct {
	Version         string
	Port            int
	LogLevel        string
	StaticDir       string
	CatalogURL      *url.URL
	InventoryURL    *url.URL
	OrdersURL       *url.URL
	UpstreamTimeout time.Duration
	RateLimitRPS    float64
	RateLimitBurst  int
	ShutdownGrace   time.Duration
}

func envInt(name string, def int) (int, error) {
	raw := os.Getenv(name)
	if raw == "" {
		return def, nil
	}
	v, err := strconv.Atoi(raw)
	if err != nil {
		return 0, fmt.Errorf("config error: %s must be an integer, got %q", name, raw)
	}
	return v, nil
}

func envFloat(name string, def float64) (float64, error) {
	raw := os.Getenv(name)
	if raw == "" {
		return def, nil
	}
	v, err := strconv.ParseFloat(raw, 64)
	if err != nil {
		return 0, fmt.Errorf("config error: %s must be a number, got %q", name, raw)
	}
	return v, nil
}

func envURL(name, example string) (*url.URL, error) {
	raw := strings.TrimRight(os.Getenv(name), "/")
	if raw == "" {
		return nil, fmt.Errorf("config error: %s is required (example: %s)", name, example)
	}
	u, err := url.Parse(raw)
	if err != nil || u.Scheme == "" || u.Host == "" {
		return nil, fmt.Errorf("config error: %s is not a valid URL: %q", name, raw)
	}
	return u, nil
}

func envOr(name, def string) string {
	if v := os.Getenv(name); v != "" {
		return v
	}
	return def
}

// LoadConfig reads and validates the environment. Any error stops the gateway at startup.
func LoadConfig() (*Config, error) {
	var err error
	c := &Config{
		Version:   envOr("APP_VERSION", "1.0.0"),
		LogLevel:  strings.ToLower(envOr("LOG_LEVEL", "info")),
		StaticDir: envOr("STATIC_DIR", "./public"),
	}
	if c.Port, err = envInt("PORT", 8080); err != nil {
		return nil, err
	}
	if c.CatalogURL, err = envURL("CATALOG_URL", "http://localhost:8001"); err != nil {
		return nil, err
	}
	if c.InventoryURL, err = envURL("INVENTORY_URL", "http://localhost:8002"); err != nil {
		return nil, err
	}
	if c.OrdersURL, err = envURL("ORDERS_URL", "http://localhost:8003"); err != nil {
		return nil, err
	}
	timeoutMs, err := envInt("UPSTREAM_TIMEOUT_MS", 5000)
	if err != nil {
		return nil, err
	}
	c.UpstreamTimeout = time.Duration(timeoutMs) * time.Millisecond
	if c.RateLimitRPS, err = envFloat("RATE_LIMIT_RPS", 20); err != nil {
		return nil, err
	}
	if c.RateLimitBurst, err = envInt("RATE_LIMIT_BURST", 40); err != nil {
		return nil, err
	}
	graceMs, err := envInt("SHUTDOWN_GRACE_MS", 10000)
	if err != nil {
		return nil, err
	}
	c.ShutdownGrace = time.Duration(graceMs) * time.Millisecond
	return c, nil
}
