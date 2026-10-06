import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from app.config import settings
from app.models.property import Property
from app.rag.chunking import chunk_text

COLLECTION_NAME = "listings"
SPARSE_KEY = "sparse_embedding"
logger = logging.getLogger(__name__)
_query_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="chroma-query")
_chroma_loaded = False
chromadb = None
K = None
Knn = None
Rrf = None
Schema = None
Search = None
SparseVectorIndexConfig = None
VectorIndexConfig = None
GroupBy = None
MinK = None
dense_embedding_function = None
local_embedding_function = None
sparse_embedding_function = None


def _load_chroma() -> None:
    global _chroma_loaded, chromadb, K, Knn, Rrf, Schema, Search
    global SparseVectorIndexConfig, VectorIndexConfig, GroupBy, MinK
    global dense_embedding_function, local_embedding_function, sparse_embedding_function
    if _chroma_loaded:
        return
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    os.environ.setdefault("CHROMA_TELEMETRY_DISABLED", "1")
    import chromadb as _chromadb
    from chromadb import K as _K, Knn as _Knn, Rrf as _Rrf, Schema as _Schema
    from chromadb import Search as _Search, SparseVectorIndexConfig as _Sparse, VectorIndexConfig as _Vector
    from chromadb.execution.expression.operator import GroupBy as _GroupBy, MinK as _MinK
    from app.rag.embeddings import (
        dense_embedding_function as _dense,
        local_embedding_function as _local,
        sparse_embedding_function as _sparse,
    )

    chromadb = _chromadb
    K = _K
    Knn = _Knn
    Rrf = _Rrf
    Schema = _Schema
    Search = _Search
    SparseVectorIndexConfig = _Sparse
    VectorIndexConfig = _Vector
    GroupBy = _GroupBy
    MinK = _MinK
    dense_embedding_function = _dense
    local_embedding_function = _local
    sparse_embedding_function = _sparse
    _chroma_loaded = True


def is_chroma_ready() -> bool:
    return _chroma_loaded


def _sync_cloud_env() -> None:
    if settings.chroma_api_key:
        os.environ["CHROMA_API_KEY"] = settings.chroma_api_key
    if settings.chroma_tenant:
        os.environ["CHROMA_TENANT"] = settings.chroma_tenant
    if settings.chroma_database:
        os.environ["CHROMA_DATABASE"] = settings.chroma_database


def _cloud_schema() -> Schema:
    _load_chroma()
    schema = Schema()
    schema.create_index(
        config=VectorIndexConfig(
            space="cosine",
            embedding_function=dense_embedding_function(),
        )
    )
    schema.create_index(
        config=SparseVectorIndexConfig(
            source_key=K.DOCUMENT,
            embedding_function=sparse_embedding_function(),
        ),
        key=SPARSE_KEY,
    )
    return schema


def _local_schema() -> Schema:
    _load_chroma()
    schema = Schema()
    schema.create_index(
        config=VectorIndexConfig(
            space="cosine",
            embedding_function=local_embedding_function(),
        )
    )
    return schema


def get_local_client():
    _load_chroma()
    settings.chroma_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(settings.chroma_path))


def get_local_collection():
    return get_local_client().get_or_create_collection(name=COLLECTION_NAME, schema=_local_schema())


def get_client():
    _load_chroma()
    _sync_cloud_env()
    if not settings.chroma_api_key:
        raise RuntimeError(
            "CHROMA_API_KEY is required for Chroma Cloud search. "
            "Copy it from https://www.trychroma.com/siddhantprajapatiaum/aws-us-east-1/real-estate/sdk?tab=env"
        )
    host = settings.chroma_host or "api.trychroma.com"
    return chromadb.CloudClient(
        tenant=settings.chroma_tenant,
        database=settings.chroma_database,
        api_key=settings.chroma_api_key,
        cloud_host=host,
    )


def wait_for_chroma(retries: int = 3, delay_seconds: float = 1.0) -> None:
    get_local_collection()
    if not settings.uses_chroma_cloud:
        return
    last_error = None
    for _ in range(retries):
        try:
            get_client().list_collections()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(delay_seconds)
    logger.warning("Chroma Cloud is not ready, using local DB: %s", last_error)


def get_collection():
    if settings.uses_chroma_cloud:
        return get_client().get_or_create_collection(name=COLLECTION_NAME, schema=_cloud_schema())
    return get_local_collection()


def reset_local_collection() -> None:
    local = get_local_client()
    try:
        local.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    get_local_collection()


def reset_collection() -> None:
    if settings.uses_chroma_cloud:
        client = get_client()
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        get_collection()
    reset_local_collection()


