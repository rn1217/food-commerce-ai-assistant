# 상품 데이터 확장과 검증

## 목적과 흐름

가격·포장·당도 조합이 적었던 5개 상품을 30개로 늘려 검색 조건을 비교한다. 모든 상품과 가격은 포트폴리오용 가상 데이터다. 당도는 영양정보가 아닌 1~5의 가상 등급이다. 중량 데이터가 없어 가성비는 판매가격 오름차순으로만 정의한다.

준비 단계: `products.csv → pandas 검증 → 매개변수 SQL → MySQL products`

서비스 단계: `사용자 → POST /api/recommendations → AI 조건 해석 → MySQL 검색 → 앞 3개 상품의 AI 설명 → JSON 응답 + ai_logs`

CSV는 준비 단계에서만 읽는다. 웹 요청마다 CSV를 읽거나 pandas를 실행하지 않는다. 상품 목록의 기준은 MySQL이다. 카테고리와 보관방법은 데이터에 있지만 현재 자연어 필터가 지원하지 않는 조건이다.

## 파일 역할

| 파일 | 역할 |
| --- | --- |
| `data/products.csv` | 기존 ID 1~5를 포함한 30개 가상 상품 원본 |
| `scripts/init_products.py` | 빈 값·중복 ID·정수·범위·허용값 검사 및 일괄 저장 |
| `scripts/evaluate_products.py` | 직접 정한 기대 ID와 실제 DB 검색 결과 비교, 선택적으로 실제 HTTP 평가 |
| `tests/test_product_import.py` | 잘못된 데이터 차단, 재실행, 충돌, 롤백 검증 |
| `docs/evaluation/products-sql.json` | 실제 DB 검색 15개 사례의 결과 |
| `docs/evaluation/products-live.json` | 실제 자연어 요청 3개 결과, 모델 메타데이터, 요청 ID |

기존 `sql/seed_products.sql`과 `app/sample_products.py`는 초기 5개 학습 자료다. 신규 설치는 CSV 입력 스크립트를 사용한다. 실제 API는 `product_repository.py`를 통해 MySQL을 조회한다.

## 직접 실행

프로젝트 루트의 PowerShell에서 실행한다. DB 테이블과 `.env`가 준비돼 있어야 한다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m scripts.init_products --check-only
.\.venv\Scripts\python.exe -m scripts.init_products
.\.venv\Scripts\python.exe -m scripts.evaluate_products
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

CSV 검사 예상: `rows=30, price=4500~65000`. 기존 상품이 5개라면 `added=25, skipped=5`, 재실행하면 `added=0, skipped=30`이다. 기존 ID의 내용이 CSV와 다르면 저장을 중단한다. 기존 상품을 수정하거나 삭제하지 않는다. 저장 중 오류가 발생하면 트랜잭션을 롤백한다.

실제 AI 검증은 서버가 실행된 상태에서 별도로 수행한다. 세 질문 각각 조건 해석과 설명 생성이 호출될 수 있으므로 무료 할당량을 사용하며, 503 재시도 시 요청 수가 늘어난다.

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_products --live
```

다른 포트라면 `--base-url http://127.0.0.1:8015`를 추가한다. 모델이나 키를 스크립트에서 바꾸지 않고 실행 중인 서버의 설정을 사용한다. 검증 실패는 종료 코드 1로 표시한다.

## 무엇을 확인하는가

- SQL 15개: 선물, 개별포장, 포장 제외, 당도, 복합 조건, 가격 이하/미만/초과/일치/범위, 검색 결과 없음, 가격 오름차순/내림차순.
- 실제 AI 3개: 담백한 개별포장 선물, 가성비·최저가 포함, 2만원 이하 개별포장 제외.
- 실제 AI 결과는 기대 상품 ID와 순서, DB 속성 보존, 앞 3개에만 추천 이유 생성, DB 로그 일치, 두 AI 단계 성공을 각각 확인한다.

SQL 15개 통과가 자연어 질문 15개 통과를 의미하지 않는다. 실제 AI 평가는 3개의 고정 질문에 대한 단일 실행이다. ID와 속성을 검사해도 설명 문장 전체의 사실성까지 자동으로 증명하지 못한다. 브라우저 화면 클릭과 새 환경 전체 설치는 별도 확인이 필요하다.

## 화면에서 확인할 예시

| 질문 | 기대 결과 |
| --- | --- |
| 선물용인데 너무 달지 않고 개별포장된 상품 추천해줘 | 7개, ID 1·5·12·18·20·26·30 |
| 가성비 있는 상품을 추천해줘 제일 싼 상품도 포함해서 | 30개 가격 오름차순, 첫 상품 미니 쌀과자 4,500원 |
| 2만원 이하 상품 중 개별포장은 제외해줘 | 5개, ID 7·9·11·21·23 |

정상 생성 시 최대 3개에만 AI 추천 이유가 붙고 나머지 검색 결과도 유지된다. AI 호출에 실패하면 대체 응답과 오류 메타데이터가 나올 수 있다.

## 오류 확인과 완료 조건

`ModuleNotFoundError: pandas`는 위 패키지 설치 명령을 해당 `.venv`로 실행한다. DB 접속 오류는 MySQL 실행 상태와 `.env`를 확인하고 비밀번호를 공유하지 않는다. CSV 오류는 메시지에 나온 열을 수정하고 `--check-only`부터 다시 실행한다. 기존 ID 충돌은 DB와 CSV 차이를 먼저 확인하고 데이터 삭제로 해결하지 않는다.

평가 스크립트는 정확히 이 30개 데이터와 일치하는 DB에서 실행한다. 다른 상품을 추가했다면 고정 정답도 검토해야 한다. 데이터가 다를 때 실패하는 것은 평가 조건이 바뀌었기 때문이다. API 오류 시 결과 JSON의 `interpretation`, `llm`, `request_id`를 확인한다.

완료 조건: DB에 30개 저장, 재실행 중복 없음, SQL 15개 통과, 실제 AI 실행 결과와 한계를 기록하고 웹에서 예시 질문을 확인한다.

학습 TODO: ID 12의 가격 20,000원을 보고 '2만원 이하'에는 포함되지만 '2만원 미만'에는 제외되는 이유를 `search_products()`의 비교 연산자와 연결해서 설명해 본다.
