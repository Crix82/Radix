"""Docling adapter (SPEC §2, §5). Imported lazily so unit tests never pull torch/docling.

Docling extracts structure (headings, tables) and text with provenance (page + bbox).
When the caller requests OCR (poor/absent text layer, decided by textlayer.probe), the
pipeline runs full-page Tesseract with the configured languages.
"""

import re
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from app.core.config import get_settings
from app.services.parsing.base import BBox, ParsedBlock, ParsedDocument
from app.services.parsing.lang import detect_language

if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter

# Docling section-header/title labels that open a new heading level.
_HEADING_LABELS = {"section_header", "title"}

# "2.5", "2.5.1", "3." at the start of a heading: the depth of the number is the heading level.
# Chapter numbers stay at two digits so years and quantities ("2004 edition") never match.
_NUMBERED_HEADING_RE = re.compile(r"^(\d{1,2}(?:\.\d{1,3})*)\.?\s+\S")


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


def heading_level(text: str, docling_level: int, stack: list[tuple[int, str]]) -> int:
    """Level of a heading in the section tree.

    Docling gives every PDF section header the same level, so a chunk under "2.5.1 Transformer
    Taps" loses its chapter "2.5 Dry-Type Transformers" — exactly the words a question uses.
    Technical documents number their sections, so the number's depth is the level. An
    unnumbered heading (an author line, "References") nests under the current numbered section
    instead of wiping it; documents without numbering keep Docling's levels.
    """
    match = _NUMBERED_HEADING_RE.match(text)
    if match:
        return match.group(1).count(".") + 1
    if stack and _NUMBERED_HEADING_RE.match(stack[-1][1]):
        return stack[-1][0] + 1
    return docling_level


def compact_table(markdown: str) -> str:
    """Docling pads table cells to align columns: strip the padding, it is only spent tokens."""
    lines = []
    for line in markdown.splitlines():
        line = re.sub(r"-{3,}", "---", line)
        lines.append(re.sub(r" {2,}", " ", line).strip())
    return "\n".join(line for line in lines if line)


def item_text(item: Any, doc: Any) -> str:
    """Text of a Docling item. Tables carry no `text`: they are exported as a markdown table,
    otherwise their content (the values a question asks for) never reaches the index."""
    text = (getattr(item, "text", "") or "").strip()
    if text:
        return text
    if hasattr(item, "export_to_markdown") and "table" in str(getattr(item, "label", "")).lower():
        try:
            return compact_table(item.export_to_markdown(doc=doc))
        except Exception:  # noqa: BLE001 - a malformed table must not fail the whole parse
            return ""
    return ""


def blocks_from_document(doc: Any) -> list[ParsedBlock]:
    """Turn a Docling document into ParsedBlocks with page, bbox and heading path."""
    pages = dict(doc.pages) if doc.pages else {}
    blocks: list[ParsedBlock] = []
    heading_stack: list[tuple[int, str]] = []
    for item, level in doc.iterate_items():
        text = item_text(item, doc)
        if not text:
            continue
        label = str(getattr(item, "label", "")).split(".")[-1].lower()
        is_heading = label in _HEADING_LABELS
        is_table = label == "table"

        if is_heading:
            lv = heading_level(text, level, heading_stack)
            heading_stack = [(h_lv, t) for h_lv, t in heading_stack if h_lv < lv]
            heading_stack.append((lv, text))

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
                is_table=is_table,
            )
        )
    return blocks


class DoclingParser:
    """Concrete DocumentParser backed by Docling."""

    def parse(self, path: str, ocr: bool) -> ParsedDocument:
        result = _converter(ocr).convert(path)
        doc = result.document
        pages = dict(doc.pages) if doc.pages else {}
        blocks = blocks_from_document(doc)

        lang = detect_language(" ".join(b.text for b in blocks[:80]))
        page_count = len(pages) or (max((b.page for b in blocks), default=1))
        return ParsedDocument(lang=lang, page_count=page_count, blocks=blocks, used_ocr=ocr)
