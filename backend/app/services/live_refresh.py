import json
import re
import time
from dataclasses import dataclass

from app.config import settings
from app.db.sqlite import list_properties, upsert_properties
from app.models.property import Property
from app.rag.retriever import parse_filters
from app.scraper.darglobal import scrape_darglobal
from app.scraper.wasalt import scrape_wasalt

STOPWORDS = {
    "show", "find", "tell", "about", "which", "what", "have", "from", "with",
    "under", "properties", "property", "listings", "listing", "give", "source",
    "sources", "links", "please", "want", "need", "some", "that", "this",
    "available", "bedroom", "bedrooms", "million",
}


@dataclass
class LiveScrapeResult:
    attempted: bool
    new_listings: int = 0
    note: str | None = None


def _cooldown_path():
    return settings.data_dir / "last_live_scrape.json"


def _in_cooldown() -> bool:
    path = _cooldown_path()
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        elapsed = time.time() - float(payload.get("ts", 0))
        return elapsed < settings.live_scrape_cooldown_seconds
    except Exception:
        return False


def _mark_scraped() -> None:
    _cooldown_path().write_text(json.dumps({"ts": time.time()}), encoding="utf-8")


def distinctive_terms(question: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", question.lower())
        if len(token) > 4 and token not in STOPWORDS
    ]


def needs_live_scrape(question: str, retrieved: list[Property]) -> bool:
    if not settings.enable_live_scrape:
        return False
    catalog = list_properties()
    haystack = " ".join(item.embedding_text() for item in catalog).lower()
    filters = parse_filters(question)
    missing = [token for token in distinctive_terms(question) if token not in haystack]

    if filters.get("city"):
        city = filters["city"]
        city_hits = [
            item
            for item in catalog
            if city in f"{item.city or ''} {item.location or ''}".lower()
        ]
        if not city_hits:
            return True

    if re.search(r"\b(tell me about|what is|details of|compare)\b", question.lower()) and missing:
        return True
    if missing and any(len(token) >= 6 for token in missing):
        return True
    if not retrieved:
        return True
    return False


def _is_new(item: Property, existing: list[Property]) -> bool:
    keys = {(row.source.lower(), row.title.lower(), row.url) for row in existing}
    return (item.source.lower(), item.title.lower(), item.url) not in keys and all(row.id != item.id for row in existing)


async def refresh_from_websites(question: str) -> LiveScrapeResult:
    if _in_cooldown():
        return LiveScrapeResult(
            attempted=False,
            note="Live websites were checked recently, so I used the stored database this time.",
        )

    existing = list_properties()
    scraped: list[Property] = []
    errors: list[str] = []
    limit = settings.live_scrape_max_per_source
    try:
        scraped.extend(await scrape_darglobal(max_properties=limit, query=question))
    except Exception as exc:
        errors.append(f"DarGlobal: {exc}")
    try:
        scraped.extend(await scrape_wasalt(max_properties=limit, query=question))
    except Exception as extra:
        errors.append(f"Wasalt: {extra}")

    _mark_scraped()
    newcomers = [item for item in scraped if _is_new(item, existing)]
    if newcomers:
        from app.rag.vector_store import upsert_indexed_properties

        upsert_properties(newcomers)
        upsert_indexed_properties(newcomers)
        return LiveScrapeResult(
            attempted=True,
            new_listings=len(newcomers),
            note=f"I checked DarGlobal and Wasalt and added {len(newcomers)} new listing(s) to the database.",
        )

    if scraped:
        return LiveScrapeResult(
            attempted=True,
            note="I checked the live websites, but did not find additional listings beyond what is already stored.",
        )

    detail = "; ".join(errors) if errors else "the sites blocked or did not return usable public HTML"
    return LiveScrapeResult(
        attempted=True,
        note=(
            "I tried to scrape DarGlobal and Wasalt for missing data, but could not collect new listings "
            f"({detail}). I answered from the stored database only."
        ),
    )
