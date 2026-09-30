# ProxyHealth AI — Architecture (backbone document)

Status: **authoritative**. Implements `docs/DECISIONS.md` and `docs/API_CONTRACT.md`. Every path below is relative to `/Users/sadiqmubarak/Desktop/ProxyHealth`. Files marked **(exists)** are already in the scaffold; **(replace)** are template files whose content is rewritten; **(delete)** are template files removed; everything else is new. Package installs are forbidden while agents run in parallel (CLAUDE.md rule 1); this architecture uses only the packages listed in `CLAUDE.md` and `apps/mobile/package.json`.

---

## 1. System overview

```
┌──────────────────────────── device (iOS / Android / web) ────────────────────────────┐
│ Expo Router app  ──  design system  ──  i18n (packs, RTL, fonts)  ──  TTS (expo-speech)│
│ storage: sqlite+files (native) | memory/IndexedDB (web)   reminders: notifications|.ics │
│ API client (generated types) ── offline/demo mode ── consent record ── install id       │
└───────────────┬──────────────────────────────────────────────────────────────────────┘
                │ HTTPS JSON (base64 pages) · X-Consent-Version · X-Install-Id · X-Request-Id
┌───────────────▼──────────────────────── apps/api (FastAPI, in-memory only) ───────────┐
│ ASGI, outermost first: CORS · request id + log · 500 guard · body limit                │
│ deps on gated routers: consent · tier gate · rate limit                                │
│ routers → pipelines → AIProvider (gemini | mock) via failover/keypool                  │
│ analysis safety pipeline: verify · contacts · deadlines · urgency · scam · emergency ·  │
│   phrasing · injection · redaction (Pillow) · ssn mask · disclaimers                    │
│ resources YAML → matcher · quicksheet (reportlab) · langpack cache · feedback counters  │
│ var/: keypool.json · langpacks/ · feedback_counts.sqlite   (no user content, ever)      │
└───────────────┬──────────────────────────────────────────────────────────────────────┘
                │ google-genai 2.25 · generate_content · response_schema · store-less
          Gemini API (paid project keys; gemini-3.8-flash / gemini-3.5-flash-lite)
```

Trust boundary = the device. The server holds nothing a subpoena could return.

---

## 2. `apps/api` directory tree (one-line purpose per file)

