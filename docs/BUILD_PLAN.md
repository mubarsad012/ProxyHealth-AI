# ProxyHealth AI — Build Plan (work packages for parallel coding agents)

Status: **authoritative for process, sequencing and file ownership**. Written 2026-09-27 from `docs/DECISIONS.md` (D-01…D-31), `docs/API_CONTRACT.md` and `docs/ARCHITECTURE.md`. It mirrors and expands ARCHITECTURE §4 "Ownership map". On *what* to build, those three documents win and this file is corrected; on *who writes which file, when, and how "done" is proven*, this file wins. Every path is relative to `/Users/sadiqmubarak/Desktop/ProxyHealth`.

Coding agents build from this document without asking questions. If something is genuinely missing, the agent appends one line to `docs/DECISIONS.md` §14 "Change log" (see §1.2) and proceeds with the most conservative reading of the backbone.

> **Completed 2026-09-27 in the buildability pass (DECISIONS §14 CL-007; closes the BUILD_PLAN item of CL-006).** §5 (work packages in detail, including the §5.0 hand-off table), §6 (integration stage), §7 (definition of done) and Appendices A–F now exist below. Two appendices are deliberately pointers rather than copies so there is one source of truth: Appendix C (`en.json`) points at `PRODUCT_SPEC.md` Appendix A + `RESOURCE_DB.md` §3.3/§4 and states the rules; Appendix D (fixtures) mirrors ids, kinds and languages only and points at `PRODUCT_SPEC.md` §12.3 for the per-fixture expectations. The same pass changed four ownership facts (`ai/schema_guard.py` is WP0 permanently; WP0 also owns `tests/unit/{test_schema_guard,test_keys_exist}.py` and `tests/contract/test_m0_smoke.py`; WP7 owns the generated `apps/mobile/assets/fonts/**`, `assets/fixtures/index.ts`, `src/i18n/packs/index.ts`; WP0 creates day-0 type stubs for three WP4 files — §5.0) and corrected the mypy command in §1.4 (the previous form silently ran without `apps/api/pyproject.toml`).

---

## 0. Contents

1. Ground rules for every agent
2. Sequencing, phases and milestones
3. Work-package summary table
4. Cross-package interfaces fixed on day 0 (beyond the Pydantic contract)
5. Work packages in detail (WP0 … WP8)
6. Integration and verification stage
7. Definition of done for v1
8. Appendices — A: file → owner index · B: test file → owner · C: `en.json` key inventory with exact copy · D: fixture inventory · E: `languages.yaml` seed · F: open questions that block specific steps

---

## 1. Ground rules for every agent

### 1.1 Hard rules (from `CLAUDE.md` and ARCHITECTURE §7; repeated because they are load-bearing)

1. **Never run `npm install`, `npx expo install`, `pip install`, `npx expo install --fix` or `npm update` while any other agent is running.** Everything needed is installed. Missing package → stop, write a change-log line (§1.2), report. Verified present: `apps/api/.venv` has fastapi 0.141, pydantic 2.13, pydantic-settings, google-genai 2.25.0, pillow, reportlab, pyyaml, python-multipart, httpx, pypdfium2, slowapi, pytest 9, pytest-asyncio, pytest-cov, ruff, mypy, types-PyYAML. `apps/mobile/node_modules` has every package listed in `apps/mobile/package.json` (see ARCHITECTURE §3 and §4.2 below). Also installed since 2026-09-27 (DECISIONS §14): `arabic-reshaper` 3.0.1 and `python-bidi` 0.6.11 (neither ships type stubs → both are in the mypy `ignore_missing_imports` overrides, §4.1). **Not installed and therefore not usable** (verified 2026-09-27 against `.venv` and `node_modules`): Python `fonttools`/`pyftsubset`, `freezegun` (inject a `clock` callable instead), `ulid`/`python-ulid` (WP7 writes the 26-char Crockford-base32 ULID with `time.time_ns()` + `secrets.token_bytes(10)` in `feedback/store.py`, ~15 lines), `jq` is not assumed on PATH (scripts parse JSON in Python); mobile `expo-brightness`, `expo-local-authentication`, `expo-calendar`, `expo-updates`, `react-native-view-shot`, `@shopify/react-native-skia`, `fake-indexeddb` (so `storage.web.test.ts` covers the in-memory adapter only; the IndexedDB opt-in path is checked manually in §6). `expo-keep-awake` is present in `node_modules` only as a transitive dependency of `expo` — it is not in `package.json` and must not be imported. `eas-cli` is not installed and `npx eas-cli@latest` downloads it; no agent runs EAS commands during Phase 1.
2. **Write only files your work package owns** (§3, §5, Appendix A). Read anything. If you need a change in another package's file, file a change-log line; do not edit it.
3. **Never create or edit `apps/mobile/ios/` or `apps/mobile/android/`.** Native config goes in `app.json` and config plugins (WP4).
4. **Nothing user-supplied is ever written to disk or logs on the server** (no images, transcripts, quotes, model prose, filenames, base64). `apps/api/var/` holds only `keypool.json`, `langpacks/`, `feedback_counts.sqlite`.
5. **Contacts and organizations come only from the paper or `data/resources/*.yaml`; dates are computed only in `analysis/deadline_rules.py`; urgency only in `analysis/urgency.py`; the model never writes disclaimers, emergency copy or contacts.**
6. **Model IDs only from `MODEL_PRO` / `MODEL_FAST`.** Never `gemini-1.5*`, `gemini-2.0*`, `gemini-2.5*`, `*-latest`; never `temperature`, `top_p`, `top_k`, `candidate_count`, `thinking_budget`; never `thinking_level="minimal"` on a `gemini-3.8*` model.
7. **Every device feature has a `Platform.OS === 'web'` path** (`.web.ts` file or branch); on web, pickers and clipboard calls are the first statement inside the gesture handler.
8. **The whole app runs with zero API keys** (`AI_PROVIDER=mock`). Every feature you add must work in mock mode; mock is never a silent fallback for a real request.
9. **Copy rules:** 4th-grade reading level, no dramatizing, no emoji in controls, 56/72 pt targets, icon + word + color for urgency, speaker button after every paragraph, machine-translation banner on every `machine_translated` pack, privacy sentences literally true per tier. All user-facing strings come from `en.json` keys (Appendix C); new keys are requested from WP0 via the change log.
10. **Secrets only via `apps/api/.env`** (git-ignored). Commit `.env.example`. No secrets in the mobile app, ever.

### 1.2 Ownership, generated files, hand-offs, change log

- **Exclusive write scope.** A file has exactly one owner at any moment (Appendix A). Owners may create new files inside their owned directories freely; a new file outside an owned directory needs a change-log line first.
- **Created-then-handed-off files.** WP0 runs alone on day 0 and creates skeletons of files that other packages own afterwards (e.g. `main.py`, router stubs, seam modules). The hand-off moment is **milestone M0** (§2). After M0, WP0 never edits a handed-off file; the new owner never changes a signature that appears in `openapi.json` without a change-log line (WP0 regenerates the snapshot and types).
- **Generated files** are written only by their generator script, never by hand: `apps/api/openapi.json` (by `scripts/export_openapi.py`, run only by WP0), `apps/mobile/src/api/schema.d.ts` (by `npm run gen:types`, run only by WP0), `apps/mobile/src/i18n/packs/*.json`, `apps/mobile/src/i18n/packs/index.ts`, `apps/mobile/src/i18n/languages.ts`, `apps/mobile/assets/fixtures/**` (incl. `index.ts`), `apps/mobile/assets/resources/national_fallbacks.json`, `apps/mobile/assets/fonts/**`, `apps/mobile/locales/*.json` (all by `apps/api/scripts/sync_to_mobile.py`, run by WP7 and by CI `--check`; WP0 writes the minimal first version of the script and performs the very first sync on day 0, then hands the script to WP7). Anyone may *run* `sync_to_mobile.py` after M0 because it is a deterministic copy, but only WP7 edits it.
- **Change log.** ARCHITECTURE §4 says cross-WP needs are filed as one line in `docs/DECISIONS.md` §14 "Change log" (append-only). That section **already exists** as a bullet list (two orchestrator entries from 2026-09-27 plus CL-001…CL-006 from the consistency pass). Append bullets in the form `- CL-nnn YYYY-MM-DD (from → to) [open|done|rejected]: request`; the next free id is the last CL number in the file + 1 (re-read the tail right before appending; CL-055 was issued twice on 2026-09-29, so cite that pair as "CL-055 (lane 2A)" / "CL-055 (orchestrator)"). Only the `to` package (or WP0 for shared files) changes the status. Nobody edits any other part of DECISIONS.md, API_CONTRACT.md or ARCHITECTURE.md; genuine contradictions are logged as `CL-nnn … (→ architect)`.
- **WP0 stays on call** through Phase 1 at low load to resolve change-log requests, add `en.json` keys, adjust contract models, regenerate `openapi.json` + `schema.d.ts`, and merge.

### 1.3 Branches, commits, PR notes

- Baseline (updated 2026-09-29): `main` carries **Phase 1 at `85e1e68`** ("Phase 1: API core, Gemini provider, analysis pipeline, resources, mobile app"), after `59f4386` (scaffold + backbone docs + research) → `f4e7a4d` (complete spec set, all spec files tracked) → `cb7b05b` (WP0: contract, day-0 skeleton, English pack, mobile types and stubs — M0) → `975bcde` (WP1–WP4, WP7 checkpoint). At `85e1e68` every gate in §1.4 was green (API 1735 passed / 24 live skipped; ruff + strict mypy clean; `openapi.json`, `make_fixtures`, `sync_to_mobile.py` deterministic; mobile `tsc`, `jest`, `expo lint`, web export, `expo config --type prebuild` green). **Remaining: WP8 (§5.9) and the integration stage (§6).** Phase 2A (2026-09-29) runs WP8, WP0 follow-ups (contract), DOCS (spec reconciliation), a WP5 fix and a cross-cutting POLISH package in parallel in one working tree; git is handled by the orchestrator, not by the packages, so the per-package branches below apply to Phase 1 only.
- One branch per package: `wp0-contract`, `wp1-api-core`, `wp2-analysis`, `wp3-resources`, `wp4-mobile-foundation`, `wp5-scan-result`, `wp6-vault-help`, `wp7-fixtures-demo`, `wp8-devops`. Rebase on `main` at least daily; merge to `main` only when your verification commands (§1.4) pass on your branch **with all of `main` merged in**.
- Commit only files you own. A commit touching another package's file is reverted by the merger.
- PR/merge note template: `WP<n>: <what>. Docs: <D-nn, API_CONTRACT §x, ARCHITECTURE §y>. Change-log: <CL-nnn or none>. Verified: <commands>.` If code and docs disagree, say which one you fixed.
- Commit messages end with the attribution line required by the session (`Co-Authored-By: …`) when one is given.

### 1.4 Canonical verification commands

Run from the repo root unless noted. All must pass before a merge to `main`.

| Scope | Command |
|---|---|
| API tests (all but live) | `apps/api/.venv/bin/pytest apps/api` (pytest finds `apps/api/pyproject.toml` from the argument path, so this works from the repo root) |
| API lint | `apps/api/.venv/bin/ruff check apps/api` (ruff resolves the nearest `pyproject.toml` per file and excludes `.venv` by default) |
| API types | `apps/api/.venv/bin/mypy --config-file apps/api/pyproject.toml apps/api/proxyhealth_api apps/api/scripts apps/api/tests` — **not** `mypy apps/api` from the repo root: mypy reads config only from the current directory, so that form ran without `strict`/plugins (verified 2026-09-27). Equivalent: `(cd apps/api && .venv/bin/mypy proxyhealth_api scripts tests)`. `CLAUDE.md` was corrected (CL-008, done 2026-09-27); WP8 uses the same form in the README. |
| Mobile config sanity (after any `app.json` edit) | `export PATH="$HOME/.local/node/bin:$PATH"; cd apps/mobile && npx expo config --type prebuild > /dev/null` (evaluates every config plugin offline; a missing icon/font path fails here instead of at the first EAS build) |
| API live golden gate (optional, needs keys) | `RUN_LIVE=1 apps/api/.venv/bin/pytest apps/api/tests/live` |
| OpenAPI snapshot regen (WP0 only) | `apps/api/.venv/bin/python apps/api/scripts/export_openapi.py && (cd apps/mobile && npm run gen:types)` |
| Mobile (Node 24 at `~/.local/node/bin`) | `export PATH="$HOME/.local/node/bin:$PATH"; cd apps/mobile && npx tsc --noEmit && npx jest && npx expo lint && npx expo export --platform web` |
| Sync check | `apps/api/.venv/bin/python apps/api/scripts/sync_to_mobile.py --check` |
| Smoke (after WP8) | `make smoke` |
| Everything (after WP8) | `make test && make export-web` |

Facts already verified on this Mac (do not re-derive): `npx tsc --noEmit`, `npx jest`, `npx expo lint`, `npx expo export --platform web` pass on the scaffold; `expo-env.d.ts` exists locally (git-ignored; CI runs `npx expo customize tsconfig.json` first); TypeScript 6 does not auto-include `@types/*` (`tsconfig.json` lists `"types": ["jest"]`); `@testing-library/react-native` v14 `render()` is async and `screen` is not implemented; `expo-file-system` is the class API (`File`, `Directory`, `Paths`) with no web implementation; `npx expo run:ios` cannot work here (no Xcode).

### 1.5 Reading order

Every agent: `CLAUDE.md` → `docs/DECISIONS.md` §0, §11, §14 → `docs/ARCHITECTURE.md` §7 → this file §1, §2, §4 and its own WP row in §3 → the docs sections listed in that WP's "Reads" row. Mobile agents also read `apps/mobile/AGENTS.md` and verify every Expo API against `https://docs.expo.dev/versions/v57.0.0/sdk/<module>/` (never memory). The screen reference is `docs/PRODUCT_SPEC.md` (S0–S19, journeys, copy in Appendix A); `docs/research/specs/user-first.md` is background only. Where PRODUCT_SPEC and the backbone disagree, the backbone wins and PRODUCT_SPEC §16.2 records the difference.

---

## 2. Sequencing, phases and milestones

```
Day 0            Days 1–6 (parallel)                                   Days 7–9
┌──────────┐     ┌──────────────────────────────────────────────┐      ┌──────────────────────┐
│ Phase 0  │ M0  │ Phase 1                                      │  M3  │ Phase 2              │
│ WP0 alone│────▶│ WP1 WP2 WP3 WP7 (API)   WP4 WP5 WP6 (mobile) │─────▶│ Integration &        │
│ contract │     │ WP8 (devops, from day 1)                     │      │ verification (§6)    │
└──────────┘     └──────────────────────────────────────────────┘      └──────────────────────┘
```

| Milestone | When | Gate (all must be true) |
|---|---|---|
| **M0 — contract frozen** | end of day 0 | Baseline commit exists. `apps/api/.venv/bin/pytest apps/api` passes (`test_openapi_snapshot`, `test_schema_guard`, `test_keys_exist`, `test_m0_smoke`). `cd apps/mobile && npx tsc --noEmit && npx jest && npx expo lint && npx expo export --platform web` pass with the generated `schema.d.ts`, `tokens.ts`, `en.json`, seam stubs and the three WP4 type stubs (§5.0) in place — the template screens are still the ones rendered at M0; WP4 replaces them on day 1. `(cd apps/api && .venv/bin/uvicorn proxyhealth_api.main:app --port 8000)` boots with no `.env` (mock); `GET /health` → `provider:"mock"`, `GET /v1/config` → `data_use_tier:"demo"`, `POST /v1/analyze` with header `X-Consent-Version: 2026-09-24` and any JPEG/PNG page returns a valid `AnalysisResult` (without the header → `428`). `GET /v1/demo/fixtures` lists the one inline fixture. §14 change log exists. Hand-offs listed in §5.0 take effect; WP0 tags the commit `m0`. |
| **M1 — first light** | day 2 | Every API route returns real data in mock mode (WP1/2/3/7 at least partially). Mobile shell renders on web: language grid → consent (tier badge `demo`) → tabs. `make dev` (WP8) boots both. |
| **M2 — end to end** | day 4 | Web: sample paper → reading → result with three cards, quotes, urgency, clerk card; ≥ 8 fixtures with `out.en.json`; ≥ 40 resources; keypool/failover/tier-gate tests green. |
| **M3 — feature complete (MUST tier)** | day 6 | All WP acceptance criteria met. 17 fixtures + 1 screenshot; goldens pass every validator; `make smoke` green; `make test` green; `sync_to_mobile.py --check` green. |
| **M4 — integrated** | day 8 | §6 checklist done: demo script rehearsed on web and on an Android development build; live keyed gate run if billed keys exist (Q1); privacy-claims and readability CI green. |
| **M5 — v1 done** | day 9 | §7 definition of done fully ticked. |

Rough effort (agent-days): WP0 1 · WP1 4 · WP2 6 · WP3 4 · WP4 5 · WP5 6 · WP6 6 · WP7 5 · WP8 3 · integration 2. WP1 and WP6 may each be run as two agents in the disjoint lanes described in their sections.

