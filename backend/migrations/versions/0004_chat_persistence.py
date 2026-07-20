"""Chat persistence: per-user conversations with their turns.

Chat was stateless — the client replayed the whole thread on every turn and nothing survived a
page reload. `conversations` owns a thread (soft-deleted by its owner, like documents) and
`chat_messages` holds the turns, with the assistant's citations stored as returned so a resumed
thread renders without re-running retrieval.

IMPORTANT — this migration is a no-op on a fresh database. Revision 0001 builds the schema with
`Base.metadata.create_all()`, i.e. from the *current* models, so a brand-new install already has
these two tables by the time we get here and CREATE TABLE would fail with "already exists". Every
migration in this repo therefore has to be idempotent against the live metadata (0002's ALTER and
0003's tsv drop/re-add happen to be); for a new table that means creating it only when absent.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.models.tables import JSONB_V

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    # Offline (`alembic upgrade --sql`) can't inspect; 0001 already emits both CREATE TABLEs
    # there, so emitting them again would render invalid SQL.
    if op.get_context().as_sql:
        return

    if not _has_table("conversations"):
        op.create_table(
            "conversations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _has_table("chat_messages"):
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column(
                "conversation_id",
                sa.Integer(),
                sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("citations", JSONB_V, nullable=True),
            sa.Column("refusal", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_chat_messages_conversation", "chat_messages", ["conversation_id", "id"])


def downgrade() -> None:
    if op.get_context().as_sql:
        return
    op.drop_table("chat_messages")
    op.drop_table("conversations")
