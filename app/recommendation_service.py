from app.sample_products import PRODUCTS


def filter_products(
    gift_only: bool = False, # 선물 가능한 상품만 검색
    individual_only: bool = False, # 개별포장 상품만 검색
    max_sweetness: int | None = None, # 당도 2 이하만 검색
):
    results = []

    for product in PRODUCTS:
        if gift_only and not product["gift_available"]: # 선물용이 아닌 상품 제외
            continue

        if individual_only and product["packaging"] != "individual":
            continue

        if (
            max_sweetness is not None
            and product["sweetness"] > max_sweetness
        ):
            continue

        results.append(product)

    return results

def extract_conditions(query: str):
    normalized_query = query.replace(" ", "")

    gift_only = "선물" in normalized_query
    individual_only = "개별포장" in normalized_query

    low_sweetness = (
        "너무달지않" in normalized_query
        or "많이달지않" in normalized_query
        or "덜달" in normalized_query
    )

    return {
        "gift_only": gift_only,
        "individual_only": individual_only,
        "max_sweetness": 2 if low_sweetness else None,
    }