#!/usr/bin/env bash
# Point the API at the local model: write apps/api/.env from the preset apps/api/.env.local-ai.example
# (AI_PROVIDER=openai_compat, Ollama at http://127.0.0.1:11434/v1, qwen3.5:4b for both tiers, data-use
# tier "local", model label Qwen, json_schema output, thinking off). Guide: docs/LOCAL_AI.md;
# research: docs/research/free-ai-providers.md §4.2–§4.5. Install Ollama first: make local-ai-setup.
#
#   scripts/use-local-ai.sh --dry-run          # show the .env it would write and what happens to yours
#   scripts/use-local-ai.sh                    # write it (refuses when a different .env exists)
#   scripts/use-local-ai.sh --force            # back up the existing .env, then write
#   scripts/use-local-ai.sh --model qwen3.5:9b # another local model (label from the name, or --label)
#   scripts/use-local-ai.sh --restore          # put your newest .env backup back (e.g. Gemini keys)
#   scripts/use-local-ai.sh --off              # move .env aside: the API runs AI_PROVIDER=mock (zero keys)
#
# Before writing, the preset is checked by the API's own Settings (boot rules included); a refusal
# writes nothing (--no-check skips the check). Backups are apps/api/.env.bak-YYYYmmdd-HHMMSS, mode 600,
# git-ignored. A .env equal to the preset is never backed up (it can be written again at any time).
# Options: --dry-run · --force · --model <tag> · --label <name> · --restore · --off · --no-check ·
#          --self-test · --help.  Exit codes: 0 ok · 1 error · 3 refused (existing .env, model tag, check)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="$ROOT/apps/api"
PRESET="$API/.env.local-ai.example"
# USE_LOCAL_AI_TARGET exists only for --self-test (a scratch path); leave it unset.
TARGET="${USE_LOCAL_AI_TARGET:-$API/.env}"
TARGET_DIR="$(dirname "$TARGET")"

DRY_RUN=0
FORCE=0
CHECK=1
ACTION=write
MODEL=""
LABEL=""
TMP_FILES=()

say()  { printf '\033[1m[use-local-ai]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[use-local-ai]\033[0m %s\n' "$*" >&2; }
die()  { local code="$1"; shift; printf '\033[1;31m[use-local-ai]\033[0m %s\n' "$*" >&2; exit "$code"; }
usage() { sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; }
cleanup() { local f; for f in "${TMP_FILES[@]:-}"; do if [ -n "$f" ]; then rm -f "$f"; fi; done; return 0; }
trap cleanup EXIT

# Same tag rules as scripts/setup-local-ai.sh (research §1.5, §3.1): sized tag, no cloud/thinking/latest,
# no -mlx/q8_0/bf16/fp16.
model_refusal() {
  local tag="$1" part
  printf '%s' "$tag" | grep -Eq '^[a-z0-9][a-z0-9._/-]*:[a-z0-9][a-z0-9._-]*$' \
    || { echo "'$tag' is not a sized Ollama tag (name:size, e.g. qwen3.5:4b)"; return; }
  part="${tag#*:}"
  case "$part" in
    latest) echo "type the size tag, not :latest (qwen3.5:latest is the 9B)" ;;
    *cloud*) echo "'$tag' is an Ollama cloud tag: it sends prompts to Ollama's servers" ;;
    *thinking*) echo "'$tag' is a thinking build (slow on this Mac)" ;;
    *mlx*|*q8_0*|*bf16*|*fp16*) echo "'$tag' is too big for this Mac: never pull -mlx, q8_0, bf16 or fp16 tags (research §3.1)" ;;
    *) if [ "${tag%%:*}" = qwen3-vl ] && [ "${part%instruct*}" = "$part" ]; then
         echo "'$tag' is the qwen3-vl thinking build; use qwen3-vl:8b-instruct"
       fi ;;
  esac
}

label_for() {  # consent copy shows this as {model}
  case "$1" in
    qwen*) echo Qwen ;;
    gemma*) echo Gemma ;;
    minicpm*) echo MiniCPM ;;
    *) echo "" ;;
  esac
}

