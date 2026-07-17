from datetime import datetime

from pydantic import BaseModel, EmailStr, model_validator

from app.models.tables import DocumentStatus, SourceType, UserRole, UserStatus


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: UserRole
    status: UserStatus

    model_config = {"from_attributes": True}


class SourceCreate(BaseModel):
    type: SourceType
    path: str | None = None
    collection_id: int | None = None

    @model_validator(mode="after")
    def path_required_for_folders(self) -> "SourceCreate":
        if self.type != SourceType.upload and not (self.path or "").strip():
            raise ValueError("path is required for smb and local sources")
        return self


class SourceUpdate(BaseModel):
    enabled: bool | None = None
    path: str | None = None


class SourceOut(BaseModel):
    id: int
    type: SourceType
    path: str
    collection_id: int
    enabled: bool
    status: str | None
    last_sync_at: datetime | None
    document_count: int = 0

    model_config = {"from_attributes": True}


class DocumentOut(BaseModel):
    id: int
    source_id: int | None
    collection_id: int
    rel_path: str
    title: str | None
    lang: str | None
    doc_type: str | None
    status: DocumentStatus
    error_msg: str | None
    size_bytes: int | None
    pages: int | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class UploadOut(BaseModel):
    created: list[DocumentOut]
    unchanged: int


class IndexingStatsOut(BaseModel):
    documents_indexed: int
    queued: int
    errors: int
    space_used_bytes: int
    space_total_bytes: int


class QueueItemOut(BaseModel):
    id: int
    rel_path: str
    source_type: SourceType | None
    source_path: str | None
    status: DocumentStatus
    error_msg: str | None
    updated_at: datetime


class ComponentHealth(BaseModel):
    status: str  # "ok" | "error"
    detail: str | None = None


class HealthOut(BaseModel):
    status: str
    components: dict[str, ComponentHealth]
