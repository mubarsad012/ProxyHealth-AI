# ProxyHealth AI — Deployment

Owner: WP8. Written 2026-09-29 from `docs/ARCHITECTURE.md` §5.3 and §6, `docs/COMPLIANCE_PRIVACY.md` §2.4, §3, §12, §16, `docs/research/expo.md` §3 (hosting) and §4 (EAS). Operations after launch (billing, key rotation, re-verification, incidents) live in `docs/RUNBOOK.md`. Store text lives in `docs/STORE_LISTING.md`.

Three things are deployed, plus one demo copy:

| Deployable | Source | Recommended host | Notes |
|---|---|---|---|
| API | `apps/api` (`Dockerfile`) | Google Cloud Run, same Google account as the billed Gemini projects (DECISIONS Q11) | in-memory only; secrets from Secret Manager |
| Demo API | same image, `AI_PROVIDER=mock` | a second Cloud Run service | zero keys, `data_use_tier: demo`; for judges and the demo build |
| Web app + privacy policy | `apps/mobile` → `npx expo export --platform web` → `dist/` | EAS Hosting (`https://proxyhealth.expo.app`) or any static host | `dist/privacy/index.html` is the public policy (`PRIVACY_POLICY_URL`) |
| iOS / Android binaries | `apps/mobile` + `eas.json` | EAS Build → EAS Submit | Android first; iOS after the organization Apple account (Q2) and the iCloud gate (Q16) |

## 0. Placeholders that need a decision (do not ship with these)

| Value | Placeholder today | Where it is used | Decided by |
|---|---|---|---|
| iOS bundle identifier / Android package | `org.proxyhealth.app` | `apps/mobile/app.json` `ios.bundleIdentifier`, `android.package` — **cannot change after the first store upload** | user — DECISIONS Q4 |
| Web host | `https://proxyhealth.expo.app` (EAS Hosting subdomain; custom domains need a paid EAS plan) | `CORS_ORIGINS`, links in the app | Q4 |
| Privacy policy URL | `https://proxyhealth.expo.app/privacy` | API `PRIVACY_POLICY_URL` → `/v1/config.privacy_policy_url` → every "Read the full privacy policy" link | Q4 |
| API hosts | `https://<prod-api>`, `https://<staging-api>`, `https://<demo-or-staging-api>`, `https://<demo-api-mock>` | `apps/mobile/eas.json` build profiles (`EXPO_PUBLIC_API_URL`, baked into each binary) | operator |
| Apple `ascAppId`, organization `appleTeamId` | `<from App Store Connect>`, `<organization team id>` | `eas.json` `submit.production.ios` | Q2 |
| Operator identity in the policy | `TODO` blocks | `apps/mobile/public/privacy/index.html` | COMPLIANCE_PRIVACY Q15 |

Nothing in the code depends on these values; they are configuration. `scripts/ci.sh` (step `eas-https`) fails if a `preview` or `production` profile's API URL is not `https://`.

---

## 1. API on Google Cloud Run

### 1.1 One-time project setup

Use the Google account that owns the **billed** Gemini projects (auditability of the paid-tier invariant, D-01). The commands are the standard `gcloud` CLI (not from the research files — check `gcloud --help` for your SDK version).

```sh
PROJECT=proxyhealth-prod            # the Cloud Run project (can be one of the Gemini projects)
REGION=us-east4                     # Northern Virginia, near the pilot users
gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
gcloud artifacts repositories create proxyhealth --repository-format=docker --location="$REGION"
```

Secrets (values never touch the repo, the image or the mobile app — CLAUDE.md rule 5):

```sh
# JSON list, one key per DISTINCT billed project; "billing": true is your attestation (RUNBOOK §1).
printf '%s' '[{"key":"AIza…","project":"proxyhealth-prod-a","billing":true},{"key":"AIza…","project":"proxyhealth-prod-b","billing":true}]' \
  | gcloud secrets create GEMINI_KEYS --data-file=-
openssl rand -hex 32 | gcloud secrets create INSTALL_HASH_SECRET --data-file=-
openssl rand -hex 24 | gcloud secrets create ADMIN_TOKEN --data-file=-
# optional: only if the app build sends X-App-Token (EXPO_PUBLIC_APP_TOKEN is NOT a secret — it ships in the app)
openssl rand -hex 16 | gcloud secrets create APP_TOKEN --data-file=-
```

