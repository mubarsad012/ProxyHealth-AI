# Test with your own papers for free: local AI

_Owner: SETUP-LOCAL-AI (Phase 3). Written 2026-10-01. Source of every fact here: [`docs/research/free-ai-providers.md`](research/free-ai-providers.md) (§ numbers below point into it). Numbers marked [E] are estimates from that document, not measurements on this Mac._

**In one paragraph.** You have no budget, the Gemini free tier must never receive a real paper (D-01), and the paid tier needs a $5 prepay. So: run an open AI model, **Qwen3.5-4B**, on this Mac with **Ollama**. The API then sends your paper to `127.0.0.1`, not to an AI company. These commands set it up; each script can show its plan first (`--dry-run`):

```sh
make local-ai-setup ARGS=--dry-run   # read the plan: nothing is downloaded or changed
make local-ai-setup                  # asks y/N before Ollama (~200 MB), then before the model (3.4 GB)
scripts/use-local-ai.sh              # writes apps/api/.env for the local model (backs up yours first)
make local-ai-check                  # a SAMPLE paper through the real pipeline with the local model
make dev                             # the app at http://localhost:8081, reading with Qwen on this Mac
```

Nobody installs Ollama or a model for you. Agents and CI never run these scripts; `make dev`, `make test`, `make smoke` and `make ci` never call them.

---

## 1. Why local

| | Gemini free tier (`unpaid`) | Gemini paid tier (`paid`) | Local Qwen (`local`) |
|---|---|---|---|
| Real papers | **No.** Google may train on them and people may read them; its terms say not to send personal information (§1.3, S80) | Yes | Yes, on this Mac, in development and staging |
| Cost | $0 | $5 prepay minimum (§1.4) | $0: Apache-2.0 weights (§1.3) |
| Account, quota | Google account, AI Studio limits | Billing account | None; the only cost is time on this Mac |
| Who sees the paper | Google | Google (short abuse log) | No AI company. Ollama says: "We don't see your prompts or data when you run locally" (§1.1, S4) |

- **What this tier is for:** a privacy-safe test of the whole pipeline on real layouts. It is not a quality benchmark, and it is not for other people's papers in production (production stays on the Gemini paid tier, D-01).
- **Server rules that keep the consent copy true** (research §4.2, §5.2): tier `local` boots only when `OPENAI_COMPAT_BASE_URL` is a loopback address (`127.0.0.0/8`, `::1`, `localhost`), and `ENV=production` refuses it. The consent copy for this tier names the model (`OPENAI_COMPAT_MODEL_LABEL`, "Qwen") and says it runs on our server (research §5.3).
- **Whose papers:** only your own, or papers from someone who said yes. That holds even locally (§1.3).

## 2. The disk math

This Mac: MacBook Air M4, 16 GB memory, about **8.5 GiB free** (`df -h /System/Volumes/Data` on 2026-10-01; it moves, so the script measures it again every time).

| Step | Disk used | Free afterwards (from 8.5 GiB) |
|---|---|---|
| Download `Ollama.dmg` | +0.2 GB (deleted after the copy) | about 8.3 |
| Copy `Ollama.app` to `~/Applications` | +0.2–0.5 GB [E] | about 8.0–8.3 |
| `ollama pull qwen3.5:4b` | +3.4 GB | **about 4.6–4.9** |
| (instead) `ollama pull qwen3.5:9b` | +6.6 GB | about 1.4–1.7: **below the safety margin** |

