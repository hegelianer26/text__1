CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    item TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO orders (item, quantity)
SELECT 'book', 1
WHERE NOT EXISTS (SELECT 1 FROM orders);

INSERT INTO orders (item, quantity)
SELECT 'notebook', 2
WHERE (SELECT COUNT(*) FROM orders) < 2;

INSERT INTO orders (item, quantity)
SELECT 'pen', 5
WHERE (SELECT COUNT(*) FROM orders) < 3;