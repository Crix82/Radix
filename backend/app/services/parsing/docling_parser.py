"""Docling adapter (SPEC §2, §5). Imported lazily so unit tests never pull torch/docling.

Docling extracts structure (headings, tables) and text with provenance (page + bbox).
When the caller requests OCR (poor/absent text layer, decided by textlayer.probe), the
pipeline runs full-page Tesseract with the configured languages.
"""

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from app.core.config import get_settings
from app.services.parsing.base import BBox, ParsedBlock, ParsedDocument
from app.services.parsing.lang import detect_language

if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter

# Docling section-header/title labels that open a new heading level.
_HEADING_LABELS = {"section_header", "title"}


def _ocr_langs() -> list[str]:
    # OCR_LANGS is Tesseract syntax, e.g. "ita+eng+deu".
    return [part for part in get_settings().ocr_langs.split("+") if part]


@lru_cache(maxsize=2)
def _converter(ocr: bool) -> "DocumentConverter":
    """Build (and cache) a Docling converter. Cached because model load is expensive."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TesseractCliOcrOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline = PdfPipelineOptions()
    pipeline.do_table_structure = True
    pipeline.do_ocr = ocr
    if ocr:
        pipeline.ocr_options = TesseractCliOcrOptions(lang=_ocr_langs(), force_full_page_ocr=True)

    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline)}
    )


def warm_models() -> None:
    """Force the model downloads the *runtime* path performs, so a build can bake them in.

    SPEC §9 promises no external calls at runtime, but `docling-tools models download` populates
    /root/.cache/docling/models while docling's LayoutModel resolves through snapshot_download
    into the HuggingFace cache — different places. The M6 image parsed nothing under
    `--network none` for exactly this reason: the layout model was fetched from the Hub on the
    first document, so an air-gapped install broke on first use.

    Building the same converters the service builds means whatever this pulls is, by
    construction, what the runtime needs. Both OCR variants: they are cached separately.
    """
    from docling.datamodel.base_models import InputFormat

    for ocr in (False, True):
        _converter(ocr).initialize_pipeline(InputFormat.PDF)


def _normalized_bbox(prov: Any, pages: dict[int, Any]) -> BBox | None:
    """Convert a Docling provenance bbox to normalized top-left coordinates (0..1)."""
    try:
        page = pages.get(prov.page_no)
        if page is None or page.size is None:
            return None
        width, height = page.size.width, page.size.height
        if not width or not height:
            return None
        box = prov.bbox.to_top_left_origin(page_height=height)
        return BBox(
            x0=max(0.0, box.l / width),
            y0=max(0.0, box.t / height),
            x1=min(1.0, box.r / width),
            y1=min(1.0, box.b / height),
        )
    except Exception:  # noqa: BLE001 - a missing bbox must not fail the whole parse
        return None


class DoclingParser:
    """Concrete DocumentParser backed by Docling."""

    def parse(self, path: str, ocr: bool) -> ParsedDocument:
        result = _converter(ocr).convert(path)
        doc = result.document
        pages = dict(doc.pages) if doc.pages else {}

        blocks: list[ParsedBlock] = []
        heading_stack: list[tuple[int, str]] = []
        for item, level in doc.iterate_items():
            text = (getattr(item, "text", "") or "").strip()
            if not text:
                continue
            label = str(getattr(item, "label", "")).split(".")[-1].lower()
            is_heading = label in _HEADING_LABELS

            if is_heading:
                heading_stack = [(lv, t) for lv, t in heading_stack if lv < level]
                heading_stack.append((level, text))

            prov = getattr(item, "prov", None)
            first = prov[0] if prov else None
            page_no = getattr(first, "page_no", 1) if first else 1
            bbox = _normalized_bbox(first, pages) if first else None
            blocks.append(
                ParsedBlock(
                    text=text,
                    page=page_no,
                    bbox=bbox,
                    heading_path=tuple(t for _, t in heading_stack),
                    is_heading=is_heading,
                )
            )

        lang = detect_language(" ".join(b.text for b in blocks[:80]))
        page_count = len(pages) or (max((b.page for b in blocks), default=1))
        return ParsedDocument(lang=lang, page_count=page_count, blocks=blocks, used_ocr=ocr)
