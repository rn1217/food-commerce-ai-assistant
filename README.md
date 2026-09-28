# Food Commerce AI Assistant

식품 이커머스 고객의 자연어 질문에서 조건을 추출하고, MySQL 상품 데이터로 검색 결과를 제공하는 포트폴리오 프로젝트입니다. 최종 목표는 LLM 기반 추천 이유와 FAQ 답변을 제공하는 로컬 웹 서비스입니다.

**현재 단계: MySQL 상품 검색 + FAQ 근거 검색 + 요청 로그 저장. LLM은 아직 연결하지 않았습니다.**

## 현재 기능

| 기능 | 동작 |
| --- | --- |
| 상품 조회 | MySQL의 활성 상품 조회 |
| 조건 검색 | 선물 가능, 개별포장, 낮은 당도 조건을 모두 만족하는 상품 검색 |
| FAQ 검색 | 키워드 기반 검색, 최대 3개 원문과 출처 반환, 동점·근거 없음 안내 |
| 입력 검증 | 앞뒤 공백 제거 후 1~500자 문자열 검사, 실패 시 422 |
| 미지원 입력 안내 | 인식한 조건이 하나도 없으면 검색하지 않고 지원 조건 안내 |
| 결과 없음 | 빈 상품 목록과 안내 메시지 반환 |
| DB 오류 처리 | MySQL 오류를 서버 로그에 기록하고 503 응답 |
| 요청 로그 | 추천·FAQ의 성공/근거 없음/추가 질문/실패를 DB에 기록 |

추천·FAQ 요청을 `ai_logs`에 `engine=rule`로 저장합니다. 질문, 응답 JSON, 처리 시간, 상태, 요청 ID를 기록하며, 저장 실패 시 콘솔에 기록하고 원래 응답을 유지합니다. 입력 검증에서 거절되는 422 요청과 GET API는 이번 DB 로그 범위에서 제외합니다.

## 기술과 구조

현재 사용: Python, FastAPI, Pydantic, Uvicorn, MySQL, PyMySQL, python-dotenv.
추후 사용: pandas, LLM API, HTML/CSS/JavaScript. 배포는 현재 범위에 포함하지 않습니다.

```text
food-commerce-ai-assistant/
├─ app/
│  ├─ main.py                   # 입력 검증, API 응답, 오류 처리
│  ├─ log_repository.py       # 요청 로그 INSERT와 commit
│  ├─ log_service.py          # 시간 측정과 저장 실패 대응
│  ├─ faq_repository.py       # 활성 공통 FAQ 조회
│  ├─ faq_service.py          # 키워드 검색과 상태 결정
│  ├─ database.py               # .env 로딩과 MySQL 연결
│  ├─ product_repository.py     # 상품 조회와 조건 검색 SQL
│  ├─ recommendation_service.py # 질문에서 조건 추출, 초기 리스트 검색 함수
│  └─ sample_products.py        # 학습용 데이터; 현재 API 검색에는 사용하지 않음
├─ sql/
│  ├─ schema.sql               # DB와 products 테이블 정의
│  ├─ seed_products.sql        # 가상 상품 5개 입력
│  ├─ create_faqs.sql          # FAQ 테이블 추가
│  └─ create_ai_logs.sql       # 요청 로그 테이블 추가
├─ data/faqs.json              # 가상 FAQ 10개
├─ scripts/init_faq.py         # FAQ 초기화
├─ scripts/init_logs.py        # 로그 테이블 초기화
├─ tests/test_faq.py           # 검색·API 검증
├─ tests/test_logs.py          # 기록·실패 시 응답 보존 검증
├─ docs/
│  ├─ development_log.md       # 개발 기록 목차
│  └─ devlog/                  # 날짜별 기록
├─ .env.example
├─ .gitignore
├─ requirements.txt
└─ README.md
```

## 요청 처리 흐름

```text
질문 JSON → FastAPI 입력 검증 → extract_conditions()
→ search_products() → MySQL SELECT → 조건과 상품 목록을 JSON으로 응답
```

`GET /api/products`와 `POST /api/recommendations`는 모두 MySQL을 사용합니다. 추천 API는 초기 `filter_products()` 함수를 더 이상 호출하지 않습니다.

