import json
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
from app.models import (
    Base,
    Chunk,
    Collection,
    Document,
    DocumentStatus,
    Source,
    SourceType,
    User,
    UserRole,
    UserStatus,
)

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


class FakeProvider:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens

    def complete(self, messages, stream=True, json_schema=None) -> Iterator[str]:
        yield from self.tokens


class FakeEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.0, 0.0, 0.0]


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:") :].strip())
        if event:
            events.append((event, data))
    return events


def wire_chat(monkeypatch, dense, fts, tokens) -> None:
    """Point the chat stack at canned retrieval results and a scripted LLM."""
    monkeypatch.setattr("app.services.vectorstore.search", lambda *a, **k: list(dense))
    monkeypatch.setattr("app.services.rag.fts_search", lambda *a, **k: list(fts))
    monkeypatch.setattr("app.api.chat.get_llm_provider", lambda: FakeProvider(tokens))


@pytest.fixture
def chat_corpus(api_db: Session, monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    create_sqlite_chunks_table(api_db.get_bind())
    # the streaming generator opens its own session — bind it to the same test engine
    monkeypatch.setattr("app.api.chat.SessionLocal", sessionmaker(bind=api_db.get_bind()))
    monkeypatch.setattr("app.api.chat.get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr("app.api.chat.get_client", lambda: object())

    col = Collection(name="C")
    api_db.add(col)
    api_db.flush()
    src = Source(type=SourceType.local, path="/x", collection_id=col.id)
    api_db.add(src)
    api_db.flush()
    doc = Document(
        source_id=src.id,
        collection_id=col.id,
        rel_path="boll.pdf",
        title="Bollettino RS",
        content_hash="b" * 64,
        status=DocumentStatus.indexed,
        lang="it",
    )
    api_db.add(doc)
    api_db.flush()
    ch = Chunk(
        document_id=doc.id,
        page_start=8,
        page_end=8,
        lang="it",
        bboxes={"8": [[0.1, 0.1, 0.5, 0.2]]},
        text="Verifica della coppia di serraggio della testata.",
    )
    api_db.add(ch)
    api_db.commit()
    return {"chunk": ch.id, "doc": doc.id}


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
