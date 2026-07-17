import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Chunk,
    Collection,
    Document,
    DocumentStatus,
    Source,
    SourceType,
    User,
    UserCollection,
)
from tests.conftest import create_sqlite_chunks_table


@pytest.fixture
def fake_retrievers(monkeypatch: pytest.MonkeyPatch):
    """Replace the Qdrant/embedding-backed retrievers with canned chunk-id lists."""
    state: dict[str, list[int]] = {"dense": [], "fts": []}
    monkeypatch.setattr("app.api.search.get_embedder", lambda: object())
    monkeypatch.setattr("app.api.search.get_client", lambda: object())
    monkeypatch.setattr(
        "app.services.search.dense_search",
        lambda *a, **k: list(state["dense"]),
    )
    monkeypatch.setattr(
        "app.services.search.fts_search",
        lambda *a, **k: list(state["fts"]),
    )
    return state


def _seed(db: Session) -> dict[str, int]:
    create_sqlite_chunks_table(db.get_bind())
    col_a, col_b = Collection(name="A"), Collection(name="B")
    db.add_all([col_a, col_b])
    db.flush()
    source = Source(type=SourceType.local, path="/x", collection_id=col_a.id)
    db.add(source)
    db.flush()
    out: dict[str, int] = {"col_a": col_a.id, "col_b": col_b.id}
    for key, coll in [("a", col_a.id), ("b", col_b.id)]:
        d = Document(
            source_id=source.id,
            collection_id=coll,
            rel_path=f"{key}.pdf",
            title=f"doc {key}",
            content_hash=key.ljust(64, "0"),
            status=DocumentStatus.indexed,
            lang="it",
        )
        db.add(d)
        db.flush()
        c = Chunk(
            document_id=d.id,
            page_start=7,
            page_end=7,
            text=f"La coppia di serraggio della testata nel documento {key}.",
            lang="it",
        )
        db.add(c)
        db.flush()
        out[f"chunk_{key}"] = c.id
    db.commit()
    return out


def test_search_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/search?q=test").status_code == 401


def test_search_requires_query(client: TestClient, admin_user: User) -> None:
    assert client.get("/api/v1/search").status_code == 422
    assert client.get("/api/v1/search?q=").status_code == 422


def test_admin_search_returns_hydrated_results(
    client: TestClient, api_db: Session, admin_user: User, fake_retrievers
) -> None:
    ids = _seed(api_db)
    fake_retrievers["dense"] = [ids["chunk_a"], ids["chunk_b"]]
    fake_retrievers["fts"] = [ids["chunk_a"]]

    body = client.get("/api/v1/search?q=coppia di serraggio testata").json()
    assert len(body) == 2
    top = body[0]
    assert top["chunk_id"] == ids["chunk_a"]  # in both lists -> ranked first
    assert top["document"]["title"] == "doc a"
    assert top["page"] == 7
    assert "<b>coppia</b>" in top["snippet_html"]
    assert top["score"] > 0


def test_search_is_audited(
    client: TestClient, api_db: Session, admin_user: User, fake_retrievers
) -> None:
    _seed(api_db)
    client.get("/api/v1/search?q=testata")
    audit = api_db.scalar(select(AuditLog).where(AuditLog.action == "search"))
    assert audit is not None and audit.meta["q"] == "testata"


def test_user_cannot_see_other_collections(
    client: TestClient, api_db: Session, plain_user: User, fake_retrievers
) -> None:
    ids = _seed(api_db)
    api_db.add(UserCollection(user_id=plain_user.id, collection_id=ids["col_a"]))
    api_db.commit()
    # both chunks surface from the (faked) retrievers, but col B must be filtered out
    fake_retrievers["dense"] = [ids["chunk_a"], ids["chunk_b"]]

    body = client.get("/api/v1/search?q=coppia").json()
    titles = [r["document"]["title"] for r in body]
    assert titles == ["doc a"]


def test_user_without_collections_sees_nothing(
    client: TestClient, api_db: Session, plain_user: User, fake_retrievers
) -> None:
    ids = _seed(api_db)
    fake_retrievers["dense"] = [ids["chunk_a"], ids["chunk_b"]]
    assert client.get("/api/v1/search?q=coppia").json() == []
