#!/usr/bin/env bash
# Radix installer for a clean Ubuntu 24 host (SPEC §11, milestone M6).
#
# Installs prerequisites, walks a minimal .env wizard, brings the stack up, pulls the
# bundled LLM model (if any) and runs a final healthcheck. Safe to re-run: an existing
# .env is reused and only missing values are filled in.
#
# Usage:
#   deploy/install.sh                 interactive wizard
#   deploy/install.sh --non-interactive   use defaults / current env vars, generate secrets
#   deploy/install.sh --help
set -euo pipefail

# --- Paths -------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
cd "${ROOT_DIR}"

# --- Logging -----------------------------------------------------------------
if [[ -t 1 ]]; then C_B="\033[1m"; C_G="\033[32m"; C_Y="\033[33m"; C_R="\033[31m"; C_0="\033[0m"
else C_B=""; C_G=""; C_Y=""; C_R=""; C_0=""; fi
info()  { printf "${C_B}==>${C_0} %s\n" "$*"; }
ok()    { printf "${C_G}  ok${C_0} %s\n" "$*"; }
warn()  { printf "${C_Y}  ! ${C_0} %s\n" "$*"; }
die()   { printf "${C_R}error:${C_0} %s\n" "$*" >&2; exit 1; }

# --- Args --------------------------------------------------------------------
INTERACTIVE=1
for arg in "$@"; do
  case "$arg" in
    --non-interactive|-y) INTERACTIVE=0 ;;
    --help|-h) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown argument: $arg" ;;
  esac
done

# Read a value: prompt in interactive mode, else fall back to the default.
#   ask VARNAME "Prompt text" "default"   (result echoed on stdout)
ask() {
  local var="$1" prompt="$2" default="${3:-}" reply
  if [[ "$INTERACTIVE" -eq 0 ]]; then printf '%s' "${!var:-$default}"; return; fi
  if [[ -n "$default" ]]; then read -r -p "$prompt [$default]: " reply </dev/tty || true
  else read -r -p "$prompt: " reply </dev/tty || true; fi
  printf '%s' "${reply:-$default}"
}
ask_secret() {  # like ask but no echo; empty keeps the passed-in (generated/existing) value
  local prompt="$1" default="${2:-}" reply
  if [[ "$INTERACTIVE" -eq 0 ]]; then printf '%s' "$default"; return; fi
  read -r -s -p "$prompt [keep generated]: " reply </dev/tty || true; echo >/dev/tty
  printf '%s' "${reply:-$default}"
}

gen_secret() { openssl rand -hex 32; }

# =============================================================================
info "Radix installer — target: clean Ubuntu 24 host"

# --- 1. Prerequisites --------------------------------------------------------
SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; else die "run as root or install sudo"; fi
fi

need_apt() { command -v apt-get >/dev/null 2>&1; }

if ! command -v openssl >/dev/null 2>&1; then
  info "Installing openssl…"
  need_apt || die "openssl missing and apt-get unavailable"
  $SUDO apt-get update -qq && $SUDO apt-get install -y -qq openssl
fi
ok "openssl present"

if ! command -v docker >/dev/null 2>&1; then
  info "Docker not found — installing Docker Engine + Compose plugin"
  if [[ "$INTERACTIVE" -eq 1 ]]; then
    read -r -p "Install Docker via get.docker.com? [Y/n]: " a </dev/tty || true
    [[ "${a:-Y}" =~ ^[Nn] ]] && die "Docker is required"
  fi
  curl -fsSL https://get.docker.com | $SUDO sh
  # Let the invoking (non-root) user talk to the daemon without sudo.
  if [[ -n "$SUDO" ]]; then
    $SUDO usermod -aG docker "$USER"
    warn "Added $USER to the 'docker' group — log out/in (or run 'newgrp docker') for it to take effect."
  fi
fi
docker compose version >/dev/null 2>&1 || die "the Docker Compose v2 plugin is missing (expected 'docker compose')"
# Use sudo for docker if the current user can't reach the daemon yet (fresh group add).
DOCKER="docker"
docker info >/dev/null 2>&1 || DOCKER="$SUDO docker"
$DOCKER info >/dev/null 2>&1 || die "cannot talk to the Docker daemon"
ok "Docker Engine + Compose plugin ready"

# --- 2. GPU detection --------------------------------------------------------
GPU=0
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  # The container toolkit is what lets Docker pass the GPU through.
  if $DOCKER info 2>/dev/null | grep -qi 'nvidia' || command -v nvidia-ctk >/dev/null 2>&1; then
    GPU=1; ok "NVIDIA GPU + Container Toolkit detected — Ollama will use the GPU"
  else
    warn "NVIDIA GPU found but the Container Toolkit is not wired into Docker — falling back to CPU."
    warn "Install nvidia-container-toolkit and re-run to enable the GPU."
  fi
else
  ok "No NVIDIA GPU detected — using the CPU profile (SPEC §10 'Cliente entry')"
fi

# --- 3. Configuration wizard (.env) -----------------------------------------
# Reuse any existing .env so a re-run doesn't clobber secrets/answers. Read keys without
# sourcing (a value may contain spaces/quotes): only set a var if not already in the env.
get_env() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2-; }
if [[ -f "$ENV_FILE" ]]; then
  info "Existing .env found — loading current values as defaults"
  for _k in RADIX_DOMAIN POSTGRES_PASSWORD JWT_SECRET ADMIN_EMAIL ADMIN_PASSWORD \
            LLM_RUNTIME LLM_MODEL LLM_BASE_URL; do
    [[ -n "${!_k:-}" ]] || printf -v "$_k" '%s' "$(get_env "$_k")"
  done
