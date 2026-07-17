import shutil
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Collection, Document, DocumentStatus, Source, SourceType
from app.services import ingest
from tests.conftest import FIXTURE_PDFS


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    target = tmp_path / "docs"
    target.mkdir()
    for pdf in FIXTURE_PDFS:
        shutil.copy2(pdf, target / pdf.name)
    return target


@pytest.fixture
def source(db_session: Session, source_dir: Path) -> Source:
    collection = Collection(name="Test")
    db_session.add(collection)
    db_session.flush()
    src = Source(
        type=SourceType.local, path=str(source_dir), collection_id=collection.id, enabled=True
    )
    db_session.add(src)
    db_session.commit()
    return src


def live_docs(db: Session) -> list[Document]:
    return list(db.scalars(select(Document).where(Document.deleted_at.is_(None))))


def test_first_sync_discovers_all_fixtures(
    db_session: Session, source: Source, enqueued: dict[str, list[int]]
) -> None:
    result = ingest.sync_source(db_session, source)

    assert result.added == len(FIXTURE_PDFS) == 5
    docs = live_docs(db_session)
    assert len(docs) == 5
    assert all(d.status == DocumentStatus.queued for d in docs)
    assert all(len(d.content_hash) == 64 for d in docs)
    assert sorted(enqueued["parse"]) == sorted(d.id for d in docs)
    for doc in docs:
        stored = ingest.original_path(doc)
        assert stored.is_file() and stored.suffix == ".pdf"
    assert source.status == "ok" and source.last_sync_at is not None


def test_resync_is_idempotent(
    db_session: Session, source: Source, enqueued: dict[str, list[int]]
) -> None:
    ingest.sync_source(db_session, source)
    result = ingest.sync_source(db_session, source)

    assert result.added == 0 and result.updated == 0 and result.unchanged == 5
    assert len(live_docs(db_session)) == 5
    assert len(enqueued["parse"]) == 5  # only the first pass enqueued


def test_modified_file_is_requeued_with_new_hash(
    db_session: Session, source: Source, source_dir: Path, enqueued: dict[str, list[int]]
) -> None:
    ingest.sync_source(db_session, source)
    target = source_dir / FIXTURE_PDFS[0].name
    doc = db_session.scalar(select(Document).where(Document.rel_path == target.name))
    assert doc is not None
    doc.status = DocumentStatus.indexed
    db_session.commit()
    old_hash = doc.content_hash

    target.write_bytes(target.read_bytes() + b"\n% new revision\n")
    result = ingest.sync_source(db_session, source)

    assert result.updated == 1 and result.added == 0
    assert doc.content_hash != old_hash
    assert doc.status == DocumentStatus.queued
    assert len(live_docs(db_session)) == 5  # updated in place, no duplicate row


def test_removed_file_becomes_tombstone(
    db_session: Session, source: Source, source_dir: Path, enqueued: dict[str, list[int]]
) -> None:
    ingest.sync_source(db_session, source)
    removed = source_dir / FIXTURE_PDFS[0].name
    removed.unlink()

    result = ingest.sync_source(db_session, source)

    assert result.removed == 1
    assert len(live_docs(db_session)) == 4
    tombstone = db_session.scalar(select(Document).where(Document.rel_path == removed.name))
    assert tombstone is not None and tombstone.deleted_at is not None
    # a further pass must not tombstone it again
    assert ingest.sync_source(db_session, source).removed == 0


def test_restored_file_resurrects_tombstone(
    db_session: Session, source: Source, source_dir: Path, enqueued: dict[str, list[int]]
) -> None:
    ingest.sync_source(db_session, source)
    target = source_dir / FIXTURE_PDFS[0].name
    content = target.read_bytes()
    target.unlink()
    ingest.sync_source(db_session, source)

    target.write_bytes(content)
    result = ingest.sync_source(db_session, source)

    assert result.updated == 1 and result.added == 0
    docs = db_session.scalars(select(Document).where(Document.rel_path == target.name)).all()
    assert len(docs) == 1  # resurrected, not duplicated
    assert docs[0].deleted_at is None and docs[0].status == DocumentStatus.queued


def test_unsupported_files_are_ignored(
    db_session: Session, source: Source, source_dir: Path, enqueued: dict[str, list[int]]
) -> None:
    (source_dir / "notes.xyz").write_text("ignored")
    (source_dir / "thumbs.db").write_text("ignored")

    result = ingest.sync_source(db_session, source)

    assert result.added == 5
    assert {d.rel_path for d in live_docs(db_session)} == {p.name for p in FIXTURE_PDFS}


def test_nested_directories_use_posix_rel_paths(
    db_session: Session, source: Source, source_dir: Path, enqueued: dict[str, list[int]]
) -> None:
    nested = source_dir / "manuali" / "2024"
    nested.mkdir(parents=True)
    shutil.copy2(FIXTURE_PDFS[0], nested / "copia.pdf")

    ingest.sync_source(db_session, source)

    doc = db_session.scalar(select(Document).where(Document.rel_path == "manuali/2024/copia.pdf"))
    assert doc is not None


def test_missing_path_raises_actionable_error(db_session: Session, source: Source) -> None:
    source.path = "/nonexistent/share"
    with pytest.raises(ingest.SourcePathError, match="not an accessible directory"):
        ingest.sync_source(db_session, source)
