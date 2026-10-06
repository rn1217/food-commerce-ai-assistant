# FAQ AI 답변 학습 안내

## 목적과 흐름

FAQ 검색 결과를 그대로 보여주던 기능에 Gemini 답변을 추가한다.

질문 → 기존 키워드 FAQ 검색 → matched인지 확인 → 최대 3개 원문을 Gemini에 전달 → JSON과 출처 ID 검증 → 답변+원문 표시 → 요청 로그 저장.

검색 결과 없음이나 최상위 점수 동점은 호출하지 않는다. 관련 FAQ가 검색됐더라도 모델이 근거가 부족하다고 판단하면 답변하지 않는다. 질문과 가상 FAQ 원문이 Google API로 전송되며 실제 고객 정보를 테스트에 넣지 않는다.

## 파일 역할

- `app/llm_faq_service.py`: 생성 프롬프트, answerable/answer/source_ids 스키마, 검색된 출처인지 검사, 실패 시 원문 유지.
- `app/llm_client.py`: 기존 Gemini HTTP 호출 재사용. 503일 때만 1초 뒤 한 번 재시도한다.
- `app/main.py`: 검색 뒤 답변 생성 연결, 로그 engine/status/error_code 반영.
- `static/app.js`: AI FAQ 답변, 클릭 가능한 출처, FAQ 원문 표시. 동적 문자열은 textContent로 출력.
- `tests/test_faq_llm.py`: 생성 성공, 근거 부족, 출처 오류, API 장애, 로그 저장 장애 테스트.

## 실행

추가 패키지나 DB 변경은 없다. 기존 .env의 키를 유지한다. LLM_ENABLED=true가 기본이며 LLM_FAQ_ENABLED=false로 FAQ 생성만 끌 수 있다. 환경변수 변경 후 서버를 재시작한다.

프로젝트 폴더에서:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

http://127.0.0.1:8000/ 에서 `궁금한 점 → 배송비 → 관련 FAQ 찾기`를 누른다.

## 예상 결과와 완료 조건

- 배송비: AI FAQ 답변에 3,000원/50,000원 이상 무료 정책과 faqs:2 출처 표시. 원문도 유지.
- 배송: 질문 구체화 안내, 생성 생략.
- 비트코인 가격: 근거 없음 안내, 생성 생략.
- 출처 링크: 해당 FAQ 원문으로 이동.

AI 답변과 원문의 정책이 일치하고 출처를 확인할 수 있으면 화면 확인 완료다. 이번 개발 환경은 브라우저 연결이 없어 화면 클릭/레이아웃 검증은 미실시했으며 실제 HTTP·MySQL·Gemini 연결은 확인했다.

## 오류와 상태

| 조건 | API 결과 | DB 로그 |
| --- | --- | --- |
| 생성 성공 | mode=generated, answer와 sources | gemini / success |
| 미검색·모호한 질문 | retrieval_only, answer=null | rule / no_match 또는 needs_clarification |
| 모델의 답변 보류 | insufficient_evidence, answer=null | gemini / insufficient_evidence |
| API 오류·잘못된 출력 | retrieval_only, FAQ 원문 유지 | gemini / fallback + error_code |
| 생성 비활성화 | retrieval_only | rule / 검색 상태 |

오류 시 서버의 faq_llm_fallback 로그와 화면 요청 ID를 확인한다. 503/429는 서비스 상태나 사용량을 확인하고 나중에 재시도한다. 키를 로그나 채팅에 붙이지 않는다. 로그 DB 오류가 원래 답변을 덮어쓰지 않도록 기존 보호 구조를 유지한다.

```sql
SELECT request_id, engine, status, error_code, latency_ms,
       JSON_EXTRACT(response, '$.llm') AS llm
FROM ai_logs WHERE feature='faq'
ORDER BY log_id DESC LIMIT 10;
```

## 검증과 TODO

전체 자동 테스트 52개 통과. 실제 배송비 답변, 모호한 질문, 근거 없는 질문의 HTTP 응답과 DB 로그가 일치함을 확인했다. API 장애·출처 오류·답변 보류는 모의 테스트로 검증했다.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

TODO: 검색된 FAQ ID가 [2, 1]인데 AI가 source_ids=[999]를 주면 어떤 분기에서 원문 표시로 바뀌는지 찾아보기.

출처 ID가 유효해도 문장의 의미가 항상 맞는 것은 아니다. FAQ 검색도 아직 키워드 기반이며 부정문·복합 질문을 오해할 수 있다. 향후 고정 평가셋으로 근거 충실도와 답변 보류의 정확성을 점검한다.


10/6 장애 대응 보완: LLM 호출마다 503 재시도 1회를 허용하고 llm.attempts(상품 조건 해석은 interpretation.attempts)에 시도 횟수를 기록한다. 두 번 모두 실패하면 기존 대체 처리를 유지한다. 요청 수와 대기 시간이 증가할 수 있으며 브라우저 대기 한도는 FAQ 60초, 상품 120초다. 외부 서비스 복구를 보장하는 수정은 아니다.

FAQ 모델 설정: `.env`에 `LLM_FAQ_MODEL=gemini-3.5-flash-lite`를 사용한다. 상품 기능의 `LLM_MODEL`과 별도로 선택하며, 미설정 시 공통 모델을 따른다. 서버 재시작이 필요하다. 10/6 최종 검증: 자동 테스트 55개 통과, 실제 배송비 HTTP 요청에서 생성 답변·출처 faqs:2·DB 로그 일치 확인. LLM 3,131ms는 단일 관측이며 지속적인 성공을 보장하지 않는다.
