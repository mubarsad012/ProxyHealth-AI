#!/usr/bin/env bash
# Guarded local-AI setup: Ollama + an open-weight vision model (default qwen3.5:4b) on THIS Mac, so the
# developer can test ProxyHealth with real papers without sending them to any AI company.
# Spec: docs/research/free-ai-providers.md §3 (install, disk budget, context, pull, smoke test A);
# guide: docs/LOCAL_AI.md. The developer runs this themselves; `make dev`, CI and agents never do.
#
#   scripts/setup-local-ai.sh --dry-run     # print every step, change nothing (start here)
#   scripts/setup-local-ai.sh               # asks y/N before each download (Ollama ~0.2 GB, model 3.4 GB)
#   scripts/setup-local-ai.sh --model qwen3.5:9b --context 32768
#   scripts/setup-local-ai.sh --smoke-only  # only (start the server if needed and) re-run smoke test A
#
# What it does, in order (each step skipped when already done):
#   0. preflight: macOS 14+ on Apple silicon (arm64), not root, not CI, model tag allowed
#   1. disk budget BEFORE any download: Ollama (0.7 GiB) + model + 2.5 GiB headroom (research §3.1)
#   2. Ollama: curl the official https://ollama.com/download/Ollama.dmg, mount it read-only with
#      hdiutil, verify the code signature, copy Ollama.app to ~/Applications (no sudo, no admin
#      password), detach and delete the dmg
#   3. start `ollama serve` on 127.0.0.1:11434 with OLLAMA_CONTEXT_LENGTH (default 16384), flash
#      attention, q8_0 KV cache and a 10 min keep-alive (research §3.3); no launchctl, no app GUI
#   4. print the model size + free disk, ask y/N, then `ollama pull <model>`
#   5. smoke test A (research §3.6): the SYNTHETIC USCIS receipt fixture through /v1/chat/completions
#      with a base64 image and a JSON schema; nothing is written to disk
#
# Options: --dry-run · --yes (skip the y/N prompts) · --model <tag> · --model-gb <size> (needed for a
# tag not in the size table) · --context <tokens> · --smoke-only · --skip-smoke · --self-test · --help
# Exit codes: 0 ok · 1 error · 2 not enough disk · 3 refused (platform, model tag, declined prompt)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The ONLY download source (research §3.2, official link from https://ollama.com/download/mac).
readonly OLLAMA_DMG_URL="https://ollama.com/download/Ollama.dmg"
# Loopback only. LOCAL_AI_TEST_ADDR (127.0.0.1:<port>) exists so the script can be exercised against a
# fake OpenAI-compatible server without touching a real Ollama; leave it unset.
OLLAMA_ADDR="${LOCAL_AI_TEST_ADDR:-127.0.0.1:11434}"
printf '%s' "$OLLAMA_ADDR" | grep -Eq '^127\.0\.0\.1:[0-9]{2,5}$' \
  || { echo "LOCAL_AI_TEST_ADDR must be 127.0.0.1:<port>" >&2; exit 1; }
readonly OLLAMA_ADDR
readonly OLLAMA_URL="http://${OLLAMA_ADDR}"
readonly DEFAULT_MODEL="qwen3.5:4b"
readonly DEFAULT_CONTEXT=16384
# Disk sizes in tenths of a GiB (Ollama's "GB" is treated as GiB, which slightly overstates use: §3.1).
readonly DMG_TENTHS=2        # Ollama.dmg, about 200 MB, deleted after the copy
readonly APP_TENTHS=5        # Ollama.app installed, 0.2–0.5 GB [E]
readonly HEADROOM_TENTHS=25  # keep 2–3 GB free for macOS swap and updates (§3.1)
readonly SMOKE_FIXTURE_REL="apps/api/data/fixtures/uscis_i797c_receipt_i765/page-1.png"
readonly INSTALL_DIR="$HOME/Applications"

DRY_RUN=0
ASSUME_YES=0
MODEL="$DEFAULT_MODEL"
MODEL_GB=""
CONTEXT="$DEFAULT_CONTEXT"
SMOKE_ONLY=0
SKIP_SMOKE=0
SELF_TEST=0
GUARD_FAILED=0     # dry-run only: a guard that would stop a real run
SERVER_UP=0
STARTED_SERVER=0
SERVE_PID=""
MODEL_PRESENT=0
CLI=""
WORK_DIR=""
MOUNTED=""