```
apps/api/
  .venv/                              (exists) Python 3.13 venv with all deps; run everything through it
  pyproject.toml                      package metadata `proxyhealth_api`, ruff/mypy/pytest config (deps already installed; no pip install)
  requirements.txt                    `.venv/bin/pip freeze` output for the Dockerfile (WP1; regenerated only in an install window)
  .env.example                        every variable in §6 with comments; committed. `.env` is git-ignored
  openapi.json                        committed OpenAPI snapshot written by scripts/export_openapi.py; CI diff-tested
  Dockerfile                          python:3.13-slim, non-root, `uvicorn proxyhealth_api.main:app --workers 1 --limit-concurrency 32 --timeout-keep-alive 5`
  proxyhealth_api/
    __init__.py                       version string
    main.py                           `create_app()` factory: settings → logging → middleware → routers → startup validators; `app = create_app()`
    settings.py                       pydantic-settings `Settings` (§6); parses GEMINI_KEYS JSON; validates model IDs (D-04), tier/billing rules (D-01), caps
    errors.py                         `ApiError(code, status, user_message_key, retry_after, key_exhausted, details)`; exception handlers → ErrorResponse; maps Pydantic/Starlette errors
    middleware.py                     request-id, X-Contract-Version/X-Data-Use-Tier headers, body-size limit (413), consent header check (428), tier gate (403), CORS setup, content-free access log
    ratelimit.py                      `limits` moving-window limiter (slowapi's engine) keyed by HMAC(install id, daily salt) and IP class (D-08)
    logging_.py                       structured JSON logger with an allow-list of fields; any other key is dropped (§7)
    deps.py                           FastAPI dependencies: settings, provider, keypool, resource repo, pack cache, fixtures
    contracts/
      __init__.py                     re-exports every public model (WP0-owned; others read only)
      enums.py                        all enums from API_CONTRACT §1 (str Enums)
      common.py                       PageInput, MaskRect, Preferences, BBox, TextBlock, PageText, TranslatedPage, ModelMeta, GeoHints, LanguageTag
      errors.py                       ErrorBody, ErrorResponse
      config.py                       HealthResponse, ServerConfig, ModelsInfo, FeatureFlags, Limits, LanguageInfo, KeySlotSummary
      langpack.py                     LanguagePack, LanguagePackRequest
      analysis.py                     AnalyzeRequest, AnalysisResult, Quality, Urgency, SummaryCard, Demand, DateInfo, AmountInfo, PlanStep, RedFlag, GlossaryTerm, Entities, ClerkMessage, VerificationSummary, Safety, PageThumbnail
      troubleshoot.py                 TroubleshootRequest, TroubleshootResult, TroubleshootStep
      chat.py                         ChatRequest, AnalysisContext, ChatMessage, ChatAnswer, Quote
      resources.py                    Resource, Serves, ResourceMatchRequest, ResourceMatch, ChecklistItem, ResourceMatchResponse, ResourceList
      rules.py                        DeadlineRule, RulesResponse
      quicksheet.py                   QuickSheetRequest, QuickSheetSection, QuickSheetResource
      feedback.py                     FeedbackRequest, FeedbackResponse
      demo.py                         DemoFixture
      admin.py                        AdminKeysResponse, KeySlotState, TierState
      model_out.py                    AnalysisModelOut, TranscriptOut, ExplainOut, DemandOut, PlanStepOut, RedFlagOut, TroubleshootModelOut, ChatModelOut, LanguagePackModelOut, KeyValue, LanguageResolveOut, RewriteOut, TaggingModelOut (API_CONTRACT §4)
    ai/
      provider.py                     `AIProvider` Protocol: `generate_structured(task, tier, parts, system, schema, thinking, media_resolution, max_output_tokens, request_id) -> StructuredResult(parsed, model_id, usage, blocked_reason, finish_reason)`; `Part` (text | bytes+mime); `Task`/`Tier` enums
      gemini.py                       `GeminiProvider`: one `genai.Client` per slot, `client.aio.models.generate_content` with GenerateContentConfig (D-05); blocked-response detection; upstream status extraction
      mock.py                         `MockProvider`: demo_sample_id → fixture; dHash match; generic fallback; canned chat; pseudo-localized packs; 300–900 ms latency (D-29)
      recording.py                    `RecordingProvider` decorator (dev only): wraps gemini, writes anonymized fixture outputs to data/fixtures/<id>/out.<lang>.json
      keypool.py                      slot state machine per tier, Retry-After/exponential cooldown, RPD detection regex, Pacific-midnight reset, `var/keypool.json` persistence, distinct-project validation (D-07)
      failover.py                     `call_with_failover(tier, build_request)`: slot selection, 3-attempt/deadline budget, 503 same-slot retry, degradation to MODEL_FAST, 429/503/422 mapping
      routing.py                      task → (tier, model id, thinking level, media resolution, max tokens); page-count-based thinking downgrade; degraded thinking config
      schema_guard.py                 import-time lint of every model_out schema: depth ≤ 3, no dict/Any/recursion, enum size (D-06)
      prompts/
        preamble.md                   common rules (information not advice, 4th-grade level, untrusted document text, no contacts, no date math, JSON only)
        analyze.md                    document analysis system prompt (single-call)
        transcribe.md                 two-call mode call 1
        explain.md                    two-call mode call 2
        troubleshoot.md               screenshot troubleshooting / scam check
        chat.md                       follow-up chat
        langpack.md                   UI-string translation
        tag.md                        resource tagging
        phrasing_rewrite.md           one-pass neutral rewrite template
        user/<task>_user.md           user-prompt templates, one per Task (analyze_user.md, transcribe_user.md, explain_user.md, troubleshoot_user.md, chat_user.md, langpack_user.md, tag_user.md, phrasing_rewrite_user.md, resolve_language_user.md)
        VERSION                       single line `prompts_version = <date>.<n>`; bumped on any prompt edit; recorded in golden `out.<lang>.json` `_meta.prompts_version` (AI_PROMPTS §1)
      prompt_loader.py                loads prompts, fills `{target_language}`, `{direction}`, `{state_or_unknown}`, `{today}`, `{tone}`, `{calendar_notes}`, `{tag_list}`, `{taxonomy_ids}` and the rest of the placeholder table in AI_PROMPTS §2; `untrusted()` wraps user-typed text
    analysis/
      pipeline.py                     `run_analysis(req, ctx)`: validate → redact → (single | two_call) → verify → contacts → deadlines → urgency → scam → emergency → phrasing → injection re-run → clerk → tags/resources → disclaimers → AnalysisResult
      uploads.py                      MIME allow-list, base64 decode, size caps, image/PDF sniffing (magic bytes), PDF page count via pypdfium2 (all in memory)
      redaction.py                    Pillow burn of MaskRect list; rotation; EXIF strip; returns JPEG bytes (never written to disk) (D-19); HEIC/HEIF that this Pillow cannot decode passes through unchanged, EXIF included, when no masks are requested (masks → 400 invalid_request); clients send JPEG (D-21; CL-030(j))
      pdf_pages.py                    pypdfium2 rasterization to PNG thumbnails ≤ 1200 px for crops
      transcript.py                   block id assignment, page dimension bookkeeping, SSN pattern masking (`***-**-1234`), optional A-number/receipt masking
      verify.py                       quote/value verification: NFKC, whitespace, dash/quote unification, OCR confusion map, difflib ≥ 0.92 sliding window; edge-crop low-confidence rule (D-09)
      contacts_filter.py              phone/URL/email/address regexes; keep only if in transcript; org-name replacement using resource DB names (D-10)
      deadline_rules.py               strict date parsing (US formats + 26 languages' month names), rules table matcher, business-day/mail-day math with zoneinfo, DateKind assignment (D-11)
      urgency.py                      level computation, doc-type floors, past-date rule, verify_resource_id selection (D-12)
      scam.py                         regex signals + model flags → ScamRisk, reasons, scam_report tag forcing (D-13)
      emergency.py                    per-language lexicon on transcript/questions; over-trigger bias (D-14)
      phrasing.py                     forbidden-phrasing lint + one FAST rewrite + fixed hedge (D-17)
      injection.py                    injection phrase detection; block masking; single re-run (D-15)
      clerk.py                        fixed template, need-line lint/cap/fallback, conditional HHS interpreter line (D-18)
      fixed_notices.py                doc-type → fixed RedFlag cards (jury, EAD receipt, not-a-court-order, …) (D-20)
      disclaimers.py                  category → DisclaimerKind + secondary disclaimers
      tagging.py                      validate model resource_tags; FAST re-tag when empty/invalid
      troubleshoot_pipeline.py        screenshot flow: contacts filter on steps, credential guard, scam scorer, quote check against screen_text, emergency lexicon over screen_text + user_goal → `TroubleshootResult.safety` (D-14)
      chat_pipeline.py                context compaction (≤ 60k chars), FAST call, grounding check of span ids against original_text, refusal templates, emergency lexicon on question
    packs/
      base.py                         loads data/langpacks/en.json, computes pack_version = sha256, key list with contexts
      resolve.py                      language query → BCP-47 tag (ISO table data/languages.yaml → FAST model → `x-<slug>`)
      generator.py                    60-key chunked FAST calls (LanguagePackModelOut), list → map merge, direction/script/digits from model + languages.yaml override
      qa.py                           placeholder equality, non-empty, length ratio, no HTML, no phone-like digit runs → fallback_keys
      cache.py                        `var/langpacks/<tag>--<pack_version>.json`, ETag, single-flight `asyncio.Lock` per tag, in-memory LRU
    resources/
      loader.py                       loads data/resources/**/*.yaml (excluding `_*.yaml`) at boot into `Resource` models; strips the YAML-only `x_meta` block, applies defaults, prefixes `warnings` with `warn.`; refuses to boot on an invalid file (prints path/line) or duplicate id; freshness is a boot *warning* (`verified_on` > 120 days) and a CI *failure* (`scripts/check_links.py --freshness`); entries > 365 days old are excluded from matching (RESOURCE_DB §8)
      matcher.py                      deterministic scoring (tags, geo, language, institution bonus, status/health penalties), crisis/scam forcing, ≤ 2 per org_type, national fallbacks (user-first §7 + builder-first §7.3)
      checklist.py                    prepare_checklist_keys + data/rules/prepare.yaml doc-type items → ChecklistItem list
      rules_repo.py                   loads data/rules/deadlines.yaml, fixed_notices.yaml, clerk_needs.yaml
    quicksheet/
      render.py                       reportlab text-only PDF, RTL shaping via embedded Noto fonts: `arabic_reshaper.reshape()` + `bidi.algorithm.get_display()` (both installed in the venv on 2026-09-27) are applied to every Arabic-script line (ar, prs, ps, ur, fa) before reportlab draws it, then `direction` right-aligned paragraphs; verified on fixtures, ≤ 200 KB
      fonts.py                        font registry mapping font_hint → data/fonts/*.ttf (`PDF_SUBSTITUTES`: Nastaliq → Naskh for the PDF)
    demo/
      fixtures.py                     loads data/fixtures/*/manifest.yaml; serves DemoFixture list and page PNGs; fixture bytes for keyed demo requests
      phash.py                        Pillow 16×16 dHash + Hamming distance
      as_of.py                        `DEMO_AS_OF = 2026-10-02`, the pinned "today" of sample papers (= every manifest's `today`): `analysis/pipeline.py` `analysis_today()` computes a sample's dates/urgency from it (demo_sample_id or dHash match), chat pins its prompt date when `demo_sample_id` is set; real papers use the real clock; changes together with en `demo.as_of_note` (PRODUCT_SPEC §12.3; CL-067(a))
    feedback/
      store.py                        sqlite counters (`var/feedback_counts.sqlite`), enum-only keys, ULID ids
    routers/
      health.py                       GET /health
      config.py                       GET /v1/config
      langpacks.py                    GET/POST /v1/language-packs
      analyze.py                      POST /v1/analyze
      troubleshoot.py                 POST /v1/troubleshoot
      chat.py                         POST /v1/chat
      resources.py                    POST /v1/resources/match, GET /v1/resources, GET /v1/resources/{id}
      rules.py                        GET /v1/rules
      quicksheet.py                   POST /v1/quicksheet/pdf
      feedback.py                     POST /v1/feedback
      demo.py                         GET /v1/demo/fixtures, GET /v1/demo/fixtures/{id}/pages/{n}
      admin.py                        GET /v1/admin/keys (mounted only when ADMIN_TOKEN set)
  data/
    langpacks/
      en.json                         CANONICAL base pack (flat keys, {placeholders}); includes "langpack.adapting": "Adapting system environment to your language..."
      es.json … rw.json               bundled Tier 1+2 packs generated by scripts/gen_packs.py; `machine_translated` flag inside each
      _contexts.json                  optional per-key translator context strings (fed to the langpack prompt)
    languages.yaml                    tag → names, direction, script, digit_system, font_hint, tier, tts_tag, tts_fallback_tag (served in /v1/config; synced to mobile)
    resources/
      national_immigration.yaml       ImmigrationLawHelp, EOIR lists, USCIS contact/scams, DHS OIG, FTC, ASAP, Afghan/ORR …
      national_health.yaml            HealthCare.gov, Medicaid finder, InsureKidsNow, Dollar For, 501(r), No Surprises, Medicare appeals, MedlinePlus, CDC IIS, HHS OCR LEP (status_note_key hhs_funded_health) …
      national_benefits_food.yaml     211, SNAP directory, WIC, school meals, Feeding America, USA.gov Benefit Finder, SSA appeals/scams, LIHEAP …
      national_housing.yaml           HUD counselors, PHA contacts, USA.gov housing, LSC eviction DB (staff reference), LawHelp/LSC (lsc_restricted) …
      national_crisis.yaml            988, DV hotline, Poison Control, Trafficking hotline
      national_school_work_tax.yaml   NCHE, Plyler explainer, PTI centers, DOL WHD, EEOC, OSHA, IRS notices/ITIN, US Courts jury (warnings: never check citizen / never register to vote)
      regional/va_nova.yaml           Inova FA, Fairfax CHCN, Neighborhood Health, LAJC, Ayuda, Just Neighbors, Tahirih, CAFB, NVFS, Fairfax CSP, VA courts/sheriff eviction pages, VA eviction self-help (`va_eviction_helpline`: phone withheld until a human verifies it; `status_note_key: manual_verify`)
      _meta.yaml                      resource_db_version, checklist vocabulary, why/notes templates, warning-key registry, doc_type_pins, urgent_doc_boost, well_known_ids (RESOURCE_DB §4)
    rules/
      deadlines.yaml                  12 seeded rules with source_url/source_verified_on/verification/valid_until (D-11; no eviction periods)
      prepare.yaml                    doc_type → extra checklist items (e.g. uscis_rfe → "the RFE notice itself on top of your response")
      fixed_notices.yaml              doc_type → fixed RedFlag cards (D-20)
      clerk_needs.yaml                doc_type → fallback English need line
    safety/
      phrasing.yaml                   forbidden patterns per language + rewrite templates
      emergency.yaml                  keyword lists per language with reviewed_by
      scam.yaml                       regex signals + reason keys + fixed copy keys
      injection.yaml                  injection phrases
    fixtures/
      <fixture_id>/manifest.yaml      id, title_en, document_type, category, language_of_document, pages, expected facts (for precision/recall), kind
      <fixture_id>/page-1.png …       synthetic pages watermarked SAMPLE (thumbnail served by /v1/demo)
      <fixture_id>/transcript.txt     canonical transcript used by the mock provider
      <fixture_id>/out.<lang>.json    expected AnalysisModelOut (TroubleshootModelOut for the screenshot) per target language: `out.en.json` for every fixture; `out.es.json`, `out.prs.json`, `out.ar.json` only for the eight demo fixtures listed in BUILD_PLAN §4.5
      (17 fixtures: medicaid_address_confirmation, uscis_i797c_receipt_i765, uscis_rfe_87d, nta_hearing_date, inova_final_notice, insurance_denial_180d, prescription_label, school_immunization_notice, va_pay_or_quit_14d, snap_interview_notice, irs_cp_notice, jury_summons, scam_gift_card_letter, blurry_unreadable_page, spanish_lease, w2_form, traffic_court_notice; plus screenshot portal_file_too_large)
    fonts/                            (exists) static Noto TTFs, Regular + Bold, for the nine `font_hint` families + OFL.txt, used by reportlab; same files as mobile assets/fonts (DECISIONS §14: subsetting is LATER)
  scripts/
    export_openapi.py                 writes openapi.json deterministically from create_app()
    gen_packs.py                      generates/refreshes bundled packs with MODEL_FAST (requires keys; run by one agent, never in CI)
    sync_to_mobile.py                 copies data/langpacks/*.json, languages.yaml, fixture thumbnails + manifest into apps/mobile (CI verifies equality)
    check_links.py                    weekly link-health checker (browser UA; 403 → unknown_403; JS → js_rendered; Cloudflare → unverified; 404/410 → broken)
    eval_golden.py                    live golden evaluation (RUN_LIVE=1): precision/recall, invented-contact count
    spike_schema.py                   day-0 structured-output spike against MODEL_PRO for single vs two_call (D-06)
    make_fixtures.py                  renders synthetic fixture pages from text templates with Pillow (SAMPLE watermark)
    smoke.py                          used by scripts/smoke.sh: posts fixtures to every endpoint against a running mock API
  tests/
    conftest.py                       app fixture with AI_PROVIDER=mock, tmp VAR_DIR, frozen clock
    unit/                             test_keypool.py test_failover.py test_routing.py test_gemini_timeout_unit.py test_logging_allowlist.py test_schema_guard.py test_keys_exist.py test_prompts_match_doc.py test_verify.py test_contacts_filter.py test_deadline_rules.py test_urgency.py test_scam.py test_emergency.py test_phrasing.py test_injection.py test_clerk.py test_redaction.py test_uploads.py test_packs_qa.py test_packs_cache.py test_resolve.py test_matcher.py test_loader.py test_checklist.py test_quicksheet.py test_feedback_store.py test_privacy_claims.py test_readability.py (owner per §4 "Test ownership")
    contract/                         test_openapi_snapshot.py test_health.py test_config.py test_langpacks.py test_analyze.py test_troubleshoot.py test_chat.py test_resources.py test_rules.py test_quicksheet_pdf.py test_feedback.py test_demo.py test_admin.py test_errors.py (error envelope, MIME/size rejections, 428, 403 gate, 429 shape)
    golden/                           test_fixtures_golden.py (mock output == out.<lang>.json; every validator passes; urgency/date kinds asserted)
    live/                             test_live_gemini.py (skipped unless RUN_LIVE=1 and keys)
  var/                                git-ignored runtime state: keypool.json, langpacks/, feedback_counts.sqlite (no user content)
```

