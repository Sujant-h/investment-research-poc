from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .http_client import JsonHttpClient
from .models import Document


class MarketauxNewsProvider:
    def __init__(self, client: JsonHttpClient, api_token: str) -> None:
        self.client = client
        self.api_token = api_token

    def fetch_documents(
        self,
        *,
        symbols: list[str],
        language: str,
        limit: int,
        lookback_days: int,
        keywords: str | None = None,
    ) -> list[Document]:
        published_after = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y-%m-%dT%H:%M")
        params: dict[str, object] = {
            "api_token": self.api_token,
            "language": language,
            "limit": limit,
            "filter_entities": "true",
            "published_after": published_after,
        }
        if symbols:
            params["symbols"] = ",".join(symbols)
        elif keywords:
            params["search"] = keywords
        payload = self.client.get_json("https://api.marketaux.com/v1/news/all", params=params)
        return normalize_marketaux_documents(payload)


class AlphaVantageNewsProvider:
    def __init__(self, client: JsonHttpClient, api_key: str) -> None:
        self.client = client
        self.api_key = api_key

    def fetch_documents(
        self,
        *,
        symbols: list[str],
        language: str,
        limit: int,
        lookback_days: int,
    ) -> list[Document]:
        del language
        published_after = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y%m%dT%H%M")
        payload = self.client.get_json(
            "https://www.alphavantage.co/query",
            params={
                "function": "NEWS_SENTIMENT",
                "tickers": ",".join(symbols),
                "time_from": published_after,
                "limit": min(limit, 1000),
                "apikey": self.api_key,
            },
        )
        return normalize_alpha_vantage_documents(payload)


def normalize_marketaux_documents(payload: dict[str, Any]) -> list[Document]:
    documents: list[Document] = []
    for item in payload.get("data", []):
        title = str(item.get("title") or "Untitled marketaux article").strip()
        description = str(item.get("description") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        highlights = extract_marketaux_highlights(item)
        content = "\n".join(part for part in [description, snippet, highlights] if part).strip()
        if not content:
            content = title
        documents.append(
            Document(
                document_id=str(item.get("uuid") or stable_id(title)),
                title=title,
                source_path=Path(f"marketaux/{stable_id(title)}.json"),
                source_type="market_news",
                content=content,
                source_url=str(item.get("url") or ""),
                published_at=str(item.get("published_at") or ""),
                provider="marketaux",
                metadata={
                    "source": item.get("source"),
                    "entities": item.get("entities", []),
                },
            )
        )
    return documents


def normalize_alpha_vantage_documents(payload: dict[str, Any]) -> list[Document]:
    documents: list[Document] = []
    for item in payload.get("feed", []):
        title = str(item.get("title") or "Untitled alpha vantage article").strip()
        summary = str(item.get("summary") or "").strip()
        topics = ", ".join(topic.get("topic", "") for topic in item.get("topics", []) if topic.get("topic"))
        sentiment = item.get("overall_sentiment_label") or item.get("overall_sentiment_score")
        content_parts = [summary]
        if topics:
            content_parts.append(f"Topics: {topics}")
        if sentiment:
            content_parts.append(f"Overall sentiment: {sentiment}")
        documents.append(
            Document(
                document_id=stable_id(f"alpha-vantage-{title}"),
                title=title,
                source_path=Path(f"alpha_vantage/{stable_id(title)}.json"),
                source_type="market_news",
                content="\n".join(part for part in content_parts if part),
                source_url=str(item.get("url") or ""),
                published_at=str(item.get("time_published") or ""),
                provider="alpha_vantage",
                metadata={
                    "source": item.get("source"),
                    "ticker_sentiment": item.get("ticker_sentiment", []),
                },
            )
        )
    return documents


def extract_marketaux_highlights(item: dict[str, Any]) -> str:
    snippets: list[str] = []
    for entity in item.get("entities", []):
        for highlight in entity.get("highlights", []):
            text = str(highlight.get("highlight") or "").strip()
            if text:
                snippets.append(text)
    unique = list(dict.fromkeys(snippets))
    return "\n".join(unique[:5])


def stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
