import logging
from time import perf_counter
from uuid import uuid4

import pymysql
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.product_repository import get_active_products, search_products
from app.recommendation_service import extract_conditions
from app.faq_service import search_faqs
from app.log_service import record_request


app = FastAPI(title="Food Commerce AI Assistant")
logger = logging.getLogger("uvicorn.error")


# 입력 검증 실패 시 함수에 들어오기 전에 422로 반환한다.
class RecommendationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=500)


@app.post("/api/recommendations")
def recommend_products(request: RecommendationRequest):
    started_at = perf_counter()
    request_id = str(uuid4())
    # 예기치 않은 실패까지 기록할 수 있도록 기본 상태를 오류로 준비한다.
    status, http_status, error_code = "error", 500, None
    response = {"detail": "추천 요청 처리 중 오류가 발생했습니다."}

    try:
        conditions = extract_conditions(request.query)
        has_condition = (
            conditions["gift_only"]
            or conditions["individual_only"]
            or conditions["max_sweetness"] is not None
        )
        if not has_condition:
            products = []
            status = "unsupported"
            message = (
                "검색 조건을 찾지 못했습니다. "
                "'선물', '개별포장', '너무 달지 않은' "
                "조건을 포함해 질문해 주세요."
            )
        else:
            products = search_products(**conditions)
            status = "success" if products else "no_match"
            message = "조건에 맞는 상품을 찾았습니다." if products else "조건에 맞는 상품이 없습니다."

        http_status = 200
        response = {
            "request_id": request_id,
            "query": request.query,
            "conditions": conditions,
            "count": len(products),
            "products": products,
            "message": message,
        }
        return response
    except pymysql.MySQLError as exc:
        status, http_status, error_code = "error", 503, type(exc).__name__
        response = {"detail": "추천 상품을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."}
        logger.exception("추천 후보 검색 중 MySQL 오류 request_id=%s", request_id)
        raise HTTPException(503, response["detail"], headers={"X-Request-ID": request_id}) from exc
    except Exception as exc:
        status, http_status, error_code = "error", 500, type(exc).__name__
        response = {"detail": "추천 요청 처리 중 오류가 발생했습니다."}
        logger.exception("추천 요청 처리 오류 request_id=%s", request_id)
        raise HTTPException(500, response["detail"], headers={"X-Request-ID": request_id}) from exc
    finally:
        # return이나 예외가 있어도 실행된다. 한 요청에 한 번만 기록한다.
        record_request(
            request_id=request_id, feature="recommendation", query=request.query,
            response=response, started_at=started_at, status=status,
            http_status=http_status, error_code=error_code,
        )


@app.get("/api/products")
def list_products():
    try:
        products = get_active_products()
    except pymysql.MySQLError:
        logger.exception("상품 조회 중 MySQL 오류 발생")
        raise HTTPException(
            status_code=503,
            detail="상품 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
        )
    return {"count": len(products), "products": products}


# HTTP 응답만 확인하며 DB 상태를 검사하지 않는다.
@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/hello")
def say_hello(name: str = "방문자"):
    return {"message": f"{name}님, 안녕하세요!"}


class FaqSearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=500)


@app.post("/api/faq/search")
def find_faq(request: FaqSearchRequest):
    started_at = perf_counter()
    request_id = str(uuid4())
    status, http_status, error_code = "error", 500, None
    response = {"detail": "FAQ 요청 처리 중 오류가 발생했습니다."}

    try:
        response = search_faqs(request.query)
        response["request_id"] = request_id
        # API의 matched는 로그에서는 공통 상태 success로 저장한다.
        status = "success" if response["status"] == "matched" else response["status"]
        http_status = 200
        return response
    except pymysql.MySQLError as exc:
        status, http_status, error_code = "error", 503, type(exc).__name__
        response = {"detail": "FAQ 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."}
        logger.exception("FAQ 검색 중 MySQL 오류 request_id=%s", request_id)
        raise HTTPException(503, response["detail"], headers={"X-Request-ID": request_id}) from exc
    except Exception as exc:
        status, http_status, error_code = "error", 500, type(exc).__name__
        response = {"detail": "FAQ 요청 처리 중 오류가 발생했습니다."}
        logger.exception("FAQ 요청 처리 오류 request_id=%s", request_id)
        raise HTTPException(500, response["detail"], headers={"X-Request-ID": request_id}) from exc
    finally:
        record_request(
            request_id=request_id, feature="faq", query=request.query,
            response=response, started_at=started_at, status=status,
            http_status=http_status, error_code=error_code,
        )