say()  { printf '\033[1m[local-ai]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[local-ai]\033[0m %s\n' "$*" >&2; }
die()  { local code="$1"; shift; printf '\033[1;31m[local-ai]\033[0m %s\n' "$*" >&2; exit "$code"; }
step() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
usage() { sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; }

# A guard that refuses: a real run exits; a dry run records it, keeps printing the plan, exits non-zero.
refuse() {
  local code="$1"; shift
  if [ "$DRY_RUN" = 1 ]; then
    printf '\033[1;31m[local-ai]\033[0m WOULD STOP HERE: %s\n' "$*" >&2
    GUARD_FAILED="$code"
  else
    die "$code" "$*"
  fi
}

# Print a command; run it unless --dry-run.
run() {
  printf '  + '; printf '%q ' "$@"; printf '\n'
  [ "$DRY_RUN" = 1 ] && return 0
  "$@"
}

confirm() {  # confirm "question" → 0 yes / 1 no
  local answer=""
  if [ "$DRY_RUN" = 1 ]; then say "would ask: $1 [y/N]"; return 0; fi
  if [ "$ASSUME_YES" = 1 ]; then say "$1 [y/N] yes (--yes)"; return 0; fi
  if ! { : </dev/tty; } 2>/dev/null; then die 3 "no terminal to ask: $1  (run this in a terminal, or pass --yes)"; fi
  printf '\033[1m[local-ai]\033[0m %s [y/N] ' "$1"
  read -r answer </dev/tty || answer=""
  case "$answer" in y|Y|yes|YES|Yes) return 0 ;; *) return 1 ;; esac
}

fmt_tenths() { printf '%d.%d' "$(( $1 / 10 ))" "$(( $1 % 10 ))"; }

# Known model sizes in tenths of a GiB (research §2.1, §3.1; ollama.com tag pages, 2026-10-01).
model_size_tenths() {
  case "$1" in
    qwen3.5:0.8b) echo 10 ;;
    qwen3.5:2b) echo 27 ;;
    qwen3.5:4b) echo 34 ;;
    qwen3.5:9b) echo 66 ;;
    qwen3-vl:4b-instruct) echo 33 ;;
    qwen3-vl:8b-instruct) echo 61 ;;
    minicpm-v4.5:8b) echo 61 ;;
    gemma4:e4b-it-qat) echo 61 ;;
    *) echo "" ;;
  esac
}

# Why a model tag is refused (empty output = allowed). research §1.5, §3.1, §4.5.
model_refusal() {
  local tag="$1" name part
  [ -n "$tag" ] || { echo "no model tag given"; return; }
  if ! printf '%s' "$tag" | grep -Eq '^[a-z0-9][a-z0-9._/-]*(:[a-z0-9][a-z0-9._-]*)?$'; then
    echo "'$tag' is not an Ollama model tag (lowercase name:tag, as listed on ollama.com)"; return
  fi
  case "$tag" in
    *:*) name="${tag%%:*}"; part="${tag#*:}" ;;
    *) echo "type the size tag ('$tag' means '$tag:latest'; qwen3.5:latest is the 9B, 6.6 GB)"; return ;;
  esac
  case "$part" in
    latest) echo "'$tag' points at a default size; type the size tag (qwen3.5:latest is the 9B, 6.6 GB)"; return ;;
    *cloud*) echo "'$tag' is an Ollama cloud tag: it sends prompts to Ollama's servers (research §1.5)"; return ;;
    *thinking*) echo "'$tag' is a thinking build: much slower on this Mac (research §3.1, §4.5)"; return ;;
    *mlx*|*q8_0*|*bf16*|*fp16*) echo "'$tag' is too big for this Mac: never pull -mlx, q8_0, bf16 or fp16 tags (research §3.1)"; return ;;
  esac
  if [ "$name" = "qwen3-vl" ] && [ "${part%instruct*}" = "$part" ]; then
    echo "'$tag' is the thinking build (bare qwen3-vl size tags share the -thinking hash); use qwen3-vl:8b-instruct or qwen3-vl:4b-instruct (research §3.1)"; return
  fi
  echo ""
}

# Disk needed before starting, in tenths of a GiB: Ollama (if missing) + model (if missing) + headroom.
budget_tenths() {  # budget_tenths <ollama_installed 0|1> <model_present 0|1> <model_tenths>
  local need="$HEADROOM_TENTHS"
  [ "$1" = 1 ] || need=$(( need + DMG_TENTHS + APP_TENTHS ))
  [ "$2" = 1 ] || need=$(( need + $3 ))
  echo "$need"
}

