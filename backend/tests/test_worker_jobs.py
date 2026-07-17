import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.models import Collection, Document, DocumentStatus, Source, SourceType
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


def test_parse_document_advances_queued_to_parsing(worker_db: Session) -> None:
    doc = _seed_document(worker_db, DocumentStatus.queued)

    jobs.parse_document(doc.id)

    worker_db.refresh(doc)
    assert doc.status == DocumentStatus.parsing


def test_parse_document_ignores_non_queued_and_missing(worker_db: Session) -> None:
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
