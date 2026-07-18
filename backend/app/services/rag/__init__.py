"""RAG orchestration (SPEC §8): retrieve → refuse-or-answer → stream → cite.

Retrieval reuses the M3 hybrid primitives (dense + FTS + RRF). Refusal is decided on the
best *dense cosine* (a semantic-relevance signal), not the RRF score — RRF is rank-based
and does not distinguish an on-corpus hit from an off-corpus one (see ADR 0005).
"""

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import QdrantClient
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.services import vectorstore
from app.services.chunking import estimate_tokens
from app.services.embeddings import Embedder
from app.services.llm.base import LLMProvider
from app.services.rag.prompts import REFUSAL_PHRASE, SYSTEM_PROMPT
from app.services.search import TOP_PER_RETRIEVER, fts_search
from app.services.search.fusion import rrf_fuse

TOP_CONTEXT = 8
MAX_CONTEXT_TOKENS = 3500
# When a chunk is retrieved, also pull this many chunks on each side of it within the same
# document. Retrieval matches a single chunk, but a fact can straddle a chunk boundary (an
# invoice's payee header and its total line land in adjacent chunks); the neighbours carry the
# rest of the fact into the LLM context. See _expand_with_neighbors.
NEIGHBOR_RADIUS = 1
_CITATION_RE = re.compile(r"\[(\d{1,2})\]")


def _as_dict(value: Any) -> dict[str, Any] | None:
    """Normalize a JSONB column: pg8000 returns a dict; raw reads on SQLite give a str."""
    if isinstance(value, str):
        parsed: dict[str, Any] = json.loads(value)
        return parsed
    return value if value is None else dict(value)


@dataclass
class ContextChunk:
    n: int
    chunk_id: int
    document_id: int
    title: str | None
    lang: str | None
    page: int
    text: str
    bboxes: dict[str, Any] | None


@dataclass
class Retrieval:
    chunks: list[ContextChunk]
    max_dense_score: float


@dataclass
class Citation:
    n: int
    chunk_id: int
    document_id: int
    title: str | None
    lang: str | None
    page: int
    bboxes: dict[str, Any] | None

    @classmethod
    def from_chunk(cls, c: "ContextChunk") -> "Citation":
        return cls(
            n=c.n,
            chunk_id=c.chunk_id,
            document_id=c.document_id,
            title=c.title,
            lang=c.lang,
            page=c.page,
            bboxes=c.bboxes,
        )


@dataclass
class ChatResult:
    """Terminal payload of a chat turn (the SSE `final` event)."""

    answer_md: str
    citations: list[Citation] = field(default_factory=list)
    refusal: bool = False


def _expand_with_neighbors(
    db: Session, ordered_ids: list[int], radius: int = NEIGHBOR_RADIUS
) -> list[int]:
    """Grow the selected chunk ids with their same-document neighbours (adjacent in chunk-id
    order — ids are monotonic within a document, see worker/jobs.py). Fusion order is kept:
    each anchor is emitted with its window of neighbours, de-duplicated. Neighbours share the
    anchor's document (hence its collection), so this surfaces no chunk the caller wasn't
    already permitted to retrieve."""
    if radius <= 0 or not ordered_ids:
        return ordered_ids
    doc_of: dict[int, int] = {
        cid: did
        for cid, did in db.execute(
            text("SELECT id, document_id FROM chunks WHERE id IN :ids").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": ordered_ids},
        )
    }
    doc_ids = list(dict.fromkeys(doc_of.values()))
    if not doc_ids:
        return ordered_ids
    order: dict[int, list[int]] = {}
    for cid, did in db.execute(
        text(
            "SELECT id, document_id FROM chunks WHERE document_id IN :docs ORDER BY document_id, id"
        ).bindparams(bindparam("docs", expanding=True)),
        {"docs": doc_ids},
    ):
        order.setdefault(did, []).append(cid)
    position = {did: {cid: i for i, cid in enumerate(ids)} for did, ids in order.items()}

    expanded: list[int] = []
    seen: set[int] = set()
    for anchor in ordered_ids:
        did = doc_of.get(anchor)
        if did is None:
            window = [anchor]
        else:
            i = position[did][anchor]
            window = order[did][max(0, i - radius) : i + radius + 1]
        for cid in window:
            if cid not in seen:
                seen.add(cid)
                expanded.append(cid)
    return expanded


