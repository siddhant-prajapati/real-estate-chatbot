import json
import threading
from pathlib import Path

from app.config import settings
from app.db.sqlite import count_properties, list_properties, replace_all
from app.models.property import Property


def dump_seed_json(path: Path | None = None) -> Path:
    from app.data.seed_catalog import all_seed_properties

    target = path or settings.seed_path
    target.parent.mkdir(parents=True, exist_ok=True)
    properties = all_seed_properties()
    target.write_text(
        json.dumps([item.model_dump() for item in properties], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return target


def load_json_properties(path: Path) -> list[Property]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Property.model_validate(item) for item in payload]


def load_seed_properties() -> list[Property]:
    from app.data.seed_catalog import all_seed_properties

    if settings.seed_path.exists():
        return load_json_properties(settings.seed_path)
    properties = all_seed_properties()
    dump_seed_json()
    return properties


def ingest_properties(properties: list[Property]) -> dict:
    from app.rag.vector_store import cloud_collection_count, index_properties

    sqlite_count = replace_all(properties)
    fill_cloud = settings.uses_chroma_cloud and cloud_collection_count() == 0
    vector_count = index_properties(properties, cloud=fill_cloud)
    return {"sqlite": sqlite_count, "chroma": vector_count}


_ready_lock = threading.Lock()
_ready_result: dict | None = None


def status_snapshot() -> dict:
    sqlite_count = count_properties()
    chroma_count = 0
    try:
        from app.rag.vector_store import collection_count, is_chroma_ready

        if is_chroma_ready():
            chroma_count = collection_count()
    except Exception:
        chroma_count = 0
    result = _ready_result
    return {
        "ready": result is not None or sqlite_count > 0,
        "sqlite": sqlite_count if result is None else int(result.get("sqlite") or sqlite_count),
        "chroma": chroma_count,
    }


def ensure_ready() -> dict:
    """Load SQLite from seed only. Chroma is imported on first search."""
    global _ready_result
    with _ready_lock:
        if _ready_result is not None:
            return _ready_result
        sqlite_count = count_properties()
        if sqlite_count == 0:
            sqlite_count = replace_all(load_seed_properties())
        _ready_result = {"sqlite": sqlite_count, "chroma": 0}
        return _ready_result
