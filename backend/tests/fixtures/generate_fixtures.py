"""Generate the 5 fixture PDFs used across milestones (M1 discover, M2 parse, M3 search).

Dependency-free: writes minimal but valid single-xref PDFs with Helvetica text.
Run from this directory to (re)create the checked-in fixtures:

    python generate_fixtures.py
"""

from pathlib import Path

PAGE_WIDTH = 595
PAGE_HEIGHT = 842


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _page_stream(lines: list[str]) -> bytes:
    ops = ["BT", "/F1 12 Tf", f"50 {PAGE_HEIGHT - 60} Td", "16 TL"]
    for i, line in enumerate(lines):
        if i:
            ops.append("T*")
        ops.append(f"({_escape(line)}) Tj")
    ops.append("ET")
    return "\n".join(ops).encode("latin-1", errors="replace")


def build_pdf(pages: list[list[str]]) -> bytes:
    """Assemble a valid PDF: catalog, page tree, one font, one content stream per page."""
    objects: list[bytes] = []  # 1-indexed object bodies, without "N 0 obj" wrapper

    n_pages = len(pages)
    catalog_id = 1
    pages_id = 2
    font_id = 3
    first_page_id = 4  # page objects, then content streams after them

    kids = " ".join(f"{first_page_id + i} 0 R" for i in range(n_pages))
    objects.append(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    content_ids = [first_page_id + n_pages + i for i in range(n_pages)]
    for i in range(n_pages):
        objects.append(
            (
                f"<< /Type /Page /Parent {pages_id} 0 R "
                f"/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                f"/Contents {content_ids[i]} 0 R >>"
            ).encode()
        )
    for lines in pages:
        stream = _page_stream(lines)
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


FIXTURES: dict[str, list[list[str]]] = {
    "RS-30_instruction_manual.pdf": [
        [
            "RS-30 Rotary Screw Compressor - Instruction Manual",
            "Section 1. Safety instructions",
            "Read this manual before operating the RS-30 unit.",
        ],
        [
            "Section 4. Maintenance",
            "4.2 Cylinder head bolts",
            "La coppia di serraggio della testata e di 85 Nm.",
            "Tighten the cylinder head bolts to a torque of 85 Nm.",
        ],
    ],
    "L12_manuale_operatore.pdf": [
        [
            "L12 - Manuale operatore",
            "Capitolo 1. Avvertenze generali",
            "Indossare sempre i dispositivi di protezione individuale.",
        ],
        [
            "Capitolo 3. Avviamento",
            "Premere il pulsante verde per avviare il ciclo automatico.",
        ],
    ],
    "HP-200_wartungshandbuch.pdf": [
        [
            "HP-200 Hydraulikpresse - Wartungshandbuch",
            "Kapitel 2. Wartungsplan",
            "Der Hydraulikoelstand ist woechentlich zu pruefen.",
        ],
    ],
    "catalogo_ricambi_2024.pdf": [
        [
            "Catalogo ricambi 2024",
            "Codice 10-442: guarnizione testata RS-30",
            "Codice 10-518: filtro olio L12",
        ],
    ],
    "formulazione_EP-204.pdf": [
        [
            "Formulazione EP-204 - Scheda tecnica",
            "Resina epossidica bicomponente per incollaggi strutturali.",
            "Rapporto di miscelazione 2:1 in peso.",
        ],
    ],
}


def main() -> None:
    out_dir = Path(__file__).parent
    for name, pages in FIXTURES.items():
        (out_dir / name).write_bytes(build_pdf(pages))
        print(f"wrote {name}")


if __name__ == "__main__":
    main()
