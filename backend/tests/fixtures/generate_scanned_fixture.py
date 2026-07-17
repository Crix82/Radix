"""Generate the scanned Italian fixture used for the M2 OCR DoD.

A born-digital PDF (built with the proven generate_fixtures.build_pdf) is rasterized
at high scale (pypdfium2) and re-wrapped as an image-only PDF (Pillow), so it carries
NO text layer — exactly what triggers the OCR branch. The raster is of real Italian
text, so Tesseract (ita) recovers it.

Run from this directory:  python generate_scanned_fixture.py
"""

from pathlib import Path

import pypdfium2 as pdfium
from generate_fixtures import build_pdf
from PIL import Image

OUT_NAME = "scansione_ita_manutenzione.pdf"

# Clear, high-frequency Italian words → robust OCR. The test asserts a subset of these.
PAGE_LINES = [
    "MANUALE DI MANUTENZIONE",
    "Istruzioni per la sicurezza",
    "Controllare il livello dell olio ogni settimana",
    "Sostituire il filtro dopo cento ore di funzionamento",
    "Indossare sempre i dispositivi di protezione",
]


def main() -> None:
    pdf_bytes = build_pdf([PAGE_LINES])
    pdf = pdfium.PdfDocument(pdf_bytes)
    # Scale 4 → large glyphs; Tesseract is happiest well above 150 DPI.
    image: Image.Image = pdf[0].render(scale=4.0).to_pil().convert("RGB")
    pdf.close()
    out_path = Path(__file__).parent / OUT_NAME
    image.save(out_path, "PDF", resolution=200.0)  # single image → image-only PDF, no text layer
    print(f"wrote {OUT_NAME} ({out_path.stat().st_size} bytes, image-only)")


if __name__ == "__main__":
    main()