fi

info "Configuration"
RADIX_DOMAIN="$(ask RADIX_DOMAIN 'Hostname/domain served by Caddy (self-signed TLS)' "${RADIX_DOMAIN:-localhost}")"
ADMIN_EMAIL="$(ask ADMIN_EMAIL 'First-boot admin email' "${ADMIN_EMAIL:-admin@example.com}")"

# Secrets: keep existing, else generate; interactive users may override the admin password.
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$(gen_secret)}"
JWT_SECRET="${JWT_SECRET:-$(gen_secret)}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(gen_secret | cut -c1-16)}"
if [[ "$INTERACTIVE" -eq 1 ]]; then
  ADMIN_PASSWORD="$(ask_secret 'First-boot admin password' "$ADMIN_PASSWORD")"
fi

# LLM runtime switch (SPEC §10; decision recorded in ADR 0007).
LLM_RUNTIME="$(ask LLM_RUNTIME 'LLM runtime — "bundled" (Ollama in-stack) or "external"' "${LLM_RUNTIME:-bundled}")"
case "$LLM_RUNTIME" in
  bundled)
    LLM_MODEL="$(ask LLM_MODEL 'Model tag to pull' "${LLM_MODEL:-qwen3.5:9b-q4_K_M}")"
    LLM_BASE_URL="http://ollama:11434/v1"
    COMPOSE_FILE="docker-compose.yml:docker-compose.llm.yml"
    [[ "$GPU" -eq 1 ]] && COMPOSE_FILE="${COMPOSE_FILE}:docker-compose.gpu.yml"
    ;;
  external)
    LLM_BASE_URL="$(ask LLM_BASE_URL 'External OpenAI-compatible base URL' "${LLM_BASE_URL:-http://127.0.0.1:11434/v1}")"
    LLM_MODEL="$(ask LLM_MODEL 'Model name exposed by that endpoint' "${LLM_MODEL:-qwen3.5:9b-q4_K_M}")"
    COMPOSE_FILE="docker-compose.yml"
    ;;
  *) die "LLM_RUNTIME must be 'bundled' or 'external' (got '$LLM_RUNTIME')" ;;
esac

info "Writing $ENV_FILE"
umask 077  # secrets inside — keep .env owner-only
cat > "$ENV_FILE" <<EOF
# Radix configuration — generated by deploy/install.sh. See .env.example for docs.

# --- Domain / TLS (Caddy, self-signed) ---
RADIX_DOMAIN=${RADIX_DOMAIN}

# --- Database ---
POSTGRES_USER=radix
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=radix

# --- LLM (SPEC §2, §10) ---
LLM_RUNTIME=${LLM_RUNTIME}
LLM_PROVIDER=ollama
LLM_MODEL=${LLM_MODEL}
LLM_BASE_URL=${LLM_BASE_URL}

# --- Compose wiring (managed by install.sh) ---
COMPOSE_FILE=${COMPOSE_FILE}

# --- Pipeline ---
EMBED_DEVICE=auto
OCR_LANGS=ita+eng+deu
SYNC_INTERVAL_MIN=5

# --- Storage ---
DATA_DIR=./data
SOURCES_DIR=./data/sources

# --- Security ---
JWT_SECRET=${JWT_SECRET}
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
EOF
ok ".env written (permissions 600)"

# --- 4. Bring the stack up ---------------------------------------------------
info "Building and starting the stack (this pulls images on first run)…"
$DOCKER compose up -d --build

# --- 5. Pull the bundled model ----------------------------------------------
if [[ "$LLM_RUNTIME" == "bundled" ]]; then
  info "Waiting for the Ollama container to be ready…"
  for _ in $(seq 1 60); do
    $DOCKER compose exec -T ollama ollama list >/dev/null 2>&1 && break
    sleep 3
  done
  info "Pulling model '${LLM_MODEL}' (this can take several minutes)…"
  $DOCKER compose exec -T ollama ollama pull "${LLM_MODEL}" || \
    warn "Model pull failed — run '$DOCKER compose exec ollama ollama pull ${LLM_MODEL}' by hand."
fi

# --- 6. Final healthcheck ----------------------------------------------------
info "Waiting for the API to report healthy…"
URL="https://${RADIX_DOMAIN}/api/v1/health"
HEALTHY=0
for _ in $(seq 1 40); do
  if curl -fsk "$URL" 2>/dev/null | grep -q '"status":"ok"'; then HEALTHY=1; break; fi
  sleep 3
done

echo
if [[ "$HEALTHY" -eq 1 ]]; then
  ok "Radix is up and healthy."
else
  warn "API not healthy yet — check '$DOCKER compose logs -f api'. Components may still be warming up."
fi
info "Open:  https://${RADIX_DOMAIN}/   (self-signed certificate — accept the browser warning)"
info "Admin: ${ADMIN_EMAIL}  (password set during install; stored in .env)"
if [[ "$LLM_RUNTIME" == "bundled" && "$GPU" -eq 0 ]]; then
  warn "Running the LLM on CPU — expect slower answers (SPEC §10 CPU profile)."
fi
