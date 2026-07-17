"""Discover stage of the indexing pipeline (SPEC §5).

Scans a source (local folder or SMB mount — both are filesystem paths), computes
content hashes, dedupes on (source_id, rel_path, content_hash), copies new or
modified files into the internal repository (data/repository/{document_id}/original.ext)
and enqueues parsing. Files that disappeared from the source become tombstones.
"""

import hashlib
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.queue import enqueue_parse_document
from app.models import Document, DocumentStatus, Source

# Formats Docling can parse (SPEC §2); everything else is ignored during discovery.
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".html", ".txt"}


class SourcePathError(Exception):
    """The source path does not exist or is not a directory."""


@dataclass
class SyncResult:
    added: int = 0
    updated: int = 0
    removed: int = 0
    unchanged: int = 0
    document_ids: list[int] = field(default_factory=list)
    removed_document_ids: list[int] = field(default_factory=list)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def repository_dir() -> Path:
    return Path(get_settings().data_dir) / "repository"


def original_path(document: Document) -> Path:
    ext = Path(document.rel_path).suffix.lower()
    return repository_dir() / str(document.id) / f"original{ext}"


def _store_original(document: Document, src: Path) -> None:
    dest = original_path(document)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _upsert_document(
    db: Session, source: Source, rel_path: str, content_hash: str, size_bytes: int, src_file: Path
) -> tuple[Document | None, str]:
    """Create, update or resurrect the document for one discovered file.

    Returns (document to enqueue or None, outcome in {added, updated, unchanged}).
    """
    live = db.scalar(
        select(Document).where(
            Document.source_id == source.id,
            Document.rel_path == rel_path,
            Document.deleted_at.is_(None),
        )
    )
    if live is not None and live.content_hash == content_hash:
        return None, "unchanged"

    exact = db.scalar(
        select(Document).where(
            Document.source_id == source.id,
            Document.rel_path == rel_path,
            Document.content_hash == content_hash,
        )
    )
    now = datetime.now(UTC)
    if exact is not None:
        # Same content seen before (tombstoned version restored): resurrect it.
        if live is not None:
            live.deleted_at = now
        exact.deleted_at = None
        doc = exact
        outcome = "updated"
    elif live is not None:
        # Modified in place: keep the row, refresh content.
        live.content_hash = content_hash
        doc = live
        outcome = "updated"
    else:
        doc = Document(
            source_id=source.id,
            collection_id=source.collection_id,
            rel_path=rel_path,
            title=Path(rel_path).stem,
            content_hash=content_hash,
        )
        db.add(doc)
        db.flush()  # assign doc.id for the repository path
        outcome = "added"

    doc.size_bytes = size_bytes
    doc.status = DocumentStatus.queued
    doc.error_msg = None
    _store_original(doc, src_file)
    return doc, outcome


def sync_source(db: Session, source: Source) -> SyncResult:
    """Run one discover pass over a filesystem-backed source. Idempotent."""
    root = Path(source.path)
    if not root.is_dir():
        raise SourcePathError(f"Path is not an accessible directory: {source.path}")

    result = SyncResult()
    seen: set[str] = set()
    for file in sorted(p for p in root.rglob("*") if p.is_file()):
        if file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        rel_path = file.relative_to(root).as_posix()
        seen.add(rel_path)
        doc, outcome = _upsert_document(
            db, source, rel_path, file_sha256(file), file.stat().st_size, file
        )
        setattr(result, outcome, getattr(result, outcome) + 1)
        if doc is not None:
            result.document_ids.append(doc.id)

    stale = db.scalars(
        select(Document).where(
            Document.source_id == source.id,
            Document.deleted_at.is_(None),
            Document.rel_path.notin_(seen) if seen else Document.rel_path.is_not(None),
        )
    )
    now = datetime.now(UTC)
    for doc in stale:
        doc.deleted_at = now  # tombstone; the worker drops the Qdrant points (SPEC §5)
        result.removed += 1
        result.removed_document_ids.append(doc.id)

    source.last_sync_at = now
    source.status = "ok"
    db.commit()

    for document_id in result.document_ids:
        enqueue_parse_document(document_id)
    return result


def store_upload(db: Session, source: Source, filename: str, content: bytes) -> Document | None:
    """Register one manually uploaded file on an upload source. Returns None if unchanged."""
    rel_path = Path(filename).name  # drop any client-provided directories
    tmp = repository_dir() / "uploads.tmp" / rel_path
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(content)
    try:
        doc, _ = _upsert_document(
            db, source, rel_path, hashlib.sha256(content).hexdigest(), len(content), tmp
        )
    finally:
        tmp.unlink(missing_ok=True)
    source.last_sync_at = datetime.now(UTC)
    source.status = "ok"
    db.commit()
    if doc is not None:
        enqueue_parse_document(doc.id)
    return doc
