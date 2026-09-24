"""Lightweight tokenizer shared by BM25 indexing and query time."""

from __future__ import annotations

import re


_TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)?", re.IGNORECASE)

_STOP = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "for",
    "on",
    "at",
    "by",
    "with",
    "from",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "this",
    "that",
    "these",
    "those",
}


def tokenize(text: str) -> list[str]:
    tokens = [tok.lower() for tok in _TOKEN_RE.findall(text or "")]
    return [tok for tok in tokens if tok not in _STOP and len(tok) > 1]
