#!/usr/bin/env bash
# The full CI sequence, locally (BUILD_PLAN §3 WP8 row, §5.9 step 3, §6). Runs in order and
# stops at the first failure; .github/workflows/ci.yml runs the same steps in two jobs.
#
#   scripts/ci.sh                  # everything
#   CI_FROM=mobile-tsc scripts/ci.sh   # resume from a step (names in the "steps" list below)
#   CI_ONLY=privacy scripts/ci.sh      # run one step
#
# Steps: pytest · ruff · mypy (BUILD_PLAN §1.4 form) · openapi snapshot + TS types idempotence ·
# make_fixtures --check · sync_to_mobile --check · YAML parses · no xfail outside tests/live ·
# privacy-claims + readability · eas.json https · mobile tsc · jest · expo lint ·
# expo config --type prebuild · web export (--clear) with dist/privacy/index.html and a static-host
# rewrite for every dynamic route (scripts/web-host-rules.py --check).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$HOME/.local/node/bin:$PATH"
API="$ROOT/apps/api"
MOBILE="$ROOT/apps/mobile"
PY="$API/.venv/bin/python"
export EXPO_PUBLIC_API_URL="${EXPO_PUBLIC_API_URL:-http://127.0.0.1:8000}"
CI_FROM="${CI_FROM:-}"
CI_ONLY="${CI_ONLY:-}"

started_all=$(date +%s)
reached_from=0
[ -z "$CI_FROM" ] && reached_from=1

run() {  # run <name> <description> <command...>
  local name="$1" desc="$2"; shift 2
  if [ -n "$CI_ONLY" ] && [ "$CI_ONLY" != "$name" ]; then return 0; fi
  if [ "$reached_from" -eq 0 ]; then
    if [ "$CI_FROM" = "$name" ]; then reached_from=1; else return 0; fi
  fi
  printf '\n\033[1m▶ %-14s\033[0m %s\n' "$name" "$desc"
  local t0; t0=$(date +%s)
  if "$@"; then
    printf '\033[32m✔ %-14s\033[0m %ss\n' "$name" "$(( $(date +%s) - t0 ))"
  else
    local code=$?
    printf '\n\033[1;31m✘ %s failed (exit %s) after %ss — stopping.\033[0m\n' "$name" "$code" "$(( $(date +%s) - t0 ))" >&2
    exit "$code"
  fi
}

no_xfail_outside_live() {
  local hits
  hits="$(grep -rn "xfail" "$API/tests" --include='*.py' | grep -v "/tests/live/" || true)"
  if [ -n "$hits" ]; then
    echo "xfail markers outside tests/live (BUILD_PLAN §6 step 1):" >&2
    echo "$hits" >&2
    return 1
  fi
  echo "no xfail outside tests/live"
}

yaml_parses() {
  "$PY" - "$ROOT" <<'PY'
import sys
from pathlib import Path

import yaml

root = Path(sys.argv[1])
files = sorted((root / "apps/api/data").rglob("*.yaml")) + sorted((root / ".github").rglob("*.yml"))
bad = []
for f in files:
    try:
        yaml.safe_load(f.read_text("utf-8"))
    except yaml.YAMLError as exc:
        bad.append(f"{f.relative_to(root)}: {exc}")
print(f"{len(files)} YAML files parsed")
if bad:
    print("\n".join(bad), file=sys.stderr)
    sys.exit(1)
PY
}

eas_https() {  # Play "secure transmission": preview/production builds must talk HTTPS (COMPLIANCE §11)
  "$PY" - "$MOBILE/eas.json" <<'PY'
import json
import sys

cfg = json.load(open(sys.argv[1], encoding="utf-8"))
bad = []
for name in ("preview", "production"):
    url = cfg.get("build", {}).get(name, {}).get("env", {}).get("EXPO_PUBLIC_API_URL", "")
    if not url.startswith("https://"):
        bad.append(f"eas.json build.{name}.env.EXPO_PUBLIC_API_URL must be https:// (got {url!r})")
if bad:
    print("\n".join(bad), file=sys.stderr)
    sys.exit(1)
print("preview and production API URLs are https://")
PY
}

mobile() { (cd "$MOBILE" && "$@"); }

ensure_expo_env() {  # typed routes need expo-env.d.ts (git-ignored); CI creates it (BUILD_PLAN §1.4)
  if [ ! -f "$MOBILE/expo-env.d.ts" ]; then
    mobile npx expo customize tsconfig.json
  fi
  mobile npx tsc --noEmit
}

prebuild_config() { mobile npx expo config --type prebuild > /dev/null && echo "prebuild config resolves"; }

web_export() {
  local out="${CI_EXPORT_DIR:-}"
  local cleanup=0
  if [ -z "$out" ]; then out="$(mktemp -d "${TMPDIR:-/tmp}/proxyhealth-web.XXXXXX")"; cleanup=1; fi
  mobile npx expo export --platform web --clear --output-dir "$out"
  local ok=0
  [ -f "$out/privacy/index.html" ] && [ -f "$out/index.html" ] || ok=1
  if [ "$ok" -ne 0 ]; then echo "web export lacks index.html or privacy/index.html in $out" >&2; fi
  # Every dynamic route file (result/[id].html …) must get a static-host rewrite (DEPLOYMENT §2.3).
  if [ "$ok" -eq 0 ]; then python3 "$ROOT/scripts/web-host-rules.py" "$out" --check || ok=1; fi
  [ "$cleanup" -eq 1 ] && rm -rf "$out"
  return "$ok"
}

run pytest     "API tests (all but live)"               "$API/.venv/bin/pytest" "$API" -q -p no:cacheprovider
run ruff       "ruff check apps/api"                     "$API/.venv/bin/ruff" check "$API"
run mypy       "strict mypy (BUILD_PLAN §1.4 form)"      "$API/.venv/bin/mypy" --config-file "$API/pyproject.toml" "$API/proxyhealth_api" "$API/scripts" "$API/tests"
run openapi    "openapi.json + schema.d.ts idempotent"   "$ROOT/scripts/gen-types.sh" --check
run fixtures   "make_fixtures.py --check"                "$PY" "$API/scripts/make_fixtures.py" --check
run sync       "sync_to_mobile.py --check"               "$PY" "$API/scripts/sync_to_mobile.py" --check
run yaml       "every data/*.yaml and workflow parses"   yaml_parses
run xfail      "no xfail outside tests/live"             no_xfail_outside_live
run privacy    "privacy-claims + readability"            "$API/.venv/bin/pytest" -q -p no:cacheprovider "$API/tests/unit/test_privacy_claims.py" "$API/tests/unit/test_readability.py"
run eas-https  "eas.json preview/production use https"   eas_https
run mobile-tsc "tsc --noEmit"                            ensure_expo_env
run jest       "jest"                                    mobile npx jest --maxWorkers=2
run lint       "expo lint"                               mobile npx expo lint
run prebuild   "expo config --type prebuild"             prebuild_config
run web-export "expo export --platform web --clear"      web_export

if [ -n "$CI_FROM" ] && [ "$reached_from" -eq 0 ]; then
  echo "unknown step for CI_FROM: $CI_FROM" >&2
  exit 2
fi
printf '\n\033[1;32mci.sh: all steps green in %ss\033[0m\n' "$(( $(date +%s) - started_all ))"
