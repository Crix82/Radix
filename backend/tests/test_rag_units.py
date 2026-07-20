from app.services.rag import (
    HISTORY_TURNS,
    Citation,
    ContextChunk,
    build_messages,
    parse_citations,
)
from app.services.rag.prompts import REFUSAL_PHRASE, SYSTEM_PROMPT


def _ctx(n: int, chunk_id: int = None, page: int = 10) -> ContextChunk:
    return ContextChunk(
        n=n,
        chunk_id=chunk_id or n * 100,
        document_id=n,
        title=f"Doc {n}",
        lang="it",
        page=page,
        text=f"Testo del passaggio {n}.",
        bboxes={str(page): [[0.1, 0.1, 0.5, 0.2]]},
    )


def test_parse_citations_maps_markers_to_chunks() -> None:
    context = [_ctx(1, page=142), _ctx(2, page=8), _ctx(3, page=33)]
    answer = "La coppia è 85 Nm [1], da verificare dopo 50 ore [2]."
    cites = parse_citations(answer, context)
    assert [c.n for c in cites] == [1, 2]
    assert cites[0].page == 142 and cites[1].page == 8
    assert cites[0].bboxes == {"142": [[0.1, 0.1, 0.5, 0.2]]}


def test_parse_citations_dedupes_and_ignores_unknown() -> None:
    context = [_ctx(1), _ctx(2)]
    answer = "Testo [1] altro [1] e un marcatore inesistente [9]."
    cites = parse_citations(answer, context)
    assert [c.n for c in cites] == [1]


def test_parse_citations_falls_back_to_all_sources_when_uncited() -> None:
    context = [_ctx(1), _ctx(2)]
    cites = parse_citations("Risposta senza marcatori.", context)
    assert [c.n for c in cites] == [1, 2]  # SPEC §8: attach used sources anyway


def test_build_messages_has_system_context_and_question() -> None:
    context = [_ctx(1, page=142)]
    history = [{"role": "user", "content": "Qual è la coppia di serraggio?"}]
    msgs = build_messages(context, history, "Qual è la coppia di serraggio?")
    assert msgs[0]["role"] == "system" and msgs[0]["content"] == SYSTEM_PROMPT
    last = msgs[-1]
    assert last["role"] == "user"
    assert "[1]" in last["content"] and "pag. 142" in last["content"]
    assert "Domanda: Qual è la coppia di serraggio?" in last["content"]


def test_build_messages_keeps_prior_turns() -> None:
    context = [_ctx(1)]
    history = [
        {"role": "user", "content": "prima domanda"},
        {"role": "assistant", "content": "prima risposta [1]"},
        {"role": "user", "content": "seconda domanda"},
    ]
    msgs = build_messages(context, history, "seconda domanda")
    roles = [m["role"] for m in msgs]
    assert roles == ["system", "user", "assistant", "user"]
    assert msgs[1]["content"] == "prima domanda"
    assert "seconda domanda" in msgs[-1]["content"]


def test_build_messages_caps_the_replayed_history() -> None:
    """Conversations are persisted now, so an old thread must not grow the prompt unbounded."""
    context = [_ctx(1)]
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"turno {i}"} for i in range(20)
    ]
    history.append({"role": "user", "content": "domanda corrente"})

    msgs = build_messages(context, history, "domanda corrente")
    prior = msgs[1:-1]
    assert len(prior) == HISTORY_TURNS
    assert prior[-1]["content"] == "turno 19"  # the most recent turns are the ones kept
    assert "turno 0" not in [m["content"] for m in prior]


def test_refusal_phrase_is_exact() -> None:
    assert REFUSAL_PHRASE == "Non presente nella documentazione indicizzata."


def test_citation_dataclass_shape() -> None:
    c = Citation(n=1, chunk_id=5, document_id=2, title="Doc", lang="it", page=142, bboxes=None)
    assert (c.n, c.chunk_id, c.document_id, c.page) == (1, 5, 2, 142)
    assert (c.title, c.lang) == ("Doc", "it")
