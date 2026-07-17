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


class UserDetailOut(UserOut):
    collection_ids: list[int] = []


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    role: UserRole = UserRole.user
    collection_ids: list[int] = []
    # If a password is set the user is active immediately; otherwise they are 'invited'
    # and an admin activates them later by setting a password (SPEC §9, on-prem).
    password: str | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    role: UserRole | None = None
    status: UserStatus | None = None
    password: str | None = None
    collection_ids: list[int] | None = None


class CollectionCreate(BaseModel):
    name: str


class CollectionOut(BaseModel):
    id: int
    name: str
    document_count: int = 0

    model_config = {"from_attributes": True}


class AuditEntryOut(BaseModel):
    id: int
    ts: datetime
    user_id: int | None
    user_email: str | None
    action: str
    object_type: str | None
    object_id: str | None
    ip: str | None


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


class SearchDocumentRef(BaseModel):
    id: int
    title: str | None
    lang: str | None
    doc_type: str | None
    rel_path: str


class SearchResultOut(BaseModel):
    chunk_id: int
    document: SearchDocumentRef
    page: int
    snippet_html: str
    score: float


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatFilters(BaseModel):
    lang: str | None = None
    doc_type: str | None = None
    collection_id: int | None = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    filters: ChatFilters = ChatFilters()


class ComponentHealth(BaseModel):
    status: str  # "ok" | "error"
    detail: str | None = None


class HealthOut(BaseModel):
    status: str
    components: dict[str, ComponentHealth]
