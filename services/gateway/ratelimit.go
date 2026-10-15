package main

import (
	"net"
	"net/http"
	"strings"
	"sync"
	"time"
)

// RateLimiter is a per-client-IP token bucket, kept in memory.
// Note: with N gateway replicas the effective limit is N times higher.
type RateLimiter struct {
	mu      sync.Mutex
	rate    float64
	burst   float64
	buckets map[string]*bucket
}

type bucket struct {
	tokens float64
	last   time.Time
}

func NewRateLimiter(rps float64, burst int) *RateLimiter {
	rl := &RateLimiter{rate: rps, burst: float64(burst), buckets: map[string]*bucket{}}
	go rl.cleanup()
	return rl
}

func (rl *RateLimiter) Allow(key string) bool {
	if rl.rate <= 0 {
		return true // disabled
	}
	now := time.Now()
	rl.mu.Lock()
	defer rl.mu.Unlock()
	b, ok := rl.buckets[key]
	if !ok {
		b = &bucket{tokens: rl.burst, last: now}
		rl.buckets[key] = b
	}
	b.tokens += now.Sub(b.last).Seconds() * rl.rate
	if b.tokens > rl.burst {
		b.tokens = rl.burst
	}
	b.last = now
	if b.tokens < 1 {
		return false
	}
	b.tokens--
	return true
}

func (rl *RateLimiter) cleanup() {
	for range time.Tick(time.Minute) {
		rl.mu.Lock()
		for k, b := range rl.buckets {
			if time.Since(b.last) > 5*time.Minute {
				delete(rl.buckets, k)
			}
		}
		rl.mu.Unlock()
	}
}

// clientIP prefers the first X-Forwarded-For hop (set by a load balancer / ingress).
func clientIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		return strings.TrimSpace(strings.Split(xff, ",")[0])
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}
