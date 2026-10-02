# ProxyHealth AI — Compliance, Privacy, Safety and Accessibility (spec)

Status: **authoritative for copy, disclosures, store declarations and privacy controls**. Implements `docs/DECISIONS.md` (D-01, D-02, D-03, D-08, D-10, D-13, D-14, D-17, D-18, D-19, D-20, D-22, D-23, D-24, D-25, D-28, D-31), `docs/API_CONTRACT.md` and `docs/ARCHITECTURE.md`. Written 2026-09-27 from `docs/research/compliance.md`, `docs/research/gemini.md`, `docs/research/expo.md`, `docs/research/resources.md` and the candidate specs in `docs/research/specs/`. Owner: WP8 (store/devops) for the file; WP0 adds the approved strings to `apps/api/data/langpacks/en.json`; WP1/WP2/WP4/WP5/WP6 implement the controls named per section. When this document and code disagree, fix one and say which in the PR.

How to read this file:
- Every sentence in double quotes under a `key:` is **final English copy**. It goes into `en.json` under that key exactly (WP0). Every other language is a pack translation (D-25). Copy is written for a 4th–5th grade reading level; the legally fixed sentences in §5 and §6 are exempt from the readability check (their keys are allow-listed in `tests/unit/readability_allowlist.txt`, BUILD_PLAN §5.9 step 4 — see §5).
- "MUST" = launch blocker. "SHOULD" = v1.x. "LATER" = not in v1 and **never claimed in copy**.
- §17 `privacy_claims` is machine-readable and is the source for `apps/api/tests/unit/test_privacy_claims.py` (D-02).
- Nothing here asks the model to write disclaimers, contacts, dates or legal conclusions. Those are fixed copy or code (D-10, D-11, D-12, D-17).

Definitions: **paper** = any document the user photographs or picks. **Content** = page bytes, transcript blocks, translations, quotes, model prose, chat text, quick-sheet text. **Tier** = `DataUseTier` from `GET /v1/config` (`paid | unpaid | mixed | demo | none`) plus the client-only state `unknown` (API unreachable). **Operator** = whoever runs `apps/api` with keys.

---

## 1. Compliance posture at a glance

| Regime | Applies? | What ProxyHealth AI does | Where implemented / verified |
|---|---|---|---|
| Gemini API Additional Terms (2026-03-23): unpaid content used for product improvement with human review; "do not submit sensitive, confidential, or personal information" to Unpaid Services | Yes, central | Real papers only on `paid` tier; `unpaid`/`mixed` → `403 unpaid_tier_real_documents_disabled` unless `demo_sample_id`; production refuses to boot with unbilled keys unless `ALLOW_UNPAID_KEYS=1` (fixtures only) | D-01; `settings.py`, `middleware.py`, `tests/contract/test_errors.py` |
| Gemini terms: 18+, no clinical practice / medical advice, no regulated-device use; Prohibited Use Policy: no unsupervised high-risk automated decisions, no misleading expertise claims | Yes | 18+ line at consent, 18+ store ratings, "information not advice" framing, no eligibility/outcome/filing conclusions (phrasing lint, refusal kinds), urgency computed in code with "Verify this date" | D-02, D-12, D-17; §5, §6 |
| Gemini terms: EEA/Switzerland/UK clients may use Paid Services only | Only if users are there | v1 is US-only (`region_notice: "us_only"`); any EEA/CH/UK exposure requires all `billing:true` and `ALLOW_UNPAID_KEYS` unset | D-03; §14 |
| Apple App Store Review 1.4.1, 2.3.1, 5.1.1(i)(ii)(iii)(v)(ix), 5.1.2(i)(vi), 5.1.3(i)(ii); age rating; privacy nutrition label; privacy manifest | Yes | Clinician reminder in UI, consent screen naming Google Gemini before first upload, camera + system pickers only, no login, organization account, no analytics SDKs, no iCloud for vault, 18+, label per tier | §10 |
| Google Play Health Content and Services; User Data; Data safety; AI-Generated Content; Photo and Video Permissions | Yes | Health apps declaration (not a medical device), prominent disclosure + affirmative consent (S2), Data safety per tier, in-app flag on every AI output (`FeedbackRow`), no `READ_MEDIA_*` | §11 |
| HIPAA | No (consumer-chosen app; no covered entity/business associate relationship) | Re-analyze if any clinic, plan, school or legal-aid grantee contracts the operator to deploy it | §13.1 |
| FTC Health Breach Notification Rule (16 CFR 318) | Treat as applicable | Primary controls: paid tier only, nothing persisted server-side, no analytics SDKs; incident-response plan with 60-day notice; counsel opinion before launch | §13.2 |
| FTC Act §5 (literal truth of privacy and accuracy claims) | Yes | Every privacy sentence is in §17 and CI-tested against `en.json`; no "human-reviewed", "encrypted by the app", "never sees" claims | §17 |
| State consumer-health / privacy law (WA MHMDA, CA CPRA sensitive PI incl. immigration status and health; others) | Likely for some users | Consent = S2; purpose-limited processing; no sale; on-device deletion; policy sections; never ask immigration status; counsel confirms thresholds | §13.3; D-24 |
| FDA (FD&C §520(o)(1)(D) display/transfer exclusion) | Excluded if outputs stay descriptive | "This paper says X. Ask your clinician what it means for you."; phrasing lint blocks interpretation verbs | §6.3 |
| Unauthorized practice of law (state law; *Upsolve v. James*, 2d Cir. 2025) | Yes | Generic information about the paper type; no individualized advice, no filing recommendation, no outcome prediction, no form drafting; referrals only to DOJ rosters / EOIR pro bono list / vetted DB | §6.1 |
| WCAG 2.2 AA (floor), Apple HIG, Material a11y; Section 508 / ADA Title II only if a government body deploys | Yes | "Big Calm" tokens (D-28): 18 base, 56/72 pt controls, 7:1 body, icon+word+color, per-pane language, live regions, RTL/bidi | §15 |
| COPPA | No (18+, not directed at children) | No child-directed features; school papers are framed for parents/guardians | §4.6 |

---

## 2. Data flow (text)

### 2.1 The path of a paper

1. **Device.** The user photographs or picks a paper. The client resizes to 1600 px longest edge, JPEG quality 0.8, strips EXIF (`features/scan/compress.ts`). The user may draw black rectangles ("Hide parts", S5). On **web** the rectangles are burned into the JPEG on a `<canvas>` before upload (`masks_applied_client_side: true`, `pages[].masks: []`). On **native** the rectangles are sent as normalized `MaskRect`s.
2. **Transport.** HTTPS only. JSON body with base64 pages (no multipart). Headers: `X-Request-Id` (random UUID), `X-Install-Id` (random per-install UUID, rotatable), `X-Consent-Version` (the consent version the user accepted), optional `X-App-Token`. No cookies, no account, no device identifiers other than the app-generated install id.
3. **API (`apps/api`, in memory only).** Pure ASGI middleware, outermost first: CORS → request context (request id, `X-Contract-Version`/`X-Data-Use-Tier` headers, optional `X-App-Token` check, content-free access log) → unhandled-error guard (content-free `500 internal`) → body limit (413). On the gated routers, FastAPI dependencies then run the consent check (428) → tier gate (403) (`consent_and_tier_gate`, exported from `middleware.py`, because it must read `demo_sample_id` from the body; only a `demo_sample_id` that names a bundled fixture is exempt — CL-031 — and on `unpaid`/`mixed` not when the request carries typed text, `/v1/chat` or a troubleshoot `user_goal`) → rate limit (429, `ratelimit.rate_limit_dependency`) — BUILD_PLAN §4.1. `analysis/uploads.py` validates MIME by magic bytes and enforces caps (D-21). `analysis/redaction.py` burns native masks with Pillow **before** any model call and before thumbnails. Bytes live only in the request's memory and are released when the response is sent. No temp files. No database of content.
4. **Gemini (paid project keys).** `client.aio.models.generate_content` with `response_schema`; text prompt then media parts. On the paid tier Google does not use prompts or responses to improve products; Google keeps a short abuse-detection log "for a limited period of time". Optional AI Studio developer logging is **off**. The Files API is **never** used (48-hour retention). If the Interactions provider is ever enabled (LATER), every call sets `store=False`.
5. **API post-processing.** Verification, contact filter, deadline rules, urgency, scam, emergency lexicon, phrasing lint, injection re-run, SSN masking (`***-**-1234` always; A-/receipt numbers only when `hide_id_numbers`), disclaimers. Result returned; nothing written.
6. **Device.** The result is shown. Saving to the vault is **opt-in** ("Save" → "Whose paper is this?"). Chat re-sends the stored transcript text (never images). Quick sheets are rendered from the result. Reminders store only demand label + date.

Trust boundary = the device. **The server holds nothing a subpoena could return** (ARCHITECTURE §1).

### 2.2 What leaves the device, per endpoint

