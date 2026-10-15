'use strict';
// Request ID, access log, metrics, chaos (fault injection) and error handling.
const crypto = require('node:crypto');
const config = require('./config');
const log = require('./logger');
const metrics = require('./metrics');

const QUIET = new Set(['/health', '/ready', '/metrics']);

class HttpError extends Error {
  constructor(status, message, details) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

function requestContext(req, res, next) {
  const requestId = req.get('x-request-id') || crypto.randomUUID().replace(/-/g, '');
  res.set('x-request-id', requestId);
  log.context.run({ requestId }, () => {
    const start = process.hrtime.bigint();
    res.on('finish', () => {
      const seconds = Number(process.hrtime.bigint() - start) / 1e9;
      const route = req.route ? `${req.baseUrl}${req.route.path}` : 'unmatched';
      metrics.requests.inc({ service: config.serviceName, method: req.method, route, status: res.statusCode });
      metrics.latency.observe({ service: config.serviceName, method: req.method, route }, seconds);
      if (!QUIET.has(req.path)) {
        log.context.run({ requestId }, () => log.info('request', {
          method: req.method, path: req.originalUrl, status: res.statusCode,
          duration_ms: Math.round(seconds * 10000) / 10, client: req.ip,
        }));
      }
    });
    next();
  });
}

function chaos(req, res, next) {
  if (QUIET.has(req.path)) return next();
  const proceed = () => {
    if (config.chaosErrorRate > 0 && Math.random() < config.chaosErrorRate) {
      log.error('chaos: injected failure');
      return res.status(500).json({ detail: 'injected failure (chaos)' });
    }
    return next();
  };
  if (config.chaosLatencyMs > 0) return setTimeout(proceed, config.chaosLatencyMs);
  return proceed();
}

// Wrap async route handlers so rejected promises reach the error handler.
const asyncHandler = (fn) => (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next);

function notFound(req, res) {
  res.status(404).json({ detail: `route ${req.method} ${req.path} not found` });
}

// eslint-disable-next-line no-unused-vars
function errorHandler(err, req, res, next) {
  if (err instanceof HttpError) {
    return res.status(err.status).json({ detail: err.message, ...(err.details ? { details: err.details } : {}) });
  }
  if (err.type === 'entity.parse.failed') {
    return res.status(400).json({ detail: 'request body is not valid JSON' });
  }
  log.error('unhandled error', { error: err.message, stack: err.stack });
  return res.status(500).json({ detail: 'internal error', request_id: res.get('x-request-id') });
}

module.exports = { HttpError, requestContext, chaos, asyncHandler, notFound, errorHandler };
