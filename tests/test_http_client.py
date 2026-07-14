from __future__ import annotations

import unittest

from investment_research_poc.http_client import build_default_headers, normalize_query_value


class HttpClientHelpersTest(unittest.TestCase):
    def test_normalize_query_value_lowercases_booleans(self) -> None:
        self.assertEqual(normalize_query_value(True), "true")
        self.assertEqual(normalize_query_value(False), "false")
        self.assertEqual(normalize_query_value("en"), "en")

    def test_build_default_headers_adds_json_accept_and_user_agent(self) -> None:
        headers = build_default_headers({"Authorization": "Bearer test"})

        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(headers["User-Agent"], "investment-research-poc/0.1")
        self.assertEqual(headers["Authorization"], "Bearer test")


if __name__ == "__main__":
    unittest.main()
