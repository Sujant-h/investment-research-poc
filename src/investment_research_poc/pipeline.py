from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .analysis import assess_sentiment, build_summary, derive_recommendation, extract_opportunities_and_risks
from .config import PipelineConfig
from .ingest import discover_files, load_documents
from .http_client import JsonHttpClient
from .models import ResearchBrief
from .news_providers import AlphaVantageNewsProvider, MarketauxNewsProvider
from .openai_analysis import OpenAIResearchAnalyzer
from .reporting import export_brief
from .retrieval import KeywordRetriever, chunk_documents
from .runtime import getenv_required, load_env_file


class ResearchAssistant:
    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()

    def run(
        self,
        *,
        query: str,
        output_dir: Path | None = None,
        input_path: Path | None = None,
        symbols: list[str] | None = None,
        keywords: str | None = None,
        include_live_news: bool = False,
        provider_name: str | None = None,
        use_openai: bool = True,
        base_dir: Path | None = None,
    ) -> ResearchBrief:
        load_env_file(self.config.resolve_env_file(base_dir))

        documents = []
        if input_path is not None:
            files = discover_files(input_path)
            documents.extend(load_documents(files))
        if include_live_news:
            documents.extend(
                self._fetch_live_news(symbols=symbols or [], provider_name=provider_name, keywords=keywords)
            )
        if not documents:
            raise ValueError("No supported documents found for analysis.")

        chunks = chunk_documents(documents, self.config)
        retriever = KeywordRetriever(chunks, documents)
        evidence = retriever.search(query=query, top_k=self.config.top_k_chunks)
        if not evidence:
            raise ValueError("No relevant evidence found for the provided query.")

        brief = self._analyze(query=query, evidence=evidence, use_openai=use_openai)
        if output_dir is not None:
            export_brief(brief, output_dir)
        return brief

    def _analyze(self, *, query: str, evidence: list, use_openai: bool) -> ResearchBrief:
        if use_openai:
            try:
                analyzer = OpenAIResearchAnalyzer(
                    client=JsonHttpClient(
                        timeout_seconds=self.config.request_timeout_seconds,
                        max_retries=self.config.max_retries,
                    ),
                    api_key=getenv_required("OPENAI_API_KEY"),
                    config=self.config,
                )
                return analyzer.analyze(query=query, evidence=evidence)
            except RuntimeError:
                pass

        evidence_text = " ".join(item.text for item in evidence)
        sentiment = assess_sentiment(evidence_text)
        opportunities, risks = extract_opportunities_and_risks(evidence)
        summary = build_summary(
            evidence=evidence,
            query=query,
            max_sentences=self.config.max_summary_sentences,
        )
        recommendation = derive_recommendation(sentiment, opportunities, risks)

        return ResearchBrief(
            query=query,
            executive_summary=summary,
            sentiment=sentiment,
            recommendation=recommendation,
            opportunities=opportunities,
            risks=risks,
            evidence=evidence,
            generated_at=datetime.now(UTC).isoformat(),
            analysis_mode="rule_based_fallback",
            model_name=None,
        )

    def _fetch_live_news(
        self, *, symbols: list[str], provider_name: str | None, keywords: str | None = None
    ) -> list:
        if not symbols and not keywords:
            raise ValueError("At least one symbol or a search keyword is required when live news is enabled.")

        provider = provider_name or self.config.news_provider
        client = JsonHttpClient(
            timeout_seconds=self.config.request_timeout_seconds,
            max_retries=self.config.max_retries,
        )

        if provider == "marketaux":
            news_provider = MarketauxNewsProvider(client, getenv_required("MARKETAUX_API_TOKEN"))
            return news_provider.fetch_documents(
                symbols=symbols,
                keywords=keywords,
                language=self.config.news_language,
                limit=self.config.live_news_limit,
                lookback_days=self.config.lookback_days,
            )
        if provider == "alpha_vantage":
            if not symbols:
                raise ValueError(
                    "Alpha Vantage unterstützt keine Keyword-Suche. "
                    "Bitte wähle einen Ticker oder wechsle zu Marketaux."
                )
            news_provider = AlphaVantageNewsProvider(client, getenv_required("ALPHA_VANTAGE_API_KEY"))
            return news_provider.fetch_documents(
                symbols=symbols,
                language=self.config.news_language,
                limit=self.config.live_news_limit,
                lookback_days=self.config.lookback_days,
            )
        raise ValueError(f"Unsupported news provider: {provider}")
