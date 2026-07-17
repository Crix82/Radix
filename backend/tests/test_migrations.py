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
]


def test_initial_migration_emits_full_schema() -> None:
    """Render the migration SQL offline and check the whole SPEC §4.1 schema is there."""
    cfg = Config("alembic.ini")
    buf = io.StringIO()
    with redirect_stdout(buf):
        command.upgrade(cfg, "head", sql=True)
    sql = buf.getvalue()

    for table in EXPECTED_TABLES:
        assert f"CREATE TABLE {table}" in sql, f"missing table {table}"
    assert "GENERATED ALWAYS AS" in sql  # chunks.tsv computed column
    assert "USING gin" in sql  # GIN index on chunks.tsv
    assert "regconfig" in sql  # per-language FTS config
