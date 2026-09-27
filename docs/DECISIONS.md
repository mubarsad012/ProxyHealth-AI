# ProxyHealth AI — Architecture Decisions (backbone document)

Status: **authoritative**. Written 2026-09-24 by the lead architect after three judges scored the three candidate specs in `docs/research/specs/` (base = `user-first.md`, grafts from `risk-first.md` and `builder-first.md`). Every other document in `docs/` and every coding agent must conform to this file, `docs/API_CONTRACT.md` and `docs/ARCHITECTURE.md`. When code and these docs disagree, fix one and say which in a PR note.

Research these decisions rest on (do not re-derive): `docs/research/gemini.md`, `docs/research/expo.md`, `docs/research/compliance.md`, `docs/research/resources.md`. Fixed project givens (not relitigated here): monorepo at `/Users/sadiqmubarak/Desktop/ProxyHealth`; `apps/mobile` = Expo SDK 57 / RN 0.86 / React 19 / TS 6 / Expo Router in `src/app/`; `apps/api` = Python 3.13 FastAPI + `google-genai` 2.25; Pydantic models are the API contract; TypeScript types generated from `/openapi.json`; user documents never persist server-side; whole app runs with zero API keys via the mock provider; name "ProxyHealth AI"; ship iOS/Android/web from one codebase; store builds via EAS; no Xcode on the dev Mac.

Conventions in this file: **D-nn** = a decision. Each has *Decision*, *Rationale*, and where useful *Consequences*. "MUST/SHOULD/LATER" follow the feature tiers in `docs/PRODUCT_SPEC.md` (to be written from these decisions).

---

## 0. Product stance (one paragraph, binding)

ProxyHealth AI is a *paper decoder with a caseworker's manners*, not a chatbot and not a legal or medical adviser. It transcribes, translates, explains (three cards: *What is this?* / *What is it asking for?* / *Your step-by-step plan*), anchors every fact to the exact words on the page, hands the user a "Show the clerk" card, routes only to humans we verified, keeps every family member's papers in an on-device vault, and refuses to invent a date, a phone number or an outcome. Design target: a stressed adult reading at a 4th-grade level in their own language, on a cracked mid-range Android with two bars of data, possibly reading right-to-left, possibly handing the phone to a 12-year-old to interpret. The app is rated 18+ (Gemini terms) and is directed at adults; copy must never dramatize ("You may be deported") and must always offer to be *heard* privately (earbuds) rather than read through a child.

---

## 1. Gemini data-use tier (research finding #1)

### D-01 The data-use tier is computed server-side from operator-attested per-key billing flags and enforced in the API, not just shown in a banner

**Decision.**
- Keys are configured as `GEMINI_KEYS` = JSON list of `{"key": "...", "project": "<label>", "billing": true|false}`. There is no comma-separated key list. `GEMINI_BILLING_ATTACHED` is *not* a separate global flag; the per-key `billing` field is the single source of truth (the SDK cannot detect billing, so this is an operator attestation and `.env.example` says so).
- Startup validation (`ai/keypool.py`): `project` labels must be distinct (rate limits are per project, not per key — same-project keys add nothing and hide quota exhaustion); duplicates abort boot with a clear message. Model IDs are validated (D-04). In `ENV=production` the server refuses to boot if any slot has `billing=false` unless `ALLOW_UNPAID_KEYS=1`.
- `data_use_tier` (enum `DataUseTier`): `paid` if provider is gemini and every slot has `billing=true`; `unpaid` if any slot has `billing=false` (a `mixed` pool is *reported* as `mixed` but *routed* as `unpaid`); `demo` when `AI_PROVIDER=mock`; `none` when `AI_PROVIDER=gemini` and zero slots are configured (boot fails unless `ENV=development`).
- Exposed in `GET /v1/config` (`data_use_tier`, `features.real_documents_allowed`) and echoed on every response as header `X-Data-Use-Tier`.
- **Hard gate:** when the tier is `unpaid` or `mixed`, `POST /v1/analyze`, `POST /v1/troubleshoot` and `POST /v1/chat` return `403 unpaid_tier_real_documents_disabled` unless the request carries a `demo_sample_id` **or** `ALLOW_UNPAID_REAL_DOCUMENTS=true`. That flag is refused (boot error) when `ENV=production`. When `demo_sample_id` is set, the server loads the fixture bytes *from disk* and ignores any client-supplied pages, so a real photo can never ride along on a demo request that reaches an unpaid key.
- `mixed` pools additionally log a warning per request naming the unbilled slot; the key pool never prefers an unbilled slot when a billed one is available.
- Mock is **never** a silent fallback for a real request (quota exhaustion returns 429; the *client* offers "Try a sample" explicitly).