### 2.1 API internals, module by module

**App factory (`main.py`).** `create_app(settings: Settings | None = None)` builds the FastAPI app with `title="ProxyHealth AI API"`, `version`, `openapi_url="/openapi.json"`, registers exception handlers (`errors.py`), pure-ASGI middleware in order, outermost first: CORS → request context (request id, `X-Contract-Version`/`X-Data-Use-Tier` headers, optional `X-App-Token` check — only CORS preflight `OPTIONS` is exempt — and the content-free access log) → unhandled-error guard (any unexpected exception becomes the content-free `500 internal` envelope) → body limit (`413` from a declared `Content-Length` before reading; a body without `Content-Length` is buffered up to `MAX_REQUEST_BYTES` and answered `413` the moment it passes the cap). CORS is outermost so the 401/413/500 envelopes written by inner layers still carry CORS headers (CL-023). The consent check, tier gate and rate limit are FastAPI dependencies on the gated routers, not middleware (BUILD_PLAN §4.1); mounts routers; on startup: `settings.validate_runtime()` (model IDs, keys/tier, caps), `resources.loader.load()`, `rules_repo.load()`, `packs.base.load()`, `demo.fixtures.load()`, `keypool.restore()`; `/openapi.json` includes `ErrorResponse` for every error status.

**Settings (`settings.py`).** `class Settings(BaseSettings)` with `model_config = SettingsConfigDict(env_file=(<apps/api/.env anchored on settings.py>, ".env"), extra="forbid", hide_input_in_errors=True)` — repo-root commands (`uvicorn --app-dir apps/api`, `scripts/gen_packs.py`) read `apps/api/.env`, the current directory's `.env` wins on conflicts, and a malformed secret is never echoed in a validation error (`KeySlotConfig` also sets `hide_input_in_errors`); `GEMINI_KEYS` is `NoDecode` and parsed by a before-validator (blank → `[]`; a JSON error reports only its position) — CL-054(a); `GEMINI_KEYS: list[KeySlotConfig]` parsed from JSON (`KeySlotConfig{key: SecretStr, project: str, billing: bool}`); validators: distinct projects; forbidden model patterns; `ALLOW_UNPAID_REAL_DOCUMENTS` only when `ENV != production`; `data_use_tier` property; `features` property (`real_documents_allowed = provider==mock or tier==paid or ALLOW_UNPAID_REAL_DOCUMENTS`). Secrets never appear in `repr`/logs.

**Provider Protocol and implementations (`ai/`).** `AIProvider.generate_structured` returns `StructuredResult{parsed: BaseModel | None, raw_text: str | None, model_id, usage: Usage{input_tokens, output_tokens, thought_tokens}, blocked_reason: str | None, finish_reason: str | None, incomplete: bool}`. `GeminiProvider.__init__(slots)` builds one `genai.Client(api_key=slot.key, http_options=HttpOptions(retry_options=HttpRetryOptions(attempts=2, initial_delay=1.0, max_delay=4.0), timeout=UPSTREAM_TIMEOUT_MS))` per slot (timeout unit verified in `tests/unit/test_gemini_timeout_unit.py` by inspecting the field docstring at import time). `generate_structured(slot_index, ...)` assembles `contents=[system text? no — system goes in config], [prompt_text, *media_parts]` (text before media), `GenerateContentConfig(system_instruction=..., response_mime_type="application/json", response_schema=schema, thinking_config=ThinkingConfig(thinking_level=..., include_thoughts=False), media_resolution=..., max_output_tokens=...)`, inspects `resp.prompt_feedback.block_reason` and `resp.candidates[0].finish_reason` (blocked/`MAX_TOKENS` → `incomplete=True`), and returns `resp.parsed`. `MockProvider` implements the same Protocol from fixtures. Only `failover.call_with_failover` chooses slots; pipelines never touch the keypool.

**Key pool / failover state machine.** See D-07. `keypool.acquire(tier) -> Slot | None` (LRU healthy, billed first), `keypool.report(slot, tier, outcome, retry_after, error_text)`, `keypool.snapshot()` (admin), `keypool.persist()` to `var/keypool.json` after each transition (atomic write). `failover.call_with_failover(tier, build_request, deadline_s)`: loop ≤ 3 slots within deadline; on `StructuredResult.blocked_reason` raise `ApiError(422 content_blocked)` immediately; on `incomplete` in `single` mode raise `SchemaFallbackNeeded` (pipeline switches to `two_call`); when no slot is available and `tier==pro` and `ALLOW_DEGRADED`, run once on fast with `MODEL_PRO_DEGRADED_THINKING` and mark degraded; else `ApiError(429 quota_exhausted, key_exhausted=True, retry_after=min cooldown)`.

**Tier routing (`ai/routing.py`).** `route(task, pages) -> RouteConfig{tier, model_id, thinking, media_resolution, max_output_tokens}` from the table in D-04; enforces "never minimal on gemini-3.8*"; page-count downgrade.

**Structured output.** Pydantic classes passed as `response_schema`; `schema_guard.assert_subset_safe(model)` runs at import for every class in `model_out.py`; `ANALYSIS_MODE` auto/single/two_call as in D-06.

**Retries/timeouts.** SDK retry 2 attempts; failover ≤ 3 slots; `FAILOVER_DEADLINE_S=100`; uvicorn/Cloud Run request timeout 120 s; client 120 s.

**Response block detection (`ai/gemini.py`).** `blocked_reason` from `prompt_feedback.block_reason` or candidate `finish_reason ∈ {SAFETY, RECITATION, PROHIBITED_CONTENT, SPII, BLOCKLIST}` or empty candidates → 422 with `details.block_reason` lower-cased; never retried on another slot.

**Language-pack cache (`packs/cache.py`).** Path `var/langpacks/<tag>--<pack_version>.json`; `ETag` = `LanguagePack.etag` = sha256 of the canonical JSON of `{language_tag, pack_version, strings}` (sorted keys, compact separators, UTF-8; AI_PROMPTS §7.7 — CL-054(c)); in-memory LRU(256); single-flight lock per tag; `GET` serves bundled files from `data/langpacks/` first; `LANGPACK_CACHE_TTL_DAYS` (default 180) prunes stale generated packs.

