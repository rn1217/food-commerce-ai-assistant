import json
import os
import unittest
from unittest.mock import MagicMock, patch

from app.llm_client import LLMError
from app.query_service import SearchIntent, empty_intent, interpret_query, safe_rule_intent
from app.product_repository import search_products
from test_faq import request_api


def model_reply(**changes):
    values = empty_intent().model_dump()
    values.update(changes)
    return {'text': json.dumps(values), 'model': 'test', 'usage': {'total_tokens': 50}}


class IntentTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'LLM_ENABLED': 'true', 'LLM_QUERY_ENABLED': 'true'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_cheapest_and_value_force_price_ascending(self):
        for field in ('include_cheapest', 'value_requested'):
            with self.subTest(field=field):
                intent = SearchIntent.model_validate_json(model_reply(**{field: True})['text'])
                self.assertEqual(intent.sort, 'price_asc')
                self.assertTrue(intent.has_condition())

    def test_price_range_and_exclusion_reach_sql_arguments(self):
        with patch('app.query_service.generate_text', return_value=model_reply(min_price=10000, max_price=20000, exclude_individual=True)):
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
                SearchIntent.model_validate_json(model_reply(**changes)['text'])
        with self.assertRaises(ValueError):
            SearchIntent.model_validate_json('{}')

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
        patch.dict(os.environ, {'LLM_ENABLED': 'true', 'LLM_QUERY_ENABLED': 'true'}).start()
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
