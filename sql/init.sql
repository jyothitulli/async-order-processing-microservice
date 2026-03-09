-- Create products table
CREATE TABLE IF NOT EXISTS products (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    stock_quantity INT NOT NULL
);

-- Updated orders table to match models.py
CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    total_amount FLOAT NOT NULL,
    status VARCHAR(50) DEFAULT 'PENDING',
    idempotency_key VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Mandatory Outbox table for the Outbox Relayer
CREATE TABLE IF NOT EXISTS outbox (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(255) NOT NULL,
    payload JSON NOT NULL,
    processed TINYINT(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed initial products
INSERT IGNORE INTO products (id, name, price, stock_quantity) VALUES
('prod-101', 'Laptop Pro', 1200.00, 50),
('prod-102', 'Mechanical Keyboard', 150.00, 100),
('prod-103', 'Gaming Mouse', 75.00, 200);