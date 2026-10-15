'use strict';
// Stock levels: list, get one, restock (set on_hand).
const express = require('express');
const config = require('../config');
const db = require('../db');
const log = require('../logger');
const validate = require('../validate');
const { HttpError, asyncHandler } = require('../middleware');

const router = express.Router();

const COLUMNS = `sku, on_hand, reserved, (on_hand - reserved) AS available,
  (on_hand - reserved) <= ${Number(config.lowStockThreshold)} AS low_stock, updated_at`;

router.get('/', asyncHandler(async (req, res) => {
  const onlyLow = req.query.low_stock === 'true';
  const { rows } = await db.pool.query(
    `SELECT ${COLUMNS} FROM stock ${onlyLow ? `WHERE on_hand - reserved <= ${Number(config.lowStockThreshold)}` : ''}
     ORDER BY sku`,
  );
  res.json({ items: rows, low_stock_threshold: config.lowStockThreshold });
}));

router.get('/:sku', asyncHandler(async (req, res) => {
  const sku = validate.sku(req.params.sku);
  const { rows } = await db.pool.query(`SELECT ${COLUMNS} FROM stock WHERE sku = $1`, [sku]);
  if (rows.length === 0) throw new HttpError(404, `sku ${sku} not tracked`);
  res.json(rows[0]);
}));

// Restock / correction: sets the physical quantity on hand.
router.put('/:sku', asyncHandler(async (req, res) => {
  const sku = validate.sku(req.params.sku);
  const onHand = validate.positiveInt(req.body?.on_hand, 'on_hand', { allowZero: true });
  const { rows } = await db.pool.query(
    `INSERT INTO stock (sku, on_hand) VALUES ($1, $2)
     ON CONFLICT (sku) DO UPDATE SET on_hand = EXCLUDED.on_hand, updated_at = now()
     WHERE stock.reserved <= EXCLUDED.on_hand
     RETURNING ${COLUMNS}`,
    [sku, onHand],
  );
  if (rows.length === 0) {
    throw new HttpError(409, `on_hand cannot be lower than the quantity already reserved for ${sku}`);
  }
  log.info('stock set', { sku, on_hand: onHand });
  res.json(rows[0]);
}));

module.exports = router;
