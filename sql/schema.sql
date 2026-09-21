CREATE DATABASE IF NOT EXISTS food_commerce
    CHARACTER SET utf8mb4;

USE food_commerce;

CREATE TABLE IF NOT EXISTS products (
    product_id INT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    category VARCHAR(50) NOT NULL,
    price INT UNSIGNED NOT NULL,
    description TEXT NOT NULL,
    sweetness TINYINT UNSIGNED NOT NULL,
    packaging ENUM('individual', 'bulk') NOT NULL,
    storage_method ENUM('room', 'refrigerated', 'frozen') NOT NULL,
    gift_available BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT chk_products_sweetness
        CHECK (sweetness BETWEEN 1 AND 5)
);