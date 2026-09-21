from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field
from app.recommendation_service import extract_conditions, filter_products

#서비스의 앱 객체 생성
app = FastAPI(title="Food Commerce AI Assistant")

class RecommendationRequest(BaseModel): # 요청 데이터가 어떤 모양이어야 하는지 정의
    model_config = ConfigDict(str_strip_whitespace=True) # 문자열 앞뒤 공백 제거

    query: str = Field(min_length=1, max_length=500) # 문자열 길이 최소 1 이상

@app.post("/api/recommendations")
def recommend_products(request: RecommendationRequest):
    conditions = extract_conditions(request.query) # 질문을 검색 조건 딕셔너리로 바꿈

    has_condition = ( # 인식한 조건이 하나라도 있는지 저장
        conditions["gift_only"]
        or conditions["individual_only"]
        or conditions["max_sweetness"] is not None # 당도 제한이 지정돼 있는지 확인
    )

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

    products = filter_products(**conditions) # 조건을 함수의 입력값으로 풀어 전달하고 상품 검색

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

@app.get("/health")
def health_check(): #요청 처리할 함수 정의
    return {"status": "ok"} #응답 딕셔너리

@app.get("/hello")
def say_hello(name: str = "방문자"):
    return {"message": f"{name}님, 안녕하세요!"}