render() {  # the .env content: the preset, with the model and label swapped when asked
  local model="${MODEL:-}" label="${LABEL:-}"
  echo "# Written by scripts/use-local-ai.sh from apps/api/.env.local-ai.example. Edit freely."
  echo "# Switch back: scripts/use-local-ai.sh --restore (your previous .env) or --off (mock)."
  if [ -z "$model" ]; then cat "$PRESET"; return; fi
  sed -e "s|^OPENAI_COMPAT_MODEL_PRO=.*|OPENAI_COMPAT_MODEL_PRO=$model|" \
      -e "s|^OPENAI_COMPAT_MODEL_FAST=.*|OPENAI_COMPAT_MODEL_FAST=$model|" \
      -e "s|^OPENAI_COMPAT_MODEL_LABEL=.*|OPENAI_COMPAT_MODEL_LABEL=$label|" "$PRESET"
}

# By the timestamped name, not mtime: mv keeps the original .env's mtime (set_aside, --restore).
newest_backup() { ls -1 "$TARGET".bak-* 2>/dev/null | sort | tail -n 1 || true; }

backup_path() {
  local path; path="$TARGET.bak-$(date +%Y%m%d-%H%M%S)"
  while [ -e "$path" ]; do sleep 1; path="$TARGET.bak-$(date +%Y%m%d-%H%M%S)"; done
  echo "$path"
}

# Move the current .env out of the way: deleted when it equals the preset, else kept as a backup.
set_aside() {
  local rendered="$1" dest
  [ -f "$TARGET" ] || return 0
  if [ "$(cat "$TARGET")" = "$rendered" ]; then
    say "the current .env is the local-AI preset; removing it (no backup needed)."
    [ "$DRY_RUN" = 1 ] || rm -f "$TARGET"
    return 0
  fi
  dest="$(backup_path)"
  say "backing up the current .env → ${dest#"$ROOT"/} (mode 600, git-ignored)"
  if [ "$DRY_RUN" = 0 ]; then mv "$TARGET" "$dest"; chmod 600 "$dest"; fi
}

write_target() {  # write_target <content>: atomic, mode 600
  local tmp
  [ "$DRY_RUN" = 1 ] && { say "would write ${TARGET#"$ROOT"/} (mode 600)."; return 0; }
  tmp="$(mktemp "$TARGET_DIR/.env.writing.XXXXXX")"; TMP_FILES+=("$tmp")
  printf '%s\n' "$1" > "$tmp"
  chmod 600 "$tmp"
  mv "$tmp" "$TARGET"
  say "wrote ${TARGET#"$ROOT"/}."
}

# Ask the API's own Settings whether it would boot with this .env (read-only; prints no secrets:
# Settings uses hide_input_in_errors, and the preset holds none).
check_settings() {
  local content="$1" tmp out rc=0
  [ -x "$API/.venv/bin/python" ] || { warn "apps/api/.venv is missing; cannot check the preset."; return 1; }
  tmp="$(mktemp "${TMPDIR:-/tmp}/use-local-ai.XXXXXX")"; TMP_FILES+=("$tmp")
  printf '%s\n' "$content" > "$tmp"
  out="$(cd "$API" && .venv/bin/python - "$tmp" 2>&1 <<'PY'
import sys

from proxyhealth_api.settings import Settings

try:
    settings = Settings(_env_file=sys.argv[1])  # type: ignore[call-arg]
    settings.validate_runtime()
except Exception as exc:  # noqa: BLE001 - report any refusal, never the inputs
    print(f"REFUSED: {type(exc).__name__}: {exc}")
    sys.exit(1)
tier = getattr(settings.data_use_tier, "value", settings.data_use_tier)
print(f"OK: provider={settings.ai_provider} data_use_tier={tier} "
      f"real_documents_allowed={settings.real_documents_allowed}")
PY
)" || rc=$?
  printf '%s\n' "$out" | sed 's/^/    /'
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q 'Extra inputs are not permitted'; then
    warn "this checkout's API does not know the OPENAI_COMPAT_* settings yet (the openai_compat provider has not landed)."
  fi
  return "$rc"
}

