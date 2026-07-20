# Radix — Operating conventions

Radix is an on-premise document intelligence platform for industrial SMEs.
`SPEC.md` contains the locked decisions; `docs/mock/radix-mock-v1.html` is the visual
source of truth for the UI. Work proceeds one milestone at a time (SPEC §11).

## Language
- Code, comments, identifiers: **English**.
- UI strings: **Italian**, only via the i18n file (`frontend/src/i18n/it.ts`), default locale `it`.

## Quality gates
- Type hints everywhere; `make lint` runs `ruff` (check + format) and `mypy` on the backend,
  `tsc --noEmit` on the frontend. No merge with red tests.
- Every pipeline service and every endpoint gets pytest coverage.
- Tests run on in-memory SQLite (no Docker needed): Postgres-only column types must use
  `with_variant` fallbacks (see `app/models/tables.py`); the `chunks` table (tsvector)
  stays Postgres-only and is excluded from SQLite test schemas (tests that need it build a
  tsvector-free copy via `create_sqlite_chunks_table`).
- Heavy deps (Docling/torch) must stay behind lazy imports so unit tests never load them;
  real-pipeline tests are marked `slow` and `importorskip` when Docling/Tesseract are absent.
- **Every Alembic migration must be idempotent against the current models.** Migration `0001`
  builds the schema with `Base.metadata.create_all()`, i.e. from the models as they are *now*,
  so a fresh install already has the tables/columns a later migration adds — a bare
  `CREATE TABLE` there fails with "already exists", and only on a clean install (never on a
  populated DB, never on the SQLite tests). Create/alter only when absent, and make the
  migration a no-op under `--sql` (offline can't inspect; `0001` already emits the DDL).
  See `docs/adr/0008` and the `test_no_table_is_created_twice` guard.
- Conventional commits (`feat:`, `fix:`, `chore:`, …).

## Dependencies & licenses
- **No new dependency without a license check**: run `make licenses` after adding one.
- **`backend/requirements.lock` is what the image installs**, not `pyproject.toml`. The
  `pyproject` entries are open lower bounds (`>=`) — an unconstrained resolve picks whatever is
  newest that day, so the image would differ between a verification run and a customer install.
  After changing `pyproject.toml`: `make lock` (resolves inside `python:3.12-slim`, the image's
  own base), review the diff, then `make licenses`. See `docs/adr/0009`.
- Only permissive licenses (Apache-2.0, MIT, BSD or equivalent). AGPL, SSPL, BUSL and
  non-commercial licenses are forbidden (SPEC §14). PyMuPDF is explicitly banned — use pypdfium2.

## Scope & decisions
- Do not implement anything in the out-of-scope list (SPEC §13).
- Always prefer the simplest solution that satisfies the DoD: this project is maintained by one person.
- On any ambiguity in the spec: stop and ask, propose options — never decide silently.
- Decisions taken along the way are recorded in `docs/adr/` (one line of context, the choice, the why).

## Workflow
- One milestone (M0 → M6) per work session; verify the DoD (green tests + manual checks)
  before moving on.
- At the end of a milestone: update this file if new conventions emerged, and the CHANGELOG
  section at the bottom of `SPEC.md`.

## Local commands
- `make up` / `make down` — dev stack (Docker Compose, hot reload, ollama)
- `make venv` — create `backend/.venv` with dev dependencies
- `make test` / `make lint` / `make licenses` — local CI
- `make eval` — RAG quality harness (from M4)
- `make install` — guided on-prem install (from M6; `ARGS=--non-interactive` to skip prompts)
- `make backup` / `make restore ARCHIVE=<f>` / `make test-restore` — backup + round-trip (M6)

## Deploy (M6)
- Deploy scripts live in `deploy/` and share `deploy/_common.sh` (root dir, docker/sudo
  detection, `.env` load). They are bash, outside the ruff/mypy gate — verify with `bash -n`
  (and `shellcheck` if installed).
- **LLM runtime switch is `COMPOSE_FILE` in `.env`**, not compose profiles: `docker-compose.yml`
  (external) `:docker-compose.llm.yml` (bundled CPU) `:docker-compose.gpu.yml` (bundled GPU).
  `install.sh` writes it; the dev stack (`make up`) is unaffected. Don't add `depends_on: ollama`
  to api/worker in the prod base compose.
- Prod runs `alembic upgrade head` at container start and seeds the admin from `ADMIN_*`;
  `install.sh` only needs to produce a correct `.env` and `compose up`.
