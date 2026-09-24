"""Retrieval and optional generation evaluation for the NCD gold set."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.schemas import ChatSettings, MetadataFilters, ProviderName
from app.eval.metrics import (
    citation_metrics,
    abstention_signal,
    summarize,
    first_relevant_rank,
    lexical_overlap,
    mean_reciprocal_rank,
    question_answer_overlap,
    document_hit_rate_at_k,
)
from app.rag.generate import SYSTEM_PROMPT, build_messages, stream_llm
from app.rag.pipeline import retrieve_contexts, to_citations


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_gold_set(path: Path | None = None) -> list[dict[str, Any]]:
    gold_path = path or (_repo_root() / "evals" / "ncd_gold_set.json")
    with gold_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload["cases"]


def retrieval_metrics(cases: list[dict[str, Any]], k: int = 5) -> dict[str, Any]:
    ranks: list[int | None] = []
    details = []
    for case in cases:
        if case.get("unanswerable") or not case.get("expected_doc_ids"):
            continue
        filters = MetadataFilters(**(case.get("filters") or {}))
        settings = ChatSettings(top_k=k, hybrid=True, rerank=True, filters=filters)
        retrieved = retrieve_contexts(case["question"], settings)
        rank = first_relevant_rank(retrieved, case.get("expected_doc_ids", []))
        ranks.append(rank)
        details.append(
            {
                "id": case["id"],
                "hit_at_k": rank is not None and rank <= k,
                "rank": rank,
                "retrieved_docs": [c["doc_id"] for c in retrieved[:k]],
            }
        )
    return {
        "n": len(ranks),
        "document_hit_rate_at_k": document_hit_rate_at_k(ranks, k),
        "mrr": mean_reciprocal_rank(ranks),
        "k": k,
        "cases": details,
    }


async def _complete_answer(
    question: str,
    contexts: list[dict[str, Any]],
    provider: ProviderName,
    model: str,
    api_key: str,
) -> str:
    messages = build_messages(question, contexts, [])
    parts: list[str] = []
    async for token in stream_llm(provider, api_key, model, messages, temperature=0.0):
        parts.append(token)
    return "".join(parts)


async def run_evaluation(
    provider: ProviderName = "openai",
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
    include_generation: bool = False,
    max_cases: int | None = None,
) -> dict[str, Any]:
    cases = load_gold_set()
    if max_cases is not None:
        if max_cases < 1:
            raise ValueError("max_cases must be positive.")
        cases = cases[:max_cases]
    retrieval = retrieval_metrics(cases, k=5)

    generation = None
    if include_generation:
        if not api_key:
            raise ValueError("Generation evaluation requires an API key.")
        gen_rows = []
        for case in cases:
            settings = ChatSettings(top_k=5, hybrid=True, rerank=True,
                                    filters=MetadataFilters(**(case.get("filters") or {})))
            contexts = retrieve_contexts(case["question"], settings)
            citations = [c.model_dump() for c in to_citations(contexts)]
            answer = await _complete_answer(case["question"], contexts, provider, model, api_key)
            unanswerable = bool(case.get("unanswerable"))
            gen_rows.append({
                "id": case["id"],
                "unanswerable": unanswerable,
                "answer_context_token_overlap": None if unanswerable else lexical_overlap(answer, contexts),
                "question_answer_token_overlap": None if unanswerable else question_answer_overlap(case["question"], answer),
                **citation_metrics(answer, citations, case.get("expected_sources") or []),
                "unanswerable_abstention_signal": float(abstention_signal(answer)) if unanswerable else None,
                "answerable_abstention_signal": float(abstention_signal(answer)) if not unanswerable else None,
                "requires_manual_review": True,
                "answer": answer,
                "citations": citations,
            })
        metric_names = (
            "answer_context_token_overlap", "question_answer_token_overlap",
            "citation_id_precision", "citation_source_precision", "citation_source_hit",
            "unanswerable_abstention_signal", "answerable_abstention_signal",
        )
        generation = {
            "n": len(gen_rows),
            "metrics": {key: summarize(gen_rows, key) for key in metric_names},
            "cases": gen_rows,
            "note": "Token overlap and abstention signals are lexical diagnostics, not semantic correctness or faithfulness. Review full answers for unsupported claims and refusals followed by invented advice. Citation location matching does not establish claim support. Unannotated source scores are null and excluded from means.",
        }

    return {
        "schema_version": 2,
        "provider": provider if include_generation else None,
        "model": model if include_generation else None,
        "retrieval": {
            "document_hit_rate_at_5": retrieval["document_hit_rate_at_k"],
            "mrr": retrieval["mrr"],
            "k": retrieval["k"],
            "n": retrieval["n"],
            "cases": retrieval["cases"],
        },
        "generation": generation,
        "system_prompt_chars": len(SYSTEM_PROMPT),
    }


async def _cli() -> None:
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Run NCD RAG evaluation.")
    parser.add_argument("--generation", action="store_true")
    parser.add_argument("--provider", choices=["openai", "gemini", "anthropic"], default="openai")
    parser.add_argument("--output", type=Path, help="Save the complete evaluation report.")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--max-cases", type=int, default=None)
    args = parser.parse_args()
    key_env = {"openai": "OPENAI_API_KEY", "gemini": "GOOGLE_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
    api_key = os.environ.get(key_env[args.provider])
    result = await run_evaluation(
        provider=args.provider,  # type: ignore[arg-type]
        model=args.model,
        api_key=api_key,
        include_generation=args.generation,
        max_cases=args.max_cases,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    summary = {"retrieval": {k: v for k, v in result["retrieval"].items() if k != "cases"},
               "generation": None if result["generation"] is None else {k: v for k, v in result["generation"].items() if k != "cases"}}
    print(json.dumps(summary, indent=2))



if __name__ == "__main__":
    import asyncio

    asyncio.run(_cli())
