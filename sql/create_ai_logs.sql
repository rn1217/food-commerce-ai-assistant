-- 기존 상품/FAQ는 변경하지 않고 요청 기록 테이블만 추가한다.
CREATE TABLE IF NOT EXISTS ai_logs (
    log_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    request_id CHAR(36) NOT NULL UNIQUE,
    feature VARCHAR(30) NOT NULL,
    engine VARCHAR(20) NOT NULL,
    user_query TEXT NOT NULL,
    response JSON NOT NULL,
    latency_ms INT UNSIGNED NOT NULL,
    status VARCHAR(30) NOT NULL,
    http_status SMALLINT UNSIGNED NOT NULL,
    error_code VARCHAR(100) NULL,
    created_at DATETIME(6) NOT NULL,
    INDEX idx_ai_logs_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
