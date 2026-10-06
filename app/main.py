import logging
from time import perf_counter
from uuid import uuid4
from pathlib import Path

import pymysql
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from app.product_repository import get_active_products, search_products
from app.query_service import interpret_query
from app.faq_service import search_faqs
from app.log_service import record_request
from app.llm_recommendation_service import add_recommendation_reasons
from app.llm_faq_service import add_faq_answer


app = FastAPI(title="Food Commerce AI Assistant")
logger = logging.getLogger("uvicorn.error")

# static 폴더만 공개한다. 프로젝트 전체나 .env는 공개하지 않는다.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")


@app.get("/", include_in_schema=False)
def home():
    # 고정 HTML을 그대로 반환하므로 템플릿 엔진을 추가하지 않는다.
    return FileResponse(PROJECT_ROOT / "templates" / "index.html")


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
    engine = "rule"

    try:
        intent, interpretation = interpret_query(request.query, request_id)
        conditions = intent.model_dump()
        engine = interpretation["engine"]
        if intent.unsupported or not intent.has_condition() or intent.needs_clarification:
            products = []
            status = "needs_clarification" if intent.has_condition() and intent.needs_clarification else "unsupported"
            message = "질문 전체를 검색 조건으로 확정하지 못했습니다. 가격·선물 여부·개별포장·당도 조건으로 구체화해 주세요."
            if intent.unsupported:
                message = "아직 지원하지 않는 조건: " + ", ".join(intent.unsupported) + ". 해당 조건을 제외하거나 질문을 바꿔 주세요."
        else:
            products = search_products(**intent.search_arguments())
            status = "success" if products else "no_match"
            message = "조건에 맞는 상품을 찾았습니다." if products else "조건에 맞는 상품이 없습니다."

        if intent.value_requested:
            message += " 가성비는 중량·품질 비교가 아닌 판매가격이 낮은 순서로 해석했습니다."
        if intent.include_cheapest:
            message += " 최저가는 지정한 조건을 만족하는 활성 상품 안에서 비교합니다."
        if interpretation["status"] == "fallback":
            status, error_code = "fallback", "query_" + interpretation["error_code"]
            message += " AI 조건 해석에 실패해 확인 가능한 단순 조건만 처리했습니다."

        products, llm = add_recommendation_reasons(request.query, products, request_id)
        if llm["engine"] == "gemini":
            engine = "gemini"
        if llm["status"] == "fallback":
            status, error_code = "fallback", llm["error_code"]
            message += " AI 설명을 생성하지 못해 상품 검색 결과만 표시합니다."
        elif llm["status"] == "success":
            message += " 최대 3개 상품에 AI 추천 이유를 덧붙였습니다."
        elif llm["status"] == "disabled":
            message += " AI 설명이 꺼져 있어 검색 결과만 표시합니다."
        http_status = 200
        response = {
            "request_id": request_id,
            "query": request.query,
            "conditions": conditions,
            "count": len(products),
            "products": products,
            "message": message,
            "llm": llm,
            "interpretation": interpretation,
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
            engine=engine,
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
    engine = "rule"

    try:
        response = search_faqs(request.query)
        response = add_faq_answer(request.query, response, request_id)
        engine = response["llm"]["engine"]
        response["request_id"] = request_id
        # API의 matched는 로그에서는 공통 상태 success로 저장한다.
        status = "success" if response["status"] == "matched" else response["status"]
        if response["llm"]["status"] == "fallback":
            status, error_code = "fallback", response["llm"]["error_code"]
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
            engine=engine,
        )