# 1 = leave the model out of the step-1 budget: it is pulled, or Ollama is installed but stopped, so
# GET /api/tags cannot tell yet (after a reboot). Step 4 re-checks free disk against model + headroom
# once step 3 has started the server and asked again.
budget_model_present() {  # budget_model_present <ollama_installed 0|1> <server_up 0|1> <model_present 0|1>
  if [ "$3" = 1 ] || { [ "$1" = 1 ] && [ "$2" = 0 ]; }; then echo 1; else echo 0; fi
}

free_tenths() {  # free space on the volume holding the model store, in tenths of a GiB
  local dir="${OLLAMA_MODELS:-$HOME/.ollama/models}"
  while [ ! -d "$dir" ]; do dir="$(dirname "$dir")"; done
  df -Pk "$dir" | awk 'NR == 2 { printf "%d\n", $4 * 10 / 1048576 }'
}

app_cli() {  # the CLI inside an Ollama.app (Contents/Resources/ollama; -name is case-sensitive, so
             # the GUI binary Contents/MacOS/Ollama never matches on a case-insensitive volume)
  [ -d "$1/Contents" ] || return 1
  local hit
  hit="$(find "$1/Contents" -maxdepth 3 -type f -name ollama -perm -u+x 2>/dev/null | head -n 1)"
  [ -n "$hit" ] && echo "$hit"
}

find_cli() {  # the ollama binary: PATH first, then inside Ollama.app (no /usr/local/bin link needed)
  local app
  if command -v ollama >/dev/null 2>&1; then command -v ollama; return 0; fi
  for app in "$INSTALL_DIR/Ollama.app" "/Applications/Ollama.app"; do
    if app_cli "$app"; then return 0; fi
  done
  return 1
}

server_version() { curl -fsS --max-time 2 "$OLLAMA_URL/api/version" 2>/dev/null || true; }

model_is_present() {  # asks the running server (GET /api/tags); 1 when the server is down
  curl -fsS --max-time 5 "$OLLAMA_URL/api/tags" 2>/dev/null | tr -d ' \n' | grep -Fq "\"name\":\"$1\""
}

python_bin() {
  if [ -x "$ROOT/apps/api/.venv/bin/python" ]; then echo "$ROOT/apps/api/.venv/bin/python"
  elif [ -x /usr/bin/python3 ]; then echo /usr/bin/python3
  else return 1; fi
}

