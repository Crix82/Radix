"""RAG eval harness (`make eval`, SPEC §11 / M4).

Runs each question in questions.yaml through the real RAG pipeline and checks that the
answer cites the expected document and page; the out-of-corpus question must produce the
exact refusal phrase. Requires an indexed corpus (Postgres + Qdrant) and a running LLM.

Env: DATABASE_URL, QDRANT_URL, LLM_PROVIDER/LLM_MODEL/LLM_BASE_URL (see .env).
Exits non-zero if fewer than PASS_TARGET answers are correct (DoD: >= 8/10).
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


@dataclass
class Expected:
    q: str
    doc: str
    page: int


@dataclass
class EvalDeps:
    db: Any
    embedder: Any
    client: Any
    provider: Any
    threshold: float


def load_questions(path: Path) -> tuple[list[Expected], list[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    questions = [
        Expected(q=item["q"], doc=item["doc"], page=item["page"]) for item in data["questions"]
    ]
    refusals = [item["q"] for item in data.get("refusal", [])]
    return questions, refusals


def run_question(deps: EvalDeps, question: str) -> ChatResult:
    result: ChatResult | None = None
    for kind, payload in rag.answer_stream(
        db=deps.db,
        embedder=deps.embedder,
        client=deps.client,
        provider=deps.provider,
        messages=[{"role": "user", "content": question}],
        allowed_collection_ids=None,
        refusal_threshold=deps.threshold,
    ):
        if kind == "final":
            result = payload
    assert result is not None
    return result


def citation_matches(result: ChatResult, expected: Expected) -> bool:
    stem = expected.doc.rsplit(".", 1)[0]
    return any(
        c.title is not None and stem in c.title and c.page == expected.page
        for c in result.citations
    )


def evaluate(deps: EvalDeps, questions: list[Expected], refusals: list[str]) -> int:
    passed = 0
    print(f"\nEval: {len(questions)} questions + {len(refusals)} refusal\n")
    for i, exp in enumerate(questions, 1):
        result = run_question(deps, exp.q)
        ok = citation_matches(result, exp)
        passed += ok
        cited = ", ".join(f"{c.title}:p{c.page}" for c in result.citations) or "—"
        print(f"  [{'PASS' if ok else 'FAIL'}] Q{i}: expect {exp.doc} p{exp.page} | cited: {cited}")

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
    questions, refusals = load_questions(Path(__file__).parent / "questions.yaml")
    passed = evaluate(build_deps(), questions, refusals)
    return 0 if passed >= PASS_TARGET else 1


if __name__ == "__main__":
    raise SystemExit(main())
