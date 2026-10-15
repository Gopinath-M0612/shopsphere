'use strict';
// Minimal structured JSON logger: one JSON object per line on stdout.
const { AsyncLocalStorage } = require('node:async_hooks');
const config = require('./config');

const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };
const threshold = LEVELS[config.logLevel] ?? LEVELS.info;
const context = new AsyncLocalStorage();

function write(level, msg, fields = {}) {
  if (LEVELS[level] < threshold) return;
  const store = context.getStore();
  const line = {
    ts: new Date().toISOString(),
    level: level.toUpperCase(),
    service: config.serviceName,
    version: config.version,
    request_id: store?.requestId ?? '-',
    msg,
    ...fields,
  };
  process.stdout.write(`${JSON.stringify(line)}\n`);
}

module.exports = {
  context,
  debug: (msg, f) => write('debug', msg, f),
  info: (msg, f) => write('info', msg, f),
  warn: (msg, f) => write('warn', msg, f),
  error: (msg, f) => write('error', msg, f),
};