cleanup() {
  if [ -n "$MOUNTED" ]; then hdiutil detach "$MOUNTED" -quiet -force >/dev/null 2>&1 || true; fi
  if [ -n "$WORK_DIR" ] && [ -d "$WORK_DIR" ]; then rm -rf "$WORK_DIR"; fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

self_test() {  # unit checks of the pure guards above; no network, no disk writes
  local fails=0
  check() {  # check <description> <actual> <expected>
    if [ "$2" = "$3" ]; then printf '  ok    %s\n' "$1"
    else printf '  FAIL  %s: got [%s], want [%s]\n' "$1" "$2" "$3"; fails=$((fails + 1)); fi
  }
  allowed() { [ -z "$(model_refusal "$1")" ] && echo yes || echo no; }
  check "default model allowed" "$(allowed qwen3.5:4b)" yes
  check "9b allowed" "$(allowed qwen3.5:9b)" yes
  check "qwen3-vl instruct allowed" "$(allowed qwen3-vl:8b-instruct)" yes
  check "gemma4 qat allowed" "$(allowed gemma4:e4b-it-qat)" yes
  check "bare name refused" "$(allowed qwen3.5)" no
  check ":latest refused" "$(allowed qwen3.5:latest)" no
  check "bare qwen3-vl:8b refused (thinking hash)" "$(allowed qwen3-vl:8b)" no
  check "qwen3-vl:latest refused" "$(allowed qwen3-vl:latest)" no
  check "qwen3-vl bare name refused" "$(allowed qwen3-vl)" no
  check "-thinking refused" "$(allowed qwen3-vl:8b-thinking)" no
  check ":cloud refused" "$(allowed gemma4:cloud)" no
  check "-cloud refused" "$(allowed gemma4:31b-cloud)" no
  check "-mlx refused" "$(allowed qwen3.5:9b-mlx)" no
  check "q8_0 refused" "$(allowed qwen3.5:4b-q8_0)" no
  check "bf16 refused" "$(allowed qwen3.5:4b-bf16)" no
  check "shell metacharacters refused" "$(allowed 'qwen3.5:4b;rm')" no
  check "uppercase refused" "$(allowed Qwen3.5:4b)" no
  check "4b size" "$(model_size_tenths qwen3.5:4b)" 34
  check "9b size" "$(model_size_tenths qwen3.5:9b)" 66
  check "unknown size empty" "$(model_size_tenths foo:1b)" ""
  check "fresh 4b budget = 0.2+0.5+3.4+2.5" "$(budget_tenths 0 0 34)" 66
  check "fresh 9b budget" "$(budget_tenths 0 0 66)" 98
  check "installed, model present = headroom only" "$(budget_tenths 1 1 34)" 25
  check "installed, 4b missing" "$(budget_tenths 1 0 34)" 59
  check "installed, server down, model pulled: step 1 leaves the model out" \
    "$(budget_tenths 1 "$(budget_model_present 1 0 0)" 34)" 25
  check "installed, server up, model missing: step 1 counts the model" "$(budget_model_present 1 1 0)" 0
  check "not installed: step 1 counts the model" "$(budget_model_present 0 0 0)" 0
  check "server up, model pulled: step 1 leaves the model out" "$(budget_model_present 1 1 1)" 1
  check "format tenths" "$(fmt_tenths 66)" "6.6"
  check "format tenths < 1" "$(fmt_tenths 5)" "0.5"
  check "download URL is the official one" "$OLLAMA_DMG_URL" "https://ollama.com/download/Ollama.dmg"
  check "server is loopback" "$OLLAMA_ADDR" "127.0.0.1:11434"
  if grep -Eq 'setup-local-ai' "$ROOT/scripts/dev.sh" "$ROOT/scripts/ci.sh" "$ROOT/scripts/smoke.sh"; then
    check "make dev / ci / smoke never run this script" referenced not-referenced
  else
    check "make dev / ci / smoke never run this script" not-referenced not-referenced
  fi
  if [ "$fails" -gt 0 ]; then die 1 "self-test: $fails failure(s)"; fi
  say "self-test: all checks passed"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    --model) [ $# -ge 2 ] || die 1 "--model needs a tag"; MODEL="$2"; shift ;;
    --model=*) MODEL="${1#*=}" ;;
    --model-gb) [ $# -ge 2 ] || die 1 "--model-gb needs a size"; MODEL_GB="$2"; shift ;;
    --model-gb=*) MODEL_GB="${1#*=}" ;;
    --context) [ $# -ge 2 ] || die 1 "--context needs a number"; CONTEXT="$2"; shift ;;
    --context=*) CONTEXT="${1#*=}" ;;
    --smoke-only) SMOKE_ONLY=1 ;;
    --skip-smoke) SKIP_SMOKE=1 ;;
    --self-test) SELF_TEST=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die 1 "unknown option: $1 (see --help)" ;;
  esac
  shift
done

if [ "$SELF_TEST" = 1 ]; then self_test; exit 0; fi

[ "$DRY_RUN" = 1 ] && say "DRY RUN: every step is printed; nothing is downloaded, installed, started or written."

# ---- 0. preflight ---------------------------------------------------------------------------------
step "0. Preflight"
os="$(uname -s)"; arch="$(uname -m)"
[ "$os" = Darwin ] || die 3 "macOS only (this is $os). See docs/LOCAL_AI.md for other systems."
[ "$arch" = arm64 ] || die 3 "Apple silicon (arm64) only (this Mac is $arch): a 4B vision model is too slow without it."
macos="$(sw_vers -productVersion)"
[ "${macos%%.*}" -ge 14 ] || die 3 "Ollama needs macOS 14 or newer (this is $macos)."
[ "$(id -u)" -ne 0 ] || die 3 "do not run this with sudo: everything installs into your home folder."
if [ -n "${CI:-}" ] && [ "$DRY_RUN" = 0 ]; then die 3 "refusing to run in CI: the developer runs this by hand (docs/LOCAL_AI.md)."; fi
for tool in curl hdiutil ditto codesign df; do
  command -v "$tool" >/dev/null 2>&1 || die 1 "missing system tool: $tool"
