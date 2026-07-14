from __future__ import annotations

import json
from dataclasses import dataclass

from .config import PipelineConfig
from .http_client import JsonHttpClient
from .openai_analysis import extract_response_text


SYMBOL_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "companies": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "ticker": {"type": "string"},
                },
                "required": ["name", "ticker"],
            },
        },
        "search_terms": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["companies", "search_terms"],
}

_SYSTEM_PROMPT = (
    "You extract publicly traded companies and news search keywords from an "
    "investor's question, which may be written in German. "
    "For each company return its primary stock ticker as used by major market-data "
    "providers: prefer the US ticker or a US-listed ADR; otherwise use the local "
    "exchange ticker (e.g. RHM.DE for Rheinmetall). Omit private or unknown companies. "
    "Also return 2-5 concise English news search keywords that capture the theme "
    "(sector, catalyst, product), independent of any specific ticker. "
    "Return valid JSON only."
)


@dataclass(slots=True)
class SymbolExtraction:
    symbols: list[str]
    search_query: str | None


class LLMSymbolExtractor:
    """Erkennt Ticker und Suchbegriffe frei aus der Analysefrage per OpenAI."""

    def __init__(self, client: JsonHttpClient, api_key: str, config: PipelineConfig) -> None:
        self.client = client
        self.api_key = api_key
        self.config = config

    def extract(self, query: str) -> SymbolExtraction:
        response = self.client.post_json(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self.api_key}"},
            payload=self._build_payload(query),
        )
        parsed = json.loads(extract_response_text(response))
        return SymbolExtraction(
            symbols=_clean_symbols(parsed.get("companies", [])),
            search_query=_clean_search_query(parsed.get("search_terms", [])),
        )

    def _build_payload(self, query: str) -> dict[str, object]:
        return {
            "model": self.config.openai_model,
            "reasoning": {"effort": self.config.symbol_extraction_reasoning_effort},
            "max_output_tokens": self.config.symbol_extraction_max_output_tokens,
            "input": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Investor question: {query}"},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "symbol_extraction",
                    "strict": True,
                    "schema": SYMBOL_EXTRACTION_SCHEMA,
                }
            },
        }


def _clean_symbols(companies: list) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for company in companies:
        if not isinstance(company, dict):
            continue
        ticker = str(company.get("ticker") or "").strip().upper()
        if ticker and ticker not in seen:
            symbols.append(ticker)
            seen.add(ticker)
    return symbols


def _clean_search_query(search_terms: list) -> str | None:
    terms = [str(term).strip() for term in search_terms if str(term).strip()]
    unique = list(dict.fromkeys(terms))
    query = " ".join(unique[:5]).strip()
    return query or None
