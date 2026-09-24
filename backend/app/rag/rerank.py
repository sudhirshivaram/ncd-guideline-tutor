"""Local MiniLM cross-encoder reranking via FlashRank (ONNX, no PyTorch)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import get_settings


@lru_cache
def get_reranker():
    from flashrank import Ranker

    settings = get_settings()
    cache_dir = str(settings.index_dir.parent / ".cache" / "flashrank")
    return Ranker(model_name=settings.rerank_model, cache_dir=cache_dir)


def rerank(query: str, candidates: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    if not candidates:
        return []
    if len(candidates) == 1:
        candidates[0]["rerank_score"] = 1.0
        return candidates[:top_k]

    from flashrank import RerankRequest

    ranker = get_reranker()
    passages = [{"id": i, "text": c["text"][:4000]} for i, c in enumerate(candidates)]
    results = ranker.rerank(RerankRequest(query=query, passages=passages))
    ordered: list[dict[str, Any]] = []
    for item in results:
        if isinstance(item, dict):
            idx = int(item["id"])
            score = float(item.get("score", 0.0))
        else:
            idx = int(item.id)
            score = float(getattr(item, "score", 0.0))
        chunk = dict(candidates[idx])
        chunk["rerank_score"] = score
        ordered.append(chunk)
    return ordered[:top_k]