done
reason="$(model_refusal "$MODEL")"
[ -z "$reason" ] || die 3 "model refused: $reason"
model_tenths="$(model_size_tenths "$MODEL")"
if [ -z "$model_tenths" ]; then
  [ -n "$MODEL_GB" ] || die 3 "unknown size for '$MODEL': pass --model-gb <size in GB from its ollama.com tag page>."
  printf '%s' "$MODEL_GB" | grep -Eq '^[0-9]+(\.[0-9])?$' || die 1 "--model-gb must look like 3.4"
  model_tenths=$(( 10#${MODEL_GB%%.*} * 10 )); case "$MODEL_GB" in *.*) model_tenths=$(( model_tenths + 10#${MODEL_GB#*.} )) ;; esac
fi
printf '%s' "$CONTEXT" | grep -Eq '^[0-9]+$' || die 1 "--context must be a number of tokens"
{ [ "$CONTEXT" -ge 8192 ] && [ "$CONTEXT" -le 65536 ]; } \
  || die 1 "--context must be 8192–65536 (16384 for one-page tests, 32768 for multi-page: research §3.3)"
PY="$(python_bin)" || die 1 "no Python found for the smoke test (expected apps/api/.venv)."
say "macOS $macos on $arch · model $MODEL ($(fmt_tenths "$model_tenths") GB) · context $CONTEXT tokens"

if CLI="$(find_cli)"; then OLLAMA_INSTALLED=1; else OLLAMA_INSTALLED=0; CLI="$INSTALL_DIR/Ollama.app/Contents/Resources/ollama"; fi
ver="$(server_version)"
if [ -n "$ver" ]; then SERVER_UP=1; fi
if [ "$SERVER_UP" = 1 ] && model_is_present "$MODEL"; then MODEL_PRESENT=1; fi
if [ "$SERVER_UP" = 1 ] && [ "$OLLAMA_INSTALLED" = 0 ]; then
  refuse 1 "an Ollama server answers on $OLLAMA_ADDR but no ollama command was found (PATH, ~/Applications, /Applications). Put it on PATH and run again."
fi
if [ "$SMOKE_ONLY" = 1 ] && [ "$SERVER_UP" = 0 ] && [ "$OLLAMA_INSTALLED" = 0 ]; then
  refuse 1 "Ollama is not installed: run this script without --smoke-only first."
fi
say "Ollama installed: $([ "$OLLAMA_INSTALLED" = 1 ] && echo "yes ($CLI)" || echo no)"
say "Ollama server on $OLLAMA_ADDR: $([ "$SERVER_UP" = 1 ] && echo "running $ver" || echo "not running")"
say "model $MODEL already pulled: $([ "$MODEL_PRESENT" = 1 ] && echo yes || echo "no (or the server is not running)")"
# Installed but stopped (e.g. after a reboot): whether the model is pulled is asked again after step 3.
PRESENCE_UNKNOWN=0
{ [ "$OLLAMA_INSTALLED" = 1 ] && [ "$SERVER_UP" = 0 ]; } && PRESENCE_UNKNOWN=1

# ---- 1. disk budget, BEFORE any download ----------------------------------------------------------
if [ "$SMOKE_ONLY" = 0 ]; then
  step "1. Disk budget (checked before any download; research §3.1)"
  budget_present="$(budget_model_present "$OLLAMA_INSTALLED" "$SERVER_UP" "$MODEL_PRESENT")"
  need="$(budget_tenths "$OLLAMA_INSTALLED" "$budget_present" "$model_tenths")"
  free="$(free_tenths)"
  parts=""
  [ "$OLLAMA_INSTALLED" = 1 ] || parts="Ollama dmg+app $(fmt_tenths $(( DMG_TENTHS + APP_TENTHS ))) + "
  [ "$budget_present" = 1 ] || parts="${parts}$MODEL $(fmt_tenths "$model_tenths") + "
  [ "$PRESENCE_UNKNOWN" = 0 ] || say "the server is not running, so $MODEL is left out here; step 4 checks free disk again before any pull."
  say "free: $(fmt_tenths "$free") GiB · need: $(fmt_tenths "$need") GiB (${parts}headroom $(fmt_tenths "$HEADROOM_TENTHS") for macOS swap and updates)"
  if [ "$free" -lt "$need" ]; then
    refuse 2 "not enough free disk: $(fmt_tenths "$free") GiB free, $(fmt_tenths "$need") GiB needed. Free about $(fmt_tenths $(( need - free ))) GiB (or point OLLAMA_MODELS at an external drive) and run this again. Nothing was downloaded."
  else
    left=$(( free - model_tenths * (1 - budget_present) - APP_TENTHS * (1 - OLLAMA_INSTALLED) ))
    say "OK: about $(fmt_tenths "$left") GiB will be left after setup$([ "$OLLAMA_INSTALLED" = 1 ] || echo ' (the dmg is deleted after the copy)')."
  fi
fi

# ---- 2. install Ollama ----------------------------------------------------------------------------
if [ "$SMOKE_ONLY" = 0 ]; then
  step "2. Install Ollama into ~/Applications (official dmg, no Homebrew, no sudo; research §3.2)"
  if [ "$OLLAMA_INSTALLED" = 1 ]; then
    say "already installed ($CLI); no download."
  else
    [ ! -e "$INSTALL_DIR/Ollama.app" ] || die 1 "$INSTALL_DIR/Ollama.app exists but has no ollama binary; move it to the Trash and run again."
    confirm "Download Ollama (about 200 MB) from $OLLAMA_DMG_URL and install it to $INSTALL_DIR?" \
      || die 3 "stopped: nothing was downloaded."
    if [ "$DRY_RUN" = 1 ]; then WORK_DIR_SHOWN="${TMPDIR:-/tmp}"; WORK_DIR_SHOWN="${WORK_DIR_SHOWN%/}/proxyhealth-local-ai.XXXXXX"
    else tmp_root="${TMPDIR:-/tmp}"; WORK_DIR="$(mktemp -d "${tmp_root%/}/proxyhealth-local-ai.XXXXXX")"; WORK_DIR_SHOWN="$WORK_DIR"; fi
    DMG="$WORK_DIR_SHOWN/Ollama.dmg"; MNT="$WORK_DIR_SHOWN/mnt"
    run curl -fL --proto '=https' --proto-redir '=https' --tlsv1.2 --retry 2 --connect-timeout 20 \
      -o "$DMG" -w 'downloaded %{size_download} bytes from %{url_effective}\n' "$OLLAMA_DMG_URL"
    if [ "$DRY_RUN" = 0 ]; then
      bytes="$(stat -f%z "$DMG")"
      { [ "$bytes" -ge 50000000 ] && [ "$bytes" -le 600000000 ]; } \
        || die 1 "unexpected download size ($bytes bytes; expected about 200 MB). Nothing was installed."
    fi
    run mkdir -p "$MNT"
    run hdiutil attach -nobrowse -readonly -noautoopen -mountpoint "$MNT" "$DMG"
    if [ "$DRY_RUN" = 0 ]; then
      MOUNTED="$MNT"
      [ -d "$MNT/Ollama.app" ] || die 1 "the disk image has no Ollama.app. Nothing was installed."
    fi
    run codesign --verify --deep --strict "$MNT/Ollama.app" \
      || die 1 "Ollama.app failed the code-signature check. Nothing was installed."
    run mkdir -p "$INSTALL_DIR"
    run ditto "$MNT/Ollama.app" "$INSTALL_DIR/Ollama.app"
    run hdiutil detach "$MNT" -quiet
    MOUNTED=""
    run rm -f "$DMG"
    CLI="$INSTALL_DIR/Ollama.app/Contents/Resources/ollama"
    if [ "$DRY_RUN" = 0 ]; then
      CLI="$(app_cli "$INSTALL_DIR/Ollama.app")" \
        || die 1 "installed, but no ollama program was found inside $INSTALL_DIR/Ollama.app; see docs/LOCAL_AI.md → Troubleshooting."
      spctl --assess --type execute "$INSTALL_DIR/Ollama.app" >/dev/null 2>&1 \
        && say "Gatekeeper accepts $INSTALL_DIR/Ollama.app (signed and notarized)." \
        || warn "Gatekeeper did not confirm notarization; the signature check passed. See docs/LOCAL_AI.md."
      OLLAMA_INSTALLED=1
    fi
    run "$CLI" --version
  fi
fi

# ---- 3. start the server --------------------------------------------------------------------------
step "3. Start the Ollama server on $OLLAMA_ADDR with OLLAMA_CONTEXT_LENGTH=$CONTEXT (research §3.3)"
if [ "$SERVER_UP" = 1 ]; then
  say "already running ($ver). Its settings come from whoever started it."
  warn "document prompts need a context of at least 16384 tokens (Ollama's default is 4096 on this Mac)."
  warn "if the CONTEXT column at the end shows less, quit Ollama and run this script again."
else
  if [ "$DRY_RUN" = 0 ] && lsof -ti "tcp:${OLLAMA_ADDR##*:}" -sTCP:LISTEN >/dev/null 2>&1; then
    die 1 "port ${OLLAMA_ADDR##*:} is busy but does not answer as Ollama; stop that program first."
  fi
  serve_cmd=(env -u OLLAMA_DEBUG "OLLAMA_HOST=$OLLAMA_ADDR" "OLLAMA_CONTEXT_LENGTH=$CONTEXT"
             OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_KEEP_ALIVE=10m nohup "$CLI" serve)
  printf '  + '; printf '%q ' "${serve_cmd[@]}"; printf '>/dev/null 2>&1 &\n'
  if [ "$DRY_RUN" = 0 ]; then
    "${serve_cmd[@]}" >/dev/null 2>&1 &
    SERVE_PID=$!
    STARTED_SERVER=1
    for _ in $(seq 1 30); do ver="$(server_version)"; [ -n "$ver" ] && break; sleep 1; done
    [ -n "$ver" ] || die 1 "the server did not answer within 30 s. Run '$CLI serve' in a terminal to see why."
    SERVER_UP=1
    say "server is up ($ver), pid $SERVE_PID, bound to $OLLAMA_ADDR only. Stop it later with: kill $SERVE_PID"
    model_is_present "$MODEL" && MODEL_PRESENT=1
    PRESENCE_UNKNOWN=0
  fi
fi

# ---- 4. pull the model ----------------------------------------------------------------------------
if [ "$SMOKE_ONLY" = 0 ]; then
  step "4. Pull $MODEL (research §3.4)"
  if [ "$MODEL_PRESENT" = 1 ]; then
    say "$MODEL is already pulled; no download."
  else
    [ "$PRESENCE_UNKNOWN" = 0 ] || say "dry run: the server is not running, so this cannot tell whether $MODEL is pulled; a real run asks after step 3 and skips the pull if it is."
    free="$(free_tenths)"
    # A dry run has not installed Ollama yet: count the app it would have added.
    [ "$DRY_RUN" = 1 ] && [ "$OLLAMA_INSTALLED" = 0 ] && free=$(( free - APP_TENTHS ))
    need=$(( model_tenths + HEADROOM_TENTHS ))
    say "$MODEL is $(fmt_tenths "$model_tenths") GB. Free now: $(fmt_tenths "$free") GiB; about $(fmt_tenths $(( free > model_tenths ? free - model_tenths : 0 ))) GiB after the pull."
    say "it goes to ${OLLAMA_MODELS:-~/.ollama/models}. One model at a time: 'ollama rm $MODEL' gives the space back."
    if [ "$free" -lt "$need" ] && [ "$PRESENCE_UNKNOWN" = 1 ]; then
      # Dry run with the server stopped: a real run starts it in step 3 and skips this step if pulled.
      warn "a real run stops here only if $MODEL is not pulled yet (the server is not running, so this dry run cannot tell): $(fmt_tenths "$free") GiB free, $(fmt_tenths "$need") GiB needed."
    elif [ "$free" -lt "$need" ]; then
      refuse 2 "not enough free disk for $MODEL: $(fmt_tenths "$free") GiB free, $(fmt_tenths "$need") GiB needed (model + $(fmt_tenths "$HEADROOM_TENTHS") headroom)."
    fi
    confirm "Download $MODEL ($(fmt_tenths "$model_tenths") GB) now?" \
      || die 3 "stopped before the model download. Run this again when you are ready.$([ "$STARTED_SERVER" = 1 ] && echo " The Ollama server this run started keeps running: kill $SERVE_PID stops it.")"
    run "$CLI" pull "$MODEL"
    run "$CLI" list
  fi
fi

# ---- 5. smoke test A ------------------------------------------------------------------------------
if [ "$SKIP_SMOKE" = 0 ]; then
  step "5. Smoke test A: SAMPLE paper, base64 image + JSON schema via /v1/chat/completions (research §3.6)"
  fixture="$ROOT/$SMOKE_FIXTURE_REL"
  [ -f "$fixture" ] || die 1 "missing sample fixture $SMOKE_FIXTURE_REL"
  say "sample: $SMOKE_FIXTURE_REL (a made-up USCIS receipt notice). The image is sent from memory; nothing is written."
  say "first call loads the model into memory, so allow 1–4 minutes."
  printf '  + '; printf '%q ' "$PY" - "$SMOKE_FIXTURE_REL" "$MODEL" "$OLLAMA_URL"; printf '<<PY (inline smoke test)\n'
  if [ "$DRY_RUN" = 0 ]; then
    [ "$SERVER_UP" = 1 ] || die 1 "the Ollama server is not running; run this script without --smoke-only first."
    smoke_rc=0
    "$PY" - "$fixture" "$MODEL" "$OLLAMA_URL" <<'PY' || smoke_rc=$?
import base64
import json
import re
import sys
import time
import urllib.error
import urllib.request

fixture, model, base = sys.argv[1:4]
with open(fixture, "rb") as fh:
    b64 = base64.b64encode(fh.read()).decode("ascii")
schema = {
    "type": "object",
    "properties": {
        "sender": {"type": "string"},
        "topic": {"type": "string"},
        "dates_verbatim": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["sender", "topic", "dates_verbatim"],
    "additionalProperties": False,
}
body = {
    "model": model,
    "reasoning_effort": "none",
    "temperature": 0,
    "max_tokens": 800,
    "stream": False,
    "messages": [
        {"role": "system", "content": "You read photographed letters. Reply with JSON only."},
        {"role": "user", "content": [
            {"type": "text", "text": "Who sent this letter, what is it about, and which dates are "
             "printed on it? Copy each date exactly as printed."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
        ]},
    ],
    "response_format": {"type": "json_schema",
                        "json_schema": {"name": "smoke", "strict": True, "schema": schema}},
}
request = urllib.request.Request(
    base + "/v1/chat/completions", data=json.dumps(body).encode("utf-8"), method="POST",
    headers={"Content-Type": "application/json", "Authorization": "Bearer ollama"},
)
started = time.monotonic()
try:
    with urllib.request.urlopen(request, timeout=600) as response:
        payload = json.load(response)
except urllib.error.HTTPError as exc:
    sys.exit(f"FAIL: Ollama answered HTTP {exc.code}: {exc.read()[:300]!r}")
except (urllib.error.URLError, TimeoutError) as exc:
    sys.exit(f"FAIL: no answer from {base}: {exc}")
elapsed = time.monotonic() - started
choice = payload["choices"][0]
content = choice.get("message", {}).get("content") or ""
content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
usage = payload.get("usage") or {}
out_tokens = usage.get("completion_tokens")
print(f"wall time {elapsed:.1f} s · prompt tokens {usage.get('prompt_tokens')} · "
      f"output tokens {out_tokens} · finish_reason {choice.get('finish_reason')}")
try:
    data = json.loads(content)
except json.JSONDecodeError:
    sys.exit("FAIL: the reply is not JSON:\n" + content[:600])
print(json.dumps(data, indent=2, ensure_ascii=False))
problems = []
if not isinstance(data, dict):
    problems.append("the reply is not a JSON object")
    data = {}
missing = sorted({"sender", "topic", "dates_verbatim"} - set(data))
if missing:
    problems.append("missing keys: " + ", ".join(missing))
sender = str(data.get("sender", "")).lower()
if "citizenship" not in sender and "uscis" not in sender:
    problems.append("sender does not name U.S. Citizenship and Immigration Services")
dates = [str(d) for d in data.get("dates_verbatim") or []]
for wanted in ("08/17/2026", "08/24/2026"):
    if not any(wanted in d for d in dates):
        problems.append(f"dates_verbatim lacks {wanted}")
if problems:
    sys.exit("FAIL: " + "; ".join(problems))
print("PASS: valid JSON with sender, topic and both printed dates (08/17/2026, 08/24/2026).")
PY
    run "$CLI" ps || true
    if [ "$smoke_rc" -ne 0 ]; then
      die 1 "smoke test A failed (above). A small model can miss once: re-run with --smoke-only. Still failing? docs/LOCAL_AI.md → Troubleshooting."
    fi
    say "write down the wall time and token counts: they replace the [E] speed estimates (research §3.7)."
  fi
fi

# ---- summary --------------------------------------------------------------------------------------
step "Next steps"
cat <<NEXT
  1. scripts/use-local-ai.sh --dry-run    # see the apps/api/.env it would write (AI_PROVIDER=openai_compat, tier local)
     scripts/use-local-ai.sh              # write it (backs up an existing .env; --force to replace one)
  2. make local-ai-check                  # a SAMPLE paper through the real pipeline with the local model
  3. make dev                             # the app on http://localhost:8081, reading with $MODEL on this Mac
  Stop the server: quit 'ollama serve' (kill its pid, or: pkill -f 'ollama serve').
  After a reboot: run this script again (it skips what is done) or see docs/LOCAL_AI.md → "Keep the settings".
  Back to mock: scripts/use-local-ai.sh --off · back to your old .env: scripts/use-local-ai.sh --restore
NEXT
if [ "$DRY_RUN" = 1 ]; then
  if [ "$GUARD_FAILED" != 0 ]; then
    die "$GUARD_FAILED" "dry run finished: a real run would stop at the guard marked WOULD STOP HERE above."
  fi
  say "dry run finished: nothing was changed."
fi
