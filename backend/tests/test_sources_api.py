from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Collection, Document, Source, SourceType, User


def test_sources_require_auth(client: TestClient) -> None:
    assert client.get("/api/v1/sources").status_code == 401


def test_sources_require_admin(client: TestClient, plain_user: User) -> None:
    assert client.get("/api/v1/sources").status_code == 403
    assert client.post("/api/v1/sources", json={"type": "local", "path": "/x"}).status_code == 403


def test_create_local_source(
    client: TestClient,
    api_db: Session,
    admin_user: User,
    enqueued: dict[str, list[int]],
    tmp_path: Path,
) -> None:
    resp = client.post("/api/v1/sources", json={"type": "local", "path": str(tmp_path)})

    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "local" and body["enabled"] is True
    assert body["document_count"] == 0
    # default collection auto-created, sync enqueued, admin_change audited
    assert api_db.scalar(select(Collection).where(Collection.name == "Generale")) is not None
    assert enqueued["sync"] == [body["id"]]
    audit = api_db.scalar(select(AuditLog).where(AuditLog.action == "admin_change"))
    assert audit is not None and audit.object_type == "source"


def test_create_folder_source_without_path_is_422(client: TestClient, admin_user: User) -> None:
    assert client.post("/api/v1/sources", json={"type": "smb"}).status_code == 422
    assert client.post("/api/v1/sources", json={"type": "local", "path": " "}).status_code == 422


def test_create_upload_source_needs_no_path_and_no_sync(
    client: TestClient, admin_user: User, enqueued: dict[str, list[int]]
) -> None:
    resp = client.post("/api/v1/sources", json={"type": "upload"})
    assert resp.status_code == 201
    assert enqueued["sync"] == []


def test_toggle_source_enabled(
    client: TestClient, api_db: Session, admin_user: User, enqueued: dict[str, list[int]]
) -> None:
    source_id = client.post("/api/v1/sources", json={"type": "local", "path": "/x"}).json()["id"]
    enqueued["sync"].clear()

    resp = client.patch(f"/api/v1/sources/{source_id}", json={"enabled": False})
    assert resp.status_code == 200 and resp.json()["enabled"] is False
    assert enqueued["sync"] == []  # disabled sources are not synced

    resp = client.patch(f"/api/v1/sources/{source_id}", json={"enabled": True})
    assert resp.json()["enabled"] is True
    assert enqueued["sync"] == [source_id]  # re-enabling triggers a fresh sync


def test_delete_source_tombstones_documents(
    client: TestClient, api_db: Session, admin_user: User, enqueued: dict[str, list[int]]
) -> None:
    source_id = client.post("/api/v1/sources", json={"type": "local", "path": "/x"}).json()["id"]
    source = api_db.get(Source, source_id)
    assert source is not None
    doc = Document(
        source_id=source_id,
        collection_id=source.collection_id,
        rel_path="a.pdf",
        content_hash="0" * 64,
    )
    api_db.add(doc)
    api_db.commit()

    assert client.delete(f"/api/v1/sources/{source_id}").status_code == 204

    assert api_db.get(Source, source_id) is None
    api_db.refresh(doc)
    assert doc.deleted_at is not None  # tombstone survives the source


def test_list_sources_reports_live_document_count(
    client: TestClient, api_db: Session, admin_user: User, enqueued: dict[str, list[int]]
) -> None:
    source_id = client.post("/api/v1/sources", json={"type": "local", "path": "/x"}).json()["id"]
    source = api_db.get(Source, source_id)
    assert source is not None
    for i, deleted_at in enumerate([None, None, datetime.now(UTC)]):
        api_db.add(
            Document(
                source_id=source_id,
                collection_id=source.collection_id,
                rel_path=f"f{i}.pdf",
                content_hash=str(i) * 64,
                deleted_at=deleted_at,
            )
        )
    api_db.commit()

    body = client.get("/api/v1/sources").json()
    assert [s["document_count"] for s in body] == [2]


def test_upload_source_path_is_not_editable(
    client: TestClient, admin_user: User, enqueued: dict[str, list[int]]
) -> None:
    source_id = client.post("/api/v1/sources", json={"type": "upload"}).json()["id"]
    resp = client.patch(f"/api/v1/sources/{source_id}", json={"path": "/tmp/x"})
    assert resp.status_code == 200 and resp.json()["path"] == ""


def test_source_type_upload_enum_matches_spec() -> None:
    assert {t.value for t in SourceType} == {"smb", "local", "upload"}
