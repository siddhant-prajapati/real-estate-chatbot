import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.ingest import dump_seed_json, ensure_ready


def main() -> None:
    seed_path = dump_seed_json()
    result = ensure_ready()
    print(f"Seed JSON: {seed_path}")
    print(f"Indexed {result}")


if __name__ == "__main__":
    main()