self_test() {  # file handling against a scratch target; never touches apps/api/.env
  local dir fails=0 me="${BASH_SOURCE[0]}" t rc
  dir="$(mktemp -d "${TMPDIR:-/tmp}/use-local-ai-test.XXXXXX")"
  t="$dir/.env"
  check() { if [ "$2" = "$3" ]; then printf '  ok    %s\n' "$1"; else printf '  FAIL  %s: got [%s], want [%s]\n' "$1" "$2" "$3"; fails=$((fails + 1)); fi; }
  quiet() { USE_LOCAL_AI_TARGET="$t" "$me" --no-check "$@" >/dev/null 2>&1; }
  quiet --dry-run; check "dry run writes nothing" "$(ls -A "$dir" | wc -l | tr -d ' ')" 0
  quiet; check "writes .env when none exists" "$([ -f "$t" ] && echo yes)" yes
  check ".env is mode 600" "$(stat -f%Lp "$t")" 600
  check "preset values present" "$(grep -c -E '^(AI_PROVIDER=openai_compat|OPENAI_COMPAT_BASE_URL=http://127\.0\.0\.1:11434/v1|OPENAI_COMPAT_DATA_TIER=local|OPENAI_COMPAT_MODEL_LABEL=Qwen|OPENAI_COMPAT_MODEL_PRO=qwen3\.5:4b|OPENAI_COMPAT_MODEL_FAST=qwen3\.5:4b|OPENAI_COMPAT_JSON_MODE=json_schema|OPENAI_COMPAT_REASONING=none)$' "$t")" 8
  rc=0; quiet || rc=$?; check "same preset again is a no-op" "$rc" 0
  printf 'AI_PROVIDER=gemini\nGEMINI_KEYS=[]\n' > "$t"
  rc=0; quiet || rc=$?; check "refuses a different .env without --force" "$rc" 3
  check "different .env left untouched" "$(head -n 1 "$t")" "AI_PROVIDER=gemini"
  quiet --force; check "--force backs up" "$(ls -A "$dir" | grep -c '^\.env\.bak-' || true)" 1
  check "backup keeps the old content" "$(head -n 1 "$(ls -1t "$t".bak-* | head -n 1)")" "AI_PROVIDER=gemini"
  check "backup is mode 600" "$(stat -f%Lp "$(ls -1t "$t".bak-* | head -n 1)")" 600
  check "--force wrote the preset" "$(grep -c '^OPENAI_COMPAT_DATA_TIER=local$' "$t")" 1
  quiet --restore; check "--restore brings the backup back" "$(head -n 1 "$t")" "AI_PROVIDER=gemini"
  check "--restore of the preset leaves no extra backup" "$(ls -A "$dir" | grep -c '^\.env\.bak-' || true)" 0
  quiet --force --model qwen3.5:9b
  check "--model sets both tiers" "$(grep -c -E '^OPENAI_COMPAT_MODEL_(PRO|FAST)=qwen3\.5:9b$' "$t")" 2
  check "--model keeps label Qwen" "$(grep -c '^OPENAI_COMPAT_MODEL_LABEL=Qwen$' "$t")" 1
  rc=0; quiet --force --model gemma4:cloud || rc=$?; check "cloud tag refused" "$rc" 3
  rc=0; quiet --force --model qwen3-vl:8b || rc=$?; check "qwen3-vl thinking tag refused" "$rc" 3
  rc=0; quiet --force --model llava:7b || rc=$?; check "unknown family needs --label" "$rc" 3
  for tag in qwen3.5:9b-mlx qwen3.5:4b-q8_0 qwen3.5:4b-bf16 qwen3.5:4b-fp16; do
    rc=0; quiet --force --model "$tag" || rc=$?; check "too-big tag $tag refused" "$rc" 3
  done
  quiet --off; check "--off moves .env aside" "$([ -e "$t" ] && echo present || echo absent)" absent
  # --restore picks the newest backup by its timestamped name, even when mv kept an older mtime.
  rm -f "$t" "$t".bak-*
  printf '# HOSTED\n' > "$t.bak-20261001-215318"; touch -t 202610012153 "$t.bak-20261001-215318"
  printf '# GEMINI\n' > "$t.bak-20261001-215319"; touch -t 202609010000 "$t.bak-20261001-215319"
  quiet --restore; check "--restore takes the newest-named backup, not the newest mtime" "$(head -n 1 "$t")" "# GEMINI"
  rm -rf "$dir"
  [ "$fails" -eq 0 ] || die 1 "self-test: $fails failure(s)"
  say "self-test: all checks passed"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --force) FORCE=1 ;;
    --no-check) CHECK=0 ;;
    --model) [ $# -ge 2 ] || die 1 "--model needs a tag"; MODEL="$2"; shift ;;
    --model=*) MODEL="${1#*=}" ;;
    --label) [ $# -ge 2 ] || die 1 "--label needs a name"; LABEL="$2"; shift ;;
    --label=*) LABEL="${1#*=}" ;;
    --restore) ACTION=restore ;;
    --off) ACTION=off ;;
    --self-test) ACTION=self_test ;;
    -h|--help) usage; exit 0 ;;
    *) die 1 "unknown option: $1 (see --help)" ;;
  esac
  shift
