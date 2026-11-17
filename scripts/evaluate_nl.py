"""자연어 검색 조건 해석 성능을 평가셋으로 측정한다.

    python -m scripts.evaluate_nl --engine rule                          # LLM 없이 규칙 기반 기준선 (무료)
    python -m scripts.evaluate_nl --engine llm --prompt v2               # 실제 Gemini 호출 (질문당 1회)
    python -m scripts.evaluate_nl --engine llm --prompt v1               # 개선 전 프롬프트로 비교
    python -m scripts.evaluate_nl --engine llm --prompt v2 --dataset holdout  # 검증용 질문
    python -m scripts.evaluate_nl --engine llm --limit 10                # 일부만 빠르게 확인

dataset
    dev      data/eval_nl_queries.json (84문항). 오답을 분석해 프롬프트를 고칠 때 사용한 질문.
    holdout  data/eval_nl_holdout.json (30문항). 프롬프트 작성에 쓰지 않은 표현으로 일반화 확인.

서버와 DB 없이 동작한다. 조건 해석은 app.query_service.interpret_query를 그대로 호출하고,
결과 상품은 data/products.csv에 SQL과 같은 규칙을 적용해 계산한다.
(SQL 자체의 정확성은 scripts.evaluate_products가 별도로 검증한다.)
"""
import argparse
import csv
import json
import os
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ('gift_only', 'individual_only', 'exclude_individual', 'max_sweetness',
          'min_price', 'max_price', 'sort')
DEFAULTS = {'gift_only': False, 'individual_only': False, 'exclude_individual': False,
            'max_sweetness': None, 'min_price': None, 'max_price': None, 'sort': 'default'}
DATASETS = {'dev': 'eval_nl_queries.json', 'holdout': 'eval_nl_holdout.json'}
BEHAVIOR_KO = {'search': '검색', 'clarify': '확인 질문', 'unsupported': '미지원 안내'}


def load_catalog(path=ROOT / 'data' / 'products.csv'):
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key in ('product_id', 'price', 'sweetness', 'gift_available', 'is_active'):
            row[key] = int(row[key])
    return rows


def filter_catalog(catalog, cond):
    """product_repository.search_products와 같은 규칙으로 상품 ID 목록을 만든다."""
    c = {**DEFAULTS, **cond}
    items = [p for p in catalog if p['is_active'] == 1]
    if c['gift_only']:
        items = [p for p in items if p['gift_available'] == 1]
    if c['individual_only']:
        items = [p for p in items if p['packaging'] == 'individual']
    if c['max_sweetness'] is not None:
        items = [p for p in items if p['sweetness'] <= c['max_sweetness']]
    if c['exclude_individual']:
        items = [p for p in items if p['packaging'] != 'individual']
    if c['min_price'] is not None:
        items = [p for p in items if p['price'] >= c['min_price']]
    if c['max_price'] is not None:
        items = [p for p in items if p['price'] <= c['max_price']]
    if c['sort'] == 'price_asc':
        items.sort(key=lambda p: (p['price'], p['product_id']))
    elif c['sort'] == 'price_desc':
        items.sort(key=lambda p: (-p['price'], p['product_id']))
    else:
        items.sort(key=lambda p: p['product_id'])
    return [p['product_id'] for p in items]


def classify(intent):
    """app.main.recommend_products와 같은 분기로 응답 종류를 정한다."""
    if intent.unsupported:
        return 'unsupported'
    if not intent.has_condition() or intent.needs_clarification:
        return 'clarify'
    return 'search'


def fields_of(intent):
    return {k: getattr(intent, k) for k in FIELDS}


def matches(pred_behavior, pred_fields, accept):
    for option in accept:
        if option['behavior'] != pred_behavior:
            continue
        if pred_behavior != 'search':
            return True
        if pred_fields == {**DEFAULTS, **option['intent']}:
            return True
    return False


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    index = min(len(values) - 1, max(0, round(q / 100 * (len(values) - 1))))
    return values[index]


