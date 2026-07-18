"""FTS: rebuild chunks.tsv on the language-agnostic 'simple' config.

The tsvector was lexed with the chunk's detected-language config while queries were lexed with
the query's detected-language config; when the two diverge (an Italian invoice detected 'en',
keyword-only queries) the stemming differs and nothing matches. Switch both sides to 'simple'
(see CHUNK_TSV_EXPRESSION in app/models/tables.py and FTS_REGCONFIG in services/search).

`tsv` is a STORED generated column, so changing the ORM expression does not rewrite existing
rows. Postgres 16 has no `ALTER COLUMN ... SET EXPRESSION` (that is PG17+), so we drop and re-add
the generated column (which recomputes it for every chunk) and recreate its GIN index. No
re-embedding is needed (Qdrant is untouched).

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSVECTOR

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SIMPLE = "to_tsvector('simple', text)"
_PER_LANG = (
    "to_tsvector("
    "CASE lang WHEN 'it' THEN 'italian'::regconfig "
    "WHEN 'en' THEN 'english'::regconfig "
    "WHEN 'de' THEN 'german'::regconfig "
    "ELSE 'simple'::regconfig END, text)"
)


def _rebuild_tsv(expression: str) -> None:
    op.drop_index("ix_chunks_tsv", table_name="chunks")
    op.drop_column("chunks", "tsv")
    op.add_column("chunks", sa.Column("tsv", TSVECTOR(), sa.Computed(expression, persisted=True)))
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")


def upgrade() -> None:
    _rebuild_tsv(_SIMPLE)


def downgrade() -> None:
    _rebuild_tsv(_PER_LANG)
