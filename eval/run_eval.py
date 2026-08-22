"""RAG eval harness (`make eval`, SPEC §11 / M4).

Runs each question in questions.yaml through the real RAG pipeline and checks that the
answer cites the expected document and page; the out-of-corpus question must produce the
exact refusal phrase; the multi-turn scripts check that a follow-up, rewritten with the
conversation (ADR 0010), still cites the right place. Requires an indexed corpus
(Postgres + Qdrant) and a running LLM.

Env: DATABASE_URL, QDRANT_URL, LLM_PROVIDER/LLM_MODEL/LLM_BASE_URL (see .env).
Exits non-zero if fewer than PASS_TARGET answers are correct (DoD: >= 8/10), the refusal
fails, or fewer than FOLLOWUP_PASS_TARGET scored follow-up turns are correct.
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.services import rag  # noqa: E402
from app.services.rag import ChatResult  # noqa: E402
from app.services.rag.prompts import REFUSAL_PHRASE  # noqa: E402

PASS_TARGET = 8
FOLLOWUP_PASS_TARGET = 3  # of the 4 scored follow-up turns


@dataclass
class Expected:
    q: str
    doc: str
    page: int


@dataclass
class Turn:
    q: str
    doc: str | None = None  # scored only when an expectation is given
    page: int | None = None


@dataclass
class EvalDeps:
    db: Any
    embedder: Any
    client: Any
    provider: Any
    threshold: float


def load_questions(path: Path) -> tuple[list[Expected], list[str], list[list[Turn]]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    questions = [
        Expected(q=item["q"], doc=item["doc"], page=item["page"]) for item in data["questions"]
    ]
    refusals = [item["q"] for item in data.get("refusal", [])]
    conversations = [
        [Turn(q=t["q"], doc=t.get("doc"), page=t.get("page")) for t in item["turns"]]
        for item in data.get("conversations", [])
    ]
    return questions, refusals, conversations


def run_turn(deps: EvalDeps, messages: list[dict[str, str]]) -> ChatResult:
    result: ChatResult | None = None
    for kind, payload in rag.answer_stream(
        db=deps.db,
        embedder=deps.embedder,
        client=deps.client,
        provider=deps.provider,
        messages=messages,
        allowed_collection_ids=None,
        refusal_threshold=deps.threshold,
    ):
        if kind == "final":
            result = payload
    assert result is not None
    return result


def run_question(deps: EvalDeps, question: str) -> ChatResult:
    return run_turn(deps, [{"role": "user", "content": question}])


def citation_matches(result: ChatResult, expected: Expected) -> bool:
    stem = expected.doc.rsplit(".", 1)[0]
    return any(
        c.title is not None and stem in c.title and c.page == expected.page
        for c in result.citations
    )


def _cited(result: ChatResult) -> str:
    return ", ".join(f"{c.title}:p{c.page}" for c in result.citations) or "—"


def evaluate_conversations(deps: EvalDeps, conversations: list[list[Turn]]) -> tuple[int, int]:
    """Replay each script as one thread (the way the API replays stored turns) and score the
    turns that carry an expectation. Returns (passed, scored)."""
    passed = scored = 0
    print(f"\nFollow-ups: {len(conversations)} conversations\n")
    for i, turns in enumerate(conversations, 1):
        messages: list[dict[str, str]] = []
        for turn in turns:
            messages.append({"role": "user", "content": turn.q})
            result = run_turn(deps, messages)
            messages.append({"role": "assistant", "content": result.answer_md})
            if turn.doc is None or turn.page is None:
                print(f"         C{i}: {turn.q}")
                continue
            scored += 1
            ok = citation_matches(result, Expected(q=turn.q, doc=turn.doc, page=turn.page))
            passed += ok
            print(
                f"  [{'PASS' if ok else 'FAIL'}] C{i}: {turn.q}\n"
                f"         retrieval query: {result.retrieval_query}\n"
                f"         expect {turn.doc} p{turn.page} | cited: {_cited(result)}"
            )
    print(f"\nFollow-up score: {passed}/{scored} correct citations")
    return passed, scored


def evaluate(deps: EvalDeps, questions: list[Expected], refusals: list[str]) -> int:
    passed = 0
    print(f"\nEval: {len(questions)} questions + {len(refusals)} refusal\n")
    for i, exp in enumerate(questions, 1):
        result = run_question(deps, exp.q)
        ok = citation_matches(result, exp)
        passed += ok
        state = "PASS" if ok else "FAIL"
        print(f"  [{state}] Q{i}: expect {exp.doc} p{exp.page} | cited: {_cited(result)}")

    refusal_ok = True
    for q in refusals:
        result = run_question(deps, q)
        # A refusal is valid from either path: the cosine threshold (result.refusal) or the
        # LLM following the grounding prompt and emitting the exact phrase (SPEC §8).
        good = result.answer_md.strip() == REFUSAL_PHRASE
        refusal_ok = refusal_ok and good
        source = "threshold" if result.refusal else "grounded"
        state = f"refused ({source})" if good else result.answer_md[:50]
        print(f"  [{'PASS' if good else 'FAIL'}] refusal: {state}")

    ref = "ok" if refusal_ok else "FAILED"
    print(f"\nScore: {passed}/{len(questions)} correct citations; refusal {ref}")
    return passed if refusal_ok else -1


def build_deps() -> EvalDeps:
    from app.core.db import SessionLocal
    from app.core.settings_store import get_refusal_threshold
    from app.services.embeddings import get_embedder
    from app.services.llm.base import get_llm_provider
    from app.services.vectorstore import get_client

    db = SessionLocal()
    return EvalDeps(
        db=db,
        embedder=get_embedder(),
        client=get_client(),
        provider=get_llm_provider(),
        threshold=get_refusal_threshold(db),
    )


def main() -> int:
    questions, refusals, conversations = load_questions(Path(__file__).parent / "questions.yaml")
    deps = build_deps()
    passed = evaluate(deps, questions, refusals)
    followups, _scored = evaluate_conversations(deps, conversations)
    return 0 if passed >= PASS_TARGET and followups >= FOLLOWUP_PASS_TARGET else 1


if __name__ == "__main__":
    raise SystemExit(main())
