#!/usr/bin/env bash
# make smoke (BUILD_PLAN §5.9 step 2): boot the API in mock mode on a free local port with a
# throw-away VAR_DIR, wait for /health, run apps/api/scripts/smoke.py against it, and always stop
# the server — pass or fail. Zero keys; an apps/api/.env with keys is overridden to mock.
#
#   scripts/smoke.sh                 # free port, quiet server log (shown on failure)
#   SMOKE_PORT=8031 scripts/smoke.sh
#   scripts/smoke.sh --quiet         # extra args go to smoke.py
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/apps/api/.venv/bin/python"
[ -x "$PY" ] || { echo "[smoke] apps/api/.venv is missing" >&2; exit 1; }

PORT="${SMOKE_PORT:-$("$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')}"
if lsof -ti "tcp:$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[smoke] port $PORT is already in use" >&2
  exit 1
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/proxyhealth-smoke.XXXXXX")"
LOG="$WORK/api.log"
SERVER_PID=""

stop_server() {
  local status=$?
  set +e  # never let cleanup change the exit status (errexit/pipefail inside an EXIT trap would)
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$SERVER_PID" 2>/dev/null || break; sleep 0.3; done
    kill -9 "$SERVER_PID" 2>/dev/null || true
  fi
  # Belt and braces: nothing of ours may keep listening on the port.
  for pid in $(lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null); do
    if [ "$pid" = "$SERVER_PID" ]; then kill -9 "$pid" 2>/dev/null; fi
  done
  rm -rf "$WORK"
  return "$status"
}
trap stop_server EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "[smoke] starting the mock API on http://127.0.0.1:$PORT (VAR_DIR=$WORK/var)"
(
  cd "$ROOT/apps/api"
  exec env \
    AI_PROVIDER=mock ENV=development GEMINI_KEYS='[]' ALLOW_UNPAID_KEYS=0 \
    ALLOW_UNPAID_REAL_DOCUMENTS=false APP_TOKEN='' ADMIN_TOKEN='' \
    VAR_DIR="$WORK/var" INSTALL_HASH_SECRET=smoke LOG_LEVEL=warning \
    MOCK_LATENCY_MIN_MS=0 MOCK_LATENCY_MAX_MS=20 \
    RATE_LIMIT_ANALYZE_PER_HOUR=100000 RATE_LIMIT_ANALYZE_PER_DAY=1000000 \
    RATE_LIMIT_IP_PER_MINUTE=100000 RATE_LIMIT_IP_PER_DAY=1000000 \
    .venv/bin/uvicorn proxyhealth_api.main:app --host 127.0.0.1 --port "$PORT" --no-access-log
) >"$LOG" 2>&1 &
SERVER_PID=$!

status=0
"$PY" "$ROOT/apps/api/scripts/smoke.py" --base-url "http://127.0.0.1:$PORT" --wait 60 "$@" || status=$?
if [ "$status" -ne 0 ]; then
  echo "[smoke] FAILED (exit $status). Last lines of the API log:" >&2
  tail -n 40 "$LOG" >&2 || true
else
  echo "[smoke] passed"
fi
exit "$status"
