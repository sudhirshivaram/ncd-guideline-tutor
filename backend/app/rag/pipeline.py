"""End-to-end RAG pipeline: retrieve -> (rerank) -> generate with citations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.core.config import get_settings
from app.core.schemas import ChatMessage, ChatSettings, Citation, ProviderName
from app.rag.generate import build_messages, stream_llm
from app.rag.rerank import rerank
from app.rag.retrieve import retrieve


def to_citations(chunks: list[dict[str, Any]]) -> list[Citation]:
    citations: list[Citation] = []
    for i, chunk in enumerate(chunks, start=1):
        snippet = chunk["text"].strip()
        citations.append(
            Citation(
                index=i,
                chunk_id=chunk["chunk_id"],
                title=chunk["title"],
                short_title=chunk["short_title"],
                doc_id=chunk["doc_id"],
                page=int(chunk["page"]),
                year=int(chunk["year"]),
                ncd_types=chunk["ncd_types"],
                doc_type=chunk["doc_type"],
                section=chunk.get("section", ""),
                snippet=snippet,
                score=float(chunk.get("rerank_score", chunk.get("score", 0.0))),
            )
        )
    return citations


def retrieve_contexts(question: str, settings: ChatSettings) -> list[dict[str, Any]]:
    cfg = get_settings()
    candidates = retrieve(
        query=question,
        top_k=settings.top_k,
        hybrid=settings.hybrid,
        filters=settings.filters,
        candidate_multiplier=max(3, cfg.rerank_candidates // max(settings.top_k, 1)),
    )
    if settings.rerank:
        return rerank(question, candidates, top_k=settings.top_k)
    return candidates[: settings.top_k]


async def stream_answer(
    question: str,
    history: list[ChatMessage],
    settings: ChatSettings,
    provider: ProviderName,
    api_key: str,
) -> AsyncIterator[dict[str, Any]]:
    contexts = retrieve_contexts(question, settings)
    citations = to_citations(contexts)
    yield {
        "type": "sources",
        "citations": [c.model_dump() for c in citations],
    }
    messages = build_messages(question, contexts, history)
    async for token in stream_llm(
        provider=provider,
        api_key=api_key,
        model=settings.model,
        messages=messages,
        temperature=settings.temperature,
    ):
        yield {"type": "token", "text": token}
    yield {"type": "done"}
