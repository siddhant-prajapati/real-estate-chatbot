"""Copy SQLite/seed listings into Chroma Cloud with Qwen + Splade embeddings."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.db.sqlite import count_properties, list_properties
from app.rag.vector_store import cloud_collection_count, collection_count, index_properties, reset_collection, wait_for_chroma
from app.services.ingest import load_seed_properties


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate listings into Chroma Cloud")
    parser.add_argument("--reset", action="store_true", help="Delete the Cloud collection before upserting")
    args = parser.parse_args()

    if not settings.chroma_api_key:
        raise SystemExit(
            "CHROMA_API_KEY is missing. Copy it from "
            "https://www.trychroma.com/siddhantprajapatiaum/aws-us-east-1/real-estate/sdk?tab=env "
            "into the project .env file."
        )

    wait_for_chroma()
    properties = list_properties() or load_seed_properties()
    if args.reset:
        reset_collection()
        print("Reset Cloud collection `listings`.")
    count = index_properties(properties)
    print(f"SQLite rows: {count_properties()}")
    print(f"Indexed properties: {count}")
    print(f"Local Chroma records: {collection_count()}")
    print(f"Chroma Cloud records: {cloud_collection_count()}")
    print(f"Tenant={settings.chroma_tenant} database={settings.chroma_database}")


if __name__ == "__main__":
    main()
