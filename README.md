# Food Commerce AI Assistant

식품 이커머스 고객의 자연어 질문에서 조건을 추출하고, MySQL 상품 데이터로 검색 결과를 제공하는 포트폴리오 프로젝트입니다. 최종 목표는 LLM 기반 추천 이유와 FAQ 답변을 제공하는 로컬 웹 서비스입니다.

**현재 단계: 가상 상품 5개를 대상으로 한 MySQL 기반 조건 검색. LLM은 아직 연결하지 않았습니다.**

## 현재 기능

| 기능 | 동작 |
| --- | --- |
| 상품 조회 | MySQL의 활성 상품 조회 |
| 조건 검색 | 선물 가능, 개별포장, 낮은 당도 조건을 모두 만족하는 상품 검색 |
| 입력 검증 | 앞뒤 공백 제거 후 1~500자 문자열 검사, 실패 시 422 |
| 미지원 입력 안내 | 인식한 조건이 하나도 없으면 검색하지 않고 지원 조건 안내 |
| 결과 없음 | 빈 상품 목록과 안내 메시지 반환 |
| DB 오류 처리 | MySQL 오류를 서버 로그에 기록하고 503 응답 |

로그는 현재 서버 터미널의 오류 로그입니다. DB에 AI 요청을 저장하는 `ai_logs` 기능은 아직 없습니다.

## 기술과 구조

현재 사용: Python, FastAPI, Pydantic, Uvicorn, MySQL, PyMySQL, python-dotenv.
추후 사용: pandas, LLM API, HTML/CSS/JavaScript. 배포는 현재 범위에 포함하지 않습니다.

```text
food-commerce-ai-assistant/
├─ app/
│  ├─ main.py                   # 입력 검증, API 응답, 오류 처리
│  ├─ database.py               # .env 로딩과 MySQL 연결
│  ├─ product_repository.py     # 상품 조회와 조건 검색 SQL
│  ├─ recommendation_service.py # 질문에서 조건 추출, 초기 리스트 검색 함수
│  └─ sample_products.py        # 학습용 데이터; 현재 API 검색에는 사용하지 않음
├─ sql/
│  ├─ schema.sql               # DB와 products 테이블 정의
│  └─ seed_products.sql        # 가상 상품 5개 입력
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
.\.venv\Scripts\python.exe -m pip install "PyMySQL[rsa]" python-dotenv
```

현재 `requirements.txt`에는 새 DB 라이브러리가 아직 반영되지 않아 추가 설치 명령이 필요합니다. 버전 목록 갱신과 새 환경 재설치 검증은 남은 작업입니다. 개발자가 보고한 Python 버전은 3.14.7입니다.

### 2. MySQL 준비

MySQL 서버를 실행하고 Workbench에서 `food_commerce` DB와 `products` 테이블을 준비합니다. 초기 상품은 `sql/seed_products.sql`로 한 번 입력합니다. 이미 입력한 데이터에 재실행하면 기본키 중복 오류가 발생할 수 있습니다.

**현재 파일 주의점:** `sql/schema.sql`에는 완성된 테이블 정의 앞에 미완성 `CREATE TABLE` 구문이 남아 있습니다. 새 DB 구성 전에 해당 구문을 정리해야 하며, 현재 파일 전체를 그대로 실행하는 재현 절차는 아직 검증하지 않았습니다. 기존 로컬 DB에서의 API 동작은 개발자가 확인했습니다.

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

## 문제 해결과 확인

개발자가 로컬에서 수동 확인한 결과를 기록했습니다. 자동화 테스트나 성능 측정 결과는 아직 없습니다.

| 문제 | 개선 | 확인 결과 |
| --- | --- | --- |
| 공백 질문이 길이 검사 통과 | 공백 제거 후 길이 검사 | 같은 입력의 응답이 200 → 422 |
| 인식한 조건이 없으면 전체 상품 반환 | 조건이 없으면 검색 중단 및 안내 | 매운맛 질문의 반환 상품 수 5 → 0 |
| Python 리스트 변경에 의존 | MySQL 조회로 검색 교체 | 활성 상태 변경에 따라 결과가 `[1, 5]` → `[1]` → `[]`, 복구 후 `[1, 5]` |

## 한계와 다음 작업

- 키워드 기반 검색이라 부정문을 이해하지 못합니다. `매운 선물`은 선물 조건만 적용하며, 미지원 조건을 모두 감지하지 못합니다.
- 낮은 당도는 가상 등급 2 이하라는 고정 규칙이며 영양성분이나 건강 적합성 판단이 아닙니다.
- 검색은 활성 상품을 ID 순으로 반환하며, 후보 수 제한이나 개인화 순위는 없습니다.
- 상품은 5개이며 FAQ, AI 요청 로그 테이블과 UI는 미구현입니다.
- LLM 연동 및 반환 상품 ID 검증은 다음 단계입니다. 아직 LLM 추천 정확도나 토큰 절감 효과를 주장하지 않습니다.
- 저장된 SQL 정리, 의존성 목록 갱신, DB 장애 응답 재현 시험과 설치 재현 확인이 필요합니다.
- 이후 고정 평가 질문으로 응답 시간, 입력 토큰, 조건 위반률을 비교할 계획입니다.

## 개발 기록

[날짜별 기록 목차](docs/development_log.md) · [2026-09-21: 요청 검증과 MySQL 검색](docs/devlog/2026-09-21.md)
