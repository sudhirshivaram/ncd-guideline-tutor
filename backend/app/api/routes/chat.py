from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.core.schemas import ChatRequest, ProviderName
from app.rag.indexing import index_is_ready
from app.rag.pipeline import stream_answer


router = APIRouter(prefix="/api", tags=["chat"])


def _provider(x_llm_provider: str | None) -> ProviderName:
    value = (x_llm_provider or "openai").strip().lower()
    if value not in {"openai", "gemini", "anthropic"}:
        raise HTTPException(status_code=400, detail="Provider must be openai, gemini, or anthropic.")
    return value  # type: ignore[return-value]


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    x_llm_provider: str | None = Header(default="openai"),
    x_api_key: str | None = Header(default=None),
):
    if not index_is_ready():
        raise HTTPException(
            status_code=503,
            detail="Search index is not built. Run `python -m app.rag.indexing` from backend/.",
        )
    if not (x_api_key or "").strip():
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Add your provider key in Settings. It is sent only with this request.",
        )

    provider = _provider(x_llm_provider)

    async def events():
        try:
            async for event in stream_answer(
                question=payload.message,
                history=payload.history,
                settings=payload.settings,
                provider=provider,
                api_key=x_api_key or "",
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
