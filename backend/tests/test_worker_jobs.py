import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Chunk, Collection, Document, DocumentStatus, Source, SourceType
from app.services.parsing.base import BBox, ParsedBlock, ParsedDocument
from app.services.parsing.textlayer import TextLayerReport
from tests.conftest import create_sqlite_chunks_table
from worker import jobs


@pytest.fixture
def worker_db(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Session:
    """Point the worker's SessionLocal at the test database."""
    factory = sessionmaker(bind=db_session.get_bind(), autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(jobs, "SessionLocal", factory)
    return db_session


def _seed_document(db: Session, doc_status: DocumentStatus) -> Document:
    collection = Collection(name="Test")
    db.add(collection)
    db.flush()
    source = Source(type=SourceType.local, path="/mnt/x", collection_id=collection.id)
    db.add(source)
    db.flush()
    doc = Document(
        source_id=source.id,
        collection_id=collection.id,
        rel_path="a.pdf",
        content_hash="0" * 64,
        status=doc_status,
    )
    db.add(doc)
    db.commit()
    return doc


class _FakeParser:
    """Stands in for DoclingParser: records the ocr flag, returns canned blocks."""

    def __init__(self, blocks: list[ParsedBlock], lang: str = "it", pages: int = 2) -> None:
        self.blocks = blocks
        self.lang = lang
        self.pages = pages
        self.last_ocr: bool | None = None

    def parse(self, path: str, ocr: bool) -> ParsedDocument:
        self.last_ocr = ocr
        return ParsedDocument(
            lang=self.lang, page_count=self.pages, blocks=self.blocks, used_ocr=ocr
        )


@pytest.fixture
def parse_env(worker_db: Session, monkeypatch: pytest.MonkeyPatch):
    """Wire parse_document to a fake parser and a controllable text-layer probe."""
    create_sqlite_chunks_table(worker_db.get_bind())

    enqueued: list[int] = []
    monkeypatch.setattr(jobs, "enqueue_embed_chunks", enqueued.append)

    def install(parser: _FakeParser, needs_ocr: bool = False, page_count: int = 2) -> list[int]:
        monkeypatch.setattr(jobs, "get_parser", lambda: parser)
        monkeypatch.setattr(
            jobs,
            "probe_text_layer",
            lambda path: TextLayerReport(page_count=page_count, total_chars=0, needs_ocr=needs_ocr),
        )
        return enqueued

    return install


def test_parse_document_born_digital_writes_chunks(worker_db: Session, parse_env) -> None:
    parser = _FakeParser(
        blocks=[
            ParsedBlock("Sezione 1", page=1, heading_path=("Sezione 1",), is_heading=True),
            ParsedBlock(
                "Contenuto tecnico.",
                page=1,
                heading_path=("Sezione 1",),
                bbox=BBox(0.1, 0.1, 0.9, 0.2),
            ),
        ],
        lang="it",
        pages=2,
    )
    enqueued = parse_env(parser, needs_ocr=False)
    doc = _seed_document(worker_db, DocumentStatus.queued)

    jobs.parse_document(doc.id)

    worker_db.refresh(doc)
    assert doc.status == DocumentStatus.chunking  # embedding runs as the next stage
    assert doc.lang == "it"
    assert doc.pages == 2
    assert parser.last_ocr is False
    n_chunks = worker_db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id)
    )
    assert n_chunks >= 1
    assert enqueued == [doc.id]  # embed_chunks queued after chunking


def test_parse_document_uses_ocr_branch_when_text_layer_poor(worker_db: Session, parse_env) -> None:
    parser = _FakeParser(blocks=[ParsedBlock("Testo OCR", page=1, heading_path=("H",))])
    parse_env(parser, needs_ocr=True)
    doc = _seed_document(worker_db, DocumentStatus.queued)

    jobs.parse_document(doc.id)

    assert parser.last_ocr is True


def test_parse_document_reprocess_replaces_chunks(worker_db: Session, parse_env) -> None:
    parser = _FakeParser(blocks=[ParsedBlock("uno", page=1, heading_path=("H",))])
    parse_env(parser, needs_ocr=False)
    doc = _seed_document(worker_db, DocumentStatus.queued)
    jobs.parse_document(doc.id)
    first = worker_db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id)
    )

    doc.status = DocumentStatus.queued  # simulate reindex
    worker_db.commit()
    jobs.parse_document(doc.id)
    second = worker_db.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == doc.id)
    )
    assert first == second == 1  # replaced, not duplicated


