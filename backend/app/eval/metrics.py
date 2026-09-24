"""Retrieval and generation metric helpers."""

from __future__ import annotations

import re
from typing import Any

from app.rag.tokenize import tokenize


def first_relevant_rank(retrieved: list[dict[str, Any]], expected_doc_ids: list[str]) -> int | None:
    expected = set(expected_doc_ids)
    for i, chunk in enumerate(retrieved, start=1):
        if chunk["doc_id"] in expected:
            return i
    return None


def document_hit_rate_at_k(ranks: list[int | None], k: int) -> float:
    if not ranks:
        return 0.0
    hits = sum(1 for rank in ranks if rank is not None and rank <= k)
    return round(hits / len(ranks), 3)


def mean_reciprocal_rank(ranks: list[int | None]) -> float:
    if not ranks:
        return 0.0
    total = sum((1.0 / rank) if rank else 0.0 for rank in ranks)
    return round(total / len(ranks), 3)


def lexical_overlap(answer: str, contexts: list[dict[str, Any]]) -> float:
    answer_tokens = set(tokenize(answer))
    if not answer_tokens:
        return 0.0
    context_tokens: set[str] = set()
    for chunk in contexts:
        context_tokens.update(tokenize(chunk["text"]))
    return round(len(answer_tokens & context_tokens) / len(answer_tokens), 3)


def question_answer_overlap(question: str, answer: str) -> float:
    q = set(tokenize(question))
    a = set(tokenize(answer))
    if not q or not a:
        return 0.0
    return round(len(q & a) / len(q), 3)


def citation_metrics(answer: str, citations: list[dict[str, Any]], expected_sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Score unique inline [n] references, never the entire retrieved source list.

    Gold sources are acceptable alternatives, using 1-based PDF page numbers.
    Matching a location does not establish that it supports the associated claim.
    """
    references = set()
    for group in re.findall(r"\[([0-9]+(?:\s*,\s*[0-9]+)*)\]", answer):
        references.update(int(value.strip()) for value in group.split(","))
    by_index = {int(c["index"]): c for c in citations}
    valid = references & by_index.keys()
    expected = {(s["doc_id"], int(s["page"])) for s in expected_sources}
    matches = sum((by_index[i]["doc_id"], int(by_index[i]["page"])) in expected for i in valid)
    return {
        "citation_count": len(references),
        "invalid_citation_ids": sorted(references - by_index.keys()),
        "citation_id_precision": round(len(valid) / len(references), 3) if references else None,
        "citation_source_precision": (round(matches / len(references), 3) if references else 0.0) if expected else None,
        "citation_source_hit": float(matches > 0) if expected else None,
    }


def abstention_signal(answer: str) -> bool:
    """Lexical screening only; refusal followed by invented advice still needs review."""
    patterns = (
        r"\b(?:cannot|can't|unable to) (?:answer|provide|determine|find|recommend)\b",
        r"\b(?:not|no|insufficient) (?:covered|provided|available|included|information|evidence|found)\b",
        r"\b(?:sources|documents|excerpts|corpus|guidelines) (?:do not|don't|does not|doesn't) (?:contain|cover|provide|include|address)\b",
    )
    return any(re.search(pattern, answer, re.IGNORECASE) for pattern in patterns)


def summarize(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [row[key] for row in rows if row.get(key) is not None]
    return {"mean": round(sum(values) / len(values), 3) if values else None, "n_scored": len(values), "n_total": len(rows)}
