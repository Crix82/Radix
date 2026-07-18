#!/usr/bin/env bash
# Restore a Radix backup produced by deploy/backup.sh (SPEC §11, M6).
# DESTRUCTIVE: replaces the Postgres database, the Qdrant collection and the repository
# with the archive's contents. The live .env is NOT touched (env.backup is reference only).
#
# Usage:
#   deploy/restore.sh ARCHIVE.tar.gz [--yes]
set -euo pipefail
# shellcheck source=deploy/_common.sh
. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

ARCHIVE="${1:-}"
ASSUME_YES=0
[[ "${2:-}" == "--yes" || "${1:-}" == "--yes" ]] && ASSUME_YES=1
[[ -n "$ARCHIVE" && "$ARCHIVE" != "--yes" ]] || die "usage: deploy/restore.sh ARCHIVE.tar.gz [--yes]"
[[ -f "$ARCHIVE" ]] || die "archive not found: $ARCHIVE"

require_running postgres qdrant

if [[ "$ASSUME_YES" -ne 1 ]]; then
  warn "This will OVERWRITE the current database, vector index and repository."
  read -r -p "Type 'restore' to continue: " reply </dev/tty || true
  [[ "$reply" == "restore" ]] || die "aborted"
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
info "Extracting $(basename "$ARCHIVE")…"
tar -xzf "$ARCHIVE" -C "$STAGE"
[[ -f "$STAGE/postgres.sql" ]] || die "archive is missing postgres.sql — not a Radix backup"

# --- 1. Postgres -------------------------------------------------------------
# Pause the app so no writes race the restore; the dump is DROP+CREATE, self-contained.
info "Stopping api/worker…"
dc stop api worker >/dev/null

info "Restoring Postgres…"
dc exec -T postgres psql -v ON_ERROR_STOP=1 -U "$PGUSER" -d "$PGDB" < "$STAGE/postgres.sql" >/dev/null
ok "database restored"

# --- 2. Qdrant ---------------------------------------------------------------
if [[ -f "$STAGE/qdrant.snapshot" ]]; then
  info "Restoring Qdrant collection '${QDRANT_COLLECTION}'…"
  dc cp "$STAGE/qdrant.snapshot" "qdrant:/qdrant/snapshots/_restore.snapshot"
  dc exec -T api python -c "
from qdrant_client import QdrantClient
c = QdrantClient(url='http://qdrant:6333', timeout=600)
c.recover_snapshot(collection_name='${QDRANT_COLLECTION}', location='file:///qdrant/snapshots/_restore.snapshot')
"
  ok "vector index restored"
else
  warn "No qdrant.snapshot in archive — leaving the vector index untouched."
fi

# --- 3. Repository -----------------------------------------------------------
if [[ -f "$STAGE/repository.tar.gz" ]]; then
  info "Restoring repository…"
  rm -rf "${DATA_DIR:?}/repository"
  tar -xzf "$STAGE/repository.tar.gz" -C "$DATA_DIR"
  ok "repository restored"
fi

# --- 4. Restart + healthcheck ------------------------------------------------
info "Starting api/worker…"
dc start api worker >/dev/null
for _ in $(seq 1 40); do
  dc exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=5)" >/dev/null 2>&1 && break
  sleep 3
done
echo
ok "Restore complete."
info "The live .env was left unchanged (the backup's copy is env.backup inside the archive)."
