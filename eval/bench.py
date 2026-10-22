"""Chat latency benchmark (`make bench`): compare Radix on two machines.

Runs the eval questions (questions.yaml) through the same stages rag.answer_stream uses
for a first turn — retrieval, then the streamed LLM answer — and times each stage, so the
tables printed on two hosts can be put side by side. It measures speed only: quality is
`make eval`'s job. Needs the same indexed corpus on both machines (the fixture PDFs in
backend/tests/fixtures) for the numbers to be comparable.

The first question is run once untimed, so loading bge-m3 and the LLM into memory does not
skew the first row. Token counts are streamed chunks: with Ollama one chunk is one token.

Usage (inside the api container, like run_eval.py):
  python /app/eval/bench.py --label server --runs 3
"""

import argparse
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# run_eval puts backend/ on sys.path; import it before the app packages.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_eval import EvalDeps, build_deps, load_questions  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services import rag  # noqa: E402


@dataclass
class Timing:
    question: str
    retrieval_s: float
    first_token_s: float | None  # None when retrieval refused (no LLM call)
    total_s: float
    tokens: int

    @property
    def tokens_per_s(self) -> float | None:
        if self.first_token_s is None or self.tokens < 2:
            return None
        generation = self.total_s - self.first_token_s
        return (self.tokens - 1) / generation if generation > 0 else None


def time_question(deps: EvalDeps, question: str) -> Timing:
    """Time one first-turn question; mirrors rag.answer_stream (no rewrite on a first turn)."""
    start = time.perf_counter()
    retrieval = rag.retrieve(deps.db, deps.embedder, deps.client, question, None)
    retrieval_s = time.perf_counter() - start

    if not retrieval.chunks or retrieval.max_dense_score < deps.threshold:
        return Timing(question, retrieval_s, None, retrieval_s, 0)

    messages = rag.build_messages(
        retrieval.chunks, [{"role": "user", "content": question}], question
    )
    first_token_s: float | None = None
    tokens = 0
    for _token in deps.provider.complete(messages, stream=True):
        if first_token_s is None:
            first_token_s = time.perf_counter() - start
        tokens += 1
    return Timing(question, retrieval_s, first_token_s, time.perf_counter() - start, tokens)


def _fmt(value: float | None, unit: str = "s") -> str:
    return "—" if value is None else f"{value:.2f} {unit}".rstrip()


def _median(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return statistics.median(present) if present else None


def _device() -> str:
    import torch

    if torch.cuda.is_available():
        return f"cuda ({torch.cuda.get_device_name(0)})"
    return "cpu"


def print_report(label: str, runs: int, rows: list[list[Timing]]) -> None:
    settings = get_settings()
    print(f"\nBenchmark — {label}")
    print(f"LLM: {settings.llm_model} @ {settings.llm_base_url}")
    print(f"Embedding (this container): {_device()}")
    print(f"Questions: {len(rows)} × {runs} run(s); values are medians across runs\n")

    header = f"{'#':>3}  {'Domanda':<44} {'Ricerca':>9} {'1° token':>9} {'Totale':>9} {'tok/s':>8}"
    print(header)
    print("-" * len(header))
    for i, runs_of_q in enumerate(rows, 1):
        q = runs_of_q[0].question
        q = q if len(q) <= 44 else q[:43] + "…"
        print(
            f"{i:>3}  {q:<44} "
            f"{_fmt(_median([t.retrieval_s for t in runs_of_q])):>9} "
            f"{_fmt(_median([t.first_token_s for t in runs_of_q])):>9} "
            f"{_fmt(_median([t.total_s for t in runs_of_q])):>9} "
            f"{_fmt(_median([t.tokens_per_s for t in runs_of_q]), ''):>8}"
        )
    flat = [t for runs_of_q in rows for t in runs_of_q]
    print("-" * len(header))
    print(
        f"{'':>3}  {'Mediana':<44} "
        f"{_fmt(_median([t.retrieval_s for t in flat])):>9} "
        f"{_fmt(_median([t.first_token_s for t in flat])):>9} "
        f"{_fmt(_median([t.total_s for t in flat])):>9} "
        f"{_fmt(_median([t.tokens_per_s for t in flat]), ''):>8}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="radix", help="name of this machine in the report")
    parser.add_argument("--runs", type=int, default=1, help="repetitions per question")
    args = parser.parse_args()

    questions, _refusals, _conversations = load_questions(Path(__file__).parent / "questions.yaml")
    deps = build_deps()

    print("Warm-up (loading models)…")
    time_question(deps, questions[0].q)

    rows: list[list[Timing]] = []
    for i, exp in enumerate(questions, 1):
        print(f"  Q{i}/{len(questions)}…", flush=True)
        rows.append([time_question(deps, exp.q) for _ in range(args.runs)])

    print_report(args.label, args.runs, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
