'use strict';
// Entry point: wait for the DB, migrate, listen, and shut down cleanly on SIGTERM.
const config = require('./config');
const db = require('./db');
const log = require('./logger');
const { buildApp } = require('./app');

async function main() {
  log.info('starting', {
    port: config.port, chaos_error_rate: config.chaosErrorRate, chaos_latency_ms: config.chaosLatencyMs,
  });
  await db.waitForDb();
  if (config.runMigrations) await db.runMigrations();

  const server = buildApp().listen(config.port, '0.0.0.0', () => {
    log.info('listening', { port: config.port });
  });
  server.keepAliveTimeout = 65000;

  let stopping = false;
  const shutdown = (signal) => {
    if (stopping) return;
    stopping = true;
    log.info('shutdown signal received, draining connections', { signal, grace_ms: config.shutdownGraceMs });
    const force = setTimeout(() => {
      log.error('graceful shutdown timed out, forcing exit');
      process.exit(1);
    }, config.shutdownGraceMs);
    force.unref();
    server.close(async () => {
      await db.pool.end();
      log.info('shutdown complete');
      process.exit(0);
    });
  };
  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));
}

main().catch((err) => {
  log.error('fatal startup error', { error: err.message });
  process.exit(1);
});
