import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Postgres-native types in production, plain fallbacks so tests can run on SQLite.
JSONB_V = JSON().with_variant(JSONB(), "postgresql")
INET_V = String(45).with_variant(INET(), "postgresql")
# SQLite only autoincrements INTEGER primary keys, never BIGINT.
BIGPK = BigInteger().with_variant(Integer(), "sqlite")


class Base(DeclarativeBase):
    pass


class UserRole(enum.StrEnum):
    admin = "admin"
    user = "user"


class UserStatus(enum.StrEnum):
    active = "active"
    invited = "invited"
    disabled = "disabled"


class SourceType(enum.StrEnum):
    smb = "smb"
    local = "local"
    upload = "upload"


class DocumentStatus(enum.StrEnum):
    queued = "queued"
    parsing = "parsing"
    ocr = "ocr"
    chunking = "chunking"
    embedding = "embedding"
    indexed = "indexed"
    error = "error"
    excluded = "excluded"


class TagKind(enum.StrEnum):
    doc_type = "doc_type"
    topic = "topic"


class TagOrigin(enum.StrEnum):
    auto = "auto"
    manual = "manual"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(300))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"))
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"), default=UserStatus.invited
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)


class UserCollection(Base):
    __tablename__ = "user_collections"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True
    )


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[SourceType] = mapped_column(Enum(SourceType, name="source_type"))
    path: Mapped[str] = mapped_column(Text)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str | None] = mapped_column(String(50))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("source_id", "rel_path", "content_hash", name="uq_documents_dedupe"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Nullable: documents outlive their source (tombstones keep history after DELETE /sources).
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"))
    rel_path: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    lang: Mapped[str | None] = mapped_column(String(10))
    doc_type: Mapped[str | None] = mapped_column(String(50))
    content_hash: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    pages: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"), default=DocumentStatus.queued
    )
    error_msg: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# FTS uses the language-agnostic 'simple' config on purpose (SPEC §4.1): a per-language
# stemmer only helps when the query's detected language matches the chunk's, which is
# unreliable on a multilingual corpus (an Italian invoice can be detected 'en', short queries
# have no function words). 'simple' does exact lexeme matching — the right trade-off for the
# terms lexical search must catch (invoice/part numbers, codes, names); the dense retriever
# covers morphology. Both index and query side must use the SAME config or nothing matches.
CHUNK_TSV_EXPRESSION = "to_tsvector('simple', text)"


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),)

    id: Mapped[int] = mapped_column(BIGPK, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    page_start: Mapped[int] = mapped_column(Integer)
    page_end: Mapped[int] = mapped_column(Integer)
    heading_path: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    bboxes: Mapped[dict[str, Any] | None] = mapped_column(JSONB_V)
    lang: Mapped[str | None] = mapped_column(String(10))
    tsv: Mapped[Any] = mapped_column(TSVECTOR, Computed(CHUNK_TSV_EXPRESSION, persisted=True))


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    kind: Mapped[TagKind] = mapped_column(Enum(TagKind, name="tag_kind"))


class DocumentTag(Base):
    __tablename__ = "document_tags"

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    origin: Mapped[TagOrigin] = mapped_column(Enum(TagOrigin, name="tag_origin"))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BIGPK, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(50))
    object_type: Mapped[str | None] = mapped_column(String(50))
    object_id: Mapped[str | None] = mapped_column(String(100))
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB_V)
    ip: Mapped[str | None] = mapped_column(INET_V)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_conversation", "conversation_id", "id"),)

    id: Mapped[int] = mapped_column(BIGPK, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    # Citations are stored as returned to the client so a resumed thread renders identically
    # without re-running retrieval (chunks may have been re-indexed since).
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB_V)
    refusal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, Any] | None] = mapped_column(JSONB_V)
