#!/usr/bin/env bash
# One-command development (ARCHITECTURE §5.1, BUILD_PLAN §5.9): the API (mock by default) on
# :8000 and Expo web on :8081, pointed at each other. Ctrl-C (or any exit) stops both.
#
#   make dev                      # or: scripts/dev.sh
#   API_PORT=8010 WEB_PORT=8091 scripts/dev.sh
#   DEV_OPEN_BROWSER=0 scripts/dev.sh     # do not open a browser tab (Metro still serves web)
#
# With no apps/api/.env the API runs AI_PROVIDER=mock (zero keys, data_use_tier "demo").
# An apps/api/.env with billed GEMINI_KEYS is used as is.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$HOME/.local/node/bin:$PATH"

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-8081}"
API_HOST="${API_HOST:-127.0.0.1}"
API_URL="${EXPO_PUBLIC_API_URL:-http://127.0.0.1:${API_PORT}}"
CORS="${CORS_ORIGINS:-http://localhost:${WEB_PORT},http://127.0.0.1:${WEB_PORT}}"
DEV_OPEN_BROWSER="${DEV_OPEN_BROWSER:-1}"

say() { printf '\033[1m[dev]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[dev]\033[0m %s\n' "$*" >&2; exit 1; }

port_busy() { lsof -ti "tcp:$1" -sTCP:LISTEN >/dev/null 2>&1; }

[ -x "$ROOT/apps/api/.venv/bin/uvicorn" ] || die "apps/api/.venv is missing (see README → Quickstart)."
command -v node >/dev/null 2>&1 || die "node not found; expected Node 24 in \$HOME/.local/node/bin."
[ -d "$ROOT/apps/mobile/node_modules" ] || die "apps/mobile/node_modules is missing (see README)."
port_busy "$API_PORT" && die "port $API_PORT is already in use (another API?). Stop it or set API_PORT."
port_busy "$WEB_PORT" && die "port $WEB_PORT is already in use (another Metro?). Stop it or set WEB_PORT."

PIDS=()

kill_tree() {  # kill a process and all its descendants (uvicorn --reload and npx spawn children)
  local pid="$1" child
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do kill_tree "$child"; done
  kill "$pid" 2>/dev/null || true
}

cleanup() {
  trap - EXIT INT TERM
  say "stopping API and Expo…"
  local pid
  for pid in "${PIDS[@]:-}"; do [ -n "$pid" ] && kill_tree "$pid"; done
  sleep 1
  for pid in "${PIDS[@]:-}"; do [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

provider="mock (no apps/api/.env)"
[ -f "$ROOT/apps/api/.env" ] && provider="from apps/api/.env"
say "API  → http://${API_HOST}:${API_PORT}   provider: ${provider}   CORS: ${CORS}"
(
  cd "$ROOT/apps/api"
  exec env CORS_ORIGINS="$CORS" .venv/bin/uvicorn proxyhealth_api.main:app \
    --reload --host "$API_HOST" --port "$API_PORT"
) &
PIDS+=("$!")

for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1 \
  || die "the API did not answer /health within 60 s (see the log above)."
say "API is up: $(curl -fsS "http://127.0.0.1:${API_PORT}/health")"

web_flag=(--web)
[ "$DEV_OPEN_BROWSER" = "0" ] && web_flag=()
say "Web  → http://localhost:${WEB_PORT}   EXPO_PUBLIC_API_URL=${API_URL}"
(
  cd "$ROOT/apps/mobile"
  exec env EXPO_PUBLIC_API_URL="$API_URL" npx expo start ${web_flag[@]+"${web_flag[@]}"} --port "$WEB_PORT"
) &
PIDS+=("$!")

# Stay in the foreground until either child exits (or Ctrl-C); the trap stops the other one.
while :; do
  for pid in "${PIDS[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      say "a process exited (pid $pid); shutting down."
      exit 1
    fi
  done
  sleep 2
done