Ordering inside Phase 1 that matters:
- WP7 builds fixtures + mock first (independent), then golden tests once WP2 lands `analysis.pipeline.run_analysis` (M2).
- WP2's pipeline needs WP3's `resources.matcher.match` and `rules_repo` for `resource_preview` and fixed notices; until WP3 lands, WP2 uses the `ResourceRepo`/`RulesRepo` stubs WP0 created (they return empty lists) — tests for those paths are marked `xfail(strict=False)` until M2.
- WP5 and WP6 develop against the mock API at `EXPO_PUBLIC_API_URL=http://127.0.0.1:8000` from day 1 (WP0's hour-one mock returns a valid `AnalysisResult` for any input).
- WP4 lands `_layout.tsx`, `(tabs)/_layout.tsx`, `client.ts`, `store/*`, `design/theme.tsx`, `BigButton`, `Card`, `Bidi`, `useT`, `useDirection` **first** (day 1) because WP5/WP6 import them; WP4's onboarding/settings/storage follow.
- WP8 lands `Makefile` + `scripts/dev.sh` on day 1, CI and store docs later.

State on 2026-09-29: Phase 1 (WP0–WP7) is merged on `main` at `85e1e68` and M0–M2 hold (web walk-through in Dari with zero keys: language → consent → sample → result cards → clerk card). M3's "`make smoke`/`make test` green" waited for WP8's `Makefile` (it landed in Phase 2A, with `scripts/{dev,smoke,ci,gen-types}.sh`); M4/M5 wait for WP8 and §6. Open code requests from the Phase 1 fixer rounds stay listed in DECISIONS §14 with status `[open]` and their owning package.

---

## 3. Work-package summary table

Format required by D-30: `WP | Owner scope (exclusive write) | Reads | Definition of done`. Full file lists are in §5 and Appendix A.

| WP | Title | Owner scope (exclusive write) | Reads | Definition of done |
|---|---|---|---|---|
| **WP0** | Contract, tokens, day-0 skeleton (runs first and alone) | **Permanent:** `apps/api/proxyhealth_api/contracts/**`, `apps/api/proxyhealth_api/ai/{provider,schema_guard}.py`, `apps/api/openapi.json`, `apps/api/scripts/export_openapi.py`, `apps/api/tests/conftest.py`, `apps/api/tests/{__init__,unit/__init__,contract/__init__,golden/__init__,live/__init__}.py`, `apps/api/tests/contract/{test_openapi_snapshot,test_m0_smoke}.py`, `apps/api/tests/unit/{test_schema_guard,test_keys_exist}.py`, `apps/api/data/langpacks/en.json`, `apps/api/data/langpacks/_contexts.json`, `apps/api/data/languages.yaml`, `apps/mobile/src/api/schema.d.ts`, `apps/mobile/src/api/types.ts`, `apps/mobile/src/design/tokens.ts`, `apps/mobile/package.json` (scripts only), `apps/mobile/tsconfig.json`, `apps/mobile/eslint.config.js`, `docs/API_CONTRACT.md`. **Creates on day 0, hands off at M0** (full table in §5.0): the API skeleton (`pyproject.toml`, `.env.example`, `main/settings/errors/middleware/deps/logging_/ratelimit/__init__.py`, `routers/**` with final route signatures, `ai/{failover,routing,keypool}.py` stubs, `ai/mock.py` hour-one, repo/store stubs, `analysis/{pipeline,troubleshoot_pipeline,chat_pipeline}.py` mapping stubs, a minimal `scripts/sync_to_mobile.py`), the `.gitignore` line `apps/api/var/`, the mobile seam stubs (§4.2 table), the three WP4 type stubs (`src/store/session.ts`, `src/api/errors.ts`, `src/storage/index.ts`) and the first sync outputs | DECISIONS (all), API_CONTRACT (all), ARCHITECTURE §2, §3, §4, §5.1, §6; gemini.md §2.2, §2.4, warnings on schema subset; expo.md §6; compliance.md §5; PRODUCT_SPEC Appendix A; RESOURCE_DB §3.3, §4 | §5.1 "Verify" block green: `export_openapi.py` is idempotent and the snapshot test passes; `npm run gen:types` regenerates an identical `schema.d.ts`; `schema_guard` passes for every `model_out` class; `test_keys_exist` finds every server-emitted key in `en.json`; `MockProvider` returns a valid `AnalysisModelOut` for any input; the M0 gate (§2) is green and the commit is tagged `m0` |
| **WP1** | API core + AI providers + key pool + language packs + status endpoints | `main.py settings.py errors.py middleware.py ratelimit.py logging_.py deps.py __init__.py`, `ai/**` except `provider.py`, `schema_guard.py` (WP0), `mock.py`, `recording.py` (WP7), `prompts/**`, `prompt_loader.py` (WP2); `packs/**`; `routers/{__init__,health,config,langpacks,admin}.py`; `Dockerfile`, `requirements.txt`, `.env.example`, `pyproject.toml`; `scripts/{gen_packs,spike_schema}.py`; `data/langpacks/<tag>.json` for tags ≠ `en`; tests listed in Appendix B. Two lanes if run as two agents (§5.2): **1A** app core + routers + packs; **1B** `ai/{gemini,keypool,failover,routing}.py` + their tests | D-01, D-03, D-04, D-05, D-07, D-08, D-25; API_CONTRACT §0, §3.1–3.4, §3.14, §4; ARCHITECTURE §2.1, §5.3, §6.1; gemini.md §1–§4 + warnings | §5.2 "Verify" block green: keypool tests (429 rotation, Retry-After, RPD detection, Pacific reset, persistence, distinct projects, 401/403 disable, 400 abort, 503 same-slot retry, degraded path, all-exhausted 429); tier gate 403 + consent 428 + 413/415 + error envelope tests; `/health` and `/v1/config` correct per tier (mock → `demo`); langpack resolve/generate/QA/cache/ETag/304/409 tests; logging allow-list test; bundled packs for at least `es`, `prs`, `ar`, `ps` pass `packs/qa.py`; ruff + mypy clean |
| **WP2** | Analysis, troubleshoot and chat pipelines + safety validators + prompts | `analysis/**`, `routers/{analyze,troubleshoot,chat}.py`, `data/rules/**` **except `prepare.yaml`** (WP3), `data/safety/**`, `ai/prompts/**`, `ai/prompt_loader.py`, `scripts/eval_golden.py`, `tests/live/**`, `docs/AI_PROMPTS.md`, `docs/DOCUMENT_TAXONOMY.md`; tests per ARCHITECTURE §4 "Test ownership" | D-06, D-09…D-21; API_CONTRACT §3.5–3.7, §4; ARCHITECTURE §2 (analysis/, prompts); compliance.md §3, §7 + warnings; resources.md §3, §4 + warnings; user-first §5.4–5.5; risk-first §5.4–5.5; builder-first §5.5–5.6 | unit tests for every validator (verify, contacts, deadlines, urgency, scam, emergency, phrasing, injection, redaction, uploads, clerk, fixed notices); contract tests for the three routers against the mock; every `Demand` in a result carries `source_quote/span_ids/page/confidence/verified`; zero invented contacts on the golden set |
| **WP3** | Resource DB + matcher + deadline rules repo + quick-sheet PDF | `resources/**`, `quicksheet/**`, `routers/{resources,rules,quicksheet}.py`, `data/resources/**`, `data/rules/prepare.yaml` (keys must exist in `data/resources/_meta.yaml.checklist`; seed in RESOURCE_DB §4.8), `data/fonts/**` (already on disk), `scripts/check_links.py`, `docs/RESOURCE_DB.md`; tests per ARCHITECTURE §4 "Test ownership" | D-10, D-11, D-13, D-18, D-24; API_CONTRACT §1 (ResourceTag…LinkHealth), §3.8–3.11; ARCHITECTURE §2 (resources/, quicksheet/, data/resources, data/rules); resources.md §1, §2, warnings, key facts; user-first §7; builder-first §7.3–7.4 | YAML validates at boot (bad file → boot refused with path/line); ≥ 70 entries with `verified_on`; matcher tests (institution match, geo tiers, language, LSC penalty shown-not-hidden, ≤ 2 per org_type, crisis/scam forcing, national fallbacks); `/v1/rules` serves the 12 seeded rules; PDF renders LTR and RTL fixtures ≤ 200 KB with embedded Noto fonts |
| **WP4** | Mobile foundation: shell, design system, i18n/RTL/TTS, storage, API client, onboarding, settings route, app/eas config | `src/app/{_layout,index,+not-found,+html}.tsx`, `src/app/onboarding/**`, `src/app/(tabs)/_layout.tsx`, `src/app/(tabs)/settings.tsx`, `src/design/theme.tsx`, `src/design/components/**`, `src/i18n/**` except generated files (`packs/*.json`, `packs/index.ts`, `languages.ts`), `src/storage/**`, `src/api/{client,errors,config,offline}.ts`, `src/lib/{network,ids,platform,tts}.ts`, `src/store/**`, `src/features/onboarding/**`, `src/hooks/**`, `src/global.css`, `app.json`, `eas.json`; **deletes** the template files listed in §5.5 (`src/app/explore.tsx`, `src/components/**`, `src/constants/theme.ts`, `src/hooks/use-theme.ts`, `scripts/reset-project.js`) and moves `external-link.tsx` / `ui/collapsible.tsx` into `src/design/components/`; tests in Appendix B | D-02, D-22, D-23, D-25, D-26, D-27, D-28; API_CONTRACT §0, §3.2–3.4; ARCHITECTURE §3, §3.1, §5.3, §6.2; expo.md §2–§6 + warnings; compliance.md §5; user-first §4 (S0–S3, S17, S18), §9 | §5.5 "Verify" block green: tsc + jest + lint + web export + `expo config --type prebuild`; RTL flips on web and native (row-reverse) with restart prompt on native; consent screen shows the right badge and copy per tier incl. `unknown`; `Not now` path; storage adapters tested (web in-memory; native via mocked `expo-sqlite`); API client maps 428/403/429/422 to `user_message_key`s; every template file in §5.5 is deleted and `grep -rn "@/components/\|@/constants/theme\|unstable-native-tabs" apps/mobile/src` returns nothing |
| **WP5** | Scan → Reading → Result → Source → Chat → Clerk → Emergency | `src/app/scan/**`, `src/app/result/**`, `src/app/emergency.tsx`, `src/features/{scan,analysis,chat,clerk,speech,feedback,emergency}/**`, `src/lib/{image,pdf,dates}.ts`; tests in Appendix B | D-09, D-12…D-14, D-17…D-19, D-21, D-26, D-28; API_CONTRACT §3.5, §3.7, §3.12; ARCHITECTURE §3.1; expo.md camera/picker/manipulator/document-picker/speech/clipboard; user-first §4 S4–S10; compliance.md §5, §7 | full flow works on web and on the Android dev build against the mock API; masks: canvas burn on web, `masks[]` on native; cards render from the RFE and Medicaid goldens in LTR and RTL at 200 % font; every fact shows quote + crop + confidence; unverified section; emergency card first when `safety.emergency`; clerk mode LTR with 1.5 s long-press exit; read-aloud with honest fallback |
| **WP6** | Home, family vault, Action Hub, reminders, quick sheet, troubleshoot, demo, settings features | `src/app/(tabs)/{index,papers,help}.tsx`, `src/app/papers/**`, `src/app/reminders.tsx`, `src/app/troubleshoot.tsx`, `src/features/{vault,help,reminders,quicksheet,troubleshoot,demo,settings}/**`, `src/lib/{notifications.native,notifications.web,ics}.ts`; tests in Appendix B | D-12, D-13, D-22…D-24, D-29, D-31; API_CONTRACT §3.6, §3.8, §3.9, §3.11, §3.13; ARCHITECTURE §3.1 (storage, PDF/share, reminders, offline); expo.md print/sharing/notifications/sqlite/file-system/secure-store; user-first §4 S11–S16 | opt-in save with "Whose paper is this?", members, move, per-member wipe, one-tap "Delete everything"; reminders 7/3/1 days at 9:00 native with generic body, `.ics` on web and via share on native; quick sheet share (native) / server PDF download (web) / copy / read aloud; troubleshoot with mode chips and credential guard; Action Hub with prep checklist, LSC note, national fallbacks, "Verified on"; sample picker + sample banner; offline behaviours |
| **WP7** | Fixtures, mock provider, demo endpoints, feedback counters, goldens, sync | `data/fixtures/**`, `scripts/{make_fixtures,sync_to_mobile}.py` (after M0), `ai/mock.py` (after M0), `ai/recording.py`, `demo/**`, `routers/demo.py`, `feedback/**`, `routers/feedback.py`, `tests/golden/**`, `tests/unit/test_feedback_store.py`, `tests/contract/{test_demo,test_feedback}.py`; **generated mobile copies written only by `sync_to_mobile.py`:** `apps/mobile/assets/fixtures/**` (incl. `index.ts`), `apps/mobile/assets/resources/**`, `apps/mobile/assets/fonts/**`, `apps/mobile/locales/**`, `apps/mobile/src/i18n/packs/*.json`, `apps/mobile/src/i18n/packs/index.ts`, `apps/mobile/src/i18n/languages.ts`; `docs/DEMO_SCRIPT.md` | D-16, D-29, D-31; API_CONTRACT §3.12, §3.13, §4; ARCHITECTURE §2 (mock, recording, demo/, feedback/, fixtures, scripts); resources.md §3, §4; user-first §11; builder-first §11; risk-first §11; §5.8 mock-parity table | §5.8 "Verify" block green: 17 document fixtures + 1 screenshot, watermarked SAMPLE, with manifest, transcript, `out.en.json` for all and `out.{es,prs,ar}.json` for the eight demo fixtures; goldens pass every validator with the urgency/date kinds of Appendix D; dHash match recognises a re-encoded/scaled copy of every fixture page (hamming ≤ 10) and rejects the other fixtures; every mock behaviour in the §5.8 table has a test; `/v1/demo/*` serves list and PNGs; feedback counters store enums only; `sync_to_mobile.py --check` green; demo runs offline |
| **WP8** | DevOps, CI, store, compliance docs, artwork, README | `Makefile`, `scripts/{dev,smoke,gen-types,ci}.sh`, `apps/api/scripts/smoke.py`, `.github/workflows/ci.yml`, `.gitignore` (after M0), `README.md`, `apps/mobile/README.md`, `apps/mobile/assets/images/**` (incl. the new `notification-icon.png`), `apps/mobile/assets/expo.icon/**`, `apps/mobile/public/**`, `docs/{DEPLOYMENT,RUNBOOK,STORE_LISTING,COMPLIANCE_PRIVACY}.md`, `tests/unit/{test_privacy_claims,test_readability}.py` | D-01…D-03, D-08, D-22, D-30, §12, §13; ARCHITECTURE §5, §6, §7; compliance.md §1, §2, warnings, key facts; expo.md §3 hosting, §4 EAS; gemini.md §3 | §5.9 "Verify" block green: `make dev` boots API (mock) + Expo web; `make smoke` passes; `scripts/ci.sh` runs pytest, ruff, mypy (correct form, §1.4), tsc, jest, lint, contract diff, YAML validation, pack sync check, privacy claims, readability, `expo config --type prebuild`, web export and is green locally; template artwork deleted only after WP4's shell merged (§5.9 rule); store docs complete per compliance.md §1 checklist; `dist/privacy/index.html` exists after `make export-web` |

Phase 2A packages (2026-09-29; §1.3) are temporary and have no rows here: each runs with a write scope the orchestrator sets per task, which may cross the Phase 1 scopes above. **WP0FU** — WP0's permanent scope (`contracts/**`, `openapi.json`, `src/api/schema.d.ts`) plus API_CONTRACT §1 `FeedbackSurface` and §3.12. **DOCS** — `docs/{DECISIONS,ARCHITECTURE,API_CONTRACT,AI_PROMPTS,PRODUCT_SPEC,BUILD_PLAN,DOCUMENT_TAXONOMY,RESOURCE_DB}.md` (not the §5 prompt blocks of AI_PROMPTS, not the WP0FU parts of API_CONTRACT); the only package that edits existing DECISIONS §14 lines. **POLISH** — the only package that edits `data/langpacks/*.json` and runs `sync_to_mobile.py`, plus the files its items touch (CL-066, CL-067). **WP5FIX** — the source view's initial scroll, in WP5's files. Everyone else only appends CL lines.

---

## 4. Cross-package interfaces fixed on day 0

The Pydantic models (API_CONTRACT) are the external contract. The following *internal* seams are fixed here so packages can code in parallel from hour one. WP0 creates each as a stub with exactly these names and signatures; later owners fill bodies without renaming. Renames require a change-log line.

### 4.1 API internal interfaces (Python)

**Package layout facts.** Package `proxyhealth_api` lives at `apps/api/proxyhealth_api/`. It is **not pip-installed**; `apps/api/pyproject.toml` sets `[tool.pytest.ini_options] pythonpath = ["."]`, `testpaths = ["tests"]`, `asyncio_mode = "auto"`, `markers = ["live: needs RUN_LIVE=1 and keys"]`; scripts do `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`; uvicorn is run from `apps/api` (`--app-dir` defaults to `.`), or from the root with `--app-dir apps/api`. Ruff: `line-length = 100`, `select = ["E","F","I","B","UP","ASYNC"]`, `extend-exclude = ["var", ".venv"]`. Mypy: `python_version = "3.13"`, `strict = true`, `plugins = ["pydantic.mypy"]`, `exclude = ["^var/", "^\\.venv/"]`, `[[tool.mypy.overrides]] module = ["pypdfium2.*","reportlab.*","slowapi.*","arabic_reshaper.*","bidi.*"] ignore_missing_imports = true` (`google.genai` ships `py.typed`, so it is type-checked; `arabic_reshaper` and `bidi` do not). Mypy must be invoked with `--config-file apps/api/pyproject.toml` or from inside `apps/api` (§1.4). `tests/` and each `tests/<dir>/` carry an `__init__.py` (WP0) so pytest and mypy see unique module names and `tests/<dir>/_fixtures_<wp>.py` helpers import as `tests.<dir>._fixtures_<wp>`.

**`ai/provider.py` (WP0, permanent).**
```python
class Task(StrEnum):
    analyze_single = "analyze_single"; transcribe = "transcribe"; explain = "explain"
    troubleshoot = "troubleshoot"; chat = "chat"; langpack_chunk = "langpack_chunk"
    resolve_language = "resolve_language"; tag = "tag"; phrasing_rewrite = "phrasing_rewrite"
    clerk_translate = "clerk_translate"

@dataclass(frozen=True)
class Part:                       # text before media (D-04)
    kind: Literal["text", "bytes"]; text: str | None = None
    data: bytes | None = None; mime_type: str | None = None
    @staticmethod
    def of_text(s: str) -> "Part": ...
    @staticmethod
    def of_bytes(data: bytes, mime_type: str) -> "Part": ...

@dataclass
class Usage: input_tokens: int = 0; output_tokens: int = 0; thought_tokens: int = 0

@dataclass
class StructuredResult:
    parsed: BaseModel | None; raw_text: str | None; model_id: str; usage: Usage
    blocked_reason: str | None = None; finish_reason: str | None = None; incomplete: bool = False

class AIProvider(Protocol):
    name: Provider                # contracts.enums.Provider
    async def generate_structured(
        self, *, task: Task, tier: ModelTier, parts: Sequence[Part], system: str,
        schema: type[BaseModel], thinking: ThinkingLevel | None, media_resolution: Literal["high","medium"] | None,
        max_output_tokens: int, request_id: str, slot_index: int | None = None,
        hints: Mapping[str, str] | None = None,     # mock reads demo_sample_id / target_language / language_tag / question; gemini ignores
    ) -> StructuredResult: ...
```
Upstream errors propagate as exceptions; the failover engine reads `getattr(exc, "status_code", None) or getattr(exc, "code", None)` (D-05).

**`ai/routing.py` (WP1).** `route(task: Task, *, pages: int = 1, is_pdf: bool = False, degraded: bool = False, settings: Settings) -> RouteConfig` with `RouteConfig{tier: ModelTier, model_id: str, thinking: ThinkingLevel | None, media_resolution: Literal["high","medium"] | None, max_output_tokens: int}` (the response schema and prompt name are looked up by the pipeline from the `Task`, not returned by `route()`). Table (D-04 + AI_PROMPTS §3, which is the single source for these numbers): `analyze_single`/`explain` → pro, `high` (≤ 8 pages) / `medium` (9–12), 16384; `transcribe` → pro, `medium`, 8192; `troubleshoot` → pro, `medium`, 4096; `chat` → fast, `low`, 2048; `langpack_chunk` → fast, `minimal`, 4096; `tag` → fast, `minimal`, 1024; `clerk_translate` → fast, `minimal`, 512; `phrasing_rewrite` → fast, `minimal`, 256; `resolve_language` → fast, `minimal`, 256. `degraded=True` swaps `model_id` to `MODEL_FAST` and `thinking` to `MODEL_PRO_DEGRADED_THINKING`. Media resolution `high` for images/screenshots, `medium` for PDFs, `None` for text-only tasks. `minimal` on a `gemini-3.8*` model is downgraded to `low` with a log line.

**`ai/failover.py` (WP0 pass-through stub → WP1).** The only path from pipelines to providers:
```python
@dataclass
class GenerateOutcome:
    result: StructuredResult; route: RouteConfig; quality: ModelQuality
    slot_index: int | None; attempts: int; warnings: list[WarningCode]

class SchemaFallbackNeeded(Exception): ...   # single-call rejected/incomplete → pipeline switches to two_call

class AIService:
    def __init__(self, provider: AIProvider, keypool: KeyPool | None, settings: Settings): ...
    async def generate(self, *, task: Task, parts: Sequence[Part], system: str, schema: type[BaseModel],
                       pages: int = 1, is_pdf: bool = False, request_id: str,
                       hints: Mapping[str, str] | None = None) -> GenerateOutcome: ...
```
Raises `ApiError(422 content_blocked)` on a blocked result (never retried), `ApiError(429 quota_exhausted, key_exhausted=True, retry_after=…)` when all slots are unavailable, `ApiError(503 upstream_unavailable)` after bounded 5xx retries, `ApiError(400 invalid_request)` on upstream 400 (no rotation). Applies D-07 budgets (≤ 3 slots, `FAILOVER_DEADLINE_S`) and the degraded path (`quality="degraded"`, `warnings=[degraded_model]`). WP0's stub calls `provider.generate_structured` once with slot 0 and no retries.

**`ai/keypool.py` (WP1).** `KeyPool(slots: list[KeySlotConfig], var_dir: Path, clock: Callable[[], datetime])` with `acquire(tier) -> Slot | None`, `report(slot, tier, *, outcome: Literal["ok","429","5xx","4xx_fatal","400"], retry_after: int | None, error_text: str | None)`, `snapshot() -> AdminKeysResponse`, `summary() -> KeySlotSummary`, `persist()`, `restore()`. State per slot per tier exactly as D-07.

**`errors.py` (WP0 skeleton → WP1).**
```python
class ApiError(Exception):
    def __init__(self, code: ErrorCode, status: int, message: str, *, user_message_key: str | None = None,
                 retry_after: int | None = None, key_exhausted: bool = False,
                 details: dict[str, str | int | bool] | None = None): ...
```
`user_message_key` defaults to `f"err.{code.value}"`. `install_handlers(app)` converts `ApiError`, `RequestValidationError` (→ 400 `invalid_request`), Starlette HTTP errors and unexpected exceptions into `ErrorResponse` and sets `Retry-After` on 429/503.

**`middleware.py` (WP0 skeleton → WP1).** Pure ASGI/Starlette middlewares: request id, `X-Contract-Version`/`X-Data-Use-Tier` headers, body-size limit (413), CORS, content-free access log, rate limit. The **consent + tier gate is a FastAPI dependency** `consent_and_tier_gate(request: Request, settings=Depends(get_settings))` exported from `middleware.py` and attached to the three gated routers with `dependencies=[Depends(consent_and_tier_gate)]`; it reads the cached JSON body (`await request.json()`) to see `demo_sample_id`, then: 428 `consent_required` when `X-Consent-Version` is missing/older than `CONSENT_VERSION` and no `demo_sample_id`; 403 `unpaid_tier_real_documents_disabled` when tier ∈ {unpaid, mixed} and no `demo_sample_id` and not `ALLOW_UNPAID_REAL_DOCUMENTS`. (ARCHITECTURE calls this "middleware"; a dependency is the implementation because the gate needs the body.)

**`deps.py` (WP0 skeleton → WP1).** `app.state` attributes set in the lifespan, and accessors: `get_settings`, `get_provider`, `get_keypool`, `get_ai` (→ `AIService`), `get_resources` (→ `ResourceRepo`), `get_rules` (→ `RulesRepo`), `get_packs` (→ `BasePack`), `get_pack_cache` (→ `PackCache`), `get_fixtures` (→ `FixtureStore`), `get_feedback_store` (→ `FeedbackStore`). Routers take these via `Depends`. Tests build the app with `create_app(Settings(...))` and never touch globals.

**`main.py` (WP0 skeleton → WP1).** `create_app(settings: Settings | None = None) -> FastAPI` with `title="ProxyHealth AI API"`, `version=__version__`, `openapi_url="/openapi.json"`, a `lifespan` that builds providers/repos in the order ARCHITECTURE §2.1 gives, `install_handlers`, middlewares, and `include_router` for every module in `routers/`. `app = create_app()` at module bottom. Every route declares `response_model` and `responses={<status>: {"model": ErrorResponse}}` for each error it can return (API_CONTRACT §5).

**`analysis/pipeline.py` (WP2).**
```python
@dataclass
class PipelineDeps:
    settings: Settings; ai: AIService; resources: ResourceRepo; rules: RulesRepo; fixtures: FixtureStore
    request_id: str; data_use_tier: DataUseTier; clock: Callable[[], datetime]
    packs: PackCache | None = None; languages: LanguageTable | None = None   # optional (CL-046(a)); None → process-wide copies of the same files

async def run_analysis(req: AnalyzeRequest, deps: PipelineDeps) -> AnalysisResult: ...
async def run_troubleshoot(req: TroubleshootRequest, deps: PipelineDeps) -> TroubleshootResult: ...   # analysis/troubleshoot_pipeline.py
async def run_chat(req: ChatRequest, deps: PipelineDeps) -> ChatAnswer: ...                           # analysis/chat_pipeline.py
```
Golden tests (WP7) and smoke (WP8) call these directly. `routers/analyze.build_deps` passes the app's `PackCache`/`LanguageTable`. `analysis/pipeline.py` also exports the helpers the troubleshoot and chat pipelines share (`generate`, `prompt_base_vars`, `translator`, `make_rewriter`, `RewriteBudget`, `phrase`, `PhrasingStats`, `fixture_for`, `demo_of`, `model_meta`, `parsed_as`, `resource_tags`, `resource_hosts`, `render_paper_text`, `merge_two_call`); WP0's stub helpers `decode_pages`, `red_flag`, `disclaimer_for` are gone (use `uploads.decode_pages`, `disclaimers.disclaimer_kind`) — CL-046(a).

**`resources/` (WP3).** `ResourceRepo.load(dir: Path, *, today: date | None = None, prepare_path: Path | None = None) -> ResourceRepo` (keyword-only additions, CL-025(d)); `.all() -> list[Resource]`; `.get(id) -> Resource | None`; `.names() -> set[str]` (for the contacts filter's organization allow-list); `.version -> str`. `matcher.match(req: ResourceMatchRequest, repo: ResourceRepo, *, en_strings: Mapping[str, str] | None = None, today: date | None = None) -> ResourceMatchResponse`. `RulesRepo.load(dir: Path)` with `.deadline_rules() -> list[DeadlineRule]`, `.fixed_notices(doc_type) -> list[FixedNotice{kind: RedFlagKind, severity: Severity, fixed_copy_key: str, id: str, document_types: tuple[str, ...], when}]` (`id`/`document_types`/`when` carry the rest of the YAML row so `analysis/fixed_notices.py` can evaluate the DOCUMENT_TAXONOMY §7.3 condition grammar — CL-055(f)), `.all_fixed_notices()`, `.clerk_need(doc_type) -> str`, `.clerk_need_key(doc_type) -> str | None`, `.prepare_items(doc_type) -> list[str]`, `.version -> str`. WP0's stubs return empty collections and `"0"` versions.

**`demo/fixtures.py` (WP7).** `FixtureStore.load(dir: Path)`; `.list() -> list[DemoFixture]`; `.get(id) -> Fixture | None` with `Fixture{manifest: DemoFixture (contracts.demo — there is no separate FixtureManifest), dhash: int, page_dhashes: list[int], today: date, expected: dict, recorded_on: str | None, page_png(n: int) -> bytes, transcript: str, out(lang: str) -> AnalysisModelOut | TroubleshootModelOut | None}` (`out` is `None` for a tag not in `available_target_languages`); `.match_dhash(png_or_jpeg: bytes, max_hamming: int, *, kind=None) -> Fixture | None` searches every fixture (`kind` is an additive filter `MockProvider` passes per task) — CL-052(b)(d). WP0's hour-one mock ships one inline fixture (`medicaid_address_confirmation`, English) without needing `data/fixtures/` on disk.

**`packs/` (WP1).** `BasePack.load(path) -> BasePack` with `.strings: dict[str,str]`, `.version: str` (sha256 hex of the file bytes), `.contexts: dict[str,str]`, `.chunks(size=60) -> list[list[str]]`; `PackCache(var_dir, *, langpacks_dir=None, base=None, languages=None, …)` (keyword-only additions, CL-029(c)) with `get(tag, pack_version) -> LanguagePack | None`, `put(pack)`, `single_flight(tag) -> asyncio.Lock`, `bundled(tag) -> LanguagePack | None` (reads `data/langpacks/<tag>.json`). `t_server(tag: LanguageTag, key: str, packs: PackCache, base: BasePack, **vars) -> str` returns the target-language string with English fallback — used by WP2 for the `[contact removed — see Get help nearby]` marker, the clerk template and fixed notices in `target_language`.

**`feedback/store.py` (WP7).** `FeedbackStore(path)` with `record(req: FeedbackRequest) -> str` (ULID id) and `counts() -> list[tuple[…]]` for tests.

**`tests/conftest.py` (WP0, permanent).** Fixtures: `settings(tmp_path)` (`AI_PROVIDER=mock`, `VAR_DIR=tmp`, `MOCK_LATENCY_MIN_MS=0`, `MOCK_LATENCY_MAX_MS=0`, `INSTALL_HASH_SECRET="test"`, `CONSENT_VERSION="2026-09-24"`), `app(settings)`, `client(app)` (`httpx.AsyncClient` with `ASGITransport`), `frozen_now` (a `Callable[[], datetime]` returning `2026-09-24T14:00:00Z`; modules accept a clock parameter — no monkey-patching `datetime`), `fixture_png(id)` (reads `data/fixtures/<id>/page-1.png`, skips if absent), `consent_headers` (`{"X-Consent-Version": "2026-09-24"}`), `gemini_settings(tmp_path, slots)` for keypool tests with a fake provider. WP-specific fixtures go in that WP's own test modules or `tests/<dir>/_fixtures_<wp>.py` (imported explicitly), never in a new `conftest.py`.

### 4.2 Mobile seams (TypeScript)

**Installed and usable (from `apps/mobile/package.json`):** expo 57, expo-router, expo-camera, expo-image-picker, expo-image-manipulator, expo-image, expo-document-picker, expo-file-system, expo-font, expo-haptics, expo-localization, expo-network, expo-notifications, expo-print, expo-sharing, expo-secure-store, expo-speech, expo-sqlite, expo-clipboard, expo-crypto, expo-device, expo-constants, expo-linking, expo-splash-screen, expo-status-bar, expo-system-ui, expo-web-browser, expo-dev-client, `@react-native-async-storage/async-storage` 2.2.0, react-native-gesture-handler, react-native-reanimated, react-native-svg, react-native-safe-area-context, react-native-screens, react-native-web, zustand 5. Installed but **unused by design**: `@expo/ui`, `expo-glass-effect`, `expo-symbols` (D-27; no uninstalls).

**`src/api/types.ts` (WP0).** `export type AnalysisResult = components["schemas"]["AnalysisResult"]` and likewise for every schema in API_CONTRACT, plus `export type ErrorCode = components["schemas"]["ErrorCode"]`. No hand-written duplicates anywhere else.

**`src/api/client.ts` (WP4).** `createClient(opts: { baseUrl: string; getConsentVersion(): string | null; getInstallId(): Promise<string | null>; appToken?: string })` (the `X-Install-Id` header is omitted until consent is **accepted** — `api/config.ts` `installIdForRequests()`; CL-028(c), CL-038(b)) returning typed functions: `health()`, `getConfig()`, `getPack(tag, { packVersion?, etag? }) → { pack: LanguagePack | null (null on 304), status: 200 | 304, etag: string | null }`, `postPack(req)`, `analyze(req, { signal? })`, `troubleshoot(req)`, `chat(req)`, `matchResources(req)`, `listResources(q)`, `getResource(id)`, `getRules()`, `quicksheetPdf(req) → Blob | Uint8Array`, `feedback(req)`, `listFixtures()`, `fixturePageUrl(id, n) → string`. Timeouts 120/60/30 s per API_CONTRACT §0 via `AbortController`. Non-2xx → `throw new ApiError(...)`. The exported `noteQuotaCooling(err)` sets `session.quotaCoolingUntil` only when `retry_after_seconds > 0` (CL-039, CL-044(c)). `api/config.ts`: when `GET /v1/config` fails the tier is `unknown` even if `kv` holds a cached `ServerConfig`; the cached config stays in `session.serverConfig` for display-only rows (`useServerConfig().cached === true`), and `ensureServerConfig()`/`refreshServerConfig()` resolve to the fresh config or `null` (CL-044(a)).

**`src/api/errors.ts` (WP4).** `class ApiError extends Error { code: ErrorCode | 'network' | 'timeout'; status: number; userMessageKey: string; retryAfterSeconds: number | null; keyExhausted: boolean; requestId: string | null; details: Record<string, string | number | boolean> | null }` with `isQuotaExhausted()`, `isConsentRequired()`, `isUnpaidBlocked()`, `isBlocked()`.

**`src/store/settings.ts` (WP4, zustand, persisted via `kv`).** `languageTag: string; textSize: 'normal' | 'large' | 'xl'; highContrast: boolean; voiceId: string | null; lockScreenDetail: boolean; sampleMode: boolean; region: { state: string | null; zip3: string | null }; preferences: { tone: 'plain' | 'formal'; calendarNotes: string[]; dateFormat: 'auto' | 'mdy' | 'dmy' }; keepPageImages: boolean; hideIdNumbers: boolean; webPersist: 'session' | 'indexeddb'; clearOnClose: boolean; pinEnabled: boolean; hearItMode: boolean`.

**`src/store/session.ts` (WP4, memory only).** `pages: CapturedPage[]; demoSampleId: string | null; currentAnalysis: AnalysisResult | null; consent: ConsentRecord | null; serverConfig: ServerConfig | null; tier: DataUseTier | 'unknown'; clerkMode: boolean; offlineQueue: QueuedScan[]; quotaCoolingUntil: string | null` (+ `setQuotaCoolingUntil`, CL-039). `QueuedScan = { id: string; pages: CapturedPage[]; targetLanguage: string; memberId: string | null; queuedAt: string }` (defined by WP0 in `store/session.ts`; WP4 may extend, never rename — CL-014). `CapturedPage = { id: string; uri: string; base64?: string; mimeType: 'image/jpeg' | 'image/png' | 'image/webp' | 'image/heic' | 'image/heif' | 'application/pdf'; width?: number; height?: number; rotation: 0 | 90 | 180 | 270; masks: MaskRect[]; source: 'camera' | 'library' | 'pdf' | 'sample'; fileName?: string; byteLength?: number }`.

**`src/storage/index.ts` (WP4).**
```ts
export interface Vault {
  init(): Promise<void>;
  members: { list(): Promise<Member[]>; add(input: { name: string; color: string }): Promise<Member>; rename(id: string, name: string): Promise<void>; recolor(id: string, color: string): Promise<void>; remove(id: string, wipeDocuments: boolean): Promise<void> };   // recolor: CL-036
  documents: { list(memberId?: string): Promise<DocumentRow[]>; get(id: string): Promise<StoredDocument | null>; save(doc: StoredDocument, pages: StoredPageInput[]): Promise<void>; move(id: string, memberId: string): Promise<void>; remove(id: string): Promise<void>; search(q: string): Promise<DocumentRow[]> };
  pages: { list(documentId: string): Promise<StoredPage[]>; uri(page: StoredPage): Promise<string | null> };
  checklist: { get(documentId: string): Promise<Record<string, boolean>>; set(documentId: string, stepId: string, checked: boolean): Promise<void> };
  reminders: { list(): Promise<Reminder[]>; add(r: Omit<Reminder, 'id'>): Promise<Reminder>; remove(id: string): Promise<void>; setEnabled(id: string, on: boolean): Promise<void> };
  consent: { get(): Promise<ConsentRecord | null>; set(r: ConsentRecord): Promise<void>; clear(): Promise<void> };   // thin wrapper over storage/kv.ts (AsyncStorage) — there is no sqlite consent table (D-22)
  wipeAll(): Promise<void>;
}
export type Member = { id: string; name: string; color: string; createdAt: string };
export type DocumentRow = { id: string; memberId: string; title: string; category: DocumentCategory; documentType: DocumentType; createdAt: string; nextDateIso: string | null; pageCount: number };
export type StoredDocument = DocumentRow & { analysis: AnalysisResult; keepPages: boolean };   // "Save to read later" / "Save as proof" rows hold analysis: null despite the type (CL-024(c)) — readers must null-check
export type StoredPageInput = { page: number; base64Jpeg: string; thumbBase64?: string };
export type StoredPage = { documentId: string; page: number; filePath: string; thumbPath: string | null };
export type Reminder = { id: string; documentId: string; demandId: string; fireAt: string; notificationId: string | null; detailOptIn: boolean; enabled: boolean; label: string };   // S14 "Add my own date": documentId '' and demandId `own:<YYYY-MM-DD>:<token>` (CL-037)
export type ConsentRecord = { consent_version: string; accepted_at: string; tier_seen: 'paid' | 'unpaid' | 'mixed' | 'demo' | 'none' | 'unknown'; platform: 'ios' | 'android' | 'web' };
export const vault: Vault;   // platform re-export (vault.native.ts / vault.web.ts)
```

**`src/storage/wipe.ts` (WP4).** `wipeEverything(): Promise<WipeStep[]>` runs "Delete everything" (PRODUCT_SPEC S17 item 8, COMPLIANCE_PRIVACY §9.5) in a fixed order and keeps going when a step fails: 1 `notifications` (cancel all), then the `hooks` phase, 2–3 `vault` (files + database; web: memory + IndexedDB), 4 `secure`, `settings` reset, 5 `kv` (every key), 6 `install_id` (forgotten; a new one is created only at the next accepted consent, CL-010/CL-038(b)), 7 `memory` (session, pack and config-session reset, then the `memory` hooks); it resolves with the order that ran (the wipe order test asserts it). `registerWipeHook(hook: () => Promise<void> | void, phase: 'hooks' | 'memory' = 'hooks'): () => void` (returns an unregister function; one failing hook never stops the others) lets feature packages add cleanup: the default `'hooks'` phase runs right after notifications are cancelled (e.g. the WP6 vault-list refresh in `features/vault/store.ts` and the shared `.ics` cleanup in `lib/notifications.native.ts`); `'memory'` hooks run in step 7, after `kv` is empty, so nothing can re-read old values — `features/onboarding/consentState.ts` registers `resetConsentState` there, so a wiped "Not now"/withdrawn user lands on S2 again after S1 (CL-038(a)).

**Seam modules — created by WP0 as stubs, owned afterwards by the named package.** Each `index.ts` must keep these exports; stubs render `null` / resolve to empty values so `tsc` and `expo export` pass from M0.

| Module | Owner | Required exports |
|---|---|---|
| `src/features/vault/index.ts` | WP6 | `SaveToVaultSheet(props: { analysis: AnalysisResult; pages: CapturedPage[]; onSaved(documentId: string): void; onCancel(): void })`; `useDocument(id: string): { doc: StoredDocument \| null; loading: boolean }`; `useNextDate(): { documentId: string; title: string; dateIso: string } \| null` (`documentId` is `''` for the user's own-date reminders — read it as "no paper"; CL-049) |
| `src/features/quicksheet/index.ts` | WP6 | `QuickSheetScreen(props: { analysis: AnalysisResult; documentId?: string })`; `buildQuickSheetText(analysis, resources, t): { title: string; sections: QuickSheetSection[]; footer: string }` |
| `src/features/help/index.ts` | WP6 | `HelpForDocument(props: { analysis: AnalysisResult })`; `useResourceMatch(req: ResourceMatchRequest \| null): { data: ResourceMatchResponse \| null; loading: boolean; error: ApiError \| null; cached: boolean }` |
| `src/features/reminders/index.ts` | WP6 | `useReminders(): { scheduleForDemand(analysis: AnalysisResult, demand: Demand, documentId?: string): Promise<'scheduled' \| 'ics' \| 'denied' \| 'not_eligible'>; list(): Promise<Reminder[]>; remove(id: string): Promise<void> }` |
| `src/features/demo/index.ts` | WP6 | `SamplePicker(props: { onPick(sample: DemoFixture, pages: CapturedPage[]): void })`; `useSampleMode(): { enabled: boolean; set(on: boolean): void }`; `SampleBanner()` |
| `src/features/settings/index.ts` | WP6 | `VaultAndDataSettings()` — sections: keep page images, hide ID numbers, web persistence + clear-on-close, lock-screen detail, PIN (SHOULD), sample mode, withdraw consent, Delete everything |
| `src/features/scan/index.ts` | WP5 | `usePickImage(): { pickFromLibrary(e?: unknown): Promise<CapturedPage[]>; pickPdf(e?: unknown): Promise<CapturedPage \| null>; takePhoto(e?: unknown): Promise<CapturedPage[]> }` (gesture-safe on web; `takePhoto` is a WP5 superset, CL-048(e)); `compressPage(page: CapturedPage): Promise<CapturedPage>` |
| `src/features/emergency/index.ts` | WP5 | `EmergencyCard(props: { kinds: string[]; onClose(): void; inline?: boolean; onMoreHelp?(): void; triggered?: boolean })`; `useEmergencyTrigger(safety: Safety \| null): { triggered: boolean; kinds: string[] }` (optional props and the return shape are WP5 supersets, CL-048(e)) |
| `src/lib/image.ts` | WP5 | `toJpegBase64(input: { uri: string } \| { file: File }, opts: { maxEdge: 1600; quality: 0.8; rotation?: number }): Promise<{ base64: string; width: number; height: number; byteLength: number }>`; `burnMasksOnCanvas(base64: string, masks: MaskRect[]): Promise<string>` (web only; throws on native) |

**Design components (WP4) that WP5/WP6 import** — props are fixed here: `BigButton({ label, icon?, onPress, variant: 'primary' | 'secondary' | 'danger', size: 56 | 72, disabled?, accessibilityHint? })`, `Tile({ title, line, icon, onPress, disabled?, badge? })`, `Card({ headingKey, lang?, speakText?, children, id })` (renders `role="region"` + heading + `SpeakButton`), `SpeakButton({ text, lang })`, `UrgencyBanner({ urgency: Urgency; onVerify?(): void; onRemind?(): void })`, `ConfidenceChip({ confidence, onRescan?(): void })`, `Bidi({ children, dir?: 'ltr' | 'rtl' | 'auto' })`, `Crop({ pageImageUri, bbox, quote, width?, height? })`, `Checklist({ items: { id: string; text: string }[]; state: Record<string, boolean>; onToggle(id, checked) })`, `FeedbackRow({ surface, cardId?, documentType?, resourceId?, modelId? })` (posts counts only via `client.feedback`), `TierBadge({ tier })`, `Banner({ kind: 'demo' | 'unpaid' | 'offline' | 'machine_translation' | 'partial_pack'; text? })`, `ProgressSteps({ steps: string[]; active: number; live?: boolean })`, `EmptyState`, `ErrorState({ error: ApiError; onRetry?, onSaveLater?, onCall211?, onTrySample? })`, `ExternalLink({ href, children })`, `Collapsible({ title, children })`.

**i18n (WP4).** `useT(): (key: string, vars?: Record<string, string | number>) => string` (English fallback, one-time missing-key counter); `useDirection(): { isRTL: boolean; row: 'row' | 'row-reverse'; textAlign: 'left' | 'right'; writingDirection: 'ltr' | 'rtl'; dir: 'ltr' | 'rtl'; alignStart: 'flex-start' | 'flex-end'; alignEnd: 'flex-start' | 'flex-end' }` (`alignStart`/`alignEnd` added by WP4, CL-028(c)); `useLanguage(): { tag; info: LanguageInfo; pack: LanguagePack; loading; switchTo(tagOrQuery: string): Promise<void> }`; `localizedDateLine(iso, digitSystem): string | null` (additional line only, D-26).

**TTS (WP4 `lib/tts.ts`).** `speak(text: string, lang: string, utteranceId?): Promise<ResolvedVoice>`, `stop()`, `useSpeaking(): boolean`, `resolveVoice(lang): Promise<ResolvedVoice>` (async because `expo-speech` voices are async) with `ResolvedVoice = { voice: Voice | null; usedFallbackTag: string | null; languageTag: string }`; with no own or related voice it returns the English voice with `usedFallbackTag: "en-US"` for every language so callers show `tts.fallback_offer` (CL-028(c)); when the device lists no voices at all, or none in English, it returns `{ voice: null, usedFallbackTag: null, languageTag: <the pack's tts_tag> }`.

### 4.3 Generated files and who runs what

| Generated path | Generator | Run by | Check |
|---|---|---|---|
| `apps/api/openapi.json` | `apps/api/scripts/export_openapi.py` (deterministic: `json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"`) | WP0 only | `tests/contract/test_openapi_snapshot.py` |
| `apps/mobile/src/api/schema.d.ts` | `npm run gen:types` = `openapi-typescript ../api/openapi.json -o src/api/schema.d.ts` | WP0 only | `tsc` |
| `apps/mobile/src/i18n/packs/*.json` + `src/i18n/packs/index.ts` (static `require` map `{ [tag]: require('./<tag>.json') }` — Metro cannot `require` a dynamic path, so the loader imports this map), `src/i18n/languages.ts`, `assets/fixtures/**` (manifest.json, `<id>.png` thumbnails ≤ 600 px, `<id>.result.<lang>.json` full `AnalysisResult` — `TroubleshootResult` for the screenshot — produced by running the mock pipeline for each recorded language, plus `index.ts` with the static `require` map used by `api/offline.ts` and `features/demo`), `assets/resources/national_fallbacks.json` (`list[Resource]` for `data/resources/_meta.yaml.well_known_ids.offline_subset`, RESOURCE_DB §7), `assets/fonts/**` (byte copies of `apps/api/data/fonts/`), `locales/*.json` (permission strings from pack keys `perm.camera`, `perm.photos`, `perm.notifications`) | `apps/api/scripts/sync_to_mobile.py` (`--check` verifies equality, exit 1 on drift; WP0 writes the minimal first version on day 0, WP7 owns it after M0) | WP7 (owner), anyone after M0, CI | `sync_to_mobile.py --check` |
| `apps/api/data/langpacks/<tag>.json` (Tier 1+2) | `apps/api/scripts/gen_packs.py` (needs keys) or agent-authored per §5 WP1 step 9 | WP1 | `packs/qa.py` in `tests/unit/test_packs_qa.py` |
| `apps/api/data/fixtures/<id>/{page-*.png, transcript.txt}` and `manifest.yaml.dhash` | `apps/api/scripts/make_fixtures.py` from `data/fixtures/<id>/template.yaml` | WP7 | goldens |
| `apps/api/requirements.txt` | `apps/api/.venv/bin/pip freeze` | WP1 | Docker build in CI |

### 4.4 `en.json` conventions

Flat keys `area.name[.sub]`, `{placeholder}` syntax, English base strings at grade ≤ 5. **The inventory with exact copy is `docs/PRODUCT_SPEC.md` Appendix A** (Appendix C of this file states the rules and points there rather than duplicating 186 rows) plus the server-emitted keys in `docs/RESOURCE_DB.md` §3.3 and §4 (`status_note.*`, `why.*`, `notes.*`, `warn.*`, `prepare.*`). Prefix families actually used: `app`, `tabs`, `btn`, `a11y`, `lang`, `langpack`, `direction`, `consent`, `privacy` (`privacy.notice.*`), `home`, `capture`, `review`, `reading`, `state`, `card`, `confidence`, `role`, `demand`, `plan`, `urgency`, `disclaimer`, `banner`, `warning` (client-rendered `WarningCode`s), `fixed` (D-20 `fixed_copy_key`s), `scam`, `emergency`, `source`, `chat` (`chat.refusal.*`, `chat.refer.*`, `chat.starter.*`), `clerk`, `tts`, `help`, `need`, `resource`, `status_note`, `notes`, `why`, `warn` (resource `warnings[]`), `prepare` (checklist keys, rendered from `ChecklistItem.key`), `vault`, `member`, `wipe`, `reminders`, `notif`, `quicksheet`, `feedback`, `troubleshoot`, `portal`, `settings`, `demo`, `fixture`, `notfound`, `err`, `perm`. Server-side code (WP2/WP3) emits only keys that exist in `en.json` (`tests/unit/test_keys_exist.py`, WP0). Keys whose sentence makes a privacy claim are enumerated in `docs/COMPLIANCE_PRIVACY.md` §17 `privacy_claims` (WP8; a seed list is in place) and checked by `tests/unit/test_privacy_claims.py`.

### 4.5 Fixture ids (exact; D-29 + ARCHITECTURE §2)

`medicaid_address_confirmation`, `uscis_i797c_receipt_i765`, `uscis_rfe_87d`, `nta_hearing_date`, `inova_final_notice`, `insurance_denial_180d`, `prescription_label`, `school_immunization_notice`, `va_pay_or_quit_14d`, `snap_interview_notice`, `irs_cp_notice`, `jury_summons`, `scam_gift_card_letter`, `blurry_unreadable_page`, `spanish_lease`, `w2_form`, `traffic_court_notice`; screenshot `portal_file_too_large`. Expected outputs per fixture: `PRODUCT_SPEC.md` §12.3, mirrored per fixture in Appendix D. The eight **demo fixtures** that get `es`, `prs`, `ar` outputs (`DemoFixture.available_target_languages`): `medicaid_address_confirmation`, `uscis_rfe_87d`, `nta_hearing_date`, `inova_final_notice`, `va_pay_or_quit_14d`, `scam_gift_card_letter`, `jury_summons`, `portal_file_too_large`; every other fixture has `out.en.json` only.

---

## 5. Work packages in detail

Every subsection has the same shape: **Files** (exclusive write scope; Appendix A is the flat index), **Order of work** (numbered so a second agent in the same package can pick up from a step), **Verify** (commands that must pass before merging; pre-installed toolchain only) and **Acceptance** (what a reviewer checks; every line is observable by a command, a test name or a screen state). Steps that depend on another package name the seam they wait on; until then they use WP0's stub.

### 5.0 Day-0 creations and hand-offs (WP0 → owner at M0)

WP0 creates every file below on day 0 so that `pytest`, `tsc`, `expo export` and the mock API work from M0. **After M0 the listed owner writes the file; WP0 never touches it again.** The route *signatures* (path, method, request/response models, `responses={}` error list) in `routers/**` are frozen by the committed `openapi.json`; owners fill bodies. A signature change needs a change-log line and a WP0 snapshot regeneration.

| File(s) created by WP0 | Day-0 content | Owner after M0 |
|---|---|---|
| `apps/api/pyproject.toml` | `[project] name="proxyhealth_api" version="0.1.0" requires-python=">=3.13"` (no dependency list — nothing is installed from it); the full ruff/mypy/pytest config of §4.1 | WP1 |
| `apps/api/.env.example` | `AI_PROVIDER=mock` plus every §6.1 variable as a commented line with its default | WP1 |
| `proxyhealth_api/__init__.py` | `__version__ = "0.1.0"` | WP1 |
| `proxyhealth_api/main.py` | `create_app()` with lifespan building `MockProvider`/`GeminiProvider` (gemini raises `ApiError(503 provider_not_configured)` at first use), stub repos, `install_handlers`, middlewares, `include_router` for all 12 routers; `app = create_app()` | WP1 |
| `proxyhealth_api/settings.py` | every §6.1 variable with its default, `GEMINI_KEYS` JSON parsing, model-id forbidden-pattern validator, `data_use_tier`/`features` properties; nothing else | WP1 |
| `proxyhealth_api/errors.py` | `ApiError` exactly as §4.1, `install_handlers` (ApiError, `RequestValidationError` → 400, `HTTPException`, catch-all 500; `Retry-After` on 429/503) | WP1 |
| `proxyhealth_api/middleware.py` | request id, `X-Contract-Version`/`X-Data-Use-Tier`, CORS, `consent_and_tier_gate` dependency (complete: 428/403 logic is 20 lines); body-limit and access log as no-op pass-throughs | WP1 |
| `proxyhealth_api/deps.py`, `logging_.py`, `ratelimit.py` | accessors as §4.1; allow-list logger with the exact field set; `ratelimit` no-op returning a dependency that does nothing | WP1 |
| `proxyhealth_api/routers/__init__.py` + `health.py config.py langpacks.py admin.py` | real bodies (they only read settings/packs/keypool stubs) | WP1 |
| `proxyhealth_api/routers/analyze.py troubleshoot.py chat.py` | body = validate uploads minimally (MIME + base64 decode) → `run_analysis` etc. | WP2 |
| `proxyhealth_api/analysis/__init__.py pipeline.py troubleshoot_pipeline.py chat_pipeline.py` | `PipelineDeps` + `run_*` that call `AIService.generate` once and map `AnalysisModelOut → AnalysisResult` (all code-computed fields at their neutral defaults: `urgency.level=info`, `verified=true` copied, empty `red_flags`, `disclaimer_kind` by category); no validators | WP2 |
| `proxyhealth_api/routers/resources.py rules.py quicksheet.py` | resources: match → empty `results` + `national_fallbacks=[]`; list → empty; get → 404; rules → `[]`; quicksheet → reportlab one-page PDF with `title` only | WP3 |
| `proxyhealth_api/resources/__init__.py loader.py rules_repo.py`, `quicksheet/__init__.py render.py` | `ResourceRepo`/`RulesRepo` stubs returning empty collections and version `"0"`; `render(req) -> bytes` stub | WP3 |
| `proxyhealth_api/routers/demo.py feedback.py`, `demo/__init__.py fixtures.py`, `feedback/__init__.py store.py` | `FixtureStore` with the one inline fixture (`medicaid_address_confirmation`, English `AnalysisModelOut` literal, Pillow-generated 600×800 placeholder PNG with the text "SAMPLE"); feedback `record()` returns `"fb_stub"` without storing | WP7 |
| `proxyhealth_api/ai/mock.py` | hour-one `MockProvider`: returns the inline fixture's `AnalysisModelOut` for `analyze_single`/`explain`, a fixed `TranscriptOut`, a fixed `TroubleshootModelOut`, a fixed `ChatModelOut` (`not_in_document=true`), pseudo-localized `LanguagePackModelOut`, `LanguageResolveOut(language_tag=None)`, `RewriteOut(sentence=...)`, `TaggingModelOut(tags=[])`; honours `MOCK_LATENCY_*` | WP7 |
| `proxyhealth_api/ai/failover.py routing.py keypool.py` | `AIService` pass-through (one call, slot 0); `route()` implementing the §4.1 table verbatim (it is 10 rows — WP1 adds tests and the degraded/downgrade branches); `KeyPool` class with the §4.1 method signatures raising `NotImplementedError` | WP1 |
| `proxyhealth_api/ai/gemini.py` | **not created** on day 0; WP1 creates it | WP1 |
| `proxyhealth_api/packs/__init__.py base.py cache.py` | `BasePack.load` real (small); `PackCache` with signatures, in-memory dict only | WP1 |
| `apps/api/scripts/sync_to_mobile.py` | minimal deterministic copier: `data/langpacks/*.json` → `apps/mobile/src/i18n/packs/` + `index.ts`; `languages.yaml` → `languages.ts`; `data/fonts/**` → `assets/fonts/`; writes `assets/fixtures/manifest.json` (`[]`) + `index.ts` (empty map), `assets/resources/national_fallbacks.json` (`[]`), `locales/en.json`; `--check` mode | WP7 |
| `.gitignore` (repo root) | adds the line `apps/api/var/` | WP8 |
| `apps/mobile/src/store/session.ts` | the `CapturedPage`, `MaskRect`, `QueuedScan`, `ConsentRecord`, `ServerConfig` types of §4.2 and a zustand store with the listed fields and no-op setters | WP4 |
| `apps/mobile/src/api/errors.ts` | `ApiError` class complete as §4.2 (it is data-only; WP4 may extend, never rename) | WP4 |
| `apps/mobile/src/storage/index.ts` | the `Vault` interface and every exported type of §4.2; `export const vault: Vault` = object whose methods reject with `new Error('vault not implemented')` | WP4 |
| `apps/mobile/src/features/{vault,quicksheet,help,reminders,demo,settings}/index.ts` | stubs with the §4.2 exports; components render `null`, hooks return the empty shapes | WP6 |
| `apps/mobile/src/features/{scan,emergency}/index.ts`, `src/lib/image.ts` | stubs with the §4.2 exports; functions reject with `not implemented` | WP5 |

Not created by WP0 and left as-is at M0: every template file in §5.5 (they still compile; WP4 deletes/replaces them on day 1), `apps/mobile/AGENTS.md`, `apps/mobile/CLAUDE.md`, `apps/mobile/LICENSE`, `apps/mobile/.vscode/**`, `apps/mobile/.claude/settings.json` (unowned, read-only).

Documents: `docs/API_CONTRACT.md` → WP0; `docs/AI_PROMPTS.md`, `docs/DOCUMENT_TAXONOMY.md` → WP2; `docs/RESOURCE_DB.md` → WP3; `docs/COMPLIANCE_PRIVACY.md`, `docs/DEPLOYMENT.md`, `docs/RUNBOOK.md`, `docs/STORE_LISTING.md`, `README.md` → WP8; `docs/DEMO_SCRIPT.md` → WP7; `docs/BUILD_PLAN.md`, `docs/ARCHITECTURE.md`, `docs/PRODUCT_SPEC.md`, `docs/DECISIONS.md` (all but §14) → architect only; `docs/DECISIONS.md` §14 → anyone, append-only.

### 5.1 WP0 — Contract, tokens, day-0 skeleton (day 0, alone)

**Files.** §3 row + §5.0 table.

**Order of work.**
1. Commit the untracked docs and the consistency-pass edits on `main` (`git add docs README.md && git commit`), then work on `wp0-contract`.
2. `pyproject.toml` (§4.1 config), package dirs with `__init__.py`, `tests/**/__init__.py`.
3. `contracts/enums.py` (every enum of API_CONTRACT §1, `str` Enums; `PackTier` is `IntEnum`), then `common.py`, `errors.py`, `config.py`, `langpack.py`, `analysis.py`, `troubleshoot.py`, `chat.py`, `resources.py`, `rules.py`, `quicksheet.py`, `feedback.py`, `demo.py`, `admin.py`, `model_out.py`, `__init__.py` re-exports. Field names exactly as the contract tables (snake_case, no aliases). Request models `model_config = ConfigDict(extra="forbid")`; `AnalyzeRequest` carries the "≥ 1 page unless `demo_sample_id`" validator.
4. `ai/schema_guard.py` (`assert_subset_safe(model)`: depth ≤ 3, no `dict`/`Any`/recursion, unions only `X | None`, enums ≤ 64 values, `bbox` = `list[float]` len 4) + `tests/unit/test_schema_guard.py` iterating every class in `model_out.py`.
5. `data/langpacks/en.json` from PRODUCT_SPEC Appendix A (all 186 rows expand to one key per slash-separated entry) + RESOURCE_DB §3.3/§4 server keys (`status_note.*`, `why.*`, `notes.*`, `warn.*`, `prepare.*`) + CL-005 additions + `fixture.<id>` titles (Appendix D) + `err.<ErrorCode>` for every code. `_contexts.json` (may start `{}`). `data/languages.yaml` = Appendix E. `tests/unit/test_keys_exist.py`: every literal `"…"` matching `^(status_note|why|notes|warn|prepare|fixed|err|urgency|scam|chat\.refusal|chat\.refer|clerk|fixture)\.[a-z0-9_.]+$` found by grep over `proxyhealth_api/**/*.py` and `data/**/*.yaml` exists in `en.json`.
6. `ai/provider.py` (§4.1 verbatim), `ai/mock.py` hour-one, `ai/failover.py` pass-through, `ai/routing.py` table, `ai/keypool.py` signatures.
7. App skeleton (§5.0): all routers with final signatures, `response_model` and `responses={status: {"model": ErrorResponse}}` per API_CONTRACT errors list; `tests/conftest.py` (§4.1 fixtures); `tests/contract/test_m0_smoke.py` (health, config, analyze with/without consent header, demo list, langpack `en` 200 / `xx` 404).
8. `scripts/export_openapi.py` → `openapi.json`; `tests/contract/test_openapi_snapshot.py` (regenerate in memory, compare byte-for-byte, message tells the agent to run the script).
9. Mobile: `package.json` scripts → `"gen:types": "openapi-typescript ../api/openapi.json -o src/api/schema.d.ts"`, remove `reset-project`; `eslint.config.js` `ignores: ["dist/*", "src/api/schema.d.ts"]`; run `npm run gen:types`; `src/api/types.ts` (one alias per schema); `src/design/tokens.ts` (D-28); the three WP4 type stubs and the eight seam stubs (§5.0); minimal `sync_to_mobile.py` and its first run.
10. `.gitignore` += `apps/api/var/`. Run the Verify block, merge to `main`, tag `m0`, post the M0 note in `docs/DECISIONS.md` §14.

**Verify.**
```
apps/api/.venv/bin/pytest apps/api
apps/api/.venv/bin/ruff check apps/api
apps/api/.venv/bin/mypy --config-file apps/api/pyproject.toml apps/api/proxyhealth_api apps/api/scripts apps/api/tests
apps/api/.venv/bin/python apps/api/scripts/export_openapi.py && git diff --exit-code apps/api/openapi.json
apps/api/.venv/bin/python apps/api/scripts/sync_to_mobile.py --check
export PATH="$HOME/.local/node/bin:$PATH"; cd apps/mobile && npm run gen:types && git diff --exit-code src/api/schema.d.ts && npx tsc --noEmit && npx jest && npx expo lint && npx expo export --platform web
```
Plus the manual M0 boot check in §2.

**Acceptance.** All of §2 M0. `openapi.json` contains every path of API_CONTRACT §3 and `ErrorResponse` under every 4xx/5xx; `components.schemas` names equal the contract model names; no schema has a camelCase property. `en.json` has no duplicate keys, every value ≤ grade 5 by eye (CI check is WP8's), and `langpack.adapting` is verbatim.

### 5.2 WP1 — API core, providers, key pool, packs, status endpoints

**Files.** §3 row. **Lanes:** 1A = `main/settings/errors/middleware/ratelimit/logging_/deps`, `routers/{health,config,langpacks,admin}`, `packs/**`, `data/langpacks/<tag>.json`, `Dockerfile`, `requirements.txt`, `.env.example`, `pyproject.toml`, `scripts/gen_packs.py`; 1B = `ai/{gemini,keypool,failover,routing}.py`, `scripts/spike_schema.py` and their unit tests. The seam between lanes is `AIService`/`KeyPool` (§4.1) — 1A codes against the signatures, 1B fills them.

**Order of work.**
1. (1A) `settings.py` complete: all validators (distinct projects, forbidden model ids, `ALLOW_UNPAID_REAL_DOCUMENTS` only outside production, EEA rule is documentation only), `data_use_tier` per D-01, `features` per ARCHITECTURE §2.1. (1B) `keypool.py` state machine per D-07 with an injected `clock`; `var/keypool.json` atomic persistence.
2. (1A) `errors.py` full mapping + `tests/contract/test_errors.py` (envelope shape for 400/404/413/415/428/403/429/500; `Retry-After` present on 429/503). `middleware.py`: body limit (413 before parsing), content-free access log, rate limit wiring (`ratelimit.py`, slowapi, HMAC install hash). (1B) `failover.py` per D-07/§4.1 incl. `SchemaFallbackNeeded`, degraded path, `GenerateOutcome`; `routing.py` tests (`test_routing.py`: every row of AI_PROMPTS §3, `minimal`→`low` on `gemini-3.8*`, page downgrade, degraded swap).
3. (1B) `gemini.py`: one `genai.Client` per slot with `HttpOptions(retry_options=HttpRetryOptions(attempts=2, initial_delay=1.0, max_delay=4.0), timeout=…)`; `client.aio.models.generate_content(model=…, contents=[text, *media], config=GenerateContentConfig(system_instruction, response_mime_type="application/json", response_schema=schema, thinking_config=ThinkingConfig(thinking_level=…, include_thoughts=False), media_resolution=…, max_output_tokens=…))`; block detection (`prompt_feedback.block_reason`, candidate `finish_reason ∈ {SAFETY, RECITATION, PROHIBITED_CONTENT, SPII, BLOCKLIST}`, empty candidates) → `blocked_reason`; `MAX_TOKENS` → `incomplete=True`; status extraction from `errors.ClientError/ServerError .code`. `tests/unit/test_gemini_timeout_unit.py` asserts the `HttpOptions.timeout` field docstring's unit at import (fail loudly if the SDK changes it). No network in tests: a fake client object.
4. (1A) `packs/base.py` (`pack_version = sha256(file bytes)`, chunks of 60), `resolve.py` (`languages.yaml` table → `resolve_language` task → `x-<slug>`), `generator.py`, `qa.py`, `cache.py` (file + LRU + single-flight + TTL), `routers/langpacks.py` (ETag/304/409/404/422). Tests: `test_packs_qa.py`, `test_packs_cache.py`, `test_resolve.py`, `tests/contract/test_langpacks.py`.
5. (1A) `routers/health.py`, `config.py` (languages list from `languages.yaml` with `bundled` computed from file presence and `machine_translated` read from each pack), `admin.py` (mounted only when `ADMIN_TOKEN` set; 401 otherwise). Tests `test_health.py`, `test_config.py` (tier matrix: mock→`demo`; keys all `billing:true`→`paid`; any `billing:false`→`mixed`/`unpaid`; `real_documents_allowed` accordingly), `test_admin.py`.
6. (1A) Bundled packs without keys: author `es.json`, `prs.json`, `ar.json`, `ps.json` by hand as full translations of `en.json` (`machine_translated: true`, `reviewed_by: null`), each passing `packs/qa.py`. The remaining Tier 1+2 tags stay `bundled: false` until `scripts/gen_packs.py` is run with keys (Appendix F, Q1); the client then requests them and mock mode pseudo-localizes. Record the shipped set in `docs/DECISIONS.md` §14.
7. (1A) `logging_.py` allow-list + `test_logging_allowlist.py` (logging any key outside the set raises in tests); `Dockerfile`; `requirements.txt` from `.venv/bin/pip freeze` (no install); `.env.example` complete; `scripts/gen_packs.py`, `scripts/spike_schema.py` (both exit 2 with a clear message when `GEMINI_KEYS` is empty).
8. Tier-gate tests in `tests/contract/test_errors.py`: unpaid slot + real page → 403; unpaid + `demo_sample_id` → 200; no consent header → 428; demo id without header → 200.

**Verify.**
```
apps/api/.venv/bin/pytest apps/api -k "keypool or failover or routing or gemini or logging or packs or resolve or health or config or admin or errors or langpacks or m0_smoke or openapi"
apps/api/.venv/bin/ruff check apps/api
apps/api/.venv/bin/mypy --config-file apps/api/pyproject.toml apps/api/proxyhealth_api apps/api/scripts apps/api/tests
apps/api/.venv/bin/python -c "import json,sys; [json.load(open(p)) for p in sys.argv[1:]]" apps/api/data/langpacks/*.json
```
Optional with keys: `RUN_LIVE=1 apps/api/.venv/bin/pytest apps/api/tests/live` (WP2 owns those tests; WP1 runs them to validate `gemini.py`).

**Acceptance.** Every D-07 transition has a named test; `GET /v1/config` on a `mixed` pool shows `real_documents_allowed:false`; a 429 with `Retry-After: 17` cools that slot for 17 s (clock-injected test); `var/keypool.json` never contains a key string (test greps the file for each slot key); `docker build apps/api` is documented, not run locally.

### 5.3 WP2 — Analysis, troubleshoot and chat pipelines, validators, prompts

**Files.** §3 row (note `data/rules/prepare.yaml` is WP3's).

**Order of work.**
1. **Docs first (blocking for prompts):** write `docs/AI_PROMPTS.md` §4–§14 (schemas guidance, prompt texts, failover pseudo-code, call recipe, mock strategy, safety pipeline, evaluation) and `docs/DOCUMENT_TAXONOMY.md` §4.1–§8 (per-type reference, scam signals §6, phrasing §8). Until §5 of AI_PROMPTS exists `tests/unit/test_prompts_match_doc.py` stays `xfail(strict=False)`; flip it to a real test the same day the prompt files land.
2. `ai/prompts/*.md`, `ai/prompts/user/*.md`, `ai/prompts/VERSION`, `ai/prompt_loader.py` (AI_PROMPTS §2; brace-safety test renders every prompt with dummy vars).
3. `analysis/uploads.py` (+ `test_uploads.py`: MIME sniff vs declared, 413/415, mixed images+PDF → 400 `too_many_pages`, PDF page count via pypdfium2, inline-bytes cap), `redaction.py` (+ `test_redaction.py`: burned pixels are black, EXIF stripped, rotation applied, output never written to disk — test patches `open` for write modes), `pdf_pages.py`, `transcript.py` (SSN mask; A-number/receipt mask when `hide_id_numbers`).
4. `verify.py` (D-09; `test_verify.py` covers exact, NFKC, dash/quote unification, OCR confusion map, difflib ≥ 0.92, edge-crop low-confidence).
5. `contacts_filter.py` (D-10; uses `ResourceRepo.names()`), `deadline_rules.py` (D-11; seed `data/rules/deadlines.yaml` with the 12 rule ids of D-11, the two full entries of API_CONTRACT §3.10 verbatim, source URLs from resources.md), `urgency.py` (D-12 incl. `pay_or_quit` high floor), `scam.py` + `data/safety/scam.yaml`, `emergency.py` + `data/safety/emergency.yaml` (every bundled language; `reviewed_by: null`), `phrasing.py` + `data/safety/phrasing.yaml`, `injection.py` + `data/safety/injection.yaml`, `clerk.py` + `data/rules/clerk_needs.yaml`, `fixed_notices.py` + `data/rules/fixed_notices.yaml` (D-20 kinds → `fixed.*` keys), `disclaimers.py`, `tagging.py`. One `tests/unit/test_<module>.py` each.
6. `pipeline.py` (ARCHITECTURE §2 order; `TASK_SCHEMA`/`TASK_PROMPT` maps; single → two_call fallback on `SchemaFallbackNeeded`; `resource_preview` via `matcher.match(limit=3)` only when `state` given), `troubleshoot_pipeline.py` (fills `TroubleshootResult.safety`), `chat_pipeline.py` (context ≤ 60k chars, grounding check, refusal templates). Until WP3 merges, the stubs return empty results; tests touching resources are `xfail(strict=False)` and flipped at M2.
7. Routers `analyze.py`, `troubleshoot.py`, `chat.py` bodies; `tests/contract/test_{analyze,troubleshoot,chat}.py` against the mock (shape, `demo_sample_id` path, `quality.readable=false` for the blurry fixture once WP7 ships it, 422 on a provider `blocked_reason`, 502 after both modes fail).
8. `scripts/eval_golden.py`, `tests/live/test_live_gemini.py` (skipped unless `RUN_LIVE=1` and keys).

**Verify.**
```
apps/api/.venv/bin/pytest apps/api -k "verify or contacts or deadline or urgency or scam or emergency or phrasing or injection or clerk or redaction or uploads or prompts or analyze or troubleshoot or chat or fixed"
apps/api/.venv/bin/ruff check apps/api
apps/api/.venv/bin/mypy --config-file apps/api/pyproject.toml apps/api/proxyhealth_api apps/api/scripts apps/api/tests
apps/api/.venv/bin/python -c "import yaml,glob; [yaml.safe_load(open(p)) for p in glob.glob('apps/api/data/rules/*.yaml')+glob.glob('apps/api/data/safety/*.yaml')]"
grep -rn "1\.5\|2\.0-\|2\.5-\|-latest\|temperature" apps/api/proxyhealth_api/ai apps/api/proxyhealth_api/analysis || true   # must print nothing
```

**Acceptance.** For every golden fixture (WP7) the pipeline output has: every `Demand` in `demands` with non-empty `source_quote`, `span_ids`, `page`, `confidence`, `verified=true`; zero phone/URL/email tokens in any model-authored string that are not in the transcript or the DB (`test_contacts_filter` + golden assertion); `Demand.date.kind=="estimated"` only with `rule_id`, `formula`, `anchor_quote`; `urgency.level` equals Appendix D; `scam_gift_card_letter` → `scam_risk=="likely"`, `resource_tags[0]=="scam_report"`; `blurry_unreadable_page` → `quality.readable=false` and no second model call (call counter on the mock).

### 5.4 WP3 — Resource DB, matcher, rules repo, quick-sheet PDF

**Files.** §3 row.

**Order of work.**
1. Paste `docs/RESOURCE_DB.md` §11 seed into `data/resources/*.yaml` and `_meta.yaml`; `data/rules/prepare.yaml` from RESOURCE_DB §4.8.
2. `resources/loader.py` (RESOURCE_DB §8: per-entry checks, duplicate ids, `warn.` prefixing, `x_meta` stripping, freshness warning, > 365 d exclusion; boot refusal prints `path:line`), `ResourceRepo` API (§4.1 + RESOURCE_DB §8.4: `names()`, `org_names()`, `is_hhs_funded()`, `phone_index()`, `count()`), `rules_repo.py` (loads WP2's three YAMLs; a **missing** file is tolerated with an empty collection and a warning; a **present but invalid** file refuses boot with `RulesLoadError('<path>:<line>: …')`, like the resource loader — CL-025(f)). Tests `test_loader.py` (bad YAML → error naming path/line; duplicate id; unknown tag; unprefixed warning key).
3. `resources/matcher.py` exactly RESOURCE_DB §6 (pure functions, `today` injected), `checklist.py` (resource items first, then `prepare.yaml`, de-dup, max 8). `test_matcher.py` asserts *order* for each worked example of RESOURCE_DB §6.11, the LSC penalty (shown, not hidden), ≤ 2 per `org_type`, crisis/scam forcing, national fallbacks composition; `test_checklist.py`.
4. `routers/resources.py`, `rules.py`; `tests/contract/test_resources.py` (match/list/get/404, `broken` never listed), `test_rules.py` (12 rules once WP2's `deadlines.yaml` exists; until then asserts the empty response shape).
5. `quicksheet/fonts.py` (font_hint → `data/fonts/*.ttf`, registered once), `render.py` (reportlab, `arabic_reshaper.reshape` + `bidi.algorithm.get_display` per Arabic-script line, RTL right-aligned, English sub-headers, resource re-validation against the DB, footer; Urdu is drawn with Noto Naskh Arabic via `fonts.PDF_SUBSTITUTES` because reportlab has no OpenType GSUB and the Nastaliq TTF does not map the pre-shaped Presentation Forms — the app UI keeps Nastaliq per D-26; Arabic-script text with a missing or wrong `font_hint` also falls back to Naskh; the "Who can help" heading is localized with the English `quicksheet.help` under it — `help_heading()` takes it from a heading-carrier section (`heading_en` = English `quicksheet.help`, empty `lines`, never drawn), else from the bundled pack for `language_tag`, else English; CL-025(a), CL-025(e) superseded by CL-066), `routers/quicksheet.py` (`Content-Disposition`). `test_quicksheet.py`: LTR and RTL requests render, `%PDF` magic, size ≤ 200 KB, an unknown resource phone is dropped, embedded font names appear in the PDF bytes.
6. `scripts/check_links.py` (never run in unit tests; `--freshness` mode for CI).
7. Update `docs/RESOURCE_DB.md` if the seed changed while loading (say which way in the merge note).

**Verify.**
```
apps/api/.venv/bin/pytest apps/api -k "loader or matcher or checklist or quicksheet or resources or rules"
apps/api/.venv/bin/ruff check apps/api
apps/api/.venv/bin/mypy --config-file apps/api/pyproject.toml apps/api/proxyhealth_api apps/api/scripts apps/api/tests
apps/api/.venv/bin/python -c "import sys; sys.path.insert(0,'apps/api'); from pathlib import Path; from proxyhealth_api.resources.loader import ResourceRepo; r=ResourceRepo.load(Path('apps/api/data/resources')); print(r.count())"   # ≥ 70
```

**Acceptance.** `GET /health.resources_loaded ≥ 70` and equals the YAML entry count; every entry has `verified_on`; `GET /v1/resources?tag=jury_summons` returns the `uscourts_jury` entry with both `warn.jury_*` keys; `POST /v1/resources/match` for the Inova example of API_CONTRACT §3.8 returns `inova_fa` first when `state=VA`; RTL PDF opens (manual: Preview.app) with joined Arabic glyphs.

### 5.5 WP4 — Mobile foundation

**Files.** §3 row. **Day-1 deliverables (WP5/WP6 block on them):** `src/app/_layout.tsx`, `src/app/(tabs)/_layout.tsx`, `src/api/client.ts`, `src/store/*` (fill WP0's stub), `src/design/theme.tsx`, `BigButton`, `Card`, `SpeakButton`, `Bidi`, `useT`, `useDirection`. Announce the merge in §14.

**Template files — action, owner, timing (the NativeTabs/web decision is D-27: one JS `Tabs` layout from `expo-router` on every platform; no `_layout.web.tsx`; `expo-router/unstable-native-tabs` and `expo-router/ui` are not imported anywhere):**

| Template file (exists today) | Action | Owner | When |
|---|---|---|---|
| `src/app/_layout.tsx` | replace: root `Stack` + providers (`ThemeProvider`, `I18nProvider`, `DirectionProvider`, `ApiConfigProvider`, `StorageProvider`, splash gate) | WP4 | day 1 |
| `src/app/index.tsx` | replace: redirect logic (language → consent → `(tabs)`) | WP4 | day 1 |
| `src/app/explore.tsx` | delete | WP4 | day 1 (same commit as `_layout.tsx`) |
| `src/components/app-tabs.tsx` (NativeTabs), `app-tabs.web.tsx` (`expo-router/ui`) | delete; replaced by `src/app/(tabs)/_layout.tsx` using `Tabs` from `expo-router` | WP4 | day 1 |
| `src/components/animated-icon.tsx`, `animated-icon.web.tsx`, `animated-icon.module.css`, `hint-row.tsx`, `web-badge.tsx`, `themed-text.tsx`, `themed-view.tsx` | delete | WP4 | day 1 |
| `src/components/external-link.tsx` → `src/design/components/ExternalLink.tsx`; `src/components/ui/collapsible.tsx` → `src/design/components/Collapsible.tsx` | move + rename (`git mv`), then delete the empty `src/components/` | WP4 | day 1 |
| `src/constants/theme.ts` | delete (replaced by `src/design/tokens.ts`, WP0) | WP4 | day 1 |
| `src/hooks/use-theme.ts` | delete (replaced by `src/design/theme.tsx`); keep `use-color-scheme.ts`/`.web.ts` | WP4 | day 1 |
| `scripts/reset-project.js` | delete (WP0 removed the npm script on day 0) | WP4 | day 1 |
| `src/__tests__/smoke.test.tsx` | replace: renders the new Home with providers | WP4 | day 2 |
| `app.json` | replace per ARCHITECTURE §5.3; add the `expo-notifications` plugin block **only after** `assets/images/notification-icon.png` exists (WP8 day-1 deliverable; check the §14 note) | WP4 | day 2–3 |
| `assets/images/expo-*.png`, `react-logo*.png`, `logo-glow.png`, `tutorial-web.png`, `tabIcons/**` | delete — **WP8**, only after this table's deletions have merged (§5.9 rule) | WP8 | after M1 |
| `README.md` (apps/mobile, template text) | replace | WP8 | Phase 2 |
| `AGENTS.md`, `CLAUDE.md`, `LICENSE`, `.vscode/**`, `.claude/settings.json` | keep, read-only | — | — |

**Order of work.**
1. Day 1: the shell files above; `(tabs)/_layout.tsx` with four tabs (icon + word, 64 pt, `maxFontSizeMultiplier={2}` on labels only, RTL via `useDirection`); `design/theme.tsx`; `design/components/*` with the props of §4.2; `i18n/{store,useT,direction,digits,fonts,packLoader}.ts` (+ `readability.md`); `store/{settings,session}.ts`; `api/{client,config,offline}.ts` (+ extend `errors.ts`); `lib/{network,ids,platform,tts}.ts`. `expo-font` loads the nine Noto families from a static map.
2. Day 2: `storage/**` (`vault.native.ts` sqlite + `files.native.ts` + `secure.native.ts`; `vault.web.ts` memory Map + IndexedDB opt-in + `files.web.ts` Blob/`URL.createObjectURL` + `secure.web.ts` shim; `kv.ts`; `migrations.ts`; `wipe.ts`); `Vault.consent` over `kv`.
3. Day 2–3: onboarding S0–S2 (`onboarding/language.tsx`, `adapting.tsx`, `consent.tsx`, `features/onboarding/**` incl. `PrivacyNotice.tsx`), `(tabs)/settings.tsx` (renders WP6's `VaultAndDataSettings` seam), `+not-found.tsx`, `+html.tsx` (lang/dir attributes), `global.css` (`:root[dir=rtl]` helpers), `app.json`, `eas.json` (ARCHITECTURE §5.3 JSON verbatim with placeholders).
4. Tests: `i18n.test.ts`, `bidi.test.tsx`, `storage.web.test.ts` (imports `./vault.web` directly; in-memory path), `storage.native.test.ts` (imports `./vault.native` with `jest.mock('expo-sqlite', …)` and `jest.mock('expo-file-system', …)`; asserts SQL migration list, row mapping, `wipeAll` call order), `api-client.test.ts` (fetch mocked; headers; 428/403/429/422 → `ApiError` fields; 304 path; timeout abort), `consent.test.tsx` (badge + copy per tier incl. `unknown`; `Not now`; record shape). All tests run under the single `jest-expo` preset in `package.json`; platform files are imported explicitly, never via the `.native`/`.web` resolver.

**Verify.**
```
export PATH="$HOME/.local/node/bin:$PATH"; cd apps/mobile
npx tsc --noEmit && npx jest && npx expo lint && npx expo export --platform web
npx expo config --type prebuild > /dev/null
grep -rn "@/components/\|@/constants/theme\|unstable-native-tabs\|expo-router/ui\|expo-symbols\|@expo/ui\|expo-glass-effect" src   # must print nothing
test ! -e src/app/explore.tsx && test ! -d src/components && test ! -e src/constants/theme.ts && test ! -e src/hooks/use-theme.ts && test ! -e scripts/reset-project.js
```
Manual (web, `EXPO_PUBLIC_API_URL=http://127.0.0.1:8000` against the mock API): language grid → adapting → consent shows `Sample mode` badge in mock → tabs render; switch to `ar`/`prs` flips rows and sets `document.documentElement.dir="rtl"`.

**Acceptance.** §3 row. `app.json` has `name "ProxyHealth AI"`, `slug`/`scheme "proxyhealth"`, iOS `privacyManifests`, Android `blockedPermissions`, the `expo-camera`/`expo-image-picker`/`expo-localization`(supportsRTL)/`expo-font`/`expo-document-picker` plugin entries and the bare `expo-sqlite` entry (no SQLCipher claim). `eas.json` parses as JSON (`node -e "JSON.parse(require('fs').readFileSync('eas.json','utf8'))"`).

### 5.6 WP5 — Scan → Reading → Result → Source → Chat → Clerk → Emergency

**Files.** §3 row (fills WP0's `features/{scan,emergency}/index.ts` and `lib/image.ts` stubs).

**Order of work.**
1. `features/scan/**`, `lib/image.ts` (`toJpegBase64` native via `ImageManipulator.manipulate(uri).resize({width:1600}).renderAsync()` → `saveAsync({compress:0.8, format:'jpeg', base64:true})`; web via `<canvas>`; `burnMasksOnCanvas` web only), `lib/pdf.ts`, `scan/capture.tsx` (`CameraView`; web: `ImagePicker.launchImageLibraryAsync` is the first statement of `onPress`), `scan/review.tsx` (masks with `react-native-gesture-handler`; native sends `masks[]`, web burns and sets `masks_applied_client_side`), `scan/reading.tsx` (three steps, `ProgressSteps live`, cancel via `AbortController`, error states 428/403/429/422/503/unreadable via `ErrorState`).
2. `features/analysis/**` (`useAnalyze` builds `AnalyzeRequest` — `include_page_thumbnails: pages[0].mimeType === 'application/pdf'`, `client_platform`, `analysis_id` from `lib/ids.ts`), cards, `unverifiedSection.tsx`, `disclaimers.ts`, `hearItMode.ts`; `result/[id]/index.tsx` (emergency card first when `safety.emergency`, `UrgencyBanner`, three cards, details with `Crop` + `ConfidenceChip` + `Bidi` values, glossary, red flags, `HelpForDocument` seam, `FeedbackRow`, action bar with `SaveToVaultSheet` seam).
3. `result/[id]/source.tsx`, `chat.tsx` (`features/chat/**`, history ≤ 8, context compaction, refusal templates, `suggested_questions`), `clerk.tsx` (`features/clerk/**`, LTR + high contrast + ≥ 24 pt, `clerk.brightness_tip`, 1.5 s long-press exit, `session.clerkMode`), `quicksheet.tsx` and `help.tsx` routes rendering WP6 seams, `emergency.tsx` + `features/emergency/**`, `features/speech/**`, `features/feedback/**`, `lib/dates.ts`.
4. Tests: `result-cards.test.tsx` (renders the RFE and Medicaid `assets/fixtures/*.result.en.json` and `.prs.json` once WP7 syncs them — until then the API_CONTRACT §3.5 example pasted as a test fixture — in LTR and RTL and with `fontScale: 2`), `urgency-banner.test.tsx` (icon + word + color per level).

**Verify.**
```
export PATH="$HOME/.local/node/bin:$PATH"; cd apps/mobile
npx tsc --noEmit && npx jest && npx expo lint && npx expo export --platform web
grep -rn "Platform.OS === 'web'" src/features/scan src/lib/image.ts src/features/troubleshoot 2>/dev/null | wc -l   # > 0
```
Manual (web against mock): sample picker → reading → result shows three cards, quotes, urgency `high` for the Medicaid sample; `Show the clerk` → LTR card, long-press exits; a `429` from the API (`MOCK_FORCE_ERROR=quota_exhausted` is **not** a setting — instead stop the API and check the `network` `ErrorState` with Retry / Save later / Call 211 / Try a sample).

**Acceptance.** §3 row; every fact row shows quote, crop (or full-page fallback) and confidence; a demand in `unverified` never appears in the demands card or gets a reminder button; the web picker opens without a "user gesture" console error; `AnalyzeRequest` sent from web has `masks_applied_client_side: true` and empty `masks` when parts were hidden (assert in `api-client` mock log).

### 5.7 WP6 — Home, vault, Action Hub, reminders, quick sheet, troubleshoot, demo, settings features

**Files.** §3 row (fills WP0's six seam stubs). **Lanes:** 6A = `features/{vault,settings,demo,reminders}/**`, `(tabs)/{index,papers}.tsx`, `papers/**`, `reminders.tsx`, `lib/{notifications.*,ics}.ts`; 6B = `features/{help,quicksheet,troubleshoot}/**`, `(tabs)/help.tsx`, `troubleshoot.tsx`.

**Order of work.**
1. (6A) `(tabs)/index.tsx` Home (72 pt CTA, tiles, next-date card via `useNextDate`, `Banner` demo/offline), `features/demo/**` (`SamplePicker` from `/v1/demo/fixtures` with bundled `assets/fixtures/index.ts` fallback, `SampleBanner`, `useSampleMode`), `features/vault/**` (`SaveToVaultSheet` "Whose paper is this?", members, move, per-member wipe, `useDocument`, `useNextDate`), `(tabs)/papers.tsx`, `papers/member/[id].tsx`, `features/settings/**` (`VaultAndDataSettings`), `features/reminders/**` + `lib/notifications.native.ts` (9:00 local, 7/3/1 days, generic body, channel "Dates to remember") + `lib/notifications.web.ts` + `lib/ics.ts` + `reminders.tsx`.
2. (6B) `features/help/**` (`useResourceMatch` with cache per document, need tiles, region control from `settings.region`, LSC note + "If that is not you", `Checklist` from `checklist[]`, national fallbacks from the response or `assets/resources/national_fallbacks.json` offline, "Verified on" chips), `(tabs)/help.tsx`, `HelpForDocument`; `features/quicksheet/**` (`buildQuickSheetText` excludes anything not in `analysis` or the resource DB; `html.ts` for `expo-print` with embedded base64 fonts and `dir`; `serverPdf.ts` web → `POST /v1/quicksheet/pdf` → Blob → `<a download>`; copy; read aloud), `QuickSheetScreen`; `features/troubleshoot/**` + `troubleshoot.tsx` (mode chips, picker inside the gesture, credential-guard banner when `asks_for_credentials_or_payment`, result cards, emergency card when `safety.emergency`).
3. Tests: `reminders.test.ts` (fire-time math with a fixed `now`, generic body, `.ics` has one `VEVENT` per reminder and generic `SUMMARY` unless opted in), `quicksheet.test.ts` (text builder drops a stripped contact; html contains `dir="rtl"` and a `@font-face`).

**Verify.**
```
export PATH="$HOME/.local/node/bin:$PATH"; cd apps/mobile
npx tsc --noEmit && npx jest && npx expo lint && npx expo export --platform web
```
Manual (web against mock): save the Medicaid sample to "Me" → My papers lists it → Help shows `medicaid_state` + national fallbacks → quick sheet "Download PDF" returns a PDF → reminders "Add to calendar (.ics)" downloads a file → Settings → Delete everything empties the vault.

**Acceptance.** §3 row; saving is opt-in (nothing is stored before the sheet confirms); `Delete everything` clears vault, files, kv, secure store, consent, install id (test on `wipe.ts` order); web vault is memory-only until the IndexedDB opt-in toggle is on; troubleshoot never sends a PDF.

### 5.8 WP7 — Fixtures, mock provider, demo endpoints, feedback counters, goldens, sync

**Files.** §3 row.

**Mock-provider parity table (binding; each row has a test in `tests/golden` or `tests/contract/test_demo.py`/`test_mock_provider.py`):**

| Endpoint / `Task` | Mock behaviour (deterministic; latency `MOCK_LATENCY_MIN/MAX_MS`) | Fixture data used |
|---|---|---|
| `POST /v1/analyze` (`analyze_single`, `transcribe`, `explain`) | `hints.demo_sample_id` → that fixture's `out.<target_language>.json`, else `out.en.json` with every user-facing string prefixed `⟦<tag>⟧`; no id → dHash of page 1 vs every document fixture (Hamming ≤ `MOCK_PHASH_MAX_HAMMING`); no match → generic `AnalysisModelOut` (`document_type=unknown`, `category=other`, `legibility=poor`, `readable_reason="mock_no_match"`, empty lists) which the pipeline renders as `quality.readable=false` + `warnings=[low_quality_image]` | `data/fixtures/<id>/{manifest.yaml,page-*.png,transcript.txt,out.*.json}` |
| `POST /v1/troubleshoot` (`troubleshoot`) | `demo_sample_id` → `out.<lang>.json` of a `kind: screenshot` fixture; else dHash vs screenshot fixtures; else generic `TroubleshootModelOut` (`screen_summary` = pack string `troubleshoot.mock_unrecognised` in English, `steps=[]`, `needs_human_help=true`, `confidence=low`, `screen_text=[]`) | `portal_file_too_large` |
| `POST /v1/chat` (`chat`) | reads the request's `AnalysisContext`, never a fixture: question matches a date/deadline word list → answer quotes the first verified `deadline`/`appointment` demand's `source_quote` (`grounded_span_ids` from it); matches scam words → grounds on `red_flags`; matches eligibility/outcome/advice words → `refusal_kind` (`eligibility`/`outcome`/`filing_advice`) + `refer_to_professional` by `category`; otherwise `not_in_document=true` grounded on `summary.span_ids`. Checked in the order refusal → scam → date (so "will I win by the date?" is refused, not answered with a date — CL-052(f)). Word lists live in `demo/chat_mock.py` (`WORDS`) for `en`, `es`, `prs`, `ar`; `ai/mock.py` imports them (CL-052(e)) | none |
| `POST /v1/language-packs` (`resolve_language`, `langpack_chunk`) | `resolve_language`: `languages.yaml` name lookup (case-insensitive, `name_en`/`name_native`), else `language_tag=None` (→ `x-<slug>`); `langpack_chunk`: `value = "⟦<tag>⟧ " + english` with placeholders intact, `direction` from a script table (`ar, prs, ps, fa, ur, he, rhg, ug, sd, ckb` → `rtl`), `confidence=low`, `fallback_keys=[]` | `data/languages.yaml` |
| `tag` | tags from the matched fixture's `out.en.json` when `hints.demo_sample_id` is set, else a fixed `document_type → tags` map (`demo/mock_outputs.py` `DOCUMENT_TYPE_TAGS`, imported by `ai/mock.py` — CL-052(e)) derived from DOCUMENT_TAXONOMY §2 | fixtures |
| `phrasing_rewrite` | `RewriteOut(sentence="The paper says " + sentence with its first character lower-cased)`; the pipeline re-lints and falls back to the fixed hedge if still flagged | none |
| `clerk_translate` | `LanguagePackModelOut` with one key: `"⟦<tag>⟧ " + english` | none |
| `GET /health`, `GET /v1/config` | provider `mock`, `keys_configured=0`, `keys_healthy=0`, `data_use_tier=demo`, `key_slots` all 0, `features.real_documents_allowed=true` | none (WP1) |
| `GET /v1/language-packs/{tag}` | bundled file or 404 — no model (WP1) | `data/langpacks/*.json` |
| `/v1/resources/*`, `/v1/rules`, `/v1/quicksheet/pdf`, `/v1/feedback`, `/v1/demo/*` | no model; data-driven (WP3/WP7) | YAML + fixtures |
| `GET /v1/admin/keys` | `slots=[]`, `data_use_tier=demo` (WP1) | none |

**Order of work.**
1. `scripts/make_fixtures.py`: `data/fixtures/<id>/template.yaml` (text lines, layout hints, language) → `page-*.png` (Pillow, 1600 px wide, Noto fonts from `data/fonts`, Arabic-script lines shaped with `arabic_reshaper` + `bidi`, diagonal "SAMPLE" watermark) + `transcript.txt` + `manifest.yaml.dhash`. Build all 18 fixtures of Appendix D; `blurry_unreadable_page` is a Gaussian-blurred, low-contrast render.
2. `demo/phash.py` (16×16 dHash, Hamming) + `demo/fixtures.py` (`FixtureStore` per §4.1) + `routers/demo.py`; `tests/contract/test_demo.py` (list has 18 entries, `available_target_languages` per Appendix D, PNG bytes start with `\x89PNG`, 404s).
3. `ai/mock.py` complete per the table; `tests/unit/test_mock_provider.py` (one test per row; dHash: re-encode each page at 80 % JPEG and 0.5 scale → same fixture; every other fixture → distance > threshold).
4. `out.en.json` for all 18 fixtures (hand-authored `AnalysisModelOut`/`TroubleshootModelOut` satisfying every WP2 validator; quotes copied from `transcript.txt`; `_meta.prompts_version` from `ai/prompts/VERSION`), then `out.{es,prs,ar}.json` for the eight demo fixtures. `ai/recording.py` (`RecordingProvider`, dev only, writes these files when keys exist).
5. `tests/golden/test_fixtures_golden.py`: for each fixture × recorded language run `run_analysis`/`run_troubleshoot` with the mock and assert: result validates; `urgency.level`, `Demand.date.kind`, `scam_risk`, `quality.readable`, forced fixed-notice keys per Appendix D; zero contacts outside transcript/DB; `verification.facts_rejected == 0`. Marked `xfail(strict=False)` for rows that need WP2/WP3 until M2.
6. `feedback/store.py` (sqlite counters keyed by the API_CONTRACT §3.12 tuple; hand-rolled ULID), `routers/feedback.py`; `tests/unit/test_feedback_store.py` (no column other than the enum tuple + count; two posts increment once each; id matches `^fb_[0-9A-HJKMNP-TV-Z]{26}$`), `tests/contract/test_feedback.py`.
7. `scripts/sync_to_mobile.py` full version (§4.3 outputs incl. `<id>.result.<lang>.json` produced by running the mock pipeline, thumbnails ≤ 600 px, `index.ts` maps, `locales/<tag>.json`); `docs/DEMO_SCRIPT.md` (PRODUCT_SPEC §13 adapted to what shipped).

**Verify.**
```
apps/api/.venv/bin/pytest apps/api -k "demo or mock or golden or feedback or phash"
apps/api/.venv/bin/ruff check apps/api
apps/api/.venv/bin/mypy --config-file apps/api/pyproject.toml apps/api/proxyhealth_api apps/api/scripts apps/api/tests
apps/api/.venv/bin/python apps/api/scripts/make_fixtures.py --check      # regenerating changes no bytes
apps/api/.venv/bin/python apps/api/scripts/sync_to_mobile.py --check
ls apps/api/data/fixtures | wc -l                                          # 18
```

**Acceptance.** §3 row; `git ls-files apps/api/data/fixtures | grep -c out.en.json` = 18 and `grep -c "out.prs.json"` = 8; every fixture page has the word SAMPLE visible; `sync_to_mobile.py --check` exits 0 on `main`.

### 5.9 WP8 — DevOps, CI, store, compliance docs, artwork, README

**Files.** §3 row. **Day-1 deliverables:** `Makefile`, `scripts/dev.sh`, `apps/mobile/assets/images/notification-icon.png` (96×96, white glyph on transparent — needed before WP4 adds the notifications plugin).

**Artwork rule.** Template artwork (`expo-*.png`, `react-logo*.png`, `logo-glow.png`, `tutorial-web.png`, `tabIcons/**`) is deleted only after WP4's day-1 shell has merged to `main` and `grep -rn "assets/images/\(expo-\|react-logo\|logo-glow\|tutorial-web\|tabIcons\)" apps/mobile/src` prints nothing. `icon.png`, `splash-icon.png`, `favicon.png`, `android-icon-*.png`, `expo.icon/**` are replaced in place (same file names) so `app.json` never breaks.

**Order of work.**
1. `Makefile` (ARCHITECTURE §5.1 targets; `test` uses the mypy form of §1.4), `scripts/dev.sh` (starts uvicorn from `apps/api` and `npx expo start --web` with `EXPO_PUBLIC_API_URL`; `trap` kills both), `scripts/gen-types.sh`.
2. `apps/api/scripts/smoke.py` (stdlib `urllib` only: health, config, langpack `en`, analyze with `demo_sample_id` for every fixture + consent header, troubleshoot for the screenshot, chat, resources match, rules, quicksheet PDF magic bytes, feedback, demo list/PNG; asserts no `[contact removed` in any string, urgency per Appendix D) + `scripts/smoke.sh` (boots the API in mock mode on a free port, waits for `/health`, runs `smoke.py`, always stops the server).
3. `scripts/ci.sh` (the full list in the §3 row, in order; exits on first failure) and `.github/workflows/ci.yml` (jobs per ARCHITECTURE §5.2; mobile job runs `npm ci --legacy-peer-deps` then `npx expo customize tsconfig.json`).
4. `tests/unit/test_privacy_claims.py` (COMPLIANCE_PRIVACY §17 rules a–c) and `tests/unit/test_readability.py` (every `en.json` value: average sentence ≤ 12 words, no word > 3 syllables outside an allow-list file `tests/unit/readability_allowlist.txt`; the grade-5 target is approximated this way because no readability package is installed).
5. `apps/mobile/public/privacy/index.html` (COMPLIANCE_PRIVACY §4.5 text; plain HTML; `lang`/`dir`), artwork replacements, `.gitignore` review (`var/`, `.env`, `dist/`, `expo-env.d.ts` already covered), `README.md` (root) and `apps/mobile/README.md`, `docs/{DEPLOYMENT,RUNBOOK,STORE_LISTING}.md`, complete `docs/COMPLIANCE_PRIVACY.md` §5–§16.
6. File `CL-008` asking the architect to change the mypy line in `CLAUDE.md` to the §1.4 form.

**Verify.**
```
make smoke
make test
make export-web && test -f apps/mobile/dist/privacy/index.html
bash -n scripts/ci.sh && scripts/ci.sh
apps/api/.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
```

**Acceptance.** §3 row; `make dev` opens the web app talking to the mock API within 60 s on this Mac; `scripts/ci.sh` is green on `main` at M4; `STORE_LISTING.md` answers every item of compliance.md §1; no privacy sentence outside `approved_keys` (test).

---

## 6. Integration and verification stage (days 7–9; everyone, WP0 merges)

Run in this order on `main` after every package has merged; each line is a gate for the next.

1. `apps/api/.venv/bin/pytest apps/api` — no `xfail` markers left except `tests/live/**` skips (`grep -rn "xfail" apps/api/tests | grep -v live` prints nothing).
2. `apps/api/.venv/bin/ruff check apps/api && apps/api/.venv/bin/mypy --config-file apps/api/pyproject.toml apps/api/proxyhealth_api apps/api/scripts apps/api/tests`.
3. `apps/api/.venv/bin/python apps/api/scripts/export_openapi.py && git diff --exit-code apps/api/openapi.json` and `(cd apps/mobile && npm run gen:types && git diff --exit-code src/api/schema.d.ts)`.
4. `apps/api/.venv/bin/python apps/api/scripts/sync_to_mobile.py --check` and `make_fixtures.py --check`.
5. Mobile: `npx tsc --noEmit && npx jest && npx expo lint && npx expo export --platform web && npx expo config --type prebuild > /dev/null`.
6. `make smoke` then `scripts/ci.sh`.
7. Demo rehearsal on web (`make dev`): `docs/DEMO_SCRIPT.md` end to end in `en`, then `prs` (RTL) — Medicaid sample, RFE sample, scam sample, portal screenshot, quick sheet download, `.ics` download, Delete everything. Record timings in the script.
8. Manual web checks that no test covers: IndexedDB opt-in persists a saved paper across reload and `clearOnClose` removes it; picker opens on first click (no gesture error in console); `document.documentElement.dir` flips.
9. Android development build (needs network + Expo account; outside Phase 1): `npx eas-cli@latest build --profile development --platform android`, install, repeat step 7 on the device; verify camera, masks via `masks[]`, notifications channel, RTL restart prompt, share sheet PDF. Log results in `docs/RUNBOOK.md`.
10. If billed keys exist (Q1): `RUN_LIVE=1 apps/api/.venv/bin/pytest apps/api/tests/live` and `apps/api/.venv/bin/python apps/api/scripts/eval_golden.py`; otherwise record "not run — no keys" in the M4 note.
11. Privacy read-through: every `approved_keys` string vs the tier actually running (`/v1/config.data_use_tier`); the consent screen in mock mode shows the `demo` line.
12. Tag `v1.0.0-rc1`.

---

## 7. Definition of done for v1 (each line names the proof)

| # | Done when | Proof |
|---|---|---|
| 1 | Contract frozen and generated | `test_openapi_snapshot` passes; `git diff --exit-code` after `export_openapi.py` and `gen:types` (§6.3) |
| 2 | Zero-key operation | `make smoke` green with no `.env`; `GET /health.provider == "mock"`; every §5.8 table row has a passing test |
| 3 | Tier gate is server-side | `tests/contract/test_errors.py::test_403_unpaid_or_mixed_tier_blocks_real_pages`, `::test_428_without_consent`, `::test_428_stale_or_malformed_consent`, `::test_demo_sample_without_consent_header_is_200`, `::test_unpaid_tier_demo_sample_passes_the_gate` pass (CL-069(d)) |
| 4 | Every fact is a quotation | `tests/golden/test_fixtures_golden.py` asserts `source_quote`/`span_ids`/`page`/`confidence`/`verified` on every `Demand` and `facts_rejected == 0` for all 18 × recorded languages |
| 5 | No invented contacts | golden assertion "zero phone/URL/email/org tokens outside transcript ∪ DB" passes; `smoke.py` finds no `[contact removed` |
| 6 | Dates only from code | `test_deadline_rules.py` (stated/estimated/unresolved, printed date wins) and `GET /v1/rules` returns 12 rules with `source_url` |
| 7 | Resource DB vetted | `resources_loaded ≥ 70`; every entry `verified_on` ≤ 120 days at tag time (`check_links.py --freshness` green) |
| 8 | Mobile builds on every platform from one codebase | `npx expo export --platform web` green; `npx expo config --type prebuild` green; Android dev build installs (§6.9, recorded in RUNBOOK) |
| 9 | Web fallbacks exist | `grep -rln "Platform.OS === 'web'\|\.web\.ts" apps/mobile/src` covers scan, storage, notifications, quicksheet, troubleshoot, clipboard; manual §6.8 |
| 10 | RTL + fonts + TTS honest | `i18n.test.ts`, `bidi.test.tsx`, `result-cards.test.tsx` (RTL, 200 %) pass; manual `prs` rehearsal (§6.7) |
| 11 | Storage on device only, opt-in | `storage.*.test.ts`, `wipe` order test; server code has no file write outside `var/` (`grep -rn "open(.*[\"']w" apps/api/proxyhealth_api | grep -v var/` prints nothing) |
| 12 | Privacy copy literally true | `test_privacy_claims.py` green; `test_readability.py` green |
| 13 | Language packs | `en` + at least `es`, `prs`, `ar`, `ps` bundled and QA-clean (`test_packs_qa.py`); `POST /v1/language-packs` for "Rohingya" returns a pack in mock mode; `banner.machine_translation` shows for every `machine_translated` pack (consent/i18n tests) |
| 14 | Fixtures and demo | 18 fixtures with `out.en.json`, 8 with `es/prs/ar`; `GET /v1/demo/fixtures` lists 18; `sync_to_mobile.py --check` green; `DEMO_SCRIPT.md` rehearsed (§6.7) |
| 15 | Feedback is counts only | `test_feedback_store.py` schema test passes |
| 16 | Docs complete | no incomplete-section marker remains in `docs/*.md` (`grep -l "INCOMPLET[E]" docs/*.md` prints nothing; the bracket keeps this row from matching itself); `STORE_LISTING.md`, `DEPLOYMENT.md`, `RUNBOOK.md` exist |
| 17 | CI | `scripts/ci.sh` green locally on `main`; `ci.yml` parses |
| 18 | Tag | `v1.0.0-rc1` on `main` with all of the above |

---

## Appendix A — File → owner index

Globs are relative to `apps/api/proxyhealth_api/` (API code), `apps/api/` (API data/scripts/tests), `apps/mobile/` (mobile) or the repo root (marked). "→" = created by WP0, handed off at M0 (§5.0).

| Path | Owner |
|---|---|
| root `CLAUDE.md`, `docs/BUILD_PLAN.md`, `docs/ARCHITECTURE.md`, `docs/PRODUCT_SPEC.md`, `docs/DECISIONS.md` (except §14) | architect (nobody in Phase 1) |
| root `.gitignore` | WP0 → WP8 |
| root `README.md`, `Makefile`, `scripts/**`, `.github/**` | WP8 |
| `docs/API_CONTRACT.md` | WP0 |
| `docs/AI_PROMPTS.md`, `docs/DOCUMENT_TAXONOMY.md` | WP2 |
| `docs/RESOURCE_DB.md` | WP3 |
| `docs/DEMO_SCRIPT.md` | WP7 |
| `docs/COMPLIANCE_PRIVACY.md`, `docs/DEPLOYMENT.md`, `docs/RUNBOOK.md`, `docs/STORE_LISTING.md` | WP8 |
| `docs/DECISIONS.md` §14 | anyone, append-only |
| `apps/api/pyproject.toml`, `.env.example`, `Dockerfile`, `requirements.txt` | WP0 → WP1 (pyproject, .env.example); WP1 (Dockerfile, requirements) |
| `apps/api/openapi.json`, `scripts/export_openapi.py` | WP0 |
| `scripts/{gen_packs,spike_schema}.py` | WP1 |
| `scripts/eval_golden.py` | WP2 |
| `scripts/check_links.py` | WP3 |
| `scripts/{make_fixtures,sync_to_mobile}.py` | WP7 (`sync_to_mobile.py`: WP0 →) |
| `scripts/smoke.py` | WP8 |
| `__init__.py`, `main.py`, `settings.py`, `errors.py`, `middleware.py`, `ratelimit.py`, `logging_.py`, `deps.py` | WP0 → WP1 |
| `contracts/**` | WP0 |
| `ai/provider.py`, `ai/schema_guard.py` | WP0 |
| `ai/gemini.py`, `ai/keypool.py`, `ai/failover.py`, `ai/routing.py`, `ai/__init__.py` | WP1 (`failover`, `routing`, `keypool`: WP0 →) |
| `ai/mock.py`, `ai/recording.py` | WP7 (`mock.py`: WP0 →) |
| `ai/prompts/**`, `ai/prompt_loader.py` | WP2 |
| `analysis/**` | WP2 (`pipeline.py`, `troubleshoot_pipeline.py`, `chat_pipeline.py`, `__init__.py`: WP0 →) |
| `packs/**` | WP1 (`base.py`, `cache.py`, `__init__.py`: WP0 →) |
| `resources/**`, `quicksheet/**` | WP3 (`loader.py`, `rules_repo.py`, `render.py`, `__init__.py`: WP0 →) |
| `demo/**`, `feedback/**` | WP7 (`fixtures.py`, `store.py`, `__init__.py`: WP0 →) |
| `routers/__init__.py`, `routers/{health,config,langpacks,admin}.py` | WP0 → WP1 |
| `routers/{analyze,troubleshoot,chat}.py` | WP0 → WP2 |
| `routers/{resources,rules,quicksheet}.py` | WP0 → WP3 |
| `routers/{demo,feedback}.py` | WP0 → WP7 |
| `data/langpacks/en.json`, `data/langpacks/_contexts.json`, `data/languages.yaml` | WP0 |
| `data/langpacks/<tag>.json` (tag ≠ en) | WP1 |
| `data/rules/{deadlines,fixed_notices,clerk_needs}.yaml`, `data/safety/**` | WP2 |
| `data/rules/prepare.yaml`, `data/resources/**`, `data/fonts/**` | WP3 |
| `data/fixtures/**` | WP7 |
| `apps/api/var/**` | runtime, git-ignored, nobody |
| `tests/conftest.py`, `tests/**/__init__.py`, `tests/contract/{test_openapi_snapshot,test_m0_smoke}.py`, `tests/unit/{test_schema_guard,test_keys_exist}.py` | WP0 |
| other `tests/**` | Appendix B |
| `apps/mobile/package.json` (scripts only), `tsconfig.json`, `eslint.config.js`, `src/api/schema.d.ts`, `src/api/types.ts`, `src/design/tokens.ts` | WP0 |
| `apps/mobile/package.json` (dependencies) | nobody (install window only) |
| `app.json`, `eas.json`, `src/app/{_layout,index,+not-found,+html}.tsx`, `src/app/onboarding/**`, `src/app/(tabs)/{_layout,settings}.tsx`, `src/design/theme.tsx`, `src/design/components/**`, `src/i18n/**` (except generated), `src/storage/**`, `src/api/{client,errors,config,offline}.ts`, `src/lib/{network,ids,platform,tts}.ts`, `src/store/**`, `src/features/onboarding/**`, `src/hooks/**`, `src/global.css`, deletions in §5.5 | WP4 (`store/session.ts`, `api/errors.ts`, `storage/index.ts`: WP0 →) |
| `src/app/scan/**`, `src/app/result/**`, `src/app/emergency.tsx`, `src/features/{scan,analysis,chat,clerk,speech,feedback,emergency}/**`, `src/lib/{image,pdf,dates}.ts` | WP5 (`features/{scan,emergency}/index.ts`, `lib/image.ts`: WP0 →) |
| `src/app/(tabs)/{index,papers,help}.tsx`, `src/app/papers/**`, `src/app/reminders.tsx`, `src/app/troubleshoot.tsx`, `src/features/{vault,help,reminders,quicksheet,troubleshoot,demo,settings}/**`, `src/lib/{notifications.native,notifications.web,ics}.ts` | WP6 (`features/{vault,quicksheet,help,reminders,demo,settings}/index.ts`: WP0 →) |
| `src/i18n/packs/*.json`, `src/i18n/packs/index.ts`, `src/i18n/languages.ts`, `assets/fixtures/**`, `assets/resources/**`, `assets/fonts/**`, `locales/**` | WP7 (generated only) |
| `assets/images/**`, `assets/expo.icon/**`, `public/**`, `apps/mobile/README.md` | WP8 |
| `apps/mobile/AGENTS.md`, `CLAUDE.md`, `LICENSE`, `.vscode/**`, `.claude/**`, `expo-env.d.ts` (generated, git-ignored), `package-lock.json` | read-only |
| `src/__tests__/**` | Appendix B |

Rule for anything not listed: unowned — file a `CL-nnn` line before creating it.

## Appendix B — Test file → owner

API (`apps/api/tests/`): `conftest.py`, `**/__init__.py`, `contract/test_openapi_snapshot.py`, `contract/test_m0_smoke.py`, `unit/test_schema_guard.py`, `unit/test_keys_exist.py` → **WP0**. `unit/test_{keypool,failover,routing,gemini_timeout_unit,logging_allowlist,packs_qa,packs_cache,resolve}.py`, `contract/test_{health,config,langpacks,admin,errors}.py` → **WP1**. `unit/test_{prompts_match_doc,verify,contacts_filter,deadline_rules,urgency,scam,emergency,phrasing,injection,clerk,redaction,uploads,fixed_notices}.py`, `contract/test_{analyze,troubleshoot,chat}.py`, `live/**` → **WP2**. `unit/test_{matcher,loader,checklist,quicksheet}.py`, `contract/test_{resources,rules,quicksheet_pdf}.py` → **WP3**. `unit/test_{feedback_store,mock_provider}.py`, `contract/test_{demo,feedback}.py`, `golden/**` → **WP7**. `unit/test_{privacy_claims,readability}.py`, `unit/readability_allowlist.txt` → **WP8**. WP-specific fixtures: `tests/<dir>/_fixtures_<wp>.py`, imported explicitly; never a second `conftest.py`.

Mobile (`apps/mobile/src/__tests__/`): `smoke.test.tsx`, `i18n.test.ts`, `bidi.test.tsx`, `storage.native.test.ts`, `storage.web.test.ts`, `api-client.test.ts`, `consent.test.tsx` → **WP4**. `result-cards.test.tsx`, `urgency-banner.test.tsx` → **WP5**. `reminders.test.ts`, `quicksheet.test.ts` → **WP6**. New test files go next to these with the owner of the module under test.

## Appendix C — `en.json` key inventory (rules and pointer)

The inventory **is** `docs/PRODUCT_SPEC.md` Appendix A (186 table rows; a row `a / b / c` expands to three keys) plus the server-emitted families in `docs/RESOURCE_DB.md` §3.3 (`status_note.*`), §4.2 (`why.*`), §4.3 (`notes.*`, `warn.*`), §4.4 (`prepare.*`), plus `fixed.*` (D-20 kinds), `err.<ErrorCode>` for all 19 codes, `urgency.<level>.*` headline keys, `scam.*` reason keys, `chat.refusal.<RefusalKind>`, `chat.refer.<ReferTo>`, `clerk.*`, `fixture.<id>` for the 18 ids in Appendix D, `perm.{camera,photos,notifications}`, and the CL-005 additions. Rules: flat keys `area.name[.sub]` from the prefix families in §4.4; `{placeholder}` syntax; grade ≤ 5 English (WP8's `test_readability.py`); a key is added only by WP0 on a `CL-nnn` request; server code emits only keys that exist (`test_keys_exist.py`); privacy sentences only under COMPLIANCE_PRIVACY §17 `approved_keys`. Packs never add or drop keys; missing keys fall back to English and are listed in `fallback_keys`.

## Appendix D — Fixture inventory (ids, kinds, recorded languages; expectations in PRODUCT_SPEC §12.3)

| id | kind | `document_type` / `category` | `available_target_languages` | Golden asserts (from PRODUCT_SPEC §12.3) |
|---|---|---|---|---|
| `medicaid_address_confirmation` | document | `medicaid_renewal` / benefits | en, es, prs, ar | `high`, `stated` 2026-10-14, 2 demands, `clerk.interpreter_hhs` appended |
| `uscis_i797c_receipt_i765` | document | `uscis_receipt` / immigration | en | `info`; `fixed.uscis_receipt_i765` red flag `high` |
| `uscis_rfe_87d` | document | `uscis_rfe` / immigration | en, es, prs, ar | `high` or `critical` by days-until; `stated` date; prepare items `bring_notice`, `bring_receipt_number` |
| `nta_hearing_date` | document | `nta` / immigration | en, es, prs, ar | `critical` (≤ 7 d) else floor `high`; `verify_resource_id` set; `fixed.address_change_multi_agency` |
| `inova_final_notice` | document | `medical_bill` / medical | en, es, prs, ar | `medium`; red flag `urgency_pressure`; `inova_fa` first when `state=VA` |
| `insurance_denial_180d` | document | `insurance_denial` / medical | en | `medium`; `estimated` via `aca_internal_appeal_180d` with `formula` and `rule_source_url` |
| `prescription_label` | document | `prescription_label` / medical | en | `info`; glossary; `medical_information_only`; no interpretation |
| `school_immunization_notice` | document | `immunization_notice` / school | en | `medium`; CDC IIS resource in preview |
| `va_pay_or_quit_14d` | document | `pay_or_quit` / housing | en, es, prs, ar | printed pay-by → `stated`; `high` (floor); `fixed.pay_or_quit`; eviction resources |
| `snap_interview_notice` | document | `snap_notice` / benefits | en | `high` appointment; `documents` bring list |
| `irs_cp_notice` | document | `irs_notice` / tax | en | `medium`; IRS notice resource |
| `jury_summons` | document | `jury_summons` / civic | en, es, prs, ar | `medium`; `fixed.jury_summons` `high` |
| `scam_gift_card_letter` | document | `other_notice` / immigration | en, es, prs, ar | `scam_risk: likely`; `resource_tags[0] == scam_report`; DHS OIG first, FTC in the top 3 (RESOURCE_DB §6.11-D order; CL-052(g)) |
| `blurry_unreadable_page` | document | `unknown` / other | en | `quality.readable=false`; exactly one model call |
| `spanish_lease` | document | `lease` / housing | en | `info`; `detected_language: es`; `document_language_differs` when target ≠ es |
| `w2_form` | document | `w2_1099` / employment | en | `info`; glossary has EIN + withholding; ITIN resource |
| `traffic_court_notice` | document | `traffic_court` / court | en | `high`/`critical` court date; `legal_information_only` |
| `portal_file_too_large` | screenshot | — / benefits | en, es, prs, ar | steps quote "Back", "Choose File", "Upload"; caution names "Submit Application"; `safety.emergency=false` |

Per-fixture files: `manifest.yaml` (id, title_en, document_type, category, language_of_document, pages, kind, dhash, `today`, expected facts), `template.yaml` (source for `make_fixtures.py`), `page-<n>.png`, `transcript.txt`, `out.<lang>.json`.

The golden asserts above hold as of the pinned sample "today", 2026-10-02: every manifest's `today`, `demo/as_of.py` `DEMO_AS_OF` (the day the server computes a sample paper's dates and urgency from, never the wall clock), `sync_to_mobile.py`'s offline bundle and en `demo.as_of_note` all use it and change together (PRODUCT_SPEC §12.3; CL-067(a)).

## Appendix E — `data/languages.yaml` seed

Format: one entry per tag with the `LanguageInfo` fields except `bundled` and `machine_translated`, which the server computes at boot (`bundled` = `data/langpacks/<tag>.json` exists; `machine_translated` = the pack file's flag, `false` only for `en`). `font_hint: null` means system fonts (CJK). `tts_tag: null` means "no voice expected; use `tts_fallback_tag` or English with the honest message".

```yaml
# data/languages.yaml — WP0. tag: {name_native, name_en, direction, script, digit_system, font_hint, tier, tts_tag, tts_fallback_tag}
en:      {name_native: English,            name_en: English,                 direction: ltr, script: Latn, digit_system: western,        font_hint: NotoSans,               tier: 1, tts_tag: en-US, tts_fallback_tag: null}
es:      {name_native: Español,            name_en: Spanish,                 direction: ltr, script: Latn, digit_system: western,        font_hint: NotoSans,               tier: 1, tts_tag: es-US, tts_fallback_tag: es-MX}
zh-Hans: {name_native: 简体中文,             name_en: Chinese (Simplified),    direction: ltr, script: Hans, digit_system: western,        font_hint: null,                   tier: 1, tts_tag: zh-CN, tts_fallback_tag: null}
zh-Hant: {name_native: 繁體中文,             name_en: Chinese (Traditional),   direction: ltr, script: Hant, digit_system: western,        font_hint: null,                   tier: 1, tts_tag: zh-TW, tts_fallback_tag: zh-HK}
vi:      {name_native: Tiếng Việt,         name_en: Vietnamese,              direction: ltr, script: Latn, digit_system: western,        font_hint: NotoSans,               tier: 1, tts_tag: vi-VN, tts_fallback_tag: null}
tl:      {name_native: Tagalog,            name_en: Tagalog (Filipino),      direction: ltr, script: Latn, digit_system: western,        font_hint: NotoSans,               tier: 1, tts_tag: fil-PH, tts_fallback_tag: null}
ar:      {name_native: العربية,            name_en: Arabic,                  direction: rtl, script: Arab, digit_system: eastern_arabic, font_hint: NotoNaskhArabic,        tier: 1, tts_tag: ar-SA, tts_fallback_tag: ar-EG}
ht:      {name_native: Kreyòl ayisyen,     name_en: Haitian Creole,          direction: ltr, script: Latn, digit_system: western,        font_hint: NotoSans,               tier: 1, tts_tag: null,  tts_fallback_tag: fr-FR}
pt-BR:   {name_native: Português (Brasil), name_en: Portuguese (Brazil),     direction: ltr, script: Latn, digit_system: western,        font_hint: NotoSans,               tier: 1, tts_tag: pt-BR, tts_fallback_tag: pt-PT}
ru:      {name_native: Русский,            name_en: Russian,                 direction: ltr, script: Cyrl, digit_system: western,        font_hint: NotoSans,               tier: 1, tts_tag: ru-RU, tts_fallback_tag: null}
uk:      {name_native: Українська,         name_en: Ukrainian,               direction: ltr, script: Cyrl, digit_system: western,        font_hint: NotoSans,               tier: 1, tts_tag: uk-UA, tts_fallback_tag: null}
ko:      {name_native: 한국어,               name_en: Korean,                  direction: ltr, script: Kore, digit_system: western,        font_hint: null,                   tier: 1, tts_tag: ko-KR, tts_fallback_tag: null}
fr:      {name_native: Français,           name_en: French,                  direction: ltr, script: Latn, digit_system: western,        font_hint: NotoSans,               tier: 1, tts_tag: fr-FR, tts_fallback_tag: fr-CA}
prs:     {name_native: دری,                name_en: Dari,                    direction: rtl, script: Arab, digit_system: persian,        font_hint: NotoNaskhArabic,        tier: 2, tts_tag: fa-AF, tts_fallback_tag: fa-IR}
ps:      {name_native: پښتو,               name_en: Pashto,                  direction: rtl, script: Arab, digit_system: persian,        font_hint: NotoNaskhArabic,        tier: 2, tts_tag: null,  tts_fallback_tag: fa-AF}
fa:      {name_native: فارسی,              name_en: Persian (Farsi),         direction: rtl, script: Arab, digit_system: persian,        font_hint: NotoNaskhArabic,        tier: 2, tts_tag: fa-IR, tts_fallback_tag: null}
ur:      {name_native: اردو,               name_en: Urdu,                    direction: rtl, script: Arab, digit_system: persian,        font_hint: NotoNastaliqUrdu,       tier: 2, tts_tag: ur-PK, tts_fallback_tag: ur-IN}
hi:      {name_native: हिन्दी,              name_en: Hindi,                   direction: ltr, script: Deva, digit_system: western,        font_hint: NotoSansDevanagari,     tier: 2, tts_tag: hi-IN, tts_fallback_tag: null}
pa:      {name_native: ਪੰਜਾਬੀ,               name_en: Punjabi (Gurmukhi),      direction: ltr, script: Guru, digit_system: western,        font_hint: NotoSansGurmukhi,       tier: 2, tts_tag: pa-IN, tts_fallback_tag: hi-IN}
bn:      {name_native: বাংলা,               name_en: Bengali,                 direction: ltr, script: Beng, digit_system: bengali,        font_hint: NotoSansBengali,        tier: 2, tts_tag: bn-BD, tts_fallback_tag: bn-IN}
so:      {name_native: Soomaali,           name_en: Somali,                  direction: ltr, script: Latn, digit_system: western,        font_hint: NotoSans,               tier: 2, tts_tag: so-SO, tts_fallback_tag: null}
sw:      {name_native: Kiswahili,          name_en: Swahili,                 direction: ltr, script: Latn, digit_system: western,        font_hint: NotoSans,               tier: 2, tts_tag: sw-KE, tts_fallback_tag: sw-TZ}
am:      {name_native: አማርኛ,               name_en: Amharic,                 direction: ltr, script: Ethi, digit_system: western,        font_hint: NotoSansEthiopic,       tier: 2, tts_tag: am-ET, tts_fallback_tag: null}
my:      {name_native: မြန်မာ,               name_en: Burmese,                 direction: ltr, script: Mymr, digit_system: myanmar,        font_hint: NotoSansMyanmar,        tier: 2, tts_tag: my-MM, tts_fallback_tag: null}
ne:      {name_native: नेपाली,              name_en: Nepali,                  direction: ltr, script: Deva, digit_system: devanagari,     font_hint: NotoSansDevanagari,     tier: 2, tts_tag: ne-NP, tts_fallback_tag: hi-IN}
rw:      {name_native: Ikinyarwanda,       name_en: Kinyarwanda,             direction: ltr, script: Latn, digit_system: western,        font_hint: NotoSans,               tier: 2, tts_tag: null,  tts_fallback_tag: null}
rhg:     {name_native: 𐴌𐴟𐴇𐴥𐴝𐴚𐴒𐴙𐴝,          name_en: Rohingya,                direction: rtl, script: Rohg, digit_system: western,        font_hint: NotoSansHanifiRohingya, tier: 3, tts_tag: null,  tts_fallback_tag: my-MM}
```
Tier 3 entries beyond `rhg` are added by `packs/resolve.py` at runtime as `x-<slug>` tags (never written to this file). `packs/resolve.py` also matches `name_en`/`name_native` case-insensitively before calling the model. The nine `font_hint` values must equal the family names of the TTFs in `data/fonts/` (asserted by `test_keys_exist.py`).

## Appendix F — Open questions that block specific steps (and what to do meanwhile)

| Q (DECISIONS §12 / PRODUCT_SPEC §16.1) | Blocks | Meanwhile |
|---|---|---|
| Q1 billing owner / billed keys | WP1 step 6 (`gen_packs.py` for the remaining Tier 1+2 packs), `spike_schema.py`, `RecordingProvider`, `tests/live`, `eval_golden.py`, §6.10 | ship `en`+`es`+`prs`+`ar`+`ps` hand-authored; `ANALYSIS_MODE=auto` stays; live gate recorded as "not run" |
| Q2 developer accounts / legal entity | `eas.json` `submit` block values, `eas submit`, §6.9 device build (needs an Expo account) | placeholders `<…>` in `eas.json`; Android dev build deferred to Phase 2 |
| Q3 counsel review | store submission only | `STORE_LISTING.md` marks "pending counsel" |
| Q4 bundle id / web host | `app.json` `ios.bundleIdentifier`, `android.package`, `PRIVACY_POLICY_URL`, `CORS_ORIGINS` | use `org.proxyhealth.app` and `https://proxyhealth.expo.app/privacy`; both are env/config values, no code depends on them |
| Q5 pilot geography | `data/resources/regional/*.yaml` beyond `va_nova.yaml` | national + NoVA seed only; `notes.set_region_for_local_help` shown elsewhere |
| Q6/Q7 language reviewers | `reviewed_by` on any pack; `emergency.yaml` `reviewed_by` | everything `machine_translated: true`, `reviewed_by: null`; banner shown |
| Q8 per-device budget | `RATE_LIMIT_*` defaults | 20/h, 100/d as documented |
| Q9 web positioning | nothing in v1 (web is the companion surface) | session-only storage, server PDF, `.ics` |
| Q10 Interactions API | nothing (`gemini_interactions` provider is LATER) | — |
| Q11 hosting | `DEPLOYMENT.md` specifics | write for Cloud Run with a Fly.io/Render appendix |
| **Internal F-1** `docs/AI_PROMPTS.md` §4–§14 unwritten | WP2 step 2 (prompt files) and `test_prompts_match_doc.py` | WP2 writes the doc first (step 1); test is `xfail(strict=False)` until then |
| **Internal F-2** `docs/DOCUMENT_TAXONOMY.md` §4.1–§8 unwritten | WP2 `scam.yaml`, `phrasing.yaml`, per-type pitfalls; WP7 fixture expected facts | WP2 completes it in step 1; WP7 uses PRODUCT_SPEC §12.3 + Appendix D meanwhile |
| **Internal F-3** `docs/COMPLIANCE_PRIVACY.md` §5–§16 unwritten | `STORE_LISTING.md`, `DEPLOYMENT.md` | WP8 completes it in step 5; `test_privacy_claims.py` needs only §17, which exists |
| **Internal F-4** no readability package installed | `test_readability.py` exactness | heuristic in §5.9 step 4; a proper metric is LATER (install window) |
| **Internal F-5** `fake-indexeddb` not installed | automated test of the web IndexedDB adapter | manual check §6.8 |
| **Internal F-6** `CLAUDE.md` shows the old mypy invocation | nothing (agents follow §1.4) | WP8 files `CL-008` |
