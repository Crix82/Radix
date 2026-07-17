"""Normalized parser output, shared by the Docling adapter and the chunker.

Keeping this model independent of Docling means the chunking logic (and its tests)
never import torch/docling: unit tests build ParsedDocument by hand.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class BBox:
    """Bounding box in normalized page coordinates (0..1), origin at top-left."""

    x0: float
    y0: float
    x1: float
    y1: float

    def as_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass
class ParsedBlock:
    """One text block with its provenance (page + bbox) and heading context."""

    text: str
    page: int  # 1-based page number
    bbox: BBox | None = None
    heading_path: tuple[str, ...] = ()  # e.g. ("Section 4. Maintenance", "4.2 Cylinder head bolts")
    is_heading: bool = False


@dataclass
class ParsedDocument:
    lang: str  # detected document language: it | en | de | simple
    page_count: int
    blocks: list[ParsedBlock] = field(default_factory=list)
    used_ocr: bool = False


class DocumentParser(Protocol):
    """Parses an original file into the normalized structure above (SPEC §5, Parse stage)."""

    def parse(self, path: str, ocr: bool) -> ParsedDocument: ...
