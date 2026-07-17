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
- Conventional commits (`feat:`, `fix:`, `chore:`, …).

## Dependencies & licenses
- **No new dependency without a license check**: run `make licenses` after adding one.
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
