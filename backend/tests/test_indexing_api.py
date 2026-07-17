from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Collection, Document, DocumentStatus, Source, SourceType, User


def seed(db: Session) -> dict[str, Document]:
    collection = Collection(name="Test")
    db.add(collection)
    db.flush()
    source = Source(
        type=SourceType.local, path="/mnt/docs", collection_id=collection.id, enabled=True
    )
    db.add(source)
    db.flush()

    def doc(rel_path: str, doc_status: DocumentStatus, **kwargs: object) -> Document:
        d = Document(
            source_id=source.id,
            collection_id=collection.id,
            rel_path=rel_path,
            content_hash=rel_path.ljust(64, "0"),
            size_bytes=1000,
            status=doc_status,
            **kwargs,
        )
        db.add(d)
        return d

    docs = {
        "indexed": doc("ok.pdf", DocumentStatus.indexed),
        "parsing": doc("parsing.pdf", DocumentStatus.parsing),
        "queued": doc("queued.pdf", DocumentStatus.queued),
        "error": doc("broken.pdf", DocumentStatus.error, error_msg="PDF protetto da password"),
    }
    db.commit()
    return docs


def test_indexing_requires_admin(client: TestClient, plain_user: User) -> None:
    assert client.get("/api/v1/indexing/stats").status_code == 403
    assert client.get("/api/v1/indexing/queue").status_code == 403


def test_stats_aggregates_by_status(client: TestClient, api_db: Session, admin_user: User) -> None:
    seed(api_db)
    body = client.get("/api/v1/indexing/stats").json()

    assert body["documents_indexed"] == 1
    assert body["queued"] == 2  # parsing + queued both count as pipeline work
    assert body["errors"] == 1
    assert body["space_used_bytes"] == 4000
    assert body["space_total_bytes"] == 500 * 1024**3


def test_queue_lists_documents_with_source_and_error(
    client: TestClient, api_db: Session, admin_user: User
) -> None:
    seed(api_db)
    body = client.get("/api/v1/indexing/queue").json()

    assert len(body) == 4
    by_path = {item["rel_path"]: item for item in body}
    assert by_path["broken.pdf"]["error_msg"] == "PDF protetto da password"
    assert by_path["ok.pdf"]["source_path"] == "/mnt/docs"
    assert by_path["ok.pdf"]["source_type"] == "local"


def test_exclude_document(client: TestClient, api_db: Session, admin_user: User) -> None:
    docs = seed(api_db)
    resp = client.post(f"/api/v1/documents/{docs['error'].id}/exclude")

    assert resp.status_code == 200
    assert resp.json()["status"] == "excluded"
    assert resp.json()["error_msg"] is None


def test_reindex_document(
    client: TestClient, api_db: Session, admin_user: User, enqueued: dict[str, list[int]]
) -> None:
    docs = seed(api_db)
    resp = client.post(f"/api/v1/documents/{docs['error'].id}/reindex")

    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    assert enqueued["parse"] == [docs["error"].id]


def test_document_actions_404_on_missing_or_deleted(
    client: TestClient, api_db: Session, admin_user: User
) -> None:
    assert client.post("/api/v1/documents/999/exclude").status_code == 404