**Resource DB (`resources/`).** YAML → `Resource` models at boot; `matcher.match(req, repo, meta, today) -> ResourceMatchResponse` is deterministic and fully specified in `docs/RESOURCE_DB.md` §6: `score = 2·Jaccard(tags) + 1 (primary tag) + geo (1.0 county/zip3 · 0.9 state-only-known · 0.7 state · 0.5 national) + language (1.0 / 0.9 same family / 0.8) + institution 0.5 + priority/100 + pin 0.5 + urgent-doc boost 0.5 − penalties (lsc_restricted −0.2 shown not hidden, manual_verify −0.2, unknown_403/js_rendered −0.1, unverified −0.3, stale > 120 d −0.3)`; forced ordering for crisis/scam; diversity cap ≤ 2 per `org_type`; `national_fallbacks` always appended. Scores order results only; tests assert order.

**Quick sheet (`quicksheet/render.py`).** reportlab `SimpleDocTemplate`, registered Noto TTF per `font_hint` from `data/fonts/`; every Arabic-script line (`ar`, `prs`, `ps`, `ur`, `fa`) is shaped with `arabic_reshaper.reshape()` then `bidi.algorithm.get_display()` before reportlab draws it (both packages installed 2026-09-27, DECISIONS §14); right-aligned paragraphs for `rtl`, English section headers under localized ones (for the clerk), resource phones only after re-validation against the DB (RESOURCE_DB §7), footer disclaimer; returns bytes ≤ ~200 KB. Urdu is drawn with Noto Naskh Arabic in the PDF (`fonts.PDF_SUBSTITUTES`: reportlab has no OpenType GSUB, so Arabic script is pre-shaped into Presentation Forms, which the Nastaliq TTF does not map); a missing or wrong `font_hint` on Arabic-script text also falls back to Naskh (`languages.yaml` + a glyph-coverage guard); the app UI keeps Nastaliq (D-26). The resources block's "Who can help" heading is localized like the other sections, with the English `quicksheet.help` under it for the clerk: `help_heading()` takes it from a *heading carrier* the client sends (a section whose `heading_en` is the English `quicksheet.help` and whose `lines` are empty; never drawn as a section of its own — the app's `features/quicksheet/build.ts` sends one), else from the bundled pack `data/langpacks/<tag>.json` for `language_tag` (exact tag, then base subtag), else English (CL-066; supersedes CL-025(e)).

**Upload validation (`analysis/uploads.py`).** Decode base64 → sniff magic bytes → compare with declared MIME → enforce per-page and total caps → for PDF count pages with `pypdfium2.PdfDocument(bytes)`; reject mixed images+PDF; compute total inline bytes ≤ `MAX_UPSTREAM_INLINE_BYTES` before calling the provider.

**Rate limiting.** the `limits` package used directly (`MovingWindowRateLimiter` over `MemoryStorage`, the engine slowapi wraps; slowapi stays pinned but unused — CL-054(b)); keys from `ratelimit.install_hash(install_id, secret, day=None)` (the secret and day arguments are additive — CL-029(c)); limits from settings; `429 rate_limited` with `Retry-After`.

**CORS.** `CORS_ORIGINS` list (dev `http://localhost:8081`, web host); methods GET/POST; headers include `X-Consent-Version`, `X-Install-Id`, `X-Request-Id`, `X-App-Token`, `If-None-Match`; exposed headers `X-Request-Id`, `X-Data-Use-Tier`, `Retry-After`, `ETag`.

