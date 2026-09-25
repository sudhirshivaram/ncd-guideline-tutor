# Code walkthrough — NCD Guideline Tutor

This document is the interview-oriented walkthrough of the implementation: what each module does, why it exists, and which alternatives were rejected.

## Project structure

```
data/                     WHO PDFs (knowledge sources)
backend/app/core/         settings and request schemas
backend/app/rag/          ingest → chunk → embed → index → retrieve → rerank → generate
backend/app/api/routes/   FastAPI: /api/chat, /api/filters, /api/eval/run
backend/app/ui/           Gradio Blocks chat UI
backend/app/eval/         gold-set runner and metrics
evals/ncd_gold_set.json   reproducible questions
indexes/                  Chroma + BM25 artifacts
```

The backend is a FastAPI app (`backend/app/main.py`) with Gradio mounted at `/`. REST routes under `/api/*` stay available for health checks, scripting, and evals.

## End-to-end data flow

1. `ingest.py` opens each catalogued PDF with PyMuPDF, extracts text blocks in reading order, and drops headers/footers that repeat across pages.
2. `chunking.py` splits on headings and size (~3200 characters, 600 overlap). Chunks keep `page` and `section`; text never crosses a page boundary.
3. `metadata.py` attaches document-level fields: NCD type(s), year, doc type, source family (`clinical_protocols` for the current three documents).
4. `indexing.py` writes `chunks.jsonl`, a BM25 pickle, and a Chroma collection with MiniLM embeddings.
5. A Gradio chat turn calls `pipeline.stream_answer` in-process: retrieve, optional rerank, stream LLM tokens, emit citations first so the Sources panel can update while tokens arrive.
6. `POST /api/chat` remains as an SSE alternative for non-UI clients (`token`, `sources`, `done`, `error`).

## Why this design

**Chunking vs fixed windows.** WHO protocols include nested headings and dose tables. Naive 512-token windows split tables mid-row. Chunks stop at every PDF page boundary for accurate citations and at detected headings for section labels. Overlap applies only within a page section. Large tables and tables spanning pages can split; heading detection remains heuristic.

**Local embeddings vs OpenAI embeddings.** The spec requires a user-supplied LLM key and a **sub-$0.50** test budget. Local indexing requires no API key or per-token embedding charges. ONNX `all-MiniLM-L6-v2` (via Chroma) is weaker semantically than large API embedders, but it is free, CPU-friendly, and good enough for a focused three-document corpus. We avoided PyTorch `sentence-transformers` so Hugging Face CPU Spaces and low-disk laptops can still run the stack.

**Chroma + BM25 vs a hosted vector DB.** A hosted store (Pinecone, Qdrant Cloud) adds credentials and vendor lock-in. Persistent Chroma plus `rank_bm25` is portable for GitHub and Hugging Face Spaces. Alternative: SQLite + sqlite-vec; we kept Chroma because it is the common teaching stack.

**Hybrid RRF vs vector-only.** Keyword search is essential for drug names, protocol numbers, and abbreviations (HEARTS, HbA1c, ACEi). RRF (`1/(k+rank)`) avoids mixing incompatible raw scores. We did not train a learned fusion model; the corpus is too small to justify it.

**Metadata filtering in Python + Chroma `where`.** Scalar fields (`year`, `doc_id`, `doc_type`) can be pushed into Chroma. `ncd_types` is multi-label (comma-separated), so we filter that in Python after fusion. Pushing multi-value arrays into Chroma metadata is awkward and less portable.

**Cross-encoder rerank vs sending the full fused list.** LLMs degrade when the context is noisy. Reranking the top ~20 fused hits down to 5–8 costs milliseconds locally and usually improves faithfulness. Users can disable it in Settings to see the difference.

**Three LLM providers via official SDKs rather than a single gateway.** LiteLLM is convenient, but official OpenAI / Gemini / Anthropic clients fail more clearly in interviews and avoid another abstraction. Streaming is first-class because the chat UI expects tokens.

**API keys in the Gradio password field, not `.env`.** The spec forbids committing keys and wants users to bring their own. The server never writes the key to disk.

**Gradio on FastAPI.** Gradio gives a portable chat UI for Hugging Face Spaces without a Node build. FastAPI still owns health/eval/chat REST and mounts Gradio at `/` via `gr.mount_gradio_app`. The pipeline modules stay UI-agnostic.

## Important modules

| Module | Role |
| --- | --- |
| `rag/metadata.py` | Source catalog — the only place document identity lives |
| `rag/ingest.py` | PDF → cleaned pages |
| `rag/chunking.py` | Pages → overlapping section chunks |
| `rag/embeddings.py` | Lazy ONNX MiniLM encoder |
| `rag/indexing.py` | Build/load Chroma + BM25 |
| `rag/retrieve.py` | Hybrid RRF + filters |
| `rag/rerank.py` | FlashRank MiniLM cross-encoder |
| `rag/generate.py` | System prompt + provider streams |
| `rag/pipeline.py` | Orchestration and citation objects |
| `ui/gradio_app.py` | Gradio Blocks: settings, filters, streaming chat, citations |
| `api/routes/chat.py` | SSE endpoint for non-UI clients |
| `eval/runner.py` | document hit rate@5, MRR, optional generation proxies |

## How the UI talks to the pipeline

`backend/app/ui/gradio_app.py` builds `ChatSettings` / `MetadataFilters` from the left-panel controls and calls `stream_answer` directly:

- provider + API key + model / temperature / top_k / hybrid / rerank
- document filters (NCD type, document, year, doc type) from `IndexStore.facets()`
- chat history converted to `ChatMessage` list

On each turn it yields growing chatbot messages for `token` events and refreshes the Sources markdown for `sources` events. Keys are not persisted server-side.

## Evaluation

`evals/ncd_gold_set.json` encodes expected `doc_id`s and verified supporting PDF pages for all 14 answerable cases, with evidence excerpts and source-file hashes. Unanswerable questions (COVID antivirals, pediatric CHOP, FHIR/EHR) are excluded from document hit rate@5 so a correct “not in sources” retrieval pattern is not punished.

Generation reports name token-overlap diagnostics explicitly; they do not claim to measure semantic faithfulness. Source scoring checks inline citations against annotated document/page pairs and excludes missing annotations. Refusal signals are reported separately for answerable and unanswerable cases, with full answers retained for manual review. See README for scoring denominators and limitations.

`app.eval.semantic` adds cached, budget-limited LLM judging of context relevance, answer quality, groundedness, claim/citation support, and refusals. The saved 17-case run cost an estimated $0.0355481. Read `evals/semantic_results.json` together with `evals/semantic_review.md`: assistant source review found retrieval noise and an incomplete insulin-protocol summary that the automated judge missed. These are documented evaluation findings, not clinical validation.

## Debugging and extending

- Index missing → `503` / `index_ready: false` from `/api/health`. Rebuild with `python -m app.rag.indexing`.
- Empty or wrong answers → inspect citation snippets first; if the right page is absent, debug retrieve/rerank before the prompt.
- Add a PDF → register it in `DOCUMENT_CATALOG` and rebuild the index.
- Add a provider → new branch in `generate.py` `stream_llm` and the Gradio provider catalog.
- Tune chunk size → `CHUNK_SIZE_CHARS` / `CHUNK_OVERLAP_CHARS` in `.env`.

## Security notes

- Keys are not logged or written to disk.
- The Docker image serves Gradio and the API same-origin on port 7860.
- The system prompt forbids patient-specific prescribing; the UI shows a persistent disclaimer. This is not a medical device.