def pct(n, d):
    return f'{n / d * 100:.1f}% ({n}/{d})' if d else '-'


def run(args):
    if args.engine == 'rule':
        os.environ['LLM_QUERY_ENABLED'] = 'false'
    else:
        os.environ['LLM_ENABLED'] = 'true'
        os.environ['LLM_QUERY_ENABLED'] = 'true'
    if args.model:
        os.environ['LLM_MODEL'] = args.model
    if args.prompt:
        os.environ['LLM_QUERY_PROMPT_VERSION'] = args.prompt
    # 환경변수를 정한 뒤 import해야 .env보다 명령행 설정이 우선한다.
    from app.query_service import interpret_query

    dataset = json.loads((ROOT / 'data' / DATASETS[args.dataset]).read_text(encoding='utf-8'))
    cases = dataset['cases'][:args.limit] if args.limit else dataset['cases']
    catalog = load_catalog()
    rows = []
    for i, case in enumerate(cases, 1):
        intent, meta = interpret_query(case['query'], f"eval-{case['id']}")
        if args.engine == 'llm' and meta.get('error_code') == 'http_429' and args.wait_429:
            print(f'  429(요청 한도) → {args.wait_429}초 대기 후 1회 재시도', flush=True)
            time.sleep(args.wait_429)
            intent, meta = interpret_query(case['query'], f"eval-{case['id']}-retry")
        behavior = classify(intent)
        pred = fields_of(intent)
        gold = case['accept'][0]
        gold_ids = filter_catalog(catalog, gold['intent']) if gold['behavior'] == 'search' else []
        pred_ids = filter_catalog(catalog, pred) if behavior == 'search' else []
        partial_ids = filter_catalog(catalog, case['partial']) if case.get('partial') else []
        # invalid_output은 모델이 스키마를 어긴 것이므로 모델 오류로 센다.
        # 네트워크·한도·키 문제만 인프라 오류로 보고 정확도에서 제외한다.
        fallback = args.engine == 'llm' and meta['status'] == 'fallback'
        api_error = fallback and meta.get('error_code') != 'invalid_output'
        invalid_output = fallback and meta.get('error_code') == 'invalid_output'
        row = {
            'id': case['id'], 'category': case['category'], 'query': case['query'],
            'gold_behavior': gold['behavior'], 'pred_behavior': behavior,
            'correct': (not (args.engine == 'llm' and meta.get('error_code') == 'invalid_output'))
                       and matches(behavior, pred, case['accept']),
            'accept_search': any(o['behavior'] == 'search' for o in case['accept']),
            'accepted_behaviors': sorted({o['behavior'] for o in case['accept']}),
            'pred_fields': pred, 'gold_fields': {**DEFAULTS, **gold.get('intent', {})},
            'unsupported': intent.unsupported, 'needs_clarification': intent.needs_clarification,
            'pred_ids': pred_ids, 'gold_ids': gold_ids, 'partial_ids': partial_ids,
            'result_count': len(pred_ids),
            'status': meta['status'], 'error_code': meta.get('error_code'),
            'latency_ms': meta.get('latency_ms'), 'usage': meta.get('usage'),
            'prompt_version': meta.get('prompt_version'),
            'invalid_detail': meta.get('invalid_detail'),
            'raw_output_preview': meta.get('raw_output_preview'),
            'api_error': api_error, 'invalid_output': invalid_output, 'note': case.get('note'),
        }
        rows.append(row)
        mark = 'API오류' if api_error else ('형식오류' if invalid_output else ('PASS' if row['correct'] else 'FAIL'))
        print(f"[{i:>2}/{len(cases)}] {mark:<5} {case['id']} {BEHAVIOR_KO[behavior]:<6} "
              f"결과 {len(pred_ids):>2}개 | {case['query']}", flush=True)
        if args.engine == 'llm' and i < len(cases):
            time.sleep(args.sleep)
    return dataset, rows