| Endpoint | User content leaving the device | Forwarded to Gemini | Stored server-side | Audit log fields (allow-list only) |
|---|---|---|---|---|
| `GET /health`, `GET /v1/config` | none | no | no | route, status, latency |
| `GET /v1/language-packs/{tag}` | language tag | no | no (bundled/cached UI strings served) | route, status |
| `POST /v1/language-packs` | the typed language name (≤ 60 chars) | yes — the name only, fast tier | generated UI-string pack in `var/langpacks/` (no user content) | route, status, model, tokens |
| `POST /v1/analyze` | page bytes (masked), rotation, `target_language`, `state`, `zip3`, `document_hint`, `preferences` (tone, `calendar_notes`, date format), `analysis_id`, `client_platform` | yes — prompt + masked page bytes + preferences text (never `state`/`zip3` as identifiers; they appear only as "state: VA" context) | **no** | ARCHITECTURE §"Logging" allow-list (counts, sizes, enums, latencies, token counts, `install_id_hash`) |
| `POST /v1/troubleshoot` | screenshot bytes, `user_goal` (≤ 300), `mode`, `portal_hint` | yes | **no** | same allow-list |
| `POST /v1/chat` | `AnalysisContext` (transcript blocks, demands, summary; ≤ 60k chars), ≤ 8 prior messages, the question (with a known `demo_sample_id` the server ignores the sent context and rebuilds it from the fixture; the question and history are still the reader's words) | yes — text only; images are never re-sent | **no** | same allow-list |
| `POST /v1/resources/match` | tags, doc type, `state`/`county`/`zip3`, language, `institutions_as_written` (≤ 10 names printed on the paper), `scam_risk`, `emergency` | no (deterministic matcher) | no | route, status |
| `GET /v1/resources*`, `GET /v1/rules` | none | no | no | route, status |
| `POST /v1/quicksheet/pdf` | the localized quick-sheet text (contains the paper's dates, amounts, sender) and DB resource ids | no (reportlab in memory) | **no** | route, status, size |
| `POST /v1/feedback` | enums only (`kind`, `surface`, `language_tag`, `document_type`, `card_id`, `resource_id`, `app_version`, `platform`, `model_id`) — never text | no | counters in `var/feedback_counts.sqlite` | route, status |
| `GET /v1/demo/*` | none | no | no | route, status |
| `GET /v1/admin/keys` | none (operator) | no | no | route, status |

Sensitive-by-nature fields and their handling:
- `preferences.calendar_notes` (e.g. "Ramadan") can reveal religion. Device-only storage (AsyncStorage). Sent only inside the prompt for tone. Never logged. Settings copy (§4.5) says it travels with each paper.
- `state`/`zip3` are typed by the user in Settings, never inferred, never GPS, never a full ZIP (D-24). Only what the paper prints goes into `entities.geo` and the server truncates ZIPs to 3 digits.
- Immigration status is **never** asked, stored, inferred or sent as a field (D-24). No `status_hint`/`immigration_status_bucket` exists in the contract.
- SSN-like patterns are always masked in returned text; A-numbers/receipt numbers only when the user enables "Hide ID numbers in saved copies" (default off — receipt numbers are needed to check case status).

### 2.3 What is logged, and for how long

Server structured log (`logging_.py`) allows **exactly** these fields and drops any other key (a unit test enforces the allow-list): `ts, request_id, route, status, error_code, provider, model, tier, slot_index, quality, analysis_mode, latency_ms, input_tokens, output_tokens, thought_tokens, page_count, total_bytes, document_type, category, urgency_level, scam_risk, contacts_stripped, phrasing_rewrites, facts_total, facts_unverified, injection_suspected, target_language, detected_language, install_id_hash, client_platform, data_use_tier`.

These are content-free, but they are more than counts: each line records enums such as `document_type`, `category`, `urgency_level`, `scam_risk`, the languages and `install_id_hash`. The in-app notice therefore describes them as "short technical notes, like the kind of paper and how long it took", deleted after 30 days (`privacy.notice.what_we_keep`, §4.5); it must never say the server keeps "only counts" (CL-061; that phrase is in §17 `forbidden_phrases`).

Explicitly forbidden anywhere in logs, metrics, error messages, exception traces sent to any tool, or `ErrorBody.message`: document text, quotes, filenames, base64, model prose, prompts, `user_goal`, chat text, `calendar_notes`, `institutions_as_written`, raw install ids, API keys (`SecretStr`, masked to last 4 in `/v1/admin/keys` only), IP addresses outside the 7-day process log.

| Store | Contains | Retention | Owner |
|---|---|---|---|
| Structured audit log | allow-list fields above; `install_id_hash` = HMAC-SHA256(install id, `INSTALL_HASH_SECRET` + daily salt) | 30 days, then aggregate counters only | operator (Cloud Logging bucket retention set to 30 days) |
| Host process/request log (uvicorn access log **disabled**; Cloud Run request log) | method, path, status, latency, client IP | 7 days (set the `_Default` bucket or a dedicated sink to 7 days) | operator |
| `var/keypool.json` | key-slot state (no user data, no keys) | until reset | operator |
| `var/langpacks/` | generated UI-string packs | `LANGPACK_CACHE_TTL_DAYS` (180) | operator |
| `var/feedback_counts.sqlite` | counters keyed by enums | indefinite (aggregate, no content) | operator |
| Google Gemini paid tier | abuse-detection log of prompts/responses | Google-defined "limited period"; developer logging **off**; Files API never; Interactions `store=False` | Google |
| Device vault (native) | saved analyses, page JPEGs, checklist state, reminders, consent record | until the user deletes (per paper, per member, or "Delete everything") | user |
| Device prefs (AsyncStorage) | language, text size, region, preferences, consent record, install id, pack cache, server-config cache | until "Delete everything" | user |
| Web (default) | session memory only | tab close | user |
| Web (opt-in) | IndexedDB (unencrypted by the app) | until cleared; with "Clear when I close this tab" on, papers stay in memory only and are never written to IndexedDB (§9.5) | user |

No analytics, advertising, attribution or crash-reporting SDK is shipped (Apple 5.1.2(vi), 5.1.3(i); Play "no selling"). If crash reporting is ever added it MUST be configured to exclude screen content, breadcrumbs with text, and request bodies, and the store labels in §10–§11 MUST be revisited.

### 2.4 Hosting configuration that keeps §2.1 true

- Cloud Run (recommended) in the same Google account as the billed Gemini project: no persistent disk except an optional small volume for `var/`; request timeout 120 s; secrets (`GEMINI_KEYS`, `INSTALL_HASH_SECRET`, `ADMIN_TOKEN`, `APP_TOKEN`) from Secret Manager; request-body logging disabled (Cloud Run does not log bodies by default — do not add a logging proxy that does); Cloud Logging retention per §2.3; no Cloud Armor/CDN that caches POST responses.
- `ENV=production` MUST have: every slot `billing:true`; `ALLOW_UNPAID_KEYS` unset; `ALLOW_UNPAID_REAL_DOCUMENTS` unset (boot error otherwise); `LOG_LEVEL=info`; `CORS_ORIGINS` = the web host only.
- AI Studio project settings: developer logging OFF for every production project; confirm in the AI Studio logs page that no interactions are stored.
- A separate **demo instance** runs `AI_PROVIDER=mock` permanently (`data_use_tier: demo`).
- Web hosting (EAS Hosting or static host) serves `/privacy` as HTML (not PDF) at `PRIVACY_POLICY_URL`.

---

## 3. Data-use tier: what it means for users, stores and operators

| Tier (`X-Data-Use-Tier`) | When | Real papers allowed? | What the user sees (S2 badge + line, §4.2) | Store submission allowed? |
|---|---|---|---|---|
| `paid` | `AI_PROVIDER=gemini`, every slot `billing:true` | yes | "Paid service" badge; paid line | **yes** — the only tier a store build may point at |
| `unpaid` | any slot `billing:false` | **no** (403) — fixtures only | red badge "Test build — free AI key"; unpaid line; scan tiles disabled | **no** — release blocker; a store build whose `EXPO_PUBLIC_API_URL` resolves to an `unpaid`/`mixed` API fails the pre-launch checklist (§18) |
| `mixed` | some slots billed, some not | **no** (routed as unpaid) | same as unpaid | no |
| `demo` | `AI_PROVIDER=mock` | scans go to our server for sample matching only; no AI service | "Sample mode" badge; demo line | only as a clearly labelled demo build (`EXPO_PUBLIC_DEFAULT_SAMPLE_MODE=true`); not for public store release |
| `none` | gemini with zero slots (dev only) | no | treated as `unknown` | no |
| `unknown` (client only) | `GET /v1/config` unreachable | not until the tier is known — S2 "I understand, continue" is disabled, so consent cannot be recorded; with consent already recorded the scan CTA stays enabled and an offline scan can be saved on the device to read later (`review.read_later_cta`) or wait on S5 for the connection; nothing is sent while the API is unreachable and nothing is queued in the background (CL-064); samples enabled (PRODUCT_SPEC §5.3) | "Cannot confirm" badge; unknown line | n/a |

Operator attestation: `billing` in `GEMINI_KEYS` is a human statement that a Cloud Billing account is attached to that project; the SDK cannot detect it. `.env.example` says so. Falsely marking an unbilled key as billed would make every paid-tier privacy sentence false — treat it as a reportable incident (§13.2).

Dev-only bypass: `ALLOW_UNPAID_REAL_DOCUMENTS=true` (boot error in production) exists for synthetic test scans on free keys. Never use it with a real person's paper, even your own. Keyed demos and hackathon judging use fixtures or a photographed printed SAMPLE sheet only (D-29).

---

## 4. Consent and onboarding copy

### 4.1 S1b — "Adapting" state (language pack loading)

The English base string is fixed by the user's request (D-25):

- `langpack.adapting`: "Adapting system environment to your language..."
- `langpack.about_20s`: "About 20 seconds"
- `banner.partial_pack`: "Some words are in English."
- `state.lang_needs_internet`: "I need internet to add a new language. Choose one of these for now."

No consent is needed here: only the typed language name is sent (§2.2).

### 4.2 S2 — "What happens to your paper" (consent; Apple 5.1.2(i), Play prominent disclosure)

Shown before the first upload and again whenever `consent_version` from `/v1/config` changes or the tier differs from `tier_seen`. Layout: heading, tier badge, three pictogram lines, 18+ line, "Read more" link, three actions. Pictograms are not mirrored in RTL; every line has a speaker button.

- `consent.title`: "What happens to your paper"
- Tier badge labels (`TierBadge`): `consent.badge.paid`: "Paid service" · `consent.badge.unpaid`: "Test build — free AI key" (used for `unpaid` and `mixed`) · `consent.badge.demo`: "Sample mode" · `consent.badge.unknown`: "Cannot confirm"
- Line 1 (tiers `paid`, `unpaid`, `mixed`, `unknown`) — `consent.line1`: "Your photo is sent to Google's AI (Gemini) to be read. Our server does not keep it."
- Line 2 by tier:
  - `consent.line2.paid`: "Google does not use your paper to improve its products. Google keeps a short safety log for a limited time, then deletes it."
  - `consent.line2.unpaid` (red; icon + word, used for `unpaid` and `mixed`): "This test build uses a free AI key. Google may read and use what is sent. Do not send real papers. Sample papers only."
  - `consent.line2.demo`: "Sample mode. No AI service is contacted. Your photo is only compared with our sample papers and is not kept." (D-02 as revised 2026-09-27 — the only rendering that is literally true when a real photo is scanned in mock mode; the former "Nothing leaves this device" is retired and is a forbidden phrase in §17.)
  - `consent.line2.unknown`: "I cannot confirm how your paper would be handled right now. You can try a sample paper or come back later."
- Line 3 — `consent.line3`: "Papers you save stay only on this phone. You can delete everything any time." Web variant `consent.line3.web`: "Papers you save stay only in this browser, if you choose to keep them."
- "Hide parts" line (fourth small line): native, shown only when `features.hide_parts_server_masking` is true — `consent.line4.masks`: "Parts you hide are blacked out on our server before Google's AI sees them." Web — `consent.line4.masks_web`: "Parts you hide are blacked out on your device before anything is sent."
- 18+ — `consent.adults_only`: "This app is for adults 18 and older."
- Link — `consent.read_more`: "Read more" → opens the in-app notice (§4.5, `features/onboarding/PrivacyNotice.tsx`) whose last row links to `privacy_policy_url`.
- Primary (72 pt) — `consent.btn_continue`: "I understand, continue"
- Secondary — `consent.btn_not_now`: "Not now"
- Link — `consent.try_sample`: "Try a sample paper first"

Behaviour:
- `unknown`: "I understand, continue" disabled with `consent.unknown_hint`: "Come back when you have internet to confirm this.", so consent cannot be recorded while the tier is unknown; samples enabled. The S3 scan CTA is not disabled by `unknown` itself: without recorded consent a tap opens S2; with consent already recorded, scanning works and an offline scan can be saved to read later (`review.read_later_cta`) or wait on S5 for the connection; nothing is sent (PRODUCT_SPEC §5.3, CL-044(a)).
- `unpaid`/`mixed`: "I understand, continue" is **not shown** (there is nothing to consent to — real papers are blocked server-side and sample requests are exempt from consent); "Try a sample paper first" becomes the primary action, "Not now" stays. `PRODUCT_SPEC.md` S2 and J-J follow this.
- Consent record (device, AsyncStorage via `storage/kv.ts`): `{ "consent_version": "2026-10-01", "accepted_at": "2026-09-27T14:03:11Z", "tier_seen": "paid", "platform": "android" }`. Never sent to the server except as the `X-Consent-Version` header value.
- API: `X-Consent-Version` required on `/v1/analyze`, `/v1/troubleshoot`, `/v1/chat`; missing or older than `CONSENT_VERSION` → `428 consent_required`; the client re-shows S2. A request whose `demo_sample_id` names a bundled fixture is exempt; an unknown id is gated like no id (CL-031); on `unpaid`/`mixed` a sample request that carries typed text (every `/v1/chat` request, a non-blank troubleshoot `user_goal`) is gated like a real paper, and `/v1/config` `features.chat` is `false` (it equals `real_documents_allowed`), so the app shows `chat.unavailable_unpaid` in place of the chat box and sends nothing (Phase 2C). A chat with a known `demo_sample_id` never uses the client's context: the server rebuilds it from the fixture (`chat_pipeline.sample_context`).
- Backing out (Android back / swipe) equals "Not now" (Play: no consent by backing out).

### 4.3 "Not now" and sample mode copy

- Home line when consent is absent or withdrawn — `home.consent_needed`: "Scanning is off until you accept how your paper is handled. Tap to read it." (tapping the scan CTA opens S2)
- Sample explainer (before the sample list) — `demo.explainer`: "Sample papers are made up. They are not real people's papers. You can try everything with them. None of your papers or photos are sent."
- Sample-mode banner on Home in `demo` tier — `banner.sample_mode`: "Sample mode: the helper is not connected. Try the sample papers."; on a sample (S5 review of sample pages, S7, S9, S16) — `banner.demo_sample`: "This is a made-up sample paper. What you type is still sent to be answered." (2026-09-30: the former "Nothing of yours was sent" was false — a sample request carries the reader's settings, a chat question or troubleshoot goal typed about a sample reaches our server, and on the paid tier a sample chat question goes on to Google before consent, because the gate exempts known `demo_sample_id`s there; §9.1)
- Unpaid banner (dev builds) — `banner.unpaid_tier`: "Test build with a free AI key. Sample papers only."
- Offline line on Home — `home.offline_line`: "No internet. I can take the photo now and read it later."

### 4.4 Withdrawing consent (Settings → "How your data is handled")

- `btn.withdraw_consent`: "Stop sending papers" → sets consent to withdrawn, disables scan/chat/troubleshoot, then offers `settings.wipe_offer`: "Do you also want to delete everything saved on this phone?" with `btn.delete_everything`: "Delete everything on this phone" / `settings.keep_saved`: "Keep my saved papers".
- `btn.delete_everything`: "Delete everything on this phone" (double confirm). Dialog `wipe.title`: "Delete everything on this phone?" / `wipe.body`: "This removes all saved papers, members, reminders and settings from this phone. It cannot be undone." Buttons `wipe.confirm`: "Yes, delete everything" / `btn.cancel`: "Cancel". Removes DB, files, pack cache, consent record, install id, SecureStore items; cancels scheduled notifications (`storage/wipe.ts`).
- Web wording of the same action — `btn.delete_everything_web`: "Delete everything in this browser".

### 4.5 In-app privacy notice ("Read more" / Settings → "How your data is handled")

Plain-language, one screen, every line has a speaker button. Keys `privacy.notice.*`:

1. `privacy.notice.sent`: "When you read a paper, the photo goes to our server and then to Google's AI (Gemini). Our server does not keep it." — left out of the notice on the `demo` tier, where no AI service is contacted (`features/onboarding/PrivacyNotice.tsx`, Phase 2B).
2. Tier line (same strings as `consent.line2.*`).
3. `privacy.notice.what_we_keep`: "Our server does not keep your papers or photos. It keeps short technical notes, like the kind of paper and how long it took. It deletes them after 30 days. The notes never hold your paper's words, what you type, or the AI's words." (2026-09-30, CL-061: the structured log of §2.3 keeps per-request enums, so "only counts" was not literally true.)
4. `privacy.notice.device`: "Papers you choose to save stay on this phone, protected by your phone's own encryption. Turn on a phone passcode." Web — `privacy.notice.device_web`: "In this browser, papers are kept only while the tab is open, unless you turn on 'Keep on this device'. The app does not encrypt them."
5. `privacy.notice.hide_parts`: "You can black out parts of a page before it is read."
6. `privacy.notice.no_status`: "We never ask about your immigration status. We do not ask for your exact address. Only your state and the first 3 digits of your ZIP code, if you choose to give them."
7. `privacy.notice.no_ads`: "We do not sell your information. There are no ads and no trackers."
8. `privacy.notice.settings_sent`: "Your language, your state, your ZIP prefix and your calendar notes (like Ramadan) are sent with each paper so the answer fits you. They are not kept on our server."
9. `privacy.notice.install_id`: "Your phone sends a random code so one phone cannot use the service too much. The code is scrambled and forgotten after 30 days. You can reset it with 'Delete everything'."
10. `privacy.notice.feedback`: "When you tap 'Was this clear?' or 'Report a problem', we count it. We do not receive the text of your paper."
11. `privacy.notice.delete`: "You can delete one paper, one family member's papers, or everything, any time."
12. `privacy.notice.full_policy`: "Read the full privacy policy" → `privacy_policy_url`.

### 4.6 Age, children and shared phones

- The app is 18+ (Gemini terms; store ratings). The consent 18+ line is a statement, not an age-verification gate; no birthdate is collected.
- School papers are explained **to the parent or guardian**: prompts and copy say "your child's school", never address a student.
- Shared-phone defaults: saving is opt-in; lock-screen reminder text is generic; the clerk card hides vault navigation; "I want to hear it, not read it" mode and an earbuds tip (`tts.earbuds_tip`: "Plug in earbuds to listen privately.") support reading without a child interpreting.

### 4.7 Changing consent copy

Any change to a string listed in §17, to the privacy policy's data-flow section, to the tier logic, or to what leaves the device MUST: (1) bump `CONSENT_VERSION` (`YYYY-MM-DD`) in the API environment, (2) update `privacy_policy_url` content with a new "Effective" date, (3) update §17 and pass `test_privacy_claims.py`, (4) regenerate packs for the changed keys (`scripts/gen_packs.py --keys ...`). Clients re-show S2 automatically (D-02).

---

## 5. Fixed disclaimers (exact copy and placement)

The model never writes a disclaimer (D-17). The server sets `AnalysisResult.disclaimer_kind` from `category` (DOCUMENT_TAXONOMY §2 column `disclaimer_kind`) and adds secondary `disclaimers[]`; the client renders the pack string for each `DisclaimerKind` value. Keys and English strings below are the ones fixed in `PRODUCT_SPEC.md` §5.6 / Appendix A and are **exempt from the grade-5 readability check** (`test_readability.py` allow-lists these keys) because their wording was chosen against `docs/research/compliance.md` §3 (immi.org, LawHelp.org, NLM and Apple 1.4.1 / Play Health wording). Any change is a legal-review change (§18), not a copy edit.

### 5.1 Primary disclaimer per category

| `DisclaimerKind` | Categories (`DocumentCategory`) | Key | Exact English | Screens |
|---|---|---|---|---|
| `legal_information_only` | `immigration`, `court`, `civic`, `employment` | `disclaimer.legal_information_only` | "This is general information about this type of paper, not legal advice about your case. Only a licensed lawyer can advise you. For an immigration case, a DOJ-accredited representative can too." (Phase 2B rewrite: a DOJ-accredited representative practises immigration law only) | S7 header (item 5 in the S7 card order), S9 (with `chat.scope`), S15 first line under the title |
| `medical_information_only` | `medical` | `disclaimer.medical_information_only` | "This explains what your paper says. It is not medical advice. Ask your doctor, nurse or pharmacist what it means for you." | S7 header, S9, S15 — this line is the Apple 1.4.1 / Play Health "consult a professional" reminder and MUST be visible without scrolling on S7 for `medical` papers |
| `benefits_information_only` | `benefits` | `disclaimer.benefits_information_only` | "This explains what your paper says. It is not a decision about your benefits. Only the office that sent it can tell you what happens next." | S7 header, S9, S15 |
| `housing_information_only` | `housing` | `disclaimer.housing_information_only` | "This is general information about this type of paper, not legal advice. A housing lawyer or counselor can advise you about your home." | S7 header, S9, S15 |
| `general_information` | `school`, `tax`, `other`; every `TroubleshootResult`; the Help tab | `disclaimer.general_information` | "This is general information from your paper. It can be wrong. Check the highlighted words and confirm with the sender." | S7 header, S9, S15, S16 result footer, S11 footer (below `help.always`) |

Rendering rules (WP5/WP6): plain text, 16 pt minimum, `SpeakButton`, not collapsible, not a card; placed **above** Card 1 and **below** the urgency banner (S7 order item 5), so the first thing a reader hears after the date is the boundary. In clerk mode (S10) no disclaimer is shown — the card is a fixed template addressed to the clerk, not information for the user (D-18). On S8 (source viewer) none is shown: it displays the paper's own words. `document_type = other_notice` takes the disclaimer of its `category`; `unknown` takes `general_information`.

### 5.2 Secondary disclaimers and footers

| `DisclaimerKind` / element | Key | Exact English | Where |
|---|---|---|---|
| `ai_generated` | `footer.ai_generated` | "Made by a computer from your paper. It can be wrong. Check the highlighted words." | S7 footer (item 17), S16 footer; every AI surface carries it — this is the Prohibited-Use-Policy provenance line (§14) |
| `verify_with_sender` | `footer.verify_with_sender` | "Confirm dates and amounts with the sender." | S7 footer; S15 via `quicksheet.footer` |
| quick-sheet footer | `quicksheet.footer` | "Made with a computer from your paper. It can be wrong. Confirm dates with the sender. Made on {date}." | S15 preview and every PDF (native `expo-print` HTML and `POST /v1/quicksheet/pdf` `footer`) |
| `machine_translation` | `banner.machine_translated` | "This language was translated by a computer. It may have mistakes. Numbers and dates are kept as printed. Tap the speaker to hear it." | every screen while a `machine_translated` pack is active (D-25) |
| `degraded_model` | `banner.degraded_model` | "A faster helper read this paper. Check the highlighted words carefully." | S7/S9/S16 when `model_meta.quality == degraded` |
| `unpaid_tier_warning` | `banner.unpaid_tier` | "Test build with a free AI key. Sample papers only." | S3, S7 (red, icon + word) |
| `demo_sample` | `banner.demo_sample` | "This is a made-up sample paper. What you type is still sent to be answered." | S5 (sample pages), S7/S9/S16 when `model_meta.demo` |
| chat scope line | `chat.scope` | "I can only answer from this paper. This is information, not legal or medical advice." | S9, pinned above the message list on every visit |
| clerk-card boundary | (none) | the S10 template contains no advice; `clerk_need_en` is contact-filtered and phrasing-linted (D-18) | S10 |

### 5.3 The "what this app does not do" list (About, S17 item 9)

`PRODUCT_SPEC.md` §1.3 fixes seven sentences for the About screen but Appendix A assigns them no keys. WP8 asks WP0 (DECISIONS §14 CL-010) for keys `about.not.1` … `about.not.7` with the §1.3 sentences verbatim, in this order: does not diagnose or interpret lab values; does not say whether you qualify, what to file, or what will happen; does not draft, fill or format any official form or letter; does not invent phone numbers, websites, addresses or organization names; does not compute dates from memory; does not store papers on any server, log their content, or ask immigration status; does not send real papers to the AI on unpaid keys. Until the keys exist the About screen renders the disclaimers of §5.1 only.

### 5.4 Store and marketing copy

Store descriptions, screenshots and the web landing page (`docs/STORE_LISTING.md`) reuse §5.1 sentences verbatim where a boundary is stated and never use the words "advice", "diagnosis", "eligible", "guaranteed", "certified", "lawyer-reviewed", "doctor-approved" or "HIPAA". The tagline is "ProxyHealth AI — Your paper, explained." (DECISIONS §13). Screenshots come from fixtures only (SAMPLE watermark visible).

---

## 6. Information, not advice — the boundaries in operation

The product stance (DECISIONS §0, D-17) is "a paper decoder with a caseworker's manners". This section turns that into the four boundaries the code enforces: unauthorized practice of law (§6.1), chat refusals (§6.2), the FDA / "interpret or analyze" line for medical papers (§6.3) and no form drafting (§6.4). Enforcement points: prompts (`ai/prompts/**`, AI_PROMPTS §0 rule 1), `analysis/phrasing.py` + `data/safety/phrasing.yaml`, `analysis/contacts_filter.py`, `ChatAnswer.refusal_kind`/`refer_to_professional`, and the fixed disclaimers of §5. The client never softens or removes a refusal.

### 6.1 Unauthorized practice of law — the line per document type

Legal background (`docs/research/compliance.md` §3, all verified unless noted): USCIS — "Only an attorney or an accredited representative working for a Department of Justice recognized organization can give you legal advice"; FTC — everyone else "may help only with clerical tasks like typing or translating"; *Upsolve, Inc. v. James* (2d Cir. Sept 9 2025, likely) — New York's UPL statutes are content-neutral and may be applied to trained non-lawyers who give **individualized advice on a check-the-box court form**. UPL is state law and varies; the pilot states are Virginia and DC (RESOURCE_DB §11.8), and counsel confirms each new state (§18). The operative rule for every legal-adjacent type:

> **Information** = what this kind of paper is, what such papers ordinarily ask for, what the paper itself says, generic next steps that end in a referral. **Advice** = applying the law to this reader's facts: what to file, argue, choose or sign; whether they qualify; what will happen. The app does the first and never the second.

| `DocumentType` group | The app may say (grounded in the paper) | The app never says (phrasing lint patterns, D-17) | Referral target (`ReferTo` → resource ids, D-10) |
|---|---|---|---|
| USCIS notices: `uscis_receipt`, `uscis_rfe`, `uscis_noid`, `uscis_biometrics`, `uscis_interview`, `uscis_approval`, `uscis_denial`, `ead_related`, `green_card_related`, `tps_related`, `asylum_fee_notice`, `parole_related` | "This is a receipt/request from USCIS about form {form as printed}." "The paper says a response is due by {date as printed}." "Papers like this usually need a reply before the date." Fixed notices D-20 (`fixed.uscis_receipt_i765`, `fixed.asylum_fee_notice`). | "You should respond/appeal/refile", "you qualify for…", "you will be approved/denied", which evidence to send, whether to withdraw, anything about the reader's status | `lawyer_or_accredited_rep` → `eoir_roster`, `eoir_probono`, `immlawhelp`, `uscis_find_legal`; verification `uscis_contact` |
| Immigration court: `nta`, `hearing_notice`, `ij_decision`, `bia_notice`, `ice_checkin` | "The hearing date printed is {date}." "Missing a hearing can have serious results; the court decides." (calm, D-12 wording) "The paper says an appeal must be received within 30 days" **only when the paper prints it**; the estimate rule `bia_appeal_30d` shows formula + source (D-11). `fixed.address_change_multi_agency`. | whether to appeal, what relief to seek, "you will be deported", "you have a strong/weak case", advice about attending or not | `lawyer_or_accredited_rep` → `eoir_probono`, `eoir_roster`, `immlawhelp`; verification `eoir_hotline` |
| Civic / other court: `jury_summons`, `traffic_court` | `fixed.jury_summons` (reviewed, high-severity — the one place the app uses "must", because the citizenship box is a documented immigration trap, resources.md Warnings). "The paper lists a court date of {date} and a fine of {amount}." | whether to contest, plead or pay to avoid court; any immigration consequence beyond the fixed notice | `lawyer_or_accredited_rep` → `lawhelp`, `immlawhelp` (traffic matters can affect status — referral only) |
| Housing: `pay_or_quit`, `eviction_summons`, `lease`, `rent_increase`, `section8_recert`, `utility_shutoff` | `fixed.pay_or_quit` "This is not a court order. Only a court can make you leave."; `fixed.eviction_summons` "The court date on this paper is the date that matters. Go, or you can lose automatically."; "The lease says rent is {amount} due on {day as printed}." Never a computed answer period (D-11: no eviction rule is seeded). | "you don't have to leave", "you have X days to answer", whether to withhold rent, sign, or move | `housing_counselor` → `hud_counselor`, `lawhelp` (LSC note `status_note.lsc_restricted` + `help.lsc_alternative`), `liheap` for shutoffs |
| Employment: `w2_1099`, `i9`, `offer_letter`, `pay_stub` | "This form reports wages of {amount} as printed." "The paper says re-verification is needed by {date}." The EEOC/OSHA rules apply **only via a printed phrase** (DOCUMENT_TAXONOMY §2). | whether the employer broke the law, whether to sign the I-9, tax filing advice, "you are owed…" | `lawyer_or_accredited_rep` for immigration questions; workers' rights resources via tags `workers_rights`, `wage_theft` |
| Benefits: `medicaid_renewal`, `snap_notice`, `wic_notice`, `ssa_letter` | "The office asks for {document as printed} by {date}." "The paper does not say your coverage ended." (`not_in_document`) | eligibility ("you qualify"), appeal recommendations, income calculations | `benefits_office` → the sender's printed contact (labelled "from your paper"), `medicaid_state`, `211` |
| Medical: see §6.3 | | | `clinician` |
| Tax: `irs_notice`, `itin` | "The notice number printed is {as printed}; it says {amount} by {date}." `irs_scams` pinned. | how to respond to the IRS, whether the amount is right, filing status | `sender` + tag `tax_notice` (free tax helpers via DB) |
| School: `school_enrollment`, `immunization_notice`, `iep_504_notice`, `school_meals`, `report_card` | addressed to the parent/guardian (§4.6); "The school asks for {item} by {date}." `warn.schools_may_not_ask_status` from the DB. | legal rights conclusions ("the school must…"), medical advice on vaccines | `sender`; tags `school_enrollment`, `special_education`, `homeless_students` |

Rules that make the table hold:
1. **Professional word by category** (PRODUCT_SPEC §7.2) is fixed (`data/safety/phrasing.yaml` `professional_by_category` + `professional_by_document_type`): immigration and the immigration-court types (`nta`, `hearing_notice`, `ij_decision`, `bia_notice`, `ice_checkin`) → "a licensed lawyer or a DOJ-accredited representative"; other court and civic papers → "a licensed lawyer"; employment → "a licensed lawyer or a workers' rights office" (`w2_1099` → "a free tax helper or a tax professional"); housing → "a housing lawyer or counselor"; benefits → "the office that sent this paper"; tax → "the IRS or a free tax helper"; school → "the school office or a parent center". The model's `professional` plan steps end with that word; `tagging.py` maps to `ResourceTag`s; contacts come from the DB only.
2. **Never "notario", "consultant" or a paid directory as a referral.** `aila.never_show_with_tags = [scam_report]` (RESOURCE_DB §12.2); `status_note.not_endorsed` is shown on government rosters. The referral lines are "Only a licensed lawyer can advise you. For an immigration case, a DOJ-accredited representative can too." (inside `disclaimer.legal_information_only`) and "A licensed lawyer can advise you about your case. For an immigration case, a DOJ-accredited representative can too. Find one in Get help." (`chat.refer.lawyer_or_accredited_rep`) — rewritten in Phase 2B so they stay accurate for every category that uses them; the bundled translations of both keys are re-done in the same merge.
3. **No "must/should" verbs from the model.** The only "must" sentence in the product is the reviewed fixed notice `fixed.jury_summons`; the other reviewed imperatives are fixed notices (`fixed.eviction_summons` "Go, or you can lose automatically.") and DB `warn.*` keys — WP2's `phrasing.yaml` blocks "you should (file|appeal|apply|pay|sign|respond|attend)", "you must" (outside quotes), "you (do not|don't) have to", "does not require you to", "you qualify / are (not) eligible", "you will (be|get|win|lose)", "this means you have"; the golden set asserts the four reference rewrites of PRODUCT_SPEC §7.2.
4. **Individualized form help is out.** The app explains what a form asks for; it never tells the reader which box applies to them (the *Upsolve* fact pattern). "Show the clerk" (S10) exists so a human at the counter does that.
5. **State variation.** Deadline rules carry `source_url` and `valid_until` (D-11); no state-specific legal periods are hardcoded; Virginia's changing eviction statute is the worked example (resources.md Warnings). Counsel confirms the UPL framing for each pilot state before launch (§18.1).

### 6.2 What chat refuses, and the copy

`POST /v1/chat` is stateless and grounded (§3.7). The model answers only from `AnalysisContext`; the server classifies every turn into `RefusalKind` and, when refusing, sets `refer_to_professional`. The client renders the fixed template (PRODUCT_SPEC S9); if `answer` is non-empty (a warm acknowledgement or a grounded quote) it is shown first, the template second. Templates (Appendix A, byte for byte):

| `refusal_kind` | Triggers (examples the golden chat set asserts) | Key → exact English | Default `refer_to_professional` |
|---|---|---|---|
| `eligibility` | "Do I qualify?", "Am I eligible for Medicaid/asylum/charity care?", "Will they approve me?" | `chat.refusal.eligibility` → "I cannot say whether you qualify. The paper says what it says; a professional can tell you what it means for you." | by category (§6.1 table) |
| `filing_advice` | "Should I appeal?", "What should I send?", "Should I sign this?", "Should I go to the hearing?" | `chat.refusal.filing_advice` → "I cannot tell you what to file or send. I can explain what the paper asks for." | `lawyer_or_accredited_rep` / `housing_counselor` / `benefits_office` |
| `outcome` | "Will I be deported?", "Will I lose my apartment?", "Will I win?" | `chat.refusal.outcome` → "I cannot predict what will happen. No one can promise a result." | by category; plus `distress_acknowledged` when the question shows fear |
| `medical_interpretation` | "Is my potassium dangerous?", "Is this medicine safe with my other pills?", "Do I have diabetes?" | `chat.refusal.medical_interpretation` → "I cannot say what this means for your health. Ask your doctor, nurse or pharmacist." | `clinician` |
| `drafting` | "Write my appeal letter", "Fill in the form for me", "Translate this into a letter to the judge" | `chat.refusal.drafting` → "I cannot write letters or fill in forms. A professional or the office itself can help with that." | by category |
| `contact_request` | "What is USCIS's phone number?", "Give me a lawyer's number", "Where is the office?" (when not printed on the paper) | `chat.refusal.contact_request` → "I only share phone numbers and websites printed on your paper or checked by a person. See Get help nearby." | `none` + `btn.get_help` |
| `out_of_scope` | questions about another paper, news, general law, the model itself | `chat.refusal.out_of_scope` → "That is outside this paper. I can only help with what is written here." | `none` |
| `none` with `not_in_document: true` | a fair question the paper does not answer ("Does my son lose Medicaid?") | `chat.not_in_document` → "The paper does not say." + referral template | by category (`chat.refer.*`) |

Rules: a refusal never lectures, never repeats the word "cannot" more than once per bubble beyond the template, and always leaves a door open (`btn.get_help`, `suggested_questions`). Refusals are still phrasing-linted and contact-filtered (`contacts_stripped` counts). The emergency lexicon runs on every question (§7); `safety.emergency` opens S19 over the chat before any answer. Refusal counts are not logged per user (only `route`/`status` — §2.3); `FeedbackRow surface=chat` remains under refusal bubbles so a wrong refusal can be flagged (Play flag control, §11.4).

### 6.3 Medical papers — the FDA "interpret or analyze" boundary

FD&C Act §520(o)(1)(D) excludes from the device definition software intended to "transfer, store, convert formats, or display" medical data **unless** it is intended "to interpret or analyze clinical laboratory test or other device data" (`compliance.md` §2, likely). The Gemini terms separately forbid use "to provide medical advice" or in a manner requiring regulatory clearance (§14). ProxyHealth AI therefore stays on the display side:

| Allowed (display / plain-language description) | Forbidden (interpretation / advice) |
|---|---|
| "The paper lists potassium as H (high) next to the normal range 3.5–5.1." | "Your potassium is high, which can be dangerous." |
| "The label says: take 1 tablet by mouth twice a day. Refills: 2. Discard after {date}." | "You should take this with food", "this is safe with your other medicine", what the medicine treats |
| "This is a bill from {sender as printed} for {amount}. It says financial assistance exists for households under 400% of the poverty level." | "You qualify for charity care." |
| "The letter says the plan denied {service as printed} and that an appeal can be asked for within 180 days of the notice." | "You should appeal; you will probably win." |
| "The discharge paper lists a follow-up on {date} and says to call if {symptom as printed}." | triage of the reader's current symptoms (the emergency card is fixed copy, §7) |
| glossary: administrative words only — copay, deductible, EOB, prior authorization, refill, generic, in-network | glossary: what a drug does, what a diagnosis code means for the reader, whether a value is normal |

Enforcement: `medical_information_only` disclaimer (§5.1) on every medical result; `phrasing.yaml` medical patterns "your (results|levels|numbers) (are|show|mean)", diagnosis verbs ("you have", "this indicates", "suggests you"), dosing verbs ("you should take", "increase/decrease", "stop taking"), safety verbs ("safe", "dangerous", "normal for you"); one `MODEL_FAST` rewrite with "The paper says X. Your doctor, nurse or pharmacist can tell you what it means for you." then the fixed hedge (D-17); chat `medical_interpretation` refusal; `refer_to_professional = clinician` for every medical follow-up; prompts (WP2, AI_PROMPTS) say "describe what is printed; never say what it means for the reader's health". The golden fixtures `prescription_label`, `insurance_denial_180d` and `inova_final_notice` assert zero interpretation sentences. The Apple 1.4.1 "check with a doctor" reminder and the Play "consult a healthcare professional" reminder are the same fixed sentence, shown in the UI (not only in the policy). FDA's 2026 comment period on excluded software (compliance.md §2) is tracked in §19.

### 6.4 No form drafting

The model is never asked to draft, fill, format or "help complete" any official form, letter, appeal, affidavit or e-mail (D-17; Play's AI-generated-content policy treats "AI-generated official documentation that enables dishonest behavior" as prohibited — compliance.md §1, likely; it also invites notario-style misuse). Concretely: no prompt contains the words draft/write/compose a letter; `ChatModelOut` has no free-form document field; `drafting` requests return `chat.refusal.drafting`; the quick sheet (S15) is a **summary for the reader** with fixed headings and DB contacts, never addressed to an agency and never formatted as a form; the clerk card (S10) is a fixed template with one linted need-line, addressed to a human clerk, never to an agency by mail. "Questions you can ask them" (`questions_to_ask`) are questions, not statements, and carry no contacts. `btn.copy`/`btn.copy_text` copy text the reader may paste anywhere; that is the reader's act, and the copied text still carries `quicksheet.footer` when it is the quick sheet.

---

## 7. Emergency triage copy (fixed, keyword-triggered in every bundled language — D-14)

**Copy is fixed and lives only in `en.json` (packs translate) and, as DB entries, in `data/resources/national_crisis.yaml`**; `tests/unit/test_loader.py::test_emergency_numbers_match_fixed_copy` keeps the digits identical (RESOURCE_DB §12.1). The model never writes any of it; if model text contains these digits, `contacts_filter.py` strips them anyway (D-10). Numbers are verified official numbers (`compliance.md` §3, `resources.md` §1G).

| Row (S19 order) | Key → exact English | Buttons (72 pt) |
|---|---|---|
| title | `emergency.title` → "Need help now?" | — |
| 911 | `emergency.911` → "If someone is in danger or very sick, call 911." | `btn.call_911` "Call 911" (`tel:911`) |
| 988 | `emergency.988` → "If you are thinking about hurting yourself, call or text 988. It is free and private." | `btn.call_988` "Call 988" (`tel:988`), `btn.text_988` "Text 988" (`sms:988`) |
| poison | `emergency.poison` → "If someone swallowed something dangerous, call Poison Help 1-800-222-1222." | `btn.call_poison` "Call Poison Help" |
| DV | `emergency.dv` → "If someone at home is hurting you, call 1-800-799-7233 or text START to 88788." | `btn.call_dv` "Call the helpline", `btn.text_dv` "Text START to 88788" (`sms:88788?body=START`) |
| note | `emergency.free_us` → "These numbers are free and work anywhere in the U.S." | `emergency.more_help` "More help near you" → S11 with `emergency: true` (crisis entries forced first; `trafficking` appears there, not on the card) |
| context (triggered only) | `emergency.triggered_by` → "I saw words about {kinds} on this paper. If this is happening now, use these numbers." with `{kinds}` from `emergency.kind.*` (chest pain / trouble breathing / overdose / poison / hurting yourself / stroke / heavy bleeding / a severe allergic reaction / violence) | `btn.close` |
| web desktop | `emergency.desktop_note` → "Use a phone to call." | numbers shown large as text |

**Trigger.** `analysis/emergency.py` runs `data/safety/emergency.yaml` over transcripts (`original_text`), `screen_text` + `user_goal` (troubleshoot, CL-003) and every chat question, plus the model's `emergency_terms_found`. Any hit → `Safety.emergency = true`, `emergency_kinds` ⊆ the nine kinds above → the client shows S19 **first**: inline as S7 card 1 (not collapsible, live region `a11y.emergency_shown`), as a modal over S9/S16, and via `need.crisis` on S11. `urgency.level = emergency` (D-12) with headline `urgency.emergency.headline`. Bias: **over-trigger**; a false positive costs one dismiss, a false negative may cost a life. Discharge instructions that merely list warning signs will trigger — that is accepted, and `emergency.triggered_by` explains why.

**Lexicon file schema** (`data/safety/emergency.yaml`, WP2; as built, CL-021(c)): `{ version, kinds: [chest_pain, breathing, overdose, poison, self_harm, stroke, bleeding, allergic, violence], fallback_languages: [en, es], languages: { <tag>: { reviewed_by: str|null, reviewed_on: date|null, match: word|prefix|substring, proclitics: [letters…] (optional), exclude: [phrases…], terms: { <kind>: [phrases…] } } } }` (seed `version: "2026-10-01"`). Matching is case-insensitive after NFKC, quote/dash unification and removal of zero-width joiners (Persian ZWNJ: spaced, joined and ZWNJ spellings match alike); Arabic-script letters people type interchangeably are folded on both sides (hamza-carrying alefs → ا, Arabic yeh / alef maksura ↔ Persian yeh, Arabic ↔ Persian kaf, teh marbuta → ه; harakat and tatweel dropped), so "انتحر" matches "أنتحر". `proclitics` (Phase 2C; `ar`: و ف ب ل ك) are one-letter prefixes written attached to the next word: up to two may stand before a term's first word, so "ولا أستطيع التنفس" and "بألم في صدري" match; the same round added missing Arabic chest-pain/breathing/violence terms and Dari/Farsi beating terms. `match` per language: `word` — whole-word (Latin scripts; a term ending in `*` also matches longer words); `prefix` — the term must start a word but may continue (inflecting non-Latin scripts); `substring` — anywhere (scripts written without spaces between words: `zh-Hans`, `zh-Hant`, `my`, and Korean, whose particles attach to the word). `exclude` phrases (resource names printed on ordinary papers such as "Poison Control", and label boilerplate such as "If swallowed") are removed from **printed** text only (transcripts, `screen_text`), never from what the user typed (chat question and earlier user turns, troubleshoot `user_goal`): "should I call poison control?" typed by the reader still fires. What the user typed runs through **every** bundled language's list; chat runs it before the model call, and when that call is blocked or fails after a hit the server still answers with the fixed `emergency.*` lines and `safety.emergency: true` (API_CONTRACT §3.7, Phase 2C). `fallback_languages` (default `[en, es]`) are the lists run for a language that has none. Every one of the 26 bundled tags (Tier 1: en, es, zh-Hans, zh-Hant, vi, tl, ar, ht, pt-BR, ru, uk, ko, fr; Tier 2: prs, ps, fa, ur, hi, pa, bn, so, sw, am, my, ne, rw) MUST have a list at launch, `reviewed_by: null` allowed; a target or detected language without a list falls back to `en` + `es` and sets `warnings: [emergency_lexicon_unavailable]` → chip `warning.checks_unavailable`. Native-speaker review of Tier 1/2 lists is a launch gate for the languages marketed at launch (DECISIONS Q6; §18.3); unreviewed lists still ship because absence is worse than imperfection.

**Tests.** `test_emergency.py`: one positive and one negative phrase per kind per bundled language; the English negative set includes common false-friend words ("bleeding-edge" is not required to pass — over-trigger is fine); `test_fixtures_golden.py` asserts `safety.emergency == false` for all 18 fixtures except any fixture WP7 marks `expects_emergency`. Manual: S19 opens from `home.need_help_now` on every screen in LTR and RTL; VoiceOver reads numbers digit-grouped.

---

## 8. Scam and impersonation warnings (D-13)

Sources: USCIS Common Scams, FTC "How to avoid immigration scams", SSA and IRS scam pages, DHS OIG hotline (`resources.md` §1I, §4; `compliance.md` §3 — verified). Facts the copy relies on: official sites and e-mails end in .gov; USCIS "will never ask you to pay fees to a person on the phone or by e-mail" and does not accept Western Union, MoneyGram, PayPal, Venmo or gift cards; ICE does not phone people to warn of arrest; SSA never demands gift cards or crypto or threatens arrest; USCIS forms and accounts are always free; a "notario" is not a lawyer in the U.S.

**Scoring is code** (`analysis/scam.py` + `data/safety/scam.yaml`, DOCUMENT_TAXONOMY §6): model `red_flags[].kind` (enum only) plus regexes on the transcript → `scam_risk ∈ {none, possible, likely}` and `scam_reasons[]` fixed keys. The model never labels a sender a scammer; the app never asserts a paper is genuine.

| Surface | Fixed copy (key → exact English) | Contacts shown |
|---|---|---|
| `likely` card (S7 position 2, S16 first, S11 `scam_report` forced first) | `scam.card.likely` → "Scam risk: likely — ICE, USCIS, SSA and the IRS never demand payment by phone, gift card, wire, or app. Do not pay. Report it:" | `dhs_oig.phone` (1-800-323-8603) and `ftc_reportfraud.url` read from the DB via `well_known_ids.scam_card_phone/url` — never typed into copy |
| `possible` card | `scam.card.possible` → "Some things in this paper look like a scam. Be careful. Do not pay or share ID numbers until you check with the real office." | `national_fallbacks` gains `ftc_reportfraud`, `dhs_oig` |
| reason chips (one per `scam_reasons` key) | `scam.gift_card` "Asks for gift cards" · `scam.wire_transfer` "Asks for a wire transfer" · `scam.payment_app` "Asks for a payment app" · `scam.crypto` "Asks for cryptocurrency" · `scam.arrest_threat` "Threatens arrest" · `scam.deportation_threat` "Threatens deportation" · `scam.guaranteed` "Promises a guaranteed result" · `scam.notario` "Mentions a \"notario\"" · `scam.non_gov_domain` "Website is not .gov" · `scam.expedite_fee` "Charges to go faster" · `scam.fee_for_free_form` "Charges for a free form" · `scam.urgency_pressure` "Pushes you to hurry" · `scam.impersonation` "Pretends to be a government office" | each chip has a `source_quote` crop when the flag came from the model (verified) |
| red-flag cards from the model | `RedFlagKind` ∈ `scam_payment_method`, `urgency_pressure`, `impersonation`, `notario`, `fee_for_free_form`, `guaranteed_result`, `unusual_contact` → `text` + `source_quote`; unverified flags are dropped, never shown | — |
| credential guard (S16 always; red when `asks_for_credentials_or_payment`) | `troubleshoot.credential_guard` → "Never type passwords, card numbers or ID numbers into this app. I will never ask for them."; `troubleshoot.credential_detected` → "This screen asks for a password or payment. Only type them on the official website, never here." | `troubleshoot.ask_person` → S11 |
| sender-specific pages | `uscis_scams` (immigration), `irs_scams` (`irs_notice`), `ssa_scams` (`ssa_letter`), `ftc_immigrant_scams` (14 languages), `uscis_forms_free` | DB pins (RESOURCE_DB §4.5, §12.2) |
| verify-a-helper (`notario` flag) | `eoir_roster`, `uscis_find_legal` + checklist `prepare.bring_name_of_helper` | DB |
| user feedback | `feedback.kind.scam_missed` "This looks like a scam but the app did not say so" → counter feeds the regex review (PRODUCT_SPEC §11.4) | — |
| evidence | `btn.save_evidence` "Save as proof" stores the screenshot in the vault under `vault.title_scam_check` "Scam check" (device only) | — |

Rules: (1) wording is "likely"/"possible", never "this is a scam" or a named accusation — the sender may be a real agency with a bad letter; (2) the card precedes Card 1 so a frightened reader sees "Do not pay" before any deadline; (3) urgency floors still apply — a scam-flagged `nta` stays `high` (the paper might be real); (4) in `demo` tier the fixture `scam_gift_card_letter` shows the full path; (5) no scam copy names a payment brand as a chip except the generic wording above (brands appear only inside quoted `source_quote`); (6) the D-13 regex list (gift card, Western Union, MoneyGram, Zelle/Venmo/PayPal/Cash App, Bitcoin, "pay to avoid arrest/deportation", "guaranteed", "notario", non-.gov domain near an agency name, "expedite for a fee") is reviewed quarterly against USCIS/FTC pages (RESOURCE_DB §9 link check cadence).

---

## 9. Data flow, retention and logging — the detailed view

§2 gives the path and the per-endpoint table; this section adds what an auditor, a store reviewer or counsel asks next.

### 9.1 What leaves the device, per tier

| Tier | Real paper bytes | Where they go | Who can see them | User-visible statement |
|---|---|---|---|---|
| `paid` | yes, after consent | our API (memory only) → Gemini Paid Services | our server process for the request's lifetime; Google's abuse-detection log "for a limited period of time" (gemini.md §3) | `consent.line1` + `consent.line2.paid` |
| `unpaid` / `mixed` | **never** — `403 unpaid_tier_real_documents_disabled`; only `demo_sample_id` requests, whose bytes are loaded from disk | fixture bytes → Gemini Unpaid Services (may be read by Google reviewers — fixtures are synthetic), with the settings sent alongside (language, `state`/`zip3`, `preferences`). **Typed text never reaches these keys**: a demo request that carries it — `/v1/chat` (client analysis context, history, question) or a troubleshoot `user_goal` — is gated like a real paper on these tiers (428 without consent, then 403; `consent_and_tier_gate`, SEC-01/02 fix 2026-09-30), and a sample troubleshoot never puts the typed goal into the prompt on any tier. `features.chat = real_documents_allowed = false`, so the app replaces the S9 box and S7's Ask prompts with `chat.unavailable_unpaid` (Phase 2C) | Google | `consent.line2.unpaid`; continue button hidden |
| `demo` | a photographed page is posted to our API for dHash matching only, then released | our API memory; no AI service | our server process only | `consent.line2.demo` |
| `unknown` | nothing while the tier is unknown (S2 Continue disabled; a scan by a user who already consented stays on the device — saved to read later or waiting on S5 — and is not sent; CL-044(a)) | — | — | `consent.line2.unknown` |

Always, on every tier: `X-Install-Id` (random UUID, HMAC-hashed server-side), `X-Consent-Version`, `X-Request-Id`, `target_language`, `state`/`zip3` if set, `preferences` (tone, calendar notes, date format), `client_platform`, `analysis_id`, `document_hint`, `hide_id_numbers`, `user_goal` (troubleshoot), the question and `AnalysisContext` (chat), feedback enums. Never: names, e-mail, phone, GPS, full ZIP, immigration status, device identifiers, advertising ids, contacts, photo-library metadata (EXIF stripped client-side), account data (there are no accounts).

### 9.2 Server-side state (`var/`, git-ignored) and everything else that persists

| Store | Content | Contains user content? | Retention | Owner |
|---|---|---|---|---|
| `var/keypool.json` | slot states, cooldowns, counters | no | until reset | operator |
| `var/langpacks/<tag>--<version>.json` | generated UI strings (from `en.json`, not from users; the typed language *name* is not stored) | no | `LANGPACK_CACHE_TTL_DAYS` = 180 | operator |
| `var/feedback_counts.sqlite` | counters keyed by `FeedbackKind × FeedbackSurface × language_tag × document_category × document_type × card_id × resource_id × app_version × platform × model_id` | no (enums and ids only; `card_id` is `d1`/`s2`-style) | indefinite (aggregate) | operator |
| structured log (Cloud Logging) | the 31-field allow-list of §2.3 | no | 30 days → aggregates | operator |
| Cloud Run request log | method, path, status, latency, IP | no | 7 days | operator |
| Secret Manager | `GEMINI_KEYS`, `INSTALL_HASH_SECRET`, `ADMIN_TOKEN`, `APP_TOKEN` | no | operator lifecycle | operator |
| Google Gemini | prompts + responses in the abuse log (paid); nothing in developer logging (OFF); nothing in Files API (never used); Interactions `store=False` (LATER) | yes, transiently, at Google | Google-defined "limited period" | Google |
| nothing else | there is no database of analyses, no object store of images, no temp files (`test_redaction.py` patches `open` for write modes; DoD #11 grep) | — | — | — |

Consequence for rights requests and subpoenas: the operator cannot retrieve, correct or delete any user's paper because none exists server-side; the only user-linked datum is `install_id_hash`, which is daily-salted and useless without the device. The privacy policy (§16) says exactly this.

### 9.3 Content-free logging — the rule and its tests

`logging_.py` accepts **exactly** `ts, request_id, route, status, error_code, provider, model, tier, slot_index, quality, analysis_mode, latency_ms, input_tokens, output_tokens, thought_tokens, page_count, total_bytes, document_type, category, urgency_level, scam_risk, contacts_stripped, phrasing_rewrites, facts_total, facts_unverified, injection_suspected, target_language, detected_language, install_id_hash, client_platform, data_use_tier` and drops any other key (`test_logging_allowlist.py`, WP1). Forbidden everywhere (logs, metrics, `ErrorBody.message`, exception traces, alerts, crash reporters — none shipped): document text, quotes, filenames, base64, prompts, model prose, `user_goal`, chat text, `calendar_notes`, `institutions_as_written`, raw install ids, keys (`SecretStr`), IPs outside the 7-day host log. Exception handlers (`errors.py`) log `error_code` + `request_id` only; Pydantic validation errors are reduced to field paths (no values). SHOULD (WP1, cross-WP need): `settings.py` refuses `LOG_LEVEL=debug` in `ENV=production`.

### 9.4 On-device storage and encryption, per platform (D-22, D-23)

| Platform | Vault | Protection the app can truthfully claim | Not claimed (LATER / verify) |
|---|---|---|---|
| iOS | `expo-sqlite` `proxyhealth.db` + JPEGs under `Paths.document/vault/<doc_id>/`; `vault_key` in Keychain (`WHEN_UNLOCKED_THIS_DEVICE_ONLY`) | iOS Data Protection encrypts app files at rest when a passcode is set (platform default class; general platform knowledge, not in the research files) → copy: "protected by your phone's own encryption. Turn on a phone passcode." | `NSFileProtectionComplete`, SQLCipher, iCloud-backup exclusion of the vault directory — **verify in the first EAS dev build**; until then not claimed and iOS submission is gated by §10.2 (5.1.3(ii)) |
| Android | same layout in internal storage; `vault_key` in Keystore-backed `expo-secure-store`; `android.allowBackup: false` | app-private internal storage; file-based encryption on modern Android (platform default); no cloud backup of the vault | SQLCipher; PIN lock (SHOULD) |
| Web | memory by default; IndexedDB only after `vault.web_keep_confirm`; no secrets (`secure.web.ts` shim) | nothing — copy says "The app does not encrypt them." | — |

Never in copy (forbidden phrases, §17): "encrypted by the app", "end-to-end encrypted", "SQLCipher", "backed up". Small preferences in AsyncStorage (unencrypted, nothing sensitive: language, text size, region, preferences, consent record, install id, pack cache, server-config cache).

### 9.5 Wipe (`storage/wipe.ts`) — order and proof

1. cancel every scheduled notification (`expo-notifications`), 2. delete `Paths.document/vault/` recursively, 3. delete `proxyhealth.db` (+ `-wal`, `-shm`), 4. delete SecureStore items (`vault_key`, PIN verifier), 5. clear `kv` (settings, consent record, pack cache index, server-config cache; there is no feedback queue — PRODUCT_SPEC §11.3), 6. generate a new install id, 7. restart at S1. Per-paper and per-member deletes remove rows, files, checklist state, chat history (`meta` `chat:<doc_id>`) and reminders (cancelling their notifications). Web: memory cleared; IndexedDB `proxyhealth` deleted. With `settings.web_clear_on_close` on, papers are never written to IndexedDB at all — they live in memory only, `pagehide` clears that memory synchronously, and any leftover `proxyhealth` database is deleted at the next start before anything is loaded (`storage/vault.web.ts`; an IndexedDB delete started on `pagehide` does not reliably finish, so the earlier "wipe on pagehide" design could bring papers back on a shared computer). Proof: `storage.native.test.ts` / `storage.web.test.ts` assert an empty state after wipe (PRODUCT_SPEC §15). Reminders keep only `demand_id`, `fire_at`, `notification_id`, `detail_opt_in`; the OS notification body is `notif.generic_body` unless `detail_opt_in`.

---

## 10. Apple App Store declarations

Source: `docs/research/compliance.md` §1 (guidelines verified 2026-09-23). Store text lives in `docs/STORE_LISTING.md` (WP8); this section fixes the answers. A store build MUST point at a `paid`-tier API (§3).

### 10.1 Guideline-by-guideline

| Guideline | Requirement | ProxyHealth AI control | Proof |
|---|---|---|---|
| 1.4.1 Medical | remind users to check with a doctor; expect greater scrutiny | `disclaimer.medical_information_only` on S7/S9/S15 for `medical`; `chat.refusal.medical_interpretation`; §6.3; Notes for Review name the screen | golden fixtures `prescription_label`, `insurance_denial_180d` |
| 2.3.1 Accurate metadata | describe new features with specificity | Notes for Review (§10.5) + fixture screenshots | STORE_LISTING |
| 5.1.1(i) Privacy policy | link in App Store Connect and in-app; retention/deletion/revocation described | `privacy_policy_url` (§16) linked from S2 `consent.read_more` → notice → `privacy.notice.full_policy`, and S17 `btn.privacy` | `make export-web && test -f apps/mobile/dist/privacy/index.html` |
| 5.1.1(ii) Consent | consent before collecting any user data, even anonymous | S2 before the first upload; `428 consent_required` server-side; the install id SHOULD be generated at consent rather than first launch (cross-WP need for WP4 filed in DECISIONS §14 CL-010 — `X-Install-Id` is optional, so pre-consent `GET /v1/config` and pack fetches work without it) | `consent.test.tsx`, `tests/contract/test_errors.py::test_428_without_consent`, `::test_428_stale_or_malformed_consent` (CL-069(d)) |
| 5.1.1(iii) Data minimization | out-of-process picker rather than full Photos access | `expo-image-picker` (PHPicker) + `expo-camera`; no `PHPhotoLibrary` full access request | permission strings §12 |
| 5.1.1(v) Login | usable without login | no accounts exist (so no account-deletion duty) | — |
| 5.1.1(ix) Regulated fields | submit from a legal entity, not an individual | organization Apple Developer account (DECISIONS Q2) — **launch blocker** | `eas.json` `appleTeamId` of the org |
| 5.1.2(i) Third-party AI | clearly disclose and obtain explicit permission before sharing personal data with third-party AI | S2 names "Google's AI (Gemini)" in `consent.line1`; primary button `consent.btn_continue`; re-consent on `consent_version`/tier change; withdrawal in S17 | D-02 tests |
| 5.1.2(vi) Camera/Photo data | no marketing, advertising or use-based data mining | no analytics/ad SDKs; photos go only to inference; feedback is counts | §2.3 |
| 5.1.3(i) Health data | no advertising/marketing/data mining; disclose specific health data collected | label §10.2 lists Health; no SDKs | — |
| 5.1.3(ii) iCloud | may not store personal health information in iCloud | vault directory MUST be excluded from iCloud backup **before iOS submission** — see §10.2 gate | dev-build verification recorded in RUNBOOK |
| Privacy manifest | required-reason APIs declared | `ios.privacyManifests`: UserDefaults `CA92.1`, FileTimestamp `C617.1`, SystemBootTime `35F9.1`; `NSPrivacyTracking: false`; `NSPrivacyTrackingDomains: []`; `NSPrivacyCollectedDataTypes` mirrors §10.3 | `npx expo config --type prebuild` |
| Export compliance | encryption declaration | `ios.config.usesNonExemptEncryption: false` (HTTPS only) | app.json |

### 10.2 The iCloud-backup gate (5.1.3(ii))

By default iOS backs up an app's Documents directory. D-22 says backup exclusion is *verified in the first EAS dev build* and not claimed until then. Because 5.1.3(ii) forbids personal health information in iCloud, **iOS store submission is blocked until the vault directory is verifiably excluded** (a config plugin / small native module setting `NSURLIsExcludedFromBackupKey` on `Paths.document/vault/`, which needs the WP0 install window — DECISIONS §11 rejected claiming it unverified). Android is unaffected (`allowBackup: false`). **Status 2026-10-01: not done — still a store-submission blocker.** Checked in this tree: `expo-file-system` 57.0.7 and `expo-sqlite` expose no backup-exclusion API (no `isExcludedFromBackup` / `NSURLIsExcludedFromBackupKey` in their JS or iOS sources), and Phase 2C changed no native config. Both `Documents/vault/` (page JPEGs) and `Documents/SQLite/` (`proxyhealth.db`) need the flag, which takes a config plugin or small native module registered in `app.json`, an install window, and a check on an EAS dev build recorded in RUNBOOK §7.3 and §9; then `features/vault/platformCopy.ts` `IOS_VAULT_BACKUP_EXCLUDED` flips to `true`. Until then iOS shows the D-22 interim vault copy (`vault.privacy_native`), but `consent.line3` ("Papers you save stay only on this phone…") is still shown on iOS (`features/onboarding/consentModel.ts`) — it must switch to the interim wording on iOS before any iOS build reaches users (code request, CL-085). Interim options for the user (§19): ship Android first; or accept a v1 iOS build whose vault is disabled (`btn.save` hidden on iOS) — not recommended. No copy anywhere says "backed up" or "not backed up" (§17 forbids "backed up").

### 10.3 Privacy nutrition label (paid tier; the only tier a store build may use)

Stance: **declare conservatively**. Apple exempts data "sent to your servers then immediately discarded", but the paper also transits Google's abuse log, so we do not rely on the exemption for document content. Nothing is "Linked to You" (no account, no persistent identifier) and nothing is "Used to Track You".

| Apple data type | Collected? | Linked | Tracking | Purpose | Why |
|---|---|---|---|---|---|
| Photos or Videos | Yes | No | No | App Functionality | page images sent for reading |
| Health & Fitness → Health | Yes | No | No | App Functionality | medical papers contain health data |
| Sensitive Info | Yes | No | No | App Functionality | papers may reveal religion (`calendar_notes`), ethnicity; immigration status is inferable |
| Other Data → Other User Content | Yes | No | No | App Functionality | `user_goal`, chat questions |
| Location → Coarse Location | Yes | No | No | App Functionality | user-typed state + zip3 (never GPS) |
| Identifiers → Device ID | Yes | No | No | App Functionality (abuse prevention) | app-generated install id, hashed, 30 days |
| Usage Data → Product Interaction | Yes | No | No | Analytics, App Functionality | "Was this clear?" counts |
| Diagnostics → Performance Data | Yes | No | No | App Functionality | latency/token counts, content-free |
| Contacts, Financial Info, Browsing/Search History, Purchases, Name, Email, Phone, Precise Location, Advertising Data, Crash Data | No | — | — | — | not collected; no crash SDK |

Counsel may approve the minimal variant (only Identifiers, Usage Data, Diagnostics) if Google's abuse log is judged "service provider processing"; the conservative answers are never false, so they are the default (§18.6). Any SDK addition re-opens this table.

### 10.4 Age rating

Answer the questionnaire truthfully — "Medical or wellness topics": yes; AI chatbot present: yes (Apple asks how AI features affect sensitive-content frequency) — then **set the rating to 18+** using Apple's option to choose a higher rating than computed. Rationale in Notes: Gemini API terms require 18+ users and forbid apps likely to be accessed by under-18s (`compliance.md` §4); `consent.adults_only` is shown on S2; school papers are framed for parents. Accessibility Nutrition Labels (optional): claim only VoiceOver, Larger Text, Sufficient Contrast and Reduced Motion after the §15 matrix passes; do not claim Voice Control or captions.

### 10.5 Notes for Review (English; paste into App Store Connect)

> ProxyHealth AI photographs a letter, bill or notice and explains what it says in the reader's language. It does not diagnose, give legal advice, decide eligibility or fill in forms; every screen that explains a paper carries a fixed boundary sentence (for medical papers: "It is not medical advice. Ask your doctor, nurse or pharmacist what it means for you."). There is no account and no login.
> How to test: on first launch choose a language, then read the "What happens to your paper" screen — this is our disclosure and consent for sending the photo to Google's Gemini API (a paid, non-training tier; our server keeps nothing). Tap "Try a sample paper first" to use built-in sample documents without sending anything of your own, or "I understand, continue" and photograph any printed page. Sample papers are synthetic and watermarked SAMPLE.
> Where things are: disclaimers appear above the first result card; "Need help now?" (top of every screen) opens the fixed emergency card; "Was this clear?" / "Report a problem" under every AI-generated card is the flag control; Settings → "How your paper is handled" shows the consent status, the privacy notice and "Stop sending papers"; Settings → "Delete everything on this phone" wipes all local data. Saved papers stay on the device only.
> Permissions: camera (to photograph a paper) and the system photo picker (no photo-library access); notifications only if the user sets a reminder. The app is rated 18+ because the AI provider's terms require adult users. Server status: GET {API_URL}/health returns `data_use_tier: paid`.

---

## 11. Google Play declarations

Source: `docs/research/compliance.md` §1 "Google Play" (policies verified 2026-09-23). Answers below go into Play Console → App content; text into `docs/STORE_LISTING.md`. Category **Tools** (not Medical), still subject to the Health Content and Services policy because the app offers health-related information.

| Play item | Answer / control | Proof |
|---|---|---|
| **Health apps declaration** | Health-related features: yes (explains medical documents). Not a medical device; does not "diagnose, treat, cure, or prevent any medical condition"; in-app reminder to consult a healthcare professional = `disclaimer.medical_information_only` (S7/S9/S15). Human-subject research: no. Uses Health Connect: no. | §5.1, §6.3 |
| **Privacy policy** | public, non-geofenced, non-PDF URL `privacy_policy_url`; linked in Console and in-app (S2 → notice → full policy; S17 `btn.privacy`) | §16 |
| **Prominent disclosure + affirmative consent** (User Data policy) | S2 shown during normal use before the first upload, names Google Gemini and the data sent; consent = tapping `consent.btn_continue`; backing out = "Not now" (no consent); re-consent on change; withdrawal in S17 | D-02, `consent.test.tsx` |
| **Secure transmission** | HTTPS only; `EXPO_PUBLIC_API_URL` must be `https://` in `preview`/`production` profiles (CI check in `scripts/ci.sh`) | `eas.json` |
| **No selling of sensitive data** | no ads, no analytics/attribution SDKs, no data brokers (`privacy.notice.no_ads`) | §2.3 |
| **Account deletion** | not applicable — no accounts; all data is on-device and deletable in-app (`btn.delete_everything`) | §9.5 |
| **AI-Generated Content policy** — in-app flag control | `FeedbackRow` ("Was this clear?" → `btn.no` → kinds incl. `feedback.kind.offensive`, `.wrong_fact`, `.scam_missed`) and `btn.report_problem` on every AI output (summary, demands, plan, details, glossary, red flags, clerk, chat, troubleshoot, resources, language banner, quick sheet — PRODUCT_SPEC §11.1) without leaving the screen; reports drive review (§11.4 of PRODUCT_SPEC). Prohibited outputs: no drafting of official documentation (§6.4) | `test_feedback_store.py` |
| **Photo and Video Permissions policy** | no `READ_MEDIA_IMAGES` / `READ_MEDIA_VIDEO`: `android.blockedPermissions` lists both plus `RECORD_AUDIO`; picking uses the system photo picker (`expo-image-picker`) and `expo-document-picker`; camera via `CAMERA` | merged manifest check §12.3 |
| **Data safety form** | see §11.1 | — |
| **Target audience and content** | target age group: 18 and over only; not designed for children; no ads | Gemini terms (§14) |
| **Content rating (IARC)** | answer truthfully (medical information topics, user-generated interaction via chat with the app only, no user-to-user content); accept the computed rating; the 18+ target-audience declaration and `consent.adults_only` carry the age requirement | STORE_LISTING |
| **Government / financial / news app declarations** | no / no / no | — |

### 11.1 Data safety form (paid tier; same conservative stance as §10.3)

Play's definitions: "collection" excludes data kept only in memory for the real-time request; "sharing" excludes transfers to service providers processing on the developer's behalf. Google Gemini on Paid Services is treated as a **service provider** (no product-improvement use), so nothing is declared as *shared*; document content is declared as *collected* because it transits Google's abuse log.

| Data type | Collected | Shared | Ephemeral | Required | Purpose |
|---|---|---|---|---|---|
| Photos and videos → Photos | Yes | No | No (see stance) | Yes (core function) | App functionality |
| Health and fitness → Health info | Yes | No | No | Yes | App functionality |
| Personal info → Other info (names/dates printed on papers) | Yes | No | No | Yes | App functionality |
| Location → Approximate location (typed state + zip3) | Yes | No | Yes (not stored) | No (optional in Settings) | App functionality |
| Messages → Other in-app messages (chat questions, `user_goal`) | Yes | No | Yes | No | App functionality |
| App activity → App interactions (feedback counts) | Yes | No | No | No | Analytics, App functionality |
| App info and performance → Diagnostics | Yes | No | No | Yes | App functionality (content-free) |
| Device or other IDs (app-generated install id, hashed) | Yes | No | No | Yes | Fraud prevention, security |
| Contacts, calendar, files (other than the chosen photo/PDF), audio, financial info, precise location, web browsing, installed apps, crash logs | No | — | — | — | — |

Security practices: data encrypted in transit — yes; users can request deletion — yes (in-app wipe; the server holds nothing to delete, stated in the policy); independent security review — not claimed. Any SDK addition re-opens this form (compliance.md Warnings).

---

## 12. Permission strings and manifests (final wording; where they live)

English strings are `en.json` keys (Appendix A; packs translate); iOS shows them from `locales/<tag>.json` (`expo.locales`, synced by `sync_to_mobile.py` — WP7) while Android's system dialogs are OS-localized and the in-app rationale card is pack-localized. Strings are baked into the binary: any change needs a new EAS build (expo.md §4).

| Purpose | Final English (key) | iOS Info.plist key | Android | Where in `app.json` |
|---|---|---|---|---|
| Camera | "ProxyHealth AI uses the camera only to photograph the paper you want explained. Photos are not saved on our servers." (`perm.camera`) | `NSCameraUsageDescription` | `android.permission.CAMERA` (runtime) | `plugins` → `["expo-camera", {"cameraPermission": …, "microphonePermission": false}]` and `["expo-image-picker", {"cameraPermission": "ProxyHealth AI uses the camera only to photograph the paper you want explained.", …}]`; mirrored in `ios.infoPlist` |
| Photo picker | "ProxyHealth AI lets you choose a photo of a paper to explain. We do not access your other photos." (`perm.photos`) | `NSPhotoLibraryUsageDescription` (required because the picker API is linked; PHPicker itself shows no prompt) | none (system photo picker; `READ_MEDIA_*` blocked) | `["expo-image-picker", {"photosPermission": …}]`; `android.blockedPermissions: ["android.permission.READ_MEDIA_IMAGES", "android.permission.READ_MEDIA_VIDEO", "android.permission.RECORD_AUDIO"]` |
| Photo library *add* | **not used** — the app never writes to the camera roll (`btn.save_evidence` saves into the vault) | `NSPhotoLibraryAddUsageDescription` omitted; add it only if a "Save image to Photos" feature ships | — | — |
| Microphone / speech | **not used** (mic is LATER) | `NSMicrophoneUsageDescription`, `NSSpeechRecognitionUsageDescription` omitted | `RECORD_AUDIO` blocked | `microphonePermission: false` on both plugins |
| Notifications | "ProxyHealth AI reminds you about dates it found on your papers. Reminder text is generic unless you choose otherwise." (`perm.notifications`) — shown on the in-app card `reminders.permission_explain` **before** the OS prompt; iOS has no plist string for notifications | — | `POST_NOTIFICATIONS` (Android 13+ runtime); plugin may add `RECEIVE_BOOT_COMPLETED`, exact-alarm permissions — verify in the merged manifest | `["expo-notifications", {"icon": "./assets/images/notification-icon.png", "color": "#1F5F8B", "defaultChannel": "dates"}]` |
| Documents (PDF) | no permission (system document picker) | — | none | `expo-document-picker` plugin |
| Location | **never requested** | none | none (`ACCESS_*_LOCATION` must not appear) | — |
| Files/storage | none (app-private storage only) | — | `READ/WRITE_EXTERNAL_STORAGE` must not appear | — |
| Network | implicit | — | `INTERNET` | — |
| Haptics | — | — | `VIBRATE` (auto-added by `expo-haptics`) | — |
| Backup | — | vault backup exclusion: §10.2 gate | `android.allowBackup: false` | `android` |
| Privacy manifest | — | `ios.privacyManifests` (§10.1 row) | — | `ios` |

Rules: (1) the camera rationale inside the app is `capture.permission_rationale` ("I need the camera to photograph your paper. The photo is sent only to be read, and our server does not keep it."), shown before the OS prompt; denial → `state.camera_denied` + `btn.open_settings` + `btn.pick_instead`; (2) `perm.*` strings are in `approved_keys` (§17) because they make privacy claims — "Photos are not saved on our servers" and "We do not access your other photos" must stay literally true; (3) never ask for a permission the current action does not need (Apple 5.1.1(iii), Play User Data); (4) Expo Go shows generic strings — only dev/store builds show these (BUILD_PLAN §1.4 `npx expo config --type prebuild` validates the plugin config offline).

### 12.1 Manifest verification (before every store build)

`cd apps/mobile && npx expo config --type prebuild` (plugin strings resolve); after the Android build, inspect the merged manifest of the `.aab`/`.apk` (e.g. `aapt2 dump permissions` or the EAS build log) and confirm the permission set is exactly `CAMERA, INTERNET, POST_NOTIFICATIONS, VIBRATE` plus whatever `expo-notifications` adds for scheduling, and contains none of `READ_MEDIA_IMAGES, READ_MEDIA_VIDEO, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, RECORD_AUDIO, ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION`. Record the list in `docs/RUNBOOK.md`; a diff re-opens §10.3/§11.1.

---

## 13. HIPAA, the FTC Health Breach Notification Rule and state law

Sources: `docs/research/compliance.md` §2 (OCR scenarios likely; FTC HBNR pages and 16 CFR 318.2 verified; WA/CA law likely). Nothing here is a legal opinion; §18 asks counsel to confirm each conclusion before launch.

### 13.1 HIPAA — does not attach (today)

A consumer who chooses an app to understand her own papers is not a covered entity; the operator is not a business associate because no covered entity engaged it (OCR Health App Scenario 1; FTC Mobile Health App tool). **Re-analyze immediately if** a clinic, health plan, school district, legal-aid grantee or government body contracts the operator to deploy ProxyHealth AI to its patients/clients (BA status turns on who hires and pays), or if any server-side storage of papers is ever added. Copy never says "HIPAA compliant" (§17 forbidden phrase); the policy says HIPAA does not apply and why.

### 13.2 FTC Health Breach Notification Rule (16 CFR 318) — treated as applicable

Why it plausibly applies: the app "provides mechanisms to track… diagnoses or diagnostic testing, treatment, medications" (health care services or supplies) and the vault can "draw information from multiple sources" (camera captures from several providers + user edits + calendar export) — a personal health record; a "breach" includes **unauthorized disclosure**, not only intrusion (GoodRx, 2023). Mitigants that keep the exposure small: no server persistence; paid tier only; no analytics SDKs; consent before the first upload; the vault is on the user's device (the operator is not its custodian). Events the operator treats as HBNR breaches: (a) a real paper reaching Gemini **Unpaid Services** (misattested `billing:true`, `ALLOW_UNPAID_REAL_DOCUMENTS` in a non-dev deployment, a mis-pointed store build); (b) developer logging found ON for a production project; (c) any server-side write of content (log, temp file, crash dump); (d) a compromised `GEMINI_KEYS`/Cloud Run project; (e) a client bug that uploads without consent. Not breaches (but incidents): loss of a user's own phone; a user forwarding a quick sheet.

**60-day plan** (owner: operator on-call + counsel; runbook detail in `docs/RUNBOOK.md`):

| Clock | Action |
|---|---|
| T+0–4 h | Contain: rotate keys in Secret Manager, redeploy with the offending slot `disabled`/removed, set `ENV=production` guards, confirm `GET /health` and `/v1/admin/keys`; if a build is mis-pointed at an unpaid API the 403 gate is already blocking real papers; bump `CONSENT_VERSION` so every client re-shows S2 (`consent.changed`). (LATER, §19 Q18: an operator kill switch that forces `features.real_documents_allowed=false` on a paid deployment — no such flag exists today.) Open the incident log (content-free: request ids, install hashes, time window). |
| T+0–72 h | Scope from the 30-day structured log: count distinct `install_id_hash` values and `page_count`/`document_type` in the window (no content exists to review). Determine whether "unsecured PHR identifiable health information" was involved (any `category = medical` request counts). Preserve the log window beyond 30 days. |
| ≤ 60 calendar days after discovery | **Individual notice**: the operator holds no names or addresses, so notice is given by substitute means — a dated notice at `privacy_policy_url`, an in-app notice (interim channel: `CONSENT_VERSION` bump with the changed line; LATER: a `ServerConfig.notice` field — contract change filed in §19), and, where the affected count in a state exceeds 500, media notice in that state. Content: what happened, the window, what data was involved, what we did, what users can do (nothing is stored server-side; they may delete local copies), contact address. Plain language, translated into the launch languages. |
| same time as individual notice (≥ 500 affected) or within 60 days after the calendar year (< 500) | **FTC notice** per the Rule's form; counsel files. |
| after | Root-cause entry in DECISIONS §14; re-run §18 checklist; consider Vertex AI zero-retention terms (§14). |

### 13.3 State law (likely for some users; counsel confirms thresholds)

| Law | Why it may apply | Control already in place | Counsel question (§18.5) |
|---|---|---|---|
| Washington My Health My Data Act (eff. 2024-03-31) | "consumer health data" held by non-HIPAA businesses; consent to collect/share; private right of action | S2 consent (purpose-specific, named third party); no sale; on-device deletion; policy section | small-business threshold and timing; whether a separately titled "Consumer Health Data Privacy Policy" link is required on the web homepage; geofencing is not planned |
| California CCPA/CPRA | "sensitive personal information" includes health data and citizenship or immigration status (Civ. Code §1798.140(ae)); the app processes SPI by design though it never asks status | notice at collection = S2 + policy; purpose limitation (inference only); no sale/share for advertising; deletion on device | whether the business thresholds are met at pilot scale; whether a "Limit the Use of My Sensitive Personal Information" link is needed when SPI is used only for the requested service |
| Virginia CDPA and similar acts (CO, CT, …) — pilot geography is Northern Virginia | sensitive data (health; citizenship/immigration status) requires consent; controller thresholds (not in the research files — counsel) | same | applicability at pilot scale; data protection assessment duty |
| State UPL statutes | §6.1 | fixed disclaimers, refusals, referrals | per-state review (§18.1) |

Design commitments that hold in every state: no immigration-status field anywhere (D-24); state + zip3 only, typed by the user; no GPS; no sale; no cross-context tracking; consent before disclosure to Google; one-tap deletion; policy in plain language (§16). FTC Act §5 applies everywhere: `test_privacy_claims.py` is the literal-truth control (§17).

---

## 14. Gemini API terms — compliance checklist (D-01, D-03; `docs/research/gemini.md` §3, `compliance.md` §4)

| Term (Gemini API Additional Terms, eff. 2026-03-23; Prohibited Use Policy 2024-12-17) | Control | Verified by |
|---|---|---|
| Unpaid Services: content used to improve products, human review; "Do not submit sensitive, confidential, or personal information" | real papers only on `paid`; `403 unpaid_tier_real_documents_disabled` on `unpaid`/`mixed`; production refuses unbilled keys unless `ALLOW_UNPAID_KEYS=1` (fixtures only); `ALLOW_UNPAID_REAL_DOCUMENTS` boot error in production; fixtures are synthetic; a demo request that carries typed text (`/v1/chat`, a troubleshoot `user_goal`) is gated like a real paper on these tiers, so nothing the reader types reaches unbilled keys (§9.1) | `tests/contract/test_errors.py::test_403_unpaid_or_mixed_tier_blocks_real_pages`, `::test_demo_sample_without_consent_header_is_200`, `::test_unpaid_tier_demo_sample_passes_the_gate`, `::test_unknown_demo_sample_id_is_not_exempt_from_the_403_gate`, `::test_sample_chat_on_unpaid_or_mixed_is_gated_like_a_real_paper`, `::test_sample_troubleshoot_with_a_typed_goal_is_gated_on_unpaid`; boot rules in `tests/unit/test_settings.py::test_production_rules` (CL-069(d)) |
| Paid Service = API access through a Cloud project with an active billing account | `billing:true` is an operator attestation per slot; distinct `project` labels; attestation procedure: screenshot of the Cloud Billing link per project filed in RUNBOOK at each key rotation; false attestation = incident (§13.2) | `.env.example`, RUNBOOK |
| Paid: prompts/responses logged "for a limited period" for abuse detection; optional developer logging (55 d default) | disclosed in `consent.line2.paid` and the policy; developer logging **OFF** on every production project (checked at each release in AI Studio); Files API never; Interactions `store=False` (LATER) | release checklist §18.7 |
| EEA / Switzerland / UK: Paid Services only | v1 US-only: `region_notice: "us_only"`, US storefronts only, resource DB US-only; if any EEA/CH/UK exposure: all slots `billing:true` and `ALLOW_UNPAID_KEYS` unset (D-03) | `.env.example` note; STORE_LISTING territories |
| 18+: developer and users; not directed at / likely accessed by under-18s | `consent.adults_only`; 18+ store ratings (§10.4, §11); school papers addressed to parents; no student marketing; no child-directed features (COPPA n/a) | copy review |
| No use in clinical practice, to provide medical advice, or in a manner requiring medical-device clearance | §6.3 boundary; `medical_information_only`; phrasing lint; `medical_interpretation` refusal; no diagnostic/analytic function | golden medical fixtures |
| "Don't rely on the Services for medical, mental health, legal, financial, or other professional advice… informational purposes only" | mirrored in §5 disclaimers, `chat.scope`, the policy and store copy | `test_privacy_claims.py` (approved keys) |
| Prohibited Use: no automated decisions with material detrimental impact in healthcare, legal, housing, insurance, social welfare without human supervision | urgency is an informational banner computed from verified printed facts with a "Verify this date" CTA (D-12); no eligibility/outcome/filing decisions (D-17); every plan ends in a human referral | `test_urgency.py`, phrasing goldens |
| Prohibited Use: no misleading claims of expertise in health, government services or law | no "advice", "certified", "lawyer-reviewed", "doctor-approved" in copy (§5.4); disclaimers name the real professionals | STORE_LISTING review |
| Prohibited Use: no misrepresenting provenance as solely human | `footer.ai_generated` on every AI surface; `banner.machine_translated` on machine-translated packs; no "human-reviewed" claim without `reviewed_by` (§17) | `test_privacy_claims.py` |
| API keys: keep secret; developer account "not for consumer use" | keys only server-side in Secret Manager (`SecretStr`), never in the client (`EXPO_PUBLIC_*` carries none); users never hold keys | `grep` in CI for `AIza` in `apps/mobile` |
| Model lifecycle terms (deprecations) | env-configurable IDs, forbidden 1.5/2.0/2.5/`-latest` (D-04) | `settings.py` validators |
| Alternative: Google Cloud / Vertex AI Generative AI terms (same health/18+ restrictions; zero-data-retention options; BAA available but not needed) | evaluated in §19 as a trust upgrade; not required for v1 | — |

---

## 15. Accessibility baseline (WCAG 2.2 AA floor — D-28, PRODUCT_SPEC §5.1–§5.2; `compliance.md` §5)

WCAG 2.2 AA is the floor on every platform; Apple HIG and Material sizes are exceeded by the "Big Calm" tokens; Section 508 / ADA Title II bind only if a government body deploys the app (the same criteria satisfy them). Tokens live in `src/design/tokens.ts` (WP0); components in `src/design/components/` (WP4).

| WCAG 2.2 SC | Token / component / rule | Test |
|---|---|---|
| 1.1.1 Non-text content | `Crop` `alt` = the quote; pictograms `consent.pictogram*_alt`; icons are vector glyphs with `accessibilityLabel`; no emoji in controls | `result-cards.test.tsx` labels; manual VoiceOver |
| 1.3.1 Info and relationships | `Card` = `role="region"` + heading; headings levels on S2/S7; lists are lists (`plan_steps`, `documents[]`) | axe (web) |
| 1.4.1 Use of color | urgency = icon + word + color (`tokens.urgency.*`), confidence chips carry words | `urgency-banner.test.tsx` |
| 1.4.3 / 1.4.6 Contrast | body text 7:1 (AAA, never below 4.5:1); `palette.highContrast` via `useHighContrast()` = toggle OR `AccessibilityInfo.isHighTextContrastEnabled()` / `isDarkerSystemColorsEnabled()` | SHOULD (WP4): a unit test computing the contrast ratio of every palette pair in `tokens.ts`; axe |
| 1.4.4 Resize text 200 % | `allowFontScaling` on; `maxFontSizeMultiplier={2}` **only** on tab labels; no fixed-height text containers; verbatim values wrap, never truncate | `result-cards.test.tsx` at `fontScale: 2`; manual iOS AX5 and Android 200 % non-linear |
| 1.4.10 Reflow | web: no two-dimensional scroll at 320 CSS px; S8 side-by-side collapses below 900 px; page images pinch-zoom instead of horizontal scroll | manual web at 320 px |
| 1.4.11 Non-text contrast | UI components and focus ring ≥ 3:1 (`tokens.palette.*.border`, `focusRing`) | tokens unit test |
| 1.4.12 Text spacing (web) | no `overflow: hidden` on text; line-height from `fonts.ts` multipliers (Nastaliq 2.0) | manual with a text-spacing bookmarklet |
| 2.1.1 Keyboard (web) | every control focusable; S10 exit long-press has a keyboard path (hold Space 1.5 s) and `accessibilityActions: ["activate"]` (PRODUCT_SPEC §8.6) | manual keyboard-only pass S1–S3, S7, S9–S11 |
| 2.2.1 Timing adjustable | no session timeouts; the `429` Retry countdown is informational; TTS has a persistent stop | — |
| 2.3.3 Animation | reduce-motion respected (`theme.tsx`); no decorative animation | manual |
| 2.4.3 Focus order / 2.4.7 Focus visible / 2.4.11 Focus not obscured | focus order = reading order; visible focus ring; the sticky 56 pt action bar (S7) and banners never cover the focused element (scroll padding = bar height) | manual web + TalkBack |
| 2.5.8 Target size (24×24 min) | buttons 56 pt, primary 72 pt, `SpeakButton` 44×44, `hitSlop` 8, 8 pt spacing (exceeds Apple 44 pt / Material 48 dp) | tokens; snapshot |
| 3.1.1 / 3.1.2 Language of page / parts | web root `lang` + `dir` from the pack (`+html.tsx`, `direction.ts`); per-pane `accessibilityLanguage`/`lang`: source blocks = `detected_language`, UI = pack tag; S10 lines `en-US`; language chips announce their own language | `i18n.test.ts`; manual VoiceOver voice switch on S8 |
| 3.2.3 Consistent navigation | four JS tabs everywhere; header pattern identical; `home.need_help_now` on every screen | — |
| 3.3.1 / 3.3.3 Errors | `ErrorState` copy from `user_message_key` + one primary action; never raw upstream text | `api-client.test.ts` |
| 3.3.7 Redundant entry | region, tone and calendar notes remembered in Settings; "Whose paper is this?" offers existing members | — |
| 4.1.3 Status messages | one live region per screen (`a11y.*`: `a11y.reading_finished`, `a11y.page_added`, `a11y.emergency_shown`, `reminders.added`); `ProgressSteps` `aria-live="polite"` | manual screen reader |

**RTL / bidi** (compliance.md §5; D-26): `useDirection()` drives `flexDirection`, `textAlign`, `writingDirection`; verbatim values (`value_verbatim`, dates, case/receipt numbers, amounts, phones, URLs, agency names, `ui_target_as_written`, `error_text_quoted`, `source_quote`, `term_as_written`) render inside `<Bidi dir="ltr">` (LRI/PDI native, `unicode-bidi: isolate` web); digits are never localized or reversed — `DateInfo.localized_line` is an *additional* line in the pack's `DigitSystem`; page images, crops and icons of real objects are never mirrored; chevrons, progress bars and back arrows are; thumbnail strips keep page order left-to-right with Western page numbers. **Fonts**: Noto Naskh Arabic (ar, prs, ps, fa), Noto Nastaliq Urdu with line-height 2.0 (nuqtas/descenders), Noto Sans Ethiopic (am), Noto Sans Myanmar (my), Devanagari/Bengali/Gurmukhi, Hanifi Rohingya; CJK system fonts. TTS: honest fallback (`tts.fallback_offer`), `tts.earbuds_tip` for private listening.

**Test procedure (release gate; results recorded in `docs/RUNBOOK.md`):** (1) automated — `npx jest` (`result-cards.test.tsx` LTR/RTL/`fontScale 2`, `urgency-banner.test.tsx`, `bidi.test.tsx`, `i18n.test.ts`, tokens contrast test); (2) web — axe DevTools browser extension (no axe package is installed) on S1, S2, S3, S7, S11 in light, dark and high-contrast, at 320 px and 200 % zoom, keyboard-only; (3) iOS — VoiceOver full flow J-A with text size AX5, Reduce Motion on, Increase Contrast on; (4) Android — TalkBack full flow J-C at 200 % font, on a mid-range device, Dari (`prs`) RTL; (5) S10 clerk card at ≥ 24 pt with 7:1 contrast and the keyboard exit; (6) S19 numbers announced digit-grouped. Accessibility Nutrition Label claims (§10.4) are made only for items that passed.

---

## 16. Privacy policy (outline and required sentences)

File: `apps/mobile/public/privacy/index.html` (WP8; draft written 2026-09-29, operator identity and effective date still `TODO` per Q15), copied by `expo export` into `dist/privacy/index.html`, served at `PRIVACY_POLICY_URL` (default `https://proxyhealth.expo.app/privacy`; ARCHITECTURE §5.3). Requirements: HTML (never PDF), public, non-geofenced, no JavaScript needed to read, `<html lang="en" dir="ltr">`, headings `h1`/`h2`, readable at 320 px and 200 % zoom (§15), no analytics on the page, an "Effective" date and the matching `CONSENT_VERSION`. Translated copies at `/privacy/<tag>/` are SHOULD (generated from the same source, labelled machine-translated until reviewed). The page must contain no `forbidden_phrases` (§17); `test_privacy_claims.py` scans the page's visible text and the STORE_LISTING ```` ```text ```` blocks with the same list, checks `lang`/`dir`, no `<script>`, the verbatim reuse of the notice sentences and the printed consent version (done 2026-09-29, WP8). Every change bumps `CONSENT_VERSION` (§4.7).

Sections in order, with the sentences that MUST appear (plain language; the `privacy.notice.*` strings are reused verbatim so the in-app notice and the policy never disagree):

1. **Who we are** — operator legal name, address, contact e-mail for privacy questions (open: §19), effective date, consent version ("This policy matches consent version {CONSENT_VERSION} shown in the app.").
2. **What the app does** — one paragraph; "ProxyHealth AI explains what a paper says. It does not give legal or medical advice, decide eligibility, or fill in forms."
3. **What is sent when you read a paper** — `privacy.notice.sent`; the list of fields from §9.1 in plain words, where the page-photos bullet reuses `consent.line4.masks` (phone app: blacked out on our server) and `consent.line4.masks_web` (web: on the device) verbatim (`test_privacy_claims.py::test_policy_states_where_masks_are_applied`, CL-069(b)); "The app does not ask for your name, e-mail, phone number, contacts, exact location, full ZIP code or immigration status, and it never sends them on its own. Apart from what is printed on a paper, shown in a screenshot or typed in a question that you choose to send, none of these leave your device." (CL-069(c)); "None of your own photos or papers are sent until you tap "I understand, continue"." (not "photos, papers or questions": a question about a sample goes to `/v1/chat` with `demo_sample_id` before consent — CL-069(a)) followed by what *is* sent before consent: the server config request, the words of the app in the chosen language and, if the user types one, the language name (§2.2), because the shorter "Nothing is sent until you tap…" would be false for S1b; then the sample path ("Try a sample paper first" / "Not now"): `GET /v1/demo/fixtures`, the chosen sample with the same settings as a real paper (language, state and ZIP prefix if typed, preferences, client platform — `POST /v1/analyze` with `demo_sample_id`, `tests/contract/test_demo.py::test_demo_sample_analyze_without_consent`), and what is done with a sample: its questions (`/v1/chat`), a troubleshoot goal (`/v1/troubleshoot`), state + ZIP prefix on "Get help nearby" (`/v1/resources/match`), "Was this clear?" answers (`/v1/feedback`) and the sample's cards in a quick sheet (`/v1/quicksheet/pdf`); tier sentence: `consent.line2.paid` (the paid deployment) — plus, for any demo instance, `consent.line2.demo`, and one line saying free-key test builds refuse real papers (the 403 gate, §3).
4. **Google Gemini** — named as the AI provider on paid terms: "Google does not use your paper to improve its products. Google keeps a short safety log for a limited time, then deletes it." with a link to Google's Gemini API terms; "We do not turn on Google's optional logging."
5. **What our server keeps** — `privacy.notice.what_we_keep`; the §9.2 table in prose; retention: 30 days for technical logs, 7 days for connection logs; "We cannot see, retrieve or delete your paper because we do not have it."
6. **Your settings that travel with a paper** — `privacy.notice.settings_sent`; `privacy.notice.no_status`.
7. **The random device code** — `privacy.notice.install_id`.
8. **What stays on your phone or in your browser** — `privacy.notice.device` and `privacy.notice.device_web`; `privacy.notice.hide_parts`; `privacy.notice.delete`; reminders: "Reminders store only a label and a date. The reminder text is generic unless you choose otherwise."
9. **Feedback** — `privacy.notice.feedback`.
10. **No ads, no sale, no tracking** — `privacy.notice.no_ads`; "We do not use analytics or advertising software."
11. **Children** — "This app is for adults 18 and older. It is not directed at children."
12. **Your choices and rights** — withdraw consent (S17 "Stop sending papers"), delete one paper / one person / everything, reset the device code; state-specific rights paragraphs (California, Washington, Virginia — text from counsel, §18.5) that state truthfully that no personal data is held by the operator to access, correct or delete.
13. **Security** — HTTPS; keys in a secrets manager; on-device protection sentence identical to `vault.privacy_native`; the web sentence identical to `vault.privacy_web`.
14. **If something goes wrong** — "If your paper is ever exposed in a way you did not agree to, we will post a notice here and in the app within 60 days and tell you what happened." (§13.2).
15. **Laws that apply** — "HIPAA does not apply to this app because we do not work for your doctor, hospital or insurer."; FTC Health Breach Notification Rule commitment; state laws named.
16. **Changes** — "When this policy changes, the app shows the new consent screen before sending another paper."
17. **Contact** — e-mail and postal address.

Cross-checks: every sentence about data handling is either a `privacy.notice.*` / `consent.*` / `vault.privacy_*` string or a sentence listed above; STORE_LISTING quotes the same sentences; `docs/DEPLOYMENT.md` records where the page is served and that `CORS_ORIGINS` includes the web host.

---

## 17. `privacy_claims` (machine-readable seed — restored 2026-09-27; WP8 reviews and extends)

`apps/api/tests/unit/test_privacy_claims.py` (WP8) parses the fenced `yaml` block below. It asserts: (a) every `en.json` key listed under `approved_keys` exists and its English string equals the copy fixed in `PRODUCT_SPEC.md` Appendix A / this file §4 byte for byte; (b) no `en.json` string (any key) contains a phrase from `forbidden_phrases` (case-insensitive); (c) every `en.json` key whose value contains one of the `claim_markers` is listed under `approved_keys` (so a new privacy sentence cannot ship unreviewed). The store-listing check (`docs/STORE_LISTING.md`, LATER for this test) reuses `forbidden_phrases`.

```yaml
privacy_claims:
  version: "2026-09-30"
  approved_keys:
    # consent screen (D-02)
    - consent.line1
    - consent.line2.paid
    - consent.line2.unpaid
    - consent.line2.demo
    - consent.line2.unknown
    - consent.line3
    - consent.line3.web
    - consent.line4.masks          # shown only when features.hide_parts_server_masking is true (D-19)
    - consent.line4.masks_web
    - consent.adults_only
    # home / scan / reading
    - home.trust_footer
    - home.trust_footer.web
    - home.tile_sample_sub
    - home.offline_line
    - capture.permission_rationale
    - reading.trust_line
    - review.hide_tip
    # banners
    - banner.demo_sample
    - banner.unpaid_tier
    - banner.sample_mode
    - banner.web_session_only
    - demo.explainer
    # vault and settings
    - vault.saved
    - vault.empty
    - vault.web_kept
    - vault.web_keep_confirm
    - vault.privacy_native
    - vault.privacy_web
    - vault.privacy_server
    - settings.web_keep
    - settings.tone_why
    - settings.sample_why
    - settings.zip3_why
    - wipe.body
    # in-app privacy notice (§4.5)
    - privacy.notice.sent
    - privacy.notice.what_we_keep
    - privacy.notice.device
    - privacy.notice.device_web
    - privacy.notice.hide_parts
    - privacy.notice.no_status
    - privacy.notice.no_ads
    - privacy.notice.settings_sent
    - privacy.notice.install_id
    - privacy.notice.feedback
    - privacy.notice.delete
    # feedback, errors, guards
    - feedback.thanks
    - err.internal
    - err.network
    - err.timeout
    - troubleshoot.credential_guard
    # OS permission strings (baked into the binary; packs translate)
    - perm.camera
    - perm.photos
    - perm.notifications
    # added 2026-09-29 by WP8 (CL-012), each reviewed against the implementation (§17.1)
    - about.not.6
    - btn.delete_everything_web
    - settings.reviewed_by
    - source.no_image
    - vault.empty.web
    - vault.saved.web
    # added 2026-09-30 (Phase 2B) with the web variants of CL-047(a), reviewed in §17.1
    - wipe.title.web
    - settings.wipe_offer.web
  claim_markers:               # a string containing any of these must be an approved key
    - "our server"
    - "Google"
    - "Gemini"
    - "encrypt"
    - "stay only"
    - "stays on this phone"
    - "in this browser"
    - "not kept"
    - "does not keep"
    - "is not sent"
    - "was not sent"
    - "Nothing was sent"
    - "None of your"
    - "never ask"
    - "do not sell"
    - "trackers"
    - "reviewed by"
  forbidden_phrases:           # never in en.json, store copy or the privacy policy (FTC §5 literal truth; D-22, D-25)
    - "encrypted by the app"
    - "end-to-end encrypted"
    - "never leaves your device"
    - "nothing leaves this device"
    - "Google never sees"
    - "human-reviewed"
    - "reviewed by a human"          # allowed only as the runtime string settings.reviewed_by "Reviewed by {name}" when reviewed_by is non-null
    - "SQLCipher"
    - "HIPAA compliant"
    - "HIPAA-compliant"
    - "backed up"
    - "not saved on our computers"    # the retired S2 sentence (D-02)
    - "lawyer-reviewed"               # store/marketing expertise claims (§5.4, §14)
    - "doctor-approved"
    - "nothing of yours"              # retired sample copy (2026-09-30): typed questions and goals about a sample are sent
    - "keeps only counts"             # retired privacy.notice.what_we_keep (CL-061): the 30-day log keeps per-request enums
```

Rules the seed encodes: every sentence must be true on **every** tier it can appear on (tier-specific sentences are keyed per tier); web variants exist wherever the native sentence would be false in a browser; nothing claims app-layer encryption, human review, or iOS backup exclusion until verified (D-22, D-25).

Test mechanics (WP8, 2026-09-29, resolves CL-012): the forbidden-phrase check (b) is **negation-aware** — an occurrence directly preceded by "not", "never" or "no" is the honest disclaimer itself ("Keep on this device (not encrypted by the app)"), not a claim; every other occurrence fails. The same check runs over the visible text of `apps/mobile/public/privacy/index.html` and over the ```` ```text ```` store-copy blocks of `docs/STORE_LISTING.md`, and the policy page must contain every §16 sentence verbatim plus "consent version {CONSENT_VERSION}".

### 17.1 Reviewed copy for approved keys that Appendix A does not fix

Rule (a) compares each approved key with the copy fixed in `PRODUCT_SPEC.md` Appendix A, §4 or §12 of this file, or this list. Each line was checked against the implementation on 2026-09-29:

- `about.not.6`: "Does not store your papers on any server, does not log their content, and never asks your immigration status." — true on every tier: requests are processed in memory (§2.1), logs are the content-free allow-list (§2.3), no contract field asks status (D-24). Web opt-in storage is the user's own browser, not a server.
- `vault.empty.web`: "Papers you keep stay only in this browser. Nothing is saved until you tap Save." — `vault.web.ts` keeps papers in tab memory or, after opt-in, IndexedDB; saving is opt-in (D-23).
- `vault.saved.web`: "Saved. It stays in this browser." — same adapter; nothing is uploaded on save.
Rewritten 2026-09-30 (Phase 2B; CONSENT_VERSION bump required, §4.7 — these keys' fixed copy in PRODUCT_SPEC Appendix A and §4 changed with them):

- `privacy.notice.what_we_keep`: "Our server does not keep your papers or photos. It keeps short technical notes, like the kind of paper and how long it took. It deletes them after 30 days. The notes never hold your paper's words, what you type, or the AI's words." — true on every tier: requests are processed in memory (§2.1); the structured log (§2.3) holds only the allow-listed enums, counts and latencies (`logging_.py` `ALLOWED_FIELDS`, `test_logging_allowlist.py`), never document text, prompts, chat text or `user_goal`, with 30-day retention (DEPLOYMENT §1.3). Replaces "Our server keeps only counts: …", which the per-request enums made untrue (CL-061).
- `banner.demo_sample`: "This is a made-up sample paper. What you type is still sent to be answered." — shown on S5 (sample pages), S7, S9 and S16. A sample request still carries the reader's settings, and a chat question or troubleshoot goal typed about a sample is sent to our server — on `paid` a sample chat question then goes to Gemini, before consent (the gate exempts known `demo_sample_id`s there); on `unpaid`/`mixed` typed sample text is gated like a real paper; a sample troubleshoot goal is never put into the prompt (§9.1) — so the former "Nothing of yours was sent" was false. "Still sent" is true on every tier; the sentence never understates what leaves the device.
- `home.tile_sample_sub`: "See how it works with a made-up paper." — makes no sending claim (the former "Nothing of yours is sent" was false for the same reason).
- `settings.sample_why`: "Try the app with made-up sample papers. What you type is still sent to be answered." — the former "with a pretend helper" was false on Gemini tiers, where a sample is read by the real model.
- `banner.web_session_only`: "This paper is kept only while this tab is open. To keep it, turn on keeping in Settings." — the same meaning as before, split for readability (CL-059); `vault.web.ts` keeps papers in tab memory unless `settings.web_keep` is on (D-23).

Added 2026-09-30 (Phase 2B, CL-047(a) web variants from the mobile vault round; they contain the marker "in this browser"):

- `wipe.title.web`: "Delete everything in this browser?" — the web title of the "Delete everything" dialog; a question, not a claim, and "in this browser" is exactly the scope of the web wipe (`storage/wipe.ts` on web clears the vault — tab memory and, after opt-in, IndexedDB — then every `kv` key, including settings, consent and the device code; nothing is held server-side to delete).
- `settings.wipe_offer.web`: "Do you also want to delete everything saved in this browser?" — the web variant of the offer after "Stop sending papers" (§4.4); a question, not a claim.

- `btn.delete_everything_web`, `settings.reviewed_by`, `source.no_image` are fixed in Appendix A; `settings.reviewed_by` ("Reviewed by {name}") renders only when a pack's `reviewed_by` is non-null (D-25), and `source.no_image` only when the user turned off "Keep page images" (§9.4).


---

## 18. Pre-launch legal and compliance review checklist

Owner: WP8 assembles; the user's counsel (DECISIONS Q3) answers §18.1–§18.6; engineering proves §18.7. Every line needs a named person and a dated proof before `v1.0.0-rc1` (BUILD_PLAN §7 #16–#18). "Pending counsel" is recorded in `docs/STORE_LISTING.md` until then.

### 18.1 Unauthorized practice of law (counsel)
- [ ] Does the §6.1 table keep every document type on the "legal information" side in Virginia and DC (pilot), and in each additional pilot state (Q5)? Which state's UPL statute is most restrictive for a *generic explanation of a court form*, given *Upsolve v. James*?
- [ ] Are `disclaimer.legal_information_only`, `disclaimer.housing_information_only`, the `chat.refer.*` and `chat.refusal.*` templates sufficient, or must the app state "not a law firm; no attorney–client relationship" (Upsolve pattern) in About and the policy?
- [ ] Is the fixed jury-summons notice (`fixed.jury_summons`, the only "must" sentence) acceptable as public legal information? Same for `fixed.eviction_summons` and `fixed.uscis_receipt_i765`.
- [ ] Does "Show the clerk" (S10) or the quick sheet (S15) risk being read as document preparation? (Our position: no — neither is addressed to an agency or formatted as a form, §6.4.)
- [ ] Referral wording: Phase 2B replaced "Only a licensed lawyer or a DOJ-accredited representative can advise you." with "Only a licensed lawyer can advise you. For an immigration case, a DOJ-accredited representative can too." (and the matching `chat.refer.lawyer_or_accredited_rep`) — confirm it is correct for every category where it appears (court, civic and employment included).

### 18.2 Medical / FDA / Gemini health terms (counsel)
- [ ] Do the §6.3 allowed/forbidden columns keep the app within the FD&C §520(o)(1)(D) display exclusion, including reading dosing instructions verbatim from a prescription label? Anything to change given FDA's 2026 comment period on excluded software?
- [ ] Is `disclaimer.medical_information_only` sufficient as the Apple 1.4.1 / Play Health reminder, or should the emergency card be referenced from it?
- [ ] Does anything in the product amount to "medical advice" under the Gemini API terms (§14)?

### 18.3 Safety copy (counsel + community reviewers)
- [ ] Emergency lexicon lists reviewed by a native speaker for the languages marketed at launch (Q6); `reviewed_by` set in `emergency.yaml`.
- [ ] Scam copy: no sentence names a specific organization as fraudulent; "likely"/"possible" wording approved.

### 18.4 FTC Act §5 and HBNR (counsel)
- [ ] Written opinion on HBNR applicability (vendor of PHR? "multiple sources"?) and on treating misattested unpaid-key use as a breach (§13.2).
- [ ] Substitute-notice plan acceptable given that the operator holds no contact information; who signs the FTC notice.
- [ ] Claims audit: every `approved_keys` string, the policy (§16) and STORE_LISTING read against the implementation; `test_privacy_claims.py` green.

### 18.5 State law (counsel)
- [ ] WA MHMDA: applicability at pilot scale; separate "Consumer Health Data Privacy Policy" link requirement; consent sufficiency of S2.
- [ ] CA CPRA: thresholds; SPI notice; whether a "Limit the Use of My Sensitive Personal Information" link is required when SPI is used only for the requested service.
- [ ] VA CDPA (pilot geography) and other state acts: thresholds, consent for sensitive data, data protection assessment.
- [ ] State-specific paragraphs for §16 item 12 drafted.

### 18.6 Store filings (counsel + WP8)
- [ ] Apple: organization developer account exists (5.1.1(ix)); nutrition label stance (§10.3 conservative vs minimal) decided; 18+ rating set; Notes for Review (§10.5) final; privacy manifest values verified against the first rejection e-mail if any.
- [ ] Google Play: Health apps declaration, Data safety (§11.1), target audience 18+, content rating, no `READ_MEDIA_*` in the merged manifest (§12.1).
- [ ] Terms of use / EULA decision (none exists today; Apple's standard EULA applies by default) — §19.
- [ ] Trademark clearance for "ProxyHealth AI" and the tagline (not covered by the research files).

### 18.7 Engineering gates (proof = command or file)
- [ ] `ENV=production`; every slot `billing:true` with the Cloud Billing screenshot filed; `ALLOW_UNPAID_KEYS`, `ALLOW_UNPAID_REAL_DOCUMENTS`, `LOG_LEVEL=debug` unset; `GET /v1/config` on the store API returns `data_use_tier: paid`.
- [ ] AI Studio developer logging OFF for every production project (dated screenshot in RUNBOOK).
- [ ] `apps/api/.venv/bin/pytest apps/api` green incl. `test_privacy_claims.py`, `test_readability.py`, `test_logging_allowlist.py`, `test_errors.py`, `test_loader.py::test_emergency_numbers_match_fixed_copy`, and `test_privacy_claims.py::test_server_writes_only_at_reviewed_sites` (every server file write is a reviewed site — BUILD_PLAN §7 row 11; it replaces the old `open(… 'w')` grep, which flagged the pack-cache write and missed `write_text`/`sqlite3.connect`).
- [ ] iOS: vault directory excluded from iCloud backup and verified on a dev build (§10.2) — or iOS submission deferred.
- [ ] Android merged manifest matches §12.1; `android.allowBackup: false`.
- [ ] On any web host other than EAS Hosting: `make host-rules` applied and `python3 scripts/web-host-rules.py apps/mobile/dist --verify <host>` green, so reminder and clerk deep links (`/result/<id>/…`) open the app (DEPLOYMENT §2.3).
- [ ] `make export-web && test -f apps/mobile/dist/privacy/index.html`; the page contains no `forbidden_phrases`; `CONSENT_VERSION` in `.env` equals the version printed on the page.
- [ ] Accessibility matrix (§15) recorded in RUNBOOK; Accessibility Nutrition Label claims limited to passed items.
- [ ] No analytics, ads, attribution or crash SDK in `apps/mobile/package.json`; no `AIza` string in `apps/mobile`.
- [ ] No truncation marker remains in `docs/*.md` (the BUILD_PLAN §7 #16 grep prints nothing); STORE_LISTING, DEPLOYMENT, RUNBOOK exist.

---

## 19. Open questions for the user (continue DECISIONS §12 Q1–Q11 and PRODUCT_SPEC Q12–Q14)

- **Q15 Legal identity for the policy.** Operator legal name, postal address and privacy contact e-mail to print in §16 items 1 and 17 (and to use as the FTC/HBNR contact). Blocks the policy page and STORE_LISTING.
- **Q16 iOS backup exclusion.** Approve a WP0 install window for a config plugin/native module that sets `NSURLIsExcludedFromBackupKey` on the vault directory (§10.2), or ship Android first and defer iOS? (A v1 iOS build with saving disabled is the only other honest option.)
- **Q17 Label stance.** Accept the conservative Apple nutrition label / Play Data safety answers (§10.3, §11.1), or ask counsel to approve the minimal variant that treats Google's abuse log as service-provider processing?
- **Q18 Breach-notice channel.** Approve a LATER contract change adding `ServerConfig.notice {id, severity, text_key}` so the app can show a dated notice without a consent bump (§13.2)? Until then the channel is the policy page + a `CONSENT_VERSION` bump.
- **Q19 Terms of use.** Do you want a Terms of Use / EULA (no-law-firm, no-clinician, no-warranty, 18+, US-only) drafted by counsel and linked beside the policy, or rely on the stores' default EULAs?
- **Q20 State exposure.** Are Washington, California or other non-pilot states expected among users at launch (§13.3)? This decides whether the WA/CA paragraphs and links are required now or SHOULD.
- **Q21 Translated policy.** Publish machine-translated copies of the privacy policy at `/privacy/<tag>/` at launch (labelled), or English only until reviewed?
- **Q22 Vertex AI.** Weigh Google Cloud Vertex AI Generative AI terms (zero-data-retention options, enterprise DPA; same health/18+ restrictions) against Gemini API paid keys for the store release (§14). Cost and key-pool changes would follow.
- **Q23 Demo build in stores.** Confirm the labelled demo build (`EXPO_PUBLIC_DEFAULT_SAMPLE_MODE=true`, `demo` tier) is for judges/internal tracks only and never published publicly (§3).
- **Q24 Accessibility label claims.** Which Accessibility Nutrition Labels to claim on the App Store after the §15 matrix (VoiceOver, Larger Text, Sufficient Contrast, Reduced Motion proposed).
- **Q25 Incident roles.** Who is on-call for §13.2 (operator), who is counsel of record, and who approves public notices?
