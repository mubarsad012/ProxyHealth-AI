# ProxyHealth AI — Your paper, explained.

One codebase for iOS, Android and the web that photographs a letter, bill, notice or form, reads it, translates it, explains it in three calm cards anchored to the exact words on the page, and then points the reader to a human we verified.

| | |
|---|---|
| **Status (2026-09-27)** | Specification set is complete and authoritative; code is at scaffold stage (Expo SDK 57 template in `apps/mobile`, Python 3.13 virtualenv and pre-downloaded Noto fonts in `apps/api`). Coding agents build from `docs/` — see the [docs table of contents](#docs-table-of-contents). The repository has no commits yet. |
| **Backbone documents** | [`docs/DECISIONS.md`](docs/DECISIONS.md) · [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) · [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Everything else conforms to them. When code and these docs disagree, fix one and say which in the PR note. |
| **Runs with zero API keys** | Yes. `AI_PROVIDER=mock` (the default when `apps/api/.env` is absent) serves 17 synthetic sample papers plus one portal screenshot end to end, with simulated latency. |
| **Models** | `MODEL_PRO=gemini-3.8-flash` (document analysis, screenshot troubleshooting) · `MODEL_FAST=gemini-3.5-flash-lite` (language packs, chat, tagging, rewrites). Env-configurable; `gemini-1.5`/`2.0`/`2.5` and `-latest` IDs are rejected at boot. |
| **Real documents** | Sent to Gemini only on the **paid** data-use tier (every key from a distinct Google Cloud project with billing attached). On unpaid or mixed key pools the server answers `403 unpaid_tier_real_documents_disabled` and serves sample papers only. |
| **Store path** | EAS Build → Android development build first (no Apple account needed) → iOS development build when the organization Apple account exists → SDK 58 upgrade → `eas submit`. See [Roadmap to the app stores](#roadmap-to-the-app-stores-eas). |

---

## Table of contents

1. [What ProxyHealth AI is](#what-proxyhealth-ai-is)
2. [Features](#features)
3. [What it deliberately does not do](#what-it-deliberately-does-not-do)
4. [Architecture](#architecture)
5. [Quickstart](#quickstart)
6. [Environment variables](#environment-variables)
7. [Scripts and commands](#scripts-and-commands)
8. [Repository layout](#repository-layout)
9. [API at a glance](#api-at-a-glance)
10. [Docs table of contents](#docs-table-of-contents)
11. [Roadmap to the app stores (EAS)](#roadmap-to-the-app-stores-eas)
12. [Contributing and testing](#contributing-and-testing)
13. [Open questions and license](#open-questions-and-license)

---

## What ProxyHealth AI is

ProxyHealth AI is a *paper decoder with a caseworker's manners*. Immigrants and other underserved adults receive hospital bills, USCIS and immigration-court notices, leases and eviction papers, Medicaid and SNAP letters, school forms, pay stubs and IRS notices — often in a language they do not read, at a reading level they were never taught, with the one date that matters buried on page three. You photograph the paper (or pick a photo or a PDF), and the app returns three cards in your own language: **What is this?**, **What is it asking for?** and **Your step-by-step plan**. Every fact — each date, amount, requested document and contact — is shown next to the exact words on the page it came from, as a highlighted crop with a confidence chip; anything the AI saw but could not confirm on the page is listed separately under "I saw these but could not confirm them on the page." and never drives urgency or reminders. Then it does what a good caseworker does: hands you a "Show the clerk" card in English for the counter, reads every paragraph aloud so it can be heard privately through earbuds instead of read through a child, keeps each family member's papers in a vault that lives only on the phone, sets reminders for the dates it found, prints a text-only quick sheet that works offline, troubleshoots the government portal you are stuck on from a screenshot, and routes you only to organizations a human verified, labelled with the date they were checked. Any language works: a grid of common languages, a free-text box for rare ones (a pack is generated while the screen reads *"Adapting system environment to your language..."*), right-to-left layouts, Noto fonts, and an honest "translated by a computer" label on every machine-translated pack.

It is **information, not advice**, and that is a design constraint enforced in code, not a footer. The app transcribes, translates, summarizes and explains what a document *says*. It does not diagnose, does not interpret a lab value for you, does not say whether you qualify for a benefit, does not predict a case outcome, does not tell you to file, appeal, pay or sign, and never drafts or fills any official form or letter. Legal-domain results carry the fixed line "This is general information about this type of paper, not legal advice about your case. Only a licensed lawyer or a DOJ-accredited representative can advise you."; medical results carry "This explains what your paper says. It is not medical advice. Ask your doctor, nurse or pharmacist what it means for you." Those sentences are chosen by document category in code; the model never writes disclaimers, never sets urgency, never computes a date, and never emits a phone number, URL or organization name (contacts come only from the paper or from the vetted resource database — anything else is replaced with "[contact removed — see Get help nearby]"). Sentences that drift into advice ("you qualify", "you should file") are caught by a phrasing linter and rewritten to "The paper says X. A {professional} can tell you what it means for you." The app is for adults 18 and older (a Gemini terms requirement), never asks anyone's immigration status, never persists a document, image or transcript on the server, and sends real documents to Gemini only on the paid data-use tier, because Google's unpaid tier uses submitted content for product improvement with human review. Full rationale: [`docs/DECISIONS.md`](docs/DECISIONS.md) §0, §4 and §5; [`docs/research/compliance.md`](docs/research/compliance.md).

---

## Features

Decision references in brackets point into [`docs/DECISIONS.md`](docs/DECISIONS.md). Everything below is v1 (MUST) unless marked SHOULD or LATER.

### Decode a paper
- **Photo, gallery or PDF in; three cards out.** 1–12 photos or exactly one PDF (≤ 12 MB, ≤ 60 pages). The client compresses to 1600 px longest edge, JPEG 0.8, EXIF stripped. Cards: *What is this?* / *What is it asking for?* / *Your step-by-step plan*, plus *Details and quotes*, a glossary of ≤ 8 terms as written, red flags, and ≤ 5 questions to ask the sender. [D-06, D-21]
- **Every fact is a quotation.** Each `Demand` and `RedFlag` carries `source_quote`, `span_ids`, `page`, `confidence` and `verified`. A verifier (NFKC, whitespace collapse, dash/quote unification, OCR confusion map O/0, l/I/1, S/5, `difflib` ratio ≥ 0.92) checks each quote against the transcript. Failures move to `unverified[]`, render struck through under "I saw these but could not confirm them on the page", and never drive urgency or reminders. Low confidence renders amber with "Re-scan this part". [D-09]
- **Side-by-side original and translation** with tappable highlight boxes from block bounding boxes. Full translation for ≤ 4 pages; above that only referenced blocks plus page 1, flagged `translation_partial`. [D-06]
- **Urgency computed in code, never by the model:** `emergency` / `critical` (a verified hearing, USCIS appointment, eviction court date or asylum-fee due date ≤ 7 days away, or recently past on court/USCIS papers: "This date may have passed — contact them today") / `high` ≤ 14 days / `medium` ≤ 30 days / `info`. Document-type floors: an NTA, hearing notice, eviction summons, NOID or utility shut-off is never below `high`. The banner is icon + word + color with a "Verify this date" CTA to the matching verification resource. Copy never dramatizes. [D-12]
- **Date math only from a printed relative phrase + a verified anchor + a cited rule** (`data/rules/deadlines.yaml`, 12 seeded rules with `source_url`, `verification ∈ {verified, likely}` and `valid_until`; served at `GET /v1/rules`). A printed date always wins; estimates render as "Estimate: … Confirm with the sender." No eviction notice or answer period is ever hardcoded — an eviction summons shows the printed court date and "The court date on this paper is the date that matters." [D-11]
- **Fixed high-severity notices by document type:** jury summons (answer it; never check "citizen", never register to vote), an I-765 renewal receipt is not work authorization, a pay-or-quit is not a court order, the asylum annual fee has no waiver, a move needs EOIR-33 (USPS forwarding does not update the court or USCIS). [D-20]
- **Scam handling as a first-class path.** Code regexes (gift cards, Western Union, MoneyGram, Zelle/Venmo/PayPal/Cash App, Bitcoin, "pay to avoid arrest/deportation", "guaranteed", "notario", a non-.gov domain near an agency name, "expedite for a fee") plus model flags produce `scam_risk ∈ {none, possible, likely}`. `likely` shows the fixed card "Scam risk: likely — ICE, USCIS, SSA and the IRS never demand payment by phone, gift card, wire, or app. Do not pay. Report it:" with DHS OIG and ReportFraud.ftc.gov from the resource DB, and forces `scam_report` resources to the top. [D-13]
- **Emergency card from fixed copy**, keyword-triggered in every bundled language and biased to over-trigger (911 / 988 call-or-text / Poison Help 1-800-222-1222 / DV hotline). Never authored by the model. [D-14]
- **Prompt-injection defence:** instruction-in-document phrasing is detected in code; the analysis re-runs once with the offending block masked; the result carries `injection_suspected` and `warnings: [injection_masked]`. [D-15]
- **"Hide parts" before sending.** Black rectangles are burned into the JPEG on a `<canvas>` on web; on native the client sends normalized mask rectangles and the server burns them with Pillow in memory before Gemini sees the image; unmasked bytes are never stored. SSN-like patterns are always masked in returned text; A-numbers and receipt numbers only when the user opts in. [D-19]
- **Unreadable pages are a `200`**, not an error: `quality.readable=false` shows "Try again in brighter light / flatten the page" and does not spend quota again automatically.

### Act on it
- **"Show the clerk" card.** Fixed English template "Hello. I speak {Language}. I am here about: {document type as written}. I need help with: {need line}. Please speak slowly or write it down. Thank you." with a linted, contact-filtered AI need line (≤ 200 chars) that falls back to a per-document-type template. "I may ask for a free interpreter." is appended only when the matched resource or sender is tagged `hhs_funded_health`. Clerk mode is LTR, high contrast, ≥ 24 pt, hides vault navigation, and exits only by a 1.5 s long-press on "Back to me". [D-18]
- **Action Hub ("Get help nearby").** Deterministic matching of validated `resource_tags` × state/county/zip3 × language over a vetted YAML database (≥ 70 entries, national plus a Northern Virginia seed, each with `verified_on`, `verification_method`, `link_health`), a prepare-these-documents checklist per resource and document type, ≤ 2 results per organization type, `211` / ImmigrationLawHelp / HRSA health centers as national fallbacks, and an honest one-line note on LSC-restricted legal aid with "If that is not you, try these instead". [D-10, D-24]
- **Screenshot troubleshooting** with two modes, *Stuck on a website?* (`portal`) and *Is this a scam?* (`scam_check`): what the screen asks for, the exact quoted error text, 1–6 taps naming buttons as written, cautions ("This button submits the form."), and a fixed credential/payment guard banner. [D-13]
- **Grounded follow-up chat.** Stateless: the client re-sends the analysis context and ≤ 8 prior turns. Answers cite block ids, say "The paper does not say" when it does not, and refuse with a typed `refusal_kind` (`eligibility`, `filing_advice`, `outcome`, `medical_interpretation`, `drafting`, `contact_request`, `out_of_scope`) plus a fixed referral (`lawyer_or_accredited_rep`, `clinician`, `housing_counselor`, `benefits_office`, `sender`). [D-17]
- **Reminders** 7/3/1 days before each verified, stated date at 9:00 local time (native `expo-notifications`, Android channel "Dates to remember"); `.ics` download on web and via the share sheet on native. Notification text is generic ("You have a date coming up") unless the user opts into detail. [D-22]
- **Offline quick sheet.** Text-only: three cards, dates, checklist, and resource phones re-validated against the DB. Native: `expo-print` HTML with embedded Noto fonts → share sheet. Web: `POST /v1/quicksheet/pdf` (reportlab, embedded Noto fonts, Arabic-script shaping, ≤ ~200 KB, nothing stored) → download. "Copy text" fallback everywhere.

### Keep it private
- **Family vault, on-device only, opt-in.** After each scan: "Save" → "Whose paper is this?" (Me plus members with initials and a color); move between members; per-member wipe. Native: `expo-sqlite` (WAL) plus page files under `Paths.document/vault/<doc_id>/`, OS file encryption, a random device-only key in SecureStore reserved for the PIN lock (SHOULD), `android.allowBackup: false`. Web: session-only by default, opt-in IndexedDB labelled "Keep on this device (not encrypted by the app)" with "Clear when I close this tab". One-tap "Delete everything". No SQLCipher or iOS-backup-exclusion claim until verified in the first development build. [D-22, D-23]
- **Nothing on the server.** Request bodies are processed in memory and released; no temp files; the access log is an allow-list of content-free fields; `var/` holds only key-pool state, generated language packs and feedback counters. Feedback is counts only — no free text, no AI sentence. [D-08, D-31]
- **Consent that is literally true per tier.** Screen S2 fetches the tier from `GET /v1/config` and shows: paid — "Google does not use your paper to improve its products. Google keeps a short safety log for a limited time, then deletes it."; unpaid/mixed (red, icon + word) — "This test build uses a free AI key. Google may read and use what is sent. Do not send real papers. Sample papers only."; demo — "Sample mode. No AI service is contacted. Nothing leaves this device."; unknown (API unreachable) — "I cannot confirm how your paper would be handled right now. You can try a sample paper or come back later." Plus "This app is for adults 18 and older.", a 72 pt "I understand, continue", "Not now" (Home with scan tiles disabled) and "Try a sample paper first" (no consent needed). The API requires `X-Consent-Version` on analyze/troubleshoot/chat → `428 consent_required`. A CI test asserts every privacy sentence in `en.json` is on the approved list. [D-02]
- **Never asks immigration status; location is state plus zip3, never a full ZIP or GPS; no analytics or ad SDKs.** [D-24]

### Speak the reader's language
- **Bundled offline packs (machine-translated, labelled):** Tier 1 `en es zh-Hans zh-Hant vi tl ar ht pt-BR ru uk ko fr`; Tier 2 `prs` (Dari) `ps` (Pashto) `fa ur hi pa bn so sw am my ne rw`. Only `en` is `machine_translated: false` at v1; every other pack shows "This language was translated by a computer" until a named reviewer signs it. [D-25]
- **Any typed language (Tier 3):** `POST /v1/language-packs {language_query, pack_version}` resolves to a BCP-47 tag (or an `x-<slug>` private-use tag), generates the pack in 60-key chunks with the fast model, QA's it, and caches it server-side with an ETag, single-flight per tag. Loading copy is exactly *"Adapting system environment to your language..."* followed by "About 20 seconds"; partial packs say "Some words are in English." [D-25]
- **RTL without `expo-updates`:** `useDirection()` drives `row-reverse`, `textAlign` and `writingDirection` immediately; native also syncs `I18nManager` and shows "Restart the app to finish switching"; web sets the `dir` attribute. Verbatim values (dates, case numbers, amounts, phones, URLs, agency names) are Bidi-isolated; digits are never reversed or substituted (a localized date line may be *added*). Fonts: Noto Sans, Noto Naskh Arabic, Noto Nastaliq Urdu (line-height 2.0), Noto Sans Ethiopic, Myanmar, Devanagari, Bengali, Gurmukhi, Hanifi Rohingya — pre-downloaded (OFL) into `apps/api/data/fonts/` and `apps/mobile/assets/fonts/`. [D-26]
- **Read-aloud on every paragraph** with `expo-speech`: a 44×44 speaker button after each paragraph, "I want to hear it, not read it" auto-play, a persistent stop button, and an honest closest-language fallback ("No Rohingya voice on this phone. Hear it in Burmese or English?"). Server TTS is LATER. [D-26]
- **Cultural and tone preferences** (`tone: plain|formal`, `calendar_notes` such as "Ramadan", `date_format`) are passed to prompts and never logged.

### Be honest about the AI
- **Data-use tier `paid | unpaid | mixed | demo | none`** computed server-side from per-key operator attestations, exposed in `GET /v1/config` and the `X-Data-Use-Tier` response header, and enforced: real documents are blocked (403) on unpaid or mixed pools; mock is never a silent fallback. [D-01]
- **Multi-key failover across distinct Cloud projects:** a per-slot, per-tier state machine (`healthy` / `cooling` / `rpd_exhausted` / `disabled`); `Retry-After` or exponential cooldown capped at 15 min; daily exhaustion only when the 429 mentions a daily quota; one same-slot retry on 503; 401/403 disables a slot; LRU billed-first selection; ≤ 3 slot attempts within 100 s; optional pro→fast degradation flagged `model_meta.quality="degraded"`; state persisted to `var/keypool.json`. All slots exhausted → `429 quota_exhausted` with `Retry-After` and `key_exhausted: true`, rendered as "Our helper is very busy right now. Try again in {n} minutes, or see what you can do offline." with Retry / Save to read later / Call 211 / Try a sample paper. [D-07]
- **Structured output the API accepts:** small, flat model-output schemas (depth ≤ 3, no dicts, no `Any`, enums ≤ 64, `list[{key, value}]` for pack strings) separate from the rich API result; `ANALYSIS_MODE=auto` falls back from single-call to two-call (transcribe → explain) when the schema is rejected or the output is incomplete; a day-0 spike script pins the mode. [D-06]
- **Blocked generations** (`safety`, `spii`, `prohibited_content`, `recitation`, `blocklist`) surface as `422 content_blocked` with a clear message and are never retried on another key.
- **Demo mode is real product surface:** `demo_sample_id` → fixture output; a 16×16 dHash match so a judge can photograph a printed SAMPLE sheet in zero-key mode; 300–900 ms simulated latency; canned grounded chat; pseudo-localized packs. Keyed demos use fixtures only — never a real letter. [D-29]

### Everywhere, accessibly
- **One Expo Router codebase:** root `Stack` + a `(tabs)` group using JS `Tabs` on every platform (Home · My papers · Get help · Settings); scan, result, chat, clerk, quick sheet, troubleshoot, reminders and emergency are stack screens above the tabs. Every device feature has a `Platform.OS === 'web'` path; pickers on web run inside the click handler. [D-27]
- **"Big Calm" design system:** base font 18 (body never below 16), 56 pt buttons, 72 pt primary CTA, `hitSlop` 8, 7:1 body contrast, light/dark/high-contrast palettes, reduce-motion, `allowFontScaling` on, one primary action per screen, a calm persistent "Need help now?" affordance, no emoji in controls, WCAG 2.2 AA floor, tested at 200 % font scale in LTR and RTL with VoiceOver and TalkBack. [D-28]
- **Offline:** capture works offline ("No internet. I can take the photo now and read it later."); vault, quick sheets, reminders, bundled packs and a bundled national-resource subset work with no connection; Help shows the last cached results per document.

---

## What it deliberately does not do

| Never | Because |
|---|---|
| Diagnose, interpret a lab value "for you", or give medical advice | Gemini terms forbid use "to provide medical advice"; FDA "interpret or analyze" line; Apple 1.4.1 scrutiny. Fixed `medical_information_only` disclaimer and a clinician reminder instead. |
| Say whether you qualify, whether you should file/appeal/pay/sign, or what the outcome will be | Unauthorized practice of law is state law (*Upsolve v. James*); Google's Prohibited Use Policy bars unsupervised high-stakes decisions in legal, healthcare, housing and social-welfare domains. Phrasing linter, `refusal_kind` and fixed referrals. |
| Draft, fill or format any official form or letter | Play policy on AI-generated official documentation; notario-style misuse. `drafting` requests are refused with a referral. |
| Invent a phone number, URL, address or organization | Highest-severity failure for this population. Contacts only from the paper or the vetted DB; everything else becomes "[contact removed — see Get help nearby]". |
| Compute a deadline from memory | Agency- and state-specific and unforgiving. Only printed dates, or a cited rule with a verified anchor, ever produce a date. |
| Send a real document to an unpaid Gemini key | Unpaid-tier content is used for product improvement with human review, and Google says not to submit personal information there. Server-side 403. |
| Store a document, image or transcript server-side, or ask immigration status | The trust boundary is the device; design as if any server store will eventually be subpoenaed. |
| Claim human-reviewed translations, SQLCipher encryption or iOS backup exclusion before they are verified | FTC Act §5 literal truth; store-claim risk. Copy says only what the implementation does. |

---

## Architecture

```
┌────────────────────── one Expo codebase · iOS / Android / web  (apps/mobile) ──────────────────────┐
│ Expo Router: root Stack + JS Tabs (Home · My papers · Get help · Settings) + stack screens          │
│ "Big Calm" tokens · i18n packs (RTL via useDirection, Noto fonts, Bidi isolation) · expo-speech     │
│ vault: expo-sqlite + files under Paths.document/vault/ (native) | memory / opt-in IndexedDB (web)   │
│ reminders: expo-notifications (native) | .ics (web) · quick sheet: expo-print (native) | server PDF │
│ typed API client (schema.d.ts generated from openapi.json) · consent record · install id · samples  │
└───────────────┬────────────────────────────────────────────────────────────────────────────────────┘
                │ HTTPS · JSON bodies with base64 pages (≤ 20 MB) · X-Consent-Version · X-Install-Id · X-Request-Id
┌───────────────▼───────────────── apps/api · FastAPI · Python 3.13 · in-memory only ────────────────┐
│ middleware: request id → content-free access log → body limit (413) → CORS → X-Contract-Version /   │
│             X-Data-Use-Tier headers → consent check (428) → tier gate (403) → rate limit (429)       │
│ routers ──► pipelines ──► AIProvider ──┬─ GeminiProvider  (failover.py ⇄ keypool.py, per slot/tier) │
│                                        └─ MockProvider    (fixtures · dHash match · 300–900 ms)     │
│ analysis safety pipeline: uploads → redaction (Pillow) → single | two_call → verify quotes →        │
│   contacts filter → deadline rules → urgency → scam → emergency → phrasing lint → injection re-run  │
│   → clerk card → fixed notices → tags/resources → disclaimers → AnalysisResult                      │
│ resources YAML → deterministic matcher · reportlab quick sheet · langpack cache (ETag) · feedback   │
│ var/ (git-ignored): keypool.json · langpacks/<tag>--<pack_version>.json · feedback_counts.sqlite    │
│                     — never a document, image, transcript or model sentence                         │
└───────────────┬────────────────────────────────────────────────────────────────────────────────────┘
                │ google-genai 2.25 · client.aio.models.generate_content · response_schema=<Pydantic> · store-less
       Gemini API ── MODEL_PRO=gemini-3.8-flash (analyze / troubleshoot) · MODEL_FAST=gemini-3.5-flash-lite
                     (language packs / chat / tagging) · one key per DISTINCT billed Cloud project
                     unpaid keys → fixtures only (403 on real documents)
```

**Trust boundary = the device.** The server holds nothing a subpoena could return. Pydantic v2 models in `apps/api/proxyhealth_api/contracts/` are the single source of truth for the API; `apps/api/openapi.json` is committed and snapshot-tested; `apps/mobile/src/api/schema.d.ts` is generated from that file with `openapi-typescript` (no running server needed). Full directory trees, module-by-module internals and the ownership map: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Quickstart

### 0. Prerequisites (this Mac: macOS arm64, no Xcode, no Homebrew)

- **Node 24 LTS** lives at `~/.local/node/bin` (added to `~/.zprofile`). In a non-login shell run `export PATH="$HOME/.local/node/bin:$PATH"` first.
- **Python 3.13 virtualenv already exists** at `apps/api/.venv` with every dependency installed: fastapi, uvicorn, pydantic v2, pydantic-settings, google-genai 2.25, pillow, reportlab, pyyaml, python-multipart, httpx, pypdfium2, slowapi, arabic-reshaper, python-bidi; dev: pytest, pytest-asyncio, pytest-cov, ruff, mypy, types-PyYAML. Run everything through it: `apps/api/.venv/bin/python`, `apps/api/.venv/bin/pytest`, `apps/api/.venv/bin/uvicorn`.
- **Mobile `node_modules` are installed.** Do **not** run `npm install`, `npx expo install` or `pip install` while other agents are working ([`CLAUDE.md`](CLAUDE.md) rule 1). If you must reinstall alone: `cd apps/mobile && npm install --legacy-peer-deps` (`openapi-typescript` pins TypeScript 5).
- **No iOS simulator** here (Command Line Tools only): `npx expo run:ios` will not work. Local testing = Expo web plus a phone; store builds go through EAS.
- Once WP8 lands, `make dev` runs steps 1 and 2 together (see [Scripts and commands](#scripts-and-commands)); the raw commands below are what the Makefile runs.

### 1. API in demo mode (zero keys)

With no `apps/api/.env` the server defaults to `AI_PROVIDER=mock`, `ENV=development`, `VAR_DIR=./var`.

```sh
cd /Users/sadiqmubarak/Desktop/ProxyHealth/apps/api
.venv/bin/uvicorn proxyhealth_api.main:app --reload --port 8000
```

Verify with the "tier: none" endpoints (no model call):

```sh
curl -s http://127.0.0.1:8000/health
# {"status":"ok","provider":"mock","version":"0.1.0","contract_version":1,"keys_configured":0,"keys_healthy":0,"data_use_tier":"demo","resources_loaded":74}

curl -s http://127.0.0.1:8000/v1/config | head -c 800        # data_use_tier "demo", features.real_documents_allowed true, limits, consent_version, languages
curl -s http://127.0.0.1:8000/v1/demo/fixtures                # 17 sample papers + 1 screenshot, all watermarked SAMPLE
curl -s http://127.0.0.1:8000/v1/language-packs/prs | head -c 400   # bundled Dari pack, machine_translated: true
curl -s http://127.0.0.1:8000/openapi.json | head -c 300      # the committed contract (FastAPI's interactive docs are at /docs)
```

Run a full analysis against a sample. The mock provider resolves `demo_sample_id` to the fixture's expected output; `X-Consent-Version` is not required on demo requests; `pages` is still required by the schema (the mock uses it for dHash matching when no `demo_sample_id` is given):

```sh
apps/api/.venv/bin/python - <<'PY'
import base64, json, urllib.request
base = "http://127.0.0.1:8000"
png = urllib.request.urlopen(f"{base}/v1/demo/fixtures/medicaid_address_confirmation/pages/1").read()
body = json.dumps({
    "pages": [{"mime_type": "image/png", "data_base64": base64.b64encode(png).decode()}],
    "target_language": "en",
    "demo_sample_id": "medicaid_address_confirmation",
    "client_platform": "web",
}).encode()
req = urllib.request.Request(f"{base}/v1/analyze", data=body, headers={"Content-Type": "application/json"})
result = json.load(urllib.request.urlopen(req))
print(result["category"], result["document_type"], result["urgency"]["level"], result["demands"][0]["value_verbatim"], result["model_meta"])
# benefits medicaid_renewal high October 14, 2026 {'provider': 'mock', ..., 'data_use_tier': 'demo', 'demo': True, ...}
PY
```

`scripts/smoke.sh` (WP8) does this for every endpoint and asserts urgency, verified facts, resources and the absence of `[contact removed]` markers.

### 2. Web app

In a second terminal:

```sh
export PATH="$HOME/.local/node/bin:$PATH"
cd /Users/sadiqmubarak/Desktop/ProxyHealth/apps/mobile
EXPO_PUBLIC_API_URL=http://127.0.0.1:8000 npx expo start --web
```

Opens `http://localhost:8081` (the API's default `CORS_ORIGINS` already allows it). Walk the zero-key demo: pick **Dari** on the language grid (the UI flips RTL immediately) → the consent screen shows the **demo** badge ("Sample mode. No AI service is contacted. Nothing leaves this device.") → **Try a sample paper first** → *Medicaid letter asking to confirm your address* → three cards, urgency banner with October 14, 2026, a speaker button on every paragraph, **Show the clerk**, **Get help nearby**, **Save** → "Whose paper is this?"; then Settings → *My language is not here* → type "Rohingya" → *"Adapting system environment to your language..."* → a pseudo-localized Hanifi Rohingya pack with the computer-translated banner.

Static build (what EAS Hosting serves): `npx expo export --platform web` → `dist/`. `EXPO_PUBLIC_API_URL` is baked in at export time.

### 3. Phone via Expo Go (smoke only)

Expo Go is for quick smoke checks. Config-plugin permission strings, notifications, the RTL restart prompt, `expo-sqlite` options and SecureStore behaviour all need a **development build** (phase 3 of the [roadmap](#roadmap-to-the-app-stores-eas)). Caveat from [`docs/research/expo.md`](docs/research/expo.md): as of the May 2026 changelog the App Store build of Expo Go supported SDK 54, while SDK 57 Expo Go was available through Expo CLI for Android devices and iOS simulators, or through `eas go` (TestFlight, needs an Apple Developer account). Check the store version before relying on it; if it does not match SDK 57, go straight to the Android development build.

1. Put the Mac and the phone on the same Wi-Fi and bind the API to the LAN (the default binds `127.0.0.1`, which a phone cannot reach):
   ```sh
   cd apps/api && .venv/bin/uvicorn proxyhealth_api.main:app --reload --host 0.0.0.0 --port 8000
   ```
2. Find the Mac's LAN IP (`ipconfig getifaddr en0`) and start Metro pointing the app at it:
   ```sh
   cd apps/mobile && EXPO_PUBLIC_API_URL=http://192.168.1.23:8000 npx expo start
   ```
3. Scan the QR code with Expo Go on Android (or with the iOS Camera app when a matching Expo Go exists). The consent badge reads **demo** because the API is in mock mode; photographing a printed SAMPLE sheet is recognised by dHash matching.
4. If the API is unreachable the consent badge reads **unknown** ("I cannot confirm how your paper would be handled right now. You can try a sample paper or come back later."), scanning is disabled and samples stay enabled — that is the intended behaviour, not a bug.

### 4. Adding Gemini keys — read the billing / data-tier note first

**The Gemini API Additional Terms (effective 2026-03-23)** say that on *Unpaid Services* Google uses submitted content and responses to improve its products, that "human reviewers may read, annotate, and process your API input and output", and, verbatim, "Do not submit sensitive, confidential, or personal information to the Unpaid Services." Your access is a *Paid Service* **only when the key's Cloud project has an active Cloud Billing account attached** — even at $0 usage. Even on the paid tier Google keeps a short abuse log "for a limited period of time", so "Google never sees it" would be false. Rate limits are per **project**, not per key, so several keys from one project add nothing; per-model free-tier RPM/RPD figures are no longer published (read them in AI Studio). EEA/Switzerland/UK users may only be served from paid keys. Sources: [`docs/research/gemini.md`](docs/research/gemini.md) §1 and §3, [`docs/research/compliance.md`](docs/research/compliance.md) §4.

ProxyHealth AI encodes this as an operator attestation per key and enforces it server-side ([D-01](docs/DECISIONS.md)):

```sh
# apps/api/.env  (git-ignored; start from apps/api/.env.example)
ENV=development
AI_PROVIDER=gemini
GEMINI_KEYS='[{"key":"AIza...","project":"proxyhealth-prod-a","billing":true},{"key":"AIza...","project":"proxyhealth-prod-b","billing":true}]'
MODEL_PRO=gemini-3.8-flash
MODEL_FAST=gemini-3.5-flash-lite
CORS_ORIGINS=http://localhost:8081
```

- `project` labels **must be distinct** (duplicates abort boot with a clear message). `billing` is your statement that a Cloud Billing account is attached to that project — the SDK cannot detect it, which is why `.env.example` calls it an attestation.
- Startup rejects any model ID containing `gemini-1.5`, `gemini-2.0` or `gemini-2.5` or ending in `-latest`, and rejects `gemini-3.1-pro-preview` unless every key is billed (it has no free tier). `thinking_level="minimal"` is never sent to a `gemini-3.8*` model; `temperature`, `top_p`, `top_k`, `candidate_count` and `thinking_budget` are never sent.
- Run the day-0 structured-output spike once and pin the result in `.env.example` comments: `apps/api/.venv/bin/python apps/api/scripts/spike_schema.py` decides whether the fixtures need `ANALYSIS_MODE=single` or `two_call` (default `auto`).

What each resulting **data-use tier** means (visible in `GET /v1/config.data_use_tier`, the `X-Data-Use-Tier` header and the consent badge):

| Tier | When | Real documents | Consent badge copy (English base string) |
|---|---|---|---|
| `paid` | `AI_PROVIDER=gemini`, every slot `billing:true` | Allowed | "Google does not use your paper to improve its products. Google keeps a short safety log for a limited time, then deletes it." |
| `unpaid` | any slot `billing:false` | **Blocked** — `403 unpaid_tier_real_documents_disabled` on `/v1/analyze`, `/v1/troubleshoot`, `/v1/chat` unless `demo_sample_id` is set (fixture bytes are loaded from disk; client pages are ignored) | "This test build uses a free AI key. Google may read and use what is sent. Do not send real papers. Sample papers only." (red, icon + word) |
| `mixed` | some slots billed, some not | Reported as `mixed`, **routed as `unpaid`** (blocked); a warning is logged per request naming the unbilled slot; the pool never prefers an unbilled slot | same as unpaid |
| `demo` | `AI_PROVIDER=mock` | Fixtures only; no AI service is contacted | "Sample mode. No AI service is contacted. Nothing leaves this device." |
| `none` | `AI_PROVIDER=gemini` with zero slots | Boot fails unless `ENV=development` (then `503 provider_not_configured`) | — |

Rules that keep this honest:

- **Developer testing on a free key:** `ALLOW_UNPAID_REAL_DOCUMENTS=true` bypasses the 403 for *synthetic* test scans only and is a **boot error in `ENV=production`**. Never photograph a real letter through a free key — not your own, not a judge's, regardless of consent.
- **Production with an unbilled slot:** refused at boot unless `ALLOW_UNPAID_KEYS=1`, and even then real documents stay blocked; the flag exists so a fixtures-only demo instance can run.
- **Mock is never a silent fallback.** Quota exhaustion returns `429 quota_exhausted` with `Retry-After` and `key_exhausted: true`; the *client* offers "Try a sample paper" explicitly.
- **Inspect the pool** (content-free): set `ADMIN_TOKEN=...` and call `curl -H 'X-Admin-Token: ...' http://127.0.0.1:8000/v1/admin/keys` — per-slot, per-tier state with the operator `project` label and `key_last4`, never the key or a hash of it.
- **Store privacy answers** ("Data Not Collected" for document content) are defensible only on the `paid` tier — see the per-tier matrix in [`docs/COMPLIANCE_PRIVACY.md`](docs/COMPLIANCE_PRIVACY.md).

---

## Environment variables

Exactly as specified in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §6. Settings are parsed by pydantic-settings from `apps/api/.env` with `extra="forbid"`, so an unknown variable is a boot error. Secrets never appear in `repr` or logs.

### `apps/api/.env` (copy from `apps/api/.env.example`)

| Variable | Default | Meaning |
|---|---|---|
| `ENV` | `development` | `development \| staging \| production`. Production forbids unbilled keys (unless `ALLOW_UNPAID_KEYS=1`) and forbids `ALLOW_UNPAID_REAL_DOCUMENTS`. |
| `AI_PROVIDER` | `mock` | `mock \| gemini \| gemini_interactions` (last is LATER). |
| `GEMINI_KEYS` | `[]` | JSON list of `{"key","project","billing"}`. Each key from a **different** Google Cloud project. `billing` is an operator attestation that a Cloud Billing account is attached (paid tier). EEA/CH/UK users → all `billing:true`. |
| `ALLOW_UNPAID_KEYS` | `0` | Lets production boot with `billing:false` slots (fixtures only; real documents stay blocked). |
| `ALLOW_UNPAID_REAL_DOCUMENTS` | `false` | Dev-only: bypass the 403 gate for synthetic test scans. Boot error in production. |
| `MODEL_PRO` | `gemini-3.8-flash` | Reasoning tier. 1.5/2.0/2.5/`-latest` rejected. |
| `MODEL_FAST` | `gemini-3.5-flash-lite` | Fast tier. |
| `MODEL_PRO_DEGRADED_THINKING` | `medium` | Thinking level when a pro task runs on the fast model. |
| `ALLOW_DEGRADED` | `true` | Enable pro → fast degradation. |
| `ANALYSIS_MODE` | `auto` | `auto \| single \| two_call` (D-06). |
| `TRANSLATE_FULL_MAX_PAGES` | `4` | Full translation only up to this many pages. |
| `RPD_SOFT_CAP_PRO` / `RPD_SOFT_CAP_FAST` | `0` | Per-slot daily soft caps; 0 = disabled. Set after reading AI Studio limits. |
| `UPSTREAM_TIMEOUT_S` | `90` | Per upstream call. |
| `FAILOVER_DEADLINE_S` | `100` | Total budget per request across slots. |
| `MAX_PAGES` | `12` | Images per request. |
| `MAX_PAGE_BYTES` | `4194304` | Per image (decoded). |
| `MAX_PDF_BYTES` | `12582912` | Per PDF (decoded). |
| `MAX_PDF_PAGES` | `60` | |
| `MAX_REQUEST_BYTES` | `20971520` | JSON body. |
| `MAX_UPSTREAM_INLINE_BYTES` | `18874368` | Sum of media bytes sent to Gemini. |
| `MAX_CHAT_HISTORY` | `8` | |
| `CORS_ORIGINS` | `http://localhost:8081` | Comma list. Add the web host. |
| `APP_TOKEN` | (empty) | When set, `X-App-Token` is required. |
| `ADMIN_TOKEN` | (empty) | Enables `/v1/admin/keys`. |
| `INSTALL_HASH_SECRET` | (random in dev) | HMAC secret for install-id hashing. |
| `RATE_LIMIT_ANALYZE_PER_HOUR` / `RATE_LIMIT_ANALYZE_PER_DAY` | `20` / `100` | Per install hash. |
| `RATE_LIMIT_IP_PER_MINUTE` | `60` | Coarse per-IP-class. |
| `CONSENT_VERSION` | `2026-09-24` | Echoed in `/v1/config`; bump when consent copy changes. |
| `PRIVACY_POLICY_URL` | `https://proxyhealth.expo.app/privacy` | Public HTML URL. |
| `VAR_DIR` | `./var` | Runtime state dir (git-ignored). |
| `LANGPACK_CACHE_TTL_DAYS` | `180` | |
| `MOCK_LATENCY_MIN_MS` / `MOCK_LATENCY_MAX_MS` | `300` / `900` | Mock provider simulated latency. |
| `MOCK_PHASH_MAX_HAMMING` | `10` | dHash threshold. |
| `LOG_LEVEL` | `info` | |
| `RUN_LIVE` | `0` | Enables live tests. |

Deployment note ([D-03](docs/DECISIONS.md)): "If any users are in the EEA, Switzerland or the UK, every key must be `billing:true`; `ALLOW_UNPAID_KEYS` must be unset."

### `apps/mobile` (Expo public env; baked at build/export time)

| Variable | Default | Meaning |
|---|---|---|
| `EXPO_PUBLIC_API_URL` | `http://127.0.0.1:8000` | API base URL. |
| `EXPO_PUBLIC_APP_TOKEN` | (empty) | Sent as `X-App-Token` when set. |
| `EXPO_PUBLIC_APP_ENV` | `development` | Shows the developer section in Settings when not `production`. |
| `EXPO_PUBLIC_DEFAULT_SAMPLE_MODE` | `false` | Start in sample mode (judging builds). |

**No secrets ever live in the mobile app.** Use the Mac's LAN IP in `EXPO_PUBLIC_API_URL` for a phone, and set it per profile in `eas.json` for builds.

---

## Scripts and commands

### Repo-root `Makefile` (WP8; wraps the raw commands below)

| Target | Runs |
|---|---|
| `make dev` | `scripts/dev.sh`: `export PATH="$HOME/.local/node/bin:$PATH"; (cd apps/api && .venv/bin/uvicorn proxyhealth_api.main:app --reload --port 8000) & (cd apps/mobile && EXPO_PUBLIC_API_URL=http://127.0.0.1:8000 npx expo start --web)`; a trap kills both. |
| `make types` | `apps/api/.venv/bin/python apps/api/scripts/export_openapi.py && (cd apps/mobile && npm run gen:types)` — regenerates `apps/api/openapi.json` and `apps/mobile/src/api/schema.d.ts`. |
| `make sync` | `apps/api/.venv/bin/python apps/api/scripts/sync_to_mobile.py` — copies `data/langpacks/*.json`, `languages.yaml`, fixture thumbnails and manifest into `apps/mobile`. |
| `make test` | `apps/api/.venv/bin/pytest apps/api && (cd apps/mobile && npx tsc --noEmit && npx jest && npx expo lint)` |
| `make smoke` | `scripts/smoke.sh` — boots the API with `AI_PROVIDER=mock`, runs `apps/api/scripts/smoke.py` against every endpoint, asserts urgency / facts / resources / no `[contact removed]`. |
| `make export-web` | `cd apps/mobile && npx expo export --platform web` |

Root `scripts/` (WP8): `dev.sh`, `smoke.sh`, `gen-types.sh`, `ci.sh`.

### Raw commands (verified on this machine — keep them green)

| Purpose | Command |
|---|---|
| API server (mock by default) | `cd apps/api && .venv/bin/uvicorn proxyhealth_api.main:app --reload --port 8000` |
| API tests (all but live) | `apps/api/.venv/bin/pytest apps/api` |
| API live golden gate | `RUN_LIVE=1 apps/api/.venv/bin/pytest apps/api/tests/live` (needs `GEMINI_KEYS`) |
| API lint / type-check | `apps/api/.venv/bin/ruff check apps/api` · `apps/api/.venv/bin/mypy apps/api` |
| Export the OpenAPI snapshot | `apps/api/.venv/bin/python apps/api/scripts/export_openapi.py` |
| Mobile type-check | `cd apps/mobile && npx tsc --noEmit` (in CI run `npx expo customize tsconfig.json` first so `expo-env.d.ts` exists for typed routes) |
| Mobile tests | `cd apps/mobile && npx jest` |
| Mobile lint | `cd apps/mobile && npx expo lint` |
| Mobile web dev server | `cd apps/mobile && EXPO_PUBLIC_API_URL=http://127.0.0.1:8000 npx expo start --web` |
| Mobile web export | `cd apps/mobile && npx expo export --platform web` → `dist/` |
| Metro for a phone | `cd apps/mobile && EXPO_PUBLIC_API_URL=http://<mac-lan-ip>:8000 npx expo start` |
| EAS | `npx eas-cli@latest build:configure` · `npx eas-cli@latest build --profile development --platform android` · `npx eas-cli@latest build --platform all --profile production` · `npx eas-cli@latest submit --platform ios` / `--platform android` · `npx eas-cli@latest deploy` (web; `--prod` for production) |

### `apps/mobile/package.json` scripts

| Script | Command | Note |
|---|---|---|
| `start` / `android` / `ios` / `web` | `expo start [--android \| --ios \| --web]` | `ios` cannot work on this Mac (no Xcode). |
| `lint` | `expo lint` | |
| `test` | `jest` (preset `jest-expo`) | `@testing-library/react-native` v14: `render()` is **async** (`const { getByText } = await render(<X/>)`); the `screen` helper is not implemented — use the queries `render` returns. |
| `typecheck` | `tsc --noEmit` | TypeScript 6: `@types/*` are not auto-included; `tsconfig.json` lists `"types": ["jest"]` — add to that list rather than relying on auto-inclusion. |
| `gen:types` | **target (WP0):** `openapi-typescript ../api/openapi.json -o src/api/schema.d.ts` | The template value still points at `http://127.0.0.1:8000/openapi.json`; WP0 changes it to the committed file so no server is needed. |
| `export:web` | `expo export --platform web` | |
| `reset-project` | template helper (`scripts/reset-project.js`) | Deleted with the other template files (D-27). |

### `apps/api/scripts/*.py`

| Script | Purpose |
|---|---|
| `export_openapi.py` | Writes `apps/api/openapi.json` deterministically from `create_app()`; `tests/contract/test_openapi_snapshot.py` fails CI if the committed file is stale. |
| `gen_packs.py` | Generates or refreshes the bundled Tier 1+2 packs with `MODEL_FAST` in 60-key chunks (requires keys; run by one agent, never in CI). |
| `sync_to_mobile.py` | Copies `data/langpacks/*.json`, `languages.yaml`, fixture thumbnails and manifest into `apps/mobile` (`--check` in CI verifies equality). |
| `check_links.py` | Weekly resource link-health checker (browser UA; 403 → `unknown_403`; JS-rendered → `js_rendered`; Cloudflare → `unverified`; 404/410 → `broken`). |
| `eval_golden.py` | Live golden evaluation (`RUN_LIVE=1`): fact precision/recall and invented-contact count. |
| `spike_schema.py` | Day-0 structured-output spike against `MODEL_PRO` for `single` vs `two_call` (D-06). |
| `make_fixtures.py` | Renders the synthetic fixture pages from text templates with Pillow (SAMPLE watermark; Arabic-script text shaped with `arabic_reshaper` + `python-bidi`). |
| `smoke.py` | Used by `scripts/smoke.sh`: posts fixtures to every endpoint against a running mock API. |

---

## Repository layout

Target layout from [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §2–§3, condensed. **Today only the items marked `(exists)` are present**; everything else is created by the work package named in the [ownership map](#work-packages-and-ownership). Template files marked `(delete)` are removed by WP4.

```
ProxyHealth/
  README.md                          (exists) this file
  CLAUDE.md                          (exists) agent rules: toolchain, no installs in parallel, write scopes, zero-key rule
  .gitignore                         (exists) node_modules, .expo, dist, .venv, .env (keeps .env.example); WP8 adds var/
  Makefile                           dev / types / sync / test / smoke / export-web                          (WP8)
  scripts/{dev,smoke,gen-types,ci}.sh                                                                        (WP8)
  .github/workflows/ci.yml           api · mobile · links (weekly) · live-golden (manual/nightly)              (WP8)
  docs/                              the specification set — see the docs table of contents
    DECISIONS.md  API_CONTRACT.md  ARCHITECTURE.md  PRODUCT_SPEC.md           (exist; authoritative)
    AI_PROMPTS.md DOCUMENT_TAXONOMY.md RESOURCE_DB.md COMPLIANCE_PRIVACY.md
    BUILD_PLAN.md DEPLOYMENT.md RUNBOOK.md STORE_LISTING.md DEMO_SCRIPT.md    (planned; owners below)
    research/{gemini,expo,compliance,resources}.md  research/specs/*.md  research/_json/*.json   (exist)

  apps/api/                          Python 3.13 · FastAPI · google-genai 2.25 · in-memory only
    .venv/                           (exists) all dependencies installed — run everything through it
    pyproject.toml  .env.example  openapi.json  Dockerfile
    proxyhealth_api/
      main.py settings.py errors.py middleware.py ratelimit.py logging_.py deps.py
      contracts/                     Pydantic = the API contract: enums, common, errors, config, langpack, analysis,
                                     troubleshoot, chat, resources, rules, quicksheet, feedback, demo, admin, model_out
      ai/                            provider.py (Protocol) · gemini.py · mock.py · recording.py · keypool.py · failover.py ·
                                     routing.py · schema_guard.py · prompts/*.md · prompt_loader.py
      analysis/                      pipeline · uploads · redaction · pdf_pages · transcript · verify · contacts_filter ·
                                     deadline_rules · urgency · scam · emergency · phrasing · injection · clerk · fixed_notices ·
                                     disclaimers · tagging · troubleshoot_pipeline · chat_pipeline
      packs/                         base · resolve · generator · qa · cache
      resources/                     loader · matcher · checklist · rules_repo
      quicksheet/                    render (reportlab + arabic_reshaper + python-bidi) · fonts
      demo/                          fixtures · phash
      feedback/                      store (sqlite counters)
      routers/                       health config langpacks analyze troubleshoot chat resources rules quicksheet feedback demo admin
    data/
      langpacks/en.json              CANONICAL base pack (flat keys; includes "langpack.adapting")
      langpacks/<tag>.json           bundled Tier 1+2 packs (machine_translated: true)   languages.yaml
      resources/*.yaml               national_* + regional/va_nova.yaml (vetted, verified_on)
      rules/{deadlines,prepare,fixed_notices,clerk_needs}.yaml
      safety/{phrasing,emergency,scam,injection}.yaml
      fixtures/<id>/{manifest.yaml,page-1.png,transcript.txt,out.<lang>.json}   17 papers + 1 screenshot
      fonts/                         (exists) static Noto TTFs, Regular + Bold, nine families + OFL.txt (reportlab)
    scripts/                         export_openapi gen_packs sync_to_mobile check_links eval_golden spike_schema make_fixtures smoke
    tests/{conftest.py,unit,contract,golden,live}
    var/                             git-ignored runtime state: keypool.json, langpacks/, feedback_counts.sqlite

  apps/mobile/                       Expo SDK 57 · RN 0.86 · React 19 · TS 6 · Expo Router in src/app/
    app.json                         (exists → replace) name "ProxyHealth AI", slug/scheme "proxyhealth", ids, plugins, permissions
    eas.json                         development / preview / production + submit                                 (WP4)
    package.json tsconfig.json       (exist) gen:types script changed to read ../api/openapi.json
    AGENTS.md CLAUDE.md              (exist) Expo agent rules — read before touching this app (CLAUDE.md is "@AGENTS.md")
    LICENSE README.md                (exist) MIT notice and README from create-expo-app (template only)
    eslint.config.js expo-env.d.ts   (exist)
    scripts/reset-project.js         (exists → delete) template helper
    assets/images/ assets/expo.icon  (exist) replaced with ProxyHealth artwork by WP8 (same file names); template artwork (delete)
    assets/fonts/Noto*.ttf OFL.txt   (exist) same static Noto files as apps/api/data/fonts, loaded with expo-font
    assets/fixtures/                 synced sample thumbnails + manifest for the offline sample list              (WP7)
    src/
      app/                           ROUTES ONLY
        _layout.tsx                  (exists → replace) root Stack + providers
        index.tsx                    (exists → replace) redirect → onboarding or (tabs)
        explore.tsx                  (exists → delete)
        +not-found.tsx  +html.tsx
        onboarding/{language,adapting,consent}.tsx
        (tabs)/{_layout,index,papers,help,settings}.tsx      JS Tabs: Home · My papers · Get help · Settings
        scan/{capture,review,reading}.tsx
        result/[id]/{index,source,chat,clerk,quicksheet,help}.tsx
        troubleshoot.tsx  reminders.tsx  emergency.tsx  papers/member/[id].tsx
      api/                           schema.d.ts (GENERATED) · types.ts · client.ts · errors.ts · config.ts · offline.ts
      design/                        tokens.ts ("Big Calm") · theme.tsx · components/ (BigButton, Tile, Card, SpeakButton,
                                     UrgencyBanner, ConfidenceChip, Bidi, Crop, Checklist, FeedbackRow, TierBadge, Banner, …)
      i18n/                          packs/*.json (synced) · languages.ts · store.ts · useT.ts · packLoader.ts · direction.ts ·
                                     digits.ts · fonts.ts · readability.md
      storage/                       index.ts (Vault) · vault.native.ts · vault.web.ts · files.* · secure.* · kv.ts · migrations.ts · wipe.ts
      features/                      onboarding scan analysis chat clerk help vault reminders quicksheet troubleshoot speech demo
                                     feedback emergency settings
      lib/                           tts notifications.* ics image pdf network ids dates platform
      store/                         settings.ts · session.ts (zustand)
      hooks/use-color-scheme*.ts     (exist) kept;   hooks/use-theme.ts  constants/theme.ts  components/*   (exist → delete)
      global.css                     (exists) minimal web resets; add :root[dir=rtl] helpers
      __tests__/                     smoke.test.tsx (exists) + i18n, bidi, storage, result-cards, urgency-banner, reminders,
                                     quicksheet, api-client, consent tests
```

---

## API at a glance

Base URL `EXPO_PUBLIC_API_URL` (dev `http://127.0.0.1:8000`); versioned routes under `/v1`, `/health` unversioned; every body is `application/json` except the PDF and PNG responses; binary inputs are base64 strings inside JSON (no multipart, D-21). Every response carries `X-Request-Id`, `X-Contract-Version: 1` and `X-Data-Use-Tier`. Field-by-field definitions, enums and JSON examples: [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md).

| Method | Path | Model tier | Gate | Purpose |
|---|---|---|---|---|
| GET | `/health` | none | — | Liveness: `status`, `provider`, `keys_configured`, `keys_healthy`, `data_use_tier`, `resources_loaded` |
| GET | `/v1/config` | none | — | `ServerConfig`: provider, `data_use_tier`, `models`, `features.real_documents_allowed`, `limits`, `consent_version`, `privacy_policy_url`, `base_pack_version`, `languages`, versions, `key_slots` counts |
| GET | `/v1/language-packs/{tag}` | none | — | Bundled/cached `LanguagePack` with `ETag`/`304`; `409 pack_version_mismatch`; `404` if not generated |
| POST | `/v1/language-packs` | **fast** (minimal thinking) | — | Resolve a typed language and generate a pack in 60-key chunks; cached, single-flight |
| POST | `/v1/analyze` | **pro** (high ≤ 8 pages, medium 9–12; degraded → fast) | `X-Consent-Version`; 403 on unpaid/mixed without `demo_sample_id` | `AnalyzeRequest` (1–12 base64 images or one PDF, masks, `target_language`, `state`/`zip3`, `preferences`, `demo_sample_id`) → `AnalysisResult` |
| POST | `/v1/troubleshoot` | **pro** (medium thinking) | as analyze | Screenshot + `user_goal` + `mode portal\|scam_check` → `TroubleshootResult` |
| POST | `/v1/chat` | **fast** (low thinking) | as analyze | Stateless: `AnalysisContext` + ≤ 8 messages + `question` → `ChatAnswer` with `refusal_kind`, `refer_to_professional`, grounded quotes |
| POST | `/v1/resources/match` | none | — | Tags × state/county/zip3 × language (+ institutions, `scam_risk`, `emergency`) → scored `ResourceMatch` list, prep checklist, `national_fallbacks` |
| GET | `/v1/resources`, `/v1/resources/{id}` | none | — | Browse/search vetted resources; one `Resource` |
| GET | `/v1/rules` | none | — | Deadline rules table with `source_url`, `verification`, `valid_until` |
| POST | `/v1/quicksheet/pdf` | none | — | `QuickSheetRequest` → text-only `application/pdf` (reportlab, Noto fonts); nothing stored |
| POST | `/v1/feedback` | none | — | "Was this clear?" `kind` + enums → counters only, no content |
| GET | `/v1/demo/fixtures`, `/v1/demo/fixtures/{id}/pages/{n}` | none | — | Sample papers list; sample page PNG (watermarked SAMPLE) |
| GET | `/v1/admin/keys` | none | `X-Admin-Token` (mounted only when `ADMIN_TOKEN` is set) | Per-slot, per-tier key-pool state with `project` label and `key_last4` |

Error envelope `{"error": {code, message, user_message_key, retry_after_seconds, key_exhausted, request_id, details}}` with codes `invalid_request` `too_many_pages` `pdf_too_long` (400) · `unauthorized` (401) · `unpaid_tier_real_documents_disabled` (403) · `not_found` (404) · `pack_version_mismatch` (409) · `payload_too_large` (413) · `unsupported_media_type` (415) · `content_blocked` `language_unresolved` (422) · `consent_required` (428) · `rate_limited` `quota_exhausted` (429) · `internal` (500) · `model_output_invalid` (502) · `provider_not_configured` `upstream_unavailable` (503). An unreadable page is a `200` with `quality.readable=false`, not an error.

---

## Docs table of contents

Read in this order: `CLAUDE.md` → DECISIONS → API_CONTRACT → ARCHITECTURE → your work package's documents.

### Agent rules
| File | What it is |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Repo-root agent notes: toolchain facts verified on this Mac, hard rules for parallel work, mobile tooling facts. |
| [`apps/mobile/AGENTS.md`](apps/mobile/AGENTS.md) | Expo agent rules (verify against `https://docs.expo.dev/versions/v57.0.0/`, never memory). [`apps/mobile/CLAUDE.md`](apps/mobile/CLAUDE.md) just includes it. |

### Specification set (`docs/`)
| File | Status | Owner | Contents |
|---|---|---|---|
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | **authoritative** | architect | Product stance; D-01…D-31 (tier gate, consent, models, SDK surface, structured output, key pool, anti-hallucination, information-not-advice, caps, storage, language packs, navigation, design system, demo, process, feedback); rejected items; open questions Q1–Q11; brand tagline; §14 append-only change log. |
| [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) | **authoritative** | WP0 | Conventions, headers, error envelope, every enum, every request/response model field by field with JSON examples, model-output schemas, OpenAPI/TS generation. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | **authoritative** | architect | System overview, full `apps/api` and `apps/mobile` trees with one-line purposes, module internals, ownership map, dev scripts, CI, deployment, `app.json`/`eas.json`, environment variables, invariants. |
| [`docs/PRODUCT_SPEC.md`](docs/PRODUCT_SPEC.md) | **authoritative** for product behaviour, screens and copy (2026-09-27) | architect | Thesis and design target, personas, step-by-step journeys J-A…J-J, MUST/SHOULD/LATER feature inventory, screen-by-screen UX, copy; where it and the backbone disagree, the backbone wins and the disagreement is listed in its §16.2. |
| [`docs/AI_PROMPTS.md`](docs/AI_PROMPTS.md) | planned | WP2 | The actual system-prompt text (`ai/prompts/*.md`), prompt-loader placeholders, model-output schema rationale. |
| [`docs/DOCUMENT_TAXONOMY.md`](docs/DOCUMENT_TAXONOMY.md) | planned | WP2 | Per `DocumentType`: fields to extract, action/deadline, pitfalls, fixed notices, prepare items. |
| [`docs/RESOURCE_DB.md`](docs/RESOURCE_DB.md) | planned | WP3 | YAML schema, seed entries, matcher scoring, link-health runbook, 90-day re-verification cadence. |
| [`docs/COMPLIANCE_PRIVACY.md`](docs/COMPLIANCE_PRIVACY.md) | planned | WP8 | Per-tier privacy matrix, the approved `privacy_claims` list (CI-tested), store declarations, HBNR/UPL posture, retention. |
| [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md) | planned | architect | Work-package table `WP \| Owner scope (exclusive write) \| Reads \| Definition of done`, sequencing, day-0 stubs. |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | planned | WP8 | Cloud Run / EAS Hosting / EAS Build procedures, secrets, alerts, the permanent mock demo instance. |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | planned | WP8 | Operations: key rotation, quota exhaustion, link-checker failures, incident response. |
| [`docs/STORE_LISTING.md`](docs/STORE_LISTING.md) | planned | WP8 | Titles, descriptions, categories, age rating, privacy label / Data safety answers per tier, Notes for Review. |
| [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) | planned | WP7 | The three-minute zero-key demo and the keyed fixtures-only variant. |

### Research (`docs/research/`) — the decisions rest on these; do not re-derive
| File | Contents |
|---|---|
| [`docs/research/gemini.md`](docs/research/gemini.md) | Current model IDs and shutdown dates, thinking levels, free vs paid data-use terms (verbatim), SDK surfaces and exception hierarchies, limits and MIME types, TTS, warnings for builders, key facts with sources. |
| [`docs/research/expo.md`](docs/research/expo.md) | SDK 57 facts, per-package platform support and web gaps, Expo Router, EAS Build/Submit/Hosting, Expo Go status, accessibility, testing. |
| [`docs/research/compliance.md`](docs/research/compliance.md) | Apple/Play rules and the declaration checklist, HIPAA vs the FTC Health Breach Notification Rule, UPL and medical-disclaimer norms, Gemini terms, accessibility baseline, language needs, LLM safety patterns. |
| [`docs/research/resources.md`](docs/research/resources.md) | Verified national and Northern Virginia resource seed, document-type taxonomy with pitfalls, scam patterns, the "never hardcode eviction periods" warning. |
| [`docs/research/specs/user-first.md`](docs/research/specs/user-first.md) | **Winning candidate spec** (base for the decisions): personas, journeys, features, screens, AI layer, resources, privacy, accessibility, layout, testing, deployment. |
| [`docs/research/specs/risk-first.md`](docs/research/specs/risk-first.md) | Candidate spec grafted for per-key billing attestation, the deterministic safety pipeline, fixed notices, the manual test matrix. |
| [`docs/research/specs/builder-first.md`](docs/research/specs/builder-first.md) | Candidate spec grafted for the 403 tier gate, the OpenAPI snapshot test, the matcher diversity cap, the smoke script, the Makefile shape. |
| [`docs/research/_json/research-gemini.json`](docs/research/_json/research-gemini.json) · [`research-expo.json`](docs/research/_json/research-expo.json) · [`research-compliance.json`](docs/research/_json/research-compliance.json) · [`research-resources.json`](docs/research/_json/research-resources.json) | Machine-readable versions of the four research files (same facts, sources and confidence levels). |

---

## Roadmap to the app stores (EAS)

Local constraints: no Xcode (no `npx expo run:ios`, no simulator), no Homebrew. iOS binaries are compiled on Expo's macOS cloud runners; EAS Submit works from this Mac. Free EAS plan: 15 iOS + 15 Android builds per month, low-priority queue, 45-minute timeout — budget builds. External prerequisites: Apple Developer Program under an **organization** legal entity (Apple 5.1.1(ix), sensitive data) and a Google Play Developer account — open question Q2 in [`docs/DECISIONS.md`](docs/DECISIONS.md) §12.

| Phase | Deliverable | Gate to pass |
|---|---|---|
| **0 · Contract & tokens** (WP0, first) | `contracts/**`, `openapi.json`, `schema.d.ts`, `tokens.ts`, `en.json`, `languages.yaml`, `AIProvider` Protocol, hour-one `MockProvider` | `export_openapi.py` runs; `npm run gen:types` from the file; snapshot test; `schema_guard` passes; MockProvider returns a valid `AnalysisModelOut` for any input |
| **1 · Zero-key end to end** (WP1–WP7 in parallel) | API in mock mode + web app + every screen; 17 fixtures × en/es/prs/ar goldens; `make dev`, `make smoke` | `make test` green; golden set passes every validator; the three-minute demo runs offline |
| **2 · Live Gemini, fixtures only** | `AI_PROVIDER=gemini` with billed keys from distinct projects; `scripts/spike_schema.py` result pinned in `.env.example`; `RUN_LIVE=1` golden precision/recall baseline | No invented contact; precision not below baseline; 429/503/422 paths exercised by pulling a key |
| **3 · Android development build** | `npx eas-cli@latest build:configure` → `npx eas-cli@latest build --profile development --platform android` with `app.json` rewritten: `name "ProxyHealth AI"`, `slug`/`scheme "proxyhealth"`, `android.package "org.proxyhealth.app"`, `allowBackup: false`, `blockedPermissions` READ_MEDIA_IMAGES / READ_MEDIA_VIDEO / RECORD_AUDIO, camera / image-picker / localization (`supportsRTL`) / notifications (channel "dates", icon, color `#1F5F8B`) / document-picker / font plugins with the final permission strings | Permission strings, the "Dates to remember" channel, the RTL restart prompt, SecureStore and SQLite verified on a real mid-range Android at 200 % font, Dari RTL, TalkBack |
| **4 · iOS development build** | `eas build --profile development --platform ios` once the organization Apple account exists (`ios.bundleIdentifier "org.proxyhealth.app"` pending Q4, `supportsTablet: true`, `privacyManifests` UserDefaults `CA92.1` / FileTimestamp `C617.1` / SystemBootTime `35F9.1`, `infoPlist` camera and photo strings mirroring the plugins) | VoiceOver full flow; iOS AX5 text size; verify `["expo-sqlite", {"useSQLCipher": true}]` and vault-directory backup exclusion — **only then** may copy claim them (D-22) |
| **5 · Hardening** | SDK 58 upgrade (`npx expo install expo@^58.0.0 --fix`; `File.write` becomes async; iOS RTL follows `I18nManager`); privacy-claims CI; readability CI; counsel review of UPL and medical framing, the HBNR memo and the privacy policy (Q3); named reviewers for Dari / Pashto / Arabic / Spanish / Amharic packs and emergency lexicons (Q6) | `tests/unit/test_privacy_claims.py` and `test_readability.py` green; store copy matches implementation literally |
| **6 · Store preparation** (WP8) | [`docs/STORE_LISTING.md`](docs/STORE_LISTING.md): title "ProxyHealth AI: Your paper, explained", subtitle "Understand letters, bills and notices in your language", category Reference (iOS) / Tools (Android) — deliberately not Medical; age 18+; "Medical or wellness topics" yes; Play Health apps declaration (not a medical device; consult-a-professional reminder in-app); Apple privacy label and Play Data safety answered per tier; Notes for Review (demo mode, sample papers, no login, where the disclaimers and the flag control live); public HTML privacy policy at `PRIVACY_POLICY_URL`; screenshots from fixtures only; permission-string translations in `locales/<tag>.json` | The declaration checklist in [`docs/research/compliance.md`](docs/research/compliance.md) §1 fully ticked; all keys `billing:true` in production; camera plus system photo picker only (no READ_MEDIA permission) |
| **7 · Production builds and submission** | `npx eas-cli@latest build --platform all --profile production` (`autoIncrement`, `appVersionSource: remote`) → `npx eas-cli@latest submit --platform ios` (`ascAppId`, `appleTeamId`) and `--platform android` (service-account JSON, `track: internal` first; complete the listing by hand); web: `npx expo export --platform web` → `npx eas-cli@latest deploy --prod` on EAS Hosting (`https://proxyhealth.expo.app`, or a custom domain per Q4) with the web origin added to `CORS_ORIGINS` | API on Google Cloud Run in the same Google account as the billed Gemini project (1 vCPU / 1 GiB, request timeout 120 s, concurrency 32, secrets `GEMINI_KEYS` / `INSTALL_HASH_SECRET` / `ADMIN_TOKEN` from Secret Manager, no persistent disk) plus a separate permanent `AI_PROVIDER=mock` demo instance; alert on `keys_healthy == 0` for 5 min |

`eas.json` shape (from [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §5.3):

```json
{ "cli": { "appVersionSource": "remote" },
  "build": {
    "development": { "developmentClient": true, "distribution": "internal", "env": { "EXPO_PUBLIC_API_URL": "https://<demo-or-staging-api>" } },
    "preview":     { "distribution": "internal", "env": { "EXPO_PUBLIC_API_URL": "https://<staging-api>" } },
    "production":  { "autoIncrement": true, "env": { "EXPO_PUBLIC_API_URL": "https://<prod-api>" } } },
  "submit": { "production": { "ios": { "ascAppId": "<from App Store Connect>", "appleTeamId": "<team>" },
                              "android": { "serviceAccountKeyPath": "./google-service-account.json", "track": "internal" } } } }
```

Final English permission strings (packs translate them): camera — "ProxyHealth AI uses the camera only to photograph the paper you want explained. Photos are not saved on our servers."; photos — "ProxyHealth AI lets you choose a photo of a paper to explain. We do not access your other photos."; notifications — "ProxyHealth AI reminds you about dates it found on your papers. Reminder text is generic unless you choose otherwise."

Remember: permission strings, `ios.privacyManifests` and `ios.infoPlist` are baked into the binary, so changing them means a new EAS build and a new store submission, not an OTA update. Never create or edit `apps/mobile/ios/` or `apps/mobile/android/`; native configuration lives in `app.json` and config plugins.

---

## Contributing and testing

### Hard rules (from [`CLAUDE.md`](CLAUDE.md); they exist so nine agents can work at once)

1. **Never run `npm install`, `npx expo install` or `pip install` unless you are the only agent running.** Everything needed is installed; if something is truly missing, stop and report it.
2. **Write only files your work package owns** (table below and [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md)). Shared files — contract models, generated TS types, design tokens, `en.json`, `languages.yaml`, `ai/provider.py` — belong to WP0: read them, don't edit them.
3. **Never create or edit `apps/mobile/ios/` or `apps/mobile/android/`.** Native config goes in `app.json` and config plugins.
4. **Never persist user documents or images server-side, never log document content, never let the model invent phone numbers or URLs** (resources come only from the vetted YAML DB).
5. **Secrets only via `.env`** (git-ignored); commit `.env.example`.
6. **The whole app must run with ZERO API keys** (`AI_PROVIDER=mock`). Every feature needs a mock-provider path.

### Work packages and ownership

Exclusive write scopes; the full table with "Reads" and "Definition of done" is [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §4 and expands into [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md). Cross-WP needs are filed as one line in [`docs/DECISIONS.md`](docs/DECISIONS.md) §14 "Change log" (append-only) and resolved by WP0.

| WP | Owns (exclusive write) | Done when |
|---|---|---|
| **WP0** Contract & tokens (first) | `contracts/**`, `openapi.json`, `scripts/export_openapi.py`, `src/api/schema.d.ts`, `src/api/types.ts`, `src/design/tokens.ts`, `data/langpacks/en.json`, `data/languages.yaml`, `ai/provider.py`, hour-one `ai/mock.py`, `docs/API_CONTRACT.md` | export + gen:types + snapshot test + schema_guard pass; MockProvider returns a valid `AnalysisModelOut` for any input |
| **WP1** API core + AI | `main.py settings.py errors.py middleware.py ratelimit.py logging_.py deps.py`, `ai/**` (except `provider.py`/`mock.py`), `packs/**`, `routers/{health,config,langpacks,admin}.py`, `Dockerfile`, `.env.example`, `pyproject.toml` | keypool tests (429 rotation, Retry-After, RPD detection, persistence, distinct projects); tier-gate 403 + consent 428 tests; `/health` and `/v1/config` correct per tier; pack cache/ETag tests |
| **WP2** Analysis pipelines + safety | `analysis/**`, `routers/{analyze,troubleshoot,chat}.py`, `data/rules/**`, `data/safety/**`, `ai/prompts/**`, `ai/prompt_loader.py`, `docs/AI_PROMPTS.md`, `docs/DOCUMENT_TAXONOMY.md` | validator unit tests; pipeline tests against mock; urgency / deadline / scam / emergency / phrasing / injection / redaction tests |
| **WP3** Resources & quick sheet | `resources/**`, `quicksheet/**`, `routers/{resources,rules,quicksheet}.py`, `data/resources/**`, `data/fonts/**`, `scripts/check_links.py`, `docs/RESOURCE_DB.md` | YAML validates at boot; ≥ 70 entries with verified URLs; matcher tests; PDF renders RTL fixtures |
| **WP4** Mobile foundation | `src/app/_layout.tsx`, `src/app/index.tsx`, `src/app/(tabs)/_layout.tsx`, `src/app/onboarding/**`, `src/app/(tabs)/settings.tsx`, `src/design/theme.tsx`, `src/design/components/**`, `src/i18n/**` (except `packs/en.json`), `src/storage/**`, `src/api/{client,errors,config,offline}.ts`, `src/lib/{network,ids,platform,tts}.ts`, `src/store/**`, `app.json`, `eas.json`, template deletions | tsc + jest + lint + web export green; RTL flip on web and native; consent tier badge; storage adapter tests on both platforms |
| **WP5** Scan → Result → Chat → Clerk | `src/app/scan/**`, `src/app/result/**`, `src/app/emergency.tsx`, `src/features/{scan,analysis,chat,clerk,speech,feedback,emergency}/**`, `src/lib/{image,pdf,dates}.ts` | full flow with the mock API on web and a dev build; cards / Bidi / crop tests; a11y labels |
| **WP6** Vault, Help, Reminders, Quick sheet, Troubleshoot | `src/app/(tabs)/{index,papers,help}.tsx`, `src/app/papers/**`, `src/app/reminders.tsx`, `src/app/troubleshoot.tsx`, `src/features/{vault,help,reminders,quicksheet,troubleshoot,demo,settings}/**`, `src/lib/{notifications.*,ics}.ts` | opt-in save + members + wipe; reminders native + .ics web; quick sheet share / print / server PDF; troubleshoot modes |
| **WP7** Fixtures, mock, demo | `data/fixtures/**`, `scripts/{make_fixtures,sync_to_mobile}.py`, `ai/mock.py` (after hour one), `ai/recording.py`, `demo/**`, `routers/demo.py`, `feedback/**`, `routers/feedback.py`, `tests/golden/**`, `apps/mobile/assets/fixtures/**`, `docs/DEMO_SCRIPT.md` | 17 fixtures × 4 languages; goldens pass every validator; dHash match works; demo runs offline |
| **WP8** DevOps, CI, store | `Makefile`, `scripts/{dev,smoke,gen-types,ci}.sh`, `.github/workflows/ci.yml`, `apps/mobile/assets/images/**`, `docs/{DEPLOYMENT,RUNBOOK,STORE_LISTING,COMPLIANCE_PRIVACY}.md`, `.gitignore` (add `var/`, `.env`, `dist/`) | `make dev` boots API + web; CI runs pytest, tsc, jest, lint, contract diff, YAML validation, pack sync check, readability, web export |

### Testing

```sh
# API — unit, contract (httpx.AsyncClient against create_app() with the mock provider), golden (fixtures × languages)
apps/api/.venv/bin/pytest apps/api
apps/api/.venv/bin/ruff check apps/api && apps/api/.venv/bin/mypy apps/api

# API — live golden gate (only with billed keys; a prompt or model change that lowers precision or invents a contact fails)
RUN_LIVE=1 apps/api/.venv/bin/pytest apps/api/tests/live

# Contract drift — regenerate, then the snapshot test must pass and the TS types must be regenerated
apps/api/.venv/bin/python apps/api/scripts/export_openapi.py
(cd apps/mobile && npm run gen:types)

# Data sync — bundled packs / languages / fixture thumbnails in the app must equal the API copies
apps/api/.venv/bin/python apps/api/scripts/sync_to_mobile.py --check

# Mobile
export PATH="$HOME/.local/node/bin:$PATH"
cd apps/mobile
npx expo customize tsconfig.json   # CI only: generates expo-env.d.ts for typed routes
npx tsc --noEmit && npx jest && npx expo lint && npx expo export --platform web
```

Test layout: `apps/api/tests/unit` (pure functions: keypool, failover, routing, schema_guard, verify, contacts_filter, deadline_rules, urgency, scam, emergency, phrasing, injection, clerk, redaction, uploads, packs QA/cache, resolve, matcher, loader, checklist, quicksheet, feedback_store, privacy_claims, readability) · `tests/contract` (every endpoint, error envelope, MIME/size rejections, 428, 403 gate, 429 shape, OpenAPI snapshot) · `tests/golden` (mock output equals `out.<lang>.json` and passes every validator; urgency and date kinds asserted) · `tests/live` (gated by `RUN_LIVE=1`). Mobile: `apps/mobile/src/__tests__/` (smoke, i18n, bidi, storage native/web, result-cards from the RFE golden in LTR and RTL at 200 % font scale, urgency-banner, reminders, quicksheet, api-client, consent). `conftest.py` boots the app with `AI_PROVIDER=mock`, a temporary `VAR_DIR` and a frozen clock.

**CI** (`.github/workflows/ci.yml`): **api** (ruff, mypy, pytest including snapshot / golden / privacy-claims / readability, YAML validation, `sync_to_mobile.py --check`) · **mobile** (`npm ci --legacy-peer-deps`, `npx expo customize tsconfig.json`, `npx tsc --noEmit`, `npx jest`, `npx expo lint`, `npx expo export --platform web`) · **links** (weekly cron: `check_links.py`, opens an issue on `broken`) · **live-golden** (manual/nightly with secrets: `RUN_LIVE=1 pytest tests/live`).

**Manual matrix before any store submission:** a mid-range Android at 200 % font, Dari RTL and TalkBack; an iPhone with VoiceOver and AX5 text size; Chrome and Safari on web (picker-inside-gesture constraints); an airplane-mode walk-through; RTL development builds in Arabic and Urdu.

### Invariants every change must keep ([`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §7)

1. No user document, image, transcript or model prose is written to disk or logs on the server; `var/` holds only key-pool state, packs and feedback counters.
2. `unpaid`/`mixed` tiers cannot analyze real documents (403) — enforced in middleware, tested in `tests/contract/test_errors.py`.
3. Every fact shown carries `source_quote` + `span_ids` + `confidence` + `verified`; unverified facts never drive urgency or reminders.
4. Contacts and organization names come only from the paper or `data/resources/*.yaml`.
5. Dates are computed only by `deadline_rules.py` from a printed relative phrase + a verified anchor + a cited rule; printed dates win.
6. Model IDs come from `MODEL_PRO`/`MODEL_FAST`; never `-latest`, never 1.5/2.0/2.5; never `temperature`; never `minimal` on 3.8.
7. Every device feature has a `Platform.OS === 'web'` path (`.web.ts` file or branch); pickers on web run inside the gesture handler.
8. Nothing is installed (`npm install`, `npx expo install`, `pip install`) while agents run in parallel; missing packages are reported, not added.
9. Copy: 4th-grade level, no dramatizing, no emoji in controls, 56/72 pt targets, icon + word + color for urgency, speaker button after every paragraph, machine-translation banner on every `machine_translated` pack.
10. Privacy sentences in UI and store listings must be literally true per tier (CI `test_privacy_claims.py`).

### How to propose a change

- The docs are the contract. If code must diverge from `docs/DECISIONS.md`, `docs/API_CONTRACT.md` or `docs/ARCHITECTURE.md`, fix one and **say which in the PR note**.
- Contract changes go through WP0: change the Pydantic model → `export_openapi.py` → `npm run gen:types` → update `docs/API_CONTRACT.md` → commit all four together (the snapshot test enforces the first two).
- Cross-package needs are one appended line in `docs/DECISIONS.md` §14 "Change log" (for example the 2026-09-27 entries adding `arabic-reshaper` / `python-bidi` and the pre-downloaded Noto fonts), resolved by WP0.
- New privacy or accuracy sentences in `en.json` must be added to the approved `privacy_claims` list in `docs/COMPLIANCE_PRIVACY.md` and reviewed against the implementation before the CI test accepts them.
- Bundled pack regeneration (`gen_packs.py`) and any `npm`/`pip` install happen only in a WP0-owned window when no other agent is running.
- Commit messages end with the attribution line given in the session; the repository has no commits yet, so the first commit lands on `main`.

---

## Open questions and license

Eleven questions only the user can answer are listed in [`docs/DECISIONS.md`](docs/DECISIONS.md) §12: billing owner and number of distinct Cloud projects (Q1), store developer accounts (Q2), counsel review (Q3), bundle identifier / web hostname / privacy-policy host (Q4), pilot geography beyond Northern Virginia (Q5), language reviewers (Q6), in-session Spanish review (Q7), per-device budget (Q8), web positioning (Q9), Interactions API timing (Q10), hosting (Q11). Until Q1 is answered, keyed runs are fixtures only.

**License:** not yet chosen (open item for the user). `apps/mobile/LICENSE` is the MIT notice that ships with Expo's `create-expo-app` template and covers only that template code; the Noto fonts in `apps/api/data/fonts/` and `apps/mobile/assets/fonts/` are under the SIL Open Font License (`OFL.txt` beside them).

---

*ProxyHealth AI explains what your paper says. It is not legal, medical, housing or benefits advice, and it is not a medical device. Only a licensed professional — a lawyer or DOJ-accredited representative, your doctor, nurse or pharmacist, a housing counselor, or the office that sent the paper — can tell you what it means for you.*
