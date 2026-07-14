from __future__ import annotations

import re
from collections import Counter

from .models import Evidence, SentimentAssessment
from .retrieval import tokenize


POSITIVE_TERMS = {
    "growth",
    "improved",
    "positive",
    "strong",
    "expanded",
    "confidence",
    "robust",
    "benefiting",
    "attractive",
    "resilient",
    "opportunity",
    "cross-selling",
}

NEGATIVE_TERMS = {
    "risk",
    "pressure",
    "high",
    "warning",
    "costs",
    "integration",
    "debt",
    "penalize",
    "concentration",
    "underestimated",
    "weak",
    "leverage",
}

OPPORTUNITY_HINTS = {
    "growth",
    "expanded",
    "partnership",
    "cross-selling",
    "pipeline",
    "attractive",
    "recurring",
    "robust",
    "strong",
    "automation",
}

RISK_HINTS = {
    "risk",
    "debt",
    "costs",
    "integration",
    "pressure",
    "warning",
    "customer concentration",
    "leverage",
    "execution",
}

SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


def assess_sentiment(text: str) -> SentimentAssessment:
    tokens = tokenize(text)
    counts = Counter(tokens)
    positive_hits = sorted(term for term in POSITIVE_TERMS if counts.get(term, 0) > 0)
    negative_hits = sorted(term for term in NEGATIVE_TERMS if counts.get(term, 0) > 0)
    positive_score = sum(counts[term] for term in positive_hits)
    negative_score = sum(counts[term] for term in negative_hits)
    denominator = max(positive_score + negative_score, 1)
    score = (positive_score - negative_score) / denominator

    if score > 0.2:
        label = "positive"
    elif score < -0.2:
        label = "negative"
    else:
        label = "neutral"

    return SentimentAssessment(
        score=round(score, 3),
        label=label,
        matched_positive_terms=positive_hits,
        matched_negative_terms=negative_hits,
    )


def build_summary(evidence: list[Evidence], query: str, max_sentences: int) -> str:
    query_tokens = set(tokenize(query))
    seen_sentences: set[str] = set()
    ranked_sentences: list[tuple[float, str]] = []

    for item in evidence:
        for sentence in split_sentences(item.text):
            normalized = sentence.strip()
            if len(normalized) < 40 or normalized in seen_sentences:
                continue
            overlap = len(query_tokens.intersection(tokenize(normalized)))
            score = item.score + overlap * 0.15
            ranked_sentences.append((score, normalized))
            seen_sentences.add(normalized)

    ranked_sentences.sort(key=lambda entry: entry[0], reverse=True)
    selected = [sentence for _, sentence in ranked_sentences[:max_sentences]]
    return " ".join(selected)


def extract_opportunities_and_risks(evidence: list[Evidence]) -> tuple[list[str], list[str]]:
    opportunities = extract_signals(evidence, OPPORTUNITY_HINTS)
    risks = extract_signals(evidence, RISK_HINTS)
    return opportunities[:4], risks[:4]


def derive_recommendation(sentiment: SentimentAssessment, opportunities: list[str], risks: list[str]) -> str:
    if sentiment.label == "positive" and len(opportunities) >= len(risks):
        return (
            "The target appears attractive for further due diligence, provided that leverage and integration "
            "risks are validated in a deeper transaction workstream."
        )
    if sentiment.label == "negative":
        return (
            "The current evidence indicates elevated downside risk. A transaction should only proceed if "
            "material risk mitigants can be evidenced."
        )
    return (
        "The target warrants selective follow-up analysis. Additional validation should focus on the quality "
        "of growth and the operational risk profile."
    )


def split_sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in SENTENCE_SPLIT_PATTERN.split(text) if sentence.strip()]


def extract_signals(evidence: list[Evidence], hint_terms: set[str]) -> list[str]:
    candidates: list[tuple[float, str]] = []
    seen: set[str] = set()
    for item in evidence:
        for sentence in split_sentences(item.text):
            lower_sentence = sentence.lower()
            if any(term in lower_sentence for term in hint_terms):
                cleaned = sentence.strip()
                if cleaned not in seen:
                    candidates.append((item.score, cleaned))
                    seen.add(cleaned)
    candidates.sort(key=lambda entry: entry[0], reverse=True)
    return [sentence for _, sentence in candidates]
