from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Document:
    document_id: str
    title: str
    source_path: Path
    source_type: str
    content: str
    source_url: str | None = None
    published_at: str | None = None
    provider: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Chunk:
    chunk_id: str
    document_id: str
    title: str
    text: str
    position: int


@dataclass(slots=True)
class Evidence:
    chunk_id: str
    document_id: str
    title: str
    text: str
    score: float
    source_type: str | None = None
    source_url: str | None = None
    published_at: str | None = None
    provider: str | None = None


@dataclass(slots=True)
class SentimentAssessment:
    score: float
    label: str
    matched_positive_terms: list[str]
    matched_negative_terms: list[str]


@dataclass(slots=True)
class ResearchBrief:
    query: str
    executive_summary: str
    sentiment: SentimentAssessment
    recommendation: str
    opportunities: list[str]
    risks: list[str]
    evidence: list[Evidence]
    generated_at: str
    analysis_mode: str
    model_name: str | None = None