**Rationale.** Gemini API terms (effective 2026-03-23): unpaid-quota prompts, files and responses are used to improve Google products with human review, and Google says "Do not submit sensitive, confidential, or personal information to the Unpaid Services." A banner alone (user-first) leaves a misconfigured deployment able to upload real documents; the judges unanimously required a server block (builder-first's 403) combined with risk-first's per-key billing attestation and boot refusal. EEA/Switzerland/UK clients may only use Paid Services (D-03).

**Consequences.** Store privacy answers ("Data Not Collected" for document content) are defensible only on `paid`; `docs/COMPLIANCE_PRIVACY.md` must carry the per-tier matrix. Hackathon demos with free keys use fixtures only (D-02).

### D-02 Consent screen S2 shows a tier badge, an 18+ line, a "Not now" path, and copy that is literally true per tier

**Decision.** S2 ("What happens to your paper") renders three pictogram lines plus a tier badge fetched from `GET /v1/config`, then a "Read more" link. Copy (English base strings; every other language is a pack translation):
- Line 1 (all tiers): "Your photo is sent to Google's AI (Gemini) to be read. Our server does not keep it."
- Line 2 by tier: **paid** — "Google does not use your paper to improve its products. Google keeps a short safety log for a limited time, then deletes it." **unpaid/mixed** (red, icon + word) — "This test build uses a free AI key. Google may read and use what is sent. Do not send real papers. Sample papers only." **demo** — "Sample mode. No AI service is contacted. Nothing leaves this device." **unknown** (API unreachable) — "I cannot confirm how your paper would be handled right now. You can try a sample paper or come back later." Scan is disabled on unknown; samples stay enabled.
- Line 3: "Papers you save stay only on this phone. You can delete everything any time." (On web the line reads "...stay only in this browser, if you choose to keep them.")
- 18+ line: "This app is for adults 18 and older."
- Buttons: primary "I understand, continue" (72 pt); secondary "Not now" → Home with scan tiles disabled and a one-line explanation; link "Try a sample paper first" (no consent needed; nothing of the user's leaves the device).
- Consent record stored on device: `{consent_version, accepted_at, tier_seen, platform}`; re-shown when `consent_version` from `/v1/config` changes or the tier changes from what was seen. Withdrawing consent (Settings) disables uploads and offers wipe.
- The API requires header `X-Consent-Version` on `/v1/analyze`, `/v1/troubleshoot`, `/v1/chat`; missing or stale → `428 consent_required`. Demo-fixture requests are exempt.
- The old S2 sentence "It is not saved on our computers" is replaced by the tier-specific lines above. A CI test (`tests/unit/test_privacy_claims.py` reading `docs/COMPLIANCE_PRIVACY.md` §"privacy_claims") asserts every privacy sentence key in `en.json` matches an approved list that was reviewed against implementation (FTC §5 literal truth).

**Rationale.** Apple 5.1.2(i) requires disclosure and explicit permission before sharing personal data with third-party AI; Google Play requires prominent disclosure; the Gemini paid tier still logs prompts "for a limited period of time, solely for detecting and preventing violations", so "Google never sees it" would be false. The judges required the badge, the 18+ line, the "Not now" path, `tier_seen`, and the 428 enforcement.

### D-03 Region rule: EEA/Switzerland/UK deployments require paid keys; the app is US-scoped in v1

**Decision.** `.env.example` and `docs/ARCHITECTURE.md` deployment section carry the note: "If any users are in the EEA, Switzerland or the UK, every key must be `billing:true`; `ALLOW_UNPAID_KEYS` must be unset." v1 does not geolocate users; the resource DB, rules and store listings are US-only, and the store listing is published in the US storefronts only. LATER: an `EXPO_PUBLIC_REGION` build flag if non-US storefronts are added.

---

## 2. Models, SDK surface, structured output

### D-04 Model IDs are env-configurable with validated defaults: `MODEL_PRO=gemini-3.8-flash`, `MODEL_FAST=gemini-3.5-flash-lite`

**Decision.**
| Tier | Env var | Default | Thinking | Used for |
|---|---|---|---|---|
| reasoning ("pro") | `MODEL_PRO` | `gemini-3.8-flash` | `high` for document analysis ≤ 8 pages; `medium` for 9–12 pages and for screenshot troubleshooting | `/v1/analyze`, `/v1/troubleshoot` |
| fast | `MODEL_FAST` | `gemini-3.5-flash-lite` | `minimal` for language packs, resource tagging, clerk-line translation, phrasing rewrite; `low` for chat | `/v1/language-packs`, `/v1/chat`, internal tagging/rewrites |
| degraded | `MODEL_PRO_DEGRADED_THINKING` | `medium` | applied to `MODEL_FAST` when every pro slot is cooling and `ALLOW_DEGRADED=true` | analyze/troubleshoot only; response `model_meta.quality="degraded"` |

Startup assertion (`settings.py`): reject any model ID containing `gemini-1.5`, `gemini-2.0`, `gemini-2.5`, or ending in `-latest`; reject `gemini-3.1-pro-preview` unless every key is billed (no free tier). `thinking_level="minimal"` is never sent to a model whose ID starts with `gemini-3.8` (returns an error per gemini.md); the router downgrades to `low` and logs. If the API rejects the degraded thinking level, the provider retries once with `low`. Never send `temperature`, `top_p`, `top_k`, `candidate_count`, or `thinking_budget`. `max_output_tokens`: 16384 analysis, 8192 transcript-only call, 4096 troubleshoot, 2048 chat, 4096 per language-pack chunk. Media resolution: `MEDIA_RESOLUTION_HIGH` for photographed pages and screenshots, `MEDIA_RESOLUTION_MEDIUM` for PDFs. Text prompt precedes media parts.

**Rationale.** 1.5 models were shut down 2025-09-29, 2.0 on 2026-06-01, and new projects cannot use 2.5 since 2026-09-18; `-latest` aliases hot-swap with two weeks' notice. The project givens require env-configurable IDs; builder-first's degraded path used `thinking_level="high"` on flash-lite, which the research does not verify, so the degraded level is configurable with a `medium` default and a `low` fallback.

### D-05 v1 uses the legacy `client.aio.models.generate_content`; the Interactions API is a flagged provider for later

**Decision.** `GeminiProvider` calls `client.aio.models.generate_content(model, contents, config=GenerateContentConfig(system_instruction, response_mime_type="application/json", response_schema=<Pydantic class>, thinking_config=ThinkingConfig(thinking_level=..., include_thoughts=False), media_resolution=..., max_output_tokens=...))` and reads `resp.parsed`. One `genai.Client` per key slot with `HttpRetryOptions(attempts=2, initial_delay=1.0, max_delay=4.0)` and `HttpOptions.timeout` set from `UPSTREAM_TIMEOUT_S` (unit verified at implementation time; gemini.md marks it unverified). `GeminiInteractionsProvider` (`AI_PROVIDER=gemini_interactions`) is LATER: `client.aio.interactions.create(..., store=False, response_format={"type":"text","mime_type":"application/json","schema": Model.model_json_schema()})`, parsing `output_text`. The failover engine reads upstream status generically: `getattr(exc, "status_code", None) or getattr(exc, "code", None)`, and catches `Exception` broadly around provider calls, because the Interactions path raises a private exception hierarchy that does not subclass `google.genai.errors.APIError`.

**Rationale.** The legacy path accepts Pydantic classes directly, has one public exception hierarchy (`errors.ClientError/ServerError` with `.code`), and has no server-side storage default to opt out of. Interactions stores everything by default (1 day free / 55 days paid) and requires `store=False`, which disables `previous_interaction_id`; our chat is stateless anyway, so the migration is a configuration change when Google forces it.

### D-06 Structured output: small flat model schemas separate from the API result; auto-selected single-call or two-call analysis

**Decision.**
- Two schema families. **Model output schemas** (`contracts/model_out.py`: `AnalysisModelOut`, `TranscriptOut`, `ExplainOut`, `TroubleshootModelOut`, `ChatModelOut`, `LanguagePackModelOut`, `TaggingModelOut`) are what Gemini returns. **API result schemas** (`AnalysisResult`, `TroubleshootResult`, `ChatAnswer`, `LanguagePack`) are what the server returns after verification, and add `verification`, `model_meta`, `request_id`, `resource_tags`, `page_thumbnails`, `warnings`, `disclaimers`, `urgency`, deadline math.
- Schema-subset rules for every model output schema, enforced by `ai/schema_guard.py` at import time and in a unit test: nesting depth ≤ 3 (root → list → object → scalars or lists of scalars); no `dict`/free-form maps; no `Any`; no recursive models; unions only `X | None`; enums as `str` Enums with ≤ 64 values; `bbox` is `list[float]` of length 4 (normalized 0–1); string fields carry `max_length` where meaningful.
- `LanguagePackModelOut.strings` is `list[KeyValue{key, value}]`; the server converts to a map (`LanguagePack.strings: dict[str,str]` is fine in the *API* schema because Gemini never sees it).
- Analysis runs in one of two modes, selected by `ANALYSIS_MODE=auto|single|two_call` (default `auto`): `single` sends pages once and expects `AnalysisModelOut` (transcript blocks + cards); `two_call` first requests `TranscriptOut` (blocks with bboxes, `MEDIA_RESOLUTION_HIGH`, thinking `medium`) and then `ExplainOut` from the transcript text (no images; thinking `high`), mapping facts to block ids from call one. `auto` = `single`, falling back to `two_call` for the request if the upstream rejects the schema (HTTP 400 mentioning schema) or returns `incomplete`/truncated output; `scripts/spike_schema.py` runs on day 0 against `gemini-3.8-flash` and records which mode the fixtures need; the result is pinned in `.env.example` comments.
- Page cap 12; above 8 pages thinking drops to `medium`; full-document translation (`translated_text`) is produced only when pages ≤ `TRANSLATE_FULL_MAX_PAGES` (default 4), otherwise only blocks referenced by demands/summary plus page 1 are translated and `warnings` contains `translation_partial`.

**Rationale.** gemini.md: "Structured-output supports only a JSON-Schema subset; deeply nested schemas may be rejected", and thinking tokens count toward `max_output_tokens` (too small → `incomplete` with empty output). All three candidate schemas were deeply nested or used free-form maps; the judges required the split, the flattening, the list-of-pairs pack schema and a day-0 acceptance spike with a two-call fallback.

---

## 3. Keys, failover, quota

### D-07 Key pool: per-tier state machine with Retry-After cooldowns; daily exhaustion only when the 429 says so; state persisted

**Decision.** `ai/keypool.py` keeps, per slot and per tier: `state ∈ {healthy, cooling, rpd_exhausted, disabled}`, `cooldown_until`, `consecutive_429`, `rpm_window` (sliding 60 s deque), `rpd_count`, `rpd_reset_at` (next midnight America/Los_Angeles), `last_error`, `last_used_at`. Transitions:
- 429 → `cooling` with `cooldown_until = now + (Retry-After header if present else min(30·2^consecutive_429, 900) s)`. If the error message/details mention a daily quota (`per day`, `RPD`, `daily`, `requests per day` — case-insensitive regex in `keypool.py`), mark `rpd_exhausted` until `rpd_reset_at` instead. Never bench a key for the day on plain 429s.
- 503/504 → one same-slot retry after 1.5 s, then next slot. 500/502 → next slot.
- 400 → abort the request (our bug), no rotation, log details (content-free). 401/403 → `disabled`, alert log line.
- Blocked generation (`finish_reason`/`prompt_feedback.block_reason` ∈ safety, spii, prohibited_content, recitation, blocklist; or empty candidates) → `422 content_blocked`; never retried on another key (same result, more exposure).
- Selection: least-recently-used `healthy` slot for the tier, preferring `billing:true` slots; `cooling` slots become eligible when `cooldown_until` passes. Optional operator soft caps `RPD_SOFT_CAP_PRO` / `RPD_SOFT_CAP_FAST` (default `0` = disabled) skip slots whose `rpd_count` reached the cap. The forum figure of ~20 RPD is *not* shipped as a default (unverified).
- Per-request budget: at most 3 slot attempts and `FAILOVER_DEADLINE_S` (default 100) total; server/Cloud Run request timeout 120 s; the client shows the honest three-step progress and a "long letters take longer" tip after 20 s.
- Degradation: if every pro slot is unavailable and `ALLOW_DEGRADED=true`, analyze/troubleshoot run once on `MODEL_FAST` with `MODEL_PRO_DEGRADED_THINKING`, flagged `model_meta.quality="degraded"` and `warnings: [degraded_model]`. Fast tasks never escalate to pro.
- All slots exhausted → `429 quota_exhausted` with `Retry-After` header, `error.retry_after_seconds = min cooldown`, `error.key_exhausted = true`, `user_message_key = "err.quota_exhausted"`. The client renders: "Our helper is very busy right now. Try again in {n} minutes, or see what you can do offline." with buttons Retry / Save to read later / Call 211 / Try a sample paper.
- State is persisted to `var/keypool.json` (no user data) after every transition so a restart does not forget a burned daily quota; `var/` is git-ignored.
- Every upstream call logs `{request_id, task, tier, model, slot_index, latency_ms, in_tokens, out_tokens, thought_tokens, outcome}` — never content, never the key.
- `GET /v1/admin/keys` (header `X-Admin-Token`) returns per-slot state with the key masked to its last 4 characters and the operator `project` label (a hash of the key cannot reveal the project — builder-first's "fingerprint" is rejected).

**Rationale.** gemini.md: 429 covers per-minute and per-second limits as well as daily; only RPD resets at Pacific midnight; limits are per project. user-first's "three 429s in 10 minutes → benched until midnight" would park a key on an ordinary RPM burst.

### D-08 Per-install soft rate limiting and content-free audit logging

**Decision.** Optional header `X-Install-Id` (random UUID generated on device, rotatable in Settings → "Delete everything"). The server hashes it with HMAC-SHA256 using `INSTALL_HASH_SECRET` and a daily-rotating salt (`sha256(secret + YYYY-MM-DD)`) and applies token buckets (`RATE_LIMIT_ANALYZE_PER_HOUR` default 20, `RATE_LIMIT_ANALYZE_PER_DAY` default 100) via slowapi with an in-memory store; also a coarse per-IP-class bucket. Over limit → `429 rate_limited` with `key_exhausted=false`. Audit log fields are exactly those listed in `docs/ARCHITECTURE.md` §"Logging"; explicitly forbidden: any document text, quotes, filenames, base64, model prose, IPs beyond the 7-day process log. Retention 30 days; only aggregate counters afterwards.

---

## 4. Anti-hallucination and safety contract

### D-09 Every fact is a quotation: `source_quote` + `span_ids` + `page` + `confidence` + `verified`; failures are shown, not hidden

**Decision.** In `AnalysisResult`, every `Demand` (deadline, relative deadline, amount, document requested, appointment, action, contact) and every `RedFlag` quote carries `source_quote`, `span_ids` (block ids into `original_text`), `page`, `confidence ∈ {high, medium, low}`, `verified: bool`, `verification_note`. `analysis/verify.py` requires `source_quote` (and `value_verbatim`) to be an exact or OCR-normalized substring of the concatenated referenced blocks (NFKC; whitespace collapsed; dash/quote unification; O/0, l/I/1, S/5 equivalence for matching only; `difflib` ratio ≥ 0.92 over a sliding window as the fuzzy fallback); digits in `value_verbatim` must appear in the quote. Failures move to `AnalysisResult.unverified[]`, get `confidence=low`, are excluded from urgency computation and from reminders, and the UI shows them under the plain-language heading "I saw these but could not confirm them on the page." (struck through in the *Details and quotes* table). Confidence is forced `low` when the block is marked unclear/handwriting, digits are ambiguous, or the block lies within 3% of a page edge (possible crop); low renders amber with "Re-scan this part". Every fact renders with a highlighted crop from `original_text[].blocks[].bbox` (or the full page with the quote when bbox is missing).

**Rationale.** compliance.md §7: "Extraction is quotation, not generation"; hallucinated dates/amounts/contacts are the highest-severity failure; builder-first's schema lacked bboxes and could not deliver the crop.

### D-10 Contacts and organizations come only from the paper or the vetted DB; the model emits tags, never contacts

**Decision.** `analysis/contacts_filter.py` runs over every user-facing string (summary, demands text, plan steps, glossary, red flags, `clerk_message`, chat answers, troubleshoot steps): phone-number-like digit runs (NANP + international), URLs/domains, emails and street addresses are kept only if present verbatim in the transcript (then labelled "from your paper"), otherwise replaced with "[contact removed — see Get help nearby]" and counted in `verification.contacts_stripped`. Organization names not in the transcript and not in the resource DB are replaced with "an organization (see Get help nearby)". Resources reach the UI only through `POST /v1/resources/match` from `data/resources/*.yaml`; the model's `resource_tags` are validated against the `ResourceTag` enum and anything else is dropped. Emergency numbers (911, 988, 1-800-222-1222, 1-800-799-7233) live in fixed copy, never in model output.

### D-11 Date math happens only in code, from printed relative phrases plus a small cited rules table; a printed date always wins

**Decision.** The model never sets a deadline kind and never computes dates; it records `date_text` (as printed) or `relative_rule_text` + `anchor_span_id`. `analysis/deadline_rules.py` produces `Demand.date` with `kind ∈ {stated, estimated, unresolved}`:
- `stated`: `value_iso` accepted only if deterministic parsing of `date_text` (regex table of US formats and month names in the 26 bundled languages; no `dateutil` guessing) yields exactly one date; otherwise `value_iso=null`, `confidence=low`.
- `estimated`: only when (a) the paper prints a relative phrase matching a rule's `pattern` **and** (b) the anchor date is a *verified* stated fact **and** (c) the rule's `applies_to_doc_types` includes the detected type **and** (d) `valid_until` has not passed. Output shows `formula` ("anchor + 30 calendar days (+3 mail days)"), `anchor_quote`, `rule_id`, `rule_source_url`, `rule_verification ∈ {verified, likely}` and is rendered as "Estimate: … Confirm with the sender." A printed date on the same demand always beats a computed one.
- `unresolved`: the phrase is shown verbatim with "Ask the sender which date this means."
- Seed rules (`data/rules/deadlines.yaml`, each with `source_url`, `source_verified_on`, `verification`, `valid_until`): `bia_appeal_30d` (**likely** until the BIA Practice Manual page is re-fetched; receipt-based), `ar11_10d` (verified), `eoir33_5bd` (likely, 5 business days), `aca_internal_appeal_180d` (verified), `aca_external_review_4mo` (verified), `medicare_advantage_65d` (verified), `medicaid_fair_hearing_90d_max` (likely; state sets exact), `asylum_annual_fee_30d` (verified via USCIS fee alert), `in_absentia_rescission_180d` (verified), `eeoc_180_300d` (verified), `osha_retaliation_30d` (verified), `gfe_dispute_120d` (verified). **Not seeded:** any eviction notice/answer period (`va_pay_or_quit_14d` rejected — resources.md: "Never hardcode notice/answer periods… always tell users the court date on a summons is the deadline that matters"; Va. Code §55.1-1245 changes July 2027/2028). Eviction summonses surface the printed court date as `stated` and the fixed line "The court date on this paper is the date that matters."
- `GET /v1/rules` exposes the table with its sources so the UI's "rule ↗" link and auditors see the same data.

### D-12 Urgency is computed in code from verified facts and document type, never by the model

**Decision.** `analysis/urgency.py`: `emergency` if the emergency lexicon fires (D-14); `critical` if a verified `hearing_date`, ICE/USCIS `appointment`, eviction-summons court date, or `payment_due` on an `asylum_fee_notice` is ≤ 7 days away, **or** is past by ≤ 60 days on court/USCIS documents (headline "This date may have passed — contact them today"); `high` ≤ 14 days; `medium` ≤ 30 days; `info` otherwise. Doc-type floors: `nta`, `hearing_notice`, `eviction_summons`, `uscis_noid`, `utility_shutoff` never below `high` even without dates. Unverified facts and `estimated` dates never raise urgency above `medium`. The banner carries a "Verify this date" CTA that opens the matching verification resource (EOIR ACIS/hotline for court dates, USCIS Contact Center for USCIS dates, the sender's printed phone for others). Urgency copy is icon + word + color, from fixed keys (`urgency.critical.headline` etc.), never CAPS-only, never "You may be deported".

### D-13 Scam handling is a first-class path with fixed copy and forced reporting resources

**Decision.** `analysis/scam.py` scores `scam_risk ∈ {none, possible, likely}` from model `red_flags` (enum kinds only) plus code regexes on the transcript (gift card, Western Union, MoneyGram, Zelle/Venmo/PayPal/Cash App, Bitcoin, "pay to avoid arrest/deportation", "guaranteed", "notario", non-.gov domain near an agency name, "expedite for a fee"). `likely` renders the fixed card "Scam risk: likely — ICE, USCIS, SSA and the IRS never demand payment by phone, gift card, wire, or app. Do not pay. Report it:" with DHS OIG 1-800-323-8603 and ReportFraud.ftc.gov taken from the resource DB, and the matcher forces `scam_report` resources to the top. Troubleshoot offers mode chips *Stuck on a website* / *Is this a scam?* (`mode=scam_check`) because scams arrive as texts and screenshots, not only paper.

### D-14 Emergency card from fixed copy, keyword-triggered in every bundled language, biased to over-trigger

**Decision.** `data/safety/emergency.yaml` holds per-language keyword lists (chest pain, cannot breathe, overdose, poison, suicide/self-harm, stroke signs, severe bleeding, allergic reaction, violence) run in code on transcripts and chat messages, plus the model's `emergency_terms_found`. Any hit → `safety.emergency=true` and the client shows the fixed emergency card first (911 / 988 call-or-text / Poison Help 1-800-222-1222 / DV hotline). Lists are marked `reviewed_by` per language; unreviewed languages fall back to English + Spanish lists and set `warnings: [emergency_lexicon_unavailable]`. False positives are acceptable; false negatives are not. Native-speaker review of every Tier 1/2 list is a launch gate (open question Q6).

### D-15 Prompt injection: instruction-in-document is detected in code and the call is re-run once with the offending block masked

**Decision.** `analysis/injection.py` scans the transcript for injection phrasing (`data/safety/injection.yaml`: "ignore previous instructions", "as an AI", "system prompt", …). On a hit the analysis is re-run once with those blocks replaced by `[text addressed to computers removed]` in the transcript (two-call mode) or masked on the image (single mode, via D-19's Pillow mask path); the result carries `red_flags[kind=injection_suspected]` and `warnings: [injection_masked]`; the audit log records `injection_suspected=1`.

### D-16 Golden-set gate and recording provider

**Decision.** Every fixture (D-27) has expected outputs per target language; `tests/golden/` asserts the mock provider's output passes every validator (all quotes verifiable, zero contacts stripped, phrasing lint clean, expected urgency and deadline kinds). `tests/live/` (skipped unless `RUN_LIVE=1` and keys exist) runs each fixture through `MODEL_PRO` and reports fact precision/recall and invented-contact count; a prompt or model change that lowers precision or introduces an invented contact fails CI. A `RecordingProvider` decorator (dev only) records anonymized live outputs from fixtures to refresh goldens.

---

## 5. Information, not advice

### D-17 Fixed domain disclaimers, phrasing lint with template rewrites, chat refusal kinds, no form drafting

**Decision.**
- `AnalysisResult.disclaimer_kind` (primary, by `category`) ∈ `DisclaimerKind`: `legal_information_only` (immigration, court, civic, employment-legal) — "This is general information about this type of paper, not legal advice about your case. Only a licensed lawyer or a DOJ-accredited representative can advise you."; `medical_information_only` — "This explains what your paper says. It is not medical advice. Ask your doctor, nurse or pharmacist what it means for you."; `benefits_information_only`; `housing_information_only`; `general_information`. Secondary `disclaimers[]` add `machine_translation`, `verify_with_sender`, `ai_generated`, `degraded_model`, `unpaid_tier_warning`, `demo_sample` as applicable. The client renders fixed copy from the pack; the model never writes disclaimers.
- `analysis/phrasing.py` lints every user-facing sentence against `data/safety/phrasing.yaml` patterns (English + target language when available): "you qualify / are (not) eligible", "you should (file|appeal|apply|pay|sign)", "you will (be|get|win|lose)", "you (do not|don't) have to", "does not require you to", "this means you have", "your (results|levels) (are|show)…", diagnosis verbs. A match triggers one `MODEL_FAST` rewrite pass with the template "The paper says X. A {professional} can tell you what it means for you."; if it still matches, the fixed hedge is substituted and `verification.phrasing_rewrites` increments. Unknown languages lint English only and set `warnings: [phrasing_lint_unavailable]`.
- Chat returns `refusal_kind ∈ {none, eligibility, filing_advice, outcome, medical_interpretation, drafting, contact_request, out_of_scope}` and `refer_to_professional ∈ {none, lawyer_or_accredited_rep, clinician, housing_counselor, benefits_office, sender}` so the UI renders fixed referral templates. Example rewrite the linter must catch (from risk-first Journey B): "The notice itself does not require you to leave; a court hearing would have to happen first in Virginia" → "In Virginia, a landlord generally needs a court order before an eviction can happen. Confirm with the legal helpline today."
- The model is never asked to draft, fill or format any official form or letter; `drafting` requests are refused with a referral.
- 4th-grade reading level in every prompt ("short sentences, everyday words, one idea per sentence, no acronym without a short explanation, warm and calm like a trusted neighbor. Never shame the reader. Never exaggerate danger. Never minimize a real date."); a CI readability script checks bundled English strings at grade ≤ 5.

### D-18 Clerk card: fixed template, linted AI need-line, conditional interpreter line

**Decision.** `clerk_message.english` = fixed template "Hello. I speak {Language}. I am here about: {document type as written}. I need help with: {need line}. Please speak slowly or write it down. Thank you." The AI-proposed `clerk_need_en` passes the contact filter and phrasing lint, is capped at 200 characters, and falls back to the fixed per-document-type need line from `data/rules/clerk_needs.yaml` when it fails. The line "I may ask for a free interpreter." is appended **only** when the matched resource or document sender is tagged `hhs_funded_health` in the resource DB (HHS OCR LEP rights); a landlord/court variant never includes it (LEP.gov suspended; EO 13166 rescinded). Clerk mode (S10) is LTR, high contrast, ≥ 24 pt, raises brightness, hides vault navigation, and exits only by a 1.5 s long-press on "Back to me" in the user's language.

### D-19 Redaction ("Hide parts") without new native packages: client masks on web, server-side Pillow burn on native, nothing unmasked is ever stored

**Decision.** S5 lets the user draw black rectangles. On web the mask is burned into the JPEG on a `<canvas>` before upload and `pages[].masks=[]`, `masks_applied_client_side=true`. On native (no compositing primitive in installed packages: expo-image-manipulator only resizes/crops/rotates/flips; react-native-view-shot and Skia are not installed) the client sends `pages[].masks: [{x0,y0,x1,y1}]` in normalized coordinates; `analysis/redaction.py` burns them with Pillow in memory before the Gemini call and before any thumbnail is rendered; unmasked bytes exist only in request memory and are released. Consent copy says: "Parts you hide are blacked out on our server before Google's AI sees them." (literally true). LATER: on-device burning via a dev-build module. Additionally the server replaces SSN-like patterns in `original_text` with `***-**-1234` and masks A-numbers/receipt numbers in `AnalysisResult` only when the user enabled "Hide ID numbers in saved copies" (default off, because receipt numbers are needed for case status).

### D-20 Fixed high-severity notices by document type

**Decision.** `data/rules/fixed_notices.yaml` maps document types to fixed red-flag cards the client always shows: `jury_summons` → "You must answer this form. If you are not a U.S. citizen, mark *not a citizen* and send it back. Never check 'citizen' and never register to vote — it can permanently harm your immigration case."; `uscis_receipt` for I-765 renewals → "A receipt for a work-permit renewal filed on or after October 30, 2025 is **not** proof you can work. Ask a lawyer or DOJ-accredited representative about a possible work gap."; `pay_or_quit` → "This is not a court order. Only a court can make you leave."; `eviction_summons` → "The court date on this paper is the date that matters. Go, or you can lose automatically."; `asylum_fee_notice` → "There is no fee waiver for this fee."; `nta`/`hearing_notice` → "If you move, the court needs its own address form (EOIR-33). USPS forwarding does not update the court or USCIS."

---

## 6. Limits, uploads, PDFs

### D-21 One consistent set of caps; no Files API

**Decision.** JSON bodies with base64 pages are the only request format (typed end to end); multipart is not offered in v1. Caps, enforced server-side and shown in `GET /v1/config.limits`: images 1–12 pages, each ≤ 4 MB after client compression (client: 1600 px longest edge, JPEG 0.8, EXIF stripped); PDF exactly one file ≤ 12 MB raw and ≤ 60 pages (page count via pypdfium2 in memory); total JSON body ≤ 20 MB (`payload_too_large` 413); inline bytes sent to Gemini ≤ 18 MB (checked before the call). MIME allow-list: `image/jpeg`, `image/png`, `image/webp`, `image/heic`, `image/heif`, `application/pdf` (`unsupported_media_type` 415). Never route a larger file through `client.files.upload` (48-hour Google-side retention contradicts "never persisted"). PDF pages are rasterized in memory (pypdfium2) for `page_thumbnails` so crops work; nothing touches disk.

**Rationale.** gemini.md caps inline requests at 20 MB total; base64 inflates ×1.37; risk-first's 50 MB/200 pages and builder-first's 50 MB/1000 pages were internally inconsistent and would have needed the Files API.

---

## 7. On-device storage and privacy per platform

### D-22 Native vault: expo-sqlite (plain) + files in `Paths.document/vault/` + OS file encryption + device-only SecureStore key; no SQLCipher claim in v1; saving is opt-in

**Decision.** Native: `expo-sqlite` database `proxyhealth.db` (WAL) in `Paths.document`, tables `members`, `documents`, `pages`, `checklist_state`, `reminders`, `consent`; page JPEGs and rasterized PDF thumbnails as files under `Paths.document/vault/<doc_id>/`. A random 256-bit `vault_key` is generated with `expo-crypto` on first run and stored in `expo-secure-store` with `WHEN_UNLOCKED_THIS_DEVICE_ONLY`; in v1 it is used to derive the PIN-lock verifier (SHOULD) and reserved for future AES-GCM of blobs (expo-crypto has no AES primitive, so app-layer encryption is LATER and is **not** claimed in copy). `android.allowBackup: false`; iOS backup exclusion of the vault directory and the `["expo-sqlite", {"useSQLCipher": true}]` plugin option are *verified in the first EAS development build*; until verified, privacy copy says only "Papers you save stay on this phone, protected by your phone's own encryption. Turn on a phone passcode." Saving is **opt-in** after each scan ("Save" → "Whose paper is this?"), never automatic; "Keep page images" defaults ON native, OFF web. One-tap "Delete everything" removes DB, files, packs cache, consent, install id. Small preferences (language, text size, consent record, pack cache, member list index) use `@react-native-async-storage/async-storage` (works on web; nothing sensitive). Reminders store only demand label + date; notification body is generic ("You have a date coming up") unless the user opts into detail.

### D-23 Web vault: session-only by default; explicit opt-in to IndexedDB with an honest label; no secrets on web

**Decision.** Web storage adapter `vault.web.ts` keeps documents in memory for the session by default. Settings offers "Keep on this device (not encrypted by the app)" which switches to IndexedDB (via a thin wrapper; no COOP/COEP headers, no sqlite-wasm) and a "Clear when I close this tab" option (default on when IndexedDB is enabled on a browser that reports `navigator.storage` unavailable or on any shared-device hint). `secure.web.ts` is an in-memory shim: no vault key, no PIN on web. `files.web.ts` uses Blob/`URL.createObjectURL`. The web consent line says "stay only in this browser, if you choose to keep them."

### D-24 Family vault, clerk-safe navigation, trust-by-restraint

**Decision.** Documents belong to a member ("Me" plus added members with initials and color); post-scan "Whose paper is this?"; "Move to another member"; per-member wipe. The app never asks immigration status anywhere (no `status_hint`, no `immigration_status_bucket` fields exist in the API); LSC-restricted resources show the one-sentence note "This organization usually cannot help people without immigration papers, except survivors of violence or trafficking." with an "If that is not you, try these instead" link to ImmigrationLawHelp / DOJ pro bono list. Location is state + optional zip3 (never full ZIP, never GPS). Feedback stores counts only (D-31).

---

## 8. Language packs, RTL, fonts, speech

### D-25 Base English pack shipped; Tier 1+2 packs bundled and labelled machine-translated until reviewed; Tier 3 generated by the fast model, cached server-side with checksums

**Decision.**
- Canonical base pack: `apps/api/data/langpacks/en.json` (flat keys, `{placeholder}` syntax). `pack_version = sha256(en.json)`. `scripts/sync_to_mobile.py` copies `en.json` and all bundled packs into `apps/mobile/src/i18n/packs/`; CI fails if the copies differ.
- Bundled packs (offline, in the app binary): **Tier 1** en, es, zh-Hans, zh-Hant, vi, tl, ar, ht, pt-BR, ru, uk, ko, fr; **Tier 2** prs (Dari), ps (Pashto), fa, ur, hi, pa, bn, so, sw, am, my, ne, rw. All are generated by `scripts/gen_packs.py` with `MODEL_FAST` in 60-key chunks, QA'd (placeholder set equality, non-empty, length ratio ≤ 1.6× or 2× for `btn_*`, no HTML, no phone-like digit runs), and committed. Every pack carries `machine_translated: true` and `reviewed_by: null` until a named human reviewer signs off; only `en` is `machine_translated: false` at v1 (and `es` if reviewed in-session). The UI shows the "This language was translated by a computer" banner for every `machine_translated` pack. We do **not** claim 13 human-reviewed packs anywhere.
- **Tier 3 / typed languages**: `POST /v1/language-packs {language_query, pack_version}` → server resolves the query to a BCP-47 tag (ISO table first; `MODEL_FAST` only for names not in the table; unresolvable → `x-<slug>` private-use tag with the typed name), generates in 60-key chunks, QA's, caches in `var/langpacks/<tag>--<pack_version>.json` with a strong `ETag = sha256(content)`, single-flight per tag; `GET /v1/language-packs/{tag}` serves cached packs with `304` on `If-None-Match`; `409 pack_version_mismatch` when the client's base differs. The client caches packs on device keyed by `tag|pack_version`. Missing keys fall back to English and set `fallback_keys`.
- The loading state uses the user's requested English base string verbatim: `"langpack.adapting": "Adapting system environment to your language..."` (the pack translates it; a plain sub-line "About 20 seconds" follows). Partial packs show "Some words are in English."

**Rationale.** Judge 1 required Dari/Pashto offline on day one for the target population; Judge 3 forbade claiming human review that has not happened. Bundling machine-translated packs with an honest label satisfies both; the free-form map problem is solved by the list-of-pairs model schema (D-06).

### D-26 RTL without expo-updates; fonts; on-device TTS with honest fallbacks

**Decision.** `useDirection()` (from the active pack's `direction`) drives `flexDirection: isRTL ? 'row-reverse' : 'row'`, `textAlign`, and `writingDirection` in every component, so RTL is correct immediately in Expo Go, dev builds and web. On native, changing to/from an RTL language also calls `I18nManager.allowRTL/forceRTL` and shows "Restart the app to finish switching" (applies on next start; `expo-updates` is not installed and `Updates.reloadAsync()` is not used). On web the root sets `document.documentElement.dir`. Verbatim values (dates, case numbers, amounts, phones, URLs, agency names) render inside `<Bidi dir="ltr">` (LRI/PDI on native, `unicode-bidi: isolate` on web); digits are never localized or reversed; a localized date line (e.g., Persian digits) may be *added*, never substituted. Fonts via `expo-font`: Noto Sans, Noto Naskh Arabic, Noto Nastaliq Urdu (line-height 2.0), Noto Sans Ethiopic, Noto Sans Myanmar, Noto Sans Devanagari/Bengali/Gurmukhi, Noto Sans Hanifi Rohingya (subsetted; CJK uses system fonts). TTS: `expo-speech`; voice map from `getAvailableVoicesAsync()`; no voice → offer the closest related language (Dari → Farsi voice; Rohingya → Burmese or English) with an honest message; sentence-level chunks under `maxSpeechInputLength`; persistent stop button; "I want to hear it, not read it" auto-play mode; speaker button (44×44) after every paragraph. Server TTS (`gemini-3.8-flash-tts`) is LATER.

---

## 9. Navigation shell and design system

### D-27 Navigation: root `Stack` + a `(tabs)` group using JS `Tabs` from `expo-router` on every platform; the template's NativeTabs and its web variant are deleted

**Decision.** `src/app/_layout.tsx` becomes a root `Stack` wrapping providers (theme, i18n, direction, API config, storage). `src/app/(tabs)/_layout.tsx` uses `Tabs` from `expo-router` (JS tabs, identical on iOS, Android and web) with four tabs, each icon + word, 64 pt tall: **Home** (`index` — the giant "Take a photo of a paper" CTA plus tiles *Pick a photo or PDF*, *Stuck on a website?*, *Show the clerk*), **My papers** (`papers`), **Get help** (`help`), **Settings** (`settings`). Scan, result, chat, clerk, quick sheet, troubleshoot, reminders and emergency are stack screens above the tabs. Deleted template files: `src/components/app-tabs.tsx` (NativeTabs from `expo-router/unstable-native-tabs`), `src/components/app-tabs.web.tsx` (`expo-router/ui` headless tabs), `src/app/explore.tsx`, `src/components/animated-icon*.{tsx,css}`, `hint-row.tsx`, `web-badge.tsx`, `themed-text.tsx`, `themed-view.tsx`, `hooks/use-theme.ts`, `constants/theme.ts` (replaced by `src/design/tokens.ts`); kept: `external-link.tsx` (moved to `src/design/components/`), `ui/collapsible.tsx`, `hooks/use-color-scheme*.ts`. Packages `@expo/ui`, `expo-glass-effect`, `expo-symbols` remain installed but unused (no uninstalls during parallel work).

**Rationale.** NativeTabs fall back to "a basic implementation" on web and change import path in SDK 58; a single JS `Tabs` layout gives web parity, one code path, and fewer SDK-58 changes. Tabs (rather than a pure tile Home) give returning users a stable way back to their papers and help, which the caseworker persona needs; the 72 pt Home CTA remains the one primary action.

### D-28 "Big Calm" design system and accessibility floor

**Decision.** Tokens in `src/design/tokens.ts`: base font 18 (minimum body 16), buttons 56 pt tall, primary CTA 72 pt, touch spacing 8 pt, `hitSlop` 8, body contrast 7:1 (never below 4.5:1), UI components 3:1; urgency = icon + word + color; `allowFontScaling` on everywhere, `maxFontSizeMultiplier` 2.0 only on tab labels; light/dark/high-contrast palettes with `useHighContrast()` = user toggle OR `AccessibilityInfo.isHighTextContrastEnabled()`/`isDarkerSystemColorsEnabled()`; reduce-motion respected; every screen has one primary action; a persistent calm "Need help now?" affordance (opens the emergency card) replaces risk-first's "🆘 Emergency" header; no emoji in button labels (screen readers read them). Each card is a `role="region"` with a heading; per-pane `accessibilityLanguage`/`lang`; live regions for progress and results; WCAG 2.2 AA is the floor.

---

## 10. Demo, fixtures, parallel work

### D-29 Mock provider is real product surface: fixtures, perceptual-hash matching, simulated latency

**Decision.** `ai/mock.py` resolution order: `demo_sample_id` → fixture output for that sample and `target_language` (fallback to `en` output with a `⟦xx⟧` pseudo-translation marker); else 16×16 dHash (Pillow) of the first page against fixture images, Hamming ≤ 10, so a judge can photograph a printed sample sheet in zero-key mode; else a generic "I could not recognise this sample" result with `quality.readable=false`. Latency simulated 300–900 ms (`MOCK_LATENCY_MIN_MS/MAX_MS`) so loading states show. Chat: keyword-routed canned replies with real quotes from the fixture transcript. Language packs: bundled file if present, else pseudo-localized pack with `direction` from a small script table. `/health` reports `provider: mock, keys_configured: 0`. `MockProvider` returns a valid `AnalysisModelOut` for *any* input from hour one (one hard-coded fixture) so UI and pipeline work never block on the fixture set. Fifteen fixtures (synthetic, watermarked SAMPLE): Medicaid address-confirmation letter, USCIS I-797C receipt (I-765 renewal), I-797E RFE with 87-day date, Notice to Appear with hearing date, Inova statement "FINAL NOTICE", insurance denial with 180-day appeal text, prescription label, school immunization notice, Virginia 14-day pay-or-quit, SNAP interview notice, IRS CP notice, jury summons, scam letter demanding gift cards, blurry unreadable page, Spanish-language lease; plus a W-2 and a traffic-court notice (employment/tax and court breadth) and a portal "file too large" screenshot. Expected outputs in en, es, prs, ar. Demo rule: **keyed demos use fixtures or a photographed printed SAMPLE sheet only — never a real personal letter**, regardless of consent, and the 403 gate blocks non-demo uploads on any unpaid slot even when `ALLOW_UNPAID_KEYS=1`.

### D-30 Parallel-agent scaffolding: exclusive write scopes, day-0 stubs, committed OpenAPI snapshot, one-command dev

**Decision.** `docs/BUILD_PLAN.md` (to be written) uses the work-package table format `WP | Owner scope (exclusive write) | Reads | Definition of done`, mirrored in `docs/ARCHITECTURE.md` §"Ownership map". Day-0 interfaces: `ai/provider.py` Protocol stub, `contracts/**` models, `MockProvider` one-fixture output, `apps/api/openapi.json` committed and regenerated by `scripts/export_openapi.py`; `tests/contract/test_openapi_snapshot.py` fails CI if the committed file differs; `apps/mobile/src/api/schema.d.ts` generated from the file (no running server needed). `make dev` boots API (mock) + Expo web; `scripts/smoke.sh` posts a fixture to every endpoint. Phone demos use an EAS **development build (Android first — no Apple account needed)**; Expo Go is smoke-only. SDK 58 upgrade is planned before store submission.

### D-31 Feedback is counts only

**Decision.** `POST /v1/feedback` accepts `kind` (clear / unclear / wrong_word / wrong_fact / offensive / scam_missed / resource_problem), `surface`, `language_tag`, `document_category`, `card_id`, `resource_id`, `app_version`, `platform` — no free text, no AI sentence, no document text. The server increments counters in `var/feedback_counts.sqlite` keyed by those enums and returns an id. Free-text or "include this card" feedback is LATER and opt-in.

**Rationale.** AI sentences routinely contain the document's dates, sender and amounts (user-first retained them 12 months); the task's requirement is "counts only, no content"; Play's flag requirement is satisfied by the `offensive`/`wrong_fact` kinds.

---

## 11. Rejected from the candidate specs (and why)

| Rejected item | Source | Why |
|---|---|---|
| Unpaid-tier control as policy + banner (`ALLOW_UNPAID_TIER=true`, client `X-Demo` header as the only demo signal) | user-first | No server enforcement; a misconfigured deployment could upload real documents on free keys (Gemini terms). Replaced by D-01. |
| `GEMINI_API_KEYS` comma list; "three 429s in 10 min → benched until Pacific midnight" | user-first | Cannot verify distinct projects or billing; conflates RPM and RPD 429s. Replaced by D-01/D-07. |
| `/v1/admin/keys` "project fingerprint = first 6 chars of a hash of the key" | builder-first | A hash of the key string cannot reveal the Google Cloud project. Replaced by the operator `project` label. |
| `RPD_SOFT_CAP_DEEP=20` shipped default | builder-first | Encodes an unverified forum figure; default is 0 (disabled). |
| `Updates.reloadAsync()` after `I18nManager.forceRTL` | risk-first, builder-first | expo-updates not installed; reload unavailable in Expo Go; forceRTL applies on next start anyway. Replaced by `useDirection()` + restart prompt (D-26). |
| App lock via `expo-local-authentication` as MUST | risk-first | Package not installed; CLAUDE.md forbids installs during parallel work; no web path. Demoted to SHOULD as a PIN lock built on SecureStore + expo-crypto digest; biometrics only in a WP0-owned install window. |
| Redaction "baked into the bitmap client-side via expo-image-manipulator crop/extent composition" / "burned into the JPEG before upload" as MUST on native | risk-first, builder-first | image-manipulator has no compositing op; view-shot/Skia not installed. Replaced by D-19 (canvas on web, Pillow on server). |
| Client-side Laplacian/variance blur check on native | risk-first, user-first | No pixel access on native with installed packages. Web-only canvas heuristic + server `quality.legibility` shown before quota is spent again. |
| PDFs ≤ 50 MB / ≤ 200 or 1000 pages; 24 MB body; 20 images | risk-first, builder-first | Exceed the 20 MB inline ceiling; the Files API keeps files 48 h at Google. Replaced by D-21. |
| Multipart `/v1/analyze` with `options` as a JSON string | risk-first (and builder-first alternative) | Untyped in the generated TS contract; violates "Pydantic is the single source of truth". JSON-only (D-21). |
| `LanguagePack.strings: dict[str,str]` in the *model* response schema | user-first, risk-first | Free-form maps are the classic unsupported structured-output case. List of pairs (D-06). |
| Single deeply nested `AnalysisResult` returned by the model, mixing server-only fields | user-first (and the other two) | Likely rejected/truncated; violates the schema-subset rules. Split (D-06). |
| `immigration_status_bucket` / `status_hint` request fields; "undocumented" selector | risk-first, builder-first | CPRA sensitive PI; inferable and subpoenable; fearful users read it as a trap. Never ask status (D-24). |
| Auto-save every analysis with page images; "Recent" list on Home by default | builder-first | Exposes papers on shared phones and at the counter. Saving is opt-in (D-22). |
| Retaining `ai_sentence` in feedback for 12 months | user-first | Contains the user's dates/sender/amounts. Counts only (D-31). |
| Model-set `urgency.level` | builder-first | Most consequential triage signal must be computed from verified facts (D-12). |
| `va_pay_or_quit_14d` as a computed deadline; `bia_appeal_30d` marked verified | risk-first | resources.md forbids hardcoding eviction periods; BIA rule sourced only via search → `likely` (D-11). |
| Unconditional clerk-card interpreter-rights sentence | risk-first, builder-first | LEP.gov suspended, EO 13166 rescinded; conditional on HHS-funded setting (D-18). |
| "With keys" demo using the judge's own letter on a free key | builder-first | Personal information on Unpaid Services regardless of consent. Fixtures only (D-29). |
| `packages/shared` npm workspace with a new lockfile | risk-first | Scaffold is not a workspace; converting requires installs during parallel work. Canonical data lives in `apps/api/data/` and is synced by script (D-25). |
| Claiming 13 "human-reviewed" bundled packs | all three | FTC §5 / store-claim risk. Labelled machine-translated until a reviewer signs off (D-25). |
| Persistent "🆘 Emergency" header, CAPS "CRITICAL" banners, 6th-grade copy, 44 pt controls, emoji in buttons | risk-first, builder-first | Frightening for the persona; screen readers read emoji; replaced by D-12/D-28. |
| Dari/Pashto as on-demand (not bundled) packs | builder-first | Target population on unstable data needs them offline on first run (D-25). |
| Full ZIP in resource matching | builder-first | zip3 is enough for routing (D-24). |
| Renaming the "Adapting system environment to your language..." loading copy | user-first (and builder-first paraphrase) | The user asked for that copy; it is the English base string (D-25). |
| `["expo-sqlite", {"useSQLCipher": true}]` and iOS backup exclusion as *claimed* protections | user-first, risk-first | Unverified in expo.md; verify in the first dev build; do not claim until then (D-22). |

---

## 12. Open questions only the user can answer

1. **Billing owner.** Who owns the Google Cloud project(s) with billing attached for the paid tier, how many distinct projects can we get keys from, and what monthly spend cap do you accept? (Free keys can only ever run fixtures — D-01.)
2. **Developer accounts.** Which legal entity submits to the stores (Apple 5.1.1(ix) requires an organization account for healthcare/sensitive-data apps)? Do you already have Apple Developer Program and Google Play Developer accounts?
3. **Counsel.** Do you have (or want us to draft a brief for) an attorney to review UPL framing per document type, the FTC HBNR applicability memo, and the privacy policy before store submission?
4. **Bundle identifiers and domain.** Confirm `org.proxyhealth.app` (or another reverse-DNS id), the web hostname (EAS Hosting subdomain `proxyhealth.expo.app` vs. a custom domain), and where the public privacy policy will be hosted (must be a non-PDF URL).
5. **Pilot geography.** Northern Virginia is the seeded local resource set. Which other states/counties do you want seeded for v1, and who maintains re-verification every 90 days?
6. **Language reviewers.** Which community reviewers can sign off Tier 1/2 packs, glossaries and the emergency keyword lists (Dari, Pashto, Arabic, Spanish, Amharic first)? Until then every pack stays labelled machine-translated.
7. **Spanish review in-session.** Should we mark `es` as reviewed if a bilingual member of the team reviews it during the build, or keep everything machine-translated until an external reviewer signs?
8. **Per-device budget.** Acceptable per-install limits for the pilot (default 20 analyses/hour, 100/day) and whether to add a kinder per-device daily budget message.
9. **Web positioning.** Is web a first-class caseworker tool (drag-and-drop, keyboard flow) or a companion/demo surface for v1?
10. **Interactions API timing.** Do you want the Interactions provider built (behind the flag) in v1 or deferred until Google announces a deprecation date for `generateContent`?
11. **Hosting.** Google Cloud Run in the same account as the billed Gemini project (recommended) or another host (Fly.io/Render)?

---

## 13. Optional broader-brand suggestion (name stays "ProxyHealth AI")

The name stays **ProxyHealth AI** as the user chose. Because the product now decodes immigration, housing, benefits, school, employment and tax papers as well as medical ones, use a descriptive tagline everywhere the name appears: **"ProxyHealth AI — Your paper, explained."** Store title: "ProxyHealth AI: Your paper, explained"; subtitle: "Understand letters, bills and notices in your language." Category Reference (iOS) / Tools (Android), deliberately not "Medical". If a broader umbrella is ever wanted, "Proxy AI" with "ProxyHealth" as the health module is the least disruptive path, but nothing in v1 depends on it.

---

## Appendix A — Decision index by required topic

| Required topic | Decisions |
|---|---|
| (1) Unpaid-tier handling | D-01, D-02, D-03, D-29 |
| (2) Model IDs and env overrides | D-04 |
| (3) generate_content vs Interactions | D-05 |
| (4) Multi-key failover | D-07, D-08 |
| (5) Structured-output strategy | D-06 |
| (6) Anti-hallucination contract | D-09, D-10, D-11, D-12, D-13, D-15, D-16 |
| (7) Information-not-advice framing | D-17, D-18, D-20 |
| (8) On-device storage per platform | D-22, D-23, D-24, D-19 |
| (9) Language-pack strategy | D-25, D-26 |
| (10) Navigation shell | D-27, D-28 |
| (11) Rejected items | §11 |
| (12) Open questions | §12 |
| (13) Brand suggestion | §13 |

## 14. Change log (append-only; cross-WP needs are filed here as one line and resolved by WP0)

- 2026-09-27 (orchestrator): `arabic-reshaper` 3.0.1 and `python-bidi` 0.6.11 are now installed in `apps/api/.venv` (Pillow here has no raqm). WP3 (`quicksheet/render.py`) and WP7 (`scripts/make_fixtures.py`) MUST shape Arabic-script text with `arabic_reshaper.reshape()` then `bidi.algorithm.get_display()` before drawing; ARCHITECTURE §2.1 `render.py` line updated accordingly.
- 2026-09-27 (orchestrator): Static Noto TTFs (Regular + Bold) for the nine `font_hint` families are pre-downloaded from Google Fonts (OFL) into `apps/api/data/fonts/` and mirrored to `apps/mobile/assets/fonts/` with `OFL.txt`; WP3/WP4 use these files and do not re-download. Subsetting is LATER.