def _scalar_metadata(meta: dict | None) -> dict:
    cleaned: dict = {}
    for key, value in (meta or {}).items():
        if key in {"sparse_embedding", "embedding", "dense_embedding"}:
            continue
        if value is None or isinstance(value, (dict, list)):
            continue
        if isinstance(value, bool):
            cleaned[key] = value
        elif isinstance(value, (int, float, str)):
            cleaned[key] = value
    return cleaned


def _read_cloud_records(batch_size: int = 100) -> tuple[list[str], list[str], list[dict]]:
    collection = get_collection()
    total = collection.count()
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []
    offset = 0
    while offset < max(total, 1):
        kwargs = {
            "include": ["metadatas", "documents"],
            "limit": min(batch_size, max(total - offset, 1)),
        }
        try:
            payload = collection.get(**kwargs, offset=offset)
        except TypeError:
            payload = collection.get(include=["metadatas", "documents"], limit=max(total, 1))
            ids = payload.get("ids") or []
            documents = payload.get("documents") or []
            metadatas = payload.get("metadatas") or []
            break
        batch_ids = payload.get("ids") or []
        if not batch_ids:
            break
        ids.extend(batch_ids)
        documents.extend(payload.get("documents") or [""] * len(batch_ids))
        metadatas.extend(payload.get("metadatas") or [{}] * len(batch_ids))
        offset += len(batch_ids)
        if len(batch_ids) < kwargs["limit"]:
            break
    return ids, documents, metadatas


def seed_local_from_cloud(*, reset: bool = True) -> int:
    if not settings.uses_chroma_cloud:
        raise RuntimeError("CHROMA_API_KEY is required to seed local Chroma from Cloud")
    ids, documents, metadatas = _read_cloud_records()
    if not ids:
        logger.warning("Chroma Cloud collection is empty; local DB was not changed")
        return 0
    usable_ids: list[str] = []
    usable_docs: list[str] = []
    usable_meta: list[dict] = []
    for item_id, document, meta in zip(ids, documents, metadatas):
        if not document:
            continue
        cleaned = _scalar_metadata(meta)
        if "property_id" not in cleaned:
            cleaned["property_id"] = str(item_id).split("::chunk::")[0]
        usable_ids.append(item_id)
        usable_docs.append(document)
        usable_meta.append(cleaned)
    if not usable_ids:
        return 0
    if reset:
        reset_local_collection()
    return _upsert_batches(get_local_collection(), usable_ids, usable_docs, usable_meta)


def _record_metadata(item: Property, chunk_index: int) -> dict:
    return {
        "property_id": item.id,
        "chunk_index": chunk_index,
        "source": item.source or "",
        "title": (item.title or "")[:500],
        "city": item.city or "",
        "country": item.country or "",
        "property_type": item.property_type or "",
        "url": item.url or "",
        "status": item.status or "",
    }


def _chunk_records(properties: list[Property]) -> tuple[list[str], list[str], list[dict]]:
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []
    for item in properties:
        chunks = chunk_text(item.embedding_text())
        for index, chunk in enumerate(chunks):
            ids.append(f"{item.id}::chunk::{index}")
            documents.append(chunk)
            metadatas.append(_record_metadata(item, index))
    return ids, documents, metadatas


def _upsert_batches(collection, ids: list[str], documents: list[str], metadatas: list[dict], batch_size: int = 12) -> int:
    for start in range(0, len(ids), batch_size):
        collection.upsert(
            ids=ids[start : start + batch_size],
            documents=documents[start : start + batch_size],
            metadatas=metadatas[start : start + batch_size],
        )
    return len({meta["property_id"] for meta in metadatas}) if metadatas else 0


def _index_into(collection, properties: list[Property]) -> int:
    if not properties:
        return 0
    ids, documents, metadatas = _chunk_records(properties)
    return _upsert_batches(collection, ids, documents, metadatas)


def index_properties(properties: list[Property], *, cloud: bool = True) -> int:
    local_count = _index_into(get_local_collection(), properties)
    if cloud and settings.uses_chroma_cloud:
        try:
            _index_into(get_collection(), properties)
        except Exception as exc:
            logger.warning("Chroma Cloud index failed, local DB is still available: %s", exc)
    return local_count


def upsert_indexed_properties(properties: list[Property]) -> int:
    return index_properties(properties, cloud=True)


def _rank_from_query(result: dict, n_results: int) -> list[tuple[str, float]]:
    ids = result.get("ids", [[]])[0]
    distances = result.get("distances", [[]])[0] or [None] * len(ids)
    metas = (result.get("metadatas") or [[]])[0] or [{}] * len(ids)
    ranked: list[tuple[str, float]] = []
    seen: set[str] = set()
    for item_id, distance, meta in zip(ids, distances, metas):
        property_id = (meta or {}).get("property_id") or str(item_id).split("::chunk::")[0]
        if not property_id or property_id in seen:
            continue
        seen.add(property_id)
        ranked.append((property_id, float(distance if distance is not None else 1.0)))
        if len(ranked) >= n_results:
            break
    return ranked


