"""RQ jobs for the indexing pipeline (SPEC §5).

Each stage is idempotent and re-runnable: discover -> parse -> (ocr) -> chunk -> embed -> index.
M1 ships discover (sync_source); parse_document only advances the status so the
queue wiring is observable end-to-end — the real parser arrives in M2.
"""

import logging

from app.core.db import SessionLocal
from app.models import Document, DocumentStatus, Source
from app.services import ingest

logger = logging.getLogger(__name__)


def sync_source(source_id: int) -> None:
    with SessionLocal() as db:
        source = db.get(Source, source_id)
        if source is None or not source.enabled:
            return
        try:
            result = ingest.sync_source(db, source)
        except ingest.SourcePathError as exc:
            logger.warning("sync_source(%s) failed: %s", source_id, exc)
            db.rollback()
            source.status = "error"
            db.commit()
            return
        logger.info(
            "sync_source(%s): +%d added, %d updated, %d removed, %d unchanged",
            source_id,
            result.added,
            result.updated,
            result.removed,
            result.unchanged,
        )


def parse_document(document_id: int) -> None:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if (
            document is None
            or document.deleted_at is not None
            or document.status != DocumentStatus.queued
        ):
            return
        document.status = DocumentStatus.parsing  # real parsing lands in M2
        db.commit()


def embed_chunks(document_id: int) -> None:
    raise NotImplementedError("Implemented in M3")


def index_chunks(document_id: int) -> None:
    raise NotImplementedError("Implemented in M3")
