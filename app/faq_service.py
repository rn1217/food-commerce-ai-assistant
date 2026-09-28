import re

from app.faq_repository import get_common_faqs


def normalize_text(text: str) -> str:
    # 공백과 문장부호 차이 때문에 같은 검색어를 놓치지 않도록 정리한다.
    return re.sub(r"[^0-9a-z가-힣]", "", text.lower())


def rank_faqs(query: str, faqs: list[dict]) -> dict:
    normalized_query = normalize_text(query)
    ranked = []

    for faq in faqs:
        keywords = {
            normalize_text(keyword)
            for keyword in faq["keywords"].split(",")
        }
        matched = sorted(
            keyword for keyword in keywords
            if keyword and keyword in normalized_query
        )
        if not matched:
            continue

        # '배송'보다 '배송비'처럼 구체적인 표현을 우선한다.
        # 점수는 검색용 규칙이며 정답 확률이나 AI 신뢰도가 아니다.
        score = max(len(keyword) for keyword in matched)
        if normalized_query == normalize_text(faq["question"]):
            score += 100

        ranked.append({
            "faq_id": faq["faq_id"],
            "category": faq["category"],
            "question": faq["question"],
            "answer": faq["answer"],
            "source": f"faqs:{faq['faq_id']}",
            "score": score,
            "matched_keywords": matched,
        })

    ranked.sort(key=lambda item: (-item["score"], item["faq_id"]))
    if not ranked:
        status = "no_match"
        message = "등록된 FAQ에서 근거를 찾지 못했습니다. 질문을 더 구체적으로 입력해 주세요."
    elif len(ranked) > 1 and ranked[0]["score"] == ranked[1]["score"]:
        status = "needs_clarification"
        message = "관련 FAQ가 여러 개입니다. 아래 대표 질문을 참고해 질문을 구체적으로 입력해 주세요."
    else:
        status = "matched"
        message = "관련 FAQ 원문입니다. 답변 생성 없이 등록된 내용을 보여드립니다."

    # 관련 원문을 최대 3개 반환한다. 아직 하나의 최종 답변을 생성하지 않는다.
    matches = ranked[:3]
    return {
        "query": query,
        "mode": "retrieval_only",
        "status": status,
        "count": len(matches),
        "matches": matches,
        "message": message,
        "notice": "포트폴리오용 가상 정책이며 실제 판매처의 정책이 아닙니다.",
    }


def search_faqs(query: str) -> dict:
    # 작은 FAQ 데이터에서는 DB에서 활성 공통 FAQ를 읽고 Python으로 점수를 계산한다.
    return rank_faqs(query, get_common_faqs())
