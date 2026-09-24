"""Local MiniLM embeddings via ONNX — same model family, no PyTorch download."""

from __future__ import annotations

from functools import lru_cache

import numpy as np


@lru_cache
def get_embedder():
    try:
        from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
    except ImportError:  # older chromadb
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

    return ONNXMiniLM_L6_V2()


def embed_texts(texts: list[str], batch_size: int = 32) -> np.ndarray:
    model = get_embedder()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        vectors.extend(model(batch))
    arr = np.asarray(vectors, dtype="float32")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.clip(norms, 1e-12, None)
    return arr / norms


def embed_query(text: str) -> list[float]:
    vector = embed_texts([text], batch_size=1)[0]
    return vector.tolist()
