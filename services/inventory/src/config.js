'use strict';
// Inventory service configuration. Everything comes from environment variables.

function int(name, def) {
  const raw = process.env[name] ?? String(def);
  const value = Number.parseInt(raw, 10);
  if (Number.isNaN(value)) throw new Error(`config error: ${name} must be an integer, got "${raw}"`);
  return value;
}

function float(name, def) {
  const raw = process.env[name] ?? String(def);
  const value = Number.parseFloat(raw);
  if (Number.isNaN(value)) throw new Error(`config error: ${name} must be a number, got "${raw}"`);
  return value;
}

function load() {
  const databaseUrl = process.env.DATABASE_URL || '';
  if (!databaseUrl) {
    throw new Error('config error: DATABASE_URL is required '
      + '(example: postgresql://inventory:inventory@localhost:5432/inventory)');
  }
  return Object.freeze({
    serviceName: 'inventory',
    version: process.env.APP_VERSION || '1.0.0',
    port: int('PORT', 8002),
    logLevel: (process.env.LOG_LEVEL || 'info').toLowerCase(),
    databaseUrl,
    dbPoolMax: int('DB_POOL_MAX', 10),
    dbConnectTimeoutMs: int('DB_CONNECT_TIMEOUT_MS', 5000),
    lowStockThreshold: int('LOW_STOCK_THRESHOLD', 5),
    runMigrations: (process.env.RUN_MIGRATIONS || 'true').toLowerCase() === 'true',
    shutdownGraceMs: int('SHUTDOWN_GRACE_MS', 10000),
    chaosErrorRate: float('CHAOS_ERROR_RATE', 0),
    chaosLatencyMs: int('CHAOS_LATENCY_MS', 0),
  });
}

module.exports = load();
