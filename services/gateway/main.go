// ShopSphere API gateway: serves the web UI and routes /api/* to the backend services.
package main

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	cfg, err := LoadConfig()
	if err != nil {
		fmt.Fprintf(os.Stdout, `{"level":"ERROR","service":"gateway","msg":%q}`+"\n", err.Error())
		os.Exit(1)
	}
	log := NewLogger(cfg.LogLevel, cfg.Version)
	if _, err := os.Stat(cfg.StaticDir); err != nil {
		log.Warn("static dir not found, UI will return 404", map[string]any{"static_dir": cfg.StaticDir})
	}

	srv := &http.Server{
		Addr:              fmt.Sprintf("0.0.0.0:%d", cfg.Port),
		Handler:           NewServer(cfg, log),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      cfg.UpstreamTimeout + 5*time.Second,
		IdleTimeout:       90 * time.Second,
	}

	go func() {
		log.Info("listening", map[string]any{
			"port": cfg.Port, "catalog": cfg.CatalogURL.String(), "inventory": cfg.InventoryURL.String(),
			"orders": cfg.OrdersURL.String(), "rate_limit_rps": cfg.RateLimitRPS,
		})
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Error("server failed", map[string]any{"error": err.Error()})
			os.Exit(1)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGTERM, syscall.SIGINT)
	sig := <-stop
	log.Info("shutdown signal received, draining connections", map[string]any{
		"signal": sig.String(), "grace_ms": cfg.ShutdownGrace.Milliseconds(),
	})
	ctx, cancel := context.WithTimeout(context.Background(), cfg.ShutdownGrace)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		log.Error("graceful shutdown failed", map[string]any{"error": err.Error()})
		os.Exit(1)
	}
	log.Info("shutdown complete", nil)
}
