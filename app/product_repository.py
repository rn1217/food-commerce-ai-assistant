from app.database import get_connection


# 상품 조회 SQL을 API 코드와 분리해 관리한다.
def get_active_products():
    # 활성 상품만 가져오고, 화면에서 순서가 일정하도록 상품 ID로 정렬한다.
    sql = """
        SELECT
            product_id,
            name,
            category,
            price,
            description,
            sweetness,
            packaging,
            storage_method,
            gift_available
        FROM products
        WHERE is_active = %s
        ORDER BY product_id
    """

    # 정상 처리나 예외 발생 후에도 with 블록을 벗어나면 연결을 닫는다.
    with get_connection() as connection:
        # cursor는 SQL을 실행하고 결과를 읽는 객체이며, 사용 후 함께 닫는다.
        with connection.cursor() as cursor:
            # %s에 값을 별도 전달한다. f-string으로 값을 SQL에 직접 붙이지 않는다.
            # (True,)는 원소가 하나인 튜플이며 is_active 조건에 사용된다.
            cursor.execute(sql, (True,))
            # 조회된 모든 행을 가져온다. DictCursor이므로 각 행은 딕셔너리다.
            products = cursor.fetchall()

    # MySQL의 0/1 값을 Python의 False/True로 바꿔 JSON에서도 불리언으로 응답한다.
    for product in products:
        product["gift_available"] = bool(product["gift_available"])

    # 조회 결과가 없으면 빈 결과를 반환하고, DB 오류는 호출한 API 쪽으로 전달된다.
    # SELECT 조회만 하므로 데이터를 저장하는 commit()은 필요하지 않다.
    return products

def search_products(
    gift_only: bool = False,
    individual_only: bool = False,
    max_sweetness: int | None = None,
    exclude_individual: bool = False,
    min_price: int | None = None,
    max_price: int | None = None,
    sort: str = "default",
):
    # ORDER BY는 값 바인딩이 불가능하므로 개발자가 정한 구문만 선택한다.
    order_options = {"default": "product_id", "price_asc": "price ASC, product_id ASC",
                     "price_desc": "price DESC, product_id ASC"}
    if sort not in order_options:
        raise ValueError("unsupported sort")
    # 모든 검색에서 활성 상품만 대상으로 한다.
    conditions = ["is_active = %s"]
    params = [True]

    # 사용자가 요청한 조건만 SQL에 추가한다.
    if gift_only:
        conditions.append("gift_available = %s")
        params.append(True)

    if individual_only:
        conditions.append("packaging = %s")
        params.append("individual")

    if max_sweetness is not None:
        conditions.append("sweetness <= %s")
        params.append(max_sweetness)

    if exclude_individual:
        conditions.append("packaging <> %s")
        params.append("individual")
    if min_price is not None:
        conditions.append("price >= %s")
        params.append(min_price)
    if max_price is not None:
        conditions.append("price <= %s")
        params.append(max_price)

    # 조건들을 AND로 연결해 모두 만족하는 상품을 찾는다.
    where_clause = " AND ".join(conditions)

    sql = f"""
        SELECT
            product_id,
            name,
            category,
            price,
            description,
            sweetness,
            packaging,
            storage_method,
            gift_available
        FROM products
        WHERE {where_clause}
        ORDER BY {order_options[sort]}
    """

    with get_connection() as connection:
        with connection.cursor() as cursor:
            # 값은 SQL 문자열에 넣지 않고 별도 인자로 전달한다.
            cursor.execute(sql, tuple(params))
            products = cursor.fetchall()

    for product in products:
        product["gift_available"] = bool(product["gift_available"])

    return products
