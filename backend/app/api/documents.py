from fastapi import APIRouter, HTTPException, status

from app.core.deps import AdminUser, DbSession
from app.core.queue import enqueue_parse_document
from app.models import AuditLog, Document, DocumentStatus
from app.models.schemas import DocumentOut

router = APIRouter(prefix="/documents", tags=["documents"])


def _get_document(db: DbSession, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.deleted_at is not None:
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


@router.get("/{document_id}", include_in_schema=False)
def not_implemented(document_id: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Planned for milestone M2"
    )
