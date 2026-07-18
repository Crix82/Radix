"""Hybrid search (SPEC §8): dense (Qdrant) + FTS (Postgres) fused with RRF.

Composable so the endpoint and tests can inject fakes: dense_search and fts_search each
return a ranked list of chunk ids; fuse_and_hydrate turns those into ordered results.
"""

from dataclasses import dataclass

from qdrant_client import QdrantClient
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import BindParameter

from app.services import vectorstore
from app.services.embeddings import Embedder
from app.services.search.fusion import rrf_fuse
from app.services.search.snippet import make_snippet

TOP_PER_RETRIEVER = 24
DEFAULT_LIMIT = 20

# FTS runs on the 'simple' config on both sides — see CHUNK_TSV_EXPRESSION in models/tables.py
# for why (index and query configs must match; per-language stemming is unreliable here).
FTS_REGCONFIG = "simple"


@dataclass
class SearchResult:
    chunk_id: int
    document_id: int
    title: str | None
    lang: str | None
    doc_type: str | None
    rel_path: str
    page: int
    snippet_html: str
    score: float


def fts_search(
    db: Session,
    query: str,
    allowed_collection_ids: list[int] | None,
    lang: str | None = None,
    doc_type: str | None = None,
    limit: int = TOP_PER_RETRIEVER,
) -> list[int]:
    if allowed_collection_ids is not None and not allowed_collection_ids:
        return []

    # Conditions are built dynamically rather than with bare boolean / NULL parameters:
    # pg8000 cannot infer the type of an untyped param (e.g. `:flag OR …`, `:x IS NULL`).
    conditions = [
        "d.deleted_at IS NULL",
        "d.status = 'indexed'",
        "c.tsv @@ websearch_to_tsquery(CAST(:cfg AS regconfig), :q)",
    ]
    params: dict[str, object] = {"cfg": FTS_REGCONFIG, "q": query, "limit": limit}
    binds: list[BindParameter[object]] = []
    if allowed_collection_ids is not None:
        conditions.append("d.collection_id IN :colls")
        params["colls"] = allowed_collection_ids
        binds.append(bindparam("colls", expanding=True))
    if lang:
        conditions.append("c.lang = :lang")
        params["lang"] = lang
    if doc_type:
        conditions.append("d.doc_type = :doc_type")
        params["doc_type"] = doc_type

    sql = text(
        f"""
        SELECT c.id
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE {" AND ".join(conditions)}
        ORDER BY ts_rank(c.tsv, websearch_to_tsquery(CAST(:cfg AS regconfig), :q)) DESC
        LIMIT :limit
        """
    )
    if binds:
        sql = sql.bindparams(*binds)
    return [row[0] for row in db.execute(sql, params)]


def dense_search(
    embedder: Embedder,
    client: QdrantClient,
    query: str,
    allowed_collection_ids: list[int] | None,
    lang: str | None = None,
    doc_type: str | None = None,
    limit: int = TOP_PER_RETRIEVER,
) -> list[int]:
    vector = embedder.embed_query(query)
    hits = vectorstore.search(client, vector, limit, allowed_collection_ids, lang, doc_type)
    return [chunk_id for chunk_id, _ in hits]


def fuse_and_hydrate(
    db: Session,
    dense_ids: list[int],
    fts_ids: list[int],
    query: str,
    limit: int,
    allowed_collection_ids: list[int] | None = None,
) -> list[SearchResult]:
    if allowed_collection_ids is not None and not allowed_collection_ids:
        return []
    fused = rrf_fuse([dense_ids, fts_ids])[:limit]
    if not fused:
        return []

    params: dict[str, object] = {"ids": [cid for cid, _ in fused]}
    binds: list[BindParameter[object]] = [bindparam("ids", expanding=True)]
    # Enforce collection permissions again at hydration: a chunk is returned only if its
    # document is live, indexed, and (for non-admins) in a readable collection (SPEC §6).
    coll_clause = ""
    if allowed_collection_ids is not None:
        coll_clause = "AND d.collection_id IN :colls"
        params["colls"] = allowed_collection_ids
        binds.append(bindparam("colls", expanding=True))
    hydrate_sql = text(
        f"""
        SELECT c.id, c.document_id, c.page_start, c.text,
               d.title, d.lang, d.doc_type, d.rel_path
        FROM chunks c JOIN documents d ON d.id = c.document_id
        WHERE c.id IN :ids
          AND d.deleted_at IS NULL
          AND d.status = 'indexed'
          {coll_clause}
        """
    ).bindparams(*binds)
    rows = db.execute(hydrate_sql, params).all()
    by_id = {row[0]: row for row in rows}

    results: list[SearchResult] = []
    for chunk_id, score in fused:
        row = by_id.get(chunk_id)
        if row is None:  # chunk vanished (reindex/delete race) — skip it
            continue
        results.append(
            SearchResult(
                chunk_id=row[0],
                document_id=row[1],
                page=row[2],
                snippet_html=make_snippet(row[3], query),
                title=row[4],
                lang=row[5],
                doc_type=row[6],
                rel_path=row[7],
                score=round(score, 6),
            )
        )
    return results


def hybrid_search(
    db: Session,
    embedder: Embedder,
    client: QdrantClient,
    query: str,
    allowed_collection_ids: list[int] | None,
    lang: str | None = None,
    doc_type: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[SearchResult]:
    dense_ids = dense_search(embedder, client, query, allowed_collection_ids, lang, doc_type)
    fts_ids = fts_search(db, query, allowed_collection_ids, lang, doc_type)
    return fuse_and_hydrate(db, dense_ids, fts_ids, query, limit, allowed_collection_ids)
