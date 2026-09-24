"""Page-bounded, heading-aware chunks with exact PDF page provenance."""

from __future__ import annotations

import re
from typing import Any


HEADING_RE = re.compile(
    r"""^(
        (?:\d+(?:\.\d+){0,3}[\.\)]?\s+).{3,80}$
        |(?i:chapter|annex|protocol|recommendation|module)\b.{0,80}$
        |[A-Z0-9][A-Z0-9 ,/\-]{10,80}$
    )""",
    re.VERBOSE,
)


def _is_heading(line: str) -> bool:
    text = line.strip()
    if not text or len(text) > 120:
        return False
    if text.endswith(".") and len(text) > 60:
        return False
    if HEADING_RE.match(text):
        return True
    words = text.split()
    if 2 <= len(words) <= 12 and text[:1].isupper() and sum(ch.isalpha() for ch in text) > 8:
        alpha = [w for w in words if w[0].isalpha()]
        titled = sum(w[0].isupper() for w in alpha)
        if alpha and titled / len(alpha) >= 0.8:
            return True
    return False


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    if max_chars <= 0 or not 0 <= overlap < max_chars:
        raise ValueError("Require max_chars > 0 and 0 <= overlap < max_chars.")
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            # Prefer a line boundary in the latter half of this window.
            boundary = text.rfind("\n", start + max_chars // 2, end)
            if boundary >= 0 and boundary + 1 - start > overlap:
                end = boundary + 1
        part = text[start:end].strip()
        if part:
            chunks.append(part)
        if end == len(text):
            break
        start = end - overlap
    return chunks


def chunk_document(document: dict[str, Any], max_chars: int = 3200, overlap: int = 600) -> list[dict[str, Any]]:
    if max_chars <= 0 or not 0 <= overlap < max_chars:
        raise ValueError("Require max_chars > 0 and 0 <= overlap < max_chars.")
    chunks: list[dict[str, Any]] = []
    current_section = "Introduction"
    for page in document["pages"]:
        buffer: list[str] = []

        def flush() -> None:
            text = "\n".join(buffer).strip()
            for part in _split_long(text, max_chars, overlap):
                chunks.append(_make_chunk(document, part, page["page"], current_section, len(chunks)))
            buffer.clear()

        for line in page["text"].splitlines():
            stripped = line.strip()
            if _is_heading(stripped):
                # Flush under the previous heading before assigning the new one.
                flush()
                current_section = stripped[:180]
            buffer.append(stripped)
        # Never carry text or overlap across pages; section labels may continue.
        flush()
    return chunks


def _make_chunk(
    document: dict[str, Any],
    text: str,
    page: int,
    section: str,
    index: int,
) -> dict[str, Any]:
    chunk_id = f"{document['doc_id']}::p{page}::c{index}"
    return {
        "chunk_id": chunk_id,
        "text": text.strip(),
        "doc_id": document["doc_id"],
        "filename": document["filename"],
        "title": document["title"],
        "short_title": document["short_title"],
        "year": int(document["year"]),
        "publisher": document["publisher"],
        "doc_type": document["doc_type"],
        "ncd_types": ",".join(document["ncd_types"]),
        "audience": document["audience"],
        "source_family": document["source_family"],
        "page": int(page),
        "section": section,
    }


def chunk_corpus(documents: list[dict[str, Any]], max_chars: int = 3200, overlap: int = 600) -> list[dict[str, Any]]:
    all_chunks: list[dict[str, Any]] = []
    for document in documents:
        all_chunks.extend(chunk_document(document, max_chars=max_chars, overlap=overlap))
    return all_chunks
