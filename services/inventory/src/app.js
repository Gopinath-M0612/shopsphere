'use strict';
// Builds the Express app (no network listening here, so tests can import it).
const express = require('express');
const middleware = require('./middleware');

function buildApp() {
  const app = express();
  app.disable('x-powered-by');
  app.set('trust proxy', true);
  app.use(middleware.requestContext);
  app.use(express.json({ limit: '100kb' }));
  app.use(require('./routes/health'));
  app.use(middleware.chaos);
  app.use('/stock', require('./routes/stock'));
  app.use('/reservations', require('./routes/reservations'));
  app.use(middleware.notFound);
  app.use(middleware.errorHandler);
  return app;
}

module.exports = { buildApp };
