"""Real Docling + Tesseract pipeline. Skipped unless both are available (runs in Docker).

Covers the M2 DoD directly: RS-30 chunks carry valid bbox at a known page; the scanned
Italian fixture yields correct OCR text.
"""

import shutil

import pytest

from app.services.chunking import chunk_document
from tests.conftest import FIXTURES_DIR

docling = pytest.importorskip("docling", reason="Docling not installed (heavy; runs in Docker)")

needs_tesseract = pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="tesseract binary not available"
)


def _parse(name: str, ocr: bool):
    from app.services.parsing import get_parser

    return get_parser().parse(str(FIXTURES_DIR / name), ocr=ocr)


@pytest.mark.slow
def test_rs30_chunks_have_valid_bbox_at_known_page() -> None:
    parsed = _parse("RS-30_instruction_manual.pdf", ocr=False)
    assert parsed.lang in {"en", "it"}
    assert parsed.page_count == 2

    chunks = chunk_document(parsed)
    assert chunks, "expected at least one chunk"

    # The torque sentence lives on page 2; find the chunk covering it and check its bbox.
    hit = next((c for c in chunks if "85" in c.text and "torque" in c.text.lower()), None)
    assert hit is not None, "torque chunk not found"
    assert hit.page_start <= 2 <= hit.page_end
    boxes = hit.bboxes.get("2", [])
    assert boxes, "no bbox on page 2"
    for x0, y0, x1, y1 in boxes:
        assert 0.0 <= x0 < x1 <= 1.0
        assert 0.0 <= y0 < y1 <= 1.0


@pytest.mark.slow
@needs_tesseract
def test_scanned_italian_fixture_ocr_text() -> None:
    parsed = _parse("scansione_ita_manutenzione.pdf", ocr=True)
    assert parsed.used_ocr is True
    text = " ".join(b.text for b in parsed.blocks).lower()
    # Tesseract (ita) must recover the distinctive words from the scan.
    assert "manutenzione" in text
    assert "sicurezza" in text