def test_parse_document_failure_sets_actionable_error(
    worker_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_sqlite_chunks_table(worker_db.get_bind())

    class Boom:
        def parse(self, path: str, ocr: bool) -> ParsedDocument:
            raise RuntimeError("PDFium: file is password protected")

    monkeypatch.setattr(jobs, "get_parser", lambda: Boom())
    monkeypatch.setattr(
        jobs,
        "probe_text_layer",
        lambda path: TextLayerReport(page_count=1, total_chars=0, needs_ocr=False),
    )
    doc = _seed_document(worker_db, DocumentStatus.queued)

    jobs.parse_document(doc.id)

    worker_db.refresh(doc)
    assert doc.status == DocumentStatus.error
    assert doc.error_msg == "PDF protetto da password"


def test_parse_document_ignores_non_reprocessable_and_missing(worker_db: Session) -> None:
    doc = _seed_document(worker_db, DocumentStatus.indexed)

    jobs.parse_document(doc.id)
    jobs.parse_document(99999)  # missing id: no-op, no crash

    worker_db.refresh(doc)
    assert doc.status == DocumentStatus.indexed


def test_sync_source_job_marks_bad_path_as_error(worker_db: Session) -> None:
    collection = Collection(name="C2")
    worker_db.add(collection)
    worker_db.flush()
    source = Source(
        type=SourceType.local, path="/nonexistent", collection_id=collection.id, enabled=True
    )
    worker_db.add(source)
    worker_db.commit()

    jobs.sync_source(source.id)

    worker_db.refresh(source)
    assert source.status == "error"


def test_sync_source_job_skips_disabled_sources(worker_db: Session) -> None:
    collection = Collection(name="C3")
    worker_db.add(collection)
    worker_db.flush()
    source = Source(
        type=SourceType.local, path="/nonexistent", collection_id=collection.id, enabled=False
    )
    worker_db.add(source)
    worker_db.commit()

    jobs.sync_source(source.id)

    worker_db.refresh(source)
    assert source.status is None  # untouched


class _FakeVectorstore:
    """Captures the Qdrant calls embed_chunks would make."""

    def __init__(self) -> None:
        self.upserted: list = []
        self.deleted: list[int] = []
        self.ensured = False
        self.ChunkPoint = jobs.vectorstore.ChunkPoint

    def get_client(self) -> object:
        return object()

    def ensure_collection(self, client: object) -> None:
        self.ensured = True

    def delete_document_points(self, client: object, document_id: int) -> None:
        self.deleted.append(document_id)

    def upsert_chunks(self, client: object, points: list) -> None:
        self.upserted.extend(points)


class _FakeEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] * 3 for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.0, 0.0, 0.0]


def _seed_chunked_document(db: Session, n_chunks: int = 2) -> Document:
    collection = Collection(name="EC")
    db.add(collection)
    db.flush()
    source = Source(type=SourceType.local, path="/x", collection_id=collection.id)
    db.add(source)
    db.flush()
    doc = Document(
        source_id=source.id,
        collection_id=collection.id,
        rel_path="d.pdf",
        content_hash="0" * 64,
        status=DocumentStatus.chunking,
        lang="it",
    )
    db.add(doc)
    db.flush()
    for i in range(n_chunks):
        db.add(
            Chunk(
                document_id=doc.id, page_start=i + 1, page_end=i + 1, text=f"chunk {i}", lang="it"
            )
        )
    db.commit()
    return doc


@pytest.fixture
def embed_env(worker_db: Session, monkeypatch: pytest.MonkeyPatch) -> _FakeVectorstore:
    create_sqlite_chunks_table(worker_db.get_bind())
    fake_vs = _FakeVectorstore()
    monkeypatch.setattr(jobs, "vectorstore", fake_vs)
    monkeypatch.setattr(jobs, "get_embedder", lambda: _FakeEmbedder())
    return fake_vs


def test_embed_chunks_indexes_and_upserts(worker_db: Session, embed_env: _FakeVectorstore) -> None:
    doc = _seed_chunked_document(worker_db, n_chunks=2)

    jobs.embed_chunks(doc.id)

    worker_db.refresh(doc)
    assert doc.status == DocumentStatus.indexed
    assert embed_env.ensured is True
    assert embed_env.deleted == [doc.id]  # cleared before re-upsert
    assert len(embed_env.upserted) == 2
    point = embed_env.upserted[0]
    assert point.collection_id == doc.collection_id
    assert len(point.vector) == 3


def test_embed_chunks_with_no_chunks_still_indexes(
    worker_db: Session, embed_env: _FakeVectorstore
) -> None:
    doc = _seed_chunked_document(worker_db, n_chunks=0)

    jobs.embed_chunks(doc.id)

    worker_db.refresh(doc)
    assert doc.status == DocumentStatus.indexed
    assert embed_env.upserted == []
    assert embed_env.deleted == [doc.id]  # still clears any stale points


def test_embed_chunks_ignores_wrong_status(worker_db: Session, embed_env: _FakeVectorstore) -> None:
    doc = _seed_chunked_document(worker_db, n_chunks=1)
    doc.status = DocumentStatus.queued  # not yet chunked
    worker_db.commit()

    jobs.embed_chunks(doc.id)

    worker_db.refresh(doc)
    assert doc.status == DocumentStatus.queued
    assert embed_env.upserted == []


def test_embed_chunks_failure_sets_error(
    worker_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_sqlite_chunks_table(worker_db.get_bind())
    monkeypatch.setattr(jobs, "vectorstore", _FakeVectorstore())

    class Boom:
        def embed_texts(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("model load failed")

    monkeypatch.setattr(jobs, "get_embedder", lambda: Boom())
    doc = _seed_chunked_document(worker_db, n_chunks=1)

    jobs.embed_chunks(doc.id)

    worker_db.refresh(doc)
    assert doc.status == DocumentStatus.error
    assert doc.error_msg
