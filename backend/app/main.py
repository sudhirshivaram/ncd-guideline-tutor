import gradio as gr
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.rag.indexing import IndexUnavailableError
from app.rag.retrieve import RetrievalError

from app.api.routes.chat import router as chat_router
from app.api.routes.eval import router as eval_router
from app.api.routes.filters import router as filters_router
from app.core.config import get_settings
from app.rag.indexing import index_is_ready
from app.ui.gradio_app import build_gradio_app


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="WHO-grounded RAG tutor for NCD guidelines in primary health care.",
    version="1.0.0",
)

app.include_router(chat_router)
app.include_router(filters_router)
app.include_router(eval_router)


@app.exception_handler(IndexUnavailableError)
@app.exception_handler(RetrievalError)
async def retrieval_failure(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/api/health")
async def health():
    ready = index_is_ready()
    return JSONResponse(status_code=200 if ready else 503, content={
        "status": "ok" if ready else "unavailable",
        "app": settings.app_name,
        "index_ready": ready,
    })


demo = build_gradio_app()
app = gr.mount_gradio_app(app, demo, path="/")
