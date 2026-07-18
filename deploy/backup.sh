#!/usr/bin/env bash
# Full Radix backup (SPEC §11, M6): pg_dump + Qdrant snapshot (API) + repository + config.
# The page cache (data/pagecache) is intentionally excluded — it is regenerated on demand.
#
# Usage:
#   deploy/backup.sh [OUT_DIR]     write radix-<timestamp>.tar.gz into OUT_DIR (default ./backups)
set -euo pipefail
# shellcheck source=deploy/_common.sh
. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

OUT_DIR="${1:-${ROOT_DIR}/backups}"
mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

require_running postgres qdrant

info "Backup ${STAMP}"

# --- 1. Postgres (logical dump, self-contained: DROP + CREATE + data) --------
info "Dumping Postgres…"
dc exec -T postgres pg_dump -U "$PGUSER" -d "$PGDB" --clean --if-exists --no-owner > "$STAGE/postgres.sql"
ok "postgres.sql ($(du -h "$STAGE/postgres.sql" | cut -f1))"

# --- 2. Qdrant snapshot via API ---------------------------------------------
# Create through the api container (it already has qdrant-client and reaches qdrant:6333).
info "Creating Qdrant snapshot…"
SNAP="$(dc exec -T api python -c "
from qdrant_client import QdrantClient
c = QdrantClient(url='http://qdrant:6333', timeout=300)
if c.collection_exists('${QDRANT_COLLECTION}'):
    print(c.create_snapshot(collection_name='${QDRANT_COLLECTION}').name)
" | tr -d '\r' | tail -n1)"

if [[ -n "$SNAP" ]]; then
  dc cp "qdrant:/qdrant/snapshots/${QDRANT_COLLECTION}/${SNAP}" "$STAGE/qdrant.snapshot"
  # Don't let snapshots pile up inside the container.
  dc exec -T api python -c "
from qdrant_client import QdrantClient
QdrantClient(url='http://qdrant:6333', timeout=120).delete_snapshot(collection_name='${QDRANT_COLLECTION}', snapshot_name='${SNAP}')
" >/dev/null 2>&1 || true
  ok "qdrant.snapshot ($(du -h "$STAGE/qdrant.snapshot" | cut -f1))"
else
  warn "Qdrant collection '${QDRANT_COLLECTION}' does not exist yet — skipping vector snapshot."
fi

# --- 3. Repository (original files) -----------------------------------------
if [[ -d "${DATA_DIR}/repository" ]]; then
  info "Archiving repository…"
  tar -czf "$STAGE/repository.tar.gz" -C "$DATA_DIR" repository
  ok "repository.tar.gz ($(du -h "$STAGE/repository.tar.gz" | cut -f1))"
else
  warn "No ${DATA_DIR}/repository — skipping."
fi

# --- 4. Config + manifest ----------------------------------------------------
cp "${ROOT_DIR}/.env" "$STAGE/env.backup"  # reference only; restore.sh does NOT overwrite .env
cat > "$STAGE/manifest.txt" <<EOF
radix-backup
created=${STAMP}
postgres_db=${PGDB}
qdrant_collection=${QDRANT_COLLECTION}
qdrant_snapshot=${SNAP:-<none>}
EOF

# --- 5. Bundle ---------------------------------------------------------------
ARCHIVE="${OUT_DIR}/radix-${STAMP}.tar.gz"
tar -czf "$ARCHIVE" -C "$STAGE" .
echo
ok "Backup complete: ${ARCHIVE} ($(du -h "$ARCHIVE" | cut -f1))"
