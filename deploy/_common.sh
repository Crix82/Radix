#!/usr/bin/env bash
# Shared helpers for the Radix deploy scripts (M6). Sourced, not executed.
# Provides: ROOT_DIR, DOCKER, dc(), logging helpers, and loaded .env values.

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${_SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

if [[ -t 1 ]]; then _CB="\033[1m"; _CG="\033[32m"; _CY="\033[33m"; _CR="\033[31m"; _C0="\033[0m"
else _CB=""; _CG=""; _CY=""; _CR=""; _C0=""; fi
info() { printf "${_CB}==>${_C0} %s\n" "$*"; }
ok()   { printf "${_CG}  ok${_C0} %s\n" "$*"; }
warn() { printf "${_CY}  ! ${_C0} %s\n" "$*"; }
die()  { printf "${_CR}error:${_C0} %s\n" "$*" >&2; exit 1; }

# Read a single key from .env WITHOUT sourcing it — a spaced/quoted value (e.g. an admin
# password) must not break these scripts. Docker Compose itself reads COMPOSE_FILE and the
# ${VAR} substitutions straight from .env, so we only pull the few keys the scripts need.
[[ -f "${ROOT_DIR}/.env" ]] || die ".env not found in ${ROOT_DIR} — run deploy/install.sh first"
get_env() {  # get_env KEY [default]
  local v
  v="$(grep -E "^$1=" "${ROOT_DIR}/.env" | tail -n1 | cut -d= -f2-)"
  printf '%s' "${v:-${2:-}}"
}

PGUSER="$(get_env POSTGRES_USER radix)"
PGDB="$(get_env POSTGRES_DB radix)"
DATA_DIR="$(get_env DATA_DIR ./data)"
QDRANT_COLLECTION="$(get_env QDRANT_COLLECTION chunks)"

# Pick `docker` or `sudo docker` depending on daemon access.
command -v docker >/dev/null 2>&1 || die "docker not found — run deploy/install.sh first"
DOCKER="docker"
if ! docker info >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then DOCKER="sudo docker"
  else die "cannot talk to the Docker daemon"; fi
fi

# Thin wrapper: `dc exec -T postgres …`. COMPOSE_FILE from .env selects the stack.
dc() { $DOCKER compose "$@"; }

# Fail early if the core services aren't running.
require_running() {
  local svc
  for svc in "$@"; do
    dc ps --status running --services 2>/dev/null | grep -qx "$svc" || \
      die "service '$svc' is not running — start the stack with 'docker compose up -d'"
  done
}
