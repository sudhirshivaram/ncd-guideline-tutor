# Hugging Face Spaces — Docker
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/huggingface \
    PYTHONPATH=/app/backend \
    DATA_DIR=/app/data \
    INDEX_DIR=/app/indexes \
    PORT=7860

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Warm ONNX MiniLM + FlashRank models so Space startup is fast
RUN python -c "from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2; \
ONNXMiniLM_L6_V2()(['model warmup']); \
from flashrank import Ranker; Ranker(model_name='ms-marco-MiniLM-L-12-v2', cache_dir='/app/.cache/flashrank')"

COPY backend /app/backend
COPY data /app/data
COPY indexes /app/indexes
COPY evals /app/evals

RUN chmod +x /app/backend/entrypoint.sh
EXPOSE 7860
CMD ["/app/backend/entrypoint.sh"]
