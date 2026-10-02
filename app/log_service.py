from datetime import datetime, timezone
import json
import logging
from time import perf_counter

from app.log_repository import insert_request_log


logger = logging.getLogger("uvicorn.error")


def record_request(
    *, request_id: str, feature: str, query: str, response: dict,
    started_at: float, status: str, http_status: int,
    error_code: str | None = None,
    engine: str = "rule",
):
    # 이 시점에 측정을 마치므로 아래 로그 저장 시간은 latency_ms에 포함되지 않는다.
    # perf_counter는 시스템 시각 변경의 영향을 받지 않는 경과 시간 측정용 시계다.
    record = {
        "request_id": request_id,
        "feature": feature,
        "engine": engine,  # Gemini 호출 시도는 gemini, FAQ/생략은 rule.
        "user_query": query,
        "response": response,
        "latency_ms": max(0, round((perf_counter() - started_at) * 1000)),
        "status": status,
        "http_status": http_status,
        "error_code": error_code,
        # DATETIME에는 시간대가 없으므로 UTC로 통일해 저장하고 문서에 명시한다.
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
    }
    try:
        insert_request_log(record)
    except Exception as exc:
        # 로그 부가 작업의 실패가 성공 응답이나 원래 오류를 덮어쓰면 안 된다.
        # DB 전체가 중단돼도 같은 요청 ID와 기록을 콘솔에서 확인할 수 있다.
        # 접속 정보가 섞일 수 있는 예외 원문은 DB 기록이나 응답에 복사하지 않는다.
        logger.error(
            "request_log_fallback reason=%s record=%s",
            type(exc).__name__,
            json.dumps(record, ensure_ascii=False, default=str),
        )
