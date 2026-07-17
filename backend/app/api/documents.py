from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse

from app.core.deps import AdminUser, CurrentUser, DbSession, client_ip
from app.core.permissions import allowed_collection_ids
from app.core.queue import enqueue_parse_document
from app.models import AuditLog, Document, DocumentStatus, User
from app.models.schemas import DocumentOut
from app.services import ingest
from app.services.rendering import PageOutOfRange, render_page

router = APIRouter(prefix="/documents", tags=["documents"])


def _get_document(db: DbSession, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


def _readable_document(db: DbSession, document_id: int, user: User) -> Document:
    """Fetch a document the user is allowed to read; 404 hides existence otherwise (SPEC §6)."""
    document = _get_document(db, document_id)
    allowed = allowed_collection_ids(db, user)
    if allowed is not None and document.collection_id not in allowed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


def _audit(db: DbSession, user_id: int, op: str, document: Document) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action="admin_change",
            object_type="document",
            object_id=str(document.id),
            meta={"op": op, "rel_path": document.rel_path},
        )
    )


@router.post("/{document_id}/exclude", response_model=DocumentOut)
def exclude_document(document_id: int, db: DbSession, admin: AdminUser) -> Document:
    document = _get_document(db, document_id)
    document.status = DocumentStatus.excluded  # M3 also drops the Qdrant points
    document.error_msg = None
    _audit(db, admin.id, "excluded", document)
    db.commit()
    return document


@router.post("/{document_id}/reindex", response_model=DocumentOut)
def reindex_document(document_id: int, db: DbSession, admin: AdminUser) -> Document:
    document = _get_document(db, document_id)
    document.status = DocumentStatus.queued
    document.error_msg = None
    _audit(db, admin.id, "reindexed", document)
    db.commit()
    enqueue_parse_document(document.id)
    return document


def _audit_open(db: DbSession, request: Request, user: User, document: Document) -> None:
    db.add(
        AuditLog(
            user_id=user.id,
            action="open_document",
            object_type="document",
            object_id=str(document.id),
            meta={"rel_path": document.rel_path},
            ip=client_ip(request),
        )
    )


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, request: Request, db: DbSession, user: CurrentUser) -> Document:
    document = _readable_document(db, document_id, user)
    _audit_open(db, request, user, document)
    db.commit()
    return document


@router.get("/{document_id}/pages/{page_number}.png")
def get_page_image(
    document_id: int, page_number: int, db: DbSession, user: CurrentUser
) -> FileResponse:
    document = _readable_document(db, document_id, user)
    if Path(document.rel_path).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Page rendering is available for PDF documents only",
        )
    pdf_path = ingest.original_path(document)
    if not pdf_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original file missing")
    try:
        image_path = render_page(document.id, pdf_path, page_number)
    except PageOutOfRange as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    # Page images are immutable per (document, page): the cache key is the content itself.
    return FileResponse(
        image_path, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"}
    )
