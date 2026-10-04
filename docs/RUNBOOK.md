# ProxyHealth AI — Runbook (operations)

Owner: WP8 (the operator on call runs it). Written 2026-09-29 (§1.5 added 2026-10-04 for D-32) from `docs/DECISIONS.md` D-01, D-03, D-07, D-08, `docs/COMPLIANCE_PRIVACY.md` §2–§3, §9, §12.1, §13.2, §15, §18, `docs/RESOURCE_DB.md` §9 and `docs/research/gemini.md` §3. Deployment commands are in `docs/DEPLOYMENT.md`. Every action that produces evidence gets a dated line in §9 ("Records").

## 1. Billing and the data-use tier (do this before any real paper is read)

The Gemini API terms treat a key as **Paid Services only when its Google Cloud project has an active Cloud Billing account attached**. On unpaid quota Google may use prompts and responses to improve its products, with human review, and asks developers not to send personal information there. The API encodes this as the per-key `billing` attestation (D-01) and blocks real papers on `unpaid`/`mixed` pools with `403 unpaid_tier_real_documents_disabled`.

### 1.1 Set up the paid tier

1. Create **two or more Google Cloud projects** (e.g. `proxyhealth-prod-a`, `proxyhealth-prod-b`). Rate limits are per project, not per key, so extra keys in one project add nothing (the server refuses duplicate `project` labels at boot).
2. Attach the organization's Cloud Billing account to **each** project. Screenshot the project's Billing page (project id + billing account visible, date visible) and file it (§9).
3. In each project create one Gemini API key (AI Studio → API keys, "Create API key in existing project"). Restrict it to the Generative Language API.
4. Set a Cloud Billing **budget with alerts** per project (50 % / 90 % / 100 % of the monthly cap the billing owner accepted — DECISIONS Q1).
5. Read each project's per-model limits in AI Studio (they are no longer published centrally) and, if needed, set `RPD_SOFT_CAP_PRO` / `RPD_SOFT_CAP_FAST` below the daily limit.
6. Put the keys into Secret Manager as `GEMINI_KEYS` (DEPLOYMENT §1.1) with `"billing": true` **only** for projects whose screenshot you just filed. Marking an unbilled key as billed makes every paid-tier privacy sentence false and is treated as an incident (§6, trigger a).
7. Deploy, then confirm `GET /v1/config` → `"data_use_tier": "paid"` and `GET /health` → `keys_healthy` equals the number of slots.

### 1.2 Region rule (D-03)

v1 is US-only. If any users are in the EEA, Switzerland or the UK, every key must be `billing:true` and `ALLOW_UNPAID_KEYS` must be unset. Store listings are published in US storefronts only.

### 1.3 AI Studio developer logging

For every production project: AI Studio → Logs → developer logging **OFF**. Confirm no interactions are stored. Screenshot with the date (§9). Re-check after anyone changes project settings, and quarterly (§4).

### 1.4 Dev and judging with free keys

Free (unbilled) keys run **sample papers only**. `ALLOW_UNPAID_REAL_DOCUMENTS=true` exists for synthetic test scans in `ENV=development`; it is a boot error in production. Never photograph a real person's paper through a free key — not your own, not a judge's.

### 1.5 Local AI and other OpenAI-compatible endpoints (test builds only; D-32)

`AI_PROVIDER=openai_compat` lets a development or staging API read papers with an open model on the API host (`local`) or, in development only, with a named vendor (`attested`). **Never in production:** `ENV=production` refuses the provider at boot, and a store build may point only at the `paid` tier (COMPLIANCE_PRIVACY §3). The developer's guide is `docs/LOCAL_AI.md`; these are the operator's checks.

