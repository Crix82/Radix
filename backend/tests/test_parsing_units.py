from pathlib import Path

from app.services.parsing.errors import actionable_message
from app.services.parsing.lang import detect_language
from app.services.parsing.textlayer import probe_text_layer
from tests.conftest import FIXTURES_DIR


def test_detect_italian() -> None:
    assert detect_language("La coppia di serraggio della testata e di 85 Nm per ogni vite.") == "it"


def test_detect_english() -> None:
    assert detect_language("Tighten the cylinder head bolts to a torque of 85 Nm each.") == "en"


def test_detect_german() -> None:
    assert (
        detect_language("Der Hydraulikoelstand ist woechentlich zu pruefen und zu ergaenzen.")
        == "de"
    )


def test_detect_falls_back_to_simple() -> None:
    assert detect_language("XZ 4471 ..... ---") == "simple"
    assert detect_language("") == "simple"


def test_probe_born_digital_pdf_has_text_layer() -> None:
    report = probe_text_layer(FIXTURES_DIR / "RS-30_instruction_manual.pdf")
    assert report.page_count == 2
    assert report.total_chars > 100
    assert report.needs_ocr is False


def test_probe_scanned_pdf_needs_ocr() -> None:
    scanned = FIXTURES_DIR / "scansione_ita_manutenzione.pdf"
    report = probe_text_layer(scanned)
    assert report.total_chars == 0
    assert report.needs_ocr is True


def test_actionable_messages() -> None:
    assert (
        actionable_message(RuntimeError("PDFium: file is password protected"))
        == "PDF protetto da password"
    )
    assert (
        actionable_message(ValueError("could not open: No such file"))
        == "File original non trovato nel repository"
    )
    assert actionable_message(Exception("boom")) == "Errore durante l'elaborazione del documento"


def test_scanned_fixture_exists() -> None:
    assert (FIXTURES_DIR / "scansione_ita_manutenzione.pdf").is_file()
    assert isinstance(FIXTURES_DIR, Path)


# --- Docling adapter: tables and heading hierarchy (no Docling needed: duck-typed items) ---

from types import SimpleNamespace  # noqa: E402

from app.services.parsing.docling_parser import (  # noqa: E402
    blocks_from_document,
    compact_table,
    heading_level,
    item_text,
)


class _Table:
    label = "table"
    text = ""

    def __init__(self, markdown: str) -> None:
        self._md = markdown
        self.prov = [SimpleNamespace(page_no=24, bbox=None)]

    def export_to_markdown(self, doc: object) -> str:
        return self._md


def _item(label: str, text: str, page: int = 1) -> SimpleNamespace:
    return SimpleNamespace(label=label, text=text, prov=[SimpleNamespace(page_no=page, bbox=None)])


def _doc(items: list) -> SimpleNamespace:
    return SimpleNamespace(pages={}, iterate_items=lambda: [(it, 1) for it in items])


def test_numbered_heading_level_is_its_depth() -> None:
    assert heading_level("2.5 Dry-Type Transformers", 1, []) == 2
    assert heading_level("2.5.1 Transformer Taps", 1, []) == 3
    assert heading_level("3. Distribution", 1, []) == 1


def test_unnumbered_heading_nests_under_numbered_section() -> None:
    stack = [(2, "2.5 Dry-Type Transformers")]
    assert heading_level("References", 1, stack) == 3
    assert heading_level("Introduction", 1, []) == 1  # no numbering: Docling's level


def test_years_and_quantities_are_not_section_numbers() -> None:
    assert heading_level("2004 Edition", 1, []) == 1
    assert heading_level("100 MVA and above", 1, []) == 1


def test_table_is_exported_as_compact_markdown() -> None:
    md = "| Hot spot temperature rise     | 80°C      |\n|---------------------------|-------|"
    expected = "| Hot spot temperature rise | 80°C |\n|---|---|"
    assert item_text(_Table(md), doc=None) == expected


def test_compact_table_drops_blank_lines() -> None:
    assert compact_table("| a   | b |\n\n| 1 | 2   |") == "| a | b |\n| 1 | 2 |"


def test_blocks_keep_tables_and_the_parent_section() -> None:
    doc = _doc(
        [
            _item("section_header", "2.5 Dry-Type Transformers", 123),
            _item("section_header", "Paulette A. Payne", 123),
            _item("section_header", "2.5.1 Transformer Taps", 124),
            _item("text", "Typically two taps above and two taps below rated voltage.", 124),
            _Table("| Average winding temperature rise | 65°C |"),
        ]
    )
    blocks = blocks_from_document(doc)
    taps = blocks[3]
    assert taps.heading_path == ("2.5 Dry-Type Transformers", "2.5.1 Transformer Taps")
    assert blocks[-1].text == "| Average winding temperature rise | 65°C |"
    assert blocks[-1].page == 24
    assert blocks[-1].is_table and not taps.is_table
