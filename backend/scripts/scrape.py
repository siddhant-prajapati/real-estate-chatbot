import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.scraper.darglobal import scrape_darglobal
from app.scraper.wasalt import scrape_wasalt
from app.services.ingest import dump_seed_json, ingest_properties, load_seed_properties


async def run(source: str, persist: bool) -> None:
    properties = []
    errors = []
    if source in {"all", "darglobal"}:
        try:
            properties.extend(await scrape_darglobal())
        except Exception as exc:
            errors.append(f"DarGlobal scrape failed: {exc}")
    if source in {"all", "wasalt"}:
        try:
            properties.extend(await scrape_wasalt())
        except Exception as extra:
            errors.append(f"Wasalt scrape failed: {extra}")

    raw_dir = settings.data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "latest_scrape.json"

    if not properties:
        print("Live scrape returned no records. Using packaged public seed dataset.")
        properties = load_seed_properties()
        dump_seed_json()
    else:
        settings.seed_path.parent.mkdir(parents=True, exist_ok=True)
        settings.seed_path.write_text(
            json.dumps([item.model_dump() for item in properties], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    raw_path.write_text(
        json.dumps([item.model_dump() for item in properties], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if persist:
        result = ingest_properties(properties)
        print(f"Ingested {result}")
    print(f"Saved {len(properties)} properties to {raw_path}")
    for error in errors:
        print(error)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape a limited public subset of DarGlobal and Wasalt listings.")
    parser.add_argument("--source", choices=["all", "darglobal", "wasalt"], default="all")
    parser.add_argument("--no-ingest", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.source, persist=not args.no_ingest))


if __name__ == "__main__":
    main()
