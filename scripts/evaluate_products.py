"""고정 기대 ID로 실제 MySQL 검색을 검사한다. --live는 실제 HTTP/LLM도 호출한다."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.product_repository import search_products
from scripts.init_products import ROOT, COLUMNS, load_products
from app.database import get_connection

# 기대값은 현재 30개 가상 상품에 대해 직접 정한 정답이다.
# SQL 결과에서 정답을 만들지 않으므로 필터 누락도 발견할 수 있다.
CASES = [
    ('gift', '선물용 상품 추천해줘', {'gift_only': True},
     [1,2,3,5,11,12,13,14,15,16,17,18,19,20,26,27,28,29,30]),
    ('individual', '개별포장 상품 추천해줘', {'individual_only': True},
     [1,2,4,5,6,8,10,12,14,16,18,20,22,24,26,28,30]),
    ('bulk', '개별포장 제외하고 추천해줘', {'exclude_individual': True},
     [3,7,9,11,13,15,17,19,21,23,25,27,29]),
    ('low_sweetness', '너무 달지 않은 상품 추천해줘', {'max_sweetness': 2},
     [1,3,4,5,6,7,9,10,12,13,15,17,18,20,21,22,25,26,29,30]),
    ('gift_individual_low', '선물용인데 너무 달지 않고 개별포장된 상품 추천해줘',
     {'gift_only': True, 'individual_only': True, 'max_sweetness': 2}, [1,5,12,18,20,26,30]),
    ('max_inclusive', '2만원 이하 상품 추천해줘', {'max_price': 20000},
     [4,6,7,8,9,10,11,12,21,22,23,24]),
    ('max_exclusive', '2만원 미만 상품 추천해줘', {'max_price': 19999},
     [4,6,7,8,9,10,11,21,22,23,24]),
    ('min_exclusive', '5만원 초과 상품 추천해줘', {'min_price': 50001}, [19,20]),
    ('exact_price', '정확히 2만원인 상품 추천해줘', {'min_price': 20000, 'max_price': 20000}, [12]),
    ('range', '1만원 이상 2만원 이하 상품 추천해줘', {'min_price': 10000, 'max_price': 20000},
     [4,9,10,11,12,21,22,23,24]),
    ('gift_bulk_budget', '3만원 이하 선물용인데 개별포장은 제외해줘',
     {'gift_only': True, 'exclude_individual': True, 'max_price': 30000}, [11,13,15]),
    ('no_match', '천원 이하 상품 추천해줘', {'max_price': 1000}, []),
    ('value_cheapest', '가성비 있는 상품을 추천해줘 제일 싼 상품도 포함해서', {'sort': 'price_asc'},
     [6,7,8,9,21,4,22,10,23,11,24,12,13,25,2,14,26,1,15,3,27,5,28,16,17,29,18,30,19,20]),
    ('price_desc', '5만원 이상 상품을 비싼 순으로 추천해줘', {'min_price': 50000, 'sort': 'price_desc'},
     [20,19,30]),
    ('budget_bulk', '2만원 이하 상품 중 개별포장은 제외해줘',
     {'max_price': 20000, 'exclude_individual': True}, [7,9,11,21,23]),
]
LIVE_IDS = ('gift_individual_low', 'value_cheapest', 'budget_bulk')


def assert_dataset():
    expected = load_products(ROOT / 'data' / 'products.csv').to_dict(orient='records')
    with get_connection() as connection, connection.cursor() as cursor:
        cursor.execute('SELECT ' + ', '.join(COLUMNS) + ' FROM products ORDER BY product_id')
        actual = cursor.fetchall()
    if actual != expected:
        raise ValueError('DB와 고정 평가 CSV가 다릅니다. 먼저 데이터를 확인하세요. 자동 덮어쓰기는 하지 않습니다.')
    return {p['product_id']: p for p in actual}


def run_live(base_url, case, catalog):
    name, query, _, expected = case
    started = perf_counter()
    result = {'case': name, 'query': query, 'expected_ids': expected}
    try:
        request = Request(base_url.rstrip('/') + '/api/recommendations',
                          data=json.dumps({'query': query}).encode('utf-8'),
                          headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=125) as response:
            data = json.load(response)
        products = data['products']
        actual = [p['product_id'] for p in products]
        # ID 외에도 DB의 이름/가격/속성을 모델이 덮어쓰지 않았는지 확인한다.
        facts_ok = all(p['product_id'] in catalog and all(
            p[k] == catalog[p['product_id']][k] for k in COLUMNS if k != 'is_active') for p in products)
        reason_ids = [p['product_id'] for p in products if p.get('recommendation_reason')]
        reasons_ok = reason_ids == actual[:3] if data['llm']['status'] == 'success' else not reason_ids
        with get_connection() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT response, status, error_code FROM ai_logs WHERE request_id=%s', (data['request_id'],))
            log = cursor.fetchone()
        log_ok = log is not None and json.loads(log['response']) == data
        retrieval_ok = actual == expected
        ai_ok = data['interpretation']['status'] == 'success' and data['llm']['status'] == 'success'
        result.update(actual_ids=actual, retrieval_ok=retrieval_ok, facts_ok=facts_ok,
                      reasons_scope_ok=reasons_ok, log_ok=log_ok, ai_ok=ai_ok,
                      passed=retrieval_ok and facts_ok and reasons_ok and log_ok and ai_ok,
                      response=data)
    except (HTTPError, URLError, TimeoutError) as exc:
        result.update(passed=False, error=type(exc).__name__)
    result['elapsed_ms'] = round((perf_counter() - started) * 1000)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='3개 질문에 실제 LLM 호출 및 요청 로그 저장')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    catalog = assert_dataset()
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'product_count': len(catalog),
              'scope': 'SQL 15 cases; natural language only when live enabled', 'sql': [], 'live': []}
    for name, query, filters, expected in CASES:
        started = perf_counter()
        actual = [p['product_id'] for p in search_products(**filters)]
        row = {'case': name, 'query': query, 'filters': filters, 'expected_ids': expected,
               'actual_ids': actual, 'passed': actual == expected,
               'elapsed_ms': round((perf_counter() - started) * 1000)}
        report['sql'].append(row)
        print(f"SQL {name}: {'PASS' if row['passed'] else 'FAIL'} count={len(actual)}", flush=True)
    if args.live:
        for case in CASES:
            if case[0] in LIVE_IDS:
                row = run_live(args.base_url, case, catalog)
                report['live'].append(row)
                print(f"LIVE {case[0]}: {'PASS' if row['passed'] else 'FAIL'} ms={row['elapsed_ms']}", flush=True)
    destination = ROOT / 'docs' / 'evaluation'
    destination.mkdir(exist_ok=True)
    # 실제 호출 기록을 SQL-only 실행으로 덮어쓰지 않는다.
    path = destination / ('products-live.json' if args.live else 'products-sql.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Report:', path)
    if not all(row['passed'] for row in report['sql'] + report['live']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
