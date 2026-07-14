from __future__ import annotations

import math
import re
from collections import Counter

from .config import PipelineConfig
from .models import Chunk, Document, Evidence


TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9\-]+")


def tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def chunk_documents(documents: list[Document], config: PipelineConfig) -> list[Chunk]:
    chunks: list[Chunk] = []
    for document in documents:
        words = document.content.split()
        if not words:
            continue
        start = 0
        position = 0
        while start < len(words):
            end = min(start + config.chunk_size_words, len(words))
            chunk_words = words[start:end]
            chunks.append(
                Chunk(
                    chunk_id=f"{document.document_id}-{position}",
                    document_id=document.document_id,
                    title=document.title,
                    text=" ".join(chunk_words),
                    position=position,
                )
            )
            if end == len(words):
                break
            start = max(end - config.chunk_overlap_words, start + 1)
            position += 1
    return chunks


class KeywordRetriever:
    def __init__(self, chunks: list[Chunk], documents: list[Document] | None = None) -> None:
        self._chunks = chunks
        self._documents = {document.document_id: document for document in documents or []}
        self._term_frequencies: dict[str, Counter[str]] = {}
        self._document_frequency: Counter[str] = Counter()
        self._average_chunk_length = 0.0
        self._build_index()

    def _build_index(self) -> None:
        total_length = 0
        for chunk in self._chunks:
            tokens = tokenize(chunk.text)
            total_length += len(tokens)
            frequencies = Counter(tokens)
            self._term_frequencies[chunk.chunk_id] = frequencies
            for token in frequencies:
                self._document_frequency[token] += 1
        self._average_chunk_length = total_length / len(self._chunks) if self._chunks else 0.0

    def search(self, query: str, top_k: int) -> list[Evidence]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        results: list[Evidence] = []
        for chunk in self._chunks:
            score = self._score_chunk(chunk, query_tokens)
            if score <= 0:
                continue
            results.append(
                Evidence(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    title=chunk.title,
                    text=chunk.text,
                    score=score,
                    source_type=self._documents.get(chunk.document_id).source_type if chunk.document_id in self._documents else None,
                    source_url=self._documents.get(chunk.document_id).source_url if chunk.document_id in self._documents else None,
                    published_at=self._documents.get(chunk.document_id).published_at if chunk.document_id in self._documents else None,
                    provider=self._documents.get(chunk.document_id).provider if chunk.document_id in self._documents else None,
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]

    def _score_chunk(self, chunk: Chunk, query_tokens: list[str]) -> float:
        frequencies = self._term_frequencies.get(chunk.chunk_id, Counter())
        if not frequencies:
            return 0.0

        k1 = 1.4
        b = 0.75
        chunk_length = sum(frequencies.values())
        score = 0.0
        total_chunks = max(len(self._chunks), 1)

        for token in query_tokens:
            tf = frequencies.get(token, 0)
            if tf == 0:
                continue
            doc_freq = self._document_frequency.get(token, 0)
            idf = math.log(1 + (total_chunks - doc_freq + 0.5) / (doc_freq + 0.5))
            denominator = tf + k1 * (
                1 - b + b * (chunk_length / self._average_chunk_length if self._average_chunk_length else 1)
            )
            score += idf * ((tf * (k1 + 1)) / denominator)

        title_tokens = set(tokenize(chunk.title))
        overlap = len(title_tokens.intersection(query_tokens))
        return score + overlap * 0.25
