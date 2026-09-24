"""PDF ingestion: extract page text and strip repeating headers/footers."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import pymupdf

from app.rag.metadata import DOCUMENT_CATALOG, lookup_filename


_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")


def _blocks_to_text(page: pymupdf.Page) -> str:
    blocks = page.get_text("blocks")
    blocks = sorted(blocks, key=lambda b: (round(b[1] / 10), b[0]))
    parts: list[str] = []
    for block in blocks:
        text = (block[4] or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def _normalize_page(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_RE.sub("\n\n", text)
    return text.strip()


def _line_signature(line: str) -> str:
    return re.sub(r"\d+", "#", line).strip().lower()


def _repeated_lines(pages: list[str], min_ratio: float = 0.35) -> set[str]:
    counts: Counter[str] = Counter()
    for page in pages:
        seen = set()
        lines = [ln.strip() for ln in page.splitlines() if ln.strip()]
        edge = lines[:4] + lines[-3:]
        for line in edge:
            if len(line) < 8 or len(line) > 160:
                continue
            sig = _line_signature(line)
            if sig not in seen:
                counts[sig] += 1
                seen.add(sig)
    threshold = max(3, int(len(pages) * min_ratio))
    return {sig for sig, n in counts.items() if n >= threshold}


def _strip_boilerplate(page: str, repeated: set[str]) -> str:
    kept: list[str] = []
    for line in page.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        if _line_signature(stripped) in repeated:
            continue
        if stripped.lower().startswith("isbn "):
            continue
        kept.append(stripped)
    return _normalize_page("\n".join(kept))


def extract_document(pdf_path: Path) -> dict[str, Any]:
    
    meta = lookup_filename(pdf_path.name)
    doc = pymupdf.open(pdf_path)
    raw_pages: list[str] = []
    for page in doc:
        raw_pages.append(_normalize_page(_blocks_to_text(page)))
    doc.close()

    repeated = _repeated_lines(raw_pages)
    pages = []
    for i, raw in enumerate(raw_pages, start=1):
        text = _strip_boilerplate(raw, repeated)
        if text:
            pages.append({"page": i, "text": text})
    return {**meta, "pages": pages, "page_count": len(raw_pages)}


def ingest_corpus(data_dir: Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for filename in DOCUMENT_CATALOG:
        path = data_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing knowledge source: {path}")
        documents.append(extract_document(path))
    return documents
