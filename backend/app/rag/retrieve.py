"""Hybrid retrieval: vector + BM25 fused with Reciprocal Rank Fusion, then metadata filters."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from app.core.config import get_settings
from app.core.schemas import MetadataFilters
from app.rag.embeddings import embed_query
from app.rag.indexing import get_store
from app.rag.tokenize import tokenize


class RetrievalError(RuntimeError):
    """Retrieval failed; no fallback answer should be generated."""


logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(rank_lists: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = defaultdict(float)
    for ranking in rank_lists:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def _chroma_where(filters: MetadataFilters) -> dict[str, Any] | None:
    clauses: list[dict[str, Any]] = []
    if filters.doc_id:
        clauses.append({"doc_id": filters.doc_id})
    if filters.year is not None:
        clauses.append({"year": int(filters.year)})
    if filters.doc_type:
        clauses.append({"doc_type": filters.doc_type})
    if filters.source_family:
        clauses.append({"source_family": filters.source_family})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _matches_ncd(chunk: dict[str, Any], ncd_type: str | None) -> bool:
    if not ncd_type:
        return True
    labels = {part.strip().lower() for part in chunk.get("ncd_types", "").split(",") if part.strip()}
    return ncd_type.lower() in labels


def _vector_search(query: str, k: int, where: dict[str, Any] | None) -> list[str]:
    store = get_store()
    kwargs: dict[str, Any] = {
        "query_embeddings": [embed_query(query)],
        "n_results": k,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where
    try:
        result = store.collection.query(**kwargs)
    except Exception as exc:
        logger.error("Vector search failed (%s).", type(exc).__name__)
        raise RetrievalError("Semantic search failed. Please retry; if it persists, rebuild the search index.") from exc
    return list(result["ids"][0])


def _bm25_search(query: str, k: int, filters: MetadataFilters) -> list[str]:
    store = get_store()
    tokens = tokenize(query)
    if not tokens:
        return []
    scores = store.bm25.get_scores(tokens)
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    ids: list[str] = []
    for idx in ranked:
        chunk_id = store.bm25_ids[idx]
        chunk = store.chunk_by_id[chunk_id]
        if not _passes_filters(chunk, filters):
            continue
        ids.append(chunk_id)
        if len(ids) >= k:
            break
    return ids


def _passes_filters(chunk: dict[str, Any], filters: MetadataFilters) -> bool:
    if filters.doc_id and chunk["doc_id"] != filters.doc_id:
        return False
    if filters.year is not None and int(chunk["year"]) != int(filters.year):
        return False
    if filters.doc_type and chunk["doc_type"] != filters.doc_type:
        return False
    if filters.source_family and chunk["source_family"] != filters.source_family:
        return False
    if not _matches_ncd(chunk, filters.ncd_type):
        return False
    return True


def retrieve(
    query: str,
    top_k: int = 8,
    hybrid: bool = True,
    filters: MetadataFilters | None = None,
    candidate_multiplier: int = 3,
) -> list[dict[str, Any]]:
    settings = get_settings()
    filters = filters or MetadataFilters()
    store = get_store()
    fetch_k = max(top_k * candidate_multiplier, settings.rerank_candidates)

    where = _chroma_where(filters)
    try:
        vector_ids = _vector_search(query, fetch_k, where)
    except RetrievalError:
        raise
    except Exception as exc:
        logger.error("Semantic retrieval failed (%s).", type(exc).__name__)
        raise RetrievalError("Semantic retrieval is unavailable. Please retry or rebuild the search index.") from exc

    if hybrid:
        try:
            bm25_ids = _bm25_search(query, fetch_k, filters)
        except Exception as exc:
            logger.error("Keyword retrieval failed (%s).", type(exc).__name__)
            raise RetrievalError("Keyword search failed. Please retry or rebuild the search index.") from exc
        fused = reciprocal_rank_fusion([vector_ids, bm25_ids], k=settings.hybrid_rrf_k)
        ordered_ids = [chunk_id for chunk_id, _score in fused]
        score_map = {chunk_id: score for chunk_id, score in fused}
    else:
        ordered_ids = vector_ids
        score_map = {chunk_id: 1.0 / (i + 1) for i, chunk_id in enumerate(vector_ids)}

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk_id in ordered_ids:
        if chunk_id in seen:
            continue
        chunk = store.chunk_by_id.get(chunk_id)
        if chunk is None:
            raise RetrievalError("Retrieved source is missing from the index. Rebuild the search index.")
        if not _passes_filters(chunk, filters):
            continue
        seen.add(chunk_id)
        item = dict(chunk)
        item["score"] = float(score_map.get(chunk_id, 0.0))
        results.append(item)
        if len(results) >= fetch_k:
            break
    return results
