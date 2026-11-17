import json
import os
import unittest
from unittest.mock import MagicMock, patch

from app.llm_client import LLMError
from app.query_service import (SearchIntent, build_prompt_v2, empty_intent, interpret_query,
                               prompt_version, safe_rule_intent)
from app.product_repository import search_products
from test_faq import request_api


def intent_json(**changes):
    # 서비스 내부 SearchIntent 형식(v1 LLM 출력 형식과 같음)
    values = empty_intent().model_dump()
    values.update(changes)
    return json.dumps(values)


def v2_values(**changes):
    values = {'gift_only': False, 'packaging': 'any', 'max_sweetness': None, 'min_price': None,
              'max_price': None, 'sort': 'default', 'include_cheapest': False,
              'value_requested': False, 'needs_clarification': False, 'unsupported': []}
    values.update(changes)
    return values


def model_reply(**changes):
    # 기본 프롬프트(v2)의 LLM 출력 형식
    return {'text': json.dumps(v2_values(**changes)), 'model': 'test', 'usage': {'total_tokens': 50}}


def raw_reply(text):
    return {'text': text, 'model': 'test', 'usage': {'total_tokens': 50}}


class IntentTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'LLM_ENABLED': 'true', 'LLM_QUERY_ENABLED': 'true',
                                           'LLM_QUERY_PROMPT_VERSION': 'v2'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_cheapest_and_value_force_price_ascending(self):
        for field in ('include_cheapest', 'value_requested'):
            with self.subTest(field=field):
                intent = SearchIntent.model_validate_json(intent_json(**{field: True}))
                self.assertEqual(intent.sort, 'price_asc')
                self.assertTrue(intent.has_condition())

    def test_price_range_and_exclusion_reach_sql_arguments(self):
        with patch('app.query_service.generate_text', return_value=model_reply(min_price=10000, max_price=20000, packaging='bulk')):
            intent, meta = interpret_query('1만원부터 2만원까지 개별포장 제외', 'id')
        self.assertEqual(meta['status'], 'success')
        self.assertEqual(intent.search_arguments(), dict(gift_only=False, individual_only=False, max_sweetness=None,
                                                        min_price=10000, max_price=20000, exclude_individual=True))

    def test_rejects_bad_types_conflicts_missing_keys_and_sql_sort(self):
        cases = [dict(min_price=-1), dict(max_price=True), dict(max_price='20000'),
                 dict(min_price=20000, max_price=10000), dict(max_sweetness=8),
                 dict(individual_only=True, exclude_individual=True), dict(sort='price; DROP TABLE products'),
                 dict(unsupported=['x'*101])]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                SearchIntent.model_validate_json(intent_json(**changes))
        with self.assertRaises(ValueError):
            SearchIntent.model_validate_json('{}')

    def test_v2_packaging_value_maps_to_existing_search_arguments(self):
        expected = {'individual': (True, False), 'bulk': (False, True), 'any': (False, False)}
        for packaging, (only, exclude) in expected.items():
            with self.subTest(packaging=packaging):
                with patch('app.query_service.generate_text', return_value=model_reply(packaging=packaging)):
                    intent, meta = interpret_query('포장 조건', 'id')
                self.assertEqual((intent.individual_only, intent.exclude_individual), (only, exclude))
                self.assertEqual((meta['status'], meta['prompt_version']), ('success', 'v2'))

    def test_v2_rejects_two_boolean_packaging_and_records_reason(self):
        # v1 형식(포함+제외 동시 true)은 v2 스키마에서 형식 오류이며, 원인과 원본 일부를 남긴다.
        old_shape = intent_json(individual_only=True, exclude_individual=True)
        with patch('app.query_service.generate_text', return_value=raw_reply(old_shape)):
            with self.assertLogs('uvicorn.error', level='WARNING') as logs:
                intent, meta = interpret_query('개별포장 아닌 상품', 'id')
        self.assertEqual((meta['status'], meta['error_code']), ('fallback', 'invalid_output'))
        self.assertTrue(meta['invalid_detail'])
        self.assertEqual(meta['raw_output_preview'], old_shape[:300])
        self.assertTrue(any('query_invalid_output' in line for line in logs.output))
        self.assertFalse(intent.has_condition())

    def test_v1_keeps_original_schema_and_names_packaging_conflict(self):
        with patch.dict(os.environ, {'LLM_QUERY_PROMPT_VERSION': 'v1'}):
            with patch('app.query_service.generate_text', return_value=raw_reply(intent_json(individual_only=True))) as send:
                intent, meta = interpret_query('개별포장 상품', 'id')
            self.assertTrue(intent.individual_only)
            self.assertEqual(meta['prompt_version'], 'v1')
            self.assertIn('exclude_individual', send.call_args.args[0])
            conflict = intent_json(individual_only=True, exclude_individual=True)
            with patch('app.query_service.generate_text', return_value=raw_reply(conflict)):
                with self.assertLogs('uvicorn.error', level='WARNING'):
                    _, meta = interpret_query('개별포장 아닌 상품', 'id')
        self.assertEqual(meta['error_code'], 'invalid_output')
        self.assertIn('conflicting_packaging', meta['invalid_detail'])

    def test_prompt_version_default_and_v2_prompt_rules(self):
        with patch.dict(os.environ, {'LLM_QUERY_PROMPT_VERSION': 'v9'}):
            self.assertEqual(prompt_version(), 'v2')
        prompt = build_prompt_v2('부모님 선물')
        self.assertIn('받는 사람', prompt)
        self.assertIn('"packaging"', prompt)
        self.assertNotIn('individual_only', prompt)
        self.assertNotIn('"description"', prompt)
        self.assertTrue(prompt.endswith('질문 데이터: "부모님 선물"'))

    def test_error_does_not_drop_unrecognized_conditions(self):
        with patch('app.query_service.generate_text', side_effect=LLMError('http_503')):
            with self.assertLogs('uvicorn.error', level='WARNING'):
                intent, meta = interpret_query('2만원 이하 개별포장 제외 선물', 'id')
        self.assertFalse(intent.has_condition())
        self.assertTrue(intent.needs_clarification)
        self.assertEqual(meta['error_code'], 'http_503')

    def test_disabled_no_call_and_simple_fallback(self):
        with patch.dict(os.environ, {'LLM_ENABLED': 'false'}), patch('app.query_service.generate_text') as send:
            intent, meta = interpret_query('너무 달지 않은 개별포장 선물', 'id')
        send.assert_not_called()
        self.assertEqual(intent.search_arguments(), dict(gift_only=True, individual_only=True, max_sweetness=2))
        self.assertEqual(meta['engine'], 'rule')
        for query in ('개별포장 제외 선물', '매운 선물', '선물 말고', '2만원 이하 선물'):
            self.assertFalse(safe_rule_intent(query).has_condition())


