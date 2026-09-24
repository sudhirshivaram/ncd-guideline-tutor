from typing import Literal, Optional

from pydantic import BaseModel, Field


ProviderName = Literal["openai", "gemini", "anthropic"]


class MetadataFilters(BaseModel):
    ncd_type: Optional[str] = None
    doc_id: Optional[str] = None
    year: Optional[int] = None
    doc_type: Optional[str] = None
    source_family: Optional[str] = None


class ChatSettings(BaseModel):
    model: str = "gpt-4o-mini"
    temperature: float = Field(default=0.2, ge=0.0, le=1.5)
    top_k: int = Field(default=8, ge=1, le=20)
    hybrid: bool = True
    rerank: bool = True
    filters: MetadataFilters = Field(default_factory=MetadataFilters)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    settings: ChatSettings = Field(default_factory=ChatSettings)


class Citation(BaseModel):
    index: int
    chunk_id: str
    title: str
    short_title: str
    doc_id: str
    page: int
    year: int
    ncd_types: str
    doc_type: str
    section: str
    snippet: str
    score: float = 0.0


class FilterFacets(BaseModel):
    ncd_types: list[str]
    documents: list[dict]
    years: list[int]
    doc_types: list[str]
    source_families: list[str]


class EvalRunRequest(BaseModel):
    provider: ProviderName = "openai"
    model: str = "gpt-4o-mini"
    include_generation: bool = False
    max_cases: Optional[int] = None