done

[ "$ACTION" = self_test ] && { self_test; exit 0; }
[ -f "$PRESET" ] || die 1 "missing preset ${PRESET#"$ROOT"/}"
[ "$DRY_RUN" = 1 ] && say "DRY RUN: nothing is written, moved or deleted."

if [ -n "$MODEL" ]; then
  reason="$(model_refusal "$MODEL")"
  [ -z "$reason" ] || die 3 "model refused: $reason"
  [ -n "$LABEL" ] || LABEL="$(label_for "$MODEL")"
  [ -n "$LABEL" ] || die 3 "no consent label known for '$MODEL'; pass --label <Name> (shown as {model} in the consent copy)."
fi
if [ -n "$LABEL" ] && ! printf '%s' "$LABEL" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9 .-]{0,39}$'; then
  die 1 "--label must be a short plain name (letters, digits, space, dot, dash)."
fi
rendered="$(render)"

case "$ACTION" in
  off)
    [ -f "$TARGET" ] || { say "no ${TARGET#"$ROOT"/}: the API already runs AI_PROVIDER=mock."; exit 0; }
    set_aside "$rendered"
    say "done: with no .env the API runs AI_PROVIDER=mock (zero keys, sample papers). Restart make dev."
    exit 0 ;;
  restore)
    backup="$(newest_backup)"
    [ -n "$backup" ] || die 1 "no backup found (${TARGET#"$ROOT"/}.bak-*)."
    say "restoring ${backup#"$ROOT"/} → ${TARGET#"$ROOT"/}"
    set_aside "$rendered"
    if [ "$DRY_RUN" = 0 ]; then mv "$backup" "$TARGET"; chmod 600 "$TARGET"; fi
    say "done. Restart make dev to use it."
    exit 0 ;;
esac

# ---- write ----------------------------------------------------------------------------------------
say "the .env this writes (${TARGET#"$ROOT"/}; no secrets in it):"
printf '%s\n' "$rendered" | grep -Ev '^[[:space:]]*(#|$)' | sed 's/^/    /'
overridden=""
for key in $(printf '%s\n' "$rendered" | sed -n 's/^\([A-Z_][A-Z0-9_]*\)=.*/\1/p'); do
  if printenv "$key" >/dev/null 2>&1; then overridden="$overridden $key"; fi
done
[ -z "$overridden" ] || warn "set in your shell, so they win over the .env:$overridden"

if [ "$CHECK" = 1 ]; then
  say "checking it with the API's own Settings (boot rules included):"
  if ! check_settings "$rendered"; then
    if [ "$DRY_RUN" = 1 ]; then warn "a real run would stop here (or pass --no-check)."
    else die 3 "the API refused this preset; nothing was written. Fix the cause above, or pass --no-check."; fi
  fi
fi

if [ -f "$TARGET" ]; then
  if [ "$(cat "$TARGET")" = "$rendered" ]; then
    say "${TARGET#"$ROOT"/} already holds this preset; nothing to do."
    exit 0
  fi
  if [ "$FORCE" = 0 ]; then
    if [ "$DRY_RUN" = 1 ]; then
      warn "a different ${TARGET#"$ROOT"/} exists: a real run refuses without --force (with --force it is backed up first)."
      exit 0
    fi
    die 3 "a different ${TARGET#"$ROOT"/} exists; not overwriting it. Re-run with --force to back it up and write the preset."
  fi
  set_aside "$rendered"
fi
write_target "$rendered"
if [ "$DRY_RUN" = 0 ]; then
  say "next: make local-ai-check (a sample paper through the pipeline), then make dev."
  say "Ollama must be running with the model pulled: make local-ai-setup."
fi