- **What the script demands before any download:** Ollama 0.7 (dmg + app, counted high) + the model + **2.5 GiB headroom** for macOS swap and updates (§3.1 asks for 2–3 GB). For `qwen3.5:4b` on a fresh Mac that is **6.6 GiB**; with Ollama already installed, 5.9 GiB. For `qwen3.5:9b` it is 9.8 GiB, so free about 1.3 GiB more first. Below the budget the script stops with exit code 2 and downloads nothing.
- **One model at a time.** To try the 9B: `ollama rm qwen3.5:4b && scripts/setup-local-ai.sh --model qwen3.5:9b`, then `scripts/use-local-ai.sh --force --model qwen3.5:9b`. Never keep both (3.4 + 6.6 GB is more than the free disk).
- **Tags the scripts refuse** (§1.5, §3.1): any `:cloud` or `-cloud` tag (it sends prompts to Ollama's servers); a bare name or `:latest` (`qwen3.5:latest` is the 9B); the bare `qwen3-vl:8b` / `qwen3-vl:latest` and any `-thinking` tag (the slow thinking build; use `qwen3-vl:8b-instruct`); `-mlx`, `q8_0`, `bf16`, `fp16` (too big).
- **Memory:** the 4B uses about 5–6 GB of the 16 GB while it reads [E]. Close heavy apps during a test.
- **Where models live:** `~/.ollama/models`. Check with `ollama list` and `du -sh ~/.ollama`. `OLLAMA_MODELS` can point at an external drive (§3.1); the script measures the disk that holds it.

## 3. The exact steps

### 3.1 Install Ollama and the model: `make local-ai-setup`

Same as `scripts/setup-local-ai.sh`. Pass flags with `ARGS`, for example `make local-ai-setup ARGS="--model qwen3.5:9b --context 32768"`.

| Step | What happens | Changes |
|---|---|---|
| 0. Preflight | macOS 14 or newer on Apple silicon (arm64); not `sudo`; not CI; the model tag is allowed | nothing |
| 1. Disk budget | measures free disk **before any download** and stops below the budget in §2 | nothing |
| 2. Ollama | asks y/N, then `curl` from the official `https://ollama.com/download/Ollama.dmg` (HTTPS only, redirects too), checks the size, mounts it read-only with `hdiutil`, checks the code signature (`codesign --verify --deep --strict`), copies `Ollama.app` to `~/Applications` with `ditto`, detaches and deletes the dmg | `~/Applications/Ollama.app` |
| 3. Server | starts `ollama serve` bound to `127.0.0.1:11434` with `OLLAMA_CONTEXT_LENGTH=16384`, flash attention, a `q8_0` KV cache and a 10-minute keep-alive (§3.3), with debug logging off | a background process |
| 4. Model | prints the size and the free disk after it, asks y/N, then `ollama pull qwen3.5:4b` | `~/.ollama/models` (+3.4 GB) |
| 5. Smoke test A | sends the **synthetic** USCIS receipt fixture (`apps/api/data/fixtures/uscis_i797c_receipt_i765/page-1.png`) to `/v1/chat/completions` as a base64 image with a JSON schema and thinking off (§3.6). It passes when the JSON names U.S. Citizenship and Immigration Services and both printed dates, `08/17/2026` and `08/24/2026`. Then `ollama ps` shows CONTEXT and PROCESSOR | nothing (the image is sent from memory) |

- **Each step is skipped when it is already done**, so running the script again is safe. That includes after a reboot: it only starts the server and re-runs the smoke test.
- **Flags:** `--dry-run` (print every step, change nothing), `--yes` (skip the y/N prompts), `--model <tag>`, `--model-gb <size>` (for a tag that is not in the script's size table), `--context <tokens>` (8192–65536; 32768 for multi-page tests), `--smoke-only`, `--skip-smoke`, `--self-test` (checks the script's own guards, offline).
- **No admin password.** The script uses the `ollama` program inside the app, so it needs no `/usr/local/bin` link. If you open `Ollama.app` yourself later, it may offer to create that link and ask for your password. That is optional; type it yourself if you want it.
- **Write down** the smoke test's wall time and token counts. They replace the [E] speed estimates (§3.7).

**Keep the settings.** The server the script starts stops when you log out or restart. To bring it back, run `scripts/setup-local-ai.sh --skip-smoke`. If you would rather run the menu-bar app, give it the same settings first (§3.3), then quit and reopen Ollama:

```sh
launchctl setenv OLLAMA_CONTEXT_LENGTH 16384   # 32768 for multi-page tests
launchctl setenv OLLAMA_FLASH_ATTENTION 1
launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0
launchctl setenv OLLAMA_KEEP_ALIVE 10m
```

These values are lost at reboot too. The app's Settings slider can set the context length instead. Leave `OLLAMA_HOST` alone: the default binds `127.0.0.1` only, and the phone talks to the ProxyHealth API, never to Ollama.

### 3.2 Point the API at it: `scripts/use-local-ai.sh`

It writes `apps/api/.env` from the preset [`apps/api/.env.local-ai.example`](../apps/api/.env.local-ai.example):

| Variable | Value | Why |
|---|---|---|
| `ENV` | `development` | `local` is refused in production |
| `AI_PROVIDER` | `openai_compat` | the OpenAI-compatible provider (§4) |
| `OPENAI_COMPAT_BASE_URL` | `http://127.0.0.1:11434/v1` | Ollama on loopback; the boot rule checks it |
| `OPENAI_COMPAT_API_KEY` | `ollama` | Ollama needs some token on `/v1` and ignores it; not a secret |
| `OPENAI_COMPAT_MODEL_PRO` / `_FAST` | `qwen3.5:4b` | one model for both tiers (two would double RAM and disk) |
| `OPENAI_COMPAT_DATA_TIER` | `local` | real papers allowed (dev/staging), consent copy names the model |
| `OPENAI_COMPAT_MODEL_LABEL` | `Qwen` | shown as `{model}` in the consent copy |
| `OPENAI_COMPAT_JSON_MODE` | `json_schema` | Ollama `/v1` takes `response_format` json_schema (§4.4) |
| `OPENAI_COMPAT_REASONING` | `none` | sends `reasoning_effort: "none"`: Qwen3.5 thinks by default, which multiplies latency (§4.5) |
| `OPENAI_COMPAT_TIMEOUT_S` / `FAILOVER_DEADLINE_S` | `300` / `310` | a local call can take minutes; the deadline must be at least timeout + 10 (§4.2 rule 5) |

- **Before writing,** it asks the API's own `Settings` (boot rules included) whether the server would start with this file. If not, it writes nothing (`--no-check` skips the check). It also warns when one of these variables is set in your shell, because a real environment variable wins over `.env`.
- **It never overwrites a different `.env` without `--force`.** With `--force` it first moves yours to `apps/api/.env.bak-YYYYmmdd-HHMMSS` (mode 600, git-ignored). A `.env` that equals the preset is never backed up.
- **Other flags:** `--dry-run`, `--model <tag>` (same tag rules as the setup script) with `--label <Name>` for a model family it does not know, `--restore`, `--off`, `--self-test`.

### 3.3 Check the pipeline: `make local-ai-check`

This runs `apps/api/scripts/provider_check.py` from `apps/api`. That script ships with the `openai_compat` provider; see its `--help`. It sends a **sample** paper (by default `medicaid_address_confirmation`) through the real analysis pipeline with whatever provider `apps/api/.env` configures. It prints whether the output fit the schema, which facts the server verified or rejected, the time taken, and which structured-output mode worked. Pass flags with `ARGS`, for example `make local-ai-check ARGS=--help`.

### 3.4 Use the app: `make dev`

The API reads `apps/api/.env`, so `GET /v1/config` reports `data_use_tier: "local"`, the consent screen shows the local-tier badge and the "I understand, continue" button, and the app accepts your own photos. Start with a sample paper, then one of yours.

## 4. Testing your OWN paper safely

**Where the paper goes.** Run the API, Ollama and the browser on this Mac (`make dev`, then `http://localhost:8081`). The photo goes from the browser to the API on `127.0.0.1:8000`, then to Ollama on `127.0.0.1:11434`. It stays on this Mac. No AI company receives it.

**What is kept.**

- **The API keeps nothing.** It never writes a paper, a transcript or model output to disk or logs (ARCHITECTURE §7). That holds for this provider too: it does not log prompts, images or replies.
- **Ollama:** the setup script starts it with debug logging off. Ollama does not say whether it ever writes prompts to disk (§4.9, [U]). Check it once yourself before relying on it:

  ```sh
  MARK="phmarker$(date +%s)"
  curl -s http://127.0.0.1:11434/v1/chat/completions -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer ollama' \
    -d "{\"model\":\"qwen3.5:4b\",\"reasoning_effort\":\"none\",\"max_tokens\":20,\"messages\":[{\"role\":\"user\",\"content\":\"Repeat this word: $MARK\"}]}" >/dev/null
  grep -rl "$MARK" ~/.ollama && echo "FOUND: Ollama wrote the prompt to disk" || echo "not found under ~/.ollama"
  ```

- **The app keeps a copy only if you press Save.** On web, a saved paper stays only while the tab is open, unless you turned on "Keep on this device" in Settings (then it stays in this browser's storage on this Mac, not encrypted by the app).

**How to test a paper of yours.**

1. Run smoke test A and `make local-ai-check` first. Both use made-up sample papers.
2. In the app, use **Hide parts** to black out what the test does not need, such as A-numbers or passport numbers (§1.5: identity numbers are sensitive anywhere). The server burns those boxes black in memory before the model reads the page (`analysis/redaction.py`). Hiding a receipt number means the app cannot track that case.
3. Read one paper. Check every answer against the paper. Write down the time and anything the model missed.
4. To skip the app, `provider_check.py` can read one of your own photos from the terminal. It allows that only on the `local` tier (or the development-only `attested` tier, §8) and writes nothing (see `make local-ai-check ARGS=--help`).

**Things that would break "it stays on this Mac".**

- **A phone over a tunnel.** On the same Wi-Fi (Expo Go or a development build, API bound to the LAN as in the README), the photo crosses your local network to this Mac over plain HTTP, so use a network you trust (home Wi-Fi, not public Wi-Fi). With `npx expo start --tunnel` or any tunnel service, a tunnel company carries the traffic. Do not use a tunnel with real papers.
- **Turning a real paper into a fixture.** Never copy a real paper into `apps/api/data/fixtures/`, and keep `RECORD_FIXTURES` off.
- **Changing the base URL.** Pointing `OPENAI_COMPAT_BASE_URL` anywhere but loopback makes the server refuse the `local` tier at boot. That refusal is on purpose.
- **Ollama cloud tags.** `:cloud` and `-cloud` models run on Ollama's servers. The scripts refuse them; do not pull them by hand either.

Never call this "private AI" or say "nothing leaves your device" in the app: a phone does send the photo to our server (§5.3).

## 5. Speed

- **Expect about 1–4 minutes per paper** with the 4B model on this fanless Air [E, §1.3]. The first call after a pause also loads the model into memory (the keep-alive keeps it loaded for 10 minutes).
- **The app waits longer on this tier.** The app normally gives up after 120 s (analyze), 60 s (troubleshoot, language packs) and 30 s (everything else, chat included). With `AI_PROVIDER=openai_compat`, the API sends longer limits in `GET /v1/config` (`client_timeouts`), worked out from `FAILOVER_DEADLINE_S` and `OPENAI_COMPAT_TIMEOUT_S`, and the app reads them from there.
- **Make it faster:** one page at a time; close heavy apps; keep the context at 16384 (32768 costs more memory); keep thinking off (`OPENAI_COMPAT_REASONING=none`). `OPENAI_COMPAT_MAX_OUTPUT_TOKENS` (default 6144) caps how long a reply can get.
- **Only one request runs at a time** on loopback (`OPENAI_COMPAT_CONCURRENCY` defaults to 1). Two parallel reads would fight over 16 GB of memory.

## 6. Quality: what to expect from a small model

- **Weaker than `gemini-3.8-flash`** at reasoning and at writing in less common languages (§1.3). It may miss a date or misread a word. The server's own rules still apply: quotes are checked against the page, dates are computed only by the deadline rules, urgency only by the urgency rules, and contacts come only from the paper or the resource database.
- **Structured output:** `json_schema` first. If the reply does not fit the schema, the provider asks once for a corrected reply, then falls back to the two-call path (§4.4).
- **Languages:** Qwen3.5 claims 201 languages and dialects, but its card gives no per-language list. **Pashto is not on Qwen3's official 119-language list; whether Qwen3.5 handles it is unverified** (§1.3). Have a native speaker check Dari, Pashto and Haitian Creole output.
- **If quality is the problem**, try `qwen3.5:9b` (better on every published score, 6.6 GB; free disk first) or `qwen3-vl:8b-instruct` (the best published small-model reading scores, weaker at writing other languages, 6.1 GB). One model at a time.

## 7. Switching back

| To | Run | Then |
|---|---|---|
| Mock (zero keys, sample papers) | `scripts/use-local-ai.sh --off` (or delete `apps/api/.env`) | restart `make dev` |
| Your previous `.env` (for example billed Gemini keys) | `scripts/use-local-ai.sh --restore` (the newest `apps/api/.env.bak-*`) | restart `make dev` |
| Gemini paid tier from scratch | start from `apps/api/.env.example` and the README section "Adding Gemini keys" | restart `make dev` |

- **Stop Ollama:** `pkill -f 'ollama serve'`, or quit it from the menu bar if you run the app.
- **Get the disk back:** `ollama rm qwen3.5:4b` returns 3.4 GB. To remove Ollama completely, quit it, then move `~/Applications/Ollama.app` and `~/.ollama` (models and Ollama's own key) to the Trash yourself.

## 8. Hosted options: synthetic samples, or your own papers with care

The same `openai_compat` provider can call hosted OpenAI-compatible endpoints. **By default any hosted endpoint runs on the `unpaid` tier: sample papers only, and real papers get a 403**, exactly like the Gemini free tier. For your own papers there is the **`attested` tier**, which works **in `ENV=development` only**. It needs `OPENAI_COMPAT_DATA_TIER=attested`, `OPENAI_COMPAT_VENDOR_NAME`, `OPENAI_COMPAT_NO_TRAINING_ATTESTED=true` and a host that is not on the server's denylist (see `apps/api/.env.example`). The attestation is your own statement that the vendor's API terms say "no training on API content", like `billing` in `GEMINI_KEYS`. If it is false, every `attested` consent sentence is false; treat that as an incident (§5.2).

Only these four are worth it for your own papers (§1.3, §1.5, §2). Base URLs and model ids: check each vendor's page before use. Free limits change.

| Vendor | Model (§4.5) | Free limit | Data terms (§1.5) | Settings to change |
|---|---|---|---|---|
| **Alibaba Cloud Model Studio International** (Singapore) | `qwen3-vl-plus` (PRO), `qwen3-vl-flash` or `qwen3.8-flash` (FAST) | about 1M tokens per model for 90 days from activation (about 125–165 calls per model [E]) | contract: no training on your content unless you consent; how long it keeps call data is not stated. **PRC-headquartered parent**: content may be processed wherever Alibaba or its affiliates have facilities, and the terms say output is not a basis for medical or legal decisions | `OPENAI_COMPAT_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1`; `OPENAI_COMPAT_JSON_MODE=json_object` (JSON schema falls back to JSON mode with images). Turn on **Free Quota Only** first (off by default), and activate only when ready (the 90 days do not pause) |
| **Groq** (US) | `qwen/qwen3.8-27b` | 1,000 requests and 200K tokens per day, about 28 calls a day [E]; at most 3 images per request | contract: no training. Logs up to 30 days unless you turn on Zero Data Retention: **turn it on**. Listed as a Preview model ("evaluation purposes only") | `OPENAI_COMPAT_MAX_IMAGES=3`; `OPENAI_COMPAT_JSON_MODE=json_object` (images plus strict schema: not stated) |
| **Cerebras** free trial (US) | `qwen-3.8-27b` | $5 credit for 30 days; a payment method is required, but no automatic paid enrolment; 2 images per request | does not retain inputs or outputs; training is not stated | `OPENAI_COMPAT_MAX_IMAGES=2` |
| **Cloudflare Workers AI** | `@cf/qwen/qwen3.8-27b` | 10,000 Neurons a day, about 13 calls a day [E] | no training on your content without consent | JSON-schema output is not guaranteed for this model: if calls fail with "JSON Mode couldn't be met", set `OPENAI_COMPAT_JSON_MODE=prompt` |

- **Synthetic samples only:** the Gemini free tier, Vertex Express and NVIDIA build (their terms train on content or ban personal data). Mistral free mode and OpenRouter `:free` stay synthetic-only until you change settings: opt out of training on Mistral; on OpenRouter, turn off training for free models and pin an endpoint whose no-training policy you have confirmed.
- **Chinese-hosted services: avoid for real papers.** Zhipu bigmodel.cn (stored in mainland China; may train on anonymised data), DeepSeek (stored in the PRC; trains unless you opt out), Moonshot Kimi, MiniMax and StepFun (may use or license your content), SiliconFlow (no commercial use) and Baidu Qianfan (PRC ID verification). Z.ai's terms forbid medical or legal-substitute use and HIPAA data. The server refuses `attested` for several of these hosts.
- **The DOJ data-security rule** (28 CFR Part 202) restricts sending Americans' bulk health data to companies owned by or based in a "country of concern", China included. Your own test papers are far below every threshold. A production plan on any PRC-parented vendor would need counsel; none of these free options is for production (§1.4, §1.5).

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Setup stops at step 1 (exit code 2) | not enough free disk for the budget in §2 | free the amount it prints, or point `OLLAMA_MODELS` at an external drive; nothing was downloaded |
| `model refused: …` | a tag the scripts block (§2) | use a sized tag such as `qwen3.5:4b` or `qwen3-vl:8b-instruct` |
| The API answers 503 "Local AI server is not running." | Ollama is not running (after a reboot or logout) | `scripts/setup-local-ai.sh --skip-smoke` |
| The API will not boot: tier `local` needs a loopback base URL | `OPENAI_COMPAT_BASE_URL` points at another host | put back `http://127.0.0.1:11434/v1`, or use the `unpaid` / `attested` tiers for hosted endpoints (§8) |
| Results look cut off, or the model ignores half the page | context too small (Ollama's default is 4096 tokens on this Mac) | `ollama ps` shows CONTEXT. Stop the server (`pkill -f 'ollama serve'`), then run the script again (add `--context 32768` for multi-page tests) |
| Very slow, or the Mac swaps | memory pressure | close heavy apps; one page at a time; keep the context at 16384 |
| Smoke test A fails once | a small model can miss | `scripts/setup-local-ai.sh --smoke-only`; if it keeps failing, try `qwen3.5:9b` (free disk first) |
| "Gatekeeper did not confirm notarization" | the signature check passed but `spctl` did not confirm | open `~/Applications/Ollama.app` once from the Finder and read macOS's message before going on |
| Port 11434 is busy but does not answer as Ollama | another program uses the port | stop it; the script will not start a second server |
| The app gives up before the answer arrives | the API on this tier sends longer limits in `GET /v1/config` (`client_timeouts`) | check that `curl -s http://127.0.0.1:8000/v1/config` shows `data_use_tier: "local"` and the larger limits; restart `make dev` after changing `.env` |
