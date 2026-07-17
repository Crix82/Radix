import pytest
from sqlalchemy.orm import Session

from app.models import Chunk, Collection, Document, DocumentStatus, Source, SourceType
from app.services.search import fuse_and_hydrate
from tests.conftest import create_sqlite_chunks_table


@pytest.fixture
def seeded(db_session: Session) -> dict[str, int]:
    create_sqlite_chunks_table(db_session.get_bind())
    col_a = Collection(name="A")
    col_b = Collection(name="B")
    db_session.add_all([col_a, col_b])
    db_session.flush()
    source = Source(type=SourceType.local, path="/x", collection_id=col_a.id)
    db_session.add(source)
    db_session.flush()

    def doc(
        title: str, collection_id: int, status: DocumentStatus, deleted: bool = False
    ) -> Document:
        d = Document(
            source_id=source.id,
            collection_id=collection_id,
            rel_path=f"{title}.pdf",
            title=title,
            content_hash=title.ljust(64, "0"),
            status=status,
            lang="it",
        )
        if deleted:
            from datetime import UTC, datetime

            d.deleted_at = datetime.now(UTC)
        db_session.add(d)
        db_session.flush()
        return d

    indexed = doc("indexed", col_a.id, DocumentStatus.indexed)
    other_col = doc("othercol", col_b.id, DocumentStatus.indexed)
    excluded = doc("excluded", col_a.id, DocumentStatus.excluded)
    deleted = doc("deleted", col_a.id, DocumentStatus.indexed, deleted=True)

    ids = {}
    for d, txt in [
        (indexed, "La coppia di serraggio della testata e di 85 Nm."),
        (other_col, "Contenuto di un'altra collezione."),
        (excluded, "Documento escluso dalla ricerca."),
        (deleted, "Documento cancellato."),
    ]:
        c = Chunk(document_id=d.id, page_start=3, page_end=3, text=txt, lang="it")
        db_session.add(c)
        db_session.flush()
        ids[d.title] = c.id
    db_session.commit()
    return {"chunk": ids, "col_a": col_a.id, "col_b": col_b.id}


def test_hydrate_returns_indexed_chunk_with_snippet(seeded: dict, db_session: Session) -> None:
    cid = seeded["chunk"]["indexed"]
    results = fuse_and_hydrate(db_session, [cid], [], "coppia di serraggio testata", 20)
    assert len(results) == 1
    r = results[0]
    assert r.chunk_id == cid
    assert r.page == 3
    assert r.title == "indexed"
    assert "<b>coppia</b>" in r.snippet_html and "<b>testata</b>" in r.snippet_html


def test_hydrate_drops_excluded_and_deleted(seeded: dict, db_session: Session) -> None:
    ids = [seeded["chunk"]["excluded"], seeded["chunk"]["deleted"], seeded["chunk"]["indexed"]]
    results = fuse_and_hydrate(db_session, ids, [], "documento", 20)
    assert [r.title for r in results] == ["indexed"]


def test_hydrate_enforces_collection_permission(seeded: dict, db_session: Session) -> None:
    ids = [seeded["chunk"]["othercol"], seeded["chunk"]["indexed"]]
    # user allowed only col_a -> othercol (col_b) filtered out
    results = fuse_and_hydrate(
        db_session, ids, [], "contenuto", 20, allowed_collection_ids=[seeded["col_a"]]
    )
    assert [r.title for r in results] == ["indexed"]


def test_hydrate_empty_allowed_returns_nothing(seeded: dict, db_session: Session) -> None:
    results = fuse_and_hydrate(
        db_session, [seeded["chunk"]["indexed"]], [], "x", 20, allowed_collection_ids=[]
    )
    assert results == []


def test_hydrate_preserves_rrf_order(seeded: dict, db_session: Session) -> None:
    a = seeded["chunk"]["indexed"]
    b = seeded["chunk"]["othercol"]
    # b ranked first in both lists -> should come before a
    results = fuse_and_hydrate(db_session, [b, a], [b, a], "contenuto coppia", 20)
    assert [r.chunk_id for r in results] == [b, a]
