from fastapi import APIRouter

from app.config import settings
from app.models.property import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    from app.services.ingest import status_snapshot

    snap = status_snapshot()
    if snap["chroma"] > 0:
        vector = "ready"
    elif snap["ready"]:
        vector = "sqlite-ready, chroma deferred"
    else:
        vector = "starting"
    if settings.uses_chroma_cloud:
        vector = (
            f"{vector} (chroma-cloud/{settings.chroma_database}, "
            f"{settings.chroma_cloud_timeout_seconds:g}s timeout)"
        )
    else:
        vector = f"{vector} (local {settings.chroma_path})"
    return HealthResponse(
        status="UP",
        properties=snap["sqlite"],
        vector_store=vector,
        llm="configured" if settings.openrouter_api_key else "missing_api_key",
        live_scrape="enabled" if settings.enable_live_scrape else "disabled",
    )
