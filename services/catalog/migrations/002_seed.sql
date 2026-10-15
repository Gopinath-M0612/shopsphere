INSERT INTO categories (slug, name) VALUES
    ('electronics', 'Electronics'),
    ('home', 'Home & Kitchen'),
    ('books', 'Books'),
    ('fitness', 'Sports & Fitness');

INSERT INTO products (sku, name, description, price, category_id) VALUES
    ('EL-1001', 'Wireless Earbuds', 'Bluetooth 5.3 earbuds with 30h battery', 1999.00, (SELECT id FROM categories WHERE slug='electronics')),
    ('EL-1002', 'Smart Watch', 'Heart-rate, SpO2 and sleep tracking', 3499.00, (SELECT id FROM categories WHERE slug='electronics')),
    ('EL-1003', 'Power Bank 20000mAh', 'Fast charging, dual USB-C', 1499.00, (SELECT id FROM categories WHERE slug='electronics')),
    ('EL-1004', 'USB-C Cable 2m', 'Braided, 60W', 299.00, (SELECT id FROM categories WHERE slug='electronics')),
    ('HM-2001', 'Steel Water Bottle', '1 litre, keeps cold 24h', 549.00, (SELECT id FROM categories WHERE slug='home')),
    ('HM-2002', 'Non-stick Tawa', '28 cm, induction friendly', 899.00, (SELECT id FROM categories WHERE slug='home')),
    ('HM-2003', 'LED Desk Lamp', '3 colour modes, dimmable', 1199.00, (SELECT id FROM categories WHERE slug='home')),
    ('BK-3001', 'Kubernetes in Action', 'Hands-on Kubernetes guide', 2899.00, (SELECT id FROM categories WHERE slug='books')),
    ('BK-3002', 'The Phoenix Project', 'A novel about IT and DevOps', 699.00, (SELECT id FROM categories WHERE slug='books')),
    ('BK-3003', 'Site Reliability Engineering', 'How Google runs production systems', 3199.00, (SELECT id FROM categories WHERE slug='books')),
    ('FT-4001', 'Yoga Mat 6mm', 'Anti-slip, with carry strap', 799.00, (SELECT id FROM categories WHERE slug='fitness')),
    ('FT-4002', 'Adjustable Dumbbells', '2 x 10 kg set', 2499.00, (SELECT id FROM categories WHERE slug='fitness'));
