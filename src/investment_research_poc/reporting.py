from __future__ import annotations

import json
from pathlib import Path

from .models import ResearchBrief


def export_brief(brief: ResearchBrief, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "research_brief.md"
    json_path = output_dir / "research_brief.json"

    markdown_path.write_text(render_markdown(brief), encoding="utf-8")
    json_path.write_text(render_json(brief), encoding="utf-8")
    return markdown_path, json_path


def render_markdown(brief: ResearchBrief) -> str:
    evidence_lines = "\n".join(
        (
            f"- {item.title} (score={item.score:.2f}, provider={item.provider or 'unknown'}"
            f", published_at={item.published_at or 'n/a'}): {item.text}"
            f"{f' [source]({item.source_url})' if item.source_url else ''}"
        )
        for item in brief.evidence
    )
    opportunities = "\n".join(f"- {entry}" for entry in brief.opportunities) or "- No opportunity signals detected."
    risks = "\n".join(f"- {entry}" for entry in brief.risks) or "- No major risk signals detected."

    return (
        "# Research Brief\n\n"
        f"**Query:** {brief.query}\n\n"
        f"**Generated at:** {brief.generated_at}\n\n"
        f"**Analysis mode:** {brief.analysis_mode}\n\n"
        f"**Model:** {brief.model_name or 'rule-based fallback'}\n\n"
        "## Executive Summary\n\n"
        f"{brief.executive_summary}\n\n"
        "## Sentiment Assessment\n\n"
        f"- Label: {brief.sentiment.label}\n"
        f"- Score: {brief.sentiment.score}\n"
        f"- Positive terms: {', '.join(brief.sentiment.matched_positive_terms) or 'none'}\n"
        f"- Negative terms: {', '.join(brief.sentiment.matched_negative_terms) or 'none'}\n\n"
        "## Recommendation\n\n"
        f"{brief.recommendation}\n\n"
        "## Opportunity Signals\n\n"
        f"{opportunities}\n\n"
        "## Risk Signals\n\n"
        f"{risks}\n\n"
        "## Evidence\n\n"
        f"{evidence_lines}\n"
    )


def render_json(brief: ResearchBrief) -> str:
    payload = {
        "query": brief.query,
        "generated_at": brief.generated_at,
        "analysis_mode": brief.analysis_mode,
        "model_name": brief.model_name,
        "executive_summary": brief.executive_summary,
        "sentiment": {
            "label": brief.sentiment.label,
            "score": brief.sentiment.score,
            "matched_positive_terms": brief.sentiment.matched_positive_terms,
            "matched_negative_terms": brief.sentiment.matched_negative_terms,
        },
        "recommendation": brief.recommendation,
        "opportunities": brief.opportunities,
        "risks": brief.risks,
        "evidence": [
            {
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "title": item.title,
                "text": item.text,
                "score": item.score,
                "source_type": item.source_type,
                "source_url": item.source_url,
                "published_at": item.published_at,
                "provider": item.provider,
            }
            for item in brief.evidence
        ],
    }
    return json.dumps(payload, ensure_ascii=True, indent=2)
