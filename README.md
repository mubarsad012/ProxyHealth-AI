# ProxyHealth AI — Your paper, explained.

One codebase for iOS, Android and the web. Photograph a letter, bill, notice or form; the app reads it, translates it, explains it in three calm cards anchored to the exact words on the page, and points the reader to help a person verified.

> **Information, not advice.** ProxyHealth AI explains what a paper says. It does not give legal or medical advice, decide eligibility, or fill in forms. Only a licensed professional — a lawyer (or, for an immigration case, a DOJ-accredited representative), a doctor, nurse or pharmacist, a housing counselor, or the office that sent the paper — can tell someone what it means for them.

| | |
|---|---|
| **Status (2026-10-04)** | Phase 1 built and merged (`85e1e68`): API core, Gemini provider with key failover, the full analysis/safety pipeline, resources, fixtures and the mobile app (web walk-through verified end to end in Dari with zero keys). Phase 2A (dev tooling, CI, store docs, artwork; `3eccd27`), 2B (audit and hardening; `95e620f`) and 2C (leftovers plus S5/S11/S16 should-haves; `c948de8`) merged. Phase 3 (branch `phase3-wip`) adds an OpenAI-compatible provider and the `local`/`attested` test tiers so you can [test with your own papers for free on a local AI](#test-with-your-own-papers-for-free-local-ai) (D-32). iOS store submission stays blocked on the iCloud-backup gate (COMPLIANCE_PRIVACY §10.2); Android first. The API test suite passes (`make test`; the live tests skip without keys); ruff and strict mypy are clean; mobile `tsc`, `jest`, `expo lint`, web export and `expo config --type prebuild` are green. |
| **Try it** | `make dev`, then open <http://localhost:8081>. Zero API keys: `AI_PROVIDER=mock` serves 17 synthetic sample papers and 1 portal screenshot end to end. |
| **Models** | `MODEL_PRO=gemini-3.8-flash` (document analysis, screenshot help) · `MODEL_FAST=gemini-3.5-flash-lite` (language packs, chat, tagging, rewrites). Env-configurable; `gemini-1.5`/`2.0`/`2.5` and `-latest` IDs are refused at boot. |
| **Real papers** | Sent to Gemini only on the **paid** data-use tier (every key from a distinct Google Cloud project with billing attached). Test builds can instead read them with an open model on your own machine (**local** tier; loopback only, never in production) or, in development only, with a named vendor whose terms say no training (**attested**). On unpaid or mixed key pools the server answers `403 unpaid_tier_real_documents_disabled` and serves sample papers only; typed text (chat questions, a troubleshoot goal) is refused there too, even about a sample, so `features.chat` is off and the app hides the chat box. |
| **Stores** | Not submitted. Android development build first, iOS after an organization Apple account; see [Store roadmap](#store-roadmap) and [`docs/STORE_LISTING.md`](docs/STORE_LISTING.md). |

## Contents

1. [What it is](#what-it-is)
2. [Features](#features)
3. [What it deliberately does not do](#what-it-deliberately-does-not-do)
4. [Architecture](#architecture)
5. [Quickstart (zero keys)](#quickstart-zero-keys)
6. [Adding Gemini keys — the paid-tier requirement](#adding-gemini-keys--the-paid-tier-requirement)
7. [Test with your own papers for free (local AI)](#test-with-your-own-papers-for-free-local-ai)
8. [Environment variables](#environment-variables)
9. [Scripts and commands](#scripts-and-commands)
10. [Repository layout](#repository-layout)
11. [API at a glance](#api-at-a-glance)
12. [Docs index](#docs-index)
13. [Store roadmap](#store-roadmap)
14. [Contributing and testing](#contributing-and-testing)
15. [Open questions and license](#open-questions-and-license)

---

## What it is

ProxyHealth AI is a *paper decoder with a caseworker's manners*. Immigrants and other underserved adults receive hospital bills, USCIS and immigration-court notices, leases and eviction papers, Medicaid and SNAP letters, school forms and IRS notices — often in a language they do not read, with the one date that matters buried on page three. You photograph the paper (or pick a photo or a PDF) and get three cards in your own language: **What is this?**, **What is it asking for?** and **Your step-by-step plan**. Every date, amount, requested document and contact is shown next to the exact words on the page it came from, with a confidence chip; anything the AI saw but could not confirm on the page is listed separately and never drives urgency or reminders.

It is information, not advice, and that is enforced in code rather than in a footer: the model never writes disclaimers, never sets urgency, never computes a date and never emits a phone number, URL or organization name. Boundary sentences are fixed copy chosen by document category (for legal papers: "This is general information about this type of paper, not legal advice about your case. Only a licensed lawyer can advise you. For an immigration case, a DOJ-accredited representative can too."). The app is for adults 18 and older (a Gemini terms requirement), never asks anyone's immigration status, and never stores a paper, image or transcript on the server. Rationale: [`docs/DECISIONS.md`](docs/DECISIONS.md) §0, §4, §5.

## Features

Decision numbers point into [`docs/DECISIONS.md`](docs/DECISIONS.md).

**Decode a paper**
- 1–12 photos or one PDF in; three cards, details with quotes, a glossary, red flags and questions to ask the sender out. The client compresses to 1600 px, JPEG 0.8, EXIF stripped. [D-06, D-21]
- **Every fact is a quotation**: `source_quote` + `span_ids` + `page` + `confidence` + `verified`, checked against the transcript; failures move to "I saw these but could not confirm them on the page". [D-09]
- Side-by-side original and translation with tappable highlights. [D-06]
- **Urgency computed in code** (`emergency` / `critical` / `high` / `medium` / `info`, with document-type floors), shown as icon + word + color with "Verify this date". [D-12]
- **Dates only from the paper** or from a printed relative phrase + a verified anchor + a cited rule (`GET /v1/rules`, 12 rules with sources); estimates are labelled. [D-11]
- Fixed notices by document type (jury summons, I-765 receipt, pay-or-quit, asylum fee, address changes). [D-20]
- **Scam checks** (gift cards, wires, payment apps, "pay to avoid arrest", notarios, look-alike domains) with a fixed warning card and reporting resources first. [D-13]
- **Emergency card** from fixed copy, keyword-triggered in every bundled language. [D-14]
- Prompt-injection detection with a masked re-run; "Hide parts" masking (burned on the device on web, on the server in memory on native). [D-15, D-19]

**Act on it**
- **"Show the clerk"** card in English for a counter, with a 1.5 s long-press exit. [D-18]
- **Get help nearby**: deterministic matching over a vetted database (101 entries, national plus Northern Virginia, each with "Verified on"), a prepare-these-documents checklist per result, national fallbacks. [D-10, D-24]
- **Screenshot help** ("Stuck on a website?" / "Is this a scam?") naming buttons exactly as written, with a credential/payment guard. [D-13]
- **Grounded chat** that answers only from the paper and refuses eligibility, filing, outcome, medical-interpretation and drafting questions with a referral. [D-17]
- **Reminders** 7/3/1 days before verified dates (native notifications; `.ics` on web), with generic text by default. [D-22]
- **Quick sheet**: text-only, print or share; server-rendered PDF on web with embedded Noto fonts and Arabic-script shaping.

**Keep it private**
- Family vault on the device only, opt-in after each scan; one-tap "Delete everything". Web keeps papers for the tab session unless the user opts into browser storage (labelled "not encrypted by the app"). [D-22, D-23]
- Nothing on the server: request bodies live in memory; logs are an allow-list of content-free fields; feedback is counts only. [D-08, D-31]
- Consent that is literally true per tier (paid / unpaid / demo / unknown, plus the `local` and `attested` test-build tiers that name the model or vendor), CI-tested against an approved list. [D-02, D-32]

**Speak the reader's language**
- Bundled packs `en`, `es`, `prs` (Dari), `ar`, `ps` (Pashto); any typed language gets a generated pack while the screen says *"Adapting system environment to your language..."* (keys required; mock mode shows a pseudo-localized pack). Computer-translated packs are labelled. [D-25]
- Right-to-left layouts, Bidi-isolated numbers and names, Noto fonts for nine scripts, read-aloud on every paragraph with honest voice fallbacks. [D-26]

**Everywhere, accessibly**
- One Expo Router codebase: root Stack + JS Tabs (Home · My papers · Get help · Settings); every device feature has a web path. [D-27]
- "Big Calm" design system: 18 pt base text, 56/72 pt controls, 7:1 body contrast, high-contrast palette, 200 % text, WCAG 2.2 AA floor. [D-28]

## What it deliberately does not do

| Never | Because |
|---|---|
| Diagnose, interpret a lab value "for you", or give medical advice | Gemini terms; FDA display exclusion; Apple 1.4.1. Fixed medical disclaimer instead. |
| Say whether you qualify, should file/appeal/pay/sign, or what will happen | Unauthorized practice of law is state law; Google's Prohibited Use Policy. Phrasing linter, refusal kinds, fixed referrals. |
| Draft, fill or format an official form or letter | Play policy on AI-generated official documents; notario-style misuse. |
| Invent a phone number, URL, address or organization | Highest-severity failure; contacts come only from the paper or the vetted DB. |
| Compute a deadline from memory | Only printed dates, or a cited rule with a verified anchor. |
| Send a real paper to an unpaid Gemini key | Unpaid-tier content may be used to improve Google products with human review. Server-side 403. |
| Keep a paper on the server, or ask immigration status | The trust boundary is the device. |
| Claim human review, app-layer encryption or backup exclusion before it is verified | FTC Act §5 literal truth (`test_privacy_claims.py`). |

---

## Architecture

```
┌──────────────── one Expo codebase · iOS / Android / web  (apps/mobile) ────────────────┐
│ Expo Router: root Stack + JS Tabs (Home · My papers · Get help · Settings)             │
│ "Big Calm" tokens · language packs (RTL, Noto fonts, Bidi) · read-aloud (expo-speech)  │
│ vault: expo-sqlite + files (native) | tab memory / opt-in IndexedDB (web)              │
│ reminders: notifications (native) | .ics (web) · quick sheet: print (native) | PDF     │
│ typed API client (schema.d.ts generated from openapi.json) · consent record · samples  │
└───────────────┬────────────────────────────────────────────────────────────────────────┘
                │ HTTPS · JSON with base64 pages · X-Consent-Version · X-Install-Id
┌───────────────▼──────────── apps/api · FastAPI · Python 3.13 · in memory only ─────────┐
│ request id → content-free log → body limit → CORS → tier headers → consent (428)       │
│   → tier gate (403) → rate limit (429)                                                  │
│ routers → pipelines → AIProvider ─┬─ GeminiProvider (failover ⇄ key pool, per slot)    │
│                                   ├─ OpenAICompatProvider (test builds · local AI)     │
│                                   └─ MockProvider (sample papers · dHash · latency)    │
│ safety pipeline: uploads → redaction → model → verify quotes → contacts filter →       │
│   deadline rules → urgency → scam → emergency → phrasing lint → injection re-run →     │
│   clerk card → fixed notices → resources → disclaimers → AnalysisResult                │
│ resources YAML matcher · reportlab quick sheet · language-pack cache · feedback counts │
│ var/ (git-ignored): keypool.json · langpacks/ · feedback_counts.sqlite — no user data  │
└───────────────┬────────────────────────────────────────────────────────────────────────┘
                │ google-genai · generate_content · response_schema · no Files API
       Gemini API — MODEL_PRO / MODEL_FAST · one key per DISTINCT billed Cloud project
       test builds (D-32): Ollama / LM Studio on 127.0.0.1, or a hosted OpenAI-compatible API
```

**Trust boundary = the device.** Pydantic models in `apps/api/proxyhealth_api/contracts/` are the single source of truth; `apps/api/openapi.json` is committed and snapshot-tested; `apps/mobile/src/api/schema.d.ts` is generated from it with `openapi-typescript`. Full trees and module internals: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Quickstart (zero keys)

Prerequisites on this Mac (already installed — see [`CLAUDE.md`](CLAUDE.md)): Node 24 at `~/.local/node/bin`, the API virtualenv at `apps/api/.venv`, and `apps/mobile/node_modules`. No Xcode, so no iOS simulator: test on web or on a phone with a development build.

```sh
make dev                     # API (mock) on :8000 + Expo web on :8081; Ctrl-C stops both
open http://localhost:8081   # or let Expo open the browser for you
```

`make dev` runs `scripts/dev.sh`: it starts `uvicorn proxyhealth_api.main:app --reload` from `apps/api` with `CORS_ORIGINS=http://localhost:8081,http://127.0.0.1:8081`, waits for `/health`, then starts `npx expo start --web` with `EXPO_PUBLIC_API_URL=http://127.0.0.1:8000`. With no `apps/api/.env` the API runs `AI_PROVIDER=mock` (`data_use_tier: demo`). Options: `API_PORT`, `WEB_PORT`, `DEV_OPEN_BROWSER=0`.

The zero-key walk-through: pick **Dari** (the layout flips right to left) → the consent screen shows **Sample mode** ("Sample mode. No AI service is contacted. Your photo is only compared with our sample papers and is not kept.") → **Try a sample paper first** → the Medicaid letter → urgency banner, three cards with quotes, a speaker on every paragraph → **Show the clerk**, **Get help nearby**, **Save**. The full three-minute script is [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md).

Check the API alone:

```sh
curl -s http://127.0.0.1:8000/health          # {"status":"ok","provider":"mock",...,"data_use_tier":"demo",...}
curl -s http://127.0.0.1:8000/v1/demo/fixtures | head -c 300
make smoke                                     # boots its own mock API on a free port and exercises every endpoint
```

**Phone**: Expo Go is for smoke checks only (permission strings, notifications and the RTL restart need a development build). Bind the API to the LAN (`cd apps/api && .venv/bin/uvicorn proxyhealth_api.main:app --host 0.0.0.0 --port 8000`) and start Metro with `EXPO_PUBLIC_API_URL=http://<mac-lan-ip>:8000 npx expo start`. For a real device test, build the Android development client ([`docs/RUNBOOK.md`](docs/RUNBOOK.md) §7.1).

---

## Adding Gemini keys — the paid-tier requirement

Under the Gemini API Additional Terms, content sent through **unpaid** quota may be used to improve Google's products and read by human reviewers, and Google asks developers not to send sensitive or personal information there. A key is **paid** only when its Google Cloud project has an active Cloud Billing account attached. Even on the paid tier Google keeps a short abuse-detection log "for a limited period of time". Rate limits are per project, not per key. Sources: [`docs/research/gemini.md`](docs/research/gemini.md) §1, §3; [`docs/research/compliance.md`](docs/research/compliance.md) §4.

ProxyHealth AI turns this into an operator attestation per key and enforces it on the server (D-01):

```sh
# apps/api/.env  (git-ignored; start from apps/api/.env.example)
AI_PROVIDER=gemini
GEMINI_KEYS='[{"key":"AIza...","project":"proxyhealth-prod-a","billing":true},{"key":"AIza...","project":"proxyhealth-prod-b","billing":true}]'
```

- `project` labels must be distinct (duplicates abort boot). `"billing": true` is your statement that a Cloud Billing account is attached — the SDK cannot detect it. File the evidence ([`docs/RUNBOOK.md`](docs/RUNBOOK.md) §1).
- Resulting tier (`GET /v1/config.data_use_tier`, the `X-Data-Use-Tier` header and the consent badge): `paid` (every slot billed → real papers allowed) · `unpaid` / `mixed` (any slot unbilled → real papers **blocked** with 403, sample papers only) · `demo` (mock) · `none` (gemini with no keys; development only).
- `ENV=production` refuses unbilled slots unless `ALLOW_UNPAID_KEYS=1` (sample-only deployments) and always refuses `ALLOW_UNPAID_REAL_DOCUMENTS`. Mock is never a silent fallback: quota exhaustion returns `429 quota_exhausted`.
- If any users are in the EEA, Switzerland or the UK, every key must be billed (D-03). v1 is US-only.
- Inspect the key pool (content-free): set `ADMIN_TOKEN` and `curl -H 'X-Admin-Token: …' http://127.0.0.1:8000/v1/admin/keys`.
- Store privacy answers are defensible only on the `paid` tier ([`docs/COMPLIANCE_PRIVACY.md`](docs/COMPLIANCE_PRIVACY.md) §3).

---

## Test with your own papers for free (local AI)

No budget, but you want to see how the app reads a real letter? Never send it through a free Gemini key: Google may train on it and people may read it (D-01). Instead, run an open vision model, **Qwen3.5-4B**, on this Mac with **Ollama**. The API then sends the paper to `127.0.0.1`, not to an AI company. The full guide is [`docs/LOCAL_AI.md`](docs/LOCAL_AI.md) (disk math, safety checks, speed, quality, troubleshooting); the decision is D-32 and the research is [`docs/research/free-ai-providers.md`](docs/research/free-ai-providers.md).

```sh
make local-ai-setup ARGS=--dry-run   # read the plan: nothing is downloaded or changed
make local-ai-setup                  # asks y/N before Ollama (~200 MB), then before the model (3.4 GB)
scripts/use-local-ai.sh              # writes apps/api/.env for the local tier (backs up yours first)
make local-ai-check                  # a SAMPLE paper through the real pipeline with the local model
make dev                             # the app at http://localhost:8081, data use tier "local"
```

- **What changes.** `apps/api/.env` gets `AI_PROVIDER=openai_compat`, `OPENAI_COMPAT_BASE_URL=http://127.0.0.1:11434/v1`, `OPENAI_COMPAT_DATA_TIER=local` and `OPENAI_COMPAT_MODEL_LABEL=Qwen` (preset: `apps/api/.env.local-ai.example`). `GET /v1/config` then reports `data_use_tier: "local"`; the consent screen shows "Test build — AI on our server", names the model, and offers "I understand, continue".
- **What the server enforces.** `local` boots only when the model endpoint is a loopback address (`127.0.0.0/8`, `::1`, `localhost`) and never with an Ollama `:cloud` model; `ENV=production` refuses the provider entirely. Any hosted OpenAI-compatible endpoint runs on `unpaid` by default (sample papers only, real papers get a 403). The `attested` tier, for a vendor whose API terms you attest say "no training", boots only in `ENV=development` and refuses denylisted hosts.
- **Your part.** Use only your own papers, or papers from someone who said yes. Black out ID numbers with **Hide parts**. Run the Ollama disk check once (`docs/LOCAL_AI.md` §4) and note it in [`docs/RUNBOOK.md`](docs/RUNBOOK.md) §9. No tunnels (`expo start --tunnel`) with a real paper, and never copy one into `apps/api/data/fixtures/`.
- **Expect** about 1–4 minutes per paper on this fanless M4 Air (an estimate), so the API tells the app to wait longer (`client_timeouts` in `GET /v1/config`). A 4B model is weaker than `gemini-3.8-flash`: check every answer against the paper, and have a native speaker check Dari, Pashto and Haitian Creole output.
- **Nobody installs Ollama or a model for you.** Agents and CI never run these scripts; `make dev`, `make test`, `make smoke` and `make ci` never call them.
- **Switch back** with `scripts/use-local-ai.sh --off` (mock, zero keys) or `--restore` (your previous `.env`), then restart `make dev`.
- **Hosted second opinions** (Groq, Cloudflare Workers AI, Alibaba Model Studio International, …) use the same provider; which ones may see your own papers and which are synthetic-samples-only (Chinese-hosted services, with one documented Alibaba exception) is in `docs/LOCAL_AI.md` §8 and D-32.

---

## Environment variables

Parsed by pydantic-settings from `apps/api/.env` (then a `.env` in the working directory; real environment variables win). Unknown variables are a boot error; secrets never appear in `repr` or logs. Full meanings: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §6 and `apps/api/.env.example`.

### API (`apps/api/.env`)

| Variable | Default | Meaning |
|---|---|---|
| `ENV` | `development` | `development \| staging \| production`; production refuses unbilled slots (unless `ALLOW_UNPAID_KEYS=1`) and `ALLOW_UNPAID_REAL_DOCUMENTS`. |
| `AI_PROVIDER` | `mock` | `mock \| gemini \| openai_compat` (`gemini_interactions` is LATER and refused). `openai_compat` = test builds only, refused in production (D-32). |
| `GEMINI_KEYS` | `[]` | JSON list of `{"key","project","billing"}`; one key per **distinct** project; `billing` = your attestation. |
| `ALLOW_UNPAID_KEYS` | `0` | Lets production boot with unbilled slots (sample papers only). |
| `ALLOW_UNPAID_REAL_DOCUMENTS` | `false` | Dev-only bypass of the 403 gate for synthetic scans; boot error in production. |
| `MODEL_PRO` / `MODEL_FAST` | `gemini-3.8-flash` / `gemini-3.5-flash-lite` | Model IDs (1.5/2.0/2.5/`-latest` refused). |
| `MODEL_PRO_DEGRADED_THINKING` · `ALLOW_DEGRADED` | `medium` · `true` | Pro → fast degradation when every pro slot is cooling. |
| `ANALYSIS_MODE` | `auto` | `auto \| single \| two_call` (D-06). |
| `TRANSLATE_FULL_MAX_PAGES` | `4` | Full translation up to this many pages. |
| `RPD_SOFT_CAP_PRO` / `RPD_SOFT_CAP_FAST` | `0` | Per-slot daily soft caps (0 = off). |
| `UPSTREAM_TIMEOUT_S` / `FAILOVER_DEADLINE_S` | `90` / `100` | Per call / per request across slots. On `openai_compat` the deadline must be ≥ `OPENAI_COMPAT_TIMEOUT_S + 10` (raised automatically when unset). |
| `MAX_PAGES` · `MAX_PAGE_BYTES` · `MAX_PDF_BYTES` · `MAX_PDF_PAGES` · `MAX_REQUEST_BYTES` · `MAX_UPSTREAM_INLINE_BYTES` | `12` · 4 MiB · 12 MiB · `60` · 20 MiB · 18 MiB | Upload caps (D-21). |
| `MAX_CHAT_HISTORY` | `8` | Prior chat turns accepted. |
| `CORS_ORIGINS` | `http://localhost:8081` | Comma list; add the web host. `make dev` passes `http://localhost:8081,http://127.0.0.1:8081`. |
| `APP_TOKEN` · `ADMIN_TOKEN` | empty | Require `X-App-Token` · enable `/v1/admin/keys`. |
| `INSTALL_HASH_SECRET` | random per process | HMAC secret for install-id hashing (set it in production). |
| `RATE_LIMIT_ANALYZE_PER_HOUR` / `_PER_DAY` · `RATE_LIMIT_IP_PER_MINUTE` / `_PER_DAY` | `20` / `100` · `60` / `1000` | Soft limits per install (when `X-Install-Id` is sent) / per IP class (`/24`, `/48`; every model-calling request). 429 `details.bucket` says which. |
| `TRUSTED_PROXY_HOPS` | `0` (the Dockerfile sets `1`) | Proxies that append to `X-Forwarded-For`; Cloud Run 1, behind an external HTTPS load balancer 2 (DEPLOYMENT §1.2). |
| `CONSENT_VERSION` | `2026-10-04` | Bump when consent copy changes (clients re-consent). |
| `PRIVACY_POLICY_URL` | `https://proxyhealth.expo.app/privacy` | The public HTML policy (`apps/mobile/public/privacy/index.html`). |
| `VAR_DIR` · `LANGPACK_CACHE_TTL_DAYS` | `./var` · `180` | Runtime state (never user content) · pack cache age. |
| `MOCK_LATENCY_MIN_MS` / `_MAX_MS` · `MOCK_PHASH_MAX_HAMMING` | `300` / `900` · `10` | Mock latency · sample-photo match threshold. |
| `RECORD_FIXTURES` · `LOG_LEVEL` · `RUN_LIVE` | `false` · `info` · `0` | Recording provider (dev) · log level (content-free either way) · live tests. |
| `OPENAI_COMPAT_BASE_URL` · `OPENAI_COMPAT_API_KEY` | `http://127.0.0.1:11434/v1` · empty | `AI_PROVIDER=openai_compat` only. The OpenAI-compatible endpoint (Ollama, LM Studio or hosted) · its key (required for any non-loopback host; Ollama ignores it). |
| `OPENAI_COMPAT_MODEL_PRO` / `_FAST` | `qwen3.5:4b` / `qwen3.5:4b` | The only model ids on this provider. |
| `OPENAI_COMPAT_DATA_TIER` | `unpaid` | `local` (loopback endpoint; real papers in dev/staging) · `attested` (development only; vendor terms say no training — your attestation) · `unpaid` (samples only). |
| `OPENAI_COMPAT_MODEL_LABEL` · `OPENAI_COMPAT_VENDOR_NAME` · `OPENAI_COMPAT_NO_TRAINING_ATTESTED` | empty · empty · `false` | `{model}` (required for `local`) · `{vendor}` (required for `attested` and `unpaid`) in the consent copy · your no-training statement (required for `attested`). |
| `OPENAI_COMPAT_JSON_MODE` · `OPENAI_COMPAT_REASONING` | `auto` · `none` | `auto \| json_schema \| json_object \| prompt` · `none \| mapped \| omit` (`none` turns Qwen's thinking off). |
| `OPENAI_COMPAT_TIMEOUT_S` · `OPENAI_COMPAT_MAX_OUTPUT_TOKENS` · `OPENAI_COMPAT_MAX_IMAGES` · `OPENAI_COMPAT_CONCURRENCY` | 300 loopback / 90 hosted · `6144` · `12` · 1 loopback / 4 hosted | Per call · output cap · page images per call · parallel calls. Full meanings: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §6.1. |

### Mobile (Expo public env — baked in at build/export time; never secrets)

| Variable | Default | Meaning |
|---|---|---|
| `EXPO_PUBLIC_API_URL` | `http://127.0.0.1:8000` | API base URL (per profile in `eas.json`). |
| `EXPO_PUBLIC_APP_TOKEN` | empty | Sent as `X-App-Token` when set. |
| `EXPO_PUBLIC_APP_ENV` | `development` | The developer section in Settings shows unless `production`. |
| `EXPO_PUBLIC_DEFAULT_SAMPLE_MODE` | `false` | Start in sample mode (the `demo` build). |

---

## Scripts and commands

| Command | What it does |
|---|---|
| `make dev` | `scripts/dev.sh`: mock API on :8000 + Expo web on :8081, CORS for both localhost spellings; a trap stops both. |
| `make api` / `make web` | Either half alone. |
| `make smoke` | `scripts/smoke.sh`: boots the mock API on a free port with a throw-away `VAR_DIR`, runs `apps/api/scripts/smoke.py` (stdlib only: health, config, `en` pack, all samples × recorded languages through `/v1/analyze`, the screenshot through `/v1/troubleshoot`, grounded chat + outcome refusal, resources, 12 rules, LTR and RTL quick-sheet PDFs, feedback, sample PNGs; no `[contact removed`; D-09 fields on every demand; urgency vs BUILD_PLAN Appendix D), always stops the server. |
| `make test` | API pytest, ruff, strict mypy, mobile `tsc`, `jest`, `expo lint`. |
| `make ci` / `scripts/ci.sh` | The full CI list in order, stopping at the first failure (see [Testing](#testing)); `CI_FROM=<step>` resumes, `CI_ONLY=<step>` runs one. |
| `make export-web` | `npx expo export --platform web --clear` → `apps/mobile/dist` (includes `dist/privacy/index.html`). |
| `make host-rules` | After `make export-web`: `scripts/web-host-rules.py` writes `dist/_redirects` + `dist/404.html` so Netlify / Cloudflare Pages serve `/result/<id>` and `/papers/member/<id>` (EAS Hosting needs nothing; `--vercel` prints the `vercel.json` rewrites, `--verify <url>` checks a deploy — [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) §2.3). |
| `make types` / `make types-check` | `scripts/gen-types.sh`: regenerate / verify `apps/api/openapi.json` and `apps/mobile/src/api/schema.d.ts` (regeneration is the contract owner's job). |
| `make sync` / `make sync-check` | `apps/api/scripts/sync_to_mobile.py` (packs, languages, fixtures, fonts, national fallbacks into the app). |
| `make local-ai-setup` | `scripts/setup-local-ai.sh`: Ollama + `qwen3.5:4b` on this Mac, asking y/N before each download (`ARGS=--dry-run` shows the plan). Run it yourself; agents and CI never do. |
| `scripts/use-local-ai.sh` | Writes `apps/api/.env` for the `local` tier from `apps/api/.env.local-ai.example` (backs up a different `.env`; `--off`, `--restore`, `--dry-run`). |
| `make local-ai-check` | `apps/api/scripts/provider_check.py`: one sample paper through the real pipeline with the configured provider (schema fit, verified facts, time, JSON mode). |
| `apps/api/.venv/bin/ruff check apps/api` | Lint. |
| `apps/api/.venv/bin/mypy --config-file apps/api/pyproject.toml apps/api/proxyhealth_api apps/api/scripts apps/api/tests` | Strict type-check (mypy reads config only from the cwd, hence the flag). |
| `RUN_LIVE=1 apps/api/.venv/bin/pytest apps/api/tests/live` | Live golden gate (billed keys only). |
| `apps/api/.venv/bin/python apps/api/scripts/make_fixtures.py --check` | Sample pages render byte-identically. |
| `apps/api/.venv/bin/python apps/api/scripts/check_links.py [--freshness]` | Resource link health / `verified_on` age (weekly in CI). |
| `apps/api/.venv/bin/python scripts/make_artwork.py` | Redraws the app icon, adaptive icon, splash, favicon and notification glyph. |
| `npx eas-cli@latest build --profile development --platform android` | Android development build ([`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) §3). |

Parallel-agent rule: never run `npm install`, `npx expo install` or `pip install` while other agents work ([`CLAUDE.md`](CLAUDE.md)).

---

## Repository layout

```
ProxyHealth/
  Makefile  scripts/{dev,smoke,gen-types,ci,setup-local-ai,use-local-ai}.sh · make_artwork.py  .github/workflows/ci.yml
  CLAUDE.md                 agent rules for this machine
  docs/                     the specification set (below) + research/
  apps/api/                 Python 3.13 · FastAPI · google-genai · in memory only
    proxyhealth_api/        main, settings, errors, middleware, ratelimit, logging_, deps
      contracts/            Pydantic = the API contract (→ openapi.json → schema.d.ts)
      ai/                   provider Protocol, gemini, openai_compat, mock, recording, keypool, failover, routing, prompts/
      analysis/             pipeline + verify, contacts filter, deadline rules, urgency, scam, emergency,
                            phrasing, injection, clerk, fixed notices, redaction, uploads, troubleshoot, chat
      packs/ resources/ quicksheet/ demo/ feedback/ routers/
    data/                   langpacks/ (en canonical + es prs ar ps) · languages.yaml · resources/*.yaml ·
                            rules/*.yaml · safety/*.yaml · fixtures/<18 samples> · fonts/ (Noto, OFL)
    scripts/                export_openapi · sync_to_mobile · make_fixtures · gen_packs · spike_schema ·
                            check_links · eval_golden · smoke · provider_check
    tests/                  unit/ · contract/ · golden/ · live/ (RUN_LIVE=1)
    Dockerfile  requirements.txt  .env.example  .env.local-ai.example  openapi.json  pyproject.toml
  apps/mobile/              Expo SDK 57 · React Native 0.86 · React 19 · TypeScript 6
    app.json  eas.json      store config, plugins, permission strings, EAS profiles
    public/privacy/         the public privacy policy (copied into the web export)
    assets/                 images/ (app art, drawn by scripts/make_artwork.py) · expo.icon/ · fonts/ · fixtures/ · resources/
    locales/                iOS permission-string translations (generated)
    src/app/                routes only: onboarding/, (tabs)/, scan/, result/[id]/, papers/, troubleshoot,
                            reminders, emergency
    src/                    api/ (generated schema + client) · design/ · i18n/ · storage/ · features/ · lib/ · store/
```

---

## API at a glance

Base URL `EXPO_PUBLIC_API_URL`; `/health` plus versioned routes under `/v1`; JSON everywhere (images as base64 inside JSON); every response carries `X-Request-Id`, `X-Contract-Version: 1` and `X-Data-Use-Tier`. Field-level definitions: [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md); interactive docs at `/docs` on a running server.

| Method | Path | Model | Purpose |
|---|---|---|---|
| GET | `/health` · `/v1/config` | — | liveness; tier, features, limits, consent version, policy URL, languages |
| GET · POST | `/v1/language-packs/{tag}` · `/v1/language-packs` | — · fast | bundled/cached pack (ETag/304) · generate a pack for a typed language |
| POST | `/v1/analyze` | pro | pages + target language → `AnalysisResult` (consent header; 403 on unpaid without `demo_sample_id`) |
| POST | `/v1/troubleshoot` | pro | screenshot + goal → steps, cautions, scam risk (on unpaid, a sample only with a blank goal) |
| POST | `/v1/chat` | fast | analysis context + question → grounded answer or typed refusal; a sample's context is rebuilt on the server; 403 on unpaid/mixed; distress words → the fixed emergency lines even if the model fails |
| POST · GET | `/v1/resources/match` · `/v1/resources[/{id}]` | — | vetted help with checklist and national fallbacks |
| GET | `/v1/rules` | — | the 12 cited deadline rules |
| POST | `/v1/quicksheet/pdf` | — | text-only PDF (nothing stored) |
| POST | `/v1/feedback` | — | counts only |
| GET | `/v1/demo/fixtures[/{id}/pages/{n}]` | — | sample list and page PNGs |
| GET | `/v1/admin/keys` | — | key-pool state (`X-Admin-Token`, only when `ADMIN_TOKEN` is set) |

---

## Docs index

Read in this order: [`CLAUDE.md`](CLAUDE.md) → DECISIONS → API_CONTRACT → ARCHITECTURE → the documents for your task. When code and docs disagree, fix one and say which.

| Document | What it holds |
|---|---|
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Product stance, decisions D-01…D-32, rejected ideas, open questions, brand, the append-only change log (§14). |
| [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) | Every endpoint, model, enum and error, with examples. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Directory trees, module internals, ownership map, dev/CI/deploy, env vars, invariants. |
| [`docs/PRODUCT_SPEC.md`](docs/PRODUCT_SPEC.md) | Personas, journeys, screens S0–S19, copy (Appendix A), demo, acceptance criteria. |
| [`docs/AI_PROMPTS.md`](docs/AI_PROMPTS.md) | Prompt text, placeholders, model-output schemas, validators. |
| [`docs/DOCUMENT_TAXONOMY.md`](docs/DOCUMENT_TAXONOMY.md) | Every document type: fields, deadlines, pitfalls, fixed notices, prepare items. |
| [`docs/RESOURCE_DB.md`](docs/RESOURCE_DB.md) | Resource YAML schema, seed, matcher scoring, link-health and re-verification. |
| [`docs/COMPLIANCE_PRIVACY.md`](docs/COMPLIANCE_PRIVACY.md) | Tier matrix, consent and notice copy, store declarations, permission strings, HBNR/UPL posture, the CI-tested `privacy_claims`. |
| [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md) | Work packages, ownership, milestones, verification commands, definition of done. |
| [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) | The three-minute zero-key demo and the keyed, samples-only variant. |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Cloud Run API and demo service, web hosting with exact headers, EAS profiles, secrets, release checklist. |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Paid-tier billing setup, local-AI and attested test-build steps, key rotation, quota, quarterly resource re-verification, incidents/breach steps, device and store evidence. |
| [`docs/LOCAL_AI.md`](docs/LOCAL_AI.md) | Test with your own papers for free: Ollama + Qwen on this Mac, the `local` tier, safety checks, speed, hosted options. |
| [`docs/STORE_LISTING.md`](docs/STORE_LISTING.md) | App Store and Google Play copy and declarations, screenshot list, blockers. |
| [`docs/research/`](docs/research/) | `gemini.md`, `expo.md`, `compliance.md`, `resources.md`, `free-ai-providers.md` (the facts the decisions rest on) and the three candidate specs in `specs/`. |
| [`apps/mobile/README.md`](apps/mobile/README.md) · [`apps/mobile/AGENTS.md`](apps/mobile/AGENTS.md) | Mobile-app commands and Expo rules (verify every Expo API against the SDK 57 docs). |

---

## Store roadmap

| Phase | Deliverable | Gate |
|---|---|---|
| 1 · Zero-key end to end (done) | API in mock mode + web app + every screen; 18 samples with goldens | `make test`, `make smoke`, `scripts/ci.sh` green |
| 2 · Integration (now) | demo rehearsal on web in `en` and `prs`; privacy page; store docs; CI | [BUILD_PLAN](docs/BUILD_PLAN.md) §6 checklist |
| 3 · Live Gemini, samples only | billed keys from distinct projects (Q1); live golden gate | no invented contact; precision baseline recorded |
| 4 · Android development build | `npx eas-cli@latest build --profile development --platform android` | camera, masks, notifications channel, RTL restart, TalkBack, 200 % text ([RUNBOOK](docs/RUNBOOK.md) §7.1) |
| 5 · iOS development build | organization Apple account (Q2); vault iCloud-backup exclusion verified (Q16) | VoiceOver, AX5 text, privacy manifest accepted |
| 6 · Hardening | SDK 58 upgrade; counsel review (Q3); named language reviewers (Q6) | COMPLIANCE_PRIVACY §18 ticked |
| 7 · Store preparation | [`docs/STORE_LISTING.md`](docs/STORE_LISTING.md): title "ProxyHealth AI: Your paper, explained", Reference / Tools (not Medical), 18+, nutrition label and Data safety, Health apps declaration, Notes for Review, fixture-only screenshots | every compliance.md §1 checklist item answered; production API answers `data_use_tier: paid` |
| 8 · Submit | `eas build --profile production --platform all` → `eas submit`; web via `eas deploy --prod` | [DEPLOYMENT](docs/DEPLOYMENT.md) §5 release checklist |

---

## Contributing and testing

Hard rules (from [`CLAUDE.md`](CLAUDE.md)): no installs while other agents run; write only the files your work package owns ([`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md) Appendix A); never touch `apps/mobile/ios/` or `apps/mobile/android/`; never persist or log user content; contacts only from the paper or the vetted DB; secrets only in `.env`; everything must work with zero keys. Cross-package needs are one appended line in `docs/DECISIONS.md` §14.

### Testing

`scripts/ci.sh` runs, in order, stopping at the first failure:

1. `apps/api/.venv/bin/pytest apps/api` (unit, contract, golden; live tests skip)
2. `ruff check apps/api`
3. strict mypy in the `--config-file apps/api/pyproject.toml` form
4. `scripts/gen-types.sh --check` (OpenAPI snapshot and TS types idempotent)
5. `make_fixtures.py --check`
6. `sync_to_mobile.py --check`
7. every `data/**/*.yaml` and the workflow parse
8. no `xfail` outside `tests/live`
9. `test_privacy_claims.py` + `test_readability.py` (privacy sentences literally true and approved; grade-5 approximation over every `en.json` string with an honest allow-list)
10. `eas.json` preview/production API URLs are `https://`
11. mobile `npx tsc --noEmit`, 12. `npx jest`, 13. `npx expo lint`
14. `npx expo config --type prebuild`
15. `npx expo export --platform web --clear` with `privacy/index.html` present

`.github/workflows/ci.yml` runs the same steps (`CI_ONLY=<step> scripts/ci.sh`) in an **api** job (plus `make smoke`) and a **mobile** job (`npm ci --legacy-peer-deps`, `npx expo customize tsconfig.json`, then the mobile steps), builds and smoke-tests the Docker image, checks resource links weekly (opening an issue on a broken link) and runs the live golden gate on demand when the `GEMINI_KEYS` secret exists.

---

## Open questions and license

Questions only the user can answer: [`docs/DECISIONS.md`](docs/DECISIONS.md) §12 (Q1 billing owner, Q2 developer accounts, Q3 counsel, Q4 bundle id and web host, Q5 pilot geography, Q6–Q7 language reviewers, Q8 per-device budget, Q9 web positioning, Q10 Interactions API, Q11 hosting) and [`docs/COMPLIANCE_PRIVACY.md`](docs/COMPLIANCE_PRIVACY.md) §19 (Q15 operator identity for the privacy policy, Q16 iOS backup exclusion, Q17 label stance, Q18–Q25, Q26 approving the local-AI install, Q27 a hosted second opinion). Until Q1 is answered, keyed runs use sample papers only.

**License:** not chosen yet. `apps/mobile/LICENSE` is the MIT notice from Expo's template and covers only that template code. The Noto fonts in `apps/api/data/fonts/` and `apps/mobile/assets/fonts/` are under the SIL Open Font License (`OFL.txt`).

---

*ProxyHealth AI explains what your paper says. It is not legal, medical, housing or benefits advice, and it is not a medical device. Only a licensed professional — a lawyer (or, for an immigration case, a DOJ-accredited representative), your doctor, nurse or pharmacist, a housing counselor, or the office that sent the paper — can tell you what it means for you.*
