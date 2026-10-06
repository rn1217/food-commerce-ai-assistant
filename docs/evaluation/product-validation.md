# 상품 확장 및 실제 검증 결과 (2026-10-06)

## 평가 조건

- 데이터: 가상 상품 30개. 가격 4,500~65,000원, 개별포장 17개·묶음포장 13개.
- 기존 5개를 보존하고 25개 추가. 두 번째 입력은 added=0, skipped=30.
- DB 조건 검증은 실제 MySQL에 직접 실행. 15개의 고정 기대 ID 및 정렬 순서와 비교.
- 자연어 검증은 실행 중인 로컬 FastAPI에 HTTP 요청. 실제 Gemini 호출과 실제 ai_logs 저장을 포함.
- API 키·DB 비밀번호는 결과 파일에 포함하지 않음.

## SQL 및 자동 테스트

실제 DB 검색 15/15 통과. 자동 테스트 60개 통과(외부 API·DB는 자동 테스트에서 모의 처리). 두 결과는 서로 다른 검증이다.

| DB 사례 | 검색 수 | 결과 |
| --- | ---: | --- |
| gift | 19 | PASS |
| individual | 17 | PASS |
| bulk | 13 | PASS |
| low_sweetness | 20 | PASS |
| gift_individual_low | 7 | PASS |
| max_inclusive | 12 | PASS |
| max_exclusive | 11 | PASS |
| min_exclusive | 2 | PASS |
| exact_price | 1 | PASS |
| range | 9 | PASS |
| gift_bulk_budget | 3 | PASS |
| no_match | 0 | PASS |
| value_cheapest | 30 | PASS |
| price_desc | 3 | PASS |
| budget_bulk | 5 | PASS |

## 실제 자연어 HTTP 평가

최종 모델: gemini-3.5-flash-lite. 같은 3개 질문을 프롬프트 보완 후 재실행했다. 두 AI 단계 성공, 기대 ID/순서 일치, DB 속성 보존, 설명 대상 최대 3개, 로그 응답 일치를 검사했다.

| 질문 | 상품 수 | HTTP 전체 시간 | 해석 입력 토큰 | 설명 입력 토큰 | 결과 |
| --- | ---: | ---: | ---: | ---: | --- |
| 선물용인데 너무 달지 않고 개별포장된 상품 추천해줘 | 7 | 6490ms | 895 | 474 | PASS |
| 가성비 있는 상품을 추천해줘 제일 싼 상품도 포함해서 | 30 | 6843ms | 894 | 462 | PASS |
| 2만원 이하 상품 중 개별포장은 제외해줘 | 5 | 7259ms | 890 | 460 | PASS |

모든 검색 상품을 반환하되 이유 생성에는 앞 3개만 전달한다. 최저가 질문은 검색 30개/설명 후보 3개였다. 전체 30개를 전달하는 방식과 입력 토큰을 비교한 실험은 아니므로 토큰 절감률을 주장하지 않는다.

## 발견한 문제와 개선

1. 기존 gemini-3.8-flash에서는 3개 질문 모두 조건 해석 단계에서 실패했다. network_or_timeout 1건, http_503 2건으로 상품 결과는 없었고 오류 로그는 저장됐다. 외부 서비스의 상세 원인은 확정할 수 없다.
2. 동일 질문을 Flash-Lite로 비교했을 때 API 호출은 동작했지만 1개 질문에서 요청 동사인 “추천”을 unsupported 상품 조건으로 잘못 분류했다. 두 다른 질문은 통과했다.
3. 프롬프트에 요청 동사와 상품 조건의 구분, 지원 가능한 복합 질문 예시, 미지정 가격은 null이라는 규칙을 추가했다. unsupported를 코드에서 무조건 지우거나 검증을 완화하지 않았다.
4. 같은 3개 질문 재실행에서 3/3 통과했다. 로컬 .env와 .env.example의 LLM_MODEL을 Flash-Lite로 변경했다. 이미 실행 중인 서버는 재시작해야 새 환경변수가 적용된다.

| 시도 | 결과 | 원본 기록 |
| --- | --- | --- |
| 기존 모델 | 0/3, API 오류 | [변경 전](products-live-before.json) |
| Flash-Lite, 프롬프트 보완 전 | 2/3, 추천 동사 오분류 | [중간 결과](products-live-lite-before-prompt.json) |
| Flash-Lite, 프롬프트 보완 후 | 3/3 | [최종 결과](products-live.json) |
| SQL 직접 검증 | 15/15 | [SQL 결과](products-sql.json) |

## 해석의 한계

이는 실패 사례를 보고 보완한 개발용 고정 질문 평가다. 별도 미공개 평가셋이 아니며 전체 자연어 정확도 100%를 의미하지 않는다. 모델 변경과 프롬프트 변경이 함께 있으므로 단일 변경의 효과로 해석할 수 없다. 오류 요청과 성공 요청의 시간은 처리 경로도 다르므로 속도 개선률로 비교하지 않는다. 출력 이유의 의미적 사실성은 ID 검사만으로 보장되지 않으며 문장 검토가 필요하다. 브라우저 시각 검증과 새 환경 전체 설치는 수행하지 않았다.

## 재현

```powershell
.\.venv\Scripts\python.exe -m scripts.init_products --check-only
.\.venv\Scripts\python.exe -m scripts.init_products
.\.venv\Scripts\python.exe -m scripts.evaluate_products
.\.venv\Scripts\python.exe -m scripts.evaluate_products --live
```

실제 AI 결과는 모델 상태와 실행 시점에 따라 달라질 수 있다. 실패가 생기면 보고서와 요청 ID를 남겨 다음 비교에 사용한다.
