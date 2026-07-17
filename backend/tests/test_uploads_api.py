import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, Source, SourceType, User
from app.services import ingest
from tests.conftest import FIXTURE_PDFS


def _upload(client: TestClient, filename: str, content: bytes) -> httpx.Response:
    return client.post("/api/v1/uploads", files=[("files", (filename, content, "application/pdf"))])


def test_uploads_require_admin(client: TestClient, plain_user: User) -> None:
    assert _upload(client, "a.pdf", b"x").status_code == 403


def test_upload_creates_document_and_singleton_source(
    client: TestClient, api_db: Session, admin_user: User, enqueued: dict[str, list[int]]
) -> None:
    content = FIXTURE_PDFS[0].read_bytes()
    resp = _upload(client, FIXTURE_PDFS[0].name, content)

    assert resp.status_code == 201
    body = resp.json()
    assert len(body["created"]) == 1 and body["unchanged"] == 0
    doc = api_db.get(Document, body["created"][0]["id"])
    assert doc is not None
    assert ingest.original_path(doc).is_file()
    assert enqueued["parse"] == [doc.id]
    source = api_db.scalar(select(Source).where(Source.type == SourceType.upload))
    assert source is not None and doc.source_id == source.id


def test_reupload_same_content_is_unchanged(
    client: TestClient, api_db: Session, admin_user: User, enqueued: dict[str, list[int]]
) -> None:
    content = FIXTURE_PDFS[0].read_bytes()
    _upload(client, FIXTURE_PDFS[0].name, content)
    resp = _upload(client, FIXTURE_PDFS[0].name, content)

    body = resp.json()
    assert body["created"] == [] and body["unchanged"] == 1
    assert len(enqueued["parse"]) == 1
    # a second upload source must not appear
    sources = api_db.scalars(select(Source).where(Source.type == SourceType.upload)).all()
    assert len(sources) == 1


def test_upload_unsupported_extension_is_422(client: TestClient, admin_user: User) -> None:
    resp = client.post(
        "/api/v1/uploads", files=[("files", ("virus.exe", b"MZ", "application/octet-stream"))]
    )
    assert resp.status_code == 422


def test_upload_strips_client_directories(
    client: TestClient, api_db: Session, admin_user: User, enqueued: dict[str, list[int]]
) -> None:
    resp = _upload(client, "../../etc/passwd.pdf", FIXTURE_PDFS[0].read_bytes())
    body = resp.json()
    assert body["created"][0]["rel_path"] == "passwd.pdf"