1. **Install only with the developer's OK** (COMPLIANCE_PRIVACY Q26). `make local-ai-setup ARGS=--dry-run` shows the plan; `make local-ai-setup` asks y/N before Ollama (~200 MB) and before the model (3.4 GB for `qwen3.5:4b`) and stops when the disk budget is short. No agent and no CI job runs it.
2. **Point the API at it:** `scripts/use-local-ai.sh` (writes `apps/api/.env` from `apps/api/.env.local-ai.example`, backing up a different `.env`). Restart the API, then confirm `GET /v1/config` → `"provider": "openai_compat"`, `"data_use_tier": "local"`, `"ai_model_label": "Qwen"` and the raised `client_timeouts` (API_CONTRACT §3.2); `GET /health` → `keys_configured: 1`.
3. **Before the first real paper on `local`:** run the Ollama marker check (`docs/LOCAL_AI.md` §4: a unique word sent once, then `grep -r` under `~/.ollama`) with debug logging off, and log the result in §9. Ollama does not say whether it writes API prompts to disk; the consent line "Our server does not keep it" relies on this check. Repeat it after an Ollama upgrade.
4. **Check the pipeline on a sample first:** `make local-ai-check` (one sample paper through the real pipeline). Record the wall time and whether the output fit the schema in §9; they replace the research estimates.
5. **Keep the paper on the machine:** `OPENAI_COMPAT_BASE_URL` points at the open model's own server (Ollama, LM Studio), never at a loopback proxy or tunnel that forwards to a hosted API, and `OPENAI_COMPAT_MODEL_LABEL` names that model — the boot check sees only the loopback address, so this is your claim, like `billing` (COMPLIANCE_PRIVACY §3). API, model and browser on one machine (`make dev`); the phone over the same trusted Wi-Fi only; no tunnel with a real paper; `RECORD_FIXTURES` off; never copy a real paper into `apps/api/data/fixtures/`. Only the operator's own papers, or papers from someone who said yes.
6. **`attested` (development only):** before setting `OPENAI_COMPAT_NO_TRAINING_ATTESTED=1`, open the vendor's current API terms, find the no-training clause and log vendor, clause, URL and date in §9 (D-32 lists the clauses checked on 2026-10-01: Alibaba Model Studio International §4.48.1(e), Groq §4.2, Cloudflare Workers AI). Turn on the vendor's retention controls first (Groq Zero Data Retention; Alibaba "Free Quota Only"). Cerebras, Mistral free mode and OpenRouter `:free` qualify only after you find or switch on a no-training term; Chinese-hosted endpoints stay synthetic-samples-only except Alibaba International with the D-32 caveats. Set `OPENAI_COMPAT_VENDOR_NAME` to the vendor's name as the consent line should show it.
7. **Any other hosted endpoint** runs on `OPENAI_COMPAT_DATA_TIER=unpaid` (the default): sample papers only, real papers and typed text get `403`, like a free Gemini key.
8. **Switch back:** `scripts/use-local-ai.sh --off` (mock) or `--restore` (the previous `.env`); stop Ollama with `pkill -f 'ollama serve'`; `ollama rm qwen3.5:4b` frees 3.4 GB.

## 2. Keys: rotation, failure, quota

### 2.1 Routine rotation (quarterly, or when a team member with access leaves)

1. Create a new key in each project (AI Studio). Do not delete the old one yet.
2. `gcloud secrets versions add GEMINI_KEYS --data-file=new-keys.json` (same projects, new keys; delete the local file afterwards).
3. Redeploy (`gcloud run deploy … --set-secrets GEMINI_KEYS=GEMINI_KEYS:latest`) so every instance reads the new version.
4. Check `GET /v1/admin/keys` (header `X-Admin-Token`): every slot `healthy`, `key_last4` shows the new keys.
5. Delete the old keys in AI Studio. Rotate `ADMIN_TOKEN` and `APP_TOKEN` the same way. `INSTALL_HASH_SECRET` rotation resets every install's rate-limit bucket (harmless).

### 2.2 Emergency rotation (a key leaked or a project was compromised)

Delete the leaked key in AI Studio **first** (it stops working at once), then do §2.1 steps 2–4 with a fresh key, then follow §6 if the key could have been used to read users' papers.

### 2.3 What failure looks like

