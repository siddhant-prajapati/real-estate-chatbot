"""Copy Chroma Cloud listing chunks into the local Chroma DB."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.rag.vector_store import (
    cloud_collection_count,
    collection_count,
    index_properties,
    seed_local_from_cloud,
    wait_for_chroma,
)
from app.services.ingest import load_seed_properties


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed local Chroma from Chroma Cloud")
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Upsert into local DB without deleting the current local collection first",
    )
    args = parser.parse_args()

    wait_for_chroma()
    if settings.uses_chroma_cloud:
        count = seed_local_from_cloud(reset=not args.keep_existing)
        if count:
            print(f"Seeded {count} properties from Chroma Cloud into {settings.chroma_path}")
            print(f"Local records: {collection_count()}")
            print(f"Cloud records: {cloud_collection_count()}")
            return
        print("Chroma Cloud had no documents. Indexing seed listings into local DB instead.")

    count = index_properties(load_seed_properties(), cloud=False)
    print(f"Indexed {count} seed properties into {settings.chroma_path}")
    print(f"Local records: {collection_count()}")


if __name__ == "__main__":
    main()
