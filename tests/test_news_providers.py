from __future__ import annotations

import unittest

from investment_research_poc.news_providers import normalize_alpha_vantage_documents, normalize_marketaux_documents


class NewsProviderNormalizationTest(unittest.TestCase):
    def test_normalize_marketaux_documents(self) -> None:
        payload = {
            "data": [
                {
                    "uuid": "abc123",
                    "title": "AlphaTech expands",
                    "description": "Expansion announced.",
                    "snippet": "Recurring revenue base improves.",
                    "url": "https://example.com/article",
                    "published_at": "2026-04-23T10:00:00Z",
                    "source": "Example News",
                    "entities": [
                        {
                            "highlights": [
                                {"highlight": "AlphaTech signs a new long-term contract."}
                            ]
                        }
                    ],
                }
            ]
        }

        documents = normalize_marketaux_documents(payload)
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].provider, "marketaux")
        self.assertIn("Recurring revenue", documents[0].content)

    def test_normalize_alpha_vantage_documents(self) -> None:
        payload = {
            "feed": [
                {
                    "title": "AlphaTech on watch",
                    "summary": "Analysts review AlphaTech.",
                    "url": "https://example.com/alpha",
                    "time_published": "20260423T0900",
                    "overall_sentiment_label": "Neutral",
                    "topics": [{"topic": "technology"}],
                }
            ]
        }

        documents = normalize_alpha_vantage_documents(payload)
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].provider, "alpha_vantage")
        self.assertIn("technology", documents[0].content.lower())


if __name__ == "__main__":
    unittest.main()
