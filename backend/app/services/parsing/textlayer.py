"""Text-layer quality probe (SPEC §5): decide whether a PDF needs the OCR branch.

A born-digital PDF carries an extractable text layer; a scan carries none (or a poor
one). We extract text per page with pypdfium2 and flag OCR when the average extracted
character count per page falls below a threshold.
"""

from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium

# Below this many extracted characters per page on average, treat the layer as absent/poor.
MIN_CHARS_PER_PAGE = 40


@dataclass
class TextLayerReport:
    page_count: int
    total_chars: int
    needs_ocr: bool

    @property
    def avg_chars_per_page(self) -> float:
        return self.total_chars / self.page_count if self.page_count else 0.0


def probe_text_layer(pdf_path: Path) -> TextLayerReport:
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page_count = len(pdf)
        total = 0
        for i in range(page_count):
            page = pdf[i]
            textpage = page.get_textpage()
            try:
                total += len(textpage.get_text_range().strip())
            finally:
                textpage.close()
        avg = total / page_count if page_count else 0.0
        return TextLayerReport(
            page_count=page_count, total_chars=total, needs_ocr=avg < MIN_CHARS_PER_PAGE
        )
    finally:
        pdf.close()
