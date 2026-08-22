import pytest

from app.services.rag import (
    CONDENSE_TURN_CHARS,
    HISTORY_TURNS,
    MAX_REWRITE_CHARS,
    Citation,
    ContextChunk,
    build_messages,
    condense_question,
    parse_citations,
)
from app.services.rag.prompts import CONDENSE_PROMPT, REFUSAL_PHRASE, SYSTEM_PROMPT


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


class _CondenseProvider:
    """Scripted rewrite; records the single (non-streaming) call condense_question makes."""

    def __init__(self, reply: str | None = None, error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.calls: list[tuple[bool, list[dict[str, str]]]] = []

    def complete(self, messages, stream=True, json_schema=None):
        self.calls.append((stream, messages))
        if self.error is not None:
            raise self.error
        yield self.reply or ""


_THREAD = [
    {"role": "user", "content": "Qual è la coppia di serraggio della testata RS-30?"},
    {"role": "assistant", "content": "La coppia è 85 Nm [1]."},
    {"role": "user", "content": "E in quale pagina l'hai trovata?"},
]


def test_condense_skips_the_llm_on_a_first_turn() -> None:
    provider = _CondenseProvider("mai usato")
    q = "Qual è la coppia di serraggio?"
    assert condense_question(provider, [{"role": "user", "content": q}], q) == q
    assert provider.calls == []


def test_condense_rewrites_from_the_prior_turns() -> None:
    provider = _CondenseProvider("In quale pagina del manuale RS-30 è indicata la coppia?")
    out = condense_question(provider, _THREAD, _THREAD[-1]["content"])
    assert out == "In quale pagina del manuale RS-30 è indicata la coppia?"
    (stream, messages), *rest = provider.calls
    assert rest == [] and stream is False  # one short non-streaming call
    assert messages[0] == {"role": "system", "content": CONDENSE_PROMPT}
    prompt = messages[-1]["content"]
    assert "Utente: Qual è la coppia di serraggio della testata RS-30?" in prompt
    assert "Assistente: La coppia è 85 Nm [1]." in prompt
    assert prompt.endswith("Ultima domanda: E in quale pagina l'hai trovata?\n\nDomanda riscritta:")
    # the current question is not replayed as a prior turn
    assert prompt.count("E in quale pagina l'hai trovata?") == 1


def test_condense_strips_label_quotes_and_extra_lines() -> None:
    provider = _CondenseProvider('Domanda riscritta: "Coppia di serraggio RS-30?"\nNota: ok')
    assert condense_question(provider, _THREAD, "E la coppia?") == "Coppia di serraggio RS-30?"


@pytest.mark.parametrize(
    "reply",
    ["", "   \n", REFUSAL_PHRASE, "x" * (MAX_REWRITE_CHARS + 1)],
    ids=["empty", "blank", "refusal-phrase", "overlong"],
)
def test_condense_falls_back_to_the_question_on_unusable_output(reply: str) -> None:
    q = _THREAD[-1]["content"]
    assert condense_question(_CondenseProvider(reply), _THREAD, q) == q


def test_condense_falls_back_when_the_provider_fails() -> None:
    q = _THREAD[-1]["content"]
    assert condense_question(_CondenseProvider(error=RuntimeError("down")), _THREAD, q) == q


def test_condense_clips_long_turns_and_caps_history() -> None:
    long_answer = "parola " * 400  # far beyond CONDENSE_TURN_CHARS
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"turno {i}"} for i in range(20)
    ]
    history += [
        {"role": "assistant", "content": long_answer},
        {"role": "user", "content": "e poi?"},
    ]
    provider = _CondenseProvider("E poi cosa succede?")
    condense_question(provider, history, "e poi?")
    prompt = provider.calls[0][1][-1]["content"]
    assert "turno 0" not in prompt and "turno 19" in prompt  # HISTORY_TURNS most recent only
    assert len(prompt) < CONDENSE_TURN_CHARS * (HISTORY_TURNS + 1)
    assert "…" in prompt  # the long answer was clipped, not dropped
