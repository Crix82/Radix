from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.deps import AdminUser, DbSession
from app.models import Document, DocumentStatus, Source
from app.models.schemas import IndexingStatsOut, QueueItemOut

router = APIRouter(prefix="/indexing", tags=["indexing"])

PENDING_STATUSES = (
    DocumentStatus.queued,
    DocumentStatus.parsing,
    DocumentStatus.ocr,
    DocumentStatus.chunking,
    DocumentStatus.embedding,
)


@router.get("/stats", response_model=IndexingStatsOut)
def stats(db: DbSession, _admin: AdminUser) -> IndexingStatsOut:
    live = select(Document).where(Document.deleted_at.is_(None)).subquery()
    counts: dict[DocumentStatus, int] = {
        row[0]: row[1]
        for row in db.execute(select(live.c.status, func.count()).group_by(live.c.status))
    }
    space_used = db.scalar(select(func.coalesce(func.sum(live.c.size_bytes), 0))) or 0
    return IndexingStatsOut(
        documents_indexed=counts.get(DocumentStatus.indexed, 0),
        queued=sum(counts.get(status, 0) for status in PENDING_STATUSES),
        errors=counts.get(DocumentStatus.error, 0),
        space_used_bytes=int(space_used),
        space_total_bytes=get_settings().storage_capacity_gb * 1024**3,
    )


@router.get("/queue", response_model=list[QueueItemOut])
def queue(
    db: DbSession, _admin: AdminUser, limit: int = Query(default=50, ge=1, le=200)
) -> list[QueueItemOut]:
    rows = db.execute(
        select(Document, Source.type, Source.path)
        .join(Source, Document.source_id == Source.id, isouter=True)
        .where(Document.deleted_at.is_(None))
        .order_by(Document.updated_at.desc(), Document.id.desc())
        .limit(limit)
    ).all()
    return [
        QueueItemOut(
            id=doc.id,
            rel_path=doc.rel_path,
            source_type=source_type,
            source_path=source_path,
            status=doc.status,
            error_msg=doc.error_msg,
            updated_at=doc.updated_at,
        )
        for doc, source_type, source_path in rows
    ]
