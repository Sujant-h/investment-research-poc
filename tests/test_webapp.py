from __future__ import annotations

import json
import shutil
import threading
import unittest
import uuid
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from investment_research_poc.models import Evidence, ResearchBrief, SentimentAssessment
from investment_research_poc.reporting import export_brief
from investment_research_poc.webapp import build_app_context, create_handler


class WebAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self.test_root = Path(__file__).resolve().parent / "_artifacts" / str(uuid.uuid4())
        self.context = build_app_context(self.test_root)
        self.context.assistant.run = self._fake_run  # type: ignore[method-assign]
        self.last_run_kwargs: dict[str, object] | None = None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(self.context))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        shutil.rmtree(self.test_root, ignore_errors=True)

    def test_defaults_endpoint_returns_project_defaults(self) -> None:
        status, payload, headers = self._request("GET", "/api/defaults")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "application/json; charset=utf-8")
        self.assertEqual(payload["default_output_path"], str((self.test_root / "output" / "web_run").resolve()))
        self.assertIn(".txt", payload["supported_extensions"])
        self.assertEqual(payload["default_symbol_mode"], "query")
        self.assertEqual(payload["providers"], ["marketaux", "alpha_vantage"])
        self.assertEqual(payload["symbol_modes"][0]["value"], "query")
        self.assertEqual(payload["symbol_options"][0]["value"], "AAPL")
        self.assertEqual(payload["suggested_queries"][0]["symbols"], ["INTC", "NVDA", "QCOM"])

    def test_build_app_context_tolerates_trailing_quote_in_base_dir(self) -> None:
        malformed_base_dir = Path(f'{self.test_root}"')
        context = build_app_context(malformed_base_dir)
        self.assertEqual(context.base_dir, self.test_root.resolve())

    def test_research_endpoint_generates_brief_and_files(self) -> None:
        status, payload, _ = self._request(
            "POST",
            "/api/research",
            {
                "query": "Assess Example Corp as an acquisition target",
                "provider_name": "marketaux",
                "symbol_mode": "manual",
                "symbols": "SAP,MSFT",
            },
        )

        output_dir = self.test_root / "output" / "web_run"
        self.assertEqual(status, 200)
        self.assertEqual(payload["brief"]["query"], "Assess Example Corp as an acquisition target")
        self.assertEqual(payload["input_source"], "News-Provider-API")
        self.assertEqual(payload["provider_name"], "marketaux")
        self.assertEqual(payload["requested_symbol_mode"], "manual")
        self.assertEqual(payload["resolved_symbols"], ["SAP", "MSFT"])
        self.assertEqual(payload["symbol_source"], "manual")
        self.assertEqual(payload["output_path"], str(output_dir.resolve()))
        self.assertTrue((output_dir / "research_brief.md").exists())
        self.assertTrue((output_dir / "research_brief.json").exists())

    def test_research_endpoint_infers_symbols_from_query(self) -> None:
        status, payload, _ = self._request(
            "POST",
            "/api/research",
            {
                "query": "Assess whether SAP is an attractive strategic acquisition candidate in enterprise AI software",
                "provider_name": "marketaux",
                "symbol_mode": "query",
                "symbols": "MSFT",
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["resolved_symbols"], ["SAP"])
        self.assertEqual(payload["symbol_source"], "inferred")
        self.assertEqual(self.last_run_kwargs["symbols"], ["SAP"])

    def test_research_endpoint_manual_mode_requires_symbols(self) -> None:
        status, payload, _ = self._request(
            "POST",
            "/api/research",
            {
                "query": "Assess BMW as an investment candidate",
                "provider_name": "marketaux",
                "symbol_mode": "manual",
                "symbols": "",
            },
        )

        self.assertEqual(status, 400)
        self.assertEqual(
            payload["error"],
            "Bitte waehle mindestens ein Symbol aus oder wechsle zur automatischen Ableitung aus der Analysefrage.",
        )

    def test_root_serves_frontend(self) -> None:
        status, payload, headers = self._request("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "text/html")
        self.assertIn("Investment Research Workspace", payload)

    def _fake_run(
        self,
        *,
        query: str,
        output_dir: Path | None = None,
        input_path: Path | None = None,
        symbols: list[str] | None = None,
        include_live_news: bool = False,
        provider_name: str | None = None,
        use_openai: bool = True,
        base_dir: Path | None = None,
    ) -> ResearchBrief:
        self.last_run_kwargs = {
            "query": query,
            "output_dir": output_dir,
            "input_path": input_path,
            "symbols": symbols,
            "include_live_news": include_live_news,
            "provider_name": provider_name,
            "use_openai": use_openai,
            "base_dir": base_dir,
        }
        brief = ResearchBrief(
            query=query,
            executive_summary="Example Corp appears attractive based on recent momentum and news flow.",
            sentiment=SentimentAssessment(
                score=0.66,
                label="positive",
                matched_positive_terms=["growth", "strong"],
                matched_negative_terms=["risk"],
            ),
            recommendation="Proceed with targeted follow-up diligence.",
            opportunities=["Recurring revenue profile.", "Positive sector demand."],
            risks=["Integration risk remains relevant."],
            evidence=[
                Evidence(
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    title="Live News",
                    text="Example Corp is benefiting from strong market demand.",
                    score=1.25,
                    source_type="api",
                    provider=provider_name,
                )
            ],
            generated_at="2026-04-23T00:00:00+00:00",
            analysis_mode="openai_structured_output",
            model_name="gpt-5.4",
        )
        if output_dir is not None:
            export_brief(brief, output_dir)
        return brief

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> tuple[int, object, dict[str, str]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        body = None
        headers: dict[str, str] = {}
        if payload is not None:
            body = json.dumps(payload)
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw_body = response.read().decode("utf-8")
        content_type = response.getheader("Content-Type", "")
        parsed_body: object = json.loads(raw_body) if content_type.startswith("application/json") else raw_body
        result = (response.status, parsed_body, dict(response.getheaders()))
        connection.close()
        return result


if __name__ == "__main__":
    unittest.main()
