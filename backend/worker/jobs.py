"""RQ jobs for the indexing pipeline (SPEC §5).

Each stage is idempotent and re-runnable: discover -> parse -> (ocr) -> chunk -> embed -> index.
M1 shipped discover (sync_source); M2 implements parse_document (parse -> optional OCR ->
chunk). Embedding and indexing arrive in M3, so a chunked document rests at status
`chunking` until then.
"""

import logging
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import Chunk, Document, DocumentStatus, Source
from app.services import ingest
from app.services.chunking import chunk_document
from app.services.parsing import get_parser, probe_text_layer
from app.services.parsing.base import ParsedDocument
from app.services.parsing.errors import actionable_message

logger = logging.getLogger(__name__)

REPROCESSABLE = {DocumentStatus.queued, DocumentStatus.parsing, DocumentStatus.ocr}


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


def _parse_and_chunk(db: Session, document: Document, path: Path) -> None:
    is_pdf = path.suffix.lower() == ".pdf"
    needs_ocr = False
    probed_pages: int | None = None
    if is_pdf:
        report = probe_text_layer(path)
        needs_ocr = report.needs_ocr
        probed_pages = report.page_count

    if needs_ocr:
        document.status = DocumentStatus.ocr
        db.commit()

    parsed: ParsedDocument = get_parser().parse(str(path), ocr=needs_ocr)

    document.status = DocumentStatus.chunking
    db.commit()

    # Idempotent reprocess: drop any chunks from a previous run before writing new ones.
    db.execute(delete(Chunk).where(Chunk.document_id == document.id))
    for chunk in chunk_document(parsed):
        db.add(
            Chunk(
                document_id=document.id,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                heading_path=chunk.heading_path,
                text=chunk.text,
                bboxes=chunk.bboxes or None,
                lang=chunk.lang,
            )
        )

    document.lang = parsed.lang
    document.pages = probed_pages or parsed.page_count
    document.error_msg = None
    # Rests at `chunking` until M3 embeds and indexes it.
    db.commit()


def parse_document(document_id: int) -> None:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if (
            document is None
            or document.deleted_at is not None
            or document.status not in REPROCESSABLE
        ):
            return

        document.status = DocumentStatus.parsing
        db.commit()

        path = ingest.original_path(document)
        try:
            _parse_and_chunk(db, document, path)
        except Exception as exc:  # noqa: BLE001 - any parse failure becomes an actionable status
            logger.warning("parse_document(%s) failed: %s", document_id, exc)
            db.rollback()
            document.status = DocumentStatus.error
            document.error_msg = actionable_message(exc)
            db.commit()
            return
        logger.info(
            "parse_document(%s): lang=%s pages=%s", document_id, document.lang, document.pages
        )


def embed_chunks(document_id: int) -> None:
    raise NotImplementedError("Implemented in M3")


def index_chunks(document_id: int) -> None:
    raise NotImplementedError("Implemented in M3")
