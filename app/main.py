import logging
import pymysql
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.product_repository import get_active_products, search_products
from app.recommendation_service import extract_conditions

# HTTP 요청을 받을 FastAPI 앱 생성
app = FastAPI(title="Food Commerce AI Assistant")
# Uvicorn의 로거를 사용해 서버 터미널에 오류 원인을 남긴다.
logger = logging.getLogger("uvicorn.error")

# POST 요청 본문의 JSON을 검사하는 모델. DB 테이블을 정의하는 클래스는 아니다.=
class RecommendationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True) # 문자열 앞뒤 공백 제거

    query: str = Field(min_length=1, max_length=500) # 공백 제거 후 길이가 1~500자여야 한다.

# 질문 → 조건 추출 → Python 가상 상품 검색 → JSON 응답
@app.post("/api/recommendations")
def recommend_products(request: RecommendationRequest):
    conditions = extract_conditions(request.query) # 질문을 검색 조건 딕셔너리로 바꿈

    has_condition = ( # 인식한 조건이 하나라도 있는지 저장
        conditions["gift_only"]
        or conditions["individual_only"]
        or conditions["max_sweetness"] is not None # 당도 제한이 지정돼 있는지 확인
    )

    # 인식한 조건이 없으면 전체 상품을 잘못 추천하지 않도록 여기서 종료한다.
    if not has_condition: 
        return {
            "query": request.query,
            "conditions": conditions,
            "count": 0,
            "products": [],
            "message": (
                "검색 조건을 찾지 못했습니다. "
                "'선물', '개별포장', '너무 달지 않은' "
                "조건을 포함해 질문해 주세요."
            ),
        }

    # 추출한 조건을 전달해 MySQL의 실제 상품을 검색한다.
    try:
        products = search_products(**conditions)
    except pymysql.MySQLError:
        logger.exception("추천 후보 검색 중 MySQL 오류 발생")
        raise HTTPException(
            status_code=503,
            detail="추천 상품을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
        )

    # 빈 리스트는 False로 평가되므로 결과 없음 안내를 구분할 수 있다.
    if products:
        message = "조건에 맞는 상품을 찾았습니다."
    else:
        message = "조건에 맞는 상품이 없습니다."

    return {
        "query": request.query,
        "conditions": conditions,
        "count": len(products),
        "products": products,
        "message": message,
    }

# 상품 조회는 실제 MySQL을 사용한다: API → repository → database → MySQL.
@app.get("/api/products")
def list_products():
    try:
        # SQL 실행은 repository에 맡기고, 여기서는 요청과 응답을 처리한다.
        products = get_active_products()
    # MySQL 연결/조회 오류를 처리한다. 환경변수 누락 등 모든 오류를 잡는 것은 아니다.
    except pymysql.MySQLError:
        # traceback(오류 발생 경로)은 서버에 기록하고 사용자에게 그대로 보내지 않는다.
        logger.exception("상품 조회 중 MySQL 오류 발생")
        raise HTTPException(
            status_code=503,
            detail="상품 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
        )

    # 딕셔너리와 상품 리스트를 FastAPI가 JSON 응답으로 변환한다.
    return {
        "count": len(products),
        "products": products,
    }

# 서버의 HTTP 응답만 확인한다. DB 연결 상태까지 검사하는 API는 아니다.
@app.get("/health")
def health_check(): #요청 처리할 함수 정의
    return {"status": "ok"} #응답 딕셔너리

@app.get("/hello")
def say_hello(name: str = "방문자"):
    return {"message": f"{name}님, 안녕하세요!"}