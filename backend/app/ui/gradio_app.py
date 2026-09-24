"""Gradio Blocks UI that calls the RAG pipeline in-process."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import gradio as gr

from app.core.schemas import ChatMessage, ChatSettings, MetadataFilters, ProviderName
from app.rag.indexing import get_store, index_is_ready
from app.rag.pipeline import stream_answer


PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
        "default": "gpt-4o-mini",
    },
    "gemini": {
        "label": "Google Gemini",
        "models": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
        "default": "gemini-3.5-flash-lite",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "models": ["claude-haiku-4-5", "claude-sonnet-4-5", "claude-sonnet-5"],
        "default": "claude-haiku-4-5",
    },
}

EXAMPLES = [
    "When should pharmacological treatment for adult hypertension start?",
    "What is the HEARTS-D first-line treatment for type 2 diabetes?",
    "What does WHO recommend for combination therapy when starting hypertension treatment?",
    "When is metformin contraindicated in the HEARTS-D diabetes protocol?",
]

DISCLAIMER = (
    "Not medical advice · WHO guidelines only. This is clinical decision support, "
    "not a substitute for clinical judgment, and does not imply WHO endorsement."
)

ALL = "All"

# Saved retrieval-only baseline for the current three-document corpus.
def _saved_eval_scores() -> tuple[str, str]:
    report = Path(__file__).resolve().parents[3] / "evals" / "three_document_retrieval.json"
    try:
        metrics = json.loads(report.read_text(encoding="utf-8"))["retrieval"]
        return str(metrics["document_hit_rate_at_5"]), str(metrics["mrr"])
    except (OSError, ValueError, KeyError, TypeError):
        return "Pending", "Pending"


EVAL_RECALL_AT_5, EVAL_MRR = _saved_eval_scores()


def _load_facets() -> dict[str, Any]:
    if not index_is_ready():
        return {
            "ncd_types": [],
            "documents": [],
            "years": [],
            "doc_types": [],
        }
    try:
        return get_store().facets()
    except Exception:
        return {
            "ncd_types": [],
            "documents": [],
            "years": [],
            "doc_types": [],
        }


def _index_stats() -> dict[str, Any]:
    if not index_is_ready():
        return {"chunks": None, "pages": None, "docs": None}
    try:
        store = get_store()
        chunks = store.chunks
        pages = {(c["doc_id"], int(c["page"])) for c in chunks}
        docs = {c["doc_id"] for c in chunks}
        return {"chunks": len(chunks), "pages": len(pages), "docs": len(docs)}
    except Exception:
        return {"chunks": None, "pages": None, "docs": None}


def _metrics_html() -> str:
    stats = _index_stats()
    chunks = f"{stats['chunks']:,}" if stats["chunks"] is not None else "—"
    pages = f"{stats['pages']:,}" if stats["pages"] is not None else "—"
    docs = str(stats["docs"]) if stats["docs"] is not None else "—"

    return f"""
<div style="font-family: system-ui, -apple-system, Segoe UI, sans-serif; color: #0f172a;">
  <div style="margin-bottom: 12px;">
    <div style="font-size: 1.35rem; font-weight: 700; color: #0f766e;">NCD Guideline Tutor</div>
    <div style="font-size: 0.85rem; color: #64748b;">WHO NCD RAG · primary care protocols</div>
  </div>

  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 14px;">
    <div style="border: 2px solid #14b8a6; border-radius: 12px; padding: 10px 12px; background: #f0fdfa;">
      <div style="font-weight: 700; color: #0f766e; font-size: 0.9rem;">MiniLM ONNX</div>
      <div style="font-size: 0.75rem; color: #475569; margin-top: 4px;">all-MiniLM-L6-v2 · local embeddings</div>
    </div>
    <div style="border: 2px solid #3b82f6; border-radius: 12px; padding: 10px 12px; background: #eff6ff;">
      <div style="font-weight: 700; color: #1d4ed8; font-size: 0.9rem;">Chroma + BM25</div>
      <div style="font-size: 0.75rem; color: #475569; margin-top: 4px;">Hybrid vector + keyword · {chunks} chunks</div>
    </div>
    <div style="border: 2px solid #a855f7; border-radius: 12px; padding: 10px 12px; background: #faf5ff;">
      <div style="font-weight: 700; color: #7e22ce; font-size: 0.9rem;">Hybrid RRF + FlashRank</div>
      <div style="font-size: 0.75rem; color: #475569; margin-top: 4px;">Reciprocal rank fusion · MiniLM rerank</div>
    </div>
    <div style="border: 2px solid #f97316; border-radius: 12px; padding: 10px 12px; background: #fff7ed;">
      <div style="font-weight: 700; color: #c2410c; font-size: 0.9rem;">Gradio + FastAPI</div>
      <div style="font-size: 0.75rem; color: #475569; margin-top: 4px;">BYO OpenAI / Gemini / Claude keys</div>
    </div>
  </div>

  <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 14px; text-align: center;">
    <div style="border-radius: 12px; padding: 12px 8px; background: #f8fafc; border: 1px solid #e2e8f0;">
      <div style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em; color: #64748b;">Knowledge base</div>
      <div style="font-size: 1.6rem; font-weight: 700; color: #2563eb; line-height: 1.2;">{pages}</div>
      <div style="font-size: 0.72rem; color: #64748b;">{docs} WHO PDFs · {chunks} chunks</div>
    </div>
    <div style="border-radius: 12px; padding: 12px 8px; background: #f8fafc; border: 1px solid #e2e8f0;">
      <div style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em; color: #64748b;">Saved retrieval eval</div>
      <div style="font-size: 1.15rem; font-weight: 700; color: #0f766e; line-height: 1.25; margin-top: 4px;">Doc hit@5 {EVAL_RECALL_AT_5}</div>
      <div style="font-size: 0.85rem; font-weight: 600; color: #334155;">MRR {EVAL_MRR}</div>
    </div>
    <div style="border-radius: 12px; padding: 12px 8px; background: #f8fafc; border: 1px solid #e2e8f0;">
      <div style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em; color: #64748b;">Index cost</div>
      <div style="font-size: 1.6rem; font-weight: 700; color: #16a34a; line-height: 1.2;">$0</div>
      <div style="font-size: 0.72rem; color: #64748b;">Local MiniLM · chat uses your key</div>
    </div>
  </div>

  <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-bottom: 12px;">
    <span style="background:#0f766e;color:#fff;padding:6px 10px;border-radius:8px;font-size:0.75rem;font-weight:600;">Query</span>
    <span style="color:#94a3b8;">→</span>
    <span style="background:#2563eb;color:#fff;padding:6px 10px;border-radius:8px;font-size:0.75rem;font-weight:600;">Embed</span>
    <span style="color:#94a3b8;">→</span>
    <span style="background:#7e22ce;color:#fff;padding:6px 10px;border-radius:8px;font-size:0.75rem;font-weight:600;">Retrieve</span>
    <span style="color:#94a3b8;">→</span>
    <span style="background:#c2410c;color:#fff;padding:6px 10px;border-radius:8px;font-size:0.75rem;font-weight:600;">Rerank</span>
    <span style="color:#94a3b8;">→</span>
    <span style="background:#0f766e;color:#fff;padding:6px 10px;border-radius:8px;font-size:0.75rem;font-weight:600;">Answer</span>
  </div>

  <div style="font-size: 0.72rem; color: #94a3b8; line-height: 1.4;">
    HEARTS · HEARTS-D · hypertension · diabetes · Chroma · BM25 · MiniLM
  </div>
