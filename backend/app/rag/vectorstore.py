"""Zilliz Cloud / Milvus vector store wrapper.

Collection schema (created on first use):
  pk (varchar)        "<gfile_id>_<chunk_idx>"
  vector (float, 384) dense embedding
  sparse (sparse)     BM25 sparse vector, auto-generated from `text` (hybrid search)
  text (varchar)      chunk text
  doc_id, doc_name, drive_id, agency, page_start, page_end, year  (metadata)

Hybrid dense+BM25 search with RRF fusion; falls back to dense-only if the
server doesn't support BM25 functions.
"""
import logging

from ..config import get_settings

settings = get_settings()
log = logging.getLogger(__name__)

_client = None
_hybrid_ok: bool | None = None


def get_client():
    global _client
    if _client is None:
        from pymilvus import MilvusClient
        if not settings.zilliz_uri:
            raise RuntimeError("ZILLIZ_URI not configured")
        _client = MilvusClient(uri=settings.zilliz_uri, token=settings.zilliz_token)
    return _client


def ensure_collection() -> None:
    """Create the collection with BM25 hybrid schema if it doesn't exist."""
    client = get_client()
    name = settings.collection_name
    if client.has_collection(name):
        return

    from pymilvus import DataType, Function, FunctionType

    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("pk", DataType.VARCHAR, is_primary=True, max_length=128)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=settings.embedding_dim)
    schema.add_field("text", DataType.VARCHAR, max_length=16384, enable_analyzer=True)
    schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
    schema.add_field("doc_id", DataType.VARCHAR, max_length=128)
    schema.add_field("doc_name", DataType.VARCHAR, max_length=512)
    schema.add_field("drive_id", DataType.INT64)
    schema.add_field("agency", DataType.VARCHAR, max_length=64)
    schema.add_field("page_start", DataType.INT64)
    schema.add_field("page_end", DataType.INT64)
    schema.add_field("year", DataType.INT64)

    schema.add_function(Function(
        name="bm25", function_type=FunctionType.BM25,
        input_field_names=["text"], output_field_names=["sparse"],
    ))

    index_params = client.prepare_index_params()
    index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")
    index_params.add_index(field_name="sparse", index_type="SPARSE_INVERTED_INDEX", metric_type="BM25")

    client.create_collection(name, schema=schema, index_params=index_params)
    log.info("Created collection %s", name)


def upsert_chunks(rows: list[dict]) -> int:
    """rows: dicts with pk, vector, text, doc_id, doc_name, drive_id, agency,
    page_start, page_end, year. `sparse` is generated server-side."""
    client = get_client()
    ensure_collection()
    total = 0
    for i in range(0, len(rows), 500):
        batch = rows[i:i + 500]
        client.upsert(collection_name=settings.collection_name, data=batch)
        total += len(batch)
    return total


def delete_document(doc_id: str) -> None:
    client = get_client()
    if client.has_collection(settings.collection_name):
        client.delete(collection_name=settings.collection_name, filter=f'doc_id == "{doc_id}"')


OUTPUT_FIELDS = ["text", "doc_id", "doc_name", "agency", "page_start", "page_end", "year"]


def search(query_text: str, query_vector: list[float], top_k: int = 8,
           agency: str = "") -> list[dict]:
    """Hybrid dense+BM25 search with RRF fusion; dense-only fallback."""
    global _hybrid_ok
    client = get_client()
    flt = f'agency == "{agency}"' if agency else ""

    if _hybrid_ok is not False:
        try:
            from pymilvus import AnnSearchRequest, RRFRanker
            dense = AnnSearchRequest(data=[query_vector], anns_field="vector",
                                     param={"metric_type": "COSINE"}, limit=top_k * 2,
                                     expr=flt or None)
            sparse = AnnSearchRequest(data=[query_text], anns_field="sparse",
                                      param={"metric_type": "BM25"}, limit=top_k * 2,
                                      expr=flt or None)
            res = client.hybrid_search(
                collection_name=settings.collection_name,
                reqs=[dense, sparse], ranker=RRFRanker(60), limit=top_k,
                output_fields=OUTPUT_FIELDS,
            )
            _hybrid_ok = True
            return _to_hits(res)
        except Exception as e:  # noqa: BLE001 — fall back to dense on any hybrid failure
            log.warning("Hybrid search unavailable (%s); falling back to dense-only", e)
            _hybrid_ok = False

    res = client.search(
        collection_name=settings.collection_name, data=[query_vector],
        anns_field="vector", limit=top_k, filter=flt,
        search_params={"metric_type": "COSINE"}, output_fields=OUTPUT_FIELDS,
    )
    return _to_hits(res)


def _to_hits(res) -> list[dict]:
    hits = []
    for hit in res[0]:
        ent = hit.get("entity", hit)
        hits.append({
            "score": float(hit.get("distance", hit.get("score", 0.0))),
            "text": ent.get("text", ""),
            "doc_id": ent.get("doc_id", ""),
            "doc_name": ent.get("doc_name", ""),
            "agency": ent.get("agency", ""),
            "page_start": ent.get("page_start", 0),
            "page_end": ent.get("page_end", 0),
            "year": ent.get("year", 0),
        })
    return hits


def collection_stats() -> dict:
    try:
        client = get_client()
        if not client.has_collection(settings.collection_name):
            return {"row_count": 0, "status": "no collection"}
        stats = client.get_collection_stats(settings.collection_name)
        return {"row_count": int(stats.get("row_count", 0)), "status": "ok"}
    except Exception as e:  # noqa: BLE001
        return {"row_count": 0, "status": f"unavailable: {e}"}
