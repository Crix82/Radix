from app.services.chunking import (
    MAX_TOKENS,
    OVERLAP_TOKENS,
    TARGET_TOKENS,
    chunk_document,
    estimate_tokens,
)
from app.services.parsing.base import BBox, ParsedBlock, ParsedDocument


def block(
    text: str, page: int = 1, heading: tuple[str, ...] = (), bbox: BBox | None = None
) -> ParsedBlock:
    return ParsedBlock(text=text, page=page, heading_path=heading, bbox=bbox)


def para(tokens: int) -> str:
    # ~tokens tokens worth of text (estimate is chars // 4).
    return "parola " * (tokens * 4 // len("parola "))


def test_short_document_is_one_chunk() -> None:
    doc = ParsedDocument(
        lang="it",
        page_count=1,
        blocks=[block("Titolo", heading=("Titolo",)), block("Testo breve.", heading=("Titolo",))],
    )
    chunks = chunk_document(doc)
    assert len(chunks) == 1
    assert chunks[0].heading_path == "Titolo"
    assert chunks[0].page_start == 1 and chunks[0].page_end == 1
    assert chunks[0].lang == "it"


def test_long_group_splits_near_target_with_overlap() -> None:
    heading = ("Cap 1",)
    blocks = [block(para(120), heading=heading) for _ in range(10)]  # ~1200 tokens
    doc = ParsedDocument(lang="it", page_count=1, blocks=blocks)
    chunks = chunk_document(doc)

    assert len(chunks) >= 2
    for c in chunks:
        assert estimate_tokens(c.text) <= MAX_TOKENS + 120  # last block may push slightly over
    # consecutive chunks share overlapping text (continuity)
    assert any(chunks[i].text.split()[-1] in chunks[i + 1].text for i in range(len(chunks) - 1))


def test_chunks_split_by_heading_path() -> None:
    doc = ParsedDocument(
        lang="it",
        page_count=2,
        blocks=[
            block("A body", page=1, heading=("Sez A",)),
            block("B body", page=2, heading=("Sez B",)),
        ],
    )
    chunks = chunk_document(doc)
    assert {c.heading_path for c in chunks} == {"Sez A", "Sez B"}


def test_bboxes_grouped_by_page() -> None:
    doc = ParsedDocument(
        lang="en",
        page_count=2,
        blocks=[
            block("x", page=1, heading=("H",), bbox=BBox(0.1, 0.1, 0.5, 0.2)),
            block("y", page=2, heading=("H",), bbox=BBox(0.2, 0.3, 0.6, 0.4)),
        ],
    )
    chunk = chunk_document(doc)[0]
    assert set(chunk.bboxes) == {"1", "2"}
    assert chunk.bboxes["1"] == [[0.1, 0.1, 0.5, 0.2]]
    assert chunk.page_start == 1 and chunk.page_end == 2


def test_heading_path_joined_with_separator() -> None:
    doc = ParsedDocument(
        lang="it",
        page_count=1,
        blocks=[block("body", heading=("Sezione 4", "4.2 Bulloni"))],
    )
    assert chunk_document(doc)[0].heading_path == "Sezione 4 › 4.2 Bulloni"


def test_empty_and_whitespace_blocks_are_dropped() -> None:
    doc = ParsedDocument(
        lang="it",
        page_count=1,
        blocks=[block("   ", heading=("H",)), block("reale", heading=("H",))],
    )
    chunks = chunk_document(doc)
    assert len(chunks) == 1 and chunks[0].text == "reale"


def test_overlap_constant_is_smaller_than_target() -> None:
    assert OVERLAP_TOKENS < TARGET_TOKENS <= MAX_TOKENS
