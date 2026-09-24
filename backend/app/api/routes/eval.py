from fastapi import APIRouter, Header, HTTPException

from app.core.schemas import EvalRunRequest
from app.eval.runner import run_evaluation
from app.rag.indexing import index_is_ready


router = APIRouter(prefix="/api", tags=["eval"])


@router.post("/eval/run")
async def eval_run(
    payload: EvalRunRequest,
    x_api_key: str | None = Header(default=None),
):
    if not index_is_ready():
        raise HTTPException(status_code=503, detail="Search index is not built.")
    if payload.include_generation and not (x_api_key or "").strip():
        raise HTTPException(status_code=401, detail="Generation evals require an API key header.")
    return await run_evaluation(
        provider=payload.provider,
        model=payload.model,
        api_key=x_api_key,
        include_generation=payload.include_generation,
        max_cases=payload.max_cases,
    )