SQL 조건은 개발자가 정의한 고정 구문으로 조립하고, 실제 값은 `%s` 자리표시자와 별도 파라미터로 전달합니다. DB 연결과 커서는 `with` 블록에서 사용 후 정리합니다.

## API

| 메서드 | 경로 | 역할 |
| --- | --- | --- |
| GET | `/health` | HTTP 응답 확인; DB 상태 검사는 아님 |
| GET | `/hello?name=민수` | 쿼리 파라미터 연습용 인사말 |
| GET | `/api/products` | 활성 상품 조회 |
| POST | `/api/recommendations` | 질문에 따른 상품 검색 |
| POST | `/api/faq/search` | 공통 FAQ 검색; 생성 답변 없이 원문과 출처 제공 |

추천 요청 예시:

```json
{"query": "너무 달지 않고 개별포장된 선물 추천해줘"}
```

초기 데이터에서 `conditions`는 `gift_only: true`, `individual_only: true`, `max_sweetness: 2`이며, `count`는 2, 반환 상품 ID는 1과 5입니다. 응답에는 상품 전체 정보와 안내 메시지도 포함됩니다.

## 로컬 실행 (Windows PowerShell)

### 1. Python 환경

프로젝트 폴더에서 실행합니다. 기존 `.venv`가 있으면 생성은 생략합니다.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

DB 라이브러리를 포함한 설치 버전은 `requirements.txt`에 반영돼 있습니다. 새 환경 전체 재설치 검증은 남은 작업입니다. 개발 Python 버전은 3.14.7입니다.

### 2. MySQL 준비

MySQL 서버를 실행하고 Workbench에서 `food_commerce` DB와 `products` 테이블을 준비합니다. 초기 상품은 `sql/seed_products.sql`로 한 번 입력합니다. 이미 입력한 데이터에 재실행하면 기본키 중복 오류가 발생할 수 있습니다.

이전에 발견한 `schema.sql`의 미완성 구문은 정리됐습니다. 새 설치에서는 Workbench에서 `schema.sql`을 먼저 실행합니다. 아래 `.env` 설정과 패키지 설치를 마친 뒤 FAQ를 초기화합니다.

```powershell
.\.venv\Scripts\python.exe -m scripts.init_faq
.\.venv\Scripts\python.exe -m scripts.init_logs
```

FAQ 초기화는 없는 ID만 추가하며, 기존 답변을 덮어쓰지 않습니다. JSON 변경을 기존 DB 행에 자동 반영하는 기능은 없습니다.

### 3. 환경변수

프로젝트 최상위에 `.env`를 만들고 본인의 접속 정보를 작성합니다. 비밀번호는 예시값을 실제 값으로 바꿉니다.

```dotenv
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=food_commerce
DB_USER=root
DB_PASSWORD='your_local_password'
```

`root`는 현재 로컬 학습 환경에서 사용하는 계정입니다. 프로젝트 전용 최소 권한 계정 분리는 향후 개선 항목입니다.
`.env`는 Git에 올리지 않고 `.env.example`에만 비밀정보 없는 설정 예시를 보관합니다.

```powershell
git check-ignore .env
```

`.env`가 출력되는지 확인합니다. `.env`를 변경하면 개발 서버를 재시작합니다.

### 4. 서버 실행

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

- API 문서: http://127.0.0.1:8000/docs
- 상품 조회: http://127.0.0.1:8000/api/products
- 서버 종료: `Ctrl + C`

추천 POST 요청은 `/docs`의 `Try it out`에서 실행합니다. 주소창 직접 접속은 GET 요청입니다.

## FAQ 검색 사용과 테스트

```json
{"query": "배송비는 얼마인가요?"}
```

`POST /api/faq/search`에 보내면 `mode: retrieval_only`, `status: matched`와 FAQ 원문 목록을 반환합니다. FAQ 2가 첫 번째이며 `source`는 `faqs:2`입니다. 가상 정책임을 응답에 표시합니다.

- `배송` → `needs_clarification`: 상위 점수가 같아 질문 구체화 안내
- `비트코인 가격 알려줘` → `no_match`: 빈 근거 목록
- 공백 질문 → HTTP 422
- DB 오류 → HTTP 503 및 서버 오류 로그

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

