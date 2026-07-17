COMPOSE      = docker compose
COMPOSE_DEV  = $(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml
BACKEND_PY   = backend/.venv/bin/python
BACKEND_BIN  = backend/.venv/bin

.PHONY: up up-prod down logs test test-integration lint licenses eval backup restore venv

## --- Stack ---

up:  ## start the dev stack (hot reload + ollama)
	$(COMPOSE_DEV) up -d --build

up-prod:  ## start the production stack
	$(COMPOSE) up -d --build

down:
	$(COMPOSE_DEV) down

logs:
	$(COMPOSE_DEV) logs -f --tail=100

## --- Local CI ---

venv:  ## create the backend virtualenv with dev dependencies
	python3 -m venv backend/.venv
	$(BACKEND_PY) -m pip install -q -e "backend/.[dev]"

test:  ## fast suite (SQLite, no Docling/torch)
	cd backend && .venv/bin/python -m pytest -q -m "not slow"

test-integration:  ## real Docling + Tesseract pipeline (needs both installed; see ADR 0003)
	cd backend && .venv/bin/python -m pytest -q -m slow

lint:
	cd backend && .venv/bin/ruff check app worker tests migrations
	cd backend && .venv/bin/ruff format --check app worker tests migrations
	cd backend && .venv/bin/mypy app worker
	cd frontend && npm run typecheck

licenses:  ## fail on any non-permissive license (SPEC §14)
	# --partial-match so "GPL" also catches "LGPL-3.0-only", "AGPL-3.0", "GPL-2.0", etc.
	# NVIDIA CUDA runtime libs (pulled by torch) are proprietary but redistributable for
	# commercial use under the CUDA EULA (SPEC §14 forbids only non-commercial) — allowlisted here.
	cd backend && .venv/bin/pip-licenses --partial-match \
		--fail-on="AGPL;GPL;SSPL;BUSL;CC-BY-NC;Commons-Clause;Elastic;Proprietary" \
		--ignore-packages radix-backend pip-licenses prettytable wcwidth \
		$$(.venv/bin/pip list --format=freeze | sed -n 's/^\(nvidia-[^=]*\)==.*/\1/p' | tr '\n' ' ')
	cd frontend && npx license-checker --production --summary \
		--excludePackages "radix-frontend@0.1.0" \
		--failOn "AGPL;AGPL-3.0;GPL;GPL-2.0;GPL-3.0;LGPL;SSPL;BUSL-1.1"

## --- Later milestones ---

eval:  ## RAG quality harness (M4)
	@echo "make eval arrives with milestone M4 (eval/run_eval.py)" && exit 1

backup:  ## full backup: postgres + qdrant + repository + config (M6)
	./deploy/backup.sh

restore:  ## restore from a backup archive (M6)
	./deploy/restore.sh
