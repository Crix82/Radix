from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    Column,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.main import app
from app.models import Base, User, UserRole, UserStatus

FIXTURES_DIR = Path(__file__).parent / "fixtures"
# The 5 born-digital manuals used by the M1 ingest tests (excludes the M2 scanned fixture).
FIXTURE_PDFS = sorted(p for p in FIXTURES_DIR.glob("*.pdf") if not p.name.startswith("scansione"))
SCANNED_PDF = FIXTURES_DIR / "scansione_ita_manutenzione.pdf"

# The chunks table needs Postgres (tsvector + regconfig); every other table runs on SQLite.
SQLITE_TABLES = [t for name, t in Base.metadata.tables.items() if name != "chunks"]


def create_sqlite_chunks_table(engine: Engine) -> None:
    """A tsvector-free `chunks` table so worker/pipeline tests can insert on SQLite."""
    md = MetaData()
    Table(
        "chunks",
        md,
        Column("id", Integer, primary_key=True),
        Column("document_id", Integer),
        Column("page_start", Integer),
        Column("page_end", Integer),
        Column("heading_path", Text),
        Column("text", Text),
        Column("bboxes", Text),
        Column("lang", String(10)),
        Column("tsv", Text),  # placeholder for the Postgres computed column
        extend_existing=True,
    )
    md.create_all(engine)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c
        app.dependency_overrides.clear()


@pytest.fixture
def db_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    """In-memory SQLite session; DATA_DIR redirected to a temp dir for repository writes."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine, tables=SQLITE_TABLES)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        yield session
    get_settings.cache_clear()


@pytest.fixture
def api_db(client: TestClient, db_session: Session) -> Session:
    app.dependency_overrides[get_db] = lambda: db_session
    return db_session


def _make_user(db: Session, role: UserRole) -> User:
    user = User(
        name="Test",
        email=f"{role.value}@example.com",
        password_hash="x",
        role=role,
        status=UserStatus.active,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def admin_user(api_db: Session) -> User:
    user = _make_user(api_db, UserRole.admin)
    app.dependency_overrides[get_current_user] = lambda: user
    return user


@pytest.fixture
def plain_user(api_db: Session) -> User:
    user = _make_user(api_db, UserRole.user)
    app.dependency_overrides[get_current_user] = lambda: user
    return user


@pytest.fixture
def enqueued(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[int]]:
    """Capture queue producer calls instead of talking to Redis."""
    calls: dict[str, list[int]] = {"parse": [], "sync": []}
    for module in ("app.services.ingest", "app.api.documents"):
        monkeypatch.setattr(
            f"{module}.enqueue_parse_document", lambda doc_id: calls["parse"].append(doc_id)
        )
    monkeypatch.setattr(
        "app.api.sources.enqueue_sync_source", lambda source_id: calls["sync"].append(source_id)
    )
    return calls
