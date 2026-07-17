"""Structure-aware chunking (SPEC §5, Chunk stage).

Groups parsed blocks by their heading path, then packs each group into chunks of
~400-600 tokens with ~60 tokens of overlap between consecutive chunks. Every chunk
carries page_start/end, the union of its blocks' bboxes (normalized 0..1, keyed by
page), the heading path and the language.

Pure and Docling-free so it is fully unit-testable.
"""

from dataclasses import dataclass, field
from itertools import groupby

from app.services.parsing.base import ParsedBlock, ParsedDocument

TARGET_TOKENS = 500
MAX_TOKENS = 600
OVERLAP_TOKENS = 60
# Rough token estimate: ~4 characters per token. Good enough for sizing; the real
# bge-m3 tokenizer is only needed at embedding time (M3), not for chunk boundaries.
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass
class Chunk:
    text: str
    page_start: int
    page_end: int
    heading_path: str | None
    bboxes: dict[str, list[list[float]]]  # page number (str) -> list of [x0,y0,x1,y1]
    lang: str


@dataclass
class _Accumulator:
    blocks: list[ParsedBlock] = field(default_factory=list)
    tokens: int = 0

    def add(self, block: ParsedBlock, tokens: int) -> None:
        self.blocks.append(block)
        self.tokens += tokens

    def clear(self) -> None:
        self.blocks = []
        self.tokens = 0


def _heading_str(heading_path: tuple[str, ...]) -> str | None:
    return " › ".join(heading_path) if heading_path else None


def _finish(blocks: list[ParsedBlock], lang: str) -> Chunk:
    pages = [b.page for b in blocks]
    bboxes: dict[str, list[list[float]]] = {}
    for block in blocks:
        if block.bbox is not None:
            bboxes.setdefault(str(block.page), []).append(block.bbox.as_list())
    return Chunk(
        text="\n".join(b.text for b in blocks).strip(),
        page_start=min(pages),
        page_end=max(pages),
        heading_path=_heading_str(blocks[0].heading_path),
        bboxes=bboxes,
        lang=lang,
    )


def _overlap_tail(blocks: list[ParsedBlock]) -> list[ParsedBlock]:
    """Trailing blocks worth ~OVERLAP_TOKENS, carried into the next chunk for continuity."""
    tail: list[ParsedBlock] = []
    tokens = 0
    for block in reversed(blocks):
        if tokens >= OVERLAP_TOKENS:
            break
        tail.insert(0, block)
        tokens += estimate_tokens(block.text)
    return tail


def _seed_overlap(acc: _Accumulator, previous: list[ParsedBlock]) -> None:
    acc.clear()
    for block in _overlap_tail(previous):
        acc.add(block, estimate_tokens(block.text))


def _chunk_group(blocks: list[ParsedBlock], lang: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    acc = _Accumulator()
    new_since_emit = False
    for block in blocks:
        tokens = estimate_tokens(block.text)
        # A single oversized block still becomes its own chunk rather than being split
        # mid-sentence: provenance (page/bbox) must stay intact.
        if acc.tokens and acc.tokens + tokens > MAX_TOKENS:
            chunks.append(_finish(acc.blocks, lang))
            _seed_overlap(acc, acc.blocks)
            new_since_emit = False
        acc.add(block, tokens)
        new_since_emit = True
        if acc.tokens >= TARGET_TOKENS:
            chunks.append(_finish(acc.blocks, lang))
            _seed_overlap(acc, acc.blocks)
            new_since_emit = False
    # Flush the remainder, unless it is only the overlap already carried by the last chunk.
    if acc.blocks and new_since_emit and "\n".join(b.text for b in acc.blocks).strip():
        chunks.append(_finish(acc.blocks, lang))
    return chunks


def chunk_document(doc: ParsedDocument) -> list[Chunk]:
    """Split a parsed document into chunks, grouped by heading path."""
    chunks: list[Chunk] = []
    for _, group in groupby(doc.blocks, key=lambda b: b.heading_path):
        group_blocks = [b for b in group if b.text.strip()]
        if group_blocks:
            chunks.extend(_chunk_group(group_blocks, doc.lang))
    return chunks