def _query_texts(collection, question: str, n_results: int) -> list[tuple[str, float]]:
    if collection.count() == 0:
        return []
    result = collection.query(
        query_texts=[question],
        n_results=min(n_results * 3, max(collection.count(), 1)),
    )
    return _rank_from_query(result, n_results)


def _query_local(question: str, n_results: int) -> list[tuple[str, float]]:
    return _query_texts(get_local_collection(), question, n_results)


def _query_cloud(question: str, n_results: int) -> list[tuple[str, float]]:
    collection = get_collection()
    if collection.count() == 0:
        return []
    candidate_limit = min(max(n_results * 4, 24), 200)
    try:
        dense_rank = Knn(query=question, return_rank=True, limit=candidate_limit, default=1000)
        sparse_rank = Knn(
            query=question,
            key=SPARSE_KEY,
            return_rank=True,
            limit=candidate_limit,
            default=1000,
        )
        hybrid = Rrf(ranks=[dense_rank, sparse_rank], weights=[0.7, 0.3], k=60)
        search = (
            Search()
            .rank(hybrid)
            .group_by(GroupBy(keys=K("property_id"), aggregate=MinK(keys=K.SCORE, k=1)))
            .limit(max(n_results * 3, n_results))
            .select(K.SCORE, "property_id")
        )
        payload = collection.search(search)
        rows = payload.rows()[0] if hasattr(payload, "rows") else []
        ranked: list[tuple[str, float]] = []
        seen: set[str] = set()
        for index, row in enumerate(rows):
            meta = row.get("metadata") or {}
            property_id = (
                meta.get("property_id")
                or row.get("property_id")
                or str(row.get("id") or "").split("::chunk::")[0]
            )
            if not property_id or property_id in seen:
                continue
            seen.add(property_id)
            ranked.append((property_id, index / max(len(rows), 1)))
            if len(ranked) >= n_results:
                break
        if ranked:
            return ranked
    except Exception as exc:
        logger.warning("Hybrid Cloud search failed, using query_texts: %s", exc)
    return _query_texts(collection, question, n_results)


def query_ids(question: str, n_results: int = 8) -> list[tuple[str, float]]:
    timeout = max(float(settings.chroma_cloud_timeout_seconds), 0.1)
    if settings.uses_chroma_cloud:
        cloud_future = _query_pool.submit(_query_cloud, question, n_results)
        try:
            ranked = cloud_future.result(timeout=timeout)
            if ranked:
                return ranked
            logger.warning("Chroma Cloud returned no matches, using local DB")
        except FuturesTimeout:
            logger.warning("Chroma Cloud search exceeded %.1fs, using local DB", timeout)
        except Exception as exc:
            logger.warning("Chroma Cloud search failed, using local DB: %s", exc)

    try:
        return _query_local(question, n_results)
    except Exception as exc:
        logger.warning("Local Chroma search failed: %s", exc)
        return []


def _connection_label() -> tuple[str, str]:
    return "local-files", str(settings.chroma_path)


def collection_preview(limit: int = 25) -> dict:
    mode, host = _connection_label()
    try:
        collection = get_local_collection()
        payload = collection.get(limit=limit, include=["metadatas", "documents"])
        items = []
        ids = payload.get("ids") or []
        metadatas = payload.get("metadatas") or []
        documents = payload.get("documents") or []
        for index, item_id in enumerate(ids):
            meta = metadatas[index] if index < len(metadatas) else {}
            items.append(
                {
                    "id": item_id,
                    "title": (meta or {}).get("title") or item_id,
                    "source": (meta or {}).get("source") or "",
                    "city": (meta or {}).get("city") or "",
                    "url": (meta or {}).get("url") or "",
                    "document": (documents[index][:180] + "...") if index < len(documents) and documents[index] else "",
                }
            )
        cloud_note = ""
        if settings.uses_chroma_cloud:
            cloud_note = f" Cloud fallback timeout={settings.chroma_cloud_timeout_seconds}s."
        return {
            "ok": True,
            "mode": mode,
            "host": host,
            "collection": COLLECTION_NAME,
            "count": collection.count(),
            "items": items,
            "note": cloud_note,
        }
    except Exception as exc:
        return {
            "ok": False,
            "mode": mode,
            "host": host,
            "error": str(exc),
            "items": [],
            "count": 0,
        }


def collection_count() -> int:
    try:
        return get_local_collection().count()
    except Exception:
        return 0


def cloud_collection_count() -> int:
    if not settings.uses_chroma_cloud:
        return 0
    try:
        return get_collection().count()
    except Exception:
        return 0
