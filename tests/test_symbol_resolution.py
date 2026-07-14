from __future__ import annotations

import unittest

from investment_research_poc.symbol_extraction import SymbolExtraction
from investment_research_poc.webapp import build_keyword_query, resolve_symbols


class FakeExtractor:
    def __init__(self, extraction: SymbolExtraction | None = None, *, raise_error: bool = False) -> None:
        self.extraction = extraction
        self.raise_error = raise_error
        self.calls = 0

    def extract(self, query: str) -> SymbolExtraction:
        self.calls += 1
        if self.raise_error:
            raise RuntimeError("boom")
        assert self.extraction is not None
        return self.extraction


class BuildKeywordQueryTest(unittest.TestCase):
    def test_strips_filler_numbers_and_currency(self) -> None:
        query = "Bewerte 2 Millionen US-Dollar in Rheinmetall für die nächsten 5 Jahre"
        keywords = build_keyword_query(query)
        self.assertIn("Rheinmetall", keywords)
        self.assertNotIn("2", keywords)
        self.assertNotIn("Millionen", keywords)
        self.assertNotIn("nächsten", keywords)

    def test_falls_back_when_only_stopwords(self) -> None:
        # Selbst wenn alles gefiltert würde, darf kein leerer String entstehen.
        self.assertTrue(build_keyword_query("und oder in für die"))


class ResolveSymbolsTest(unittest.TestCase):
    def test_manual_mode_returns_manual_symbols(self) -> None:
        symbols, source, keywords = resolve_symbols(
            query="egal", raw_symbols="sap, msft", symbol_mode="manual"
        )
        self.assertEqual(symbols, ["SAP", "MSFT"])
        self.assertEqual(source, "manual")
        self.assertIsNone(keywords)

    def test_manual_mode_without_symbols_raises(self) -> None:
        with self.assertRaises(ValueError):
            resolve_symbols(query="egal", raw_symbols=None, symbol_mode="manual")

    def test_llm_extraction_is_preferred_and_adds_keywords(self) -> None:
        extractor = FakeExtractor(
            SymbolExtraction(symbols=["RHM.DE"], search_query="defense spending")
        )
        symbols, source, keywords = resolve_symbols(
            query="Ist Rheinmetall ein gutes Investment?",
            raw_symbols=None,
            symbol_mode="query",
            extractor=extractor,
        )
        self.assertEqual(symbols, ["RHM.DE"])
        self.assertEqual(source, "llm")
        self.assertEqual(keywords, "defense spending")
        self.assertEqual(extractor.calls, 1)

    def test_falls_back_to_rules_when_extractor_fails(self) -> None:
        extractor = FakeExtractor(raise_error=True)
        symbols, source, keywords = resolve_symbols(
            query="Assess whether SAP is an attractive acquisition candidate",
            raw_symbols=None,
            symbol_mode="query",
            extractor=extractor,
        )
        self.assertEqual(symbols, ["SAP"])
        self.assertEqual(source, "inferred")
        self.assertTrue(keywords)

    def test_keyword_only_when_no_ticker_found(self) -> None:
        symbols, source, keywords = resolve_symbols(
            query="Wie entwickelt sich der Markt für Wasserstofftechnologie?",
            raw_symbols=None,
            symbol_mode="query",
            extractor=None,
        )
        self.assertEqual(symbols, [])
        self.assertEqual(source, "keyword")
        self.assertTrue(keywords)


if __name__ == "__main__":
    unittest.main()
