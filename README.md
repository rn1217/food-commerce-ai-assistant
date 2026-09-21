# Food Commerce AI Assistant

식품 이커머스 환경을 가정한 AI 상품 추천 및 FAQ 응답 서비스입니다.
Python과 FastAPI를 학습하며 약 3주 동안 로컬에서 실행 가능한 MVP를 단계적으로 개발합니다.

## 현재 구현 상태

- Python 가상환경 구성
- FastAPI 앱과 Uvicorn 개발 서버 실행
- `GET /health`: 서버 응답 확인
- `GET /hello?name=민수`: 쿼리 파라미터를 받아 인사말 반환
- `/docs`: 자동 API 문서
- POST /api/recommendations: 질문 검증 및 규칙 기반 상품 검색
- 선물 가능·개별포장·당도 조건 지원
- 공백 질문 거절 및 인식 가능한 조건이 없는 경우 안내

`/hello`는 요청과 응답 흐름을 이해하기 위한 연습용 API입니다.
가상 상품을 대상으로 한 규칙 기반 검색까지 구현했다. MySQL 및 LLM 연동은 아직 구현하지 않았다.

## 목표 기능

- 가상 상품 30~50개를 MySQL에 저장
- 자연어 조건에 맞는 상품 검색 및 LLM 기반 추천 이유 생성
- FAQ 검색 결과에 근거한 답변
- 요청 결과, 처리 시간, 오류 로그 저장
- HTML/CSS/JavaScript 기반 UI

## 현재 구조

```text
food-commerce-ai-assistant/
├─ app/
│  ├─ __init__.py
│  └─ main.py
├─ docs/
│  └─ development_log.md
├─ .env.example
├─ .gitignore
├─ requirements.txt
└─ README.md
```

## 로컬 실행 (Windows PowerShell)

프로젝트 폴더에서 실행합니다. 기존 `.venv`가 있으면 생성 명령은 생략합니다.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

개발자가 확인한 Python 버전은 3.14.7입니다. 의존성 버전은 현재 가상환경의 `pip freeze` 결과를 기록했습니다. 다른 환경에서의 재설치 검증은 아직 진행하지 않았습니다.

브라우저에서 확인합니다.

| 주소 | 예상 결과 |
| --- | --- |
| http://127.0.0.1:8000/health | `{"status":"ok"}` |
| http://127.0.0.1:8000/hello | `{"message":"방문자님, 안녕하세요!"}` |
| http://127.0.0.1:8000/hello?name=민수 | `{"message":"민수님, 안녕하세요!"}` |
| http://127.0.0.1:8000/docs | API 문서 |

서버 종료: `Ctrl + C`.
루트 주소 `/`는 아직 구현하지 않아 404가 반환됩니다.

## 요청 흐름

현재: 브라우저 → GET 요청 → FastAPI → Python 함수 → JSON 응답.

계획: 사용자 질문 → FastAPI → 조건 해석 → MySQL 검색 → LLM → 응답 검증 → JSON 응답.

추천 상품의 ID를 검색 후보와 대조하고, 상품명과 가격은 DB 값으로 응답할 계획입니다. FAQ 근거가 없으면 답변을 추측하지 않습니다.

## 설정과 Git 관리

현재 앱은 환경변수를 사용하지 않습니다. `.env.example`은 향후 연동을 위한 예시이며 실제 인증정보를 포함하지 않습니다.
DB와 LLM을 연결할 때 `.env`를 만들고 환경변수 로딩을 구현합니다.
`.venv`, `.env`, Python 캐시, 로컬 로그는 Git에서 제외합니다.
실제 키나 비밀번호는 코드와 문서에 기록하지 않습니다.

## 다음 작업과 한계

요청 데이터 검증과 오류 응답을 학습한 뒤 MySQL을 연결합니다.
현재는 고정 상태와 인사말을 반환하는 학습 단계로, AI 서비스 기능은 제공하지 않습니다.
이후 고정 평가 질문으로 후보 검색 전후 토큰 수, 응답 시간, 조건 위반률을 측정할 계획입니다. 아직 측정 결과는 없습니다.

개발 과정은 [개발 기록](docs/development_log.md)에 남깁니다.
