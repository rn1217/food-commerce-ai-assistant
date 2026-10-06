import json
import os
import unittest
from unittest.mock import patch

from app.llm_client import LLMError
from app.llm_faq_service import add_faq_answer
from test_faq import request_api


def retrieval(status='matched'):
    matches = [] if status == 'no_match' else [dict(faq_id=2, category='배송', question='배송비는?',
                  answer='기본 배송비 3,000원, 50,000원 이상 무료.', source='faqs:2')]
    return dict(query='배송비', status=status, mode='retrieval_only', matches=matches,
                count=len(matches), message='FAQ 원문', notice='가상 정책')


def result(answerable=True, answer='배송비는 3,000원입니다.', source_ids=None):
    return dict(text=json.dumps(dict(answerable=answerable, answer=answer,
                                    source_ids=[2] if source_ids is None else source_ids)),
                model='test', usage={'total_tokens': 100})


class FaqGenerationTests(unittest.TestCase):
    def setUp(self):
        patch.dict(os.environ, {'LLM_ENABLED': 'true', 'LLM_FAQ_ENABLED': 'true'}).start()
        self.generate = patch('app.llm_faq_service.generate_text', return_value=result()).start()
        self.writer = patch('app.log_service.insert_request_log').start()
        self.addCleanup(patch.stopall)

    def test_success_preserves_original_and_logs_once(self):
        original = retrieval()
        with patch('app.main.search_faqs', return_value=original):
            status, data = request_api('/api/faq/search', {'query': '배송비'})
        self.assertEqual((status, data['mode'], data['sources']), (200, 'generated', ['faqs:2']))
        self.assertEqual(data['matches'], original['matches'])
        self.assertNotIn('answer', original)
        self.writer.assert_called_once()
        record = self.writer.call_args.args[0]
        self.assertEqual((record['engine'], record['status']), ('gemini', 'success'))
        self.assertEqual(record['response'], data)

    def test_no_match_and_ambiguous_do_not_call(self):
        for status in ('no_match', 'needs_clarification'):
            data = add_faq_answer('질문', retrieval(status), 'id')
            self.assertIsNone(data['answer'])
            self.assertEqual(data['llm']['status'], 'skipped')
        self.generate.assert_not_called()

    def test_disabled_does_not_call(self):
        for name in ('LLM_ENABLED', 'LLM_FAQ_ENABLED'):
            with patch.dict(os.environ, {name: 'false'}):
                data = add_faq_answer('질문', retrieval(), 'id')
            self.assertEqual(data['llm']['status'], 'disabled')
        self.generate.assert_not_called()

    def test_abstention_does_not_display_generated_text(self):
        self.generate.return_value = result(False, '', [])
        with patch('app.main.search_faqs', return_value=retrieval()):
            status, data = request_api('/api/faq/search', {'query': '내 주문 내일 도착해?'})
        self.assertEqual((status, data['status']), (200, 'insufficient_evidence'))
        self.assertIsNone(data['answer'])
        self.assertEqual(data['sources'], [])
        self.assertEqual(self.writer.call_args.args[0]['status'], 'insufficient_evidence')

    def test_invalid_outputs_fall_back_without_leaking_text(self):
        cases = [result(source_ids=[999]), result(source_ids=[2,2]), result(source_ids=[]),
                 result(source_ids=['2']), result(source_ids=[True]), result(answer=' '),
                 result(answer='x'*1201), result(False, 'unsupported claim', []),
                 dict(text='bad json', model='test', usage={})]
        for reply in cases:
            with self.subTest(reply=reply), self.assertLogs('uvicorn.error', level='WARNING'):
                self.generate.return_value = reply
                data = add_faq_answer('질문', retrieval(), 'id')
            self.assertEqual(data['llm']['status'], 'fallback')
            self.assertEqual(data['mode'], 'retrieval_only')
            self.assertIsNone(data['answer'])
            self.assertEqual(data['sources'], [])

    def test_http_and_timeout_keep_original_and_log_fallback(self):
        for code in ('http_503', 'http_429', 'network_or_timeout', 'missing_key'):
            self.writer.reset_mock()
            self.generate.side_effect = LLMError(code)
            with patch('app.main.search_faqs', return_value=retrieval()), self.assertLogs('uvicorn.error', level='WARNING'):
                status, data = request_api('/api/faq/search', {'query': '배송비'})
            self.assertEqual((status, data['matches']), (200, retrieval()['matches']))
            self.assertEqual(self.writer.call_args.args[0]['error_code'], code)
            self.assertEqual(self.writer.call_args.args[0]['status'], 'fallback')

    def test_logging_failure_does_not_remove_answer(self):
        self.writer.side_effect = RuntimeError('db down')
        with patch('app.main.search_faqs', return_value=retrieval()), self.assertLogs('uvicorn.error', level='ERROR'):
            status, data = request_api('/api/faq/search', {'query': '배송비'})
        self.assertEqual((status, data['mode']), (200, 'generated'))
