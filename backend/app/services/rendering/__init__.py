"""Page rendering service (SPEC §5): pypdfium2 → PNG per page, lazily cached.

PDFium (pypdfium2) is used deliberately; PyMuPDF is banned (AGPL, SPEC §14).
Rendering is PDF-only in v1; other formats have no page image.
"""

from pathlib import Path

import pypdfium2 as pdfium

from app.core.config import get_settings

# 72 DPI is the PDF user-space default; scale 2.0 ≈ 144 DPI, crisp enough for the viewer.
RENDER_SCALE = 2.0


class PageOutOfRange(Exception):
    """Requested page number is outside the document."""


def pagecache_dir() -> Path:
    return Path(get_settings().data_dir) / "pagecache"


def page_count(pdf_path: Path) -> int:
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        return len(pdf)
    finally:
        pdf.close()


def _render_page_png(pdf_path: Path, page_number: int, dest: Path) -> None:
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        if page_number < 1 or page_number > len(pdf):
            raise PageOutOfRange(f"page {page_number} not in 1..{len(pdf)}")
        page = pdf[page_number - 1]
        image = page.render(scale=RENDER_SCALE).to_pil()
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".png.tmp")
        image.save(tmp, format="PNG")
        tmp.replace(dest)  # atomic: concurrent readers never see a half-written file
    finally:
        pdf.close()


def render_page(document_id: int, pdf_path: Path, page_number: int) -> Path:
    """Return the cached PNG for a page, rendering it on first request (SPEC §5)."""
    dest = pagecache_dir() / str(document_id) / f"{page_number}.png"
    if not dest.exists():
        _render_page_png(pdf_path, page_number, dest)
    return dest
