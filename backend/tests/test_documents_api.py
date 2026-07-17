import shutil

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Collection, Document, DocumentStatus, Source, SourceType, User
from app.services import ingest
from tests.conftest import FIXTURES_DIR


def _seed_pdf_document(db: Session, rel_path: str = "RS-30_instruction_manual.pdf") -> Document:
    collection = Collection(name="C")
    db.add(collection)
    db.flush()
    source = Source(type=SourceType.local, path="/mnt/x", collection_id=collection.id)
    db.add(source)
    db.flush()
    doc = Document(
        source_id=source.id,
        collection_id=collection.id,
        rel_path=rel_path,
        content_hash="0" * 64,
        status=DocumentStatus.chunking,
        pages=2,
        lang="en",
    )
    db.add(doc)
    db.commit()
    # place the original where the renderer expects it
    dest = ingest.original_path(doc)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(FIXTURES_DIR / "RS-30_instruction_manual.pdf", dest)
    return doc


def test_get_document_requires_auth(client: TestClient, api_db: Session) -> None:
    assert client.get("/api/v1/documents/1").status_code == 401


def test_get_document_metadata(client: TestClient, api_db: Session, admin_user: User) -> None:
    doc = _seed_pdf_document(api_db)
    body = client.get(f"/api/v1/documents/{doc.id}").json()
    assert body["pages"] == 2 and body["lang"] == "en"
    assert body["status"] == "chunking"


def test_get_document_404(client: TestClient, api_db: Session, admin_user: User) -> None:
    assert client.get("/api/v1/documents/999").status_code == 404


def test_page_png_renders_and_caches(client: TestClient, api_db: Session, admin_user: User) -> None:
    doc = _seed_pdf_document(api_db)
    resp = client.get(f"/api/v1/documents/{doc.id}/pages/1.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"
    # cache file exists on disk
    from app.services.rendering import pagecache_dir

    assert (pagecache_dir() / str(doc.id) / "1.png").is_file()


def test_page_png_out_of_range_404(client: TestClient, api_db: Session, admin_user: User) -> None:
    doc = _seed_pdf_document(api_db)
    assert client.get(f"/api/v1/documents/{doc.id}/pages/9.png").status_code == 404


def test_page_png_non_pdf_415(client: TestClient, api_db: Session, admin_user: User) -> None:
    doc = _seed_pdf_document(api_db, rel_path="report.docx")
    assert client.get(f"/api/v1/documents/{doc.id}/pages/1.png").status_code == 415


def test_page_png_requires_auth(client: TestClient, api_db: Session) -> None:
    assert client.get("/api/v1/documents/1/pages/1.png").status_code == 401
