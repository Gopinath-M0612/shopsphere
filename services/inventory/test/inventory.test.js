'use strict';
// Integration tests: need a real PostgreSQL in DATABASE_URL.
//   DATABASE_URL=postgresql://inventory:inventory@localhost:5432/inventory_test npm test
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const db = require('../src/db');
const { buildApp } = require('../src/app');

let server;
let base;

before(async () => {
  await db.waitForDb(3, 500);
  await db.runMigrations();
  await db.pool.query("INSERT INTO stock (sku, on_hand) VALUES ('TST-0001', 10) "
    + 'ON CONFLICT (sku) DO UPDATE SET on_hand = 10, reserved = 0');
  await db.pool.query("DELETE FROM reservations WHERE order_id LIKE 'test-%'");
  server = buildApp().listen(0);
  base = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
  server.close();
  await db.pool.end();
});

const json = (method, path, body) => fetch(`${base}${path}`, {
  method, headers: { 'content-type': 'application/json' }, body: body ? JSON.stringify(body) : undefined,
});

test('health is ok', async () => {
  const r = await fetch(`${base}/health`);
  assert.equal(r.status, 200);
  assert.equal((await r.json()).service, 'inventory');
});

test('reserve, replay, commit', async () => {
  const order = `test-${Date.now()}`;
  let r = await json('POST', '/reservations', { order_id: order, items: [{ sku: 'TST-0001', qty: 3 }] });
  assert.equal(r.status, 201);
  r = await json('POST', '/reservations', { order_id: order, items: [{ sku: 'TST-0001', qty: 3 }] });
  assert.equal(r.status, 200, 'second call with same order_id is an idempotent replay');
  let stock = await (await fetch(`${base}/stock/TST-0001`)).json();
  assert.equal(stock.reserved, 3);
  r = await json('POST', `/reservations/${order}/commit`);
  assert.equal((await r.json()).status, 'COMMITTED');
  stock = await (await fetch(`${base}/stock/TST-0001`)).json();
  assert.equal(stock.on_hand, 7);
  assert.equal(stock.reserved, 0);
});

test('insufficient stock is 409 with details', async () => {
  const r = await json('POST', '/reservations', { order_id: `test-big-${Date.now()}`, items: [{ sku: 'TST-0001', qty: 999 }] });
  assert.equal(r.status, 409);
  const body = await r.json();
  assert.equal(body.details[0].sku, 'TST-0001');
});

test('release returns stock', async () => {
  const order = `test-rel-${Date.now()}`;
  await json('POST', '/reservations', { order_id: order, items: [{ sku: 'TST-0001', qty: 2 }] });
  const r = await json('DELETE', `/reservations/${order}`);
  assert.equal((await r.json()).status, 'RELEASED');
});

test('validation rejects bad qty', async () => {
  const r = await json('POST', '/reservations', { order_id: 'test-bad', items: [{ sku: 'TST-0001', qty: 0 }] });
  assert.equal(r.status, 422);
});
