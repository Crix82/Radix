"""RQ jobs for the indexing pipeline (SPEC §5).

Each stage is idempotent and re-runnable: discover -> parse -> (ocr) -> chunk -> embed -> index.
Implementations arrive with their milestones (M1: sync_source, M2: parse_document,
M3: embed_chunks / index_chunks); M0 ships the queue wiring only.
"""


def sync_source(source_id: int) -> None:
    raise NotImplementedError("Implemented in M1")


def parse_document(document_id: int) -> None:
    raise NotImplementedError("Implemented in M2")


def embed_chunks(document_id: int) -> None:
    raise NotImplementedError("Implemented in M3")


def index_chunks(document_id: int) -> None:
    raise NotImplementedError("Implemented in M3")
