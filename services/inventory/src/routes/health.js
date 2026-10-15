'use strict';
const express = require('express');
const config = require('../config');
const db = require('../db');
const metrics = require('../metrics');
const { asyncHandler } = require('../middleware');

const router = express.Router();

// Liveness: process is up. Never checks dependencies.
router.get('/health', (req, res) => {
  res.json({ status: 'ok', service: config.serviceName, version: config.version });
});

// Readiness: can this replica serve traffic?
router.get('/ready', asyncHandler(async (req, res) => {
  const dbOk = await db.ping();
  res.status(dbOk ? 200 : 503).json({
    status: dbOk ? 'ready' : 'not-ready',
    checks: { database: dbOk ? 'ok' : 'fail' },
  });
}));

router.get('/metrics', asyncHandler(async (req, res) => {
  try {
    const { rows } = await db.pool.query(
      'SELECT count(*)::int AS n FROM stock WHERE on_hand - reserved <= $1', [config.lowStockThreshold],
    );
    metrics.lowStockSkus.set(rows[0].n);
  } catch { /* metrics must still render when the DB is down */ }
  res.set('Content-Type', metrics.register.contentType);
  res.send(await metrics.register.metrics());
}));

module.exports = router;