</div>
"""


def _format_citations(citations: list[dict[str, Any]]) -> str:
    if not citations:
        return "_No passages retrieved yet._"
    lines = ["### Retrieved passages", "", "_These passages may not answer your question._", ""]
    for cite in citations:
        title = cite.get("short_title") or cite.get("title") or "Source"
        page = cite.get("page", "?")
        year = cite.get("year", "")
        section = (cite.get("section") or "").strip()
        snippet = (cite.get("snippet") or "").strip()
        ncd = cite.get("ncd_types") or ""
        doc_type = cite.get("doc_type") or ""
        idx = cite.get("index", "")
        header = f"**[{idx}] {title}** — p.{page}"
        if year:
            header += f" ({year})"
        lines.append(header)
        meta_bits = [b for b in (ncd, doc_type) if b]
        if meta_bits:
            lines.append(f"*{', '.join(meta_bits)}*")
        if section:
            lines.append(f"Section: {section}")
        if snippet:
            lines.append("")
            lines.extend(f"> {line}" for line in snippet.splitlines())
        lines.append("")
    return "\n".join(lines)


def _history_to_messages(history: list[dict[str, str]] | None) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for turn in history or []:
        if isinstance(turn, dict):
            role = turn.get("role")
            content = turn.get("content")
        else:
            role = getattr(turn, "role", None)
            content = getattr(turn, "content", None)
        if isinstance(content, list):
            # Gradio multimodal content blocks — keep text pieces only
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("text"):
                    parts.append(str(block["text"]))
            content = "\n".join(parts)
        content = (content or "").strip() if isinstance(content, str) else ""
        if role in ("user", "assistant") and content:
            messages.append(ChatMessage(role=role, content=content))
    return messages


def _build_settings(
    model: str,
    temperature: float,
    top_k: int,
    hybrid: bool,
    rerank: bool,
    ncd_type: str,
    doc_label: str,
    year: str,
    doc_type: str,
    doc_id_by_label: dict[str, str],
) -> ChatSettings:
    filters = MetadataFilters(
        ncd_type=None if not ncd_type or ncd_type == ALL else ncd_type,
        doc_id=None if not doc_label or doc_label == ALL else doc_id_by_label.get(doc_label),
        year=None if not year or year == ALL else int(year),
        doc_type=None if not doc_type or doc_type == ALL else doc_type,
    )
    return ChatSettings(
        model=model,
        temperature=float(temperature),
        top_k=int(top_k),
        hybrid=bool(hybrid),
        rerank=bool(rerank),
        filters=filters,
    )


def build_gradio_app() -> gr.Blocks:
    facets = _load_facets()
    ncd_choices = [ALL] + list(facets.get("ncd_types") or [])
    year_choices = [ALL] + [str(y) for y in (facets.get("years") or [])]
    doc_type_choices = [ALL] + list(facets.get("doc_types") or [])
    documents = facets.get("documents") or []
    doc_labels = [ALL] + [d.get("short_title") or d.get("doc_id") for d in documents]
    doc_id_by_label = {
        (d.get("short_title") or d.get("doc_id")): d["doc_id"] for d in documents
    }

    with gr.Blocks(title="NCD Guideline Tutor", fill_height=True) as demo:
        gr.Markdown(
            "# NCD Guideline Tutor\n"
            "WHO-grounded RAG for primary-care hypertension and type 2 diabetes "
            "(HEARTS, HEARTS-D, WHO hypertension guideline).\n\n"
            f"*{DISCLAIMER}*"
        )
        if not index_is_ready():
            gr.Markdown(
                "> **Search index not ready.** Run "
                "`PYTHONPATH=. python -m app.rag.indexing` from `backend/`."
            )

        with gr.Row():
            with gr.Column(scale=1, min_width=260):
                with gr.Accordion("LLM settings", open=True):
                    provider = gr.Dropdown(
                        choices=list(PROVIDERS.keys()),
                        value="openai",
                        label="Provider",
                    )
                    model = gr.Dropdown(
                        choices=PROVIDERS["openai"]["models"],
                        value=PROVIDERS["openai"]["default"],
                        label="Model",
                    )
                    api_key = gr.Textbox(
                        label="API key",
                        type="password",
                        placeholder="Paste your key (session only; never stored on the server)",
                    )
                    temperature = gr.Slider(0, 1, value=0.2, step=0.1, label="Temperature")
                    top_k = gr.Slider(3, 12, value=8, step=1, label="Top-k passages")
                    hybrid = gr.Checkbox(value=True, label="Hybrid search (vector + BM25)")
                    rerank = gr.Checkbox(value=True, label="Cross-encoder rerank")

                with gr.Accordion("WHO document filters", open=False):
                    ncd_type = gr.Dropdown(choices=ncd_choices, value=ALL, label="NCD type")
                    doc_id = gr.Dropdown(choices=doc_labels, value=ALL, label="Document")
                    year = gr.Dropdown(choices=year_choices, value=ALL, label="Year")
                    doc_type = gr.Dropdown(choices=doc_type_choices, value=ALL, label="Doc type")

            with gr.Column(scale=3, min_width=420):
                chatbot = gr.Chatbot(
                    label="Chat",
                    height=480,
                    buttons=["copy"],
                    latex_delimiters=[
                        {"left": "$$", "right": "$$", "display": True},
                        {"left": "$", "right": "$", "display": False},
                    ],
                )
                with gr.Row():
                    message = gr.Textbox(
                        placeholder="Ask a WHO NCD guideline question…",
                        label="Message",
                        scale=5,
                        lines=2,
                    )
                    send_btn = gr.Button("Send", variant="primary", scale=1)
                with gr.Row():
                    clear_btn = gr.Button("Clear chat", variant="secondary")
                citations = gr.Markdown(value="_Retrieved passages appear here after you send a question._")
                gr.Examples(
                    examples=[[q] for q in EXAMPLES],
                    inputs=[message],
                    label="Example questions",
                )

            with gr.Column(scale=2, min_width=300):
                gr.HTML(_metrics_html())

        def on_provider_change(selected: str):
            catalog = PROVIDERS.get(selected) or PROVIDERS["openai"]
            return gr.update(choices=catalog["models"], value=catalog["default"])

        provider.change(on_provider_change, inputs=[provider], outputs=[model])

        async def respond(
            user_message: str,
            history: list[dict[str, str]] | None,
            provider_value: str,
            model_value: str,
            api_key_value: str,
            temperature_value: float,
            top_k_value: float,
            hybrid_value: bool,
            rerank_value: bool,
            ncd_value: str,
            doc_value: str,
            year_value: str,
            doc_type_value: str,
        ):
            history = list(history or [])
            text = (user_message or "").strip()
            if not text:
                yield history, "", ""
                return

            if not (api_key_value or "").strip():
                history = history + [
                    {"role": "user", "content": text},
                    {
                        "role": "assistant",
                        "content": (
                            "Add your LLM API key in the left panel to chat. "
                            "Keys stay in this browser session and are never written on the server."
                        ),
                    },
                ]
                yield history, "_No passages retrieved._", ""
                return

            if not index_is_ready():
                history = history + [
                    {"role": "user", "content": text},
                    {
                        "role": "assistant",
                        "content": (
                            "Search index is not built. From `backend/` run "
                            "`PYTHONPATH=. python -m app.rag.indexing`."
                        ),
                    },
                ]
                yield history, "_No passages retrieved._", ""
                return

            prior = _history_to_messages(history)
            history = history + [
                {"role": "user", "content": text},
                {"role": "assistant", "content": "Retrieving WHO sources…"},
            ]
            citations_md = "_Retrieving passages…_"
            yield history, citations_md, ""

            settings = _build_settings(
                model=model_value,
                temperature=temperature_value,
                top_k=int(top_k_value),
                hybrid=hybrid_value,
                rerank=rerank_value,
                ncd_type=ncd_value,
                doc_label=doc_value,
                year=year_value,
                doc_type=doc_type_value,
                doc_id_by_label=doc_id_by_label,
            )
            provider_name: ProviderName = provider_value if provider_value in PROVIDERS else "openai"  # type: ignore[assignment]

            try:
                answer = ""
                async for event in stream_answer(
                    question=text,
                    history=prior,
                    settings=settings,
                    provider=provider_name,
                    api_key=api_key_value.strip(),
                ):
                    etype = event.get("type")
                    if etype == "sources":
                        citations_md = _format_citations(event.get("citations") or [])
                        if not answer:
                            history[-1] = {"role": "assistant", "content": ""}
                        yield history, citations_md, ""
                    elif etype == "token":
                        answer += event.get("text") or ""
                        history[-1] = {"role": "assistant", "content": answer}
                        yield history, citations_md, ""
                    elif etype == "error":
                        err = event.get("message") or "The model request failed."
                        history[-1] = {"role": "assistant", "content": f"**Error:** {err}"}
                        yield history, citations_md, ""
            except Exception as exc:  # noqa: BLE001 — surface provider/pipeline errors in UI
                history[-1] = {"role": "assistant", "content": f"**Error:** {exc}"}
                yield history, citations_md, ""

        inputs = [
            message,
            chatbot,
            provider,
            model,
            api_key,
            temperature,
            top_k,
            hybrid,
            rerank,
            ncd_type,
            doc_id,
            year,
            doc_type,
        ]
        outputs = [chatbot, citations, message]

        send_btn.click(respond, inputs=inputs, outputs=outputs)
        message.submit(respond, inputs=inputs, outputs=outputs)

        def clear_chat():
            return [], "_Retrieved passages appear here after you send a question._", ""

        clear_btn.click(clear_chat, inputs=None, outputs=outputs)

    return demo
