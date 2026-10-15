'use strict';
// Reservations: hold stock for an order, then commit (shipped) or release (cancelled).
//
//   reserve  : reserved += qty                 (status RESERVED)
//   commit   : on_hand -= qty, reserved -= qty  (status COMMITTED)
//   release  : reserved -= qty                 (status RELEASED)
const express = require('express');
const db = require('../db');
const log = require('../logger');
const metrics = require('../metrics');
const validate = require('../validate');
const { HttpError, asyncHandler } = require('../middleware');

const router = express.Router();

async function loadReservation(client, orderId) {
  const { rows } = await client.query(
    'SELECT sku, qty, status FROM reservations WHERE order_id = $1 ORDER BY sku', [orderId],
  );
  return rows;
}

function summary(orderId, rows) {
  return { order_id: orderId, status: rows[0]?.status ?? null, items: rows.map(({ sku, qty }) => ({ sku, qty })) };
}

router.post('/', asyncHandler(async (req, res) => {
  const { orderId, items } = validate.reservationBody(req.body);

  const result = await db.withTransaction(async (client) => {
    // idempotency: the orders service may retry the same call after a timeout
    const existing = await loadReservation(client, orderId);
    if (existing.length > 0) return { replay: true, rows: existing };

    const shortages = [];
    for (const item of items) {
      const { rows } = await client.query(
        'SELECT on_hand, reserved FROM stock WHERE sku = $1 FOR UPDATE', [item.sku],
      );
      if (rows.length === 0) {
        shortages.push({ sku: item.sku, requested: item.qty, available: 0, reason: 'not tracked' });
        continue;
      }
      const available = rows[0].on_hand - rows[0].reserved;
      if (available < item.qty) {
        shortages.push({ sku: item.sku, requested: item.qty, available, reason: 'insufficient stock' });
      }
    }
    if (shortages.length > 0) {
      metrics.reservations.inc({ result: 'rejected' });
      throw new HttpError(409, 'insufficient stock', shortages);
    }

    for (const item of items) {
      await client.query('UPDATE stock SET reserved = reserved + $2, updated_at = now() WHERE sku = $1',
        [item.sku, item.qty]);
      await client.query(
        "INSERT INTO reservations (order_id, sku, qty, status) VALUES ($1, $2, $3, 'RESERVED')",
        [orderId, item.sku, item.qty],
      );
    }
    return { replay: false, rows: await loadReservation(client, orderId) };
  });

  if (result.replay) {
    metrics.reservations.inc({ result: 'replay' });
    return res.status(200).json(summary(orderId, result.rows));
  }
  metrics.reservations.inc({ result: 'reserved' });
  log.info('stock reserved', { order_id: orderId, items });
  return res.status(201).json(summary(orderId, result.rows));
}));

router.get('/:orderId', asyncHandler(async (req, res) => {
  const orderId = validate.orderId(req.params.orderId);
  const rows = await loadReservation(db.pool, orderId);
  if (rows.length === 0) throw new HttpError(404, `no reservation for order ${orderId}`);
  res.json(summary(orderId, rows));
}));

async function transition(orderId, target) {
  return db.withTransaction(async (client) => {
    const rows = await loadReservation(client, orderId);
    if (rows.length === 0) throw new HttpError(404, `no reservation for order ${orderId}`);
    const current = rows[0].status;
    if (current === target) return { changed: false, rows };
    if (current !== 'RESERVED') {
      throw new HttpError(409, `reservation for order ${orderId} is ${current}, cannot move to ${target}`);
    }
    for (const { sku, qty } of rows) {
      await client.query('SELECT 1 FROM stock WHERE sku = $1 FOR UPDATE', [sku]);
      if (target === 'COMMITTED') {
        await client.query(
          'UPDATE stock SET on_hand = on_hand - $2, reserved = reserved - $2, updated_at = now() WHERE sku = $1',
          [sku, qty],
        );
      } else {
        await client.query('UPDATE stock SET reserved = reserved - $2, updated_at = now() WHERE sku = $1',
          [sku, qty]);
      }
    }
    await client.query('UPDATE reservations SET status = $2, updated_at = now() WHERE order_id = $1',
      [orderId, target]);
    return { changed: true, rows: await loadReservation(client, orderId) };
  });
}

router.post('/:orderId/commit', asyncHandler(async (req, res) => {
  const orderId = validate.orderId(req.params.orderId);
  const { changed, rows } = await transition(orderId, 'COMMITTED');
  if (changed) {
    metrics.reservations.inc({ result: 'committed' });
    log.info('reservation committed', { order_id: orderId });
  }
  res.json(summary(orderId, rows));
}));

router.delete('/:orderId', asyncHandler(async (req, res) => {
  const orderId = validate.orderId(req.params.orderId);
  const { changed, rows } = await transition(orderId, 'RELEASED');
  if (changed) {
    metrics.reservations.inc({ result: 'released' });
    log.info('reservation released', { order_id: orderId });
  }
  res.json(summary(orderId, rows));
}));

module.exports = router;
