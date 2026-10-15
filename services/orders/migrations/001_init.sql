CREATE TABLE orders (
    id              TEXT PRIMARY KEY,
    customer_email  TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('PENDING', 'CONFIRMED', 'SHIPPED', 'CANCELLED')),
    total           NUMERIC(12, 2) NOT NULL CHECK (total >= 0),
    currency        CHAR(3) NOT NULL DEFAULT 'INR',
    cancel_reason   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE order_items (
    order_id    TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    sku         TEXT NOT NULL,
    name        TEXT NOT NULL,
    unit_price  NUMERIC(10, 2) NOT NULL,
    qty         INTEGER NOT NULL CHECK (qty > 0),
    PRIMARY KEY (order_id, sku)
);

CREATE TABLE outbox (
    id            BIGSERIAL PRIMARY KEY,
    event_type    TEXT NOT NULL,
    payload       JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at  TIMESTAMPTZ
);

CREATE INDEX idx_orders_email ON orders(customer_email);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_outbox_unpublished ON outbox(id) WHERE published_at IS NULL;
