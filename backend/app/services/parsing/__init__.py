"""Parsing service (SPEC §5): Docling-backed structure + text extraction with OCR fallback."""

from app.services.parsing.base import BBox, DocumentParser, ParsedBlock, ParsedDocument
from app.services.parsing.lang import detect_language
from app.services.parsing.textlayer import TextLayerReport, probe_text_layer

__all__ = [
    "BBox",
    "DocumentParser",
    "ParsedBlock",
    "ParsedDocument",
    "TextLayerReport",
    "detect_language",
    "get_parser",
    "probe_text_layer",
]


def get_parser() -> DocumentParser:
    """Return the default parser. Imports Docling lazily (keeps torch out of unit tests)."""
    from app.services.parsing.docling_parser import DoclingParser

    return DoclingParser()
