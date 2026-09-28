# 요청 로그 저장 — 2026-09-28

## 목적

추천·FAQ 요청이 어떤 결과를 냈는지 DB에 남겨 오류 추적과 향후 평가의 근거로 사용한다. 테이블 이름은 초기 설계대로 `ai_logs`지만 현재 처리 방식은 `engine=rule`이다. 아직 LLM 호출이나 토큰 사용량 측정은 없다.

## 데이터 흐름

```text
입력 검증 → 요청 ID 발급·시작 시간 측정 → 상품/FAQ 검색
→ 응답과 상태 준비 → finally에서 로그 저장 → 사용자에게 응답
                          └ 저장 실패 시 콘솔 기록, 원래 응답 유지
```

`finally`는 함수 중간에서 `return`하거나 예외가 발생해도 실행된다. 두 API에 명시적으로 같은 흐름을 작성해 복잡한 미들웨어나 데코레이터 없이 처리 과정을 따라갈 수 있게 했다.

## 파일 역할

| 파일 | 역할 |
| --- | --- |
| `sql/create_ai_logs.sql` | 로그 테이블과 날짜 인덱스 정의 |
| `scripts/init_logs.py` | 테이블이 없으면 생성. 기존 기록 보존 |
| `app/main.py` | 요청 ID, 상태 분류, 성공·실패 후 기록 호출 |
| `app/log_service.py` | 처리 시간 계산, 기록 구성, 저장 실패 시 콘솔 기록 |
| `app/log_repository.py` | 파라미터 바인딩 INSERT와 commit |
| `tests/test_logs.py` | 저장 성공·실패·시간 측정·오류 보존 검사 |

## 저장하는 값

| 컬럼 | 의미 |
| --- | --- |
| `request_id` | 요청별 UUID. 성공 응답의 동일 필드와 연결 |
| `feature` | `recommendation` 또는 `faq` |
| `engine` | 현재 `rule` |
| `user_query` | 검증 후 앞뒤 공백을 제거한 질문 |
| `response` | 실제 응답 JSON. 실패 시 사용자에게 보여준 detail |
| `latency_ms` | 검증 완료 후 함수 시작부터 응답 준비까지 걸린 시간 |
| `status` | 아래 처리 상태 |
| `http_status` | 200, 503, 500 등 HTTP 상태 코드 |
| `error_code` | 오류 클래스 이름. 접속정보를 포함할 수 있는 오류 원문은 저장하지 않음 |
| `created_at` | UTC 시각. 한국 시각은 9시간을 더해 조회 |

| status | 의미 |
| --- | --- |
| `success` | 검색 결과 있음; FAQ API의 matched도 여기에 해당 |
| `no_match` | 조건/질문은 처리했지만 검색 결과 없음 |
| `unsupported` | 추천 질문에서 지원 조건을 찾지 못함 |
| `needs_clarification` | FAQ 상위 점수가 동점이라 추가 설명 필요 |
| `error` | 검색 또는 처리 실패 |

성공 응답에는 `request_id`가 추가된다. 오류 응답은 기존 detail 형식을 유지하고 `X-Request-ID` 응답 헤더로 ID를 제공한다. DB 로그에도 같은 ID가 저장된다.

## 실행 및 확인

테이블 생성은 이번 작업에서 이미 실행했다. 새 설치에서는 프로젝트 폴더에서 실행한다.

```powershell
.\.venv\Scripts\python.exe -m scripts.init_logs
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

서버가 이미 실행 중이면 코드를 반영했는지 확인하고 필요하면 재시작한다. `/docs`에서 추천 질문과 FAQ 질문을 전송한다.

```json
{"query": "배송비는 얼마인가요?"}
```

Workbench에서 조회한다.

```sql
SELECT log_id, request_id, feature, engine, user_query,
       status, http_status, latency_ms,
       created_at AS created_at_utc,
       DATE_ADD(created_at, INTERVAL 9 HOUR) AS created_at_kst
FROM food_commerce.ai_logs
ORDER BY log_id DESC
LIMIT 10;
```

응답의 request_id를 아래에 넣으면 한 요청을 추적할 수 있다.

```sql
SELECT request_id, response, error_code
FROM food_commerce.ai_logs
WHERE request_id = '응답에서_복사한_request_id';
```

`배송비는 얼마인가요?`는 success, `비트코인 가격 알려줘`는 no_match가 예상된다. 공백 질문은 입력 검증 단계에서 422로 거절되므로 이 테이블에 저장하지 않는다. GET 상품 조회와 health도 이번 기록 대상이 아니다.

## 실패 확인과 처리 기준

- MySQL 검색 오류: 서버에 traceback을 남기고 503을 반환하며 오류 기록 저장을 시도한다.
- 예상하지 못한 처리 오류: 서버에 traceback을 남기고 일반적인 500 응답을 반환한다.
- 로그 DB 쓰기만 실패: 성공 응답을 오류로 바꾸지 않고 콘솔에 `request_log_fallback`과 기록을 남긴다.
- DB 전체 장애: DB에 저장할 수 없으므로 원래 오류 응답과 콘솔 기록을 유지한다.

로그가 없으면 먼저 `init_logs` 실행 여부와 서버 콘솔의 fallback 메시지를 확인한다. 로그를 저장하는 INSERT에는 commit이 필요하다.

## 검증 결과와 한계

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

24개 자동 테스트 통과. 모의 오류로 검색 실패, 로그만 실패, 두 작업 동시 실패와 응답 보존을 확인했다. 실제 DB에서는 HTTP 요청 5건과 모의 검색 오류를 주입한 ASGI 요청 1건, 총 6개 로그를 저장하고 JSON과 요청 ID를 대조했다. 상품·FAQ 데이터는 변경하지 않았다. 검증 로그는 DB에 남아 있으며 오류 주입 기록은 질문에 `[로그 검증: 모의 DB 검색 오류]`를 표시했다.

로그 저장은 동기적으로 실행돼 사용자 대기 시간에 추가 비용이 생긴다. `latency_ms`에는 입력 검증·로그 쓰기·네트워크 전송 시간이 포함되지 않으므로 브라우저에서 측정한 전체 응답 시간과 같지 않다. 저장된 개별 시간은 성능 개선 효과나 벤치마크가 아니다.

콘솔 fallback은 영구 저장이나 재전송을 보장하지 않는다. 기록 보존 기간, 개인정보 처리, 파일 로그 회전, 비동기 저장은 아직 구현하지 않았다. 현재는 로컬 데모 질문을 사용하는 범위다.

## 직접 확인할 완료 조건

1. 정상 FAQ 요청 후 동일 request_id로 DB에서 한 행을 찾는다.
2. 근거 없는 질문 후 no_match가 저장되는지 확인한다.
3. `finally`, `commit`, `latency_ms`의 역할과 측정 범위를 설명한다.

다음 단계는 최소 웹 화면이다. LLM 연결은 별도로 진행한다.
