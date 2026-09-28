import json

from app.database import get_connection


def insert_request_log(record: dict):
    # JSON 응답은 문자열로 직렬화해 JSON 컬럼에 넣는다.
    # 질문이나 오류 내용을 SQL 문자열에 직접 붙이지 않는다.
    sql = """
        INSERT INTO ai_logs (
            request_id, feature, engine, user_query, response,
            latency_ms, status, http_status, error_code, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    values = (
        record["request_id"], record["feature"], record["engine"],
        record["user_query"], json.dumps(record["response"], ensure_ascii=False),
        record["latency_ms"], record["status"], record["http_status"],
        record["error_code"], record["created_at"],
    )
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, values)
        # INSERT는 commit해야 연결 종료 후에도 DB에 남는다.
        connection.commit()
