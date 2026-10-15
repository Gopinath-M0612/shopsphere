'use strict';
// Small hand-written validators for request bodies.
const { HttpError } = require('./middleware');

const SKU_RE = /^[A-Z0-9-]{3,40}$/;

function sku(value, field = 'sku') {
  if (typeof value !== 'string' || !SKU_RE.test(value)) {
    throw new HttpError(422, `${field} must match ${SKU_RE}`);
  }
  return value;
}

function positiveInt(value, field, { allowZero = false } = {}) {
  if (!Number.isInteger(value) || value < (allowZero ? 0 : 1)) {
    throw new HttpError(422, `${field} must be an integer ${allowZero ? '>= 0' : '>= 1'}`);
  }
  return value;
}

function orderId(value) {
  if (typeof value !== 'string' || value.length < 3 || value.length > 64) {
    throw new HttpError(422, 'order_id must be a string of 3-64 characters');
  }
  return value;
}

function reservationBody(body) {
  if (!body || typeof body !== 'object') throw new HttpError(422, 'body must be a JSON object');
  const id = orderId(body.order_id);
  if (!Array.isArray(body.items) || body.items.length === 0 || body.items.length > 50) {
    throw new HttpError(422, 'items must be a non-empty array (max 50)');
  }
  const merged = new Map();
  body.items.forEach((item, i) => {
    const s = sku(item?.sku, `items[${i}].sku`);
    const q = positiveInt(item?.qty, `items[${i}].qty`);
    merged.set(s, (merged.get(s) || 0) + q);
  });
  // sorted SKU order => rows are always locked in the same order => no deadlocks
  const items = [...merged.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([s, q]) => ({ sku: s, qty: q }));
  return { orderId: id, items };
}

module.exports = { sku, positiveInt, orderId, reservationBody };
