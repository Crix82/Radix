from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.core.deps import AdminUser, DbSession
from app.core.queue import enqueue_sync_source
from app.models import AuditLog, Collection, Document, Source, SourceType
from app.models.schemas import SourceCreate, SourceOut, SourceUpdate

router = APIRouter(prefix="/sources", tags=["sources"])

# Collections get real management in M5; until then sources land here by default.
DEFAULT_COLLECTION_NAME = "Generale"


def get_or_create_default_collection(db: DbSession) -> Collection:
    collection = db.scalar(select(Collection).where(Collection.name == DEFAULT_COLLECTION_NAME))
    if collection is None:
        collection = Collection(name=DEFAULT_COLLECTION_NAME)
        db.add(collection)
        db.flush()
    return collection


def _audit(db: DbSession, user_id: int, op: str, source: Source) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action="admin_change",
            object_type="source",
            object_id=str(source.id),
            meta={"op": op, "type": source.type.value, "path": source.path},
        )
    )


def _document_counts(db: DbSession) -> dict[int, int]:
    rows = db.execute(
        select(Document.source_id, func.count())
        .where(Document.deleted_at.is_(None), Document.source_id.is_not(None))
        .group_by(Document.source_id)
    ).all()
    return {source_id: count for source_id, count in rows}


def _to_out(source: Source, document_count: int) -> SourceOut:
    out = SourceOut.model_validate(source)
    out.document_count = document_count
    return out


@router.get("", response_model=list[SourceOut])
def list_sources(db: DbSession, _admin: AdminUser) -> list[SourceOut]:
    counts = _document_counts(db)
    sources = db.scalars(select(Source).order_by(Source.id)).all()
    return [_to_out(s, counts.get(s.id, 0)) for s in sources]


@router.post("", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
def create_source(body: SourceCreate, db: DbSession, admin: AdminUser) -> SourceOut:
    if body.collection_id is not None:
        collection = db.get(Collection, body.collection_id)
        if collection is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown collection")
    else:
        collection = get_or_create_default_collection(db)

    source = Source(
        type=body.type,
        path=(body.path or "").strip(),
        collection_id=collection.id,
        enabled=True,
    )
    db.add(source)
    db.flush()
    _audit(db, admin.id, "created", source)
    db.commit()
    if source.type != SourceType.upload:
        enqueue_sync_source(source.id)
    return _to_out(source, 0)


@router.patch("/{source_id}", response_model=SourceOut)
def update_source(source_id: int, body: SourceUpdate, db: DbSession, admin: AdminUser) -> SourceOut:
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    if body.path is not None and source.type != SourceType.upload:
        source.path = body.path.strip()
    if body.enabled is not None:
        source.enabled = body.enabled
    _audit(db, admin.id, "updated", source)
    db.commit()
    if source.enabled and source.type != SourceType.upload:
        enqueue_sync_source(source.id)
    return _to_out(source, _document_counts(db).get(source.id, 0))


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: int, db: DbSession, admin: AdminUser) -> None:
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    now = datetime.now(UTC)
    for document in db.scalars(
        select(Document).where(Document.source_id == source.id, Document.deleted_at.is_(None))
    ):
        document.deleted_at = now  # tombstone; the FK sets source_id to NULL on delete
    _audit(db, admin.id, "deleted", source)
    db.delete(source)
    db.commit()
