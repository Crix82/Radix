"""Persistence for chat threads.

Chat used to be stateless: the client held the thread and replayed it on every turn. Now a
conversation owns its turns server-side, which also makes the replayed history authoritative —
the prompt is built from what we stored, never from what the client sends back.
"""

from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import ChatMessage, Conversation, User, UserRole
from app.services.rag import HISTORY_TURNS

TITLE_MAX_CHARS = 80


def title_from_question(question: str) -> str:
    """First question, trimmed to one line — no LLM call just to name a thread."""
    title = " ".join(question.split())
    if len(title) > TITLE_MAX_CHARS:
        title = title[: TITLE_MAX_CHARS - 1].rstrip() + "…"
    return title or "Nuova conversazione"


def get_for_write(db: Session, conversation_id: int, user: User) -> Conversation | None:
    """The user's own live conversation, or None. Admins do not write into others' threads."""
    return db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
            Conversation.deleted_at.is_(None),
        )
    )


def get_for_read(db: Session, conversation_id: int, user: User) -> Conversation | None:
    """As above, but admins may read any conversation (SPEC §9 — declared in the UI)."""
    stmt = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.deleted_at.is_(None)
    )
    if user.role != UserRole.admin:
        stmt = stmt.where(Conversation.user_id == user.id)
    return db.scalar(stmt)


def create(db: Session, user: User, question: str) -> Conversation:
    conversation = Conversation(user_id=user.id, title=title_from_question(question))
    db.add(conversation)
    db.flush()
    return conversation


def append(
    db: Session,
    conversation_id: int,
    role: str,
    content: str,
    citations: list[dict[str, Any]] | None = None,
    refusal: bool = False,
) -> ChatMessage:
    message = ChatMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        citations=citations,
        refusal=refusal,
    )
    db.add(message)
    # Appending a row does not touch the parent, but the thread list sorts by recency.
    db.execute(
        update(Conversation).where(Conversation.id == conversation_id).values(updated_at=func.now())
    )
    return message


def messages(db: Session, conversation_id: int) -> list[ChatMessage]:
    return list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.id)
        ).all()
    )


def history_for_prompt(db: Session, conversation_id: int) -> list[dict[str, str]]:
    """Stored turns as LLM messages, oldest first, capped.

    Returns the whole tail including the current question as the last element — that is the
    shape rag.answer_stream expects (it reads the question from the last user message and
    build_messages drops it from the replayed history).
    """
    rows = messages(db, conversation_id)[-(HISTORY_TURNS + 1) :]
    return [{"role": m.role, "content": m.content} for m in rows]
