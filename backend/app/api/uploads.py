from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.sources import get_or_create_default_collection
from app.core.deps import AdminUser, DbSession
from app.models import AuditLog, Source, SourceType
from app.models.schemas import DocumentOut, UploadOut
from app.services import ingest
from app.services.ingest import SUPPORTED_EXTENSIONS

router = APIRouter(prefix="/uploads", tags=["uploads"])


def _get_or_create_upload_source(db: DbSession, source_id: int | None) -> Source:
    if source_id is not None:
        source = db.get(Source, source_id)
        if source is None or source.type != SourceType.upload:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Upload source not found"
            )
        return source
    source = db.scalar(
        select(Source).where(Source.type == SourceType.upload).order_by(Source.id).limit(1)
    )
    if source is None:
        collection = get_or_create_default_collection(db)
        source = Source(type=SourceType.upload, path="", collection_id=collection.id, enabled=True)
        db.add(source)
        db.flush()
    return source


@router.post("", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
async def upload_files(
    files: list[UploadFile],
    db: DbSession,
    admin: AdminUser,
    source_id: int | None = Form(default=None),
) -> UploadOut:
    source = _get_or_create_upload_source(db, source_id)
    created: list[DocumentOut] = []
    unchanged = 0
    for file in files:
        filename = file.filename or ""
        if ("." + filename.rsplit(".", 1)[-1]).lower() not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported file type: {filename}",
            )
        document = ingest.store_upload(db, source, filename, await file.read())
        if document is None:
            unchanged += 1
        else:
            db.add(
                AuditLog(
                    user_id=admin.id,
                    action="admin_change",
                    object_type="document",
                    object_id=str(document.id),
                    meta={"op": "uploaded", "rel_path": document.rel_path},
                )
            )
            created.append(DocumentOut.model_validate(document))
    db.commit()
    return UploadOut(created=created, unchanged=unchanged)
