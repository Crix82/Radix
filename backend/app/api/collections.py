from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.core.deps import AdminUser, DbSession
from app.models import AuditLog, Collection, Document
from app.models.schemas import CollectionCreate, CollectionOut

router = APIRouter(prefix="/collections", tags=["collections"])


def _document_counts(db: DbSession) -> dict[int, int]:
    rows = db.execute(
        select(Document.collection_id, func.count())
        .where(Document.deleted_at.is_(None))
        .group_by(Document.collection_id)
    ).all()
    return {collection_id: count for collection_id, count in rows}


@router.get("", response_model=list[CollectionOut])
def list_collections(db: DbSession, _admin: AdminUser) -> list[CollectionOut]:
    counts = _document_counts(db)
    collections = db.scalars(select(Collection).order_by(Collection.name)).all()
    return [
        CollectionOut(id=c.id, name=c.name, document_count=counts.get(c.id, 0)) for c in collections
    ]


@router.post("", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
def create_collection(body: CollectionCreate, db: DbSession, admin: AdminUser) -> CollectionOut:
    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name is required"
        )
    if db.scalar(select(Collection).where(Collection.name == name)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Collection already exists"
        )
    collection = Collection(name=name)
    db.add(collection)
    db.flush()
    db.add(
        AuditLog(
            user_id=admin.id,
            action="admin_change",
            object_type="collection",
            object_id=str(collection.id),
            meta={"op": "created", "name": name},
        )
    )
    db.commit()
    return CollectionOut(id=collection.id, name=collection.name, document_count=0)
