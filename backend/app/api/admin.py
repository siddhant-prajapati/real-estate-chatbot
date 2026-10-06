from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import settings
from app.scraper.darglobal import scrape_darglobal
from app.scraper.wasalt import scrape_wasalt
from app.services.ingest import ingest_properties, load_seed_properties

router = APIRouter()


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not settings.admin_token:
        raise HTTPException(status_code=403, detail="Admin scraping is disabled")
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")


@router.post("/admin/scrape")
async def scrape(authorized: None = Depends(require_admin)) -> dict:
    darglobal = []
    wasalt = []
    errors = []
    try:
        darglobal = await scrape_darglobal()
    except Exception as exc:
        errors.append(f"DarGlobal: {exc}")
    try:
        wasalt = await scrape_wasalt()
    except Exception as extra:
        errors.append(f"Wasalt: {extra}")

    properties = darglobal + wasalt
    if not properties:
        properties = load_seed_properties()
        errors.append("Live scrape returned no records; packaged seed dataset was loaded instead.")
    result = ingest_properties(properties)
    return {
        "ingested": result,
        "darglobal": len(darglobal),
        "wasalt": len(wasalt),
        "errors": errors,
    }
