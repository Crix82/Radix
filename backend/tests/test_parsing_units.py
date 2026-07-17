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