**Logging without content (`logging_.py`).** Allowed fields exactly: `ts, request_id, route, status, error_code, provider, model, tier, slot_index, quality, analysis_mode, latency_ms, input_tokens, output_tokens, thought_tokens, page_count, total_bytes, document_type, category, urgency_level, scam_risk, contacts_stripped, phrasing_rewrites, facts_total, facts_unverified, injection_suspected, target_language, detected_language, install_id_hash, client_platform, data_use_tier`. Any other key raises in tests (`test_logging_allowlist`). uvicorn access log disabled. Backstops (CL-029(a)): `configure_logging` adds `ContentFreeFilter` (drops `exc_info`/`stack_info`) to the `uvicorn` and `uvicorn.error` loggers and `DropAllFilter` to `uvicorn.access`/`uvicorn.asgi` (filters, because uvicorn's own `dictConfig` resets `disabled`); plain stdlib records from `proxyhealth.*` print as `{"ts","route"}` — while an app is serving (`logging_.serving()`, entered by the lifespan) only the message template with numeric args, cut to 120 chars; at boot the full message, cut to 1000 chars. The unhandled-error middleware never re-raises, so uvicorn has no traceback to print and the access log records the real `500`. Retention 30 days at the host; process log 7 days.

**Tests layout.** `unit/` pure functions; `contract/` `httpx.AsyncClient` against `create_app()` with mock provider; `golden/` fixtures × languages through the whole pipeline with `MockProvider`; `live/` gated. `apps/api/.venv/bin/pytest apps/api` runs all but live.

---

## 3. `apps/mobile` directory tree

```
apps/mobile/
  app.json                            (replace) name "ProxyHealth AI", slug/scheme "proxyhealth", ids, plugins, permissions, privacy manifests (§5.3)
  eas.json                            development / preview / production profiles + submit config (§5.3)
  package.json                        (exists) scripts: add "gen:types": "openapi-typescript ../api/openapi.json -o src/api/schema.d.ts"; keep the rest
  tsconfig.json                       (exists) unchanged (@/* → src/*, types: ["jest"])
  AGENTS.md / CLAUDE.md               (exists) Expo agent rules
  assets/
    images/icon.png, splash-icon.png, favicon.png, android-icon-*.png   (exists) replaced with ProxyHealth artwork by WP8 (same file names)
    images/expo-*.png, react-logo*.png, logo-glow.png, tutorial-web.png, tabIcons/   (delete) template artwork
    expo.icon                          (exists) iOS icon composer file; replaced by WP8
    fonts/NotoSans-*.ttf NotoNaskhArabic-*.ttf NotoNastaliqUrdu-*.ttf NotoSansEthiopic-*.ttf NotoSansMyanmar-*.ttf NotoSansDevanagari-*.ttf NotoSansBengali-*.ttf NotoSansGurmukhi-*.ttf NotoSansHanifiRohingya-*.ttf OFL.txt   (exists) static Regular + Bold TTFs mirrored from apps/api/data/fonts by sync_to_mobile.py; loaded with expo-font (subsetting LATER)
    fixtures/manifest.json, <id>.png, <id>.result.<lang>.json   synced by sync_to_mobile.py (WP7): thumbnails ≤ 600 px for the offline sample list and full `AnalysisResult`/`TroubleshootResult` JSON per fixture × recorded language for offline sample mode (`api/offline.ts`)
    resources/national_fallbacks.json  synced by sync_to_mobile.py (WP7): `list[Resource]` for `_meta.yaml.well_known_ids.offline_subset` (English-only text) — the bundled resource seed the Help tab shows offline
  locales/<tag>.json                   synced by sync_to_mobile.py (WP7): permission-string translations (`perm.*` pack keys) referenced by `app.json` `locales` — keys are the iOS Info.plist names `NSCameraUsageDescription` (`perm.camera`) and `NSPhotoLibraryUsageDescription` (`perm.photos`); `perm.notifications` is carried as the inert key `perm_notifications` (iOS needs no usage string for notifications); a file is written only for packs that carry every `perm.*` key (CL-015)
  public/privacy/index.html            (WP8) the public privacy policy served at `/privacy` on the web host (`PRIVACY_POLICY_URL`); copied into `dist/` by `expo export`
  src/
    app/                               Expo Router routes ONLY (no non-route code)
      _layout.tsx                      (replace) root Stack + providers (ThemeProvider, I18nProvider, DirectionProvider, ApiConfigProvider, StorageProvider, SplashScreen gate); Stack.Screen for (tabs) and modal groups
      index.tsx                        (replace) redirect: no language → /onboarding/language; no consent decision → /onboarding/consent; else /(tabs)
      explore.tsx                      (delete)
      +not-found.tsx                   S18 friendly error: "Go home", "Report a problem"
      +html.tsx                        web HTML shell: lang/dir attributes, PWA manifest link, viewport, noscript
      onboarding/
        language.tsx                   S1 language grid (native names first, device-locale preselect, "My language is not here" box, Aa toggle)
        adapting.tsx                   S1b "Adapting system environment to your language..." progress (three labelled steps, English fallback, cancel)
        consent.tsx                    S2 consent with tier badge, 18+ line, Continue / Not now / Try a sample first
      (tabs)/
        _layout.tsx                    JS `Tabs` from expo-router (D-27): Home · My papers · Get help · Settings; 64 pt bar; icon + word; RTL via useDirection
        index.tsx                      S3 Home: 72 pt "Take a photo of a paper", tiles, next-date card, demo banner, offline line
        papers.tsx                     S12 family vault: member chips, document rows, search, Add member
        help.tsx                       S11 Action Hub without a document: need tiles, region control, resource list
        settings.tsx                   S17 settings (language, text size, voice, high contrast, lock-screen detail, PIN lock (SHOULD), data handling, sample mode, delete everything, about)
      scan/
        capture.tsx                    S4 camera (expo-camera) with page guide/torch/thumbnails; web: picker inside the click handler
        review.tsx                     S5 page review: retake/rotate/remove/reorder, Hide parts (masks), member selector, "Read this paper"
        reading.tsx                    S6 honest waiting: three steps, trust line, cancel, error states (429/503/422/unreadable)
      result/[id]/
        index.tsx                      S7 result: emergency card, urgency banner, disclaimer header, three cards, details & quotes, glossary, red flags, help preview, footer, action bar
        source.tsx                     S8 side-by-side original/translation with tappable highlight boxes
        chat.tsx                       S9 grounded follow-up chat
        clerk.tsx                      S10 hand-the-phone clerk card (LTR, high contrast, `clerk.brightness_tip` line — expo-brightness is not installed, long-press exit); the reserved id `generic` renders the no-analysis card from PRODUCT_SPEC §8.4 (no separate route)
        quicksheet.tsx                 S15 quick sheet preview + share/print/copy/read aloud
        help.tsx                       S11 Action Hub for this document
      troubleshoot.tsx                 S16 Stuck on a website? / Is this a scam? (mode chips)
      reminders.tsx                    S14 reminders list, add my own date, web .ics path
      papers/member/[id].tsx           member detail: documents, move, wipe member
      emergency.tsx                    fixed emergency card (modal presentation)
    api/
      schema.d.ts                      GENERATED from ../api/openapi.json (WP0); never hand-edited
      types.ts                         convenience aliases: `type AnalysisResult = components["schemas"]["AnalysisResult"]` etc.
      client.ts                        typed fetch wrapper: base URL, headers (X-Request-Id, X-Install-Id, X-Consent-Version, X-App-Token), timeouts, ErrorResponse parsing → `ApiError`, 304 handling, retry-after
      errors.ts                        `ApiError` class; code → user_message_key mapping; `isQuotaExhausted()`, `isConsentRequired()`
      config.ts                        `useServerConfig()` (fetch, cache in AsyncStorage, `tier: 'unknown'` when unreachable)
      offline.ts                       offline/demo mode: serves fixtures from assets when the API is unreachable and the user chose sample mode; never fakes real analyses
    design/
      tokens.ts                        "Big Calm" tokens (D-28): type scale (base 18), sizes (56/72/44), spacing, radii, palettes light/dark/high-contrast (7:1 body), urgency colors+icons+words
      theme.tsx                        ThemeProvider, `useTheme()`, `useHighContrast()` (toggle OR AccessibilityInfo flags), reduce-motion
      components/
        BigButton.tsx                  56/72 pt primary/secondary buttons with icon + label, hitSlop 8
        Tile.tsx                       Home tiles with one-line explanation
        Card.tsx                       role="region" card with heading and SpeakButton slot
        SpeakButton.tsx                44×44 speaker after every paragraph; stop state
        UrgencyBanner.tsx              icon + word + color, "Verify this date" and "Remind me" CTAs
        ConfidenceChip.tsx             high/medium/low with amber "Re-scan this part"
        Bidi.tsx                       LTR isolate for verbatim values (LRI/PDI native, unicode-bidi isolate web)
        Crop.tsx                       highlighted crop from page image + bbox (expo-image), full-page fallback
        Checklist.tsx                  persistent checkboxes (state saved with the document)
        FeedbackRow.tsx                "Was this clear?" thumbs + Report (posts counts only)
        TierBadge.tsx                  paid / unpaid / demo / unknown badge (copy from pack)
        Banner.tsx                     demo / unpaid / offline / machine-translation banners
        ProgressSteps.tsx              three-step honest progress with aria-live
        EmptyState.tsx, ErrorState.tsx shared states with one primary action
        ExternalLink.tsx               (moved from components/external-link.tsx) opens resource URLs in expo-web-browser
        Collapsible.tsx                (moved from components/ui/collapsible.tsx)
    i18n/
      packs/en.json … rw.json          synced copies of apps/api/data/langpacks (CI equality check)
      languages.ts                     synced from data/languages.yaml (generated TS)
      languageNames.ts                 hand-maintained native/English names for resource-only language tags (zh, hmn, km, …) in the "Speaks: …" line; no pack, never in the S1 grid; guarded by `tests/unit/test_resource_language_names.py` (CL-067(d))
      store.ts                         zustand: active pack, direction, digit system, font hint, pack cache index
      useT.ts                          `t(key, vars)` with English fallback and one-time missing-key report (counts only)
      packLoader.ts                    bundled → device cache (AsyncStorage) → GET/POST /v1/language-packs; ETag revalidation; pack_version check
      direction.ts                     `useDirection()` → {isRTL, row, textAlign, writingDirection}; native I18nManager sync + "Restart to finish switching" prompt; web sets documentElement.dir
      digits.ts                        localized *additional* numeral line; never replaces verbatim values
      fonts.ts                         expo-font loading map from font_hint → family; line-height multipliers (Nastaliq 2.0)
      readability.md                   rule: base strings ≤ grade 5 (checked by API CI script)
    storage/
      index.ts                         `Vault` interface (members, documents, pages, checklist state, reminders, consent) + platform re-export
      vault.native.ts                  expo-sqlite implementation (WAL, migrations via PRAGMA user_version), documents JSON + page file refs
      vault.web.ts                     in-memory default; IndexedDB opt-in ("Keep on this device (not encrypted by the app)"); "clear on close"
      files.native.ts                  expo-file-system File/Directory under Paths.document/vault/<doc_id>/ (JPEG pages, thumbnails)
      files.web.ts                     Blob + URL.createObjectURL; IndexedDB blobs when opt-in
      secure.native.ts                 expo-secure-store: vault_key (WHEN_UNLOCKED_THIS_DEVICE_ONLY), PIN verifier (expo-crypto digest + salt)
      secure.web.ts                    in-memory shim; PIN lock unavailable on web
      kv.ts                            AsyncStorage wrapper for settings, consent record, install id, pack cache index, server-config cache
      migrations.ts                    schema versions for the sqlite vault
      wipe.ts                          "Delete everything": DB + files + kv + secure + consent + install id
    features/
      onboarding/                      language grid data, locale preselect, consent view-model (tier badge, record {consent_version, accepted_at, tier_seen, platform}), PrivacyNotice.tsx (the in-app `privacy.notice.*` sheet opened by `consent.read_more` and by Settings → "How your paper is handled"; links to `privacy_policy_url`)
      scan/                            useCapture (camera/picker), compress.ts (expo-image-manipulator resize 1600 px, JPEG 0.8, EXIF stripped), masks.ts (rect drawing; web canvas burn), pdfPick.ts (expo-document-picker, size/page pre-checks), pageQueue.ts, blurHint.web.ts (canvas variance; web only)
      analysis/                        useAnalyze (build AnalyzeRequest, progress, error mapping), cards/ (Summary, Demands, Plan, Details, Glossary, RedFlags), unverifiedSection.tsx ("I saw these but could not confirm…"), urgencyCopy.ts, disclaimers.ts (fixed copy keys), hearItMode.ts (auto-play cards)
      chat/                            useChat (context compaction, history ≤ 8), refusalTemplates.ts, suggestedQuestions
      clerk/                           clerk card view-model (analysis card + generic card presets), `clerk.brightness_tip` line (expo-brightness is NOT installed, so brightness is never changed and never claimed), long-press exit, vault navigation hidden flag
      help/                            resource matching hooks, need tiles, LSC note + "If that is not you" link, checklist, national fallbacks, "Verified on" chips
      vault/                           members, save flow ("Whose paper is this?"), document detail from storage, move/delete, per-member wipe
      reminders/                       schedule 7/3/1-day 9 am reminders (native), generic bodies, .ics generation (web + native "Add to calendar" via share), permission explanations
      quicksheet/                      quick-sheet text builder (from AnalysisResult + resources), html.ts (expo-print native, embedded base64 fonts, dir), serverPdf.ts (POST /v1/quicksheet/pdf on web → download)
      troubleshoot/                    screenshot pick (gesture-bound on web), mode chips, credential-guard banner, result cards
      speech/                          voice map (getAvailableVoicesAsync), closest-language fallback with honest message, sentence chunker, persistent stop
      demo/                            sample list (from /v1/demo/fixtures or bundled manifest), sample-mode banner, offline sample flow
      feedback/                        counts-only feedback client, one-time missing-key reporting
      emergency/                       fixed copy card, tel: links, trigger from AnalysisResult.safety or ChatAnswer.safety
      settings/                        text size, high contrast, voice picker, lock-screen detail toggle, PIN lock (SHOULD), sample mode, data handling text, delete everything
    lib/
      tts.ts                           expo-speech wrapper (speak/stop/isSpeaking, chunking, voice selection)
      notifications.native.ts          expo-notifications scheduling with generic bodies; channel "Dates to remember"
      notifications.web.ts             no-op + .ics download helper
      ics.ts                           RFC 5545 builder for reminders
      image.ts                         expo-image-manipulator helpers (resize/rotate/JPEG), base64 conversion (native file → base64; web File → base64)
      pdf.ts                           PDF size/page pre-check (page count from server preflight is not available → size cap only; server enforces pages)
      network.ts                       expo-network reachability, offline banner state
      ids.ts                           expo-crypto randomUUID for install id / analysis ids
      dates.ts                         days-until math, localized additional date line, never mutates verbatim
      platform.ts                      `isWeb`, gesture-bound picker helpers
    store/
      settings.ts                      zustand: language tag, text size, high contrast, voice, lock-screen detail, sample mode, region (state, zip3), preferences (tone, calendar notes, date format)
      session.ts                       zustand: current scan pages, current analysis (unsaved), consent state, server config, clerk-mode flag
    hooks/
      use-color-scheme.ts, use-color-scheme.web.ts   (exists) kept
      use-theme.ts                     (delete) replaced by design/theme.tsx
    components/                        (delete after moves) app-tabs.tsx, app-tabs.web.tsx, animated-icon.tsx, animated-icon.web.tsx, animated-icon.module.css, hint-row.tsx, web-badge.tsx, themed-text.tsx, themed-view.tsx; external-link.tsx and ui/collapsible.tsx move to design/components
    constants/theme.ts                 (delete) replaced by design/tokens.ts
    global.css                         (exists) minimal web resets; add `:root[dir=rtl]` helpers
    __tests__/
      smoke.test.tsx                   (exists) updated to render the new Home
      i18n.test.ts                     t() fallback, placeholders, direction switch, digits additional line
      bidi.test.tsx                    Bidi isolation
      storage.native.test.ts / storage.web.test.ts   vault adapters (jest-expo/universal)
      result-cards.test.tsx            cards from the RFE golden JSON, LTR + RTL, 200% font scale
      urgency-banner.test.tsx          icon + word + color per level
      reminders.test.ts                schedule math, generic body, .ics output
      quicksheet.test.ts               text builder excludes stripped contacts; html has dir + fonts
      api-client.test.ts               error mapping, 428/403/429 handling, headers
      consent.test.tsx                 tier badge copy per tier; Not now path; record shape
```

### 3.1 Mobile internals

**Route tree (Expo Router).** Root `Stack` (`_layout.tsx`) → `(tabs)` group (JS `Tabs`) → stack screens `scan/*`, `result/[id]/*`, `troubleshoot`, `reminders`, `papers/member/[id]`, `emergency` (presentation `modal`), `onboarding/*` (shown before tabs when no language/consent decision exists). Typed routes stay on (`experiments.typedRoutes`), so `expo-env.d.ts` must exist before `tsc` (run `npx expo customize tsconfig.json` in CI). Clerk mode sets `session.clerkMode=true`, which hides the tab bar and the vault routes until the 1.5 s long-press.

**Design tokens / theme.** `tokens.ts` exports `type`, `size`, `space`, `radius`, `palette.{light,dark,highContrast}`, `urgency.{emergency,critical,high,medium,info}` (each `{color, icon, wordKey}`). `theme.tsx` composes `useColorScheme()` + high-contrast detection + settings override; `allowFontScaling` stays on; `maxFontSizeMultiplier={2}` only in `(tabs)/_layout.tsx` labels.

**i18n runtime.** `I18nProvider` loads the device-locale pack (bundled) synchronously from `packs/`, then the active pack from cache/server; `t()` reads from the zustand store; `useDirection()` derives from `pack.direction`; switching a language: (1) load pack, (2) set direction (immediate via row-reverse), (3) on native, if `I18nManager.isRTL !== isRTL` call `allowRTL/forceRTL` and show the restart prompt, (4) on web set `document.documentElement.dir` and `lang`. Machine-translated packs show the banner and small source-language lines for Tier 3.

**API client.** `client.ts` wraps `fetch` with `AbortController` timeouts per endpoint, adds headers from `kv` (install id) and `session` (consent version), parses `ErrorResponse` into `ApiError`, and exposes typed functions `getConfig`, `getPack`, `postPack`, `analyze`, `troubleshoot`, `chat`, `matchResources`, `listResources`, `quicksheetPdf`, `feedback`, `listFixtures`. Demo mode: `demo_sample_id` set on requests; if the API is unreachable, `offline.ts` serves bundled sample results (`assets/fixtures`) for sample papers only and shows the sample-mode banner; real scans are never faked.

**Storage layer.** Interface `Vault` in `storage/index.ts`; Metro resolves `.native.ts`/`.web.ts` automatically. Native: sqlite tables `members(id, name, color, created_at)`, `documents(id, member_id, title, category, document_type, analysis_json, created_at, next_date_iso, keep_pages)`, `pages(document_id, page, file_path, thumb_path)`, `checklist_state(document_id, step_id, checked)`, `reminders(id, document_id, demand_id, fire_at, notification_id, detail_opt_in)`, `meta(key, value)` (schema version; chat history per document as `chat:<doc_id>`); files under `Paths.document/vault/<doc_id>/`. There is **no** `consent` table: the consent record `{consent_version, accepted_at, tier_seen, platform}` lives in `kv` (AsyncStorage) so it exists before the vault does and works on web; `Vault.consent` in BUILD_PLAN §4.2 is a thin wrapper over `kv` (D-22). Web: memory Map by default; IndexedDB (`proxyhealth` DB, object stores mirroring the tables) when opted in; `clearOnClose` via `pagehide`. Secrets: `secure.native.ts` only; web has none.

**TTS wrapper.** `lib/tts.ts` builds the voice map once, chooses `Enhanced` voices, chunks by sentence under `Speech.maxSpeechInputLength`, exposes `speak(text, lang)`, `stop()`, `useSpeaking()`; `features/speech/fallback.ts` maps `tts_fallback_tag` and produces the honest message ("No Rohingya voice on this phone. Hear it in Burmese or English?").

**Camera / picker / document flows.** Native: `expo-camera` `CameraView` in `scan/capture.tsx`, `expo-image-picker` for the library (system picker; no full-library permission), `expo-document-picker` for PDFs (`copyToCacheDirectory: true`, read via `File(uri).base64()`), compression via `ImageManipulator.manipulate(uri).resize({width: 1600}).renderAsync()` → `saveAsync({compress: 0.8, format: JPEG, base64: true})`. Web: the picker/document picker call is the first statement inside the button's `onPress` (no awaits before), `file`/`base64` fields are used directly; camera capture via `<input type=file capture>` path of `expo-image-picker`. Masks: rectangles drawn over the thumbnail with `react-native-gesture-handler`; native sends `masks`, web burns on a `<canvas>`.

**PDF / share flows.** Native quick sheet: `Print.printToFileAsync({html})` → `Sharing.shareAsync(uri, {mimeType: 'application/pdf'})` gated by `isAvailableAsync()`; fonts embedded as base64 data URIs; fallback "Copy text". Web: `POST /v1/quicksheet/pdf` → Blob → `<a download>`; secondary "Print or save as PDF" prints the sheet HTML from a hidden same-origin `<iframe srcdoc>` (`features/quicksheet/share.ts` `printHtmlInFrame`) because expo-print 57's web `Print.printAsync` ignores `html` and calls `window.print()` on the whole app page; `Print.printAsync` is only the fallback when no DOM is available (CL-040). Clipboard via `expo-clipboard` (called synchronously in the click handler on web).

**Reminders.** Native: `expo-notifications` local scheduling at 9:00 local time 7/3/1 days before each `reminder_eligible` demand; body "You have a date coming up" unless the user opts into detail; Android channel "Dates to remember"; permission explanation screen; in-app reminder list works without permission. Web: no scheduled notifications; `.ics` download (single VEVENT per reminder, `SUMMARY` generic unless opted in) and "Add to calendar" copy; the same `.ics` is offered on native via the share sheet (no `expo-calendar` in the scaffold).

**Offline behaviors.** Capture works offline ("No internet. I can take the photo now and read it later." → queued in `session` until connectivity, SHOULD: persistent queue; today the queue is memory-only and nothing drains it on reconnect — code request in CL-064); vault, quick sheets, reminders, bundled packs and bundled resource seed (synced JSON subset for national fallbacks) work offline; scan/chat/troubleshoot buttons show the offline state; Help shows cached last results per document plus national fallbacks.

**Accessibility conventions.** Every control: `role`, `accessibilityLabel`, `accessibilityHint`; cards `role="region"` + heading; live regions for progress/results ("Reading finished. Two dates found."); per-pane `accessibilityLanguage`/`lang`; 56/72 pt targets + `hitSlop`; focus order = reading order; no emoji in labels; icons for real objects not mirrored; tested at 200% font scale, LTR and RTL, VoiceOver/TalkBack.

---

## 4. Ownership map (exclusive write scopes; expands into `docs/BUILD_PLAN.md`)

| WP | Owner scope (exclusive write) | Reads | Definition of done |
|---|---|---|---|
| **WP0 Contract & tokens** (first) | `apps/api/proxyhealth_api/contracts/**`, `apps/api/openapi.json`, `apps/api/scripts/export_openapi.py`, `apps/api/tests/conftest.py`, `apps/api/tests/contract/test_openapi_snapshot.py`, `apps/api/tests/unit/{test_schema_guard,test_keys_exist}.py`, `apps/mobile/src/api/schema.d.ts`, `apps/mobile/src/api/types.ts`, `apps/mobile/src/design/tokens.ts`, `apps/mobile/package.json` (scripts only), `apps/mobile/tsconfig.json`, `apps/mobile/eslint.config.js`, `apps/api/data/langpacks/en.json`, `apps/api/data/langpacks/_contexts.json`, `apps/api/data/languages.yaml`, `apps/api/proxyhealth_api/ai/provider.py`, `apps/api/proxyhealth_api/ai/mock.py` (hour-one single fixture), `docs/API_CONTRACT.md`; day-0 skeletons handed off at M0 (BUILD_PLAN §5.0) | DECISIONS | `export_openapi.py` runs; `npm run gen:types` produces types; `tests/contract/test_openapi_snapshot.py` passes; `schema_guard` passes; MockProvider returns a valid `AnalysisModelOut` for any input |
| **WP1 API core + AI** | `main.py settings.py errors.py middleware.py ratelimit.py logging_.py deps.py __init__.py`, `ai/**` except `provider.py`, `mock.py`, `recording.py`, `prompts/**`, `prompt_loader.py`; `packs/**`, `routers/{health,config,langpacks,admin}.py`, `Dockerfile`, `requirements.txt`, `.env.example`, `pyproject.toml`, `scripts/{gen_packs,spike_schema}.py`, `data/langpacks/<tag>.json` for tags ≠ `en` | contracts | keypool tests (429 rotation, Retry-After, RPD detection, persistence, distinct projects); tier gate 403 + consent 428 tests; `/health`, `/v1/config` correct per tier; langpack cache/ETag tests |
| **WP2 Analysis pipelines + safety** | `analysis/**`, `routers/{analyze,troubleshoot,chat}.py`, `data/rules/**` **except `prepare.yaml`**, `data/safety/**`, `ai/prompts/**`, `ai/prompt_loader.py`, `scripts/eval_golden.py`, `tests/live/**`, `docs/AI_PROMPTS.md`, `docs/DOCUMENT_TAXONOMY.md` | contracts, `ai/provider.py` | validator unit tests; pipeline tests against mock; urgency/deadline/scam/emergency/phrasing/injection/redaction tests |
| **WP3 Resources & quick sheet** | `resources/**`, `quicksheet/**`, `routers/{resources,rules,quicksheet}.py`, `data/resources/**`, `data/rules/prepare.yaml` (its keys must exist in `data/resources/_meta.yaml.checklist`), `data/fonts/**`, `scripts/check_links.py`, `docs/RESOURCE_DB.md` | contracts | YAML validates at boot; ≥ 70 entries with verified URLs; matcher tests; PDF renders RTL fixtures |
| **WP4 Mobile foundation** | `src/app/{_layout,index,+not-found,+html}.tsx`, `src/app/(tabs)/_layout.tsx`, `src/app/onboarding/**`, `src/app/(tabs)/settings.tsx`, `src/design/theme.tsx`, `src/design/components/**`, `src/i18n/**` (except generated `packs/*.json` and `languages.ts`), `src/storage/**`, `src/api/{client,errors,config,offline}.ts`, `src/lib/{network,ids,platform,tts}.ts`, `src/store/**`, `src/features/onboarding/**`, `src/hooks/**`, `src/global.css`, `app.json`, `eas.json`, deletions of template files | tokens, schema.d.ts, en.json | tsc + jest + lint + web export green; RTL flip on web and native; consent tier badge; storage adapter tests both platforms |
| **WP5 Scan → Result → Chat → Clerk** | `src/app/scan/**`, `src/app/result/**`, `src/app/emergency.tsx`, `src/features/{scan,analysis,chat,clerk,speech,feedback,emergency}/**`, `src/lib/{image,pdf,dates}.ts` | WP4 components/store, contracts | full flow with mock API on web + dev build; cards/Bidi/crop tests; a11y labels |
| **WP6 Vault, Help, Reminders, Quick sheet, Troubleshoot** | `src/app/(tabs)/{index,papers,help}.tsx`, `src/app/papers/**`, `src/app/reminders.tsx`, `src/app/troubleshoot.tsx`, `src/features/{vault,help,reminders,quicksheet,troubleshoot,demo,settings}/**`, `src/lib/{notifications.*,ics}.ts` | WP4, contracts | opt-in save + members + wipe; reminders native + .ics web; quick sheet share/print/server PDF; troubleshoot modes |
| **WP7 Fixtures, mock, demo** | `data/fixtures/**`, `scripts/{make_fixtures,sync_to_mobile}.py`, `ai/mock.py` (after hour one), `ai/recording.py`, `demo/**`, `routers/demo.py`, `feedback/**`, `routers/feedback.py`, `tests/golden/**`, generated mobile copies `apps/mobile/assets/fixtures/**`, `apps/mobile/assets/resources/**`, `apps/mobile/locales/**`, `apps/mobile/src/i18n/packs/*.json`, `apps/mobile/src/i18n/languages.ts` (written only by `sync_to_mobile.py`), `docs/DEMO_SCRIPT.md` | contracts, validators | 17 fixtures + 1 screenshot with `out.en.json`, plus `es`/`prs`/`ar` outputs for the eight demo fixtures (BUILD_PLAN §4.5); goldens pass validators; dHash match works; demo runs offline; `sync_to_mobile.py --check` green |
| **WP8 DevOps, CI, store** | `Makefile`, `scripts/{dev,smoke,gen-types,ci}.sh`, `apps/api/scripts/smoke.py`, `.github/workflows/ci.yml`, `.gitignore` (`var/`, `.env`, `dist/`), `README.md`, `apps/mobile/assets/images/**`, `apps/mobile/assets/expo.icon`, `apps/mobile/public/**` (privacy policy HTML), `apps/api/tests/unit/{test_privacy_claims,test_readability}.py`, `docs/{DEPLOYMENT,RUNBOOK,STORE_LISTING,COMPLIANCE_PRIVACY}.md` | everything | `make dev` boots API + web; CI runs pytest, tsc, jest, lint, contract diff, YAML validation, pack sync check, privacy claims, readability, web export; privacy policy served at `/privacy` |

**Test ownership** (BUILD_PLAN Appendix B mirrors this; until that appendix exists this row is the rule): a test file belongs to the package that owns the module it exercises. API `tests/unit/test_<module>.py` → owner of `<module>` (keypool/failover/routing/gemini_timeout_unit/logging_allowlist/packs_qa/packs_cache/resolve → WP1; schema_guard/keys_exist → WP0; prompts_match_doc/verify/contacts_filter/deadline_rules/urgency/scam/emergency/phrasing/injection/clerk/redaction/uploads → WP2; matcher/loader/checklist/quicksheet → WP3; feedback_store → WP7; privacy_claims/readability → WP8). `tests/contract/test_<router>.py` → owner of the router (health/config/langpacks/admin/errors → WP1; analyze/troubleshoot/chat → WP2; resources/rules/quicksheet_pdf → WP3; demo/feedback → WP7; openapi_snapshot → WP0). `tests/golden/**` → WP7; `tests/live/**` → WP2; `tests/conftest.py` → WP0 (WP-specific fixtures go in that WP's own modules, never a new `conftest.py`). Mobile `src/__tests__/`: smoke, i18n, bidi, storage.*, api-client, consent → WP4; result-cards, urgency-banner → WP5; reminders, quicksheet → WP6.

Files not named in any scope are unowned: an agent that needs one files a change-log line first (BUILD_PLAN §1.2). Cross-WP needs are filed as one line in `docs/DECISIONS.md` §14 "Change log" (append-only) and resolved by WP0.

---

## 5. Dev scripts, CI, deployment

### 5.1 One-command development

```
Makefile (repo root)
  make dev      → scripts/dev.sh: export PATH="$HOME/.local/node/bin:$PATH"; (cd apps/api && .venv/bin/uvicorn proxyhealth_api.main:app --reload --port 8000) & (cd apps/mobile && EXPO_PUBLIC_API_URL=http://127.0.0.1:8000 npx expo start --web); trap kills both
  make types    → apps/api/.venv/bin/python apps/api/scripts/export_openapi.py && (cd apps/mobile && npm run gen:types)
  make sync     → apps/api/.venv/bin/python apps/api/scripts/sync_to_mobile.py
  make test     → apps/api/.venv/bin/pytest apps/api && (cd apps/mobile && npx tsc --noEmit && npx jest && npx expo lint)
  make smoke    → scripts/smoke.sh (boots API with AI_PROVIDER=mock, runs apps/api/scripts/smoke.py against every endpoint, asserts urgency/facts/resources/no "[contact removed]")
  make export-web → cd apps/mobile && npx expo export --platform web
```
`.env` for dev: `AI_PROVIDER=mock` (default when the file is absent). Phone testing: EAS development build (`eas build --profile development --platform android` first); Expo Go only for smoke (config-plugin permission strings, notifications and RTL restart need the dev build).

### 5.2 CI (`.github/workflows/ci.yml`)

Jobs: **api** (ruff, mypy, pytest incl. contract snapshot, golden, privacy-claims and readability checks, YAML validation, `sync_to_mobile.py --check`); **mobile** (`npm ci --legacy-peer-deps`, `npx expo customize tsconfig.json`, `npx tsc --noEmit`, `npx jest`, `npx expo lint`, `npx expo export --platform web`); **links** (weekly cron: `check_links.py`, opens an issue on `broken`); **live-golden** (manual/nightly with secrets: `RUN_LIVE=1 pytest tests/live`).

### 5.3 Deployment

**API host.** Recommended: Google Cloud Run in the same Google account as the billed Gemini project (auditability of the paid-tier invariant): container from `apps/api/Dockerfile`, 1 vCPU / 1 GiB, min instances 0 (or 1 for demos), **request timeout 120 s**, concurrency 32, secrets from Secret Manager into env (`GEMINI_KEYS`, `INSTALL_HASH_SECRET`, `ADMIN_TOKEN`), no persistent disk (key-pool state is re-learned after a cold start; optional small volume for `var/`). Alternatives with the same image: Fly.io, Render. A separate **demo instance** runs `AI_PROVIDER=mock` permanently for judges. Health probe `/health`. Alert: `keys_healthy == 0` for 5 min.

**Web.** `npx expo export --platform web` (`web.output: "static"`, already set) → `dist/` → `eas deploy` on EAS Hosting (`https://proxyhealth.expo.app`; `--prod` for production; free plan 100k requests/month) or Vercel/Netlify static with the documented rewrites. `EXPO_PUBLIC_API_URL` is baked at export; the web origin is added to `CORS_ORIGINS`. No COOP/COEP headers needed (no sqlite-wasm). The privacy policy is served at `/privacy` (HTML, not PDF) from `apps/mobile/public/privacy/index.html` (WP8; `expo export` copies `public/` into `dist/`), which is what `PRIVACY_POLICY_URL` points at.

**Mobile builds (`eas.json`).**
```json
{ "cli": { "appVersionSource": "remote" },
  "build": {
    "development": { "developmentClient": true, "distribution": "internal", "env": { "EXPO_PUBLIC_API_URL": "https://<demo-or-staging-api>" } },
    "preview":     { "distribution": "internal", "env": { "EXPO_PUBLIC_API_URL": "https://<staging-api>" } },
    "production":  { "autoIncrement": true, "env": { "EXPO_PUBLIC_API_URL": "https://<prod-api>" } } },
  "submit": { "production": { "ios": { "ascAppId": "<from App Store Connect>", "appleTeamId": "<team>" },
                              "android": { "serviceAccountKeyPath": "./google-service-account.json", "track": "internal" } } } }
```
Sequence: `npx eas-cli@latest build:configure` → `eas build --profile development --platform android` (day one) → iOS dev build when the Apple organization account exists → `eas build --platform all --profile production` → `eas submit`. Free-plan budget 15 iOS + 15 Android builds/month. Plan the SDK 58 upgrade (`npx expo install expo@^58.0.0 --fix`, `File.write` async, native-tabs path irrelevant to us, iOS RTL follows I18nManager) before store submission.

**`app.json` (WP4 rewrites the template):**
- `name: "ProxyHealth AI"`, `slug: "proxyhealth"`, `scheme: "proxyhealth"`, `version: "1.0.0"`, `orientation: "portrait"`, `userInterfaceStyle: "automatic"`.
- `ios`: `bundleIdentifier: "org.proxyhealth.app"` (confirm — open question Q4), `supportsTablet: true`, `icon` (exists), `privacyManifests.NSPrivacyAccessedAPITypes`: UserDefaults `CA92.1`, FileTimestamp `C617.1`, SystemBootTime `35F9.1` (verify on first rejection), `infoPlist.NSCameraUsageDescription` / `NSPhotoLibraryUsageDescription` mirror the plugin strings.
- `android`: `package: "org.proxyhealth.app"`, `allowBackup: false`, `adaptiveIcon` (exists), `blockedPermissions: ["android.permission.READ_MEDIA_IMAGES", "android.permission.READ_MEDIA_VIDEO", "android.permission.RECORD_AUDIO"]`, `predictiveBackGestureEnabled: false` (exists).
- `web`: `output: "static"` (exists), `favicon` (exists), `name`, `themeColor`.
- `plugins` (keep existing `expo-router`, `expo-splash-screen` (new colors/image), `expo-sharing`, `expo-secure-store`, `expo-sqlite`, `expo-localization`; add):
  - `["expo-camera", {"cameraPermission": "ProxyHealth AI uses the camera only to photograph the paper you want explained. Photos are not saved on our servers.", "microphonePermission": false}]`
  - `["expo-image-picker", {"photosPermission": "ProxyHealth AI lets you choose a photo of a paper to explain. We do not access your other photos.", "cameraPermission": "ProxyHealth AI uses the camera only to photograph the paper you want explained.", "microphonePermission": false}]`
  - `["expo-localization", {"supportsRTL": true, "supportedLocales": {"ios": [all bundled tags], "android": [all bundled tags]}}]` (replaces the bare entry)
  - `["expo-notifications", {"icon": "./assets/images/notification-icon.png", "color": "#1F5F8B", "defaultChannel": "dates"}]`
  - `expo-document-picker`, `expo-font` (with the `fonts` array for the Noto files)
  - `["expo-sqlite", {"useSQLCipher": true}]` **only after** the first dev build verifies it; until then the bare `expo-sqlite` entry stays and no encryption claim is made.
- `experiments`: keep `typedRoutes: true`, `reactCompiler: true`.
- `locales`: permission-string translations for bundled languages (`./locales/<tag>.json`).

**Store permission strings (final English; packs translate):** camera and photos as above; notifications: "ProxyHealth AI reminds you about dates it found on your papers. Reminder text is generic unless you choose otherwise."

**Store metadata** lives in `docs/STORE_LISTING.md` (WP8): title "ProxyHealth AI: Your paper, explained"; category Reference/Tools; age 18+; "Medical or wellness topics" yes; Play Health apps declaration (not a medical device; consult a professional reminder in-app); Data safety / privacy label per tier; Notes for Review: demo mode, sample papers, no login, where the disclaimers and the flag control are.

---

## 6. Environment variables

### 6.1 `apps/api/.env.example`

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

### 6.2 `apps/mobile` (Expo public env; baked at build/export)

| Variable | Default | Meaning |
|---|---|---|
| `EXPO_PUBLIC_API_URL` | `http://127.0.0.1:8000` | API base URL. |
| `EXPO_PUBLIC_APP_TOKEN` | (empty) | Sent as `X-App-Token` when set. |
| `EXPO_PUBLIC_APP_ENV` | `development` | Shows the developer section in Settings when not `production`. |
| `EXPO_PUBLIC_DEFAULT_SAMPLE_MODE` | `false` | Start in sample mode (judging builds). |

No secrets ever live in the mobile app.

---

## 7. Invariants every agent must keep (quick checklist)

1. No user document, image, transcript or model prose is written to disk or logs on the server; `var/` holds only key-pool state, packs and feedback counters.
2. `unpaid`/`mixed` tiers cannot analyze real documents (403) — enforced server-side by the `consent_and_tier_gate` FastAPI dependency exported from `middleware.py` (a dependency rather than pure middleware because the gate must read `demo_sample_id` from the body; BUILD_PLAN §4.1), tested in `tests/contract/test_errors.py`. The gate exempts a request only when its `demo_sample_id` names a fixture in `app.state.fixtures` (an unknown id is gated like no id), and a demo request's pages always come from the fixture on disk, never from the client (`analysis/pipeline.fixture_for`; CL-031).
3. Every fact shown carries `source_quote` + `span_ids` + `confidence` + `verified`; unverified facts never drive urgency or reminders.
4. Contacts and organization names come only from the paper or `data/resources/*.yaml`.
5. Dates are computed only by `deadline_rules.py` from a printed relative phrase + a verified anchor + a cited rule; printed dates win.
6. Model IDs come from `MODEL_PRO`/`MODEL_FAST`; never `-latest`, never 1.5/2.0/2.5; never `temperature`; never `minimal` on 3.8.
7. Every device feature has a `Platform.OS === 'web'` path (`.web.ts` file or branch); pickers on web run inside the gesture handler.
8. Nothing is installed (`npm install`, `npx expo install`, `pip install`) while agents run in parallel; missing packages are reported, not added.
9. Copy: 4th-grade level, no dramatizing, no emoji in controls, 56/72 pt targets, icon + word + color for urgency, speaker button after every paragraph, machine-translation banner on every `machine_translated` pack.
10. Privacy sentences in UI and store listings must be literally true per tier (CI `test_privacy_claims.py`).
