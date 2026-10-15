CREATE TABLE stock (
    sku         TEXT PRIMARY KEY,
    on_hand     INTEGER NOT NULL CHECK (on_hand >= 0),
    reserved    INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT reserved_le_on_hand CHECK (reserved <= on_hand)
);

CREATE TABLE reservations (
    order_id    TEXT NOT NULL,
    sku         TEXT NOT NULL REFERENCES stock(sku),
    qty         INTEGER NOT NULL CHECK (qty > 0),
    status      TEXT NOT NULL CHECK (status IN ('RESERVED', 'COMMITTED', 'RELEASED')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (order_id, sku)
);

CREATE INDEX idx_reservations_status ON reservations(status);
