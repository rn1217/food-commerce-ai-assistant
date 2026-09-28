# FAQ 검색 단계 — 2026-09-28

## 목적과 데이터 흐름

LLM을 연결하기 전에 질문과 관련된 FAQ 근거를 찾는다. 현재 API는 생성 답변이 아니라 등록된 원문과 출처를 반환한다. 호출 비용은 발생하지 않는다.

```text
POST /api/faq/search {"query": "배송비는 얼마인가요?"}
→ main.py: 문자열 앞뒤 공백 제거와 길이 검사
→ faq_service.search_faqs(): 처리 순서 제어
→ faq_repository.get_common_faqs(): 활성 공통 FAQ 조회
→ MySQL faqs
→ faq_service.rank_faqs(): 키워드 점수 계산, 최대 3개 선택
→ main.py: JSON 응답 또는 DB 오류 시 503
```

## 파일 역할

| 파일 | 역할 |
| --- | --- |
| `sql/create_faqs.sql` | FAQ 테이블 정의. 기존 상품 테이블은 변경하지 않음 |
| `data/faqs.json` | 배송·보관·해동·주문·교환환불·상품정보의 가상 FAQ 10개 |
| `scripts/init_faq.py` | 테이블 생성 및 없는 FAQ ID만 추가. 기존 답변을 덮어쓰지 않음 |
| `app/faq_repository.py` | 활성 상태이며 product_id가 NULL인 공통 FAQ만 조회 |
| `app/faq_service.py` | 질문 정규화, 키워드 매칭, 정렬과 상태 결정 |
| `app/main.py` | 요청 검증과 FAQ API 입구, DB 오류 처리 |
| `tests/test_faq.py` | 검색·입력·실패 응답·기존 추천 API 회귀 검사 |

`product_id`는 향후 상품 전용 FAQ를 위한 선택 필드다. 현재 API는 상품을 받지 않으므로 해당 값이 있는 FAQ는 검색 대상에서 제외한다.

## 주요 코드 이해

```python
matched = [keyword for keyword in keywords if keyword in normalized_query]
```

등록된 키워드가 질문에 포함되는지 확인하는 방식이다. 실제 코드에서는 빈 키워드도 제외한다. 의미를 이해하는 AI 검색은 아니다.

```python
score = max(len(keyword) for keyword in matched)
```

일치한 키워드 중 가장 긴 표현의 길이를 점수로 쓴다. 따라서 `배송비`가 `배송`보다 우선한다. 대표 질문 전체가 같으면 추가 점수를 주며, 동점은 FAQ ID 순으로 정렬한다. 점수는 정답 확률이 아니다.

| status | 의미 |
| --- | --- |
| `matched` | 1위 점수가 유일한 검색 결과. 정답 보장은 아님 |
| `needs_clarification` | 1위 점수에 여러 FAQ가 있어 추가 설명 요청 |
| `no_match` | 키워드가 일치하는 근거 없음 |

모든 응답에 `mode: retrieval_only`와 가상 정책 안내가 포함된다. 원문을 `answer`, 근거를 `source: faqs:2` 형태로 반환한다. 별도의 생성 답변은 없다.

## 실행

프로젝트 폴더의 PowerShell에서 실행한다.

```powershell
.\.venv\Scripts\python.exe -m scripts.init_faq
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

초기화는 이번 작업에서 이미 실행했다. 첫 실행은 `added=10`, 재실행은 `added=0, skipped=10`이다. JSON을 나중에 수정해도 기존 DB 답변이 자동으로 바뀌지는 않는다. 수정 작업은 별도 UPDATE 절차가 필요하다.

http://127.0.0.1:8000/docs 에서 `POST /api/faq/search`를 실행한다.

| query | 예상 결과 |
| --- | --- |
| 배송비는 얼마인가요? | matched, 첫 FAQ ID 2 |
| 냉동 떡 해동 방법 알려줘 | matched, 첫 FAQ ID 4 |
| 배송 | needs_clarification |
| 비트코인 가격 알려줘 | no_match, 빈 목록 |
| 공백만 입력 | HTTP 422 |

FAQ 테이블이 없거나 DB 연결에 실패하면 503을 반환하고 서버에 오류를 기록한다. 포트 충돌이면 이미 실행 중인 서버 창을 확인하고 해당 서버를 재시작한다. 임의로 다른 프로세스를 종료하지 않는다.

## 검증과 한계

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

DB 없이 실행하는 11개 테스트에서 API 입력 검증, 원문 보존, 동점 안내, 미일치, DB 예외를 모의 주입한 503 응답, 기존 추천 조건 전달을 검사했다. 실제 MySQL과 임시 Uvicorn 서버에서도 FAQ 6개 요청 및 기존 상품/추천 API 2개 요청을 확인했다.

문장 의미나 부정문, 복합 질문을 완전히 이해하지 못하고 키워드의 부분 일치로 오탐할 수 있다. 단일 1위가 있어도 정확한 근거라는 보장은 없다. FAQ 10개에서는 전체 공통 FAQ를 읽지만 데이터 증가 시 검색 범위 축소가 필요하다.

## 직접 해볼 TODO와 완료 조건

- `/docs`에서 배송비, 배송, 미지원 질문의 상태 차이를 확인한다.
- `faq_service.py`의 `matched`, `score`, `ranked[:3]` 역할을 말로 설명해 본다.
- 답변 문장이 새로 생성된 것이 아니라 DB 원문인지 확인한다.

위 세 가지를 설명할 수 있으면 이번 단계 완료. 다음에는 LLM 연결 없이 먼저 요청 로그 저장을 구현할 수 있다.
