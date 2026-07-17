"""Qdrant vector store (SPEC §4.2): collection `chunks`, dense 1024 cosine, int8 on disk.

Point id == chunk_id (same key as Postgres). Payload carries the fields needed to
filter at query time without a Postgres round-trip: collection_id (permissions), lang,
doc_type, plus document_id/page_start for hydration.
"""

from dataclasses import dataclass

from qdrant_client import QdrantClient, models

from app.core.config import get_settings


@dataclass
class ChunkPoint:
    chunk_id: int
    vector: list[float]
    document_id: int
    collection_id: int
    page_start: int
    lang: str | None
    doc_type: str | None


def get_client() -> QdrantClient:
    return QdrantClient(url=get_settings().qdrant_url, timeout=30)


def ensure_collection(client: QdrantClient) -> None:
    """Create the chunks collection with int8 on-disk quantization if it is missing."""
    settings = get_settings()
    name = settings.qdrant_collection
    if client.collection_exists(name):
        return
    client.create_collection(
        collection_name=name,
        vectors_config=models.VectorParams(
            size=settings.embed_dim, distance=models.Distance.COSINE, on_disk=True
        ),
        quantization_config=models.ScalarQuantization(
            scalar=models.ScalarQuantizationConfig(type=models.ScalarType.INT8, always_ram=False)
        ),
    )
    for field, schema in (
        ("collection_id", models.PayloadSchemaType.INTEGER),
        ("lang", models.PayloadSchemaType.KEYWORD),
        ("doc_type", models.PayloadSchemaType.KEYWORD),
    ):
        client.create_payload_index(collection_name=name, field_name=field, field_schema=schema)


def upsert_chunks(client: QdrantClient, points: list[ChunkPoint]) -> None:
    if not points:
        return
    client.upsert(
        collection_name=get_settings().qdrant_collection,
        points=[
            models.PointStruct(
                id=p.chunk_id,
                vector=p.vector,
                payload={
                    "chunk_id": p.chunk_id,
                    "document_id": p.document_id,
                    "collection_id": p.collection_id,
                    "page_start": p.page_start,
                    "lang": p.lang,
                    "doc_type": p.doc_type,
                },
            )
            for p in points
        ],
    )


def delete_document_points(client: QdrantClient, document_id: int) -> None:
    client.delete(
        collection_name=get_settings().qdrant_collection,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id", match=models.MatchValue(value=document_id)
                    )
                ]
            )
        ),
    )


def _search_filter(
    allowed_collection_ids: list[int] | None, lang: str | None, doc_type: str | None
) -> models.Filter | None:
    must: list[models.Condition] = []
    # None = admin (no collection restriction); [] = user with no collections (matches nothing).
    if allowed_collection_ids is not None:
        must.append(
            models.FieldCondition(
                key="collection_id", match=models.MatchAny(any=allowed_collection_ids)
            )
        )
    if lang:
        must.append(models.FieldCondition(key="lang", match=models.MatchValue(value=lang)))
    if doc_type:
        must.append(models.FieldCondition(key="doc_type", match=models.MatchValue(value=doc_type)))
    return models.Filter(must=must) if must else None


def search(
    client: QdrantClient,
    vector: list[float],
    limit: int,
    allowed_collection_ids: list[int] | None,
    lang: str | None = None,
    doc_type: str | None = None,
) -> list[tuple[int, float]]:
    """Return [(chunk_id, score)] for the nearest points passing the filters."""
    if allowed_collection_ids is not None and not allowed_collection_ids:
        return []  # user has no readable collections
    hits = client.query_points(
        collection_name=get_settings().qdrant_collection,
        query=vector,
        limit=limit,
        query_filter=_search_filter(allowed_collection_ids, lang, doc_type),
        with_payload=False,
    ).points
    return [(int(h.id), float(h.score)) for h in hits]
