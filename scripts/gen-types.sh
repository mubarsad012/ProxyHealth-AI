#!/usr/bin/env bash
# Contract generation (API_CONTRACT §5, BUILD_PLAN §4.3): Pydantic → apps/api/openapi.json →
# apps/mobile/src/api/schema.d.ts (openapi-typescript; no running server needed).
#
#   scripts/gen-types.sh           regenerate both files (the contract owner runs this — WP0)
#   scripts/gen-types.sh --check   write nothing; exit 1 if either committed file is stale (CI)
#   scripts/gen-types.sh --check-openapi | --check-types   one half only (the two CI jobs)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$HOME/.local/node/bin:$PATH"
PY="$ROOT/apps/api/.venv/bin/python"
MODE="${1:-write}"

case "$MODE" in
  write)
    "$PY" "$ROOT/apps/api/scripts/export_openapi.py"
    (cd "$ROOT/apps/mobile" && npm run --silent gen:types)
    echo "[gen-types] openapi.json and schema.d.ts regenerated"
    ;;
  --check|--check-openapi|--check-types)
    tmp="$(mktemp -d "${TMPDIR:-/tmp}/gen-types.XXXXXX")"
    trap 'rm -rf "$tmp"' EXIT
    if [ "$MODE" != "--check-types" ]; then
    # 1. The committed snapshot equals what create_app() produces now (same code path as
    #    scripts/export_openapi.py, written to a temp file instead of the repo).
    (cd "$ROOT/apps/api" && "$PY" - "$tmp/openapi.json" <<'PY'
import sys
from pathlib import Path

from proxyhealth_api.main import create_app, openapi_json
from proxyhealth_api.settings import Settings

Path(sys.argv[1]).write_text(openapi_json(create_app(Settings(_env_file=None))), encoding="utf-8")
PY
    )
    if ! cmp -s "$tmp/openapi.json" "$ROOT/apps/api/openapi.json"; then
      echo "[gen-types] apps/api/openapi.json is stale: run scripts/gen-types.sh (contract owner)" >&2
      diff -u "$ROOT/apps/api/openapi.json" "$tmp/openapi.json" | head -40 >&2 || true
      exit 1
    fi
    echo "[gen-types] openapi.json is up to date"
    fi
    if [ "$MODE" != "--check-openapi" ]; then
    # 2. The committed TS types equal openapi-typescript's output for the committed snapshot.
    (cd "$ROOT/apps/mobile" && npx --no-install openapi-typescript ../api/openapi.json -o "$tmp/schema.d.ts" >/dev/null)
    if ! cmp -s "$tmp/schema.d.ts" "$ROOT/apps/mobile/src/api/schema.d.ts"; then
      echo "[gen-types] apps/mobile/src/api/schema.d.ts is stale: run scripts/gen-types.sh" >&2
      diff -u "$ROOT/apps/mobile/src/api/schema.d.ts" "$tmp/schema.d.ts" | head -40 >&2 || true
      exit 1
    fi
    echo "[gen-types] schema.d.ts is up to date"
    fi
    ;;
  *)
    echo "usage: scripts/gen-types.sh [--check|--check-openapi|--check-types]" >&2
    exit 2
    ;;
esac
