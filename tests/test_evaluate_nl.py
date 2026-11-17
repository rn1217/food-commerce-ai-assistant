import json
import unittest

from scripts.evaluate_nl import DATASETS, DEFAULTS, FIELDS, ROOT, filter_catalog, load_catalog
from scripts.evaluate_products import CASES


class NaturalLanguageEvalSetTests(unittest.TestCase):
    def test_catalog_filter_matches_hand_labeled_sql_cases(self):
        # 평가 스크립트의 CSV 필터가 실제 SQL 평가의 수동 정답과 같아야 한다.
        catalog = load_catalog()
        for name, _, filters, expected in CASES:
            with self.subTest(case=name):
                self.assertEqual(filter_catalog(catalog, filters), expected)

    def test_eval_sets_are_well_formed_and_disjoint(self):
        sets = {name: json.loads((ROOT / 'data' / file).read_text(encoding='utf-8'))['cases']
                for name, file in DATASETS.items()}
        queries = [c['query'] for cases in sets.values() for c in cases]
        ids = [c['id'] for cases in sets.values() for c in cases]
        # 검증용 질문이 개발용 질문과 겹치면 일반화 확인이 되지 않는다.
        self.assertEqual(len(queries), len(set(queries)))
        self.assertEqual(len(ids), len(set(ids)))
        for case in (c for cases in sets.values() for c in cases):
            with self.subTest(case=case['id']):
                self.assertTrue(case['query'].strip())
                self.assertTrue(case['accept'])
                for option in case['accept']:
                    self.assertIn(option['behavior'], ('search', 'clarify', 'unsupported'))
                    if option['behavior'] == 'search':
                        self.assertTrue(set(option['intent']) <= set(FIELDS))
                        self.assertNotEqual({**DEFAULTS, **option['intent']}, DEFAULTS)
                        merged = {**DEFAULTS, **option['intent']}
                        self.assertFalse(merged['individual_only'] and merged['exclude_individual'])


if __name__ == '__main__':
    unittest.main()
