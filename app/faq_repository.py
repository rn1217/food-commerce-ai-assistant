from app.database import get_connection


def get_common_faqs():
    # 현재 API는 공통 FAQ만 검색한다. 상품을 지정하지 않은 요청에
    # 특정 상품 전용 보관/해동 안내가 섞이지 않도록 범위를 제한한다.
    sql = """
        SELECT faq_id, category, question, answer, keywords
        FROM faqs
        WHERE is_active = %s AND product_id IS NULL
        ORDER BY faq_id
    """
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, (True,))
            return cursor.fetchall()
