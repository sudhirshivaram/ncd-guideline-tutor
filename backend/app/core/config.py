from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_repo_root() / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "NCD Guideline Tutor"
    app_env: str = "development"

    data_dir: Path = _repo_root() / "data"
    index_dir: Path = _repo_root() / "indexes"

    embedding_model: str = "all-MiniLM-L6-v2"
    rerank_model: str = "ms-marco-MiniLM-L-12-v2"

    chunk_size_chars: int = 3200
    chunk_overlap_chars: int = 600

    default_top_k: int = 8
    rerank_candidates: int = 20
    hybrid_rrf_k: int = 60

    chroma_collection: str = "ncd_guidelines"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir = Path(settings.data_dir)
    settings.index_dir = Path(settings.index_dir)
    if not settings.data_dir.is_absolute():
        settings.data_dir = _repo_root() / settings.data_dir
    if not settings.index_dir.is_absolute():
        settings.index_dir = _repo_root() / settings.index_dir
    return settings
