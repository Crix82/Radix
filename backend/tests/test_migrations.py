import io
from contextlib import redirect_stdout

from alembic import command
from alembic.config import Config

EXPECTED_TABLES = [
    "users",
    "collections",
    "user_collections",
    "sources",
    "documents",
    "chunks",
    "tags",
    "document_tags",
    "audit_log",
    "settings",
    "conversations",
    "chat_messages",
]


def _render_head_sql() -> str:
    cfg = Config("alembic.ini")
    buf = io.StringIO()
    with redirect_stdout(buf):
        command.upgrade(cfg, "head", sql=True)
    return buf.getvalue()


def test_no_table_is_created_twice() -> None:
    """0001 builds from live ORM metadata, so a later CREATE TABLE would collide on a fresh DB.

    Every migration must stay idempotent against the current models — see 0004's docstring.
    """
    sql = _render_head_sql()
    for table in EXPECTED_TABLES:
        assert sql.count(f"CREATE TABLE {table} ") == 1, f"{table} created more than once"


def test_initial_migration_emits_full_schema() -> None:
    """Render the migration SQL offline and check the whole SPEC §4.1 schema is there."""
    sql = _render_head_sql()

    for table in EXPECTED_TABLES:
        assert f"CREATE TABLE {table}" in sql, f"missing table {table}"
    assert "GENERATED ALWAYS AS" in sql  # chunks.tsv computed column
    assert "USING gin" in sql  # GIN index on chunks.tsv
    assert "to_tsvector('simple'" in sql  # language-agnostic FTS config