Grant the Cloud Run runtime service account `roles/secretmanager.secretAccessor` on those secrets.

### 1.2 Build and deploy

```sh
IMAGE="$REGION-docker.pkg.dev/$PROJECT/proxyhealth/api:$(git rev-parse --short HEAD)"
gcloud builds submit apps/api --tag "$IMAGE"

gcloud run deploy proxyhealth-api \
  --image "$IMAGE" --region "$REGION" --allow-unauthenticated \
  --cpu 1 --memory 1Gi --concurrency 32 --timeout 120 \
  --min-instances 0 --max-instances 4 \
  --set-env-vars "ENV=production,AI_PROVIDER=gemini,LOG_LEVEL=info,CORS_ORIGINS=https://proxyhealth.expo.app,PRIVACY_POLICY_URL=https://proxyhealth.expo.app/privacy,CONSENT_VERSION=2026-10-01" \
  --set-secrets "GEMINI_KEYS=GEMINI_KEYS:latest,INSTALL_HASH_SECRET=INSTALL_HASH_SECRET:latest,ADMIN_TOKEN=ADMIN_TOKEN:latest"
```

Why these values (ARCHITECTURE §5.3): one worker per instance because the key pool and rate limits are in-process state (the image's `CMD` runs `--workers 1 --limit-concurrency 32`); request timeout 120 s covers `FAILOVER_DEADLINE_S=100`; min instances 0 (1 during demos to avoid cold starts); no persistent disk — `VAR_DIR=/app/var` lives in the container's memory-backed filesystem, so key-pool cooldowns are re-learned after a cold start and generated language packs are regenerated on demand. `--max-instances` caps spend: each instance has its own key-pool view, so keep it small. Rate limiting (D-08): the image sets `TRUSTED_PROXY_HOPS=1` (`apps/api/Dockerfile`) because Cloud Run's (and Fly.io's) front end appends the real client address to `X-Forwarded-For`; the server rate-limits the `/24` / `/48` class of the entry that many places from the right and never trusts entries further left. Behind an **external HTTPS load balancer** in front of Cloud Run there are two appending proxies: set `TRUSTED_PROXY_HOPS=2` there (with 1 every user would share the load balancer's bucket; with too many a client could pick its own class). The per-IP-class buckets (`RATE_LIMIT_IP_PER_MINUTE=60`, `RATE_LIMIT_IP_PER_DAY=1000`) apply to every model-calling request; a large carrier NAT or shared IPv6 `/48` shares one bucket, so raise them if real users see `429 rate_limited` with `details.bucket = "ip_class"` (RUNBOOK §2.3).

Production guards the server enforces at boot (COMPLIANCE_PRIVACY §2.4): every `GEMINI_KEYS` slot `billing:true` (unless `ALLOW_UNPAID_KEYS=1`, which a store deployment must never set); `ALLOW_UNPAID_REAL_DOCUMENTS` refused; model IDs validated. Never set `ALLOW_UNPAID_KEYS`, `ALLOW_UNPAID_REAL_DOCUMENTS` or `LOG_LEVEL=debug` in production.

Verify after every deploy:

```sh
API=https://<prod-api>
curl -fsS "$API/health"      # provider "gemini", keys_healthy ≥ 1, data_use_tier "paid"
curl -fsS "$API/v1/config" | python3 -c 'import json,sys; c=json.load(sys.stdin); print(c["data_use_tier"], c["consent_version"], c["privacy_policy_url"])'
# smoke.py asserts mock mode: run it against the demo service (§1.5), never against production
curl -fsS -H "X-Admin-Token: $(gcloud secrets versions access latest --secret ADMIN_TOKEN)" "$API/v1/admin/keys"
```

`data_use_tier` must read `paid` before any store build points at this host (STORE_LISTING §0 B4).

### 1.3 Logging retention (COMPLIANCE_PRIVACY §2.3)

The app writes only the content-free allow-listed JSON fields to stdout; uvicorn's access log is off. Cloud Run adds its own request log (method, path, status, latency, client IP). Retention targets: **30 days** for the structured log, **7 days** for request logs.

```sh
# 30-day bucket for everything the service prints (content-free structured log)
gcloud logging buckets create proxyhealth-app --location=global --retention-days=30
gcloud logging sinks create proxyhealth-app-sink logging.googleapis.com/projects/$PROJECT/locations/global/buckets/proxyhealth-app \
  --log-filter='resource.type="cloud_run_revision" AND resource.labels.service_name="proxyhealth-api" AND log_id("run.googleapis.com/stdout")'
# 7-day bucket for Cloud Run request logs (they carry client IPs)
gcloud logging buckets create proxyhealth-requests --location=global --retention-days=7
gcloud logging sinks create proxyhealth-requests-sink logging.googleapis.com/projects/$PROJECT/locations/global/buckets/proxyhealth-requests \
  --log-filter='resource.type="cloud_run_revision" AND log_id("run.googleapis.com/requests")'
# keep both out of the _Default bucket (default retention is longer)
gcloud logging sinks update _Default --add-exclusion='name=proxyhealth,filter=resource.type="cloud_run_revision" AND resource.labels.service_name=~"^proxyhealth-"'
```

Do not put a logging proxy, API gateway or CDN in front that records request bodies or caches POST responses. AI Studio developer logging stays **OFF** for every production project (RUNBOOK §1.3).

### 1.4 Monitoring

- Uptime check on `GET /health` every 5 min from 3 regions; alert on failure.
- Alert when `keys_healthy == 0` for 5 min: uptime check with a response-content matcher that fails when the body contains `"keys_healthy":0` (ARCHITECTURE §5.3).
- Alert on the log-based metric "count of `status >= 500`" > 5 in 10 min, and on `error_code="quota_exhausted"` spikes (RUNBOOK §2).

### 1.5 The demo service (zero keys)

```sh
gcloud run deploy proxyhealth-demo --image "$IMAGE" --region "$REGION" --allow-unauthenticated \
  --cpu 1 --memory 1Gi --concurrency 32 --timeout 120 --min-instances 1 --max-instances 2 \
  --set-env-vars "ENV=production,AI_PROVIDER=mock,CORS_ORIGINS=https://proxyhealth.expo.app,PRIVACY_POLICY_URL=https://proxyhealth.expo.app/privacy" \
  --set-secrets "INSTALL_HASH_SECRET=INSTALL_HASH_SECRET:latest"
apps/api/.venv/bin/python apps/api/scripts/smoke.py --base-url https://<demo-api-mock>
```

`/v1/config` answers `data_use_tier: demo`; the consent screen shows "Sample mode". The `demo` EAS profile points at this service. Demo builds are for judges and internal tracks only, never a public store release (COMPLIANCE_PRIVACY Q23).

### 1.6 Other hosts (same image)

- **Fly.io**: `fly launch --no-deploy` in `apps/api`, `internal_port = 8080`, `[http_service] auto_stop_machines = true`, `fly secrets set GEMINI_KEYS=… INSTALL_HASH_SECRET=… ADMIN_TOKEN=…`, env as §1.2; one machine size `shared-cpu-1x` / 1 GB; request timeout ≥ 120 s.
- **Render**: Docker web service from `apps/api/Dockerfile`, env group with the §1.2 variables, secrets as secret env vars, health check path `/health`.
- Any host: HTTPS only, no request-body logging, logs kept 30/7 days as §1.3, one worker per instance; set `TRUSTED_PROXY_HOPS` to the number of proxies that append to `X-Forwarded-For` in front of uvicorn (the image's `1` fits Cloud Run and Fly.io, whose front end appends one entry; check any other host's proxy chain before relying on it; `0` only when uvicorn is reached directly).

---

## 2. Web app and privacy policy (static export)

`app.json` sets `web.output: "static"`: one HTML file per route, no server code. `EXPO_PUBLIC_API_URL` is **baked in at export time**, so build once per environment, and always with `--clear` (Metro's cache can otherwise inline an earlier URL).

```sh
export PATH="$HOME/.local/node/bin:$PATH"
cd apps/mobile
EXPO_PUBLIC_API_URL=https://<prod-api> EXPO_PUBLIC_APP_ENV=production npx expo export --platform web --clear
test -f dist/privacy/index.html     # public/ is copied into dist/ — this is PRIVACY_POLICY_URL
```

(`make export-web` does the same with `EXPO_PUBLIC_API_URL` defaulting to `http://127.0.0.1:8000` — local builds only.) Then add the web origin to the API's `CORS_ORIGINS` (DEPLOYMENT §1.2) — nothing else on the API changes.

### 2.1 EAS Hosting (recommended; research/expo.md §3)

```sh
npx eas-cli@latest deploy            # preview URL https://proxyhealth--<id>.expo.app
npx eas-cli@latest deploy --prod     # https://proxyhealth.expo.app
```

Free plan: 100,000 requests/month, 1 GB storage; custom domains need a paid plan (Q4). EAS Hosting runs on Cloudflare Workers. Whether it lets a static export set the response headers below is **not covered by the research files — check the EAS Hosting docs at deploy time**; if it cannot, serve the same `dist/` from Cloudflare Pages or Netlify with the `_headers` file below **and the dynamic-route rewrites of §2.3** (without them `/result/<id>` and `/papers/member/<id>` are the host's 404), and keep EAS Hosting for previews. EAS Hosting is the only host that resolves Expo Router's `[param]` files by itself; it is the supported web host, and any other static host is supported only with §2.3 applied and verified.

### 2.2 Response headers (exact values)

No COOP/COEP headers (no SharedArrayBuffer / sqlite-wasm is used — ARCHITECTURE §5.3). The inline script Expo Router writes into every page is `globalThis.__EXPO_ROUTER_HYDRATE__=true;` (checked in the SDK 57 export on 2026-09-29), whose CSP hash is `sha256-67fhrP0+BkBqmgGGXTtgiVO/9EQs3QruYNU/7fnRkI8=`; `react-native-web` injects `<style>` tags at run time, hence `'unsafe-inline'` for styles only. Ship the CSP as **Report-Only** first, walk the demo script with the browser console open, then switch the header name to `Content-Security-Policy`.

Netlify / Cloudflare Pages `_headers` (put it in `dist/` at deploy time, not in `public/`):

```text
/*
  Strict-Transport-Security: max-age=31536000; includeSubDomains
  X-Content-Type-Options: nosniff
  Referrer-Policy: no-referrer
  X-Frame-Options: DENY
  Permissions-Policy: camera=(self), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()
  Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self' 'sha256-67fhrP0+BkBqmgGGXTtgiVO/9EQs3QruYNU/7fnRkI8='; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' blob:; worker-src 'self' blob:; connect-src 'self' https://<prod-api>; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
  Cache-Control: no-cache
/_expo/static/*
  Cache-Control: public, max-age=31536000, immutable
/assets/*
  Cache-Control: public, max-age=31536000, immutable
/privacy/*
  Cache-Control: public, max-age=300
```

Why each one: HSTS keeps every visit on HTTPS; `nosniff` stops MIME confusion; `Referrer-Policy: no-referrer` means a click to a resource's website never tells it the user came from a paper-reading app; `X-Frame-Options`/`frame-ancestors` stop the app being framed on another site; `Permissions-Policy` allows only the camera (web capture) and nothing else; `connect-src` limits network calls to our API; HTML is `no-cache` so a new deploy is seen at once, while hashed bundles under `/_expo/static/` and `/assets/` are immutable.

Vercel: `vercel.json` with `"cleanUrls": true`, the dynamic-route `"rewrites"` of §2.3 (not a catch-all SPA rewrite — every static route has its own HTML file), and the same header set under `"headers": [{"source": "/(.*)", "headers": [...]}]`.

### 2.3 Dynamic routes on static hosts (Netlify, Cloudflare Pages, Vercel)

The static export writes a dynamic route as a file whose name keeps the brackets: `dist/result/[id].html`, `dist/result/[id]/{chat,clerk,help,quicksheet,source}.html` and `dist/papers/member/[id].html` (`dist/_expo/.routes.json` holds only `{"redirects": []}`, no route table). A plain static host maps `/result/abc` to no file, so a reload, a shared link, and the reminder and clerk deep links answer the host's 404 instead of the app (for a session-only result the app itself would show S18 "I could not find that page"). EAS Hosting resolves these files; the other hosts need one rewrite per dynamic route. Generate them from the export — never by hand, so a new route cannot be missed:

```sh
export PATH="$HOME/.local/node/bin:$PATH"
make export-web EXPO_PUBLIC_API_URL=https://<prod-api>    # or the §2 command
make host-rules      # = python3 scripts/web-host-rules.py apps/mobile/dist --write --check
```

That writes `dist/_redirects` (Netlify and Cloudflare Pages read the same file) and `dist/404.html` (a copy of Expo Router's `+not-found.html`, the S18 screen, which these hosts serve for unknown paths). Today's rules, most specific first:

```text
/papers/member/:id      /papers/member/[id]      200
/result/:id/chat        /result/[id]/chat        200
/result/:id/clerk       /result/[id]/clerk       200
/result/:id/help        /result/[id]/help        200
/result/:id/quicksheet  /result/[id]/quicksheet  200
/result/:id/source      /result/[id]/source      200
/result/:id             /result/[id]             200
```

`200` makes each rule a rewrite (the address bar keeps `/result/abc`; query strings such as `?block=…&page=…` pass through). Targets carry no `.html` because both hosts serve `x.html` for `/x`, and Cloudflare Pages answers a `.html` target with a 308 to the extension-less path. Rewrites apply only when no real file matches, so static routes are untouched. For Vercel, `python3 scripts/web-host-rules.py apps/mobile/dist --vercel` prints the `cleanUrls` + `rewrites` block to paste into `vercel.json` (`/result/:id` → `/result/[id]` …).

Verify on the preview deploy before promoting it — host rewrite semantics are not covered by the research files, so this check is the proof:

```sh
python3 scripts/web-host-rules.py apps/mobile/dist --verify https://<preview-host>
# ok  https://<preview-host>/result/sample-id … one line per rule; exit 1 on any 404 or non-app page
```

Then open `https://<preview-host>/result/sample-id` and `/papers/member/sample-id` in a browser: the first shows S18 "I could not find that page" (results are session-only, so a cold link has none), the second the member screen. `scripts/ci.sh` (step `web-export`) runs `web-host-rules.py --check` on every export, so a dynamic route without a rule fails CI.

The privacy page itself (`/privacy/`) must stay public, HTML (never a PDF), not geofenced, readable without JavaScript and without analytics (COMPLIANCE_PRIVACY §16); `apps/api/tests/unit/test_privacy_claims.py` checks it on every CI run.

---

## 3. Mobile binaries (EAS Build and Submit)

No Xcode here: iOS binaries build on Expo's macOS cloud runners; EAS Submit runs from any OS (research/expo.md §4). You need an Expo account; Apple Developer Program (organization, Q2) and Google Play Developer accounts for submission. `eas-cli` is not installed — always `npx eas-cli@latest …`.

### 3.1 Profiles (`apps/mobile/eas.json`)

| Profile | Distribution | `EXPO_PUBLIC_API_URL` | Other env | Use |
|---|---|---|---|---|
| `development` | internal, Android APK, dev client | `https://<demo-or-staging-api>` | `EXPO_PUBLIC_APP_ENV=development` (developer section visible) | device testing (RUNBOOK §7.1) |
| `preview` | internal, Android APK | `https://<staging-api>` (paid tier, staging) | `EXPO_PUBLIC_APP_ENV=staging` | testers, store screenshots |
| `demo` | internal (extends `preview`) | `https://<demo-api-mock>` (`AI_PROVIDER=mock`) | `EXPO_PUBLIC_DEFAULT_SAMPLE_MODE=true`, `EXPO_PUBLIC_APP_ENV=demo` | judges; never a public store release (Q23) |
| `production` | store (`.ipa` / `.aab`), `autoIncrement` | `https://<prod-api>` (must answer `data_use_tier: paid`) | `EXPO_PUBLIC_APP_ENV=production` | App Store / Play |

`cli.appVersionSource: "remote"` lets EAS own `buildNumber` / `versionCode`. `EXPO_PUBLIC_*` values are public (they ship inside the app) — never put a secret there.

### 3.2 Sequence

```sh
export PATH="$HOME/.local/node/bin:$PATH"; cd apps/mobile
npx expo config --type prebuild > /dev/null                      # config plugins, icons, strings resolve
npx eas-cli@latest build --profile development --platform android   # day one
npx eas-cli@latest build --profile development --platform ios       # after the org Apple account (Q2)
npx eas-cli@latest build --profile production --platform all        # store binaries
npx eas-cli@latest submit --profile production --platform android   # service-account JSON, track "internal" first
npx eas-cli@latest submit --profile production --platform ios       # ascAppId + org appleTeamId
```

Before the first production build: SDK 58 upgrade in a WP0 install window (`npx expo install expo@^58.0.0 --fix`; `File.write` becomes async; iOS RTL follows `I18nManager` — ARCHITECTURE §5.3); the Android merged-manifest check (RUNBOOK §7.2); the iOS gates (RUNBOOK §7.3). **iOS status 2026-10-01: blocked** — the vault and SQLite folders are not yet excluded from iCloud backup (no SDK 57 API; needs a config plugin or native module in an install window plus a dev-build check — COMPLIANCE_PRIVACY §10.2), so the `ios` production build and `submit --platform ios` wait; ship Android first. Free plan budget: 15 Android + 15 iOS builds a month, 45-minute timeout. Permission strings, `ios.privacyManifests` and `ios.infoPlist` are baked into the binary: changing them needs a new build and submission, not an OTA update. Never create or edit `apps/mobile/ios/` or `apps/mobile/android/`.

### 3.3 Store configuration already in `app.json`

Name "ProxyHealth AI", slug and scheme `proxyhealth`, version `1.0.0`; icons and splash from `assets/images/` (drawn by the repo-root `scripts/make_artwork.py`: opaque 1024 iOS icon, adaptive foreground inside the 66 % safe zone on `#0B4F8A`, monochrome, splash tile, 48 px favicon, 96 px notification glyph) and `assets/expo.icon` (iOS 26 layered icon); camera and photo strings on the plugins and mirrored in `ios.infoPlist`; `android.allowBackup: false`; `blockedPermissions` READ_MEDIA_IMAGES / READ_MEDIA_VIDEO / RECORD_AUDIO; `ios.config.usesNonExemptEncryption: false`; `ios.privacyManifests` with the required-reason APIs (UserDefaults `CA92.1`, FileTimestamp `C617.1`, SystemBootTime `35F9.1`), `NSPrivacyTracking: false`, no tracking domains, and `NSPrivacyCollectedDataTypes` mirroring the conservative nutrition label (STORE_LISTING §2.2 — the data-type identifiers are Apple's documented names, written from general knowledge; confirm against the first App Store Connect upload).

---

## 4. Secrets and where they live

| Secret | Lives in | Used by | Never in |
|---|---|---|---|
| `GEMINI_KEYS` (JSON, one key per billed project) | Google Secret Manager; GitHub Actions repository secret for the `live-golden` job only | API | the repo, the image, the app, logs (`SecretStr`; `/v1/admin/keys` shows only `key_last4`) |
| `INSTALL_HASH_SECRET` | Secret Manager | API (HMAC of install ids) | same |
| `ADMIN_TOKEN` | Secret Manager | operator → `/v1/admin/keys` | same |
| `APP_TOKEN` (optional) | Secret Manager; the matching `EXPO_PUBLIC_APP_TOKEN` is public by nature | API | treat it as abuse friction, not security |
| Google Play service account JSON | EAS (upload as a submit credential) or a local git-ignored `apps/mobile/google-service-account.json` | `eas submit` | the repo (`.gitignore` covers `*service-account*.json`) |
| Apple credentials | EAS-managed (App Store Connect API key) | `eas build` / `eas submit` | the repo |
| Local development | `apps/api/.env` (git-ignored; start from `apps/api/.env.example`) | `make dev` | commits |

Rotation and leak handling: RUNBOOK §2.

---

## 5. Release checklist (production)

1. `scripts/ci.sh` green on the release commit; `make smoke` green; the `docker` CI job green.
2. Production API deployed (§1.2) with every guard; `GET /v1/config` → `paid`, `consent_version` = the page's printed version, `privacy_policy_url` = the live `/privacy`.
3. Web exported with the production API URL and deployed with the §2.2 headers; `/privacy/` loads without JavaScript; on any host other than EAS Hosting, `make host-rules` applied and `web-host-rules.py --verify <host>` green (§2.3).
4. `CORS_ORIGINS` = the web host only.
5. EAS `production` build; manifest check logged; STORE_LISTING §0 blockers cleared (B5, the iOS iCloud-backup exclusion, is still open on 2026-10-01 — Android only until it closes); COMPLIANCE_PRIVACY §18 ticked.
6. Tag the commit (`v1.0.0-rc1` per BUILD_PLAN §6) — the orchestrator/maintainer does git operations.
