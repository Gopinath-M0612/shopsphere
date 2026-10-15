'use strict';
// PostgreSQL pool, startup retry and a tiny SQL migration runner.
const fs = require('node:fs');
const path = require('node:path');
const { Pool } = require('pg');
const config = require('./config');
const log = require('./logger');

const MIGRATIONS_DIR = path.join(__dirname, '..', 'migrations');

const pool = new Pool({
  connectionString: config.databaseUrl,
  max: config.dbPoolMax,
  connectionTimeoutMillis: config.dbConnectTimeoutMs,
  idleTimeoutMillis: 30000,
});

pool.on('error', (err) => log.error('idle database client error', { error: err.message }));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitForDb(maxAttempts = 10, delayMs = 2000) {
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      await pool.query('SELECT 1');
      log.info('database reachable', { attempt });
      return;
    } catch (err) {
      log.warn('database not reachable yet', { attempt, max_attempts: maxAttempts, error: err.message });
      if (attempt === maxAttempts) throw new Error(`database unreachable after ${maxAttempts} attempts`);
      await sleep(delayMs);
    }
  }
}

async function runMigrations() {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    await client.query(`CREATE TABLE IF NOT EXISTS schema_migrations (
      version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())`);
    await client.query('SELECT pg_advisory_xact_lock(424202)');
    const { rows } = await client.query('SELECT version FROM schema_migrations');
    const applied = new Set(rows.map((r) => r.version));
    const files = fs.readdirSync(MIGRATIONS_DIR).filter((f) => f.endsWith('.sql')).sort();
    for (const file of files) {
      const version = path.basename(file, '.sql');
      if (applied.has(version)) continue;
      log.info('applying migration', { version });
      await client.query(fs.readFileSync(path.join(MIGRATIONS_DIR, file), 'utf8'));
      await client.query('INSERT INTO schema_migrations(version) VALUES ($1)', [version]);
    }
    await client.query('COMMIT');
    log.info('migrations complete');
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}

async function ping() {
  try {
    await pool.query('SELECT 1');
    return true;
  } catch (err) {
    log.error('database ping failed', { error: err.message });
    return false;
  }
}

// Run fn(client) inside a transaction; commit on success, roll back on any error.
async function withTransaction(fn) {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const result = await fn(client);
    await client.query('COMMIT');
    return result;
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}

module.exports = { pool, waitForDb, runMigrations, ping, withTransaction };
