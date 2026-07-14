from __future__ import annotations

import json
from datetime import UTC, datetime

from .config import PipelineConfig
from .http_client import JsonHttpClient
from .models import Evidence, ResearchBrief, SentimentAssessment


RESEARCH_BRIEF_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "executive_summary": {"type": "string"},
        "recommendation": {"type": "string"},
        "sentiment": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "label": {"type": "string", "enum": ["positive", "neutral", "negative"]},
                "score": {"type": "number"},
                "matched_positive_terms": {"type": "array", "items": {"type": "string"}},
                "matched_negative_terms": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "label",
                "score",
                "matched_positive_terms",
                "matched_negative_terms",
            ],
        },
        "opportunities": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "executive_summary",
        "recommendation",
        "sentiment",
        "opportunities",
        "risks",
    ],
}


class OpenAIResearchAnalyzer:
    def __init__(self, client: JsonHttpClient, api_key: str, config: PipelineConfig) -> None:
        self.client = client
        self.api_key = api_key
        self.config = config

    def analyze(self, *, query: str, evidence: list[Evidence]) -> ResearchBrief:
        response = self.client.post_json(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self.api_key}"},
            payload=self._build_payload(query, evidence),
        )
        parsed = json.loads(extract_response_text(response))
        sentiment_payload = parsed["sentiment"]
        return ResearchBrief(
            query=query,
            executive_summary=parsed["executive_summary"],
            sentiment=SentimentAssessment(
                score=float(sentiment_payload["score"]),
                label=str(sentiment_payload["label"]),
                matched_positive_terms=[str(item) for item in sentiment_payload["matched_positive_terms"]],
                matched_negative_terms=[str(item) for item in sentiment_payload["matched_negative_terms"]],
            ),
            recommendation=parsed["recommendation"],
            opportunities=[str(item) for item in parsed["opportunities"]],
            risks=[str(item) for item in parsed["risks"]],
            evidence=evidence,
            generated_at=datetime.now(UTC).isoformat(),
            analysis_mode="openai_structured_output",
            model_name=self.config.openai_model,
        )

    def _build_payload(self, query: str, evidence: list[Evidence]) -> dict[str, object]:
        return {
            "model": self.config.openai_model,
            "reasoning": {"effort": self.config.openai_reasoning_effort},
            "max_output_tokens": self.config.openai_max_output_tokens,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "You are a senior investment banking research assistant. "
                        "Use only the provided evidence. Do not invent facts. "
                        "If evidence is mixed, say so explicitly. Return valid JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Research query: {query}\n\n"
                        "Create a concise investment-research brief from the evidence below. "
                        "Balance upside and downside risks, and keep the language suitable for analyst review.\n\n"
                        f"{format_evidence_for_prompt(evidence)}"
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "research_brief",
                    "strict": True,
                    "schema": RESEARCH_BRIEF_SCHEMA,
                }
            },
        }


def format_evidence_for_prompt(evidence: list[Evidence]) -> str:
    sections: list[str] = []
    for index, item in enumerate(evidence, start=1):
        sections.append(
            "\n".join(
                [
                    f"Evidence {index}",
                    f"Title: {item.title}",
                    f"Provider: {item.provider or 'unknown'}",
                    f"Published At: {item.published_at or 'unknown'}",
                    f"Source URL: {item.source_url or 'n/a'}",
                    f"Retriever Score: {item.score:.2f}",
                    f"Text: {item.text}",
                ]
            )
        )
    return "\n\n".join(sections)


def extract_response_text(response: dict[str, object]) -> str:
    output = response.get("output", [])
    if not isinstance(output, list):
        raise RuntimeError("Unexpected OpenAI response: missing output array.")

    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "output_text":
                text = block.get("text")
                if isinstance(text, str):
                    return text

    raise RuntimeError(f"Unexpected OpenAI response format: {json.dumps(response, ensure_ascii=True)[:2000]}")
