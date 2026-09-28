-- 기존 products 테이블은 변경하지 않고 FAQ 테이블만 추가한다.
CREATE TABLE IF NOT EXISTS faqs (
    faq_id INT PRIMARY KEY,
    category VARCHAR(30) NOT NULL,
    question VARCHAR(300) NOT NULL,
    answer TEXT NOT NULL,
    keywords VARCHAR(500) NOT NULL,
    product_id INT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at DATETIME NOT NULL
        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_faqs_product
        FOREIGN KEY (product_id) REFERENCES products(product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
