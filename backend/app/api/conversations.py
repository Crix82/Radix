from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.models import Conversation, User, UserRole
from app.models.schemas import (
    ChatMessageOut,
    CitationOut,
    ConversationDetailOut,
    ConversationOut,
)
from app.services import conversations as service

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    db: DbSession,
    user: CurrentUser,
    user_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ConversationOut]:
    """Own threads; admins see everyone's (read-only) and may filter by user."""
    stmt = (
        select(Conversation, User.email)
        .join(User, Conversation.user_id == User.id)
        .where(Conversation.deleted_at.is_(None))
    )
    if user.role != UserRole.admin:
        stmt = stmt.where(Conversation.user_id == user.id)
    elif user_id is not None:
        stmt = stmt.where(Conversation.user_id == user_id)
    stmt = stmt.order_by(Conversation.updated_at.desc(), Conversation.id.desc()).limit(limit)

    return [
        ConversationOut(
            id=c.id,
            title=c.title,
            created_at=c.created_at,
            updated_at=c.updated_at,
            user_id=c.user_id,
            user_email=email,
        )
        for c, email in db.execute(stmt).all()
    ]


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(
    conversation_id: int, db: DbSession, user: CurrentUser
) -> ConversationDetailOut:
    conversation = service.get_for_read(db, conversation_id, user)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    owner_email = db.scalar(select(User.email).where(User.id == conversation.user_id))
    return ConversationDetailOut(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        user_id=conversation.user_id,
        user_email=owner_email,
        messages=[
            ChatMessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                citations=[CitationOut.model_validate(c) for c in (m.citations or [])],
                refusal=m.refusal,
                created_at=m.created_at,
            )
            for m in service.messages(db, conversation_id)
        ],
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: int, db: DbSession, user: CurrentUser) -> None:
    """Only the owner deletes: an admin's read access does not extend to destroying threads."""
    conversation = service.get_for_write(db, conversation_id, user)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    conversation.deleted_at = datetime.now(UTC)
    db.commit()
