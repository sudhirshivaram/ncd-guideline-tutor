from fastapi import APIRouter, HTTPException

from app.core.schemas import FilterFacets
from app.rag.indexing import get_store, index_is_ready


router = APIRouter(prefix="/api", tags=["filters"])


@router.get("/filters", response_model=FilterFacets)
async def filters() -> FilterFacets:
    if not index_is_ready():
        raise HTTPException(
            status_code=503,
            detail="Search index is not built. Run `python -m app.rag.indexing` from backend/.",
        )
    return FilterFacets(**get_store().facets())
