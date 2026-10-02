# 상품 추천 LLM 연동

## 1. 이번 단계의 목적

이미 검색된 상품에 Gemini가 추천 이유를 작성한다. 후속 단계에서 Gemini가 검색 조건을 해석하고 검증된 조건으로 Python/MySQL이 후보를 결정하도록 확장했다. natural-language-search-guide.md를 참고한다. FAQ는 아직 원문 검색이며 LLM을 호출하지 않는다.

## 2. 데이터 흐름

질문 → FastAPI 검증 → 조건 추출 → MySQL 후보 조회 → 앞 3개 후보와 질문을 Gemini에 전송 → JSON/ID 검증 → DB 상품에 이유 추가 → 응답 및 ai_logs 저장 → JS 카드 표시.

검색 결과 전체는 유지하고 SQL 정렬 결과 앞 3개에만 이유를 붙인다. 이는 개인화 순위가 아니다. 후보가 없거나 지원하지 않는 질문이면 추천 이유 생성 호출을 생략한다. 조건 해석 단계의 호출은 별개다. 사용자의 질문과 가상 후보 데이터가 Google API로 전송되므로 테스트에 실제 고객 정보를 넣지 않는다.

## 3. 파일과 핵심 코드

| 파일 | 역할 |
| --- | --- |
| app/llm_client.py | .env 읽기, HTTPS POST, 텍스트·토큰 사용량 추출, 안전한 오류 코드 |
| app/llm_recommendation_service.py | 프롬프트, 최대 3개 후보, Pydantic JSON 검증 및 후보 ID 대조 |
| app/main.py | 기존 검색 뒤 이유 생성 호출, 성공/대체 응답 구분 |
| app/log_service.py | engine을 전달받아 rule/gemini 구분 |
| static/app.js, static/style.css | 실제 응답의 recommendation_reason을 textContent로 표시 |
| tests/test_llm.py | 가짜 AI 응답·통신 오류로 검증, 유료 호출 없음 |

`validate_reasons()`는 미등록 ID, 중복 ID, 누락 ID, 잘못된 자료형, 빈 이유, 300자 초과를 거절한다. 한 항목이라도 잘못되면 AI 설명 전체를 버린다. 상품 이름과 가격은 모델 출력에서 받지 않고 DB 값을 유지한다.

## 4. 실행

기존 .env의 GEMINI_API_KEY를 유지한다. 필요하면 아래 옵션을 추가한다.

```dotenv
LLM_ENABLED=true
LLM_MODEL=gemini-3.8-flash
```

프로젝트 폴더에서 서버를 재시작한다. 새 의존성이나 DB 테이블 변경은 없다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

http://127.0.0.1:8000/ 에서 `담백한 선물` → 검색을 누른다.

## 5. 예상 결과

초기 DB라면 상품 1, 5의 카드에 `AI 추천 이유`가 나타난다. `/docs`에서 POST 응답의 `llm.status=success`와 `products[].recommendation_reason`을 확인할 수도 있다. 질문을 다시 검색할 때마다 새 호출이 발생하며 자동 재시도는 하지 않는다.

## 6. 오류 확인

- API 오류·잘못된 AI 출력: HTTP 200으로 기존 상품 유지, `llm.status=fallback`. 화면에서 AI 설명 생성 실패 안내.
- 503/429/시간 초과: 서버 로그의 llm_fallback과 request_id 확인. 결제 전환 없이 사용량/서비스 상태 확인.
- missing_key: .env 저장 후 서버 재시작.
- LLM_ENABLED=false: 설명 생성을 끄고 기존 검색만 실행.
- DB 조회 실패는 기존대로 503이며 AI 호출까지 진행하지 않는다.

AI 통신 대기는 소켓 기준 20초다. 웹 화면의 30초 제한이나 서버의 전체 처리 시간과 같은 의미는 아니다.

## 7. 로그와 완료 조건

```sql
SELECT request_id, engine, status, latency_ms, error_code,
       JSON_EXTRACT(response, '$.llm') AS llm
FROM ai_logs
ORDER BY log_id DESC LIMIT 10;
```

성공/실패 시도는 engine=gemini, 실패 대체 상태는 fallback이다. FAQ·후보 없음·비활성화는 rule이다. AI 결과 JSON의 llm에 후보 수, 모델, 토큰 사용량, LLM 처리 시간을 저장한다. 제공되지 않은 토큰 수는 null이다. latency_ms는 로그 저장 시간을 제외한다.

완료 조건: 실제 상품 카드의 AI 이유 확인, 응답 ID에 해당하는 success 로그 확인, 자동 테스트 통과.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

## 8. 직접 해볼 TODO와 한계

TODO: validate_reasons의 후보 ID 집합 비교를 읽고, 후보가 [1, 5]인데 AI가 [1, 999]를 반환하면 왜 전체 설명을 버리는지 설명해 보기.

ID 검증은 잘못된 상품 카드 추가를 막지만 설명의 의미까지 완전히 검증하지 못한다. 모델이 기존 상품의 속성을 잘못 설명할 가능성은 남아 있다. 프롬프트 인젝션 방어 문구도 완전한 보장이 아니다. 고정 평가 질문으로 속성 위반을 측정하는 작업은 다음 단계다.

공식 API 형식: https://ai.google.dev/gemini-api/docs/get-started