def retrieve(
    db: Session,
    embedder: Embedder,
    client: QdrantClient,
    query: str,
    allowed_collection_ids: list[int] | None,
    lang: str | None = None,
    doc_type: str | None = None,
) -> Retrieval:
    if allowed_collection_ids is not None and not allowed_collection_ids:
        return Retrieval(chunks=[], max_dense_score=0.0)

    dense = vectorstore.search(
        client,
        embedder.embed_query(query),
        TOP_PER_RETRIEVER,
        allowed_collection_ids,
        lang,
        doc_type,
    )
    max_dense = dense[0][1] if dense else 0.0
    fused = rrf_fuse(
        [[cid for cid, _ in dense], fts_search(db, query, allowed_collection_ids, lang, doc_type)]
    )
    fused_ids = [cid for cid, _ in fused[:TOP_CONTEXT]]
    if not fused_ids:
        return Retrieval(chunks=[], max_dense_score=max_dense)

    context_ids = _expand_with_neighbors(db, fused_ids)
    rows = db.execute(
        text(
            """
            SELECT c.id, c.document_id, c.page_start, c.text, c.bboxes, d.title, d.lang
            FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.id IN :ids AND d.deleted_at IS NULL AND d.status = 'indexed'
            """
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": context_ids},
    ).all()
    by_id = {row[0]: row for row in rows}

    chunks: list[ContextChunk] = []
    tokens = 0
    for chunk_id in context_ids:
        row = by_id.get(chunk_id)
        if row is None:
            continue
        tokens += estimate_tokens(row[3])
        if chunks and tokens > MAX_CONTEXT_TOKENS:  # keep at least one chunk
            break
        chunks.append(
            ContextChunk(
                n=len(chunks) + 1,
                chunk_id=row[0],
                document_id=row[1],
                page=row[2],
                text=row[3],
                bboxes=_as_dict(row[4]),
                title=row[5],
                lang=row[6],
            )
        )
    return Retrieval(chunks=chunks, max_dense_score=max_dense)


def build_messages(
    context: list[ContextChunk], history: list[dict[str, str]], question: str
) -> list[dict[str, str]]:
    block = "\n\n".join(f"[{c.n}] ({c.title or '—'}, pag. {c.page})\n{c.text}" for c in context)
    augmented = f"Contesto:\n{block}\n\nDomanda: {question}"
    prior = [m for m in history if m.get("role") in ("user", "assistant")][:-1]
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *prior,
        {"role": "user", "content": augmented},
    ]


def parse_citations(answer: str, context: list[ContextChunk]) -> list[Citation]:
    by_n = {c.n: c for c in context}
    seen: set[int] = set()
    citations: list[Citation] = []
    for match in _CITATION_RE.findall(answer):
        n = int(match)
        if n in by_n and n not in seen:
            seen.add(n)
            citations.append(Citation.from_chunk(by_n[n]))
    # If the model didn't cite, attach the sources actually put in the context (SPEC §8).
    if not citations:
        citations = [Citation.from_chunk(c) for c in context]
    return citations


def answer_stream(
    db: Session,
    embedder: Embedder,
    client: QdrantClient,
    provider: LLMProvider,
    messages: list[dict[str, str]],
    allowed_collection_ids: list[int] | None,
    refusal_threshold: float,
    lang: str | None = None,
    doc_type: str | None = None,
) -> Iterator[tuple[str, Any]]:
    """Yield ('token', str) events then one ('final', ChatResult) event."""
    question = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
    ).strip()
    retrieval = retrieve(db, embedder, client, question, allowed_collection_ids, lang, doc_type)

    if not retrieval.chunks or retrieval.max_dense_score < refusal_threshold:
        yield "final", ChatResult(answer_md=REFUSAL_PHRASE, citations=[], refusal=True)
        return

    llm_messages = build_messages(retrieval.chunks, messages, question)
    buffer = ""
    for token in provider.complete(llm_messages, stream=True):
        buffer += token
        yield "token", token

    answer = buffer.strip() or REFUSAL_PHRASE
    yield "final", ChatResult(answer_md=answer, citations=parse_citations(answer, retrieval.chunks))
