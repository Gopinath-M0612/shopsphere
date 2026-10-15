package main

import (
	"encoding/json"
	"os"
	"sync"
	"time"
)

// Logger writes one JSON object per line to stdout.
type Logger struct {
	mu      sync.Mutex
	level   int
	version string
}

var levels = map[string]int{"debug": 10, "info": 20, "warn": 30, "error": 40}

func NewLogger(level, version string) *Logger {
	l, ok := levels[level]
	if !ok {
		l = levels["info"]
	}
	return &Logger{level: l, version: version}
}

func (l *Logger) log(level string, msg string, fields map[string]any) {
	if levels[level] < l.level {
		return
	}
	entry := map[string]any{
		"ts":      time.Now().UTC().Format("2006-01-02T15:04:05.000Z"),
		"level":   map[string]string{"debug": "DEBUG", "info": "INFO", "warn": "WARNING", "error": "ERROR"}[level],
		"service": "gateway",
		"version": l.version,
		"msg":     msg,
	}
	for k, v := range fields {
		entry[k] = v
	}
	line, err := json.Marshal(entry)
	if err != nil {
		line = []byte(`{"level":"ERROR","msg":"log marshal failed"}`)
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	os.Stdout.Write(append(line, '\n'))
}

func (l *Logger) Debug(msg string, f map[string]any) { l.log("debug", msg, f) }
func (l *Logger) Info(msg string, f map[string]any)  { l.log("info", msg, f) }
func (l *Logger) Warn(msg string, f map[string]any)  { l.log("warn", msg, f) }
func (l *Logger) Error(msg string, f map[string]any) { l.log("error", msg, f) }