테스트는 DB 조회를 대체해 실행하므로 DB 변경이나 LLM 비용이 없습니다. 실제 MySQL·임시 HTTP 서버로도 FAQ 6개 요청과 기존 상품/추천 API를 확인했습니다. 점수는 규칙 기반 우선순위로 정답 확률이 아닙니다.

파일별 설명과 직접 확인할 내용은 [FAQ 학습 안내](docs/faq-guide.md)를 참고합니다.

## 요청 로그 확인

추천·FAQ 성공 응답의 `request_id`와 DB 기록을 연결합니다. 오류 응답에서는 `X-Request-ID` 헤더로 확인합니다. FAQ의 `matched`는 로그 상태 `success`로 저장하며 나머지는 `no_match`, `unsupported`, `needs_clarification`, `error`로 구분합니다.

```sql
SELECT request_id, feature, engine, user_query, status,
       http_status, latency_ms, created_at
FROM food_commerce.ai_logs
ORDER BY log_id DESC
LIMIT 10;
```

`created_at`은 UTC입니다. `latency_ms`는 입력 검증 후 함수 시작부터 응답 준비까지이며 로그 쓰기와 네트워크 시간은 제외합니다. 로그 쓰기는 동기 방식이어서 실제 사용자 대기에는 추가 시간이 발생할 수 있습니다.

실제 DB 저장 6건의 응답/요청 ID/상태를 대조했습니다. 그중 1건은 검색 오류를 모의 주입한 검증 기록입니다. 로그 저장 실패 시 콘솔 fallback은 영구 저장을 보장하지 않습니다.

[요청 로그 학습 안내](docs/request-logs-guide.md)에 파일 역할, 실행 방법, 실패 처리와 완료 조건을 정리했습니다.

## 문제 해결과 확인

상품 기능의 개발자 수동 확인 결과와 9/28의 실제 DB·HTTP 검증을 기록했습니다. FAQ·추천 회귀·요청 로그 자동 테스트 24개가 통과했습니다. 성능 측정은 아직 하지 않았습니다.

| 문제 | 개선 | 확인 결과 |
| --- | --- | --- |
| 공백 질문이 길이 검사 통과 | 공백 제거 후 길이 검사 | 같은 입력의 응답이 200 → 422 |
| 인식한 조건이 없으면 전체 상품 반환 | 조건이 없으면 검색 중단 및 안내 | 매운맛 질문의 반환 상품 수 5 → 0 |
| Python 리스트 변경에 의존 | MySQL 조회로 검색 교체 | 활성 상태 변경에 따라 결과가 `[1, 5]` → `[1]` → `[]`, 복구 후 `[1, 5]` |

## 한계와 다음 작업

- 키워드 기반 검색이라 부정문을 이해하지 못합니다. `매운 선물`은 선물 조건만 적용하며, 미지원 조건을 모두 감지하지 못합니다.
- 낮은 당도는 가상 등급 2 이하라는 고정 규칙이며 영양성분이나 건강 적합성 판단이 아닙니다.
- 검색은 활성 상품을 ID 순으로 반환하며, 후보 수 제한이나 개인화 순위는 없습니다.
- 상품 5개와 공통 FAQ 10개를 사용하며 요청 로그를 저장합니다. UI는 아직 미구현입니다.
- FAQ는 키워드 검색이며 부정문·복합 질문에서 오탐할 수 있습니다. 상품 전용 FAQ는 현재 검색에서 제외합니다.
- LLM 연동 및 반환 상품 ID 검증은 다음 단계입니다. 아직 LLM 추천 정확도나 토큰 절감 효과를 주장하지 않습니다.
- SQL과 의존성 목록은 정리됐습니다. FAQ의 DB 오류 응답은 모의 예외로 검사했으며 실제 장애 재현과 새 환경 전체 설치 검증은 남아 있습니다.
- 이후 고정 평가 질문으로 응답 시간, 입력 토큰, 조건 위반률을 비교할 계획입니다.

## 개발 기록

[날짜별 기록 목차](docs/development_log.md) · [9/21: MySQL 검색](docs/devlog/2026-09-21.md) · [9/28: FAQ 검색](docs/devlog/2026-09-28.md)
