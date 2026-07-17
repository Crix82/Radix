"""Documents outlive their source: source_id nullable, FK ON DELETE SET NULL.

DELETE /sources tombstones the documents and removes the source row; the
document rows must survive as tombstones (SPEC §5).

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_NAME = "documents_source_id_fkey"


def upgrade() -> None:
    op.alter_column("documents", "source_id", existing_type=sa.Integer(), nullable=True)
    op.drop_constraint(FK_NAME, "documents", type_="foreignkey")
    op.create_foreign_key(
        FK_NAME, "documents", "sources", ["source_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint(FK_NAME, "documents", type_="foreignkey")
    op.create_foreign_key(FK_NAME, "documents", "sources", ["source_id"], ["id"])
    op.alter_column("documents", "source_id", existing_type=sa.Integer(), nullable=False)