| Signal | Meaning | Action |
|---|---|---|
| `/v1/admin/keys` slot `cooling` | a 429 or 5xx; `Retry-After` cooldown ≤ 15 min | none unless all slots cool |
| slot `rpd_exhausted` | the 429 said the daily quota is used up; resets at midnight Pacific | add a project/key or raise the limit in AI Studio |
| slot `disabled` | 401/403 from Google (key revoked, API disabled, billing removed) | check billing and the key; rotate (§2.1) |
| `429 quota_exhausted` to users, `keys_healthy == 0` alert | every slot unavailable | users see "Our helper is very busy…" with retry time, Save to read later, Call 211, Try a sample paper; add capacity; never switch to mock silently (D-01) |
| `429 rate_limited` to real users, `details.bucket = "ip_class"` | many users behind one carrier NAT or IPv6 `/48`, or `TRUSTED_PROXY_HOPS` too low (everyone shares the proxy's class — DEPLOYMENT §1.2) | check `TRUSTED_PROXY_HOPS` first (1 on Cloud Run, 2 behind an external HTTPS load balancer); then raise `RATE_LIMIT_IP_PER_MINUTE` / `RATE_LIMIT_IP_PER_DAY` (defaults 60 / 1000) |
| `422 content_blocked` spikes | Gemini safety blocks | review `document_type` counts in the log; no retry on another key (by design) |
| `503 provider_not_configured` "Local AI server is not running." (`openai_compat`, loopback) | Ollama stopped (reboot, logout) | `scripts/setup-local-ai.sh --skip-smoke` restarts it; `curl -s http://127.0.0.1:11434/api/version` answers when it is up |
| `503 provider_not_configured` "The AI model is not available on the AI server." | the endpoint answered 404 for `OPENAI_COMPAT_MODEL_*` (model not pulled, or a wrong id) | `ollama list`; pull the model with the developer's OK, or fix the id in `.env` |
| the API will not boot on `openai_compat` | a boot rule (D-32): `local` needs a loopback URL and `OPENAI_COMPAT_MODEL_LABEL`; `attested` needs `ENV=development`, the vendor name, the attestation and a host off the denylist; hosted needs `OPENAI_COMPAT_API_KEY`; production refuses the provider | read the boot error (it names the rule and never prints a key); `scripts/use-local-ai.sh --dry-run` checks a preset |

## 3. Resource database: weekly links, quarterly re-verification

The Action Hub shows only organizations a person checked, each with "Verified on {date}" (D-10). Owner: the person named for DECISIONS Q5 (pilot geography). Cadence: RESOURCE_DB §9 (90 days for `manual_verify` entries; CI fails freshness at 120 days).

### 3.1 Weekly (automatic)

The `links` job in `.github/workflows/ci.yml` runs `apps/api/scripts/check_links.py --json links-report.json` every Monday and `--freshness`; it opens a GitHub issue when a link is `broken` or entries are stale. Triage within a week: a broken link is fixed or the entry's `link_health` set to `broken` (hidden from matches) the same day.

### 3.2 Quarterly (manual, first week of Jan / Apr / Jul / Oct)

1. `apps/api/.venv/bin/python apps/api/scripts/check_links.py` and `--freshness` locally; list every entry older than 90 days.
2. For each entry: open the official page; confirm name, phone, TTY, text line, hours, languages, cost and who it serves **on the organization's own site** (never from a directory or the model). Call the number if the page is unclear.
3. Edit `apps/api/data/resources/*.yaml`: update `verified_on` (today), `verification_method`, fields that changed. Remove or mark entries that closed (`link_health: broken`). Never invent a phone number.
4. Run `apps/api/.venv/bin/pytest apps/api/tests/unit/test_loader.py apps/api/tests/unit/test_matcher.py`, then `apps/api/.venv/bin/python apps/api/scripts/sync_to_mobile.py` (the bundled national fallbacks change), then `scripts/ci.sh`.
5. Log the pass in §9 with the count of entries checked and changed. The bundled fallback list ships in the next app build.

## 4. Quarterly compliance checks (same week as §3.2)

- AI Studio developer logging still OFF (§1.3); billing still attached to every `billing:true` project (§1.1 screenshots refreshed).
- `GET /v1/config` on production → `paid`; the privacy page prints the production `CONSENT_VERSION`.
- `apps/mobile/package.json` still has no analytics, ads, attribution or crash-reporting SDK; `grep -rn "AIza" apps/mobile` prints nothing.
- Log retention buckets still 30 / 7 days (DEPLOYMENT §1.3).
- Feedback counts reviewed (§5).

## 5. Feedback review (weekly)

"Was this clear?" and "Report a problem" store **counts only** in `var/feedback_counts.sqlite`, keyed by kind × surface × language × document type × card × resource × app version × platform × model (D-31). Review weekly: rising `offensive`, `wrong_fact` or `scam_missed` counts for one document type or language → open an issue, check the fixture/golden set, adjust prompts or the fixed copy; `resource_problem` for one `resource_id` → re-verify that entry now (§3.2 steps 2–4).

Known limitation: on Cloud Run without a mounted volume, `var/` is per-instance memory and the counts reset when an instance is recycled; there is also no admin endpoint that reads them (only `/v1/admin/keys`). Until one of those exists (DECISIONS §14 CL-062), run the API on a host with a small persistent volume for `var/` if feedback trends matter, or read the counts from a staging instance with a volume.

## 6. Incidents and breaches (COMPLIANCE_PRIVACY §13.2 — FTC Health Breach Notification Rule treated as applicable)

Roles (fill in — COMPLIANCE_PRIVACY Q25): on-call operator `TODO`, counsel of record `TODO`, approver of public notices `TODO`.

Treat as a **breach**: (a) a real paper reached Gemini Unpaid Services (misattested `billing:true`, `ALLOW_UNPAID_REAL_DOCUMENTS` outside development, a store build pointed at an unpaid API), or a vendor on an `openai_compat` test build under a false `OPENAI_COMPAT_NO_TRAINING_ATTESTED` statement, or any real person's paper other than the operator's own (or one given with a yes) on a `local`/`attested` test build; (b) developer logging found ON for a production project; (c) any server-side write of content (log line, temp file, crash dump); (d) a compromised `GEMINI_KEYS` secret or Cloud project; (e) a client bug that uploaded without consent. Incidents that are **not** breaches: a user's lost phone; a user forwarding their own quick sheet.

| Clock | Do |
|---|---|
| T+0–4 h | **Contain.** Delete/rotate affected keys (§2.2); redeploy with the offending slot removed; confirm `ENV=production` guards and `GET /health`, `/v1/admin/keys`, `/v1/config`; if a build points at an unpaid API, the 403 gate already blocks real papers — confirm in the log (`error_code=unpaid_tier_real_documents_disabled`). Bump `CONSENT_VERSION` so every client shows the consent screen again. Open a content-free incident log: request ids, `install_id_hash` values, time window. |
| T+0–72 h | **Scope** from the 30-day structured log: distinct `install_id_hash`, `page_count`, `document_type`, `category` in the window (there is no content to review). Any `category=medical` request means health information was involved. Preserve the log window past 30 days (export the bucket range). Call counsel. |
| ≤ 60 days after discovery | **Notify individuals.** We hold no names or addresses, so use substitute notice: a dated notice on the privacy page (`/privacy`), an in-app notice via the consent screen (the `CONSENT_VERSION` bump with the changed line), and media notice in any state with more than 500 affected. Plain language, translated into the launch languages: what happened, when, what data, what we did, what users can do, contact. |
| same time (≥ 500 affected) or within 60 days after the calendar year (< 500) | **FTC notice** on the Rule's form — counsel files. |
| after | Root cause in DECISIONS §14; re-run COMPLIANCE_PRIVACY §18; consider Vertex AI zero-retention terms (Q22). |

The privacy policy promises: "If your paper is ever exposed in a way you did not agree to, we will post a notice here and in the app within 60 days and tell you what happened." Keep that promise literally.

## 7. Builds, devices and store evidence

### 7.1 Android development build (first; no Apple account needed)

```sh
export PATH="$HOME/.local/node/bin:$PATH"; cd apps/mobile
npx expo config --type prebuild > /dev/null          # plugin strings and icon paths resolve
npx eas-cli@latest build --profile development --platform android
```

Install the APK on a mid-range Android. Walk `docs/DEMO_SCRIPT.md` in `en` then `prs`; check camera, masks (`masks[]`), the "Dates to remember" notification channel, the RTL restart prompt, the share-sheet PDF, TalkBack and 200 % font. Log the result in §9.

### 7.2 Merged manifest check (every Android store build — COMPLIANCE_PRIVACY §12.1)

Permissions must be exactly `CAMERA, INTERNET, POST_NOTIFICATIONS, VIBRATE` plus what `expo-notifications` adds for scheduling, and none of `READ_MEDIA_IMAGES, READ_MEDIA_VIDEO, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, RECORD_AUDIO, ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION`. Read them from the EAS build log or `aapt2 dump permissions <apk>`; paste the list into §9. A difference reopens the Data safety form (STORE_LISTING §3.2).

### 7.3 iOS gates (before any iOS submission)

- Vault directory **and** the SQLite folder (`Documents/vault/`, `Documents/SQLite/`) excluded from iCloud backup, verified on a dev build (COMPLIANCE_PRIVACY §10.2, Q16). **Status 2026-10-01: not done — blocker.** SDK 57's `expo-file-system` / `expo-sqlite` have no backup-exclusion API, so this needs a config plugin or small native module setting `NSURLIsExcludedFromBackupKey` (install window), then a dev-build check: inspect the flag on both folders (or confirm in Settings → iCloud → Manage Storage that a backup does not include them), log it in §9, and set `IOS_VAULT_BACKUP_EXCLUDED = true` in `features/vault/platformCopy.ts`. iOS `consent.line3` must also stop saying "stay only on this phone" until then (COMPLIANCE_PRIVACY §10.2). Until then: Android first.
- `["expo-sqlite", {"useSQLCipher": true}]` only after a dev build proves it; no copy claims it before.
- Privacy manifest values accepted by App Store Connect on the first upload (fix from the rejection e-mail if any).

### 7.4 Accessibility matrix (COMPLIANCE_PRIVACY §15)

Record VoiceOver, TalkBack, 200 % text, high contrast, reduced motion and RTL results per screen in §9 before claiming any Accessibility Nutrition Label.

### 7.5 Live golden gate (only with billed keys)

`RUN_LIVE=1 apps/api/.venv/bin/pytest apps/api/tests/live` and `apps/api/.venv/bin/python apps/api/scripts/eval_golden.py`, or the `live-golden` CI job (manual dispatch; needs the `GEMINI_KEYS` repository secret). Without keys record "not run — no keys".

## 8. Everyday commands

| Need | Command |
|---|---|
| Local stack, zero keys | `make dev` |
| Prove every endpoint works (mock) | `make smoke` |
| Full CI locally | `scripts/ci.sh` (resume with `CI_FROM=<step>`) |
| Key-pool state | `curl -H "X-Admin-Token: …" https://<api>/v1/admin/keys` |
| Tier and consent version | `curl https://<api>/v1/config` |
| Local AI (test builds, §1.5) | `make local-ai-setup ARGS=--dry-run` · `scripts/use-local-ai.sh` · `make local-ai-check` |
| Web deploy | DEPLOYMENT §2 |

## 9. Records (append one dated line per action; no personal data, no keys)

| Date | Who | What | Evidence |
|---|---|---|---|
| 2026-09-29 | WP8 | Runbook written; no production deployment exists yet; live gate not run — no keys (Q1) | this file |
| 2026-10-01 | DOCS | iOS iCloud-backup exclusion (§7.3) checked: not implemented, no SDK 57 API — iOS submission stays blocked; Android first | COMPLIANCE_PRIVACY §10.2 |
| 2026-10-04 | DOCS | §1.5 written for the `openai_compat` provider (D-32). Ollama not installed and no model pulled (waiting for the developer, COMPLIANCE_PRIVACY Q26); the Ollama marker check and `make local-ai-check` not run yet; no `attested` vendor configured | D-32; `docs/LOCAL_AI.md` |
