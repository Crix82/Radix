#!/usr/bin/env bash
# Round-trip test for backup.sh + restore.sh (SPEC §11 M6 DoD: "backup/restore tested
# round-trip"). Requires a running stack. It proves restore truly rewinds state:
#   1. record the Qdrant point count
#   2. take a backup
#   3. write a sentinel row into `settings` (state AFTER the backup)
#   4. restore the backup
#   5. assert the sentinel is gone  → Postgres was rewound to the backup
#   6. assert the Qdrant count matches  → the vector index round-tripped
#
# Usage: deploy/test-backup-restore.sh
set -euo pipefail
# shellcheck source=deploy/_common.sh
. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

require_running postgres qdrant api

PROBE="_roundtrip_probe"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

qdrant_count() {
  dc exec -T api python -c "
from qdrant_client import QdrantClient
c = QdrantClient(url='http://qdrant:6333', timeout=120)
print(c.count('${QDRANT_COLLECTION}').count if c.collection_exists('${QDRANT_COLLECTION}') else 0)
" | tr -d '\r' | tail -n1
}
probe_count() {
  dc exec -T postgres psql -tAqX -U "$PGUSER" -d "$PGDB" \
    -c "SELECT count(*) FROM settings WHERE key='${PROBE}';" | tr -d '\r' | tail -n1
}

# Make sure a stale probe from an aborted run isn't already present.
dc exec -T postgres psql -qX -U "$PGUSER" -d "$PGDB" \
  -c "DELETE FROM settings WHERE key='${PROBE}';" >/dev/null

info "Recording pre-backup state"
COUNT_BEFORE="$(qdrant_count)"
ok "Qdrant points: ${COUNT_BEFORE}"

info "Taking backup"
"${_SCRIPT_DIR}/backup.sh" "$WORK" >/dev/null
ARCHIVE="$(ls -1t "$WORK"/radix-*.tar.gz | head -n1)"
[[ -f "$ARCHIVE" ]] || die "backup produced no archive"
ok "archive: $(basename "$ARCHIVE")"

info "Mutating state after the backup (sentinel row)"
dc exec -T postgres psql -qX -U "$PGUSER" -d "$PGDB" \
  -c "INSERT INTO settings(key,value) VALUES('${PROBE}','\"1\"'::jsonb);" >/dev/null
[[ "$(probe_count)" == "1" ]] || die "failed to write sentinel"
ok "sentinel present (count=1)"

info "Restoring backup"
"${_SCRIPT_DIR}/restore.sh" "$ARCHIVE" --yes >/dev/null

info "Verifying round-trip"
FAIL=0
AFTER_PROBE="$(probe_count)"
COUNT_AFTER="$(qdrant_count)"
if [[ "$AFTER_PROBE" == "0" ]]; then ok "Postgres rewound — sentinel gone"; else warn "Postgres NOT rewound — sentinel still present"; FAIL=1; fi
if [[ "$COUNT_AFTER" == "$COUNT_BEFORE" ]]; then ok "Qdrant round-trip — ${COUNT_AFTER} points"; else warn "Qdrant mismatch: before=${COUNT_BEFORE} after=${COUNT_AFTER}"; FAIL=1; fi

echo
if [[ "$FAIL" -eq 0 ]]; then ok "ROUND-TRIP PASSED"; else die "ROUND-TRIP FAILED"; fi
