import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from app.llm_client import LLMError, generate_text
from app.llm_recommendation_service import add_recommendation_reasons, validate_reasons
from test_faq import request_api


def product(pid):
    return dict(product_id=pid, name=f'상품 {pid}', category='한과', price=20000,
                description='가상 상품', sweetness=2, packaging='individual',
                storage_method='room', gift_available=True)


def reply(ids=(1, 5)):
    return {'text': json.dumps({'recommendations': [
        {'product_id': pid, 'reason': '개별포장된 선물용 상품입니다.'} for pid in ids
    ]}), 'model': 'test-model', 'usage': {'total_tokens': 100}}


class RecommendationLLMTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'LLM_ENABLED': 'true', 'LLM_QUERY_ENABLED': 'false'})
        env.start()
        self.addCleanup(env.stop)
        self.writer = patch('app.log_service.insert_request_log').start()
        self.generate = patch('app.llm_recommendation_service.generate_text', return_value=reply()).start()
        self.addCleanup(patch.stopall)
        self.products = [product(1), product(5)]

    def test_success_preserves_db_fields_and_logs_usage(self):
        with patch('app.main.search_products', return_value=self.products):
            status, data = request_api('/api/recommendations', {'query': '선물'})
        self.assertEqual(status, 200)
        self.assertEqual(data['llm']['status'], 'success')
        self.assertEqual(data['products'][0]['name'], '상품 1')
        self.assertIn('recommendation_reason', data['products'][0])
        self.assertNotIn('recommendation_reason', self.products[0])
        record = self.writer.call_args.args[0]
        self.assertEqual((record['engine'], record['status']), ('gemini', 'success'))
        self.assertEqual(record['response']['llm']['usage']['total_tokens'], 100)
        self.writer.assert_called_once()

    def test_api_failure_keeps_products_and_records_fallback(self):
        self.generate.side_effect = LLMError('http_503')
        with patch('app.main.search_products', return_value=self.products):
            with self.assertLogs('uvicorn.error', level='WARNING'):
                status, data = request_api('/api/recommendations', {'query': '선물'})
        self.assertEqual((status, data['products']), (200, self.products))
        record = self.writer.call_args.args[0]
        self.assertEqual((record['status'], record['error_code']), ('fallback', 'http_503'))

    def test_invalid_id_never_reaches_response(self):
        self.generate.return_value = reply((999,))
        with patch('app.main.search_products', return_value=self.products):
            with self.assertLogs('uvicorn.error', level='WARNING'):
                status, data = request_api('/api/recommendations', {'query': '선물'})
        self.assertEqual(status, 200)
        self.assertEqual(data['products'], self.products)
        self.assertEqual(data['llm']['error_code'], 'invalid_output')

    def test_empty_and_unsupported_skip_external_call(self):
        with patch('app.main.search_products', return_value=[]):
            for query in ('선물', '매운 음식'):
                _, data = request_api('/api/recommendations', {'query': query})
                self.assertEqual(data['llm']['status'], 'skipped')
        self.generate.assert_not_called()

    def test_disabled_skips_external_call(self):
        with patch.dict(os.environ, {'LLM_ENABLED': 'false'}):
            products, meta = add_recommendation_reasons('선물', self.products, 'test')
        self.generate.assert_not_called()
        self.assertEqual((products, meta['status']), (self.products, 'disabled'))

    def test_only_three_candidates_sent_but_all_products_retained(self):
        self.generate.return_value = reply((1, 2, 3))
        products, meta = add_recommendation_reasons('선물', [product(i) for i in range(1, 6)], 'test')
        sent = json.loads(self.generate.call_args.args[0].split('\n', 1)[1])
        self.assertEqual([p['product_id'] for p in sent['candidates']], [1, 2, 3])
        self.assertEqual((len(products), meta['candidate_count']), (5, 3))
        self.assertIsNone(products[-1]['recommendation_reason'])

    def test_malformed_or_duplicate_or_missing_output_rejected(self):
        bad = ['not json', '[]', reply((1, 1))['text'], reply((1,))['text'],
               '{"recommendations":[{"product_id":true,"reason":"x"}]}',
               '{"recommendations":[{"product_id":1,"reason":"   "}]}',
               reply(('1', 5))['text'],
               json.dumps({'recommendations': [{'product_id': 1, 'reason': 'x' * 301}]})]
        for text in bad:
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_reasons(text, self.products)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'GEMINI_API_KEY': 'fake-test-key', 'LLM_MODEL': 'test-model'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_http_request_and_text_extraction(self):
        data = {'status': 'completed', 'steps': [{'type': 'model_output', 'content': [{'type': 'text', 'text': '응답'}]}]}
        with patch('app.llm_client.urlopen', return_value=io.BytesIO(json.dumps(data).encode())) as send:
            result = generate_text('테스트')
        req = send.call_args.args[0]
        self.assertEqual(req.method, 'POST')
        self.assertNotIn('fake-test-key', req.full_url)
        self.assertEqual(json.loads(req.data)['input'], '테스트')
        self.assertEqual(send.call_args.kwargs['timeout'], 20)
        self.assertEqual(result['text'], '응답')
        self.assertIsNone(result['usage']['total_tokens'])

    def test_errors_safe_and_no_retries(self):
        for exc, code in [(TimeoutError('private'), 'network_or_timeout'),
                          (HTTPError('url', 429, 'private', None, None), 'http_429'),
                          (HTTPError('url', 503, 'private', None, None), 'http_503')]:
            with self.subTest(code=code), patch('app.llm_client.urlopen', side_effect=exc) as send:
                with self.assertRaises(LLMError) as caught:
                    generate_text('테스트')
                self.assertEqual(str(caught.exception), code)
                send.assert_called_once()

    def test_missing_key_does_not_send(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': ''}), patch('app.llm_client.urlopen') as send:
            with self.assertRaisesRegex(LLMError, 'missing_key'):
                generate_text('테스트')
        send.assert_not_called()

    def test_invalid_or_incomplete_response(self):
        for raw in (b'bad-json', b'[]', b'{"status":"in_progress"}', b'{"status":"completed","steps":[]}'):
            with self.subTest(raw=raw), patch('app.llm_client.urlopen', return_value=io.BytesIO(raw)):
                with self.assertRaises(LLMError):
                    generate_text('테스트')


if __name__ == '__main__':
    unittest.main()