class QueryApiTests(unittest.TestCase):
    def setUp(self):
        patch.dict(os.environ, {'LLM_ENABLED': 'true', 'LLM_QUERY_ENABLED': 'true',
                                'LLM_QUERY_PROMPT_VERSION': 'v2'}).start()
        self.writer = patch('app.log_service.insert_request_log').start()
        self.generate = patch('app.query_service.generate_text').start()
        self.search = patch('app.main.search_products', return_value=[]).start()
        self.reasons = patch('app.llm_recommendation_service.generate_text').start()
        self.addCleanup(patch.stopall)

    def test_unsupported_condition_prevents_partial_search(self):
        self.generate.return_value = model_reply(gift_only=True, unsupported=['매운맛'])
        status, data = request_api('/api/recommendations', {'query': '매운 선물'})
        self.assertEqual(status, 200)
        self.assertIn('매운맛', data['message'])
        self.search.assert_not_called()
        self.reasons.assert_not_called()

    def test_cheapest_query_orders_and_logs_interpretation(self):
        self.generate.return_value = model_reply(value_requested=True, include_cheapest=True)
        status, data = request_api('/api/recommendations', {'query': '가성비 있는 상품을 추천해줘 제일 싼 상품도 포함해서'})
        self.assertEqual(status, 200)
        self.search.assert_called_once_with(gift_only=False, individual_only=False, max_sweetness=None, sort='price_asc')
        self.assertIn('중량·품질 비교가 아닌', data['message'])
        self.assertEqual(data['interpretation']['status'], 'success')
        self.assertEqual(self.writer.call_args.args[0]['engine'], 'gemini')
        self.reasons.assert_not_called()

    def test_malformed_interpretation_returns_guidance_not_full_catalog(self):
        self.generate.return_value = {'text': 'not json', 'model': 'test', 'usage': {}}
        with self.assertLogs('uvicorn.error', level='WARNING'):
            status, data = request_api('/api/recommendations', {'query': '제일 싼 선물'})
        self.assertEqual((status, data['count']), (200, 0))
        self.search.assert_not_called()
        self.assertEqual(self.writer.call_args.args[0]['status'], 'fallback')


class PriceRepositoryTests(unittest.TestCase):
    def test_prices_and_packaging_are_bound_and_order_is_allowlisted(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = []
        with patch('app.product_repository.get_connection') as connect:
            connect.return_value.__enter__.return_value = conn
            search_products(exclude_individual=True, min_price=10000, max_price=20000, sort='price_asc')
        sql, params = cur.execute.call_args.args
        self.assertEqual(params, (True, 'individual', 10000, 20000))
        self.assertIn('price >= %s', sql)
        self.assertIn('price <= %s', sql)
        self.assertIn('packaging <> %s', sql)
        self.assertIn('ORDER BY price ASC, product_id ASC', sql)
        self.assertNotIn('20000', sql)

    def test_sort_injection_rejected_before_connection(self):
        with patch('app.product_repository.get_connection') as connect:
            with self.assertRaises(ValueError):
                search_products(sort='price; DROP TABLE products')
        connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
