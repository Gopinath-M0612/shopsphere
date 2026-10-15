'use strict';
// Prometheus metrics exposed on GET /metrics.
const client = require('prom-client');

const register = new client.Registry();
client.collectDefaultMetrics({ register });

const requests = new client.Counter({
  name: 'http_requests_total',
  help: 'HTTP requests handled',
  labelNames: ['service', 'method', 'route', 'status'],
  registers: [register],
});

const latency = new client.Histogram({
  name: 'http_request_duration_seconds',
  help: 'HTTP request latency',
  labelNames: ['service', 'method', 'route'],
  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5],
  registers: [register],
});

const reservations = new client.Counter({
  name: 'inventory_reservations_total',
  help: 'Reservation attempts by result',
  labelNames: ['result'],
  registers: [register],
});

const lowStockSkus = new client.Gauge({
  name: 'inventory_low_stock_skus',
  help: 'Number of SKUs at or below the low-stock threshold',
  registers: [register],
});

module.exports = { register, requests, latency, reservations, lowStockSkus };
