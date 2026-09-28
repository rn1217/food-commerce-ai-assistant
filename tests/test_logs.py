from datetime import datetime
import json
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

import pymysql

from app.log_service import record_request
from app.log_repository import insert_request_log
from test_faq import request_api


class RequestLoggingTests(unittest.TestCase):
    def setUp(self):
        # 일반 테스트에서는 실제 DB에 쓰지 않는다.
        self.writer = patch("app.log_service.insert_request_log").start()
        self.addCleanup(patch.stopall)

    def record(self):
        self.writer.assert_called_once()
        return self.writer.call_args.args[0]

    def test_recommendation_success_saved_once_with_response_id(self):
        with patch("app.main.search_products", return_value=[{"product_id": 1}]):
            status, response = request_api("/api/recommendations", {"query": "선물"})
        record = self.record()
        self.assertEqual((status, record["status"], record["engine"]), (200, "success", "rule"))
        self.assertEqual(record["response"], response)
        self.assertEqual(record["request_id"], response["request_id"])
        UUID(record["request_id"])
        self.assertGreaterEqual(record["latency_ms"], 0)

    def test_recommendation_no_match(self):
        with patch("app.main.search_products", return_value=[]):
            status, response = request_api("/api/recommendations", {"query": "선물"})
        self.assertEqual((status, response["count"], self.record()["status"]), (200, 0, "no_match"))

    def test_unsupported_question_is_logged_without_product_search(self):
        with patch("app.main.search_products") as search:
            status, _ = request_api("/api/recommendations", {"query": "매운 음식"})
        search.assert_not_called()
        self.assertEqual((status, self.record()["status"]), (200, "unsupported"))

    def test_faq_status_mapping(self):
        for input_status, expected in (("matched", "success"), ("no_match", "no_match"), ("needs_clarification", "needs_clarification")):
            self.writer.reset_mock()
            with self.subTest(status=input_status):
                with patch("app.main.search_faqs", return_value={"status": input_status, "matches": []}):
                    status, response = request_api("/api/faq/search", {"query": "배송"})
                self.assertEqual((status, self.record()["status"]), (200, expected))
                self.assertIn("request_id", response)

    def test_validation_failure_not_saved(self):
        for path in ("/api/recommendations", "/api/faq/search"):
            status, _ = request_api(path, {"query": "   "})
            self.assertEqual(status, 422)
        self.writer.assert_not_called()

    def test_search_db_error_records_503_and_safe_error_code(self):
        with patch("app.main.search_products", side_effect=pymysql.OperationalError("private credentials")):
            with patch("app.main.logger.exception"):
                status, response = request_api("/api/recommendations", {"query": "선물"})
        record = self.record()
        self.assertEqual((status, record["status"], record["http_status"]), (503, "error", 503))
        self.assertEqual(record["error_code"], "OperationalError")
        self.assertNotIn("private credentials", json.dumps(record, default=str))
        self.assertEqual(record["response"], response)

    def test_unexpected_error_is_logged_and_returns_500(self):
        with patch("app.main.search_faqs", side_effect=ValueError("private details")):
            with patch("app.main.logger.exception"):
                status, _ = request_api("/api/faq/search", {"query": "배송"})
        self.assertEqual((status, self.record()["error_code"]), (500, "ValueError"))

    def test_log_db_failure_does_not_replace_success(self):
        self.writer.side_effect = pymysql.OperationalError("log database down")
        with patch("app.main.search_products", return_value=[{"product_id": 1}]):
            with patch("app.log_service.logger.error") as fallback:
                status, response = request_api("/api/recommendations", {"query": "선물"})
        self.assertEqual((status, response["count"]), (200, 1))
        fallback.assert_called_once()
        self.assertIn(response["request_id"], fallback.call_args.args[2])

    def test_both_search_and_logging_db_fail_preserves_503(self):
        self.writer.side_effect = pymysql.OperationalError("log database down")
        with patch("app.main.search_faqs", side_effect=pymysql.OperationalError("search database down")):
            with patch("app.main.logger.exception"), patch("app.log_service.logger.error") as fallback:
                status, _ = request_api("/api/faq/search", {"query": "배송"})
        self.assertEqual(status, 503)
        fallback.assert_called_once()
        saved_console = json.loads(fallback.call_args.args[2])
        self.assertEqual(saved_console["status"], "error")

    def test_log_writer_programming_error_also_does_not_replace_response(self):
        self.writer.side_effect = ValueError("bad log serialization")
        with patch("app.main.search_products", return_value=[]):
            with patch("app.log_service.logger.error"):
                status, _ = request_api("/api/recommendations", {"query": "선물"})
        self.assertEqual(status, 200)

    def test_timing_measured_before_insert(self):
        with patch("app.log_service.perf_counter", return_value=10.125):
            record_request(request_id="test", feature="faq", query="배송", response={}, started_at=10.0, status="success", http_status=200)
        self.assertEqual(self.record()["latency_ms"], 125)
        self.assertIsInstance(self.record()["created_at"], datetime)

    def test_each_request_has_distinct_id(self):
        with patch("app.main.search_products", return_value=[]):
            _, first = request_api("/api/recommendations", {"query": "선물"})
            _, second = request_api("/api/recommendations", {"query": "선물"})
        self.assertNotEqual(first["request_id"], second["request_id"])
        self.assertEqual(self.writer.call_count, 2)


class LogRepositoryTests(unittest.TestCase):
    def test_insert_uses_parameters_and_commits(self):
        record = {
            "request_id": "abc", "feature": "faq", "engine": "rule",
            "user_query": "' OR 1=1 --", "response": {"message": "한글"},
            "latency_ms": 10, "status": "success", "http_status": 200,
            "error_code": None, "created_at": datetime(2026, 9, 28),
        }
        connection = MagicMock()
        with patch("app.log_repository.get_connection") as connect:
            connect.return_value.__enter__.return_value = connection
            insert_request_log(record)
        cursor = connection.cursor.return_value.__enter__.return_value
        sql, params = cursor.execute.call_args.args
        self.assertNotIn(record["user_query"], sql)
        self.assertEqual(params[3], record["user_query"])
        self.assertEqual(json.loads(params[4]), record["response"])
        connection.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
