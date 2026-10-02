import asyncio
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import pymysql

from app.main import app
from app.faq_service import rank_faqs


def request_api(path, payload):
    # HTTP 클라이언트 라이브러리 없이 ASGI 요청을 보내 입력 검증까지 검사한다.
    body = json.dumps(payload).encode()
    messages = []

    async def run():
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            messages.append(message)

        await app({
            "type": "http", "asgi": {"version": "3.0"},
            "http_version": "1.1", "method": "POST", "scheme": "http",
            "path": path, "raw_path": path.encode(), "query_string": b"",
            "root_path": "", "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 1), "server": ("test", 80),
        }, receive, send)

    asyncio.run(run())
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    response = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, json.loads(response)


class FaqTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"LLM_ENABLED": "false"})
        env.start()
        self.addCleanup(env.stop)
        # 검색 테스트에서 실제 DB에 요청 로그가 쌓이지 않도록 대체한다.
        writer = patch("app.log_service.insert_request_log")
        writer.start()
        self.addCleanup(writer.stop)

    @classmethod
    def setUpClass(cls):
        cls.faqs = json.loads(
            (Path(__file__).resolve().parent.parent / "data" / "faqs.json").read_text(encoding="utf-8")
        )

    def test_specific_shipping_cost_beats_general_shipping(self):
        result = rank_faqs("배송비는 얼마예요?", self.faqs)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["matches"][0]["faq_id"], 2)

    def test_original_answer_and_source_are_preserved(self):
        result = rank_faqs("냉동 떡 해동 방법 알려줘", self.faqs)
        self.assertEqual(result["matches"][0]["source"], "faqs:4")
        self.assertEqual(result["matches"][0]["answer"], self.faqs[3]["answer"])

    def test_unknown_returns_no_evidence(self):
        result = rank_faqs("비트코인 가격 알려줘", self.faqs)
        self.assertEqual(result["status"], "no_match")
        self.assertEqual(result["matches"], [])

    def test_generic_shipping_requests_clarification(self):
        result = rank_faqs("배송", self.faqs)
        self.assertEqual(result["status"], "needs_clarification")

    def test_spacing_is_normalized(self):
        result = rank_faqs("배송 지 변경 하고 싶어요", self.faqs)
        self.assertEqual(result["matches"][0]["faq_id"], 6)

    def test_limit(self):
        self.assertLessEqual(len(rank_faqs("배송 취소 환불 보관 해동", self.faqs)["matches"]), 3)

    def test_no_faqs(self):
        self.assertEqual(rank_faqs("배송", [])["status"], "no_match")

    def test_api_valid_query(self):
        with patch("app.faq_service.get_common_faqs", return_value=self.faqs):
            status, data = request_api("/api/faq/search", {"query": "  배송비 얼마예요?  "})
        self.assertEqual(status, 200)
        self.assertEqual(data["query"], "배송비 얼마예요?")
        self.assertEqual(data["mode"], "retrieval_only")
        self.assertEqual(data["matches"][0]["faq_id"], 2)

    def test_api_bad_inputs_do_not_query_db(self):
        with patch("app.main.search_faqs") as search:
            for payload in ({}, {"query": "   "}, {"query": "x" * 501}, {"query": 123}):
                with self.subTest(payload=str(payload)[:40]):
                    status, _ = request_api("/api/faq/search", payload)
                    self.assertEqual(status, 422)
            search.assert_not_called()

    def test_api_db_failure_is_logged_without_leaking_detail(self):
        with patch("app.main.search_faqs", side_effect=pymysql.OperationalError("private detail")):
            with patch("app.main.logger.exception") as log:
                status, data = request_api("/api/faq/search", {"query": "배송"})
        self.assertEqual(status, 503)
        self.assertNotIn("private detail", json.dumps(data))
        log.assert_called_once()

    def test_recommendation_still_uses_extracted_conditions(self):
        with patch("app.main.search_products", return_value=[{"product_id": 1}]) as search:
            status, data = request_api("/api/recommendations", {"query": "너무 달지 않은 개별포장 선물"})
        self.assertEqual(status, 200)
        self.assertEqual(data["count"], 1)
        search.assert_called_once_with(gift_only=True, individual_only=True, max_sweetness=2)


if __name__ == "__main__":
    unittest.main()
