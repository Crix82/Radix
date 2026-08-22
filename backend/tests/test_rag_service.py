from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.models import Chunk, Collection, Document, DocumentStatus, Source, SourceType
from app.services import rag
from app.services.rag.prompts import REFUSAL_PHRASE
from tests.conftest import create_sqlite_chunks_table


class FakeProvider:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.received: list[dict[str, str]] | None = None

    def complete(self, messages, stream=True, json_schema=None) -> Iterator[str]:
        self.received = messages
        yield from self.tokens


class FakeEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.0, 0.0, 0.0]


@pytest.fixture
def corpus(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    create_sqlite_chunks_table(db_session.get_bind())
    col = Collection(name="C")
    db_session.add(col)
    db_session.flush()
    src = Source(type=SourceType.local, path="/x", collection_id=col.id)
    db_session.add(src)
    db_session.flush()
    ids: dict[str, int] = {}
    for key, title, page, txt in [
        ("rs30", "RS-30 manual", 142, "Tighten the cylinder head bolts to 85 Nm."),
        ("boll", "Bollettino RS", 8, "Verifica della coppia di serraggio della testata."),
    ]:
        doc = Document(
            source_id=src.id,
            collection_id=col.id,
            rel_path=f"{key}.pdf",
            title=title,
            content_hash=key.ljust(64, "0"),
            status=DocumentStatus.indexed,
            lang="it",
        )
        db_session.add(doc)
        db_session.flush()
        ch = Chunk(
            document_id=doc.id,
            page_start=page,
            page_end=page,
            text=txt,
            lang="it",
            bboxes={str(page): [[0.1, 0.1, 0.5, 0.2]]},
        )
        db_session.add(ch)
        db_session.flush()
        ids[key] = ch.id
    db_session.commit()
    return ids


def _wire(monkeypatch, dense: list[tuple[int, float]], fts: list[int]) -> None:
    monkeypatch.setattr("app.services.vectorstore.search", lambda *a, **k: list(dense))
    monkeypatch.setattr("app.services.rag.fts_search", lambda *a, **k: list(fts))


def test_retrieve_hydrates_context(corpus, db_session, monkeypatch) -> None:
    _wire(monkeypatch, dense=[(corpus["boll"], 0.71), (corpus["rs30"], 0.63)], fts=[corpus["boll"]])
    r = rag.retrieve(db_session, FakeEmbedder(), object(), "coppia di serraggio testata", None)
    assert r.max_dense_score == 0.71
    assert [c.n for c in r.chunks] == [1, 2]
    assert r.chunks[0].chunk_id == corpus["boll"]
    assert r.chunks[0].page == 8
    assert r.chunks[0].bboxes == {"8": [[0.1, 0.1, 0.5, 0.2]]}


@pytest.fixture
def invoice_doc(db_session: Session) -> list[int]:
    """One document split into three chunks in reading order (monotonic ids): payee header,
    the total line, then notes — the invoice-style case where a fact straddles chunks."""
    create_sqlite_chunks_table(db_session.get_bind())
    col = Collection(name="Fatture")
    db_session.add(col)
    db_session.flush()
    src = Source(type=SourceType.local, path="/f", collection_id=col.id)
    db_session.add(src)
    db_session.flush()
    doc = Document(
        source_id=src.id,
        collection_id=col.id,
        rel_path="fattura.pdf",
        title="Fattura",
        content_hash="fattura".ljust(64, "0"),
        status=DocumentStatus.indexed,
        lang="it",
    )
    db_session.add(doc)
    db_session.flush()
    ids: list[int] = []
    for page, txt in [
        (1, "GERUNDA, CRISTIANO - C.F. GRNCST82D20B563N"),
        (1, "Fattura Numero 5 - TOTALE 8.790,95 (EUR)"),
        (2, "Condizioni di pagamento a 30 giorni."),
    ]:
        ch = Chunk(document_id=doc.id, page_start=page, page_end=page, text=txt, lang="it")
        db_session.add(ch)
        db_session.flush()
        ids.append(ch.id)
    db_session.commit()
    return ids


def test_retrieve_expands_to_neighbors(invoice_doc, db_session, monkeypatch) -> None:
    header, total, _notes = invoice_doc
    # Only the payee-header chunk is retrieved; the amount lives in the next chunk.
    _wire(monkeypatch, dense=[(header, 0.61)], fts=[])
    r = rag.retrieve(db_session, FakeEmbedder(), object(), "importo fattura gerunda", None)
    assert [c.chunk_id for c in r.chunks] == [header, total]  # ±1 neighbour brings in the total
    assert [c.n for c in r.chunks] == [1, 2]
    assert any("8.790,95" in c.text for c in r.chunks)


def test_neighbor_expansion_dedupes_shared_neighbor(invoice_doc, db_session, monkeypatch) -> None:
    header, total, notes = invoice_doc
    # header's window is [header, total]; notes' window is [total, notes] — total is shared.
    _wire(monkeypatch, dense=[(header, 0.6), (notes, 0.5)], fts=[])
    r = rag.retrieve(db_session, FakeEmbedder(), object(), "q", None)
    got = [c.chunk_id for c in r.chunks]
    assert got == [header, total, notes]
    assert len(got) == len(set(got))  # the shared neighbour appears once


def test_answer_stream_refuses_below_threshold(corpus, db_session, monkeypatch) -> None:
    _wire(monkeypatch, dense=[(corpus["boll"], 0.30)], fts=[])
    provider = FakeProvider(["should not be called"])
    events = list(
        rag.answer_stream(
            db_session,
            FakeEmbedder(),
            object(),
            provider,
            [{"role": "user", "content": "modello RS-55?"}],
            allowed_collection_ids=None,
            refusal_threshold=0.55,
        )
    )
    assert len(events) == 1
    kind, result = events[0]
    assert kind == "final"
    assert result.refusal is True
    assert result.answer_md == REFUSAL_PHRASE
    assert provider.received is None  # LLM never called on refusal


def test_answer_stream_streams_and_cites(corpus, db_session, monkeypatch) -> None:
    _wire(monkeypatch, dense=[(corpus["boll"], 0.72), (corpus["rs30"], 0.64)], fts=[corpus["boll"]])
    provider = FakeProvider(["La coppia è ", "85 Nm ", "[1]."])
    events = list(
        rag.answer_stream(
            db_session,
            FakeEmbedder(),
            object(),
            provider,
            [{"role": "user", "content": "coppia di serraggio testata?"}],
            allowed_collection_ids=None,
            refusal_threshold=0.55,
        )
    )
    tokens = [p for k, p in events if k == "token"]
    assert "".join(tokens) == "La coppia è 85 Nm [1]."
    kind, result = events[-1]
    assert kind == "final" and result.refusal is False
    assert result.answer_md == "La coppia è 85 Nm [1]."
    assert [c.n for c in result.citations] == [1]
    assert result.citations[0].chunk_id == corpus["boll"]
    # the LLM saw the grounding system prompt + context
    assert provider.received[0]["role"] == "system"
    assert "[1]" in provider.received[-1]["content"]


def test_answer_stream_refuses_when_no_chunks(corpus, db_session, monkeypatch) -> None:
    _wire(monkeypatch, dense=[], fts=[])
    events = list(
        rag.answer_stream(
            db_session,
            FakeEmbedder(),
            object(),
            FakeProvider([]),
            [{"role": "user", "content": "domanda"}],
            allowed_collection_ids=None,
            refusal_threshold=0.55,
        )
    )
    assert events[-1][1].refusal is True


def test_answer_stream_flags_a_model_emitted_refusal(corpus, db_session, monkeypatch) -> None:
    """Retrieval passes the threshold but the model itself says it has no answer.

    Observed on the real stack: the turn was flagged refusal=False and parse_citations'
    no-markers fallback attached all 16 context chunks, so a refusal rendered with a full
    Fonti panel — and, once conversations are persisted, stayed that way in the history.
    """
    _wire(monkeypatch, dense=[(corpus["boll"], 0.9)], fts=[corpus["boll"]])
    events = list(
        rag.answer_stream(
            db_session,
            FakeEmbedder(),
            object(),
            FakeProvider(["Non presente nella ", "documentazione indicizzata."]),
            [{"role": "user", "content": "domanda fuori contesto"}],
            allowed_collection_ids=None,
            refusal_threshold=0.55,
        )
    )
    final = events[-1][1]
    assert final.refusal is True
    assert final.citations == []
    assert final.answer_md == REFUSAL_PHRASE
    # the tokens still streamed — the model was called, unlike a threshold refusal
    assert [kind for kind, _ in events].count("token") == 2


def test_answer_stream_flags_a_refusal_followed_by_an_explanation(
    corpus, db_session, monkeypatch
) -> None:
    """Seen on the live stack with qwen3.5: the exact phrase, then a paragraph explaining what
    the context does cover, with a [1] citation to the *other* model. That is a refusal."""
    _wire(monkeypatch, dense=[(corpus["rs30"], 0.66)], fts=[corpus["rs30"]])
    tokens = [
        "Non presente nella documentazione indicizzata.",
        "\n\nLa documentazione specifica che la coppia dell'RS-30 è 85 Nm [1], ",
        "ma non contiene informazioni sul modello RS-55.",
    ]
    events = list(
        rag.answer_stream(
            db_session,
            FakeEmbedder(),
            object(),
            FakeProvider(tokens),
            [{"role": "user", "content": "coppia di serraggio RS-55?"}],
            allowed_collection_ids=None,
            refusal_threshold=0.55,
        )
    )
    final = events[-1][1]
    assert final.refusal is True and final.citations == []
    assert final.answer_md == REFUSAL_PHRASE  # normalized: the explanation is dropped


def test_answer_stream_empty_allowed_refuses(corpus, db_session, monkeypatch) -> None:
    _wire(monkeypatch, dense=[(corpus["boll"], 0.9)], fts=[corpus["boll"]])
    events = list(
        rag.answer_stream(
            db_session,
            FakeEmbedder(),
            object(),
            FakeProvider(["x"]),
            [{"role": "user", "content": "domanda"}],
            allowed_collection_ids=[],
            refusal_threshold=0.55,
        )
    )
    assert events[-1][1].refusal is True


class KeyedEmbedder(FakeEmbedder):
    """Embeds a query as a vector that identifies it, so a fake vector search can answer
    differently per query (the real one only ever sees the vector)."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [float(len(text)), 0.0, 0.0]


class ScriptedProvider:
    """Non-streaming calls get `rewrite`, streaming calls get `tokens`; every call is kept."""

    def __init__(self, rewrite: str, tokens: list[str]) -> None:
        self.rewrite = rewrite
        self.tokens = tokens
        self.calls: list[tuple[bool, list[dict[str, str]]]] = []

    def complete(self, messages, stream=True, json_schema=None) -> Iterator[str]:
        self.calls.append((stream, messages))
        yield from self.tokens if stream else [self.rewrite]


def _wire_by_query(monkeypatch, dense_by_query: dict[str, list[tuple[int, float]]]) -> list[str]:
    """Dense results keyed by query text; returns the list of FTS queries as they happen."""
    by_len = {float(len(q)): hits for q, hits in dense_by_query.items()}
    fts_queries: list[str] = []
    monkeypatch.setattr(
        "app.services.vectorstore.search", lambda client, vec, *a, **k: list(by_len.get(vec[0], []))
    )
    monkeypatch.setattr(
        "app.services.rag.fts_search", lambda db, q, *a, **k: fts_queries.append(q) or []
    )
    return fts_queries


FOLLOW_UP = "E in quale pagina?"
REWRITE = "In quale pagina del bollettino è la verifica della coppia di serraggio?"
THREAD = [
    {"role": "user", "content": "Dove si verifica la coppia di serraggio della testata?"},
    {"role": "assistant", "content": "Nel bollettino RS [1]."},
    {"role": "user", "content": FOLLOW_UP},
]


def test_retrieve_keeps_the_rewrite_when_it_matches_better(corpus, db_session, monkeypatch):
    fts_queries = _wire_by_query(
        monkeypatch, {FOLLOW_UP: [(corpus["rs30"], 0.31)], REWRITE: [(corpus["boll"], 0.74)]}
    )
    embedder = KeyedEmbedder()
    r = rag.retrieve(db_session, embedder, object(), FOLLOW_UP, None, rewritten=REWRITE)
    assert embedder.queries == [FOLLOW_UP, REWRITE]  # both embedded and searched
    assert fts_queries == [REWRITE]  # FTS only for the query whose ranking is kept
    assert r.max_dense_score == 0.74 and r.query == REWRITE
    # not fused: the raw follow-up's weaker hit does not dilute the context
    assert [c.chunk_id for c in r.chunks] == [corpus["boll"]]


def test_retrieve_keeps_the_question_when_the_rewrite_drifts(corpus, db_session, monkeypatch):
    """A rewrite that lost the key term matches the corpus worse — the raw question wins."""
    _wire_by_query(
        monkeypatch, {FOLLOW_UP: [(corpus["boll"], 0.64)], REWRITE: [(corpus["rs30"], 0.50)]}
    )
    r = rag.retrieve(db_session, KeyedEmbedder(), object(), FOLLOW_UP, None, rewritten=REWRITE)
    assert r.query == FOLLOW_UP and r.max_dense_score == 0.64
    assert [c.chunk_id for c in r.chunks] == [corpus["boll"]]


def test_retrieve_ties_keep_the_question(corpus, db_session, monkeypatch) -> None:
    _wire_by_query(
        monkeypatch, {FOLLOW_UP: [(corpus["boll"], 0.6)], REWRITE: [(corpus["rs30"], 0.6)]}
    )
    r = rag.retrieve(db_session, KeyedEmbedder(), object(), FOLLOW_UP, None, rewritten=REWRITE)
    assert r.query == FOLLOW_UP and [c.chunk_id for c in r.chunks] == [corpus["boll"]]


def test_retrieve_runs_once_when_the_rewrite_is_the_question(corpus, db_session, monkeypatch):
    _wire_by_query(monkeypatch, {FOLLOW_UP: [(corpus["boll"], 0.6)]})
    embedder = KeyedEmbedder()
    rag.retrieve(db_session, embedder, object(), FOLLOW_UP, None, rewritten=FOLLOW_UP)
    assert embedder.queries == [FOLLOW_UP]


def test_answer_stream_rewrites_a_follow_up_before_retrieving(corpus, db_session, monkeypatch):
    """The raw follow-up would be refused at the threshold; its rewrite carries the thread's
    subject, clears it, and the answer is grounded on what the rewrite retrieved."""
    _wire_by_query(
        monkeypatch, {FOLLOW_UP: [(corpus["rs30"], 0.31)], REWRITE: [(corpus["boll"], 0.74)]}
    )
    provider = ScriptedProvider(rewrite=REWRITE, tokens=["Pagina 8 ", "[1]."])
    events = list(
        rag.answer_stream(
            db_session,
            KeyedEmbedder(),
            object(),
            provider,
            THREAD,
            allowed_collection_ids=None,
            refusal_threshold=0.55,
        )
    )
    final = events[-1][1]
    assert final.refusal is False
    assert final.retrieval_query == REWRITE
    assert [c.chunk_id for c in final.citations] == [corpus["boll"]]  # the rewrite's hit
    # one non-streaming rewrite call, then the streamed answer
    assert [stream for stream, _ in provider.calls] == [False, True]
    rewrite_prompt = provider.calls[0][1][-1]["content"]
    assert "Utente: Dove si verifica la coppia" in rewrite_prompt
    assert f"Ultima domanda: {FOLLOW_UP}" in rewrite_prompt
    # the answer prompt still carries the user's own words, not the rewrite
    answer_prompt = provider.calls[1][1][-1]["content"]
    assert f"Domanda: {FOLLOW_UP}" in answer_prompt and REWRITE not in answer_prompt


def test_answer_stream_first_turn_costs_no_rewrite_call(corpus, db_session, monkeypatch) -> None:
    _wire(monkeypatch, dense=[(corpus["boll"], 0.72)], fts=[])
    provider = ScriptedProvider(rewrite="mai", tokens=["ok [1]"])
    q = "coppia di serraggio testata?"
    events = list(
        rag.answer_stream(
            db_session,
            FakeEmbedder(),
            object(),
            provider,
            [{"role": "user", "content": q}],
            allowed_collection_ids=None,
            refusal_threshold=0.55,
        )
    )
    assert [stream for stream, _ in provider.calls] == [True]
    assert events[-1][1].retrieval_query == q


def test_answer_stream_query_rewrite_can_be_disabled(corpus, db_session, monkeypatch) -> None:
    _wire(monkeypatch, dense=[(corpus["boll"], 0.72)], fts=[])
    provider = ScriptedProvider(rewrite="mai", tokens=["ok [1]"])
    events = list(
        rag.answer_stream(
            db_session,
            FakeEmbedder(),
            object(),
            provider,
            THREAD,
            allowed_collection_ids=None,
            refusal_threshold=0.55,
            query_rewrite=False,
        )
    )
    assert [stream for stream, _ in provider.calls] == [True]
    assert events[-1][1].retrieval_query == FOLLOW_UP


def test_answer_stream_refusal_reports_the_rewrite_it_tried(corpus, db_session, monkeypatch):
    _wire_by_query(
        monkeypatch, {FOLLOW_UP: [(corpus["rs30"], 0.2)], REWRITE: [(corpus["boll"], 0.3)]}
    )
    provider = ScriptedProvider(rewrite=REWRITE, tokens=["mai"])
    events = list(
        rag.answer_stream(
            db_session,
            KeyedEmbedder(),
            object(),
            provider,
            THREAD,
            allowed_collection_ids=None,
            refusal_threshold=0.55,
        )
    )
    final = events[-1][1]
    assert final.refusal is True and final.retrieval_query == REWRITE
    assert [stream for stream, _ in provider.calls] == [False]  # rewritten, then refused pre-LLM