def summarize(rows, args):
    valid = [r for r in rows if not r['api_error']]
    lines = []
    add = lines.append
    versions = sorted({r['prompt_version'] for r in rows if r.get('prompt_version')})
    title = [args.engine, args.dataset]
    if args.engine == 'llm':
        title.append('prompt ' + ','.join(versions or ['-']))
    if args.model:
        title.append(args.model)
    add(f"# 자연어 검색 평가 결과 ({' / '.join(title)})")
    add('')
    add(f"- 실행 시각(UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    add(f"- 질문 수: {len(rows)}개, API 오류로 제외: {len(rows) - len(valid)}개")
    if len(rows) != len(valid):
        codes = Counter(r['error_code'] for r in rows if r['api_error'])
        add(f"- API 오류 코드: {dict(codes)} (네트워크·한도·키 문제라 정확도에서 제외)")
    invalid = sum(r['invalid_output'] for r in valid)
    if invalid:
        add(f"- 형식 오류(invalid_output): {invalid}개 — 모델 JSON이 스키마 검증 실패. 오답으로 집계")
    add('')
    add('## 핵심 지표')
    add('')
    add('| 지표 | 값 | 의미 |')
    add('|---|---|---|')
    add(f"| 전체 정답률 | {pct(sum(r['correct'] for r in valid), len(valid))} | 허용 정답 중 하나와 응답 종류·조건이 모두 일치 |")
    decide = sum(r['pred_behavior'] in r['accepted_behaviors'] for r in valid)
    add(f"| 검색/거절 판단 정확도 | {pct(decide, len(valid))} | 조건 값과 무관하게 응답 종류(검색/확인 질문/미지원)만 맞았는지 |")
    s_gold = [r for r in valid if r['gold_behavior'] == 'search']
    s_both = [r for r in s_gold if r['pred_behavior'] == 'search']
    add(f"| 검색 질문 정답률 | {pct(sum(r['correct'] for r in s_gold), len(s_gold))} | 검색해야 하는 질문에서 조건까지 정확 |")
    add(f"| 검색 결과 일치율 | {pct(sum(r['pred_ids'] == r['gold_ids'] for r in s_gold), len(s_gold))} | 대표 정답과 상품 ID·순서가 동일 |")
    # 과잉 거절: 검색이 허용 정답인데 허용되지 않은 거절로 0건을 준 경우
    over = [r for r in valid if r['accept_search'] and r['pred_behavior'] not in r['accepted_behaviors']]
    add(f"| 과잉 거절률 | {pct(len(over), sum(r['accept_search'] for r in valid))} | 검색이 정답인데 확인 질문/미지원으로 0건 반환 |")
    wrong_search = [r for r in valid if not r['accept_search'] and r['pred_behavior'] == 'search']
    add(f"| 잘못된 검색률 | {pct(len(wrong_search), sum(not r['accept_search'] for r in valid))} | 거절이 정답인데 조건을 무시하고 검색 |")
    served = [r for r in valid if r['result_count'] > 0]
    add(f"| 결과 제공률 | {pct(len(served), len(valid))} | 사용자가 상품을 1개 이상 받은 비율 |")
    lat = [r['latency_ms'] for r in valid if r['latency_ms']]
    if lat:
        add(f"| 지연시간 p50 / p95 | {percentile(lat, 50)}ms / {percentile(lat, 95)}ms | 조건 해석 LLM 호출 1회 |")
    tokens = [r['usage'].get('total_tokens') for r in valid if r.get('usage') and r['usage'].get('total_tokens')]
    if tokens:
        add(f"| 평균 토큰 | {round(statistics.mean(tokens))} | 질문당 조건 해석 토큰 |")
    add('')

    add('## 카테고리별')
    add('')
    add('| 카테고리 | 정답률 | 결과 제공률 | 과잉 거절 |')
    add('|---|---|---|---|')
    by_cat = defaultdict(list)
    for r in valid:
        by_cat[r['category']].append(r)
    for cat, items in by_cat.items():
        over_n = sum(r['accept_search'] and r['pred_behavior'] not in r['accepted_behaviors'] for r in items)
        add(f"| {cat} | {pct(sum(r['correct'] for r in items), len(items))} | "
            f"{pct(sum(r['result_count'] > 0 for r in items), len(items))} | {over_n} |")
    add('')

    if s_both:
        add('## 필드별 정확도 (정답·예측 모두 검색인 질문)')
        add('')
        add('| 필드 | 정확도 |')
        add('|---|---|')
        for f in FIELDS:
            add(f"| {f} | {pct(sum(r['pred_fields'][f] == r['gold_fields'][f] for r in s_both), len(s_both))} |")
        add('')

    partial = [r for r in valid if r['pred_behavior'] != 'search' and r['partial_ids']]
    add('## 정책상 거절됐지만 부분 검색이 가능했던 질문')
    add('')
    add('지원 조건만으로도 상품을 보여줄 수 있었지만, 미지원 단어 하나 때문에 0건이 된 질문입니다.')
    add('')
    if partial:
        for r in partial:
            add(f"- `{r['id']}` {r['query']} → {BEHAVIOR_KO[r['pred_behavior']]}, "
                f"지원 조건만 적용 시 {len(r['partial_ids'])}개 (미지원: {', '.join(r['unsupported']) or '-'})")
    else:
        add('- 없음')
    add('')

    fails = [r for r in valid if not r['correct']]
    add(f'## 오답 목록 ({len(fails)}개)')
    add('')
    if fails:
        add('| ID | 질문 | 정답 | 예측 | 예측 조건 / 미지원 |')
        add('|---|---|---|---|---|')
        for r in fails:
            diff = {k: v for k, v in r['pred_fields'].items() if v != DEFAULTS[k]}
            extra = f"미지원={r['unsupported']}" if r['unsupported'] else ''
            if r['needs_clarification']:
                extra += ' 확인필요'
            if r['invalid_output']:
                extra = f"형식 오류 → 규칙 fallback ({r.get('invalid_detail') or '원인 미기록'})"
            add(f"| {r['id']} | {r['query']} | {BEHAVIOR_KO[r['gold_behavior']]} | "
                f"{BEHAVIOR_KO[r['pred_behavior']]} | {json.dumps(diff, ensure_ascii=False)} {extra} |")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--engine', choices=('llm', 'rule'), default='llm')
    parser.add_argument('--model', help='LLM_MODEL을 이번 실행에만 덮어쓴다')
    parser.add_argument('--prompt', choices=('v1', 'v2'), help='조건 해석 프롬프트 버전 (기본: .env 또는 v2)')
    parser.add_argument('--dataset', choices=tuple(DATASETS), default='dev')
    parser.add_argument('--limit', type=int, help='앞에서부터 N개만 실행')
    parser.add_argument('--sleep', type=float, default=4.0, help='LLM 호출 간 대기(초). 무료 한도 대비')
    parser.add_argument('--wait-429', type=float, default=30.0, help='429 응답 시 대기 후 1회 재시도(0이면 끔)')
    args = parser.parse_args()

    dataset, rows = run(args)
    report = summarize(rows, args)
    out = ROOT / 'docs' / 'evaluation'
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M')
    tag = '-'.join([args.engine, args.dataset]
                   + ([args.prompt] if args.engine == 'llm' and args.prompt else [])
                   + ([args.model] if args.model else []))
    (out / f'nl-eval-{tag}-{stamp}.json').write_text(
        json.dumps({'args': vars(args), 'rows': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
    md_path = out / f'nl-eval-{tag}-{stamp}.md'
    md_path.write_text(report, encoding='utf-8')
    print()
    print(report)
    print('저장:', md_path)


if __name__ == '__main__':
    main()
