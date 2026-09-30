# ProxyHealth AI — Product Specification

Status: **authoritative for product behaviour, screens and copy.** Written 2026-09-27 from the backbone documents (`docs/DECISIONS.md`, `docs/API_CONTRACT.md`, `docs/ARCHITECTURE.md`), the winning candidate spec (`docs/research/specs/user-first.md`) with grafts from `risk-first.md` and `builder-first.md`, and the research set (`docs/research/{gemini,expo,compliance,resources}.md`). Where this document and the backbone disagree, the backbone wins and the disagreement is listed in §16.2. Coding agents build from this document without asking questions; every screen, state, string and API call they need is here or in the backbone.

Tagline used wherever the name appears: **"ProxyHealth AI — Your paper, explained."** (DECISIONS §13).

---

## 0. How to read this document

| Convention | Meaning |
|---|---|
| **S0…S19** | Screen ids. §6 gives each one purpose, route, components, states, copy, accessibility and RTL notes. Route paths are the Expo Router files in `ARCHITECTURE.md` §3 (`apps/mobile/src/app/…`). |
| **J-A…J-J** | User journeys (§3), each a numbered list of *screen → user action → system behaviour → API call*. |
| **MUST / SHOULD / LATER** | Feature tiers (§4). MUST ships in v1 and blocks store submission; SHOULD ships in v1.x behind the same contract; LATER needs a contract or package change. |
| `key.name` | A flat i18n key in `apps/api/data/langpacks/en.json` (WP0-owned). Appendix A lists every key this document introduces with its English base string. `{placeholder}` syntax; base strings are checked at reading grade ≤ 5 in CI (D-17). |
| "quoted copy" | Exact English base string. Every other language is a pack translation (D-25). |
| **D-nn** | A decision in `DECISIONS.md`. **WPn** = the work package in `ARCHITECTURE.md` §4 that owns the code. |
| *paper* | User-facing word for any document (letter, bill, notice, form). *Helper* is the user-facing word for the AI. Neither "AI", "model", "Gemini" nor "document" appears in body copy except on the consent screen and in "About". |

---

## 1. Thesis

### 1.1 What ProxyHealth AI is (binding, from DECISIONS §0)

ProxyHealth AI is a *paper decoder with a caseworker's manners*, not a chatbot and not a legal or medical adviser. You photograph the letter, bill, notice or form in your hand and, in under a minute, you get three calm cards in your own language: **What is this?**, **What is it asking for?** and **Your step-by-step plan**. Every fact on those cards — each date, amount, requested document and contact — is shown next to the exact words on the page it came from (a highlighted crop), with a confidence chip; anything the helper saw but could not confirm on the page is listed separately under "I saw these but could not confirm them on the page." The app then does what a good caseworker does and no app does today:

1. hands you a **"Show the clerk"** card in English so you can be understood at a counter (§8);
2. keeps every family member's papers in a **vault that lives only on the phone** (§9);
3. sets **reminders** for the dates it found (§10);
4. makes a **text-only quick sheet** you can print or share offline (S15);
5. **troubleshoots the website** you are stuck on from a screenshot, and checks whether a letter or text is a scam (S16);
6. routes you only to **organizations a human verified**, labelled with the date they were checked (S11);
7. **reads every paragraph aloud** so a parent can hear it privately through earbuds instead of through a child (D-26);
8. works in **any language**: a grid of common languages, a free-text box for rare ones (a pack is generated while the screen says *"Adapting system environment to your language..."*), right-to-left layouts, Noto fonts and honest machine-translation labels (D-25/26).

What makes it different is **restraint**. It refuses to give legal or medical advice, refuses to invent a phone number, refuses to compute a date it cannot show the rule for, refuses to say whether you qualify or what will happen, refuses to draft a form, and refuses to keep your documents anywhere you cannot delete with one tap. It is information, not advice, and that is a design principle enforced in code (D-09…D-20), not a footer.

### 1.2 Design target

A stressed adult reading at a 4th-grade level in their own language, on a cracked mid-range Android with two bars of data, possibly reading right-to-left, possibly handing the phone to a 12-year-old to interpret. The app is rated **18+** (Gemini terms) and directed at adults; copy never dramatizes ("You may be deported" is forbidden) and always offers to be *heard* privately rather than read through a child. Every screen is judged against one question: does it survive that kitchen table?

### 1.3 What the product deliberately does not do (fixed copy in "About")

- Does not diagnose, interpret lab values, or give medical advice (`disclaimer.medical_information_only`).
- Does not tell you whether you qualify, what to file, or what will happen to your case (`disclaimer.legal_information_only`; chat `refusal_kind`).
- Does not draft, fill or format any official form or letter (D-17).
- Does not invent phone numbers, websites, addresses or organization names — contacts come only from your paper or from the vetted resource list (D-10).
- Does not compute dates from memory — only from a phrase printed on the paper plus a cited rule, and always labelled as an estimate (D-11).
- Does not store your papers on any server, does not log their content, and never asks your immigration status (D-08, D-24).
- Does not send real papers to the AI on unpaid keys — the server refuses with `403 unpaid_tier_real_documents_disabled` and offers sample papers instead (D-01).

### 1.4 Success measures for v1

| Measure | Target | Where measured |
|---|---|---|
| Time from Home to first three cards (2 photographed pages, 2-bar LTE, paid tier) | ≤ 60 s p50, ≤ 100 s p95 (server `FAILOVER_DEADLINE_S=100`) | `model_meta.latency_ms` + client timer; content-free log |
| Verified-fact precision on the golden set (`tests/golden`, `tests/live`) | ≥ 0.95; zero invented contacts | `scripts/eval_golden.py` (D-16) |
| Facts rejected by the verifier shown, never hidden | 100% appear under "I saw these but could not confirm…" | `result-cards.test.tsx` |
| Screens meeting WCAG 2.2 AA, 200% font scale, LTR and RTL | 100% of S0–S19 | manual matrix (§15) |
| Zero-key demo | Full 3-minute script (§13) passes with `AI_PROVIDER=mock` and no network after first load | `scripts/smoke.sh`, manual |
| "Was this clear?" positive rate per language | tracked per `language_tag` × `surface`; Tier 3 languages reviewed when < 70% | `var/feedback_counts.sqlite` (counts only, D-31) |
| Privacy sentences literally true per tier | 100% (CI `test_privacy_claims.py`) | D-02 |

---

## 2. Personas

The app is used *by* adults and *around* children. Six personas plus one design constraint.

| Id | Who | Language / literacy | Device & data | Papers this month | Fear | What the app must do for them |
|---|---|---|---|---|---|---|
| **P1 Mariam** | 38, Afghan humanitarian parolee, Fairfax County VA; three children (14, 9, 4) | Dari (reads slowly), no English; device locale `fa-AF` | Samsung A-series, 2 years old, cracked screen, prepaid data | Medicaid address-confirmation letter, USCIS I-797C (I-765 renewal), school immunization notice, Inova bill | Missing an immigration or benefits date; her 14-year-old seeing the family's money problems | Dari on first run without network (bundled Tier 2 pack, RTL), read-aloud through earbuds, one giant button, dates found and remembered, a card to hand the county clerk |
| **P2 Jean-Pierre** | 44, Congolese refugee, works nights in a warehouse | Kinyarwanda / Swahili / French (French literacy good), English weak | Mid-range Android, Wi-Fi at home only | $2,300 Inova statement marked "FINAL NOTICE"; a financial-assistance flyer he does not know is related | Debt, collections | Explain the bill without pressure, flag the "FINAL NOTICE" wording as pressure not a court order, route to Inova Financial Assistance and Dollar For with a bring-this checklist, make a quick sheet he can carry to the billing office |
| **P3 Rosa** | 29, Guatemalan asylum seeker, Alexandria VA | Spanish (reads with effort), K'iche' (oral only) | Budget Android, data-limited | 14-day pay-or-quit notice taped to her door; later an eviction summons | Anything with a seal; being put out tomorrow | Say plainly "This is not a court order. Only a court can make you leave.", read it aloud in Spanish, "I want to hear it, not read it" mode, route to Legal Aid Justice Center and the VA eviction helpline, never tell her what to file |
| **P4 Nadia** | 31, bilingual case aide at a resettlement agency | English + Arabic; uses the app *with* clients | Her own phone (iPhone) and a desktop browser in the office | Whatever the client brings: NTA, RFE, SNAP interview notice, school forms | Being seen using an unsafe tool in front of a supervisor | Switch languages in two taps, type a rare language ("Rohingya"), drag a PDF in on web, print a quick sheet, copy the clerk card, storage that is session-only by default on the shared office computer |
| **P5 Anh** | 63, Vietnamese, Medicare Advantage member | Vietnamese; low vision; daughter helps on weekends | iPhone with text size at maximum | Insurance denial letter, an EOB, a prescription label | Losing coverage; taking a medicine wrong | 200% text, high contrast, read-aloud `vi-VN`, a follow-up question ("Can I appeal?") answered from the letter with a referral, never an interpretation of what the medicine does |
| **P6 Jean-Baptiste** | 52, Haitian, CHNV parolee | Haitian Creole; some French | Android; receives scams by SMS | A text claiming to be ICE demanding $500 in gift cards "to avoid arrest" | Arrest, deportation | "Is this a scam?" from a screenshot → fixed scam card, DHS OIG and ReportFraud.ftc.gov from the vetted DB, no payment, credential guard |
| **Layla (constraint)** | 14, Mariam's daughter | Fluent English and Dari | Reads Mariam's screen | — | Learning bad news before her mother does | *Not a user.* Every string must be safe for a child to read aloud: no dramatizing, no "deported", no CAPS; the adult must always have the option to hear it privately |

---

## 3. Top user journeys (step-by-step screen flows)

Each step: **Screen** · what the user does · what the app does · API call (if any). Copy is given by key; Appendix A has the English.

### J-A — Mariam's first 60 seconds and first scan (Medicaid address-confirmation letter)

1. **S0** app opens; `index.tsx` finds no language decision → `/onboarding/language`. `I18nProvider` has already loaded the device-locale pack (`fa-AF` → `prs` bundled Dari pack, `direction: rtl`) synchronously from `src/i18n/packs/`.
2. **S1** Dari (دری) is pre-highlighted at the top of the grid; the whole screen is already RTL via `useDirection()` (row-reverse; no restart needed for the first run). She taps the chip, then `btn.continue`. Native only: because the pack is RTL and `I18nManager.isRTL` is false, the app calls `allowRTL/forceRTL(true)` and shows the restart prompt `direction.restart_prompt` with `btn.restart_later` / `btn.restart_now` — she taps "Later"; layout is already correct through row-reverse.
3. **S2** consent. `useServerConfig()` has fetched `GET /v1/config` (30 s timeout) → `data_use_tier: paid`. `TierBadge` shows `consent.badge.paid`; the three pictogram lines render `consent.line1`, `consent.line2.paid`, `consent.line3`; the 18+ line `consent.adults_only`. She taps `consent.btn_continue`. The app stores `{consent_version: "2026-09-24", accepted_at, tier_seen: "paid", platform: "android"}` in `kv` and `session`.
4. **S3** Home. One 72 pt button `home.scan_cta`. She taps it.
5. **S4** capture. First time: camera permission prompt (plugin string from `app.json`). `CameraView` with page guide and `capture.guide_fit`. Shutter → haptic → thumbnail 1 appears with `capture.add_page` / `capture.done`. She adds page 2, taps Done. Each capture is compressed immediately (`features/scan/compress.ts`: 1600 px longest edge, JPEG 0.8, EXIF stripped) so S5 opens instantly.
6. **S5** review: two thumbnails, per-page Retake / Rotate / Remove, `review.hide_parts` (she skips it), member selector collapsed. Primary `review.read_cta` ("Read this paper").
7. **S6** "Reading your paper": `ProgressSteps` shows `reading.step1` → `reading.step2` → `reading.step3` with the trust line `reading.trust_line`. API: `POST /v1/analyze` with `pages: [2 × {mime_type: "image/jpeg", data_base64, masks: [], rotation: 0}]`, `target_language: "prs"`, `ui_direction: "rtl"`, `state: null` (not set yet), `zip3: null`, `preferences: {tone: "plain", calendar_notes: [], date_format: "auto"}`, `demo_sample_id: null`, `include_page_thumbnails: false`, `masks_applied_client_side: false`, `hide_id_numbers: false`, `client_platform: "android"`, `analysis_id: <uuid from expo-crypto>`; headers `X-Consent-Version: 2026-09-24`, `X-Install-Id`, `X-Request-Id`. Client timeout 120 s; after 20 s the tip `reading.tip_long` appears.
8. **S7** result (`/result/<analysis_id>`), rendered from `session.currentAnalysis`. Live region announces `a11y.reading_finished` ("Reading finished. {n} dates found."). Order: no emergency card (`safety.emergency=false`); `UrgencyBanner` level `high`, icon + `urgency.word.high` + `urgency.high.date_soon` with `{date: "October 14, 2026"}` inside `<Bidi dir="ltr">`, sub-line `urgency.days_until` ("In 20 days"); disclaimer header `disclaimer.benefits_information_only`; Card 1 `summary.title` / `summary.body` with a `SpeakButton`; Card 2 lists `demands[]`: d1 (deadline, `Crop` of `span_ids ["p1b5"]`, `ConfidenceChip high`, `btn.remind_me`) and d2 (document_requested); Card 3 `plan_steps[]` as a `Checklist`; then *Details and quotes*, *Words explained* (`glossary`), *Questions you can ask them* (`questions_to_ask`), *Get help nearby* (`resource_preview` is `[]` because `state` was null → `help.set_region_prompt`), *Ask about this paper*, footer `footer.ai_generated` + `FeedbackRow`, action bar `btn.save` / `btn.show_clerk` / `btn.quick_sheet` / `btn.read_all`.
9. She taps the speaker on Card 1: `lib/tts.ts` finds no `prs` voice, `tts_fallback_tag: "fa-IR"` exists → one-time sheet `tts.fallback_offer` ("No Dari voice on this phone. Hear it in Farsi or English?") → she picks Farsi; it is remembered for `prs`.
10. She taps `btn.remind_me` on d1 (`reminder_eligible: true`) → notification permission explanation `reminders.permission_explain` → system prompt → reminders scheduled for 7/3/1 days before 2026-10-14 at 09:00 local with the generic body `notif.generic_body`. Toast `reminders.added`.
11. She taps `btn.save` → sheet `vault.whose_paper` with chips `vault.me` + `vault.add_member` → taps "Me". The vault (`expo-sqlite`, `Paths.document/vault/<doc_id>/`) is created silently; the page JPEGs are kept (`keep_pages` default ON native). Toast `vault.saved`.
12. She taps `btn.show_clerk` → **S10** full-screen LTR English card built from `clerk_message.english` (see §8). She hands the phone to the county receptionist. Exit by 1.5 s long-press on `clerk.back_to_me` (in Dari, RTL).

### J-B — Jean-Pierre's hospital bill (financial pressure → Action Hub → quick sheet)

1. **S3** French UI (`fr`, Tier 1 bundled, `machine_translated: true` banner until a reviewer signs). He set `state: "VA"`, `zip3: "220"` earlier in **S17** ("Where you live").
2. **S4 → S5 → S6** one page. `POST /v1/analyze` as in J-A with `target_language: "fr"`, `state: "VA"`, `zip3: "220"`.
3. **S7**: `category: medical`, `document_type: medical_bill`, `sender_as_written: "Inova Health System"`, `urgency.level: medium` (payment due in 25 days), disclaimer `disclaimer.medical_information_only`. Card 2: d1 amount `$2,300.00` (verbatim, LTR isolate, crop), d2 payment due date. *Red flags*: `kind: urgency_pressure`, `severity: medium`, text (linted) explaining that "FINAL NOTICE" wording is meant to hurry you and that a bill is not a court order — quoted from the page. Card 3 step 1 (`kind: ask`): ask for an itemized bill and the financial-assistance application before paying; step 2 (`kind: call`) with `resource_tags: ["medical_bill", "charity_care"]`.
4. *Get help nearby* preview shows `resource_preview` (top 3 from the matcher because `state` was supplied): **Inova Financial Assistance** (`why: ["Named on your paper (Inova Health System)", "For hospital and doctor bills", "Serves Fairfax County"]`, `eligibility_note_key: residency_required` rendered as `status_note.residency_required`, `verified_on: 2026-09-27`), **Dollar For**, **IRS 501(r) hospital financial-assistance page** (RESOURCE_DB §6.11 example A; the exact order is the matcher's). He taps `help.see_all` → **S11** (`/result/<id>/help`), which calls `POST /v1/resources/match` `{tags: ["medical_bill","charity_care"], document_type: "medical_bill", category: "medical", state: "VA", county: null, zip3: "220", language: "fr", institutions_as_written: ["Inova Health System"], scam_risk: "none", emergency: false, limit: 8}`.
5. **S11** each `ResourceMatch` card: name, `what_it_does.fr` (falls back to `en` with a small "EN" chip), `cost` badge `resource.free`, languages, `Call` (tel:) and `Website` buttons, hours, `resource.verified_on` chip, `status_note.residency_required`, *Before you go, bring:* `checklist[]` (keys `bring_proof_income`, `bring_proof_va_address`, `bring_the_bill`, `bring_household_ids`, `bring_itemized_bill_request`, `bring_insurance_card`, rendered as `prepare.<key>`) as persistent checkboxes. `national_fallbacks` under `help.anywhere_in_us`.
6. He taps `btn.quick_sheet` → **S15**: text-only sheet (title, three cards, dates, checklist, resource names + DB phones, footer `quicksheet.footer`). Native: `Print.printToFileAsync` → `Sharing.shareAsync` → WhatsApp to his wife. Offline afterwards: the saved paper, the quick sheet text and the checklist all open with no network.

### J-C — Rosa's pay-or-quit notice (urgency, legal boundary, oral literacy)

1. **S3** Spanish UI. Home → `home.scan_cta` → one page → **S6**.
2. **S7**: `category: housing`, `document_type: pay_or_quit`, `urgency.level: high` with `floor_applied: false` (the printed "14 days from…" phrase is `relative_deadline` with `date.kind: unresolved` because `va_pay_or_quit_14d` is deliberately **not** seeded — D-11; the printed pay-by date is `stated` and drives the banner). Banner: `urgency.high.date_soon` with the printed date; a pay-or-quit with no printed date instead hits the D-12 doc-type floor (`pay_or_quit` ∈ `high` floors) and shows `urgency.high.floor` with `floor_applied: true`.
3. *Red flags* leads with the fixed card `fixed.pay_or_quit` ("This is not a court order. Only a court can make you leave.") — `RedFlag{kind: not_a_court_order, fixed_copy_key: "fixed.pay_or_quit", severity: high}`. Disclaimer header `disclaimer.housing_information_only`. Card 3 step 1 (`kind: professional`, `resource_tags: ["eviction","housing_counseling"]`): "Talk to a housing lawyer or counselor before the date on this paper."
4. Rosa taps `btn.read_all` → hear-it mode (`features/analysis/hearItMode.ts`): cards play in order in `es-US`/`es-MX` (voice map), a pinned stop button (`expo-keep-awake` is not installed, so the screen may dim; playback continues); the prompt `tts.earbuds_tip` shows once ("Plug in earbuds to listen privately."). In **S17** she can set `settings.hear_mode_default` so every result auto-plays.
5. **S9** she asks "¿Tengo que irme mañana?" → `POST /v1/chat` `{analysis: <AnalysisContext>, messages: [], question, target_language: "es", demo_sample_id: null}` → `ChatAnswer` with `refusal_kind: none`, `refer_to_professional: housing_counselor`, `distress_acknowledged: true`, `grounded_quotes` chips; the phrasing linter has already rewritten any "you do not have to leave" into "In Virginia, a landlord generally needs a court order before an eviction can happen. Confirm with the legal helpline today." (D-17). The UI appends the fixed referral template `chat.refer.housing_counselor` with a link to **S11**.
6. **S11** (`/result/<id>/help`): Virginia eviction helpline site (`status_note.manual_verify` chip — its phone number is withheld until a human verifies it, RESOURCE_DB §14), HUD counselors, Virginia courts landlord–tenant self-help, Legal Aid Justice Center, 211 (order per RESOURCE_DB §6.11 example C). LSC-funded entries carry `status_note.lsc_restricted` with the link `help.lsc_alternative` ("If that is not you, try these instead").

### J-D — Stuck on the benefits portal (screenshot troubleshooting; Layla helping Mariam)

1. **S3** → tile `home.tile_troubleshoot` → **S16** (`/troubleshoot`). Mode chips: `troubleshoot.mode_portal` (selected) / `troubleshoot.mode_scam`.
2. `troubleshoot.pick_screenshot` (on web the picker call is the first statement in `onPress`) → optional `troubleshoot.goal_label` ("What were you trying to do?", ≤ 300 chars) → optional portal hint chips (`PortalHint`) → `troubleshoot.cta`.
3. `POST /v1/troubleshoot` `{screenshot: {mime_type: "image/png", data_base64, masks: [], rotation: 0}, user_goal: "Upload my electric bill to CommonHelp", mode: "portal", portal_hint: "benefits_portal", target_language: "prs", demo_sample_id: null, client_platform: "android"}` (60 s timeout).
4. Result cards: *What this screen is* (`screen_summary`), *What the red text means* (`error_text_quoted` in a `<Bidi dir="ltr">` quote chip + `error_meaning`), *Do this next* (`steps[]`, each naming `ui_target_as_written` exactly, LTR-isolated), *Careful* (`cautions[]`), the standing credential guard `troubleshoot.credential_guard` (always shown; emphasised red when `asks_for_credentials_or_payment: true`), `troubleshoot.ask_person` CTA when `needs_human_help` (→ **S11** with `resource_tags`). Footer disclaimer `disclaimer.general_information` + `FeedbackRow surface=troubleshoot`.

### J-E — Rare language (Nadia with a Rohingya-speaking client)

1. **S17** → `settings.language` → **S1** → `lang.not_here` box → types "Rohingya" → `btn.continue`.
2. **S1b** shows exactly `langpack.adapting` ("Adapting system environment to your language...") with the sub-line `langpack.about_20s`, three labelled steps (`langpack.step_find`, `langpack.step_translate`, `langpack.step_check`), English fallback line, `btn.cancel`. API: `GET /v1/language-packs/rhg` is skipped (client cannot know the tag yet) → `POST /v1/language-packs` `{language_query: "Rohingya", pack_version: <client base hash>, hint_tag: null}` (60 s timeout). `409 pack_version_mismatch` → client refreshes `GET /v1/config.base_pack_version`, and if the bundled base differs shows `err.pack_mismatch`.
3. `LanguagePack{language_tag: "rhg", direction: rtl, script: Rohg, font_hint: NotoSansHanifiRohingya, tier: 3, source: generated, machine_translated: true, confidence: low, fallback_keys: [...], tts_tag: null, tts_fallback_tag: "my-MM"}` → cached on device keyed `rhg|<pack_version>`; direction flips; Noto Sans Hanifi Rohingya loads via `expo-font`.
4. Banner on every screen: `banner.machine_translated` ("This language was translated by a computer. It may have mistakes. Numbers and dates are kept as printed. Tap the speaker to hear it.") plus, for Tier 3 / `x-` packs, the English source line in small type under every AI sentence (`summary.body_en`, and `original_text` blocks in S8). If `fallback_keys` is non-empty: `banner.partial_pack` ("Some words are in English.").
5. Speaker → no `rhg` voice → `tts.fallback_offer` with Burmese (`my-MM`) or English.
6. If the typed name cannot be resolved at all (`422 language_unresolved`): `err.language_unresolved` with the grid shown again. If resolved only to a private-use tag (`x-hakha-chin`), the pack works the same and the language row shows the typed name.

### J-F — "Is this a scam?" (Jean-Baptiste's ICE gift-card text)

1. **S16** → chip `troubleshoot.mode_scam` → screenshot of the SMS → `POST /v1/troubleshoot` with `mode: "scam_check"`, `target_language: "ht"`.
2. `TroubleshootResult{scam_risk: likely, is_likely_scam: true, scam_reasons: ["scam.gift_card", "scam.arrest_threat", "scam.non_gov_domain"], red_flags: [...], resource_tags: ["scam_report", ...]}`.
3. UI shows the fixed scam card first: `scam.card.likely` ("Scam risk: likely — ICE, USCIS, SSA and the IRS never demand payment by phone, gift card, wire, or app. Do not pay. Report it:") followed by the reporting resources fetched with `POST /v1/resources/match {tags: ["scam_report"], scam_risk: "likely", language: "ht", ...}` — DHS OIG 1-800-323-8603 and ReportFraud.ftc.gov come from the DB, never from the model. Then the reason chips (`scam.<reason>` copy), the screen summary, and `btn.save_evidence` (saves the screenshot to the vault as a `document_type: other_notice`, category `immigration`, titled `vault.title_scam_check`).
4. The same card appears in **S7** for a scanned *letter* when `AnalysisResult.scam_risk == likely`; `possible` shows `scam.card.possible`.

### J-G — Anh's follow-up question on a denial letter (chat with a referral)

1. **S7** for `document_type: insurance_denial` (`urgency.level: medium`, d1 = `relative_deadline` "within 180 days of this notice" → `date.kind: estimated` via rule `aca_internal_appeal_180d` with `formula`, `anchor_quote`, `rule_source_url`, `rule_verification: verified`, rendered as `demand.estimate_prefix` ("Estimate:") + formula + `demand.confirm_with_sender` + link `demand.rule_link` ("rule ↗" → `GET /v1/rules` entry).
2. `btn.ask` → **S9** with `suggested_questions` chips. She asks "Can I appeal?" (Vietnamese).
3. `POST /v1/chat` → `ChatAnswer{answer: "The letter says you can ask for an internal appeal within 180 days of the notice date. …", grounded_quotes: [...], refusal_kind: none, refer_to_professional: sender, suggested_questions: [...]}`. If she asks "Should I appeal?" → `refusal_kind: filing_advice`, `refer_to_professional: benefits_office` → the UI renders `chat.refusal.filing_advice` + `chat.refer.benefits_office` instead of a free answer. Every bubble has a `SpeakButton` and a `FeedbackRow surface=chat`.

### J-H — Nadia on web/desktop (caseworker companion surface)

1. `https://proxyhealth.expo.app` → **S1** (locale `en-US`) → **S2** (`consent.line3.web`: "Papers you save stay only in this browser, if you choose to keep them.") → **S3**.
2. `home.tile_pick` → `expo-document-picker` opens inside the click handler → she picks a 3-page PDF (≤ 12 MB checked client-side; page count enforced server-side) → **S5** shows `review.pdf_summary` ("PDF, {pages} pages" once known, else file size) → `review.read_cta`.
3. `POST /v1/analyze` with one `application/pdf` page, `include_page_thumbnails: true`, `client_platform: "web"`, `target_language: "am"` (she set Amharic for the client in **S17**, or via the output-language chip on S5).
4. **S7** uses `page_thumbnails[]` for crops. Storage is session-only (memory) by default: the banner `banner.web_session_only` ("This paper is kept only while this tab is open, unless you turn on keeping in Settings."). `btn.quick_sheet` → **S15** → `btn.download_pdf` → `POST /v1/quicksheet/pdf` → Blob → `<a download="proxyhealth-quick-sheet.pdf">`; `btn.print` → the sheet HTML printed from a hidden same-origin `<iframe srcdoc>` (browser print dialog for the sheet only; `Print.printAsync` is the no-DOM fallback — CL-040). `btn.copy_text` → `expo-clipboard` synchronously in the click handler. `btn.show_clerk` → **S10** (also `btn.copy_text`).
5. `btn.remind_me` on web → `.ics` download (`lib/ics.ts`) with `reminders.web_explain` ("Your browser cannot remind you. Add this date to your calendar instead.").

### J-I — Quota exhausted, then offline

1. **S6** receives `429 quota_exhausted` (`key_exhausted: true`, `retry_after_seconds: 240`). `ErrorState` renders `err.quota_exhausted` with `{minutes: 4}` and four buttons: `btn.retry` (disabled until `Retry-After` elapses, showing a countdown), `btn.save_to_read_later`, `btn.call_211` (tel:211, from fixed copy — 211 is in the resource DB and in `national_fallbacks`), `btn.try_sample`.
2. `btn.save_to_read_later` → `vault.whose_paper` → the pages are stored with `analysis_json = null`; **S12** shows the row with the chip `vault.not_read_yet` and a `btn.read_now` action that re-opens **S6** with the stored pages.
3. Later, offline: **S3** shows the offline line `home.offline_line`; scan is still allowed (queued: `capture.offline_queue`); **S12**, saved **S7**s, **S15**, **S14** and bundled packs all work; **S9**/**S16** show `state.offline_disabled`. The Help tab shows the last matched list per document plus the bundled national fallbacks (`help.offline_cached`).

### J-J — Judge with a free key (unpaid tier) or no key at all

1. Operator runs `AI_PROVIDER=gemini` with one `{billing: false}` slot, `ENV=development`. `GET /v1/config` → `data_use_tier: unpaid`, `features.real_documents_allowed: false`.
2. **S2** shows the red badge `consent.badge.unpaid` and the line `consent.line2.unpaid` ("This test build uses a free AI key. Google may read and use what is sent. Do not send real papers. Sample papers only."). `consent.btn_continue` is **not shown** on `unpaid`/`mixed` (there is nothing to consent to: real papers are blocked server-side and sample requests are exempt from consent); the actions are `consent.try_sample` (primary) and `consent.btn_not_now`. **S3** disables `home.scan_cta` and `home.tile_pick` with the explanation `home.unpaid_disabled` and promotes the sample carousel (COMPLIANCE_PRIVACY §4.2).
3. `consent.try_sample` → sample list from `GET /v1/demo/fixtures` → **S5** shows the sample pages fetched from `GET /v1/demo/fixtures/{id}/pages/{n}` (display only) → **S6** → `POST /v1/analyze` with `demo_sample_id: "<id>"`, `pages: []` (allowed when `demo_sample_id` is set — API_CONTRACT §3.5) and the required `client_platform`; for any known id the server reads the fixture's pages from disk on every provider and ignores client pages (these requests skip the consent gate), and an unknown id is gated like no id (`428 consent_required` without `X-Consent-Version`, `403 unpaid_tier_real_documents_disabled` on `unpaid`/`mixed`) and, past the gate, is `400 invalid_request` (CL-031; ARCHITECTURE §7 item 2; AI_PROMPTS §14 item 15(b)). Header `X-Consent-Version` is not required for requests whose `demo_sample_id` names a known fixture, but the client sends it anyway when present. The result carries `warnings: ["unpaid_tier","demo_sample"]`, `disclaimers: [..., "unpaid_tier_warning", "demo_sample"]` → banners `banner.demo_sample` and `banner.unpaid_tier`.
4. With **no** key (`AI_PROVIDER=mock`): tier `demo`, badge `consent.badge.demo` with `consent.line2.demo` ("Sample mode. No AI service is contacted. Your photo is only compared with our sample papers and is not kept."), `home.scan_cta` works and returns fixture output by dHash match when a printed SAMPLE sheet is photographed, or `quality.readable=false` with `state.sample_not_recognised` for anything else. Real analyses are never faked (D-29).

---

## 4. Feature inventory

Owner = work package in `ARCHITECTURE.md` §4.

### 4.1 MUST (v1; blocks store submission)

| # | Feature | Rationale | Decisions | Owner |
|---|---|---|---|---|
| M1 | Two-screen onboarding: language grid with device-locale preselect and "My language is not here" box; consent with tier badge, 18+ line, "Not now", "Try a sample paper first" | 60-second rule; Apple 5.1.2(i)/Play prominent disclosure require consent before the first upload; tier must be shown truthfully | D-02, D-25 | WP4 |
| M2 | Bundled Tier 1 + Tier 2 packs (incl. Dari, Pashto) working offline on first run, labelled machine-translated until reviewed | Target population on unstable data; FTC literal-truth on review claims | D-25 | WP1 (packs), WP4 (runtime) |
| M3 | Dynamic language pack for any typed language with the exact loading copy "Adapting system environment to your language...", server cache, partial-pack banner, `x-` tags | Signature feature; Tier 3 languages (Rohingya, Karen, Tigrinya, Mayan) | D-25 | WP1, WP4 |
| M4 | RTL layout via `useDirection()` (row-reverse) on all platforms, native restart prompt, Bidi isolation of verbatim values, Noto fonts, digits never localized | Dari/Pashto/Arabic/Urdu are day-one languages | D-26 | WP4 |
| M5 | Scan: camera with page guide, photo picker, PDF picker, 1–12 pages, review (retake/rotate/remove/reorder), client compression 1600 px JPEG 0.8 EXIF-stripped, web pickers inside the gesture | Notices are multi-page; PDFs arrive by email; caps from D-21 | D-21 | WP5 |
| M6 | "Hide parts" masks before sending (canvas burn on web; server-side Pillow on native; SSNs always masked in returned text) | Data minimization without new native packages; literally true consent copy | D-19 | WP5 (client), WP2 (server) |
| M7 | Result: emergency card → urgency banner → fixed disclaimer → three cards → Details and quotes (crop + confidence per fact) → Words explained → Questions to ask → Red flags → Get help preview → Ask → footer + feedback → action bar; "I saw these but could not confirm them on the page" section | The three cards alone hide *where* a claim came from; quotes and crops are the anti-hallucination UX | D-09…D-12, D-17, D-20 | WP5 |
| M8 | Side-by-side original/translation viewer with tappable highlight boxes | Lets a bilingual helper check the machine; required for Tier 2–3 trust; WCAG 3.1.2 per-pane language | D-09 | WP5 |
| M9 | Read-aloud: 44×44 speaker after every paragraph, "Read all aloud", "I want to hear it, not read it" mode, honest closest-language voice fallback, persistent stop | Oral literacy; privacy from child interpreters | D-26 | WP5 |
| M10 | "Show the clerk" card: fixed template + linted need line, conditional HHS interpreter line, LTR high-contrast full screen, vault hidden, long-press exit | The counter is the moment of highest indignity | D-18 | WP5 |
| M11 | Family vault: opt-in save, "Whose paper is this?", members, per-member view/move/wipe, "Delete everything", native sqlite + files, web session-only with honest IndexedDB opt-in | Parents manage the household's papers; nothing to subpoena | D-22…D-24 | WP4 (storage), WP6 (UI) |
| M12 | Deadline reminders: 7/3/1 days at 09:00 for `reminder_eligible` demands, generic lock-screen body, detail opt-in, in-app list, "Add my own date", `.ics` on web and via share on native | Missed dates are catastrophic (in absentia removal, benefit loss) | D-22 | WP6 |
| M13 | Quick sheet: text-only sheet with English section headers; native PDF via `expo-print`+`expo-sharing`; web server PDF via `POST /v1/quicksheet/pdf` + print dialog; copy text; read aloud | Spotty data; the paper goes to the appointment | — | WP6 (client), WP3 (server) |
| M14 | Action Hub (Get help): tags × state/zip3 × language matcher, "Verified on" chips, LSC note with alternative link, "Before you go, bring" checklist, national fallbacks, need tiles without a document | Only routes to humans we checked | D-10, D-24 | WP6 (client), WP3 (server) |
| M15 | Legal-document module (USCIS/EOIR/ICE/housing/benefits/employment/tax/jury) with fixed high-severity notices and information-only guardrails | The user's explicit ask; UPL line designed in | D-17, D-20 | WP2 |
| M16 | Screenshot troubleshooting with *Stuck on a website* / *Is this a scam?* modes, credential guard, "Ask a person" | Portals are where people give up; scams arrive as texts | D-13 | WP6 (client), WP2 (server) |
| M17 | Grounded follow-up chat (stateless, ≤ 8 turns), quote chips, "The paper does not say", refusal kinds with fixed referral templates, distress acknowledgement | "Does this mean my son loses Medicaid?" is always the next question | D-17 | WP5 (client), WP2 (server) |
| M18 | Feedback loop: "Was this clear?" + Report on every AI surface, counts only | Play AI-content flag requirement; language QA signal | D-31 | WP5/WP6 (UI), WP7 (API) |
| M19 | Demo mode: mock provider, sample papers list, sample-mode banner, dHash match of printed SAMPLE sheets, offline samples, unpaid-tier gate handling | Judges and offline demos; honest fallback when quota is exhausted | D-01, D-29 | WP7 (API/fixtures), WP6 (client) |
| M20 | Emergency card from fixed copy, keyword-triggered in every bundled language, "Need help now?" affordance on every screen | Never let a model author an emergency instruction | D-14, D-28 | WP5 |
| M21 | Scam path: code-scored `scam_risk`, fixed card, forced `scam_report` resources, save as evidence | Immigrants are targeted; USCIS/FTC cues verified | D-13 | WP2, WP5/WP6 |
| M22 | Urgency computed in code with icon + word + color, "Verify this date" and "Remind me" CTAs, past-date rule | Most consequential triage signal | D-12 | WP2, WP5 |
| M23 | Honest waiting and error states: three-step progress, 20 s tip, every `ErrorCode` mapped to copy + actions (§5.4), unreadable page state without re-spending quota | Two bars of data; quota is finite | D-07 | WP5 |
| M24 | "Big Calm" design system and accessibility floor: 18 base / 56 / 72 pt, 7:1 body contrast, high-contrast palette, 200% scaling, live regions, WCAG 2.2 AA | The population's baseline | D-28 | WP0 (tokens), WP4 (components) |
| M25 | Cultural/tone preferences: tone plain/formal, calendar notes (≤ 5), date format — passed as `Preferences` on analyze | Product requirement (cultural/religious sensitivity); already in the contract | — | WP6 (settings), WP2 (prompts) |
| M26 | Region setting: state + optional zip3 (never full ZIP, never GPS), used for matching only | Better routing with minimal data | D-24 | WP6 |
| M27 | Offline capture with session queue ("I can take the photo now and read it later") and "Save to read later" from error states | Spotty data | — | WP5, WP6 |

### 4.2 SHOULD (v1.x; same contract, no new packages)

| # | Feature | Rationale | Owner |
|---|---|---|---|
| S1 | App PIN lock for the vault (SecureStore-held `vault_key` + expo-crypto digest verifier); no PIN on web | Shared phones; biometrics need a package install (LATER) | WP4/WP6 |
| S2 | Persistent offline scan queue (survives app restart), auto-send when connectivity returns | Session queue is MUST; persistence is the polish | WP5 |
| S3 | "Re-read this paper" from the vault when page images were kept (re-sends stored pages) | Prompt/model improvements reach old papers | WP6 |
| S4 | Web blur hint (canvas variance) before spending quota | No pixel access on native; web-only heuristic | WP5 |
| S5 | Community-review queue for Tier 2/3 packs (operator tooling over feedback counts; `reviewed_by` sign-off) | Converts flags into better packs; unblocks removing the machine-translated banner | WP1 |
| S6 | Kinder per-device daily budget message with the exact reset time (from `rate_limited` `Retry-After`) | Protects shared quota in pilots | WP5 |
| S7 | Web drag-and-drop onto Home and keyboard-first flow for caseworkers | Desktop companion persona (Nadia) | WP6 |
| S8 | Reminder "day-of" toggle and per-reminder time of day | Some users want the morning of the date | WP6 |

### 4.3 LATER (needs a contract change, a package install window, or external review)

| # | Feature | Why not now |
|---|---|---|
| L1 | Two-way clerk mode (clerk types an English reply → translated + read aloud) | No endpoint in `API_CONTRACT.md` v1 for reply translation; would need `POST /v1/translate` and a contract bump (§16.2) |
| L2 | Biometric unlock (`expo-local-authentication`) | Package not installed; install only in a WP0-owned window |
| L3 | On-device mask burning and OCR pre-redaction (dev-build native module) | No compositing primitive in installed packages (D-19) |
| L4 | Server TTS (`gemini-3.8-flash-tts`) for languages without a device voice | Costs quota/money; measure device-voice gaps first (D-26) |
| L5 | Voice questions (`expo-speech-recognition`) | Dev build only; not in Expo Go |
| L6 | Encrypted vault export/import between phones | Must not become cloud sync |
| L7 | Helper/organization mode (agency branding, multi-client hand-off) | Needs a BA/contract analysis (compliance.md §2) |
| L8 | App-layer AES-GCM of vault blobs; SQLCipher plugin; iOS backup-exclusion *claims* | Verify in the first EAS dev build; do not claim until verified (D-22) |
| L9 | Interactions API provider (`AI_PROVIDER=gemini_interactions`) | Config change when Google forces it (D-05) |
| L10 | Free-text feedback with opt-in card inclusion | Counts only in v1 (D-31) |
| L11 | Non-US storefronts and `EXPO_PUBLIC_REGION` | v1 is US-scoped (D-03) |


---

## 5. Global UX rules

### 5.1 "Big Calm" design system (tokens in `src/design/tokens.ts`, D-28)

| Token | Value | Note |
|---|---|---|
| Base font | 18 (body minimum 16) | `allowFontScaling` on everywhere; `maxFontSizeMultiplier={2}` **only** on tab labels (and the tab badge count, which is part of the tab item — CL-038(d)); layouts tested at 200% |
| Buttons | 56 pt tall; primary CTA 72 pt; `hitSlop` 8; 8 pt spacing | Every screen has exactly one primary action |
| Contrast | body 7:1 (never below 4.5:1); UI components 3:1 | Palettes `light`, `dark`, `highContrast`; `useHighContrast()` = user toggle OR `AccessibilityInfo.isHighTextContrastEnabled()`/`isDarkerSystemColorsEnabled()` |
| Urgency | icon + word + color, never color alone, never CAPS | table in §5.5 |
| Speaker | 44×44 `SpeakButton` after every paragraph; stop state; pinned stop bar while reading all | D-26 |
| Cards | `Card` = `role="region"` + heading + `SpeakButton` slot | screen readers navigate by region |
| Motion | respects reduce-motion; progress bars mirror in RTL; no decorative animation | |
| Emoji | never in controls or labels (screen readers read them) | icons are vector glyphs with `accessibilityLabel` |
| Help affordance | persistent calm `home.need_help_now` ("Need help now?") link in the header of every screen → **S19** | replaces an alarming emergency header (D-28) |
| Fonts | Noto Sans (Latin/Cyrillic/Vietnamese), Noto Naskh Arabic (ar, prs, ps, fa), Noto Nastaliq Urdu (ur; line-height 2.0), Noto Sans Ethiopic, Noto Sans Myanmar, Noto Sans Devanagari/Bengali/Gurmukhi, Noto Sans Hanifi Rohingya; CJK system fonts | `font_hint` from the pack selects the family |

### 5.2 RTL and bidi rules (every component)

1. `useDirection()` → `{isRTL, row, textAlign, writingDirection}` drives `flexDirection`, `textAlign`, `writingDirection`. No component hardcodes `row` or `left`.
2. Verbatim values (`value_verbatim`, dates, case/receipt numbers, amounts, phones, URLs, agency names, `ui_target_as_written`, `error_text_quoted`, `source_quote`, `term_as_written`) render inside `<Bidi dir="ltr">` (LRI/PDI on native, `unicode-bidi: isolate` on web). Digits are never localized or reversed; `DateInfo.localized_line` is shown *in addition* on its own line when present.
3. Page images and crops are never mirrored. Icons of real objects (clock, phone, camera) are not mirrored; chevrons, progress bars and back arrows are.
4. Native: switching to/from an RTL pack calls `I18nManager.allowRTL/forceRTL` and shows `direction.restart_prompt`; layout is already correct through row-reverse, so "Later" is safe. Web: `document.documentElement.dir` and `lang` are set from the pack.
5. Per-pane language: source blocks carry `accessibilityLanguage`/`lang` = `detected_language`; translation/UI text carries the pack tag.
6. Thumbnail strips keep **document page order** left-to-right with explicit page numbers in Western digits, even in RTL (builder-first graft): page 1 is always leftmost.

### 5.3 State vocabulary (every screen must implement the states marked ● in its §6 entry)

| State | Rendering rule |
|---|---|
| **loading** | `ProgressSteps` for AI calls (three labelled steps, `aria-live="polite"`), skeleton rows for lists; never a bare spinner longer than 2 s without words |
| **empty** | `EmptyState`: one sentence + one primary action |
| **error** | `ErrorState`: `user_message_key` copy (§5.4) + primary action + secondary actions; never raw upstream text |
| **offline** | `Banner variant="offline"` with `banner.offline`; AI actions disabled with `state.offline_disabled`; local features stay live |
| **all-keys-exhausted** (`429 quota_exhausted`) | `err.quota_exhausted` with Retry countdown, Save to read later, Call 211, Try a sample paper |
| **camera-denied** | `state.camera_denied` + `btn.open_settings` (`Linking.openSettings()`) + `btn.pick_instead`; on web, the picker path is the only path so this state never shows |
| **unsupported-language** | (a) `422 language_unresolved` → `err.language_unresolved` with the grid; (b) resolved but Tier 3 / `x-` → `banner.machine_translated` + English source lines; (c) no TTS voice → `tts.fallback_offer`; (d) `warnings` contains `document_language_differs` → `banner.doc_language_differs` |
| **low-confidence-translation** | `translation_confidence == low` → `banner.low_confidence_translation` on S7/S9/S16, English source lines forced on, `FeedbackRow` expanded by default |
| **unreadable** (`quality.readable == false`) | page thumbnail + `state.unreadable` ("I could not read this page. Try again in brighter light, and flatten the page.") + `btn.retake`; the app never re-spends quota automatically |
| **partially readable** (`pages_unreadable` non-empty) | chip per page `state.page_unreadable` ("Page {n} was hard to read.") above Card 1 |
| **degraded** (`model_meta.quality == degraded`) | `banner.degraded_model` ("A faster helper read this paper. Check the highlighted words carefully.") |
| **demo / sample** (`model_meta.demo` or tier `demo`) | `banner.demo_sample` on S7/S9/S16; `banner.sample_mode` on S3 |
| **unpaid tier** (`data_use_tier ∈ {unpaid, mixed}`) | `banner.unpaid_tier` (red, icon + word) on S3 and S7; real scans disabled (`home.unpaid_disabled`) |
| **tier unknown** (`/v1/config` unreachable, or tier `none`) | S2 badge `consent.badge.unknown` + `consent.unknown_hint`, S2 Continue disabled (consent cannot be recorded until the tier is known), samples enabled from the bundled manifest. The S3 scan CTA is not disabled by `unknown` itself: without recorded consent a tap opens S2; with consent already recorded, scanning works and an offline scan is queued (`capture.offline_queue`, journey J-I step 3) |
| **consent missing / withdrawn** | S3 scan tiles disabled with `home.consent_needed`; tapping opens **S2** |
| **clerk mode** (`session.clerkMode`) | tab bar hidden, vault routes blocked, exit only via long-press |
| **saved / unsaved** | S7 action bar shows `btn.save` or the chip `vault.saved_to` ("Saved for {member}") |

### 5.4 Error mapping (client `src/api/errors.ts`; copy keys in Appendix A)

| `ErrorCode` (HTTP) | Key | English base string | Primary action | Secondary actions |
|---|---|---|---|---|
| `invalid_request` (400) | `err.invalid_request` | "Something went wrong with this request. Please try again." | Retry | Go home |
| `too_many_pages` (400) | `err.too_many_pages` | "You can send up to {max_pages} pages at a time. Remove some pages, or split the paper into two scans." | Back to pages | — |
| `pdf_too_long` (400) | `err.pdf_too_long` | "This PDF has too many pages. The limit is {max_pdf_pages} pages." | Pick another file | Take photos instead |
| `unauthorized` (401) | `err.unauthorized` | "This app is not allowed to use the server right now. Please update the app." | Go home | — |
| `unpaid_tier_real_documents_disabled` (403) | `err.unpaid_tier` | "This test build uses a free AI key. Real papers cannot be sent. Try a sample paper instead." | Try a sample paper | Go home |
| `not_found` (404) | `err.not_found` | "I could not find that. It may have been removed." | Go home | — |
| `pack_version_mismatch` (409) | `err.pack_mismatch` (after one silent refresh + retry) | "The app needs an update before it can add this language. Choose one of these languages for now." | Choose a language | — |
| `payload_too_large` (413) | `err.payload_too_large` | "This file is too big. Take photos of the pages instead, or choose a smaller PDF (up to {max_pdf_mb} MB)." | Take photos | Pick another file |
| `unsupported_media_type` (415) | `err.unsupported_media_type` | "I can read photos (JPG, PNG, HEIC, WebP) and PDF files. This file is a different kind." | Pick another file | — |
| `content_blocked` (422) | `err.content_blocked` | "I could not read this paper safely. Try again with only the part you need, or ask a helper." | Hide parts and try again | Get help nearby |
| `language_unresolved` (422) | `err.language_unresolved` | "I could not find that language. Check the spelling, or choose one of these." | Try again | Choose a language |
| `consent_required` (428) | (route to **S2**; on a second 428) `err.consent_required` | "Please read how your paper is handled, then try again." | Continue | — |
| `rate_limited` (429, `key_exhausted=false`) | `err.rate_limited` | "You have read many papers today. Please wait {minutes} minutes, or open a saved paper." | Open My papers | Try a sample paper |
| `quota_exhausted` (429, `key_exhausted=true`) | `err.quota_exhausted` | "Our helper is very busy right now. Try again in {minutes} minutes, or see what you can do offline." | Retry (countdown) | Save to read later · Call 211 · Try a sample paper |
| `internal` (500) | `err.internal` | "Something went wrong on our side. Your paper was not saved anywhere. Please try again." | Retry | Go home |
| `model_output_invalid` (502) | `err.model_output_invalid` | "I could not finish reading this paper. Please try again. If it happens again, try fewer pages." | Retry | Back to pages |
| `provider_not_configured` (503) | `err.provider_not_configured` | "This server has no helper set up. Sample papers still work." | Try a sample paper | — |
| `upstream_unavailable` (503) | `err.upstream_unavailable` | "Our helper is not answering right now. Try again in {minutes} minutes, or see what you can do offline." | Retry (countdown) | Save to read later · Call 211 · Try a sample paper |
| client network failure | `err.network` | "No internet. Check your connection and try again. Nothing was sent." | Retry | Save to read later |
| client timeout (120/60/30 s) | `err.timeout` | "This is taking too long. Check your connection and try again. Your paper was not saved anywhere." | Retry | Save to read later |

`{minutes}` = `ceil(retry_after_seconds / 60)`, minimum 1. `{max_pages}`, `{max_pdf_pages}`, `{max_pdf_mb}` come from `ServerConfig.limits` (`max_pdf_mb = floor(max_pdf_bytes / 1048576)`). "Try a sample paper" opens the sample picker (§12); "Call 211" is `tel:211`; "Save to read later" runs the save flow with `analysis_json = null`.

### 5.5 Urgency rendering (`UrgencyBanner`, data from `AnalysisResult.urgency`, computed server-side — D-12)

| `level` | Icon (`tokens.urgency.*.icon`) | Word key | Color role | Headline keys `urgency.py` may emit |
|---|---|---|---|---|
| `emergency` | `alert` | `urgency.word.emergency` "Emergency" | red-900 on white | banner is replaced by **S19** shown first; the banner itself shows `urgency.emergency.headline` |
| `critical` | `calendar-alert` | `urgency.word.critical` "Very soon" | red-700 | `urgency.critical.date_soon`, `urgency.critical.date_today`, `urgency.critical.date_passed`, `urgency.critical.floor` |
| `high` | `calendar-clock` | `urgency.word.high` "Soon" | orange-700 | `urgency.high.date_soon`, `urgency.high.floor` |
| `medium` | `calendar` | `urgency.word.medium` "Coming up" | amber-700 on light / amber-300 on dark | `urgency.medium.date_soon`, `urgency.medium.estimated` |
| `info` | `info` | `urgency.word.info` "For your information" | blue-700 | `urgency.info.date_later`, `urgency.info.no_date`, `urgency.info.no_action` |

Rules: the headline is `t(urgency.headline_key, urgency.headline_params)`; `{date}` is rendered inside `<Bidi dir="ltr">`; when `days_until` is non-null a second line `urgency.days_until` ("In {days} days") or `urgency.days_ago` ("{days} days ago") is added client-side; when `past_date` the headline is `urgency.critical.date_passed` and the primary CTA is `btn.verify_date`. CTAs: `btn.remind_me` when the driving demand is `reminder_eligible`; `btn.verify_date` when `verify_resource_id` is set (→ **S11** `?focus=<resource_id>`) or when a `contact` demand with a printed phone exists (`tel:`); `floor_applied: true` adds the sub-line `urgency.floor_note` ("This kind of paper is important even without a date."). Unverified and `estimated` facts never raise the banner above `medium` (server rule; the client trusts `level`).

### 5.6 Disclaimers and warnings (fixed copy; the model never writes them — D-17)

| `disclaimer_kind` / `WarningCode` | Where | Key |
|---|---|---|
| `legal_information_only` | header of S7/S9/S15 for immigration, court, civic, employment | `disclaimer.legal_information_only` — "This is general information about this type of paper, not legal advice about your case. Only a licensed lawyer or a DOJ-accredited representative can advise you." |
| `medical_information_only` | medical | `disclaimer.medical_information_only` — "This explains what your paper says. It is not medical advice. Ask your doctor, nurse or pharmacist what it means for you." |
| `benefits_information_only` | benefits | `disclaimer.benefits_information_only` — "This explains what your paper says. It is not a decision about your benefits. Only the office that sent it can tell you what happens next." |
| `housing_information_only` | housing | `disclaimer.housing_information_only` — "This is general information about this type of paper, not legal advice. A housing lawyer or counselor can advise you about your home." |
| `general_information` | school, tax, other, troubleshoot, resources | `disclaimer.general_information` — "This is general information from your paper. It can be wrong. Check the highlighted words and confirm with the sender." |
| `machine_translation` | banner | `banner.machine_translated` |
| `verify_with_sender` | footer line | `footer.verify_with_sender` — "Confirm dates and amounts with the sender." |
| `ai_generated` | footer | `footer.ai_generated` — "Made by a computer from your paper. It can be wrong. Check the highlighted words." |
| `degraded_model` | banner | `banner.degraded_model` |
| `unpaid_tier_warning` | banner (red) | `banner.unpaid_tier` — "Test build with a free AI key. Sample papers only." |
| `demo_sample` | banner | `banner.demo_sample` — "This is a sample paper. Nothing of yours was sent." |
| `low_quality_image` | chip | `warning.low_quality_image` — "The photo was hard to read. Some words may be wrong." |
| `partial_pages` | chip | `warning.partial_pages` — "Some pages could not be read." |
| `page_edge_crop` | chip | `warning.page_edge_crop` — "Part of a page may be cut off. Check the edges." |
| `translation_partial` | chip | `warning.translation_partial` — "Only the important parts were translated. The rest is in the original language." |
| `blocked_partial` | chip | `warning.blocked_partial` — "Part of this paper could not be read safely." |
| `phrasing_lint_unavailable` / `emergency_lexicon_unavailable` | chip (Tier 3 only) | `warning.checks_unavailable` — "Some safety checks are not available in this language yet." |
| `injection_masked` | red flag card | `warning.injection_masked` — "This paper contained text meant for computers. I ignored it." |
| `contacts_stripped` | chip on the affected card | `warning.contacts_stripped` — "A phone number or link was removed because it was not printed on your paper. See Get help nearby." |
| `document_language_differs` | banner | `banner.doc_language_differs` — "Your paper is in {doc_language}. I explained it in {ui_language}." |

### 5.7 Global affordances present on every screen

- Header: back (mirrored in RTL), screen title, `home.need_help_now` link (→ **S19**). In clerk mode the header is hidden.
- Tab bar (`(tabs)/_layout.tsx`, JS `Tabs`, 64 pt, icon + word): `tabs.home` "Home", `tabs.papers` "My papers", `tabs.help` "Get help", `tabs.settings` "Settings". Hidden on stack screens above the tabs and in clerk mode. `tabs.papers` shows a badge with the count of reminders in the next 7 days.
- Live region: one per screen for status changes (`a11y.*` keys).
- Every control: `role`, `accessibilityLabel`, `accessibilityHint`; focus order = reading order; no text container has a fixed height.

---

## 6. Screen-by-screen UX spec

Format per screen: **Purpose · Route · Data & API · Components · Primary action · States (● required) · Copy · Accessibility · RTL.**

### S0 — Splash and first-run redirect

- **Purpose:** decide where to send the user in < 1 s and never show a blank screen.
- **Route:** `src/app/_layout.tsx` (root `Stack` + providers + `SplashScreen` gate) and `src/app/index.tsx` (redirect).
- **Data:** `kv`: language decision, consent record, `EXPO_PUBLIC_DEFAULT_SAMPLE_MODE`; `useServerConfig()` starts fetching `GET /v1/config` in the background (cached copy from `kv` used first).
- **Logic:** no language → `/onboarding/language`; language but no consent decision (neither accepted nor "Not now") → `/onboarding/consent`; else `/(tabs)`. Consent is re-shown when `ServerConfig.consent_version` ≠ stored `consent_version` **or** `data_use_tier` ≠ stored `tier_seen` (D-02).
- **Components:** app icon, wordmark, tagline `app.tagline` ("Your paper, explained.").
- **States:** ● loading (≤ 1 s; splash kept until the device-locale pack is loaded synchronously); ● corrupted pack cache → falls back to bundled English and clears the cache silently (`a11y.pack_reset` announced).
- **Accessibility:** announces `a11y.app_starting` ("ProxyHealth AI is starting."). **RTL:** none.

### S1 — Language

- **Purpose:** pick a language in one tap; make any language reachable.
- **Route:** `/onboarding/language` (also opened from **S17**).
- **Data & API:** `ServerConfig.languages[]` (bundled list from `src/i18n/languages.ts` when offline); `POST /v1/language-packs` for typed languages (via **S1b**); `GET /v1/language-packs/{tag}` for known non-bundled tags.
- **Components:** "Aa" text-size toggle (top corner, cycles S/M/L/XL, persisted); device-locale chip preselected at the top (`lang.suggested` "Suggested for this phone"); grid of large chips (56 pt min) with `name_native` first and `name_en` beneath, ordered: en, es, ps, prs, ar (the blueprint's five), then remaining Tier 1 by community size, then Tier 2; each chip shows a small `lang.machine_translated_dot` when `machine_translated`; `lang.not_here` text box ("My language is not here") with `btn.continue`; the `tabs.*` bar is not shown (onboarding is above the tabs).
- **Primary action:** `btn.continue` (72 pt), enabled when a chip is selected or ≥ 2 characters typed.
- **States:** ● default; ● typed-empty (box focused, nothing typed → helper `lang.type_hint` "Type the name of your language, in any language."); ● loading (typed → **S1b**); ● offline with a typed language → `state.lang_needs_internet` ("I need internet to add a new language. Choose one of these for now."); ● `422` → `err.language_unresolved`; ● `429/503` → `err.quota_exhausted`/`err.upstream_unavailable` with `btn.choose_bundled`; ● bundled-only when `/v1/config` is unreachable (no server languages; typed box still works offline-first by checking the device cache).
- **Copy:** title `lang.title` "Which language?"; `lang.not_here`; `lang.type_hint`; `btn.continue` "Continue".
- **Accessibility:** chips are `role="radio"` in a `radiogroup`; each chip sets `accessibilityLanguage`/`lang` to its own tag so VoiceOver pronounces the native name; announce "{name}, {i} of {n}". **RTL:** grid mirrors once a RTL pack is active; native names render with `dir="auto"` isolation regardless of UI direction.

### S1b — Adapting system environment to your language

- **Purpose:** the honest loading state for a generated pack (D-25).
- **Route:** `/onboarding/adapting` (also reached from **S17** language change).
- **Data & API:** `POST /v1/language-packs {language_query, pack_version, hint_tag}`; on `409` refresh `GET /v1/config` and retry once.
- **Components:** the typed language name (and `language_name_native` once the response header/first chunk arrives — the API returns the whole pack, so the native name appears at the end), `ProgressSteps` with `langpack.step_find` ("Finding your language"), `langpack.step_translate` ("Translating the app"), `langpack.step_check` ("Checking the words"), an indeterminate bar (steps advance on timers 0 s / 3 s / 15 s until the response), the exact headline `langpack.adapting` — **"Adapting system environment to your language..."** — sub-line `langpack.about_20s` ("About 20 seconds"), an English fallback line `langpack.english_meanwhile` ("The app stays in English until this finishes."), `btn.cancel`.
- **Primary action:** none while in progress; cancel is secondary. In the success state a 72 pt `btn.continue` stays on screen so the partial-pack and restart notices can be read (CL-028(d)).
- **States:** ● progress; ● success → pack stored, direction applied, an inline `banner.machine_translated` only when `pack.machine_translated` (S2 also shows the `machine_translation` / `partial_pack` banners for the active pack, so a bundled machine-translated pack chosen on S1 sees it on the next screen — CL-028(d)), native RTL restart prompt if direction changed; ● partial (`fallback_keys` non-empty) → `banner.partial_pack`; ● `422 language_unresolved` → `err.language_unresolved` + back to **S1**; ● `429/503` → error with `btn.choose_bundled` / `btn.retry`; ● offline → `state.lang_needs_internet`; ● timeout (60 s) → `err.timeout`.
- **Accessibility:** `aria-live="polite"` step announcements; reduce-motion swaps the bar for text. **RTL:** the screen flips as soon as `direction` is known from the pack (on success), before the next screen renders.

### S2 — What happens to your paper (consent)

- **Purpose:** Apple 5.1.2(i) / Play prominent-disclosure consent before the first upload, with copy that is literally true per tier (D-02).
- **Route:** `/onboarding/consent`; re-shown from **S0** on version/tier change; opened from **S17** "How your paper is handled" and from any `428`.
- **Data & API:** `GET /v1/config` → `data_use_tier`, `consent_version`, `privacy_policy_url`, `features.real_documents_allowed`.
- **Components:** title `consent.title` ("What happens to your paper"); `TierBadge` (`consent.badge.paid` "Paid service" · `consent.badge.unpaid` "Test build — free AI key" (red, icon + word) · `consent.badge.demo` "Sample mode" · `consent.badge.unknown` "Cannot confirm"); three pictogram rows (camera→cloud, server with a crossed-out disk, phone with a lock), each with one line: `consent.line1` (tiers `paid`, `unpaid`, `mixed`, `unknown` — not `demo`, where no AI service is contacted, so the line would not be literally true; COMPLIANCE_PRIVACY §4.2, CL-028(a)) "Your photo is sent to Google's AI (Gemini) to be read. Our server does not keep it."; line 2 by tier: `consent.line2.paid` "Google does not use your paper to improve its products. Google keeps a short safety log for a limited time, then deletes it." / `consent.line2.unpaid` "This test build uses a free AI key. Google may read and use what is sent. Do not send real papers. Sample papers only." / `consent.line2.demo` "Sample mode. No AI service is contacted. Your photo is only compared with our sample papers and is not kept." (D-02 as revised 2026-09-27: in mock mode a photographed page is still posted to our server for sample matching, so "Nothing leaves this device" would be false) / `consent.line2.unknown` "I cannot confirm how your paper would be handled right now. You can try a sample paper or come back later."; `consent.line3` "Papers you save stay only on this phone. You can delete everything any time." (web: `consent.line3.web` "Papers you save stay only in this browser, if you choose to keep them."); a fourth small line about "Hide parts": native, only when `features.hide_parts_server_masking` is true, `consent.line4.masks` "Parts you hide are blacked out on our server before Google's AI sees them."; web always `consent.line4.masks_web` "Parts you hide are blacked out on your device before anything is sent."; `consent.adults_only` "This app is for adults 18 and older."; link `consent.read_more` ("Read more") → opens the in-app privacy notice sheet (`features/onboarding/PrivacyNotice.tsx`, keys `privacy.notice.*` from COMPLIANCE_PRIVACY §4.5), which ends with `privacy.notice.full_policy` → `privacy_policy_url` in `expo-web-browser`; primary `consent.btn_continue` "I understand, continue" (72 pt); secondary `consent.btn_not_now` "Not now"; link `consent.try_sample` "Try a sample paper first".
- **Primary action:** `consent.btn_continue` → store `{consent_version, accepted_at, tier_seen, platform}` → `/(tabs)`.
- **States:** ● default per tier; ● unknown tier (config unreachable or `none`) → scan disabled, `consent.btn_continue` disabled with `consent.unknown_hint` ("Come back when you have internet to confirm this."), samples enabled; ● "Not now" (also Android back / swipe-dismiss) → `/(tabs)` with scan tiles disabled and `home.consent_needed`; ● re-consent (version/tier changed) → title prefix `consent.changed` ("This has changed:") with the changed line highlighted; ● unpaid/mixed → `consent.btn_continue` is **hidden** (real papers are blocked server-side; sample requests are exempt from consent), `consent.try_sample` becomes the primary action, `consent.btn_not_now` stays; **S3** disables real scans (COMPLIANCE_PRIVACY §4.2).
- **Accessibility:** heading levels; pictograms have `alt` text (`consent.pictogram1_alt` …); badge announces its word, not only its color. **RTL:** rows mirror; pictograms are not flipped; "Google", "Gemini" stay LTR-isolated.

### S3 — Home

- **Purpose:** one obvious action; a stable place to return to.
- **Route:** `/(tabs)/` (`(tabs)/index.tsx`).
- **Data & API:** `useServerConfig()` (cached), `session.consent`, `vault.reminders.list()` filtered client-side to the next 7 days (the `Vault` interface in BUILD_PLAN §4.2 has no `listUpcomingReminders`), network state, sample list (`GET /v1/demo/fixtures` cached; bundled manifest offline).
- **Components (top → bottom):** header with `home.need_help_now`; optional banners in this order: `banner.offline`, `banner.unpaid_tier`, `banner.sample_mode` ("Sample mode: the helper is not connected. Try the sample papers."), `banner.web_session_only`; **next-date card** when a saved reminder is within 30 days: `home.next_date` ("Date soon: {date} — {document_title}") → **S14**; primary CTA `home.scan_cta` **"Take a photo of a paper"** (72 pt, camera icon); tiles (56 pt, icon + word + one-line explanation): `home.tile_pick` "Pick a photo or PDF" / `home.tile_pick_sub` "Use a photo you already have, or a PDF file."; `home.tile_troubleshoot` "Stuck on a website?" / `home.tile_troubleshoot_sub` "Show me a screenshot. I will explain the screen."; `home.tile_clerk` "Show the clerk" / `home.tile_clerk_sub` "A card in English to hand to the person at the counter."; `home.tile_sample` "Try a sample paper" / `home.tile_sample_sub` "See how it works. Nothing of yours is sent." (always visible in `demo`/`unpaid` tiers; a smaller text link otherwise); trust footer with lock icon `home.trust_footer` ("Our server does not keep your paper. Papers you save stay only on this phone." / web variant `home.trust_footer.web`).
- **Primary action:** `home.scan_cta` → **S4** (native) or the picker path (web; the picker call is the first statement in `onPress`).
- **States:** ● first run (tiles explain themselves; no next-date card); ● returning (next-date card); ● offline (`home.offline_line` "No internet. I can take the photo now and read it later." under the CTA; CTA works; troubleshoot tile disabled); ● consent missing/withdrawn (`home.consent_needed` "Scanning is off until you accept how your paper is handled. Tap to read it." — tapping the CTA opens **S2**); ● unpaid tier (`home.unpaid_disabled` "Real papers are off in this test build. Try a sample paper."); ● quota cooling (after a recent `429 quota_exhausted`, CTA sub-line `home.busy_until` "The helper is busy. Try again at {time}." while still tappable); ● sample mode.
- **Copy:** `home.tile_clerk` opens **S10** with the most recent *saved* document's clerk message if one exists, else the generic card (§8.4).
- **Accessibility:** CTA `role="button"` with `accessibilityHint` `home.scan_hint` ("Opens the camera to photograph a paper."). **RTL:** tile order mirrors; icons non-directional.

### S4 — Capture

- **Purpose:** get readable pages with as little instruction as possible.
- **Route:** `/scan/capture` (native). On web this screen is skipped: `home.scan_cta` calls `ImagePicker.launchCameraAsync` (mobile browsers) or `launchImageLibraryAsync` and lands on **S5**.
- **Data:** `session.pages[]` (`CapturedPage[]`, BUILD_PLAN §4.2; max `limits.max_pages` = 12).
- **Components:** `CameraView` (back camera) with a page-shaped guide overlay; guidance line that changes by state: `capture.guide_fit` "Fit the whole page. Hold still.", `capture.guide_dark` "Too dark. Tap the light." (shown when the last capture's brightness heuristic is unavailable → shown after the user toggles torch off in low light; native has no pixel access so the line is driven by torch state only), `capture.guide_added` "Page {n} added."; torch toggle; shutter (80 pt, `capture.shutter_label` "Take photo of page {n}"); `capture.pick_from_photos` ("Pick from photos" → `ImagePicker.launchImageLibraryAsync`, system picker, no full-library permission); `capture.pick_pdf` ("Pick a PDF" → `DocumentPicker.getDocumentAsync({type: 'application/pdf'})`); thumbnail strip with page numbers; `capture.add_page` "Add another page"; `capture.done` "Done" (primary once ≥ 1 page).
- **Primary action:** shutter until one page exists, then `capture.done` → **S5**.
- **States:** ● permission not yet asked (rationale card `capture.permission_rationale` "I need the camera to photograph your paper. The photo is sent only to be read, and our server does not keep it." + `btn.allow_camera`); ● **camera-denied** (`state.camera_denied` "The camera is turned off for this app. You can turn it on in Settings, or pick a photo instead." + `btn.open_settings` + `btn.pick_instead`); ● page cap reached (`state.page_cap` "That is the most pages I can read at once ({max_pages}). Tap Done, or remove a page."); ● PDF picked → skips directly to **S5** with `review.pdf_summary`; PDF over `limits.max_pdf_bytes` → `err.payload_too_large` before upload; ● mixed images + PDF prevented in UI (`state.pdf_or_photos` "Choose photos or one PDF, not both."); ● offline → capture continues; **S5** CTA becomes `review.read_later_cta` ("Save to read later").
- **Accessibility:** shutter labelled with page number; haptic + `a11y.page_added` announcement on capture; thumbnails "Page {n} image, {rotated}". **RTL:** guidance text mirrors; thumbnail strip keeps document order (§5.2 rule 6); page numbers Western digits.

### S5 — Review pages

- **Purpose:** fix bad pages and hide sensitive parts before spending quota.
- **Route:** `/scan/review` (query `?sample=<fixture_id>` when opened from the sample picker; pages are then fetched from `GET /v1/demo/fixtures/{id}/pages/{n}` or the bundled `assets/fixtures/`).
- **Data:** `session.pages[]` (`CapturedPage`: `{id, uri, base64?, mimeType, width?, height?, rotation, masks[], source, fileName?, byteLength?}`); `settings.languageTag`, `settings.region`, `settings.preferences`; vault members.
- **Components:** page grid (2 columns; 1 on narrow); per-page `review.retake` / `review.rotate` / `review.remove`; drag handle to reorder (accessibility actions "Move up/down"); `review.hide_parts` **"Hide parts"** → mask editor (draw black rectangles over the thumbnail with `react-native-gesture-handler`; tap-to-place box with handles as the non-drag alternative; `review.hide_tip` "Hide ID numbers or anything you do not want read. I can still explain the rest."; `review.hide_note_receipt` "If you hide a case or receipt number, I cannot help you track that case."); output-language chip (defaults to UI language; opens the language grid in a sheet); optional collapsed "Whose paper is this?" member selector (`vault.whose_paper_optional`); optional `review.document_hint` chip row ("I think this is a…", maps to `DocumentType`; ≤ 8 common choices + "Not sure"); primary `review.read_cta` **"Read this paper"**; PDF variant shows the file card `review.pdf_summary` ("PDF · {size} MB") instead of thumbnails.
- **Primary action:** `review.read_cta` → **S6**. It builds `AnalyzeRequest` (§3 J-A step 7): web burns masks into the JPEG on a `<canvas>` and sets `masks: []`, `masks_applied_client_side: true`; native sends normalized `masks`.
- **States:** ● default; ● blurry hint (web only, canvas variance) `review.blur_hint` "Page {n} looks blurry. Retake?"; ● too many pages (cannot happen past S4; guard `state.page_cap`); ● offline → primary becomes `review.read_later_cta` and secondary `review.wait_for_internet` ("I will read it when internet is back" → session queue); ● sample (pages watermarked SAMPLE; `banner.demo_sample`; masks and member selector hidden); ● compressing (per-page shimmer ≤ 1 s).
- **Accessibility:** reorder via accessibility actions; mask editor announces "Box {i} added, covering part of page {n}"; `review.read_cta` hint `review.read_hint` ("Sends {n} pages to be read. Takes about a minute."). **RTL:** grid mirrors; rotation icon not mirrored; page order stays document order.

### S6 — Reading your paper

- **Purpose:** honest waiting; every failure has a next step (D-07).
- **Route:** `/scan/reading`.
- **Data & API:** `POST /v1/analyze` (120 s client timeout) with `X-Consent-Version`, `X-Install-Id`, `X-Request-Id`; on success → `session.currentAnalysis` → `/result/<analysis_id>`.
- **Components:** `ProgressSteps`: `reading.step1` "Reading the words" (0–6 s), `reading.step2` "Understanding" (6–18 s), `reading.step3` "Writing it for you" (18 s → response) — steps advance on timers, never claim completion early; trust line `reading.trust_line` ("Our server does not keep your paper."); estimated time `reading.eta` ("Usually under a minute"); `btn.cancel` (aborts the request; nothing to clean up server-side); after 20 s the tip `reading.tip_long` ("Long letters take longer. You can keep waiting."); after 60 s `reading.tip_still` ("Still working. Thank you for waiting."). Minimum on-screen time 1.5 s even when the mock answers in 300 ms, so the steps are visible.
- **Primary action:** none; `btn.cancel` returns to **S5** with pages intact.
- **States:** ● progress; ● **all-keys-exhausted** (`429 quota_exhausted`) → §5.4 row; ● `429 rate_limited`; ● `503` → same layout as quota; ● `422 content_blocked` → `err.content_blocked` with `btn.hide_and_retry` (→ **S5** mask editor) and `btn.get_help`; ● `403` → `err.unpaid_tier`; ● `428` → **S2** then auto-retry once; ● `413/415/400` → §5.4 rows returning to **S5**; ● **unreadable** (`200` with `quality.readable=false`) → `state.unreadable` with the page and `btn.retake`, no automatic re-send; ● degraded (`model_meta.quality=degraded`) → continue to **S7** with `banner.degraded_model`; ● network/timeout → `err.network`/`err.timeout` with `btn.save_to_read_later`.
- **Accessibility:** each step change announced via live region; on success `a11y.reading_finished` ("Reading finished. {n} dates found."). **RTL:** progress direction mirrors.

### S7 — Result

- **Purpose:** the three cards with anchors; everything else hangs off it.
- **Route:** `/result/[id]` (`result/[id]/index.tsx`). `id` = `analysis_id`; resolved from `session.currentAnalysis` first, then `vault.documents.get(id)`; unknown id → **S18**.
- **Data & API:** `AnalysisResult`; page images from `session.pages` / vault files (`vault.pages.uri`) / `page_thumbnails` (PDF); `resource_preview` inline; `POST /v1/feedback` from `FeedbackRow`; `vault.checklist` for checklist state and `SaveToVaultSheet` for save.
- **Components, in fixed order (each a `Card role="region"` with heading + `SpeakButton` unless noted):**
  1. **Emergency card** (only when `safety.emergency`) — the fixed **S19** content inline, above everything, not collapsible.
  2. **Scam card** (only when `scam_risk ∈ {possible, likely}`) — `scam.card.likely` / `scam.card.possible` with reason chips and the `scam_report` resources (see J-F).
  3. **Warning chips** row from `warnings[]` (§5.6) and `pages_unreadable`.
  4. **`UrgencyBanner`** (§5.5) with `btn.remind_me` / `btn.verify_date`.
  5. **Disclaimer header** `disclaimer.<disclaimer_kind>` (not a card; plain text, 16 pt, with speaker).
  6. **Banners**: `banner.machine_translated` (when the pack is machine translated), `banner.low_confidence_translation`, `banner.doc_language_differs`, `banner.degraded_model`, `banner.demo_sample`.
  7. **Card 1 — `card.what_is_this` "What is this?"**: `summary.title` (heading), `summary.body`; for Tier 3 / low-confidence packs `summary.body_en` beneath in small gray type with an "EN" chip; crop chips for `summary.span_ids`; sender line `card.sender_as_written` ("From: {sender}") in `<Bidi>` when `sender_as_written` is set, plus `sender_kind` word.
  8. **Card 2 — `card.asking_for` "What is it asking for?"**: one row per `demands[]` item: kind icon (`deadline`/`relative_deadline` calendar, `amount` coins, `document_requested` paper, `appointment` clock, `action` check, `contact` phone), `text`, `value_verbatim` in `<Bidi dir="ltr">` bold, `Crop` thumbnail (tap → **S8** scrolled to the block), `ConfidenceChip` (`confidence.high` "Clear" · `confidence.medium` "Probably" · `confidence.low` "Unclear — re-scan this part" in amber with `btn.rescan_part` → **S5**), `role` word when set (`role.hearing_date` "Hearing date", `role.response_due` "Answer by", `role.payment_due` "Pay by", `role.appointment` "Appointment", `role.notice_date` "Date of this notice", `role.decision_date` "Decision date", `role.move_date` "Move date", `role.expiry` "Expires"); for dates: `DateInfo` rendering — `stated` shows `value_verbatim` + `localized_line`; `estimated` shows `demand.estimate_prefix` "Estimate:" + `formula` + `demand.anchor` ("from: {anchor_quote}") + `demand.confirm_with_sender` "Confirm with the sender." + `demand.rule_link` "rule ↗" (opens `rule_source_url`; `rule_verification: likely` adds `demand.rule_likely` "Rule not yet re-checked"); `unresolved` shows the phrase verbatim + `demand.ask_sender_date` "Ask the sender which date this means."; `btn.remind_me` when `reminder_eligible`; `btn.call` **only** for `contact` demands whose number is verbatim on the page (`tel:`), labelled `btn.call_printed` "Call (number from your paper)"; `ambiguity_note` in italics; `documents[]` as a bullet list. Empty → `card.asking_nothing` ("This paper does not ask you to do anything. It is for your information.").
  9. **Unverified section** (only when `unverified[]` non-empty): heading `card.unverified` **"I saw these but could not confirm them on the page."**, rows struck through in gray with `verification_note`, `btn.rescan_part`. These never get `btn.remind_me`.
  10. **Card 3 — `card.plan` "Your step-by-step plan"**: `Checklist` of `plan_steps[]` (checkbox persists via `vault.checklist.set()` once saved; in session before), kind icon per `PlanStepKind`, resource chip (`plan.find_help` "Find help for this →" → **S11** with `resource_tags`) when `resource_tags` non-empty, `demand_id` link scrolls to the demand. `professional` steps end with the fixed referral word for the category.
  11. **Details and quotes** (`Collapsible`, `card.details` "Details and quotes"): table of every demand (verified and unverified) — label · `value_verbatim` · `ConfidenceChip` · `card.found_on_page` "Found on page {page}" · crop; tap → **S8**.
  12. **Words explained** (`card.glossary`): `glossary[]` rows `term_as_written` (`<Bidi>`) — `explanation`.
  13. **Questions you can ask them** (`card.questions`): `questions_to_ask[]` with `btn.copy` per row; sub-line `card.questions_sub` ("Ask the office that sent this paper.").
  14. **Red flags** (`card.red_flags`): `red_flags[]` sorted by `severity` desc; fixed-copy cards render `t(fixed_copy_key)` (D-20: `fixed.jury_summons`, `fixed.uscis_receipt_i765`, `fixed.pay_or_quit`, `fixed.eviction_summons`, `fixed.asylum_fee_notice`, `fixed.address_change_multi_agency`); model flags render `text` with `source_quote` chip; `injection_suspected` renders `warning.injection_masked`.
  15. **Get help nearby** (`card.help_preview`): top 3 `resource_preview[]` as compact rows (name, `why[0]`, `resource.verified_on`) + `help.see_all` → **S11**; when `resource_preview` is `[]` and `state` unset → `help.set_region_prompt` ("Tell me your state to find help near you." → **S17** region) plus the national fallbacks link.
  16. **Ask about this paper** (`btn.ask` → **S9**) with the first two `suggested_questions`-style prompts from `questions_to_ask`.
  17. **Footer**: `footer.ai_generated` + `footer.verify_with_sender`; `FeedbackRow surface=summary` ("Was this clear?"); `btn.report_problem`.
  18. **Action bar** (sticky bottom, 56 pt): `btn.save` (or `vault.saved_to` chip + `btn.move_member`), `btn.show_clerk` → **S10**, `btn.quick_sheet` → **S15**, `btn.read_all` (hear-it mode; toggles to `btn.stop`).
- **Primary action:** contextual — `btn.remind_me` on the banner when a date exists; otherwise `btn.save`.
- **States:** ● loading from vault (skeleton cards); ● partially verified (section 9); ● unreadable (never reaches S7; S6 handles it); ● partial pages (chips); ● degraded; ● demo; ● low-confidence translation; ● document language differs; ● unpaid (banner); ● saved/unsaved; ● offline (everything renders; `btn.ask` disabled with `state.offline_disabled`; help preview shows cached results); ● emergency (section 1 first, live region `a11y.emergency_shown`); ● no facts (`card.asking_nothing` and banner `urgency.info.no_action`).
- **Copy rules:** `summary.body` ≤ 3 sentences (server); every model sentence has been contact-filtered and phrasing-linted (server); the client never concatenates model text into fixed sentences except via `{placeholders}` designed for it.
- **Accessibility:** each card `role="region"` + heading; `btn.read_all` plays cards sequentially with the stop bar pinned; per-pane `accessibilityLanguage`: source quotes = `detected_language`, everything else = `target_language`; crops have `alt` = the quote; live region on load. **RTL:** cards mirror; verbatim values and crops LTR-isolated; kind icons not mirrored; `localized_line` may add Persian/Arabic digits on its own line, never replacing the verbatim.

### S8 — Original and translation (side by side)

- **Purpose:** let the user or a bilingual helper verify the machine; the anti-hallucination viewer.
- **Route:** `/result/[id]/source` (query `?block=<span_id>` scrolls to and highlights a block; `?page=<n>`).
- **Data:** `original_text[]` (blocks with `bbox`, `is_unclear`, `is_handwriting`), `translated_text[]`, page images (session/vault) or `page_thumbnails`.
- **Components:** page image with tappable highlight boxes (from `bbox`, normalized to `PageText.width/height`; missing `bbox` → the block is listed without a box and the page shows the quote text only); pinch-zoom; page pager with Western digits; mode toggle `source.mode_original` / `source.mode_both` / `source.mode_translation` (default `both`); block list — each block: source text (real text, `lang = detected_language`), translation line (for pages ≤ `translate_full_max_pages` the full `translated_text[page].text` is aligned by block order; for partial translations only referenced blocks have translations and the rest show `source.not_translated` "Not translated"), `SpeakButton` per block (source voice for source text, UI voice for translation), badges `source.unclear` "[unclear]" and `source.handwriting` "Handwriting"; masked SSNs appear as `***-**-1234`. Tablet/desktop (≥ 900 px): image left/right of the list (side by side); phone: image above, list below.
- **Primary action:** none (viewer); back returns to the S7 position.
- **States:** ● default; ● block selected (box highlighted, list scrolled); ● no bbox for the block (`source.no_box` "Position on the page not available; the words are: {quote}"); ● translation partial (`warning.translation_partial`); ● PDF without thumbnails (`include_page_thumbnails=false` cannot happen for PDFs — client always sets `true` for PDFs); ● images kept OFF in vault (`source.no_image` "Page images were not kept for this paper. Only the words are shown." with the block list).
- **Accessibility:** block text is real text, focusable, with `lang`; highlight boxes are buttons labelled "Block {i} on page {n}: {first 8 words}". **RTL:** the transcript pane follows the document's direction (`detected_language`); the translation pane follows the UI direction; the page image is never mirrored; mode toggle mirrors.

### S9 — Ask about this paper (grounded chat)

- **Purpose:** the next question, answered only from the paper, with a referral when it is not the app's place to answer.
- **Route:** `/result/[id]/chat`.
- **Data & API:** `POST /v1/chat` `{analysis: AnalysisContext, messages: last ≤ limits.max_chat_history (8), question ≤ limits.max_question_chars (1000), target_language, demo_sample_id}` (30 s timeout); `AnalysisContext` built by `features/chat/useChat` = `{analysis_id, category, document_type, detected_language, sender_as_written, summary, demands, unverified, plan_steps, red_flags, glossary, original_text (≤ 60 000 chars, oldest pages truncated first), urgency}`; history lives only on the device (in `session`; saved with the document when the user saves).
- **Components:** scope line `chat.scope` ("I can only answer from this paper. This is information, not legal or medical advice."); `suggested_questions` chips (from the last `ChatAnswer`, initially `questions_to_ask` and two fixed starters by category: `chat.starter.miss_date` "What happens if I miss the date?", `chat.starter.pay_now` "Do I have to pay this now?", `chat.starter.bring` "What should I bring?"); message list (user bubbles right in LTR, mirrored in RTL); assistant bubble = `answer` + `grounded_quotes[]` as chips `chat.from_your_paper` ("From your paper, page {page}: “{text}”" LTR-isolated; tap → **S8** `?block=`) + `not_in_document` line `chat.not_in_document` ("The paper does not say.") when true + referral template when `refer_to_professional ≠ none` (`chat.refer.lawyer_or_accredited_rep` "A licensed lawyer or a DOJ-accredited representative can advise you about your case. Find one in Get help." / `chat.refer.clinician` "Ask your doctor, nurse or pharmacist what this means for you." / `chat.refer.housing_counselor` "A housing lawyer or counselor can advise you. Find one in Get help." / `chat.refer.benefits_office` "The office that sent this paper can tell you what happens next. Its number is on the paper." / `chat.refer.sender` "Ask the sender. Their contact is on the paper.") with `btn.get_help`; refusal bubbles when `refusal_kind ≠ none` render the fixed template instead of `answer` unless `answer` is non-empty (then `answer` first, template second): `chat.refusal.eligibility` "I cannot say whether you qualify. The paper says what it says; a professional can tell you what it means for you." · `chat.refusal.filing_advice` "I cannot tell you what to file or send. I can explain what the paper asks for." · `chat.refusal.outcome` "I cannot predict what will happen. No one can promise a result." · `chat.refusal.medical_interpretation` "I cannot say what this means for your health. Ask your doctor, nurse or pharmacist." · `chat.refusal.drafting` "I cannot write letters or fill in forms. A professional or the office itself can help with that." · `chat.refusal.contact_request` "I only share phone numbers and websites printed on your paper or checked by a person. See Get help nearby." · `chat.refusal.out_of_scope` "That is outside this paper. I can only help with what is written here."; `distress_acknowledged` adds nothing client-side (the model's own warm sentence is in `answer`); `SpeakButton` and `FeedbackRow surface=chat` on every assistant bubble; text field with visible label `chat.input_label` ("Your question") and a 1000-character counter; send button; mic button hidden (LATER).
- **Primary action:** send.
- **States:** ● empty (starters); ● sending (typing indicator ≤ 30 s); ● `not_in_document`; ● refusal; ● emergency (`ChatAnswer.safety.emergency` → **S19** opens as a modal over the chat); ● offline (`state.offline_disabled`, history readable); ● `429/503` (§5.4, without "Save to read later"); ● `422 content_blocked` → `err.content_blocked` (chat variant without "Hide parts"); ● history cap reached (oldest turns dropped silently; note `chat.history_cap` "I remember the last 8 messages.").
- **Accessibility:** new bubbles announced; input labelled; chips are buttons. **RTL:** bubbles mirror; quotes LTR-isolated with an "EN" (or detected language) chip.

### S10 — Show the clerk (hand-the-phone mode)

Full detail in §8. Summary: **Route** `/result/[id]/clerk` (`id = generic` reserved for the no-analysis card — see §16.2). LTR, high-contrast, ≥ 24 pt English card from `clerk_message.english`; `session.clerkMode = true` hides the tab bar and blocks vault routes; exit only via 1.5 s long-press on `clerk.back_to_me` rendered in the user's language and direction; `btn.read_aloud_en` speaks the English card; `btn.copy_text`; `clerk.brightness_tip` line (§16.2 item 2). **States:** ● from analysis; ● generic; ● no TTS English voice (button hidden); ● web (copy text emphasised; long-press works with mouse/touch; keyboard alternative: hold Space 1.5 s).

### S11 — Get help nearby (Action Hub)

- **Purpose:** verified routing with a bring-this checklist; never asks status.
- **Routes:** `/(tabs)/help` (no document: need tiles) and `/result/[id]/help` (for this paper; query `?focus=<resource_id>` expands one card; `?tags=a,b` from plan steps).
- **Data & API:** `POST /v1/resources/match` (30 s) with `tags` (from `resource_tags` or the tapped need tiles), `document_type`, `category`, `state`, `county` (null in v1; no county picker), `zip3`, `language`, `institutions_as_written` (≤ 10), `scam_risk`, `emergency`, `limit: 8`; `GET /v1/resources?tag=…&state=…&q=…` for browse/search on the tab; bundled national-fallback subset for offline; `POST /v1/feedback kind=resource_problem surface=resource resource_id`.
- **Components:** region control `help.region` ("Where you live: {state} {zip3}" → **S17**; `help.set_region_prompt` when unset); language filter chip (default UI language); on the tab: need tiles (56 pt, icon + word) mapping to tags — `need.legal` "Legal help" → `immigration_legal_help`; `need.court` "Court papers" → `court_notice`, `removal_proceedings`; `need.medical_bill` "Medical bills" → `medical_bill`, `charity_care`; `need.insurance` "Insurance letters" → `insurance_denial`, `medicare_appeal`; `need.clinic` "A doctor without insurance" → `primary_care_uninsured`; `need.food` "Food" → `food`, `snap`, `wic`, `school_meals`; `need.housing` "Housing or eviction" → `eviction`, `housing_counseling`, `rent_assistance`; `need.utilities` "Utility shutoff" → `utility_shutoff`; `need.benefits` "Benefits letters" → `benefits_navigation`, `medicaid_renewal`, `ssa_benefits`; `need.school` "School" → `school_enrollment`, `special_education`, `homeless_students`; `need.work` "Work and pay" → `workers_rights`, `wage_theft`, `discrimination`, `workplace_safety`; `need.tax` "Tax letters" → `tax_notice`, `itin`; `need.scam` "Report a scam" → `scam_report`; `need.crisis` "Someone is in danger" → `crisis`, `domestic_violence`, `trafficking` (also opens **S19**); `need.interpreter` "An interpreter" → `language_access`; results grouped `help.near_you` ("Near you") / `help.anywhere_in_us` ("Anywhere in the U.S.") using `serves.scope`; each `ResourceMatch` card (`Collapsible`, expanded when focused): `resource.name` (+ `name_note`), `what_it_does[language] ?? what_it_does.en` (with "EN" chip on fallback), `why[]` chips, `cost` badge (`resource.free` "Free" / `resource.sliding` "Pay what you can" / `resource.paid` "Costs money" / `resource.unknown_cost` "Cost not known"), languages line (`resource.languages` "Speaks: {list}"; `interpreters_200+` → `resource.interpreters` "Interpreters for 200+ languages"), `btn.call` (`tel:` `phone`; label announces the organization), `btn.website` (`expo-web-browser`), `tty`/`text_line`/`hours` lines, `resource.verified_on` chip ("Verified on {date}") with `link_health` variants (`ok` plain; `unknown_403`/`js_rendered` → `resource.link_unknown` "Website could not be auto-checked"; `unverified` → `resource.link_unverified` "Not yet checked by us"; `broken` → card hidden), `verified_on` older than 120 days → `resource.stale` "Last checked over 4 months ago"; eligibility note rendered as `status_note.<eligibility_note_key>` (copy is the reviewed source in RESOURCE_DB §3.3: `status_note.lsc_restricted` **"This organization usually cannot help people without immigration papers, except survivors of violence or trafficking."** + link `help.lsc_alternative` "If that is not you, try these instead" → `POST /v1/resources/match {tags: [immigration_legal_help]}`; `status_note.residency_required` "You must live in their service area. Bring proof of your address."; `status_note.waitlist` "There is a waiting list right now. Ask to be added."; `status_note.appointment_required` "Call first to make an appointment."; `status_note.hhs_funded_health` "You can ask for a free interpreter here."; `status_note.not_endorsed` "The government publishes this list but does not endorse anyone on it."; `status_note.manual_verify` "We could not confirm every detail of this listing. Check before you go."), `eligibility_plain[language] ?? en`, `resource.warnings[]` fixed keys already prefixed on the wire (e.g. `warn.jury_never_check_citizen`, `warn.jury_never_register_to_vote`, `warn.ask_for_plain_language_summary`; registry and copy in RESOURCE_DB §4.3), **Before you go, bring** `checklist[]` (per result — `ResourceMatch.checklist`, there is no response-level checklist; `Checklist`; each `ChecklistItem.key` rendered as `prepare.<key>`, falling back to `text_en`; state persisted per document), `btn.save_quick_sheet` → **S15** with the resources embedded, `FeedbackRow surface=resource`; `national_fallbacks[]` always at the bottom under `help.always` ("Always available"); `notes_keys[]` rendered as info lines (`notes.set_region_for_local_help`, `notes.county_unknown`, `notes.no_local_results`, `notes.lsc_restricted_explained`, `notes.resource_text_english_only`, `notes.verify_before_going` — RESOURCE_DB §4.3).
- **Primary action:** `btn.call` on the first result (or `btn.website` when no phone).
- **States:** ● loading (skeleton); ● no region (`help.set_region_prompt` + national results only); ● no local matches (`state.no_local` "Nothing verified near you yet. These national services can help." + fallbacks); ● offline (`help.offline_cached` "No internet. This is the last list I found for this paper." or bundled fallbacks only); ● `scam_risk=likely` (scam card first, `scam_report` results first); ● `emergency=true` (**S19** first, crisis lines first); ● browse/search on the tab (`GET /v1/resources` with `q`); ● error (§5.4; national fallbacks still shown from the bundle).
- **Accessibility:** phone buttons announce "Call {organization}, {number grouped in digits}"; cards are regions. **RTL:** mirrored; phones, URLs, hours LTR-isolated.

### S12 — My papers (family vault)

Full detail in §9. **Route** `/(tabs)/papers`. Member chips row (`vault.me` "Me" + members with initials/color + `vault.add_member` "Add someone"); document rows (title = `summary.title` or `vault.title_fallback` "{document_type word} · {date}", category icon, `created_at`, `next_date_iso` badge, `vault.not_read_yet` chip when `analysis_json` is null, member dot); search (title, sender, category words); sort by next date then newest; `btn.reminders` header link → **S14**. **States:** ● empty (`vault.empty` "Papers you save stay only on this phone. Nothing is saved until you tap Save." + `btn.scan`); ● locked (PIN, SHOULD); ● many (group by member, then month); ● web session-only banner; ● web IndexedDB opt-in active (`vault.web_kept` "Kept in this browser (not encrypted by the app)"). Row tap → **S7** from storage. Long-press / swipe → `btn.delete_paper`, `btn.move_member`.

### S13 — Member detail

- **Route** `/papers/member/[id]`. Header with initials/color, `member.rename`, `member.color`; documents for this member; `btn.move_all`; `member.delete` ("Delete {name} and all their papers" → confirm `member.delete_confirm`). Deleting "Me" is not possible (rename only). **States:** ● empty; ● confirm delete. **RTL:** mirrored.

### S14 — Reminders

Full detail in §10. **Route** `/reminders` (query `?doc=<analysis_id>`). List sorted by `fire_at` grouped by document: document title, member dot, demand `text`, `value_verbatim` (`<Bidi>`), `localized_line`, toggle per reminder, `reminders.add_own` "Add my own date" (title ≤ 60 chars + date picker + optional note ≤ 100 chars; stored as a document-less reminder); header toggle `reminders.lockscreen_detail` ("Show details on the lock screen") with explanation `reminders.lockscreen_explain`; web: `reminders.web_explain` + `btn.download_ics` per item and `btn.download_all_ics`. **States:** ● empty (`reminders.empty` "No dates saved yet. When I find a date on a paper, tap Remind me."); ● permission denied (`reminders.permission_denied` "Reminders are off for this app. The list still works here. You can turn them on in Settings." + `btn.open_settings`); ● past (grayed, `reminders.past` "Passed"); ● estimated dates cannot be added (`reminders.estimate_blocked` "This date is an estimate. Confirm it with the sender, then add your own date."); ● web.

### S15 — Quick sheet

- **Purpose:** the paper that goes to the appointment; works offline forever after.
- **Route:** `/result/[id]/quicksheet`.
- **Data & API:** built client-side by `features/quicksheet/` from `AnalysisResult` + the last `ResourceMatchResponse` for this document (resource names/phones only; contacts stripped by the filter are never re-added). Web PDF: `POST /v1/quicksheet/pdf` `{title, language_tag, direction, font_hint, sections (≤ 8 × ≤ 40 lines), resources (≤ 8 × `{name, phone?, url?}`, DB entries only), footer, generated_on (required)}` (30 s) → `application/pdf` blob.
- **Components:** preview of the text-only sheet: title (`summary.title` + `quicksheet.title_suffix` "— quick sheet"), sections with localized heading and English `heading_en` under it (for the clerk): `card.what_is_this` / `card.asking_for` / `card.plan` / `quicksheet.dates` "Dates" / `quicksheet.bring` "Bring" / `quicksheet.help` "Who can help" (name + phone) / `quicksheet.questions`; footer `quicksheet.footer` ("Made with a computer from your paper. It can be wrong. Confirm dates with the sender. Made on {date}."); buttons: native `btn.share_pdf` (`Print.printToFileAsync({html})` with fonts embedded as base64 data URIs and `dir` set → `Sharing.shareAsync(uri, {mimeType: 'application/pdf'})`, gated by `isAvailableAsync()`), web `btn.download_pdf` (server PDF) and `btn.print` (the sheet HTML printed from a hidden same-origin `<iframe srcdoc>` — `features/quicksheet/share.ts` `printHtmlInFrame`; expo-print 57's web `printAsync` ignores `html` and prints the whole app page, so it is only the no-DOM fallback — CL-040), all platforms `btn.copy_text` and `btn.read_aloud`.
- **Primary action:** `btn.share_pdf` (native) / `btn.download_pdf` (web).
- **States:** ● default; ● sharing unavailable (`state.share_unavailable` "Sharing is not available here. Copy the text instead." → `btn.copy_text` primary); ● offline on web (`btn.download_pdf` disabled with `state.offline_disabled`; `btn.print` still works); ● server error (§5.4 → `btn.print` fallback); ● long sheet (sections truncated to 40 lines with `quicksheet.truncated` "…and more in the app").
- **Accessibility:** real text; buttons labelled. **RTL:** HTML has `dir="rtl"` and Noto fonts; English section headers stay LTR; numbers LTR-isolated.

### S16 — Stuck on a website? / Is this a scam? (troubleshoot)

- **Purpose:** portal rescue and scam check from a screenshot (D-13).
- **Route:** `/troubleshoot` (query `?mode=scam_check`).
- **Data & API:** `POST /v1/troubleshoot` (60 s) `{screenshot: PageInput (one image, no PDF; required even with `demo_sample_id` — the server then reads the fixture's screenshot and ignores these bytes), user_goal ≤ limits.max_user_goal_chars (300), mode, portal_hint, target_language, demo_sample_id, client_platform}`; `X-Consent-Version` required (except demo); `POST /v1/resources/match` for `resource_tags`.
- **Components:** mode chips `troubleshoot.mode_portal` "Stuck on a website" / `troubleshoot.mode_scam` "Is this a scam?"; `troubleshoot.pick_screenshot` "Pick a screenshot" (system picker; on web the call is the first statement of `onPress`); preview thumbnail with `review.hide_parts` (masks allowed; same burn/mask rules as S5); `troubleshoot.goal_label` "What were you trying to do?" (optional, 300 chars); portal hint chips (`portal.benefits_portal` "Benefits website", `portal.uscis_account` "USCIS account", `portal.eoir_portal` "Immigration court site", `portal.school_portal` "School site", `portal.hospital_portal` "Hospital or clinic site", `portal.insurer_portal` "Insurance site", `portal.irs_portal` "IRS site", `portal.bank` "Bank", `portal.other` "Other"); standing guard line `troubleshoot.credential_guard` **"Never type passwords, card numbers or ID numbers into this app. I will never ask for them."**; primary `troubleshoot.cta` "Explain this screen" / in scam mode `troubleshoot.cta_scam` "Check this for me".
- **Result cards:** scam card first when `scam_risk ≠ none` (§J-F); `troubleshoot.card_screen` "What this screen is" (`screen_summary`); `troubleshoot.card_error` "What the red text means" (`error_text_quoted` LTR-isolated quote chip + `error_meaning`; hidden when null); `troubleshoot.card_steps` "Do this next" (`steps[]` ordered, `ui_target_as_written` in `<Bidi>` bold, each with a checkbox); `troubleshoot.card_cautions` "Careful" (`cautions[]`); credential guard emphasised red with `troubleshoot.credential_detected` ("This screen asks for a password or payment. Only type them on the official website, never here.") when `asks_for_credentials_or_payment`; `red_flags[]`; `troubleshoot.ask_person` "Ask a person" → **S11** with `resource_tags` (shown always; emphasised when `needs_human_help`); `confidence` chip; `disclaimer.general_information`; `FeedbackRow surface=troubleshoot`; `btn.save_evidence` (scam mode).
- **States:** ● empty (example illustration + the guard line); ● loading (`ProgressSteps` 2 steps: `troubleshoot.step_read` "Reading the screen", `troubleshoot.step_explain` "Explaining"); ● emergency (`TroubleshootResult.safety.emergency` — the D-14 lexicon ran over `screen_text` and `user_goal` → **S19** opens as a modal first, then the result); ● cannot tell (`confidence: low` + `needs_human_help` → `state.cannot_tell` "I am not sure what this screen wants. Ask a person." with `troubleshoot.ask_person` primary); ● scam likely/possible; ● unreadable (`state.unreadable_screenshot` "I could not read this screenshot. Take it again with the whole screen visible."); ● offline; ● `429/503/422/403/428` per §5.4; ● demo (sample screenshot `portal_file_too_large`).
- **Accessibility/RTL:** as S7; quoted UI strings stay LTR with an "EN" chip.

### S17 — Settings

- **Route:** `/(tabs)/settings`. Sections and controls (all persisted in `store/settings.ts` via `kv`, except consent/vault which live in their stores):
  1. **`settings.language`** — current language row (native name, `machine_translated` label `settings.machine_translated` "Translated by a computer" or `settings.reviewed_by` "Reviewed by {name}") → **S1**; `settings.voice` voice picker (from `getAvailableVoicesAsync()` filtered to `tts_tag`/`tts_fallback_tag`), rate slider (0.8–1.2), `btn.test_voice`; `settings.hear_mode_default` toggle ("Read results aloud automatically"); native RTL restart prompt if pending (`direction.restart_pending`).
  2. **`settings.reading`** — text size (S/M/L/XL with live preview), `settings.high_contrast` toggle, note that reduce-motion follows the phone.
  3. **`settings.region`** "Where you live" — state picker (50 states + DC + PR + territories, `settings.state_none` "Not set"; state and territory names stay English proper nouns with no `en.json` keys — the postal names users see on their own papers, CL-038(c)/CL-056), `settings.zip3` "First 3 digits of your ZIP (optional)" with explanation `settings.zip3_why` ("Only the first 3 digits. Enough to find help near you, not enough to find your home."), `btn.clear_region`.
  4. **`settings.tone`** "Tone and calendar" — `settings.tone_plain` "Plain" / `settings.tone_formal` "Formal" (→ `Preferences.tone`); `settings.calendar_notes` chips (`Ramadan`, `Eid`, `Sabbath`, `Lent`, `Lunar New Year`, `Diwali`, `Nowruz` + custom ≤ 40 chars; ≤ 5 selected → `Preferences.calendar_notes`); `settings.date_format` auto / month-day-year / day-month-year; explanation `settings.tone_why` ("Used only to word your steps kindly, for example around a fast or a holiday. Never saved on our server.").
  5. **`settings.papers`** "Your saved papers" — `settings.keep_pages` "Keep page images" (default ON native, OFF web; explanation `settings.keep_pages_why`), `settings.hide_ids` "Hide ID numbers in saved copies" (default OFF; `settings.hide_ids_why` "Hides A-numbers and receipt numbers. Turn on only if you do not need them to check your case."), `settings.lockscreen_detail` (mirrors S14), `settings.pin` "App PIN" (SHOULD; hidden on web), web only: `settings.web_keep` "Keep on this device (not encrypted by the app)" and `settings.web_clear_on_close` "Clear when I close this tab".
  6. **`settings.data`** "How your paper is handled" — `TierBadge` + consent status (`settings.consent_accepted_on` "You agreed on {date}" / `settings.consent_not_given`), `btn.read_privacy` → the in-app privacy notice sheet (`privacy.notice.*`, COMPLIANCE_PRIVACY §4.5; its last row links to `privacy_policy_url`), `btn.review_consent` → **S2**, `btn.withdraw_consent` ("Stop sending papers" → sets consent to withdrawn, disables scan/chat/troubleshoot, then `settings.wipe_offer` "Do you also want to delete everything saved on this phone?" with `btn.delete_everything` / `settings.keep_saved`). On web the wipe button reads `btn.delete_everything_web`.
  7. **`settings.sample_mode`** — toggle `settings.sample_toggle` "Sample mode" with `settings.sample_why` ("Use sample papers with a pretend helper. Nothing of yours is sent."); forced ON with `settings.sample_forced` ("This server only has sample papers.") when `provider == mock`.
  8. **`settings.delete_everything`** — `btn.delete_everything` "Delete everything on this phone" → dialog `wipe.title` / `wipe.body` ("This removes all saved papers, members, reminders and settings from this phone. It cannot be undone.") / `wipe.confirm` "Yes, delete everything" / `btn.cancel`; runs `storage/wipe.ts` (DB + files + kv + secure + consent + install id + pack cache), cancels scheduled notifications, then restarts at **S1**.
  9. **`settings.about`** — app version, `contract_version`, pack version (short hash) + `reviewed_by`, `resource_db_version`, `rules_version`, model IDs from `ServerConfig.models` (`settings.models` "Helper models: {pro}, {fast}"), the fixed "what it does not do" list (§1.3), licenses, `btn.report_problem` (feedback sheet with kinds only), `btn.privacy`.
  10. **`settings.developer`** (only when `EXPO_PUBLIC_APP_ENV != production`) — `settings.developer_api_url`, install id (`btn.rotate_install_id`), raw `ServerConfig`, force-tier preview for screenshots.
- **States:** ● offline (server-derived rows show cached values with `state.cached`); ● restart pending; ● PIN locked (SHOULD). **RTL:** mirrored; version strings LTR-isolated.

### S18 — Not found / error boundary

- **Route:** `+not-found.tsx`; also the root error boundary. Copy `notfound.title` "I could not find that page." / `notfound.body` "Nothing was lost. Your saved papers are still here."; `btn.go_home`; `btn.report_problem`. Never shows a stack trace to the user (developer builds show a collapsible).

### S19 — Emergency card (modal)

- **Purpose:** fixed-copy life-safety card; the first thing shown when triggered (D-14).
- **Route:** `/emergency` (presentation `modal`); opened by `home.need_help_now` on every screen, by `AnalysisResult.safety.emergency`, by `ChatAnswer.safety.emergency`, and by the `need.crisis` tile.
- **Components:** title `emergency.title` "Need help now?"; four fixed rows with 72 pt call buttons: `emergency.911` "If someone is in danger or very sick, call 911." → `btn.call_911` "Call 911" (`tel:911`); `emergency.988` "If you are thinking about hurting yourself, call or text 988. It is free and private." → `btn.call_988` "Call 988", `btn.text_988` "Text 988" (`sms:988`); `emergency.poison` "If someone swallowed something dangerous, call Poison Help 1-800-222-1222." → `btn.call_poison`; `emergency.dv` "If someone at home is hurting you, call 1-800-799-7233 or text START to 88788." → `btn.call_dv`, `btn.text_dv`; note `emergency.free_us` "These numbers are free and work anywhere in the U.S."; `emergency.more_help` link → **S11** with `emergency: true`; `btn.close` "Close". When triggered by a paper, a one-line context `emergency.triggered_by` ("I saw words about {kinds} on this paper. If this is happening now, use these numbers.") with `emergency_kinds` mapped to fixed words (`emergency.kind.chest_pain` "chest pain", `emergency.kind.breathing`, `emergency.kind.overdose`, `emergency.kind.poison`, `emergency.kind.self_harm`, `emergency.kind.stroke`, `emergency.kind.bleeding`, `emergency.kind.allergic`, `emergency.kind.violence`).
- **States:** ● manual (no context line); ● triggered; ● web (`tel:`/`sms:` open the dialer on mobile browsers; on desktop show the numbers large with `emergency.desktop_note` "Use a phone to call.").
- **Accessibility:** modal traps focus; numbers announced digit-grouped; every line has a speaker. **RTL:** mirrored; numbers LTR-isolated; never model-generated text.

---

## 7. Copy and tone guidelines

### 7.1 Voice

**Supportive peer, not an authority.** The app talks like a trusted neighbor who has read a lot of these papers: calm, plain, warm, never scolding, never panicking, never promising. It says what the paper says, what people usually do next, and who can advise. It never says what *will* happen to *you*.

| Rule | Do | Don't |
|---|---|---|
| Reading level | Grade ≤ 5 for every base string (CI check). Short sentences. One idea per sentence. Everyday words. | Acronyms without a two-word gloss ("USCIS (the immigration office)") |
| Words | "paper", "letter", "bill", "notice", "form"; "the helper"; "the office that sent this"; "a licensed lawyer or a DOJ-accredited representative"; "your doctor, nurse or pharmacist" | "document", "AI", "model", "Gemini" (outside S2/About), "the system", "client", "user" |
| Danger | State the date and who to call. "This date matters. Go, or you can lose automatically." | "You may be deported", "URGENT", CAPS, exclamation marks, red text without an icon and a word |
| Certainty | "The paper says…", "usually", "you can ask", "before the date" | "you qualify", "you are eligible", "you should file/appeal/pay/sign", "you will win/lose/get", "you do not have to", "this means you have" |
| Numbers | Always as printed, LTR-isolated, Western digits; a localized line may be *added* | Translated, reformatted or rounded dates and amounts |
| Emotion | One warm sentence when the user sounds afraid (chat `distress_acknowledged`), then facts | Reassurance about outcomes ("Don't worry, you will be fine") |
| Children | Every sentence safe for a child to read aloud to a parent | Anything that would frighten or shame the family in front of a child |
| Length | Card 1 ≤ 3 sentences; chat ≤ 4 sentences; steps ≤ 2 sentences each | Walls of text; nested bullets |
| Buttons | Verb first, ≤ 3 words: "Take a photo", "Remind me", "Show the clerk" | "OK", "Submit", emoji |

### 7.2 Information, not advice (D-17) — what the phrasing linter catches and how the UI shows it

The server lints every user-facing sentence (`analysis/phrasing.py`). A match gets one fast-model rewrite using the template **"The paper says X. A {professional} can tell you what it means for you."**; if still matching, the fixed hedge is substituted and `verification.phrasing_rewrites` increments. The client shows no trace of the rewrite (no "edited" marker) but the `FeedbackRow` remains. Reference rewrites the golden set asserts:

| Model draft (forbidden) | Shipped |
|---|---|
| "The notice itself does not require you to leave; a court hearing would have to happen first in Virginia." | "In Virginia, a landlord generally needs a court order before an eviction can happen. Confirm with the legal helpline today." |
| "You qualify for financial assistance because your income is under 400% FPL." | "The paper says financial assistance is for households under 400% of the poverty level. The hospital's financial assistance office can tell you if that includes you." |
| "Your potassium is high, which can be dangerous." | "The paper lists potassium as H (high) next to the normal range. Ask your doctor or nurse what this means for you." |
| "You should appeal within 180 days." | "The paper says an internal appeal can be asked for within 180 days of the notice. A benefits counselor or your plan can advise you." |

Fixed professional words by category: immigration/court/civic/employment-legal → "a licensed lawyer or a DOJ-accredited representative"; medical → "your doctor, nurse or pharmacist"; housing → "a housing lawyer or counselor"; benefits → "the office that sent this paper"; school → "the school office or a parent center"; tax → "the IRS or a free tax helper"; other → "a professional".

### 7.3 Fixed copy blocks (never model-written; keys in Appendix A)

- Disclaimers per `DisclaimerKind` (§5.6).
- Urgency headlines (§5.5).
- Fixed high-severity notices (`fixed.*`, D-20): `fixed.jury_summons` "You must answer this form. If you are not a U.S. citizen, mark *not a citizen* and send it back. Never check 'citizen' and never register to vote — it can permanently harm your immigration case."; `fixed.uscis_receipt_i765` "A receipt for a work-permit renewal filed on or after October 30, 2025 is **not** proof you can work. Ask a lawyer or DOJ-accredited representative about a possible work gap."; `fixed.pay_or_quit` "This is not a court order. Only a court can make you leave."; `fixed.eviction_summons` "The court date on this paper is the date that matters. Go, or you can lose automatically."; `fixed.asylum_fee_notice` "There is no fee waiver for this fee."; `fixed.address_change_multi_agency` "If you move, the court needs its own address form (EOIR-33). USPS forwarding does not update the court or USCIS."
- Scam cards (`scam.card.likely`, `scam.card.possible`) and reason chips (`scam.<reason>`).
- Emergency card (S19).
- Consent lines (S2), permission strings (`app.json`), notification bodies (§10), quick-sheet footer, chat refusal/referral templates (S9), clerk template (§8).

### 7.4 Language-pack translation rules (fed to `langpack.md`, enforced by `packs/qa.py`)

Plain everyday words a 10-year-old understands, in the respectful warm register used with an elder; keep `{placeholders}` exactly; keep "ProxyHealth" unchanged; keep agency names and form numbers (USCIS, Medicaid, SNAP, I-797C) as written and add a short native gloss only for keys ending in `_explained`; ≤ 1.6× English length (2× for `btn.*`); no HTML; no digit runs that look like phone numbers; report `direction`, `script`, `digit_system`; untranslatable keys copied in English and listed in `fallback_keys`. The single string `langpack.adapting` is the user's requested English; packs translate it, the English is never paraphrased.

### 7.5 Naming and capitalization

Sentence case everywhere. Product name "ProxyHealth AI" (with the tagline on first use per screen). Tabs: "Home", "My papers", "Get help", "Settings". Cards: "What is this?", "What is it asking for?", "Your step-by-step plan", "Details and quotes", "Words explained", "Questions you can ask them", "Red flags", "Get help nearby", "Ask about this paper". The unverified heading is exactly "I saw these but could not confirm them on the page."

---

## 8. The "hand this phone to the clerk" card (S10)

### 8.1 Purpose

The moment of highest indignity is the counter. The card lets an English-only receptionist understand, in five seconds, who is standing there and what they need — without the user speaking, and without the AI adding claims.

### 8.2 Content (D-18)

`clerk_message.english` is built server-side from the fixed template:

> "Hello. I speak {Language}. I am here about: {document type as written}. I need help with: {need line}. Please speak slowly or write it down. Thank you."

- `{Language}` = `LanguageInfo.name_en` of `target_language` (for `x-` tags, the typed name).
- `{document type as written}` = `sender_as_written` + the plain document-type word (e.g., "a Virginia Medicaid letter asking me to confirm my address"), from the paper — never a guessed sender.
- `{need line}` = the AI-proposed `clerk_need_en` after the contact filter and phrasing lint, ≤ 200 characters; `need_line_source: "ai"`. When it fails either check the fixed per-document-type line from `data/rules/clerk_needs.yaml` is used and `need_line_source: "template"`.
- Appended lines come only from `appended_line_keys[]`, rendered by the client from fixed copy. In v1 the only key is `clerk.interpreter_hhs` "I may ask for a free interpreter.", appended by the server **only** when the matched resource or the sender is tagged `hhs_funded_health`. A landlord, court or school card never carries it.
- `clerk_message.translated` is the same card in the user's language, shown to the *user* (collapsed, above the exit control) so they know what they are handing over.

### 8.3 Layout and behaviour

| Element | Spec |
|---|---|
| Direction | Always LTR, regardless of UI direction; the whole route sets `writingDirection: 'ltr'` and `dir="ltr"`. |
| Type | ≥ 24 pt body, 32 pt greeting, high-contrast palette forced (black on white or the `highContrast` palette), line height 1.4, generous margins; no font scaling cap. |
| Header | Hidden. `session.clerkMode = true` hides the tab bar; `/(tabs)/papers`, `/papers/*`, `/reminders` are blocked while clerk mode is on (navigation attempts are ignored). |
| Brightness | `clerk.brightness_tip` "Turn your screen brightness up." shown as a one-line hint under the card (expo-brightness is not installed; see §16.2). |
| Controls (bottom, in the **user's** language and direction) | `btn.read_aloud_en` "Read aloud in English" (speaks the English card with an `en-US` voice; hidden if none); `btn.copy_text` "Copy text"; collapsed `clerk.what_it_says` "What this card says" → `clerk_message.translated`; `clerk.back_to_me` **"Back to me"** — exits only after a 1.5 s long-press (progress ring fills; release early cancels). Web: mouse/touch long-press, or hold Space/Enter 1.5 s. |
| Orientation | Portrait; landscape allowed on tablets. |
| Screen lock | Keep-awake while on the screen (`expo-keep-awake` not installed → not claimed; the tip line suffices). |
| Sharing | None — the card is meant to be shown, not sent. |

### 8.4 Generic card (no analysis)

Reached from `home.tile_clerk` when no saved document exists, via `/result/generic/clerk`. Template: "Hello. I speak {Language}. I need help with: {need}. Please speak slowly or write it down. Thank you." where `{need}` defaults to `clerk.generic_need` "understanding a paper I received" and can be changed by the user from preset lines (`clerk.preset.appointment` "an appointment", `clerk.preset.bill` "a bill", `clerk.preset.form` "filling out a form — I need an interpreter", `clerk.preset.address` "changing my address", `clerk.preset.benefits` "my benefits") or typed (≤ 200 chars, the user's own words, shown with `clerk.own_words` "Your words" so no AI claim is implied). No interpreter line is appended on the generic card.

### 8.5 States

● from analysis; ● generic; ● `need_line_source: template` (no visual difference); ● no English voice (button hidden); ● web (copy emphasised); ● clerk mode re-entry after app restart (`session` is memory-only, so restart exits clerk mode — acceptable).

### 8.6 Accessibility and RTL

Every line has `accessibilityLanguage="en-US"`; the exit button has the user's language; contrast 7:1 enforced; the long-press has a labelled alternative (`accessibilityActions: ["activate"]` triggers the same 1.5 s timer with an announced countdown). RTL UI: the card stays LTR; only the bottom controls mirror.

---

## 9. Family vault (S12/S13, D-22…D-24)

### 9.1 Principles

Opt-in, on-device only, per-member, one-tap wipe, never asks status. Nothing about a paper exists anywhere after **S6** unless the user taps **Save** (or "Save to read later").

### 9.2 Data model (native `expo-sqlite` `proxyhealth.db`, WAL; web memory Map / IndexedDB `proxyhealth`)

| Table / store | Fields | Notes |
|---|---|---|
| `members` | `id, name, color, created_at` | "Me" is created on first save with `id = "me"`; not deletable, renamable |
| `documents` | `id (= analysis_id), member_id, title, category, document_type, analysis_json, created_at, next_date_iso, keep_pages` | `analysis_json` is the full `AnalysisResult` (already SSN-masked by the server; A-/receipt numbers masked only if `hide_id_numbers` was on at analysis time); `null` for "read later" items; `title = summary.title` |
| `pages` | `document_id, page, file_path, thumb_path` | files under `Paths.document/vault/<doc_id>/page-<n>.jpg` and `thumb-<n>.jpg`; absent when `keep_pages = 0` |
| `checklist_state` | `document_id, step_id, checked` | plan steps and "bring" checklist items (`step_id` = `PlanStep.id` or `bring:<key>`) |
| `reminders` | `id, document_id, demand_id, fire_at, notification_id, detail_opt_in` | §10 |
| `meta` | `key, value` | schema version, chat history per document (`chat:<doc_id>`, ≤ 8 turns) |

The consent record `{consent_version, accepted_at, tier_seen, platform}` is **not** a table: it lives in `kv` (AsyncStorage) so it exists before the vault is created and works identically on web; `vault.consent` wraps `kv` (D-22, ARCHITECTURE §3.1).

Secrets: a random 256-bit `vault_key` in `expo-secure-store` (`WHEN_UNLOCKED_THIS_DEVICE_ONLY`), used in v1 only to derive the PIN verifier (SHOULD). No app-layer encryption is claimed in v1 copy.

### 9.3 Flows

| Flow | Steps |
|---|---|
| **Save** | S7 `btn.save` → sheet `vault.whose_paper` "Whose paper is this?" with chips `vault.me`, existing members, `vault.add_member` "Add someone" (name ≤ 40 chars, color from 8 swatches, initials auto) → save → toast `vault.saved` "Saved. It stays on this phone." → action bar shows `vault.saved_to` "Saved for {member}". Page images kept if `settings.keep_pages` (default ON native, OFF web). |
| **Save to read later** | From S6 errors or offline S5: same sheet; `analysis_json = null`; row shows `vault.not_read_yet` "Not read yet" and `btn.read_now`. |
| **Open** | S12 row → `/result/<id>` from storage; chat history restored from `meta`. |
| **Move** | `btn.move_member` → member sheet → updates `member_id`; reminders keep working. |
| **Delete a paper** | `btn.delete_paper` → confirm `vault.delete_confirm` "Delete this paper from this phone?" → removes row, files, checklist state, reminders (cancels notifications), chat history. |
| **Delete a member** | S13 `member.delete` → confirm → deletes all their papers as above; "Me" cannot be deleted. |
| **Delete everything** | S17 → `wipe.*` → `storage/wipe.ts` removes DB, files, `kv` (settings, consent, pack cache index, install id), SecureStore items, cancels all notifications, rotates the install id, returns to **S1**. |
| **Search** | Local substring over title, `sender_as_written`, category/document-type words in the current language. |
| **Re-read** (SHOULD) | When pages were kept: `btn.reread` re-sends the stored pages as a new analysis (new `analysis_id`), keeps the old one until the user confirms replacement. |

### 9.4 Web behaviour (D-23)

Default: in-memory for the tab session; banner `banner.web_session_only`. `settings.web_keep` "Keep on this device (not encrypted by the app)" switches to IndexedDB (`proxyhealth` DB mirroring the tables; blobs for pages) after the confirmation `vault.web_keep_confirm` ("This browser will keep your papers. Anyone who uses this browser could open them. The app does not encrypt them."). `settings.web_clear_on_close` (default ON when IndexedDB is enabled) clears the store on `pagehide`. No PIN on web (`secure.web.ts` is an in-memory shim). Consent line 3 on web: "Papers you save stay only in this browser, if you choose to keep them."

### 9.5 Privacy copy that is literally true (CI `test_privacy_claims.py`)

- Native: `vault.privacy_native` "Papers you save stay on this phone, protected by your phone's own encryption. Turn on a phone passcode." (no SQLCipher or iOS-backup claims until verified in the first EAS dev build — D-22).
- Web: `vault.privacy_web` "Papers you keep stay in this browser. The app does not encrypt them."
- Everywhere: `vault.privacy_server` "Our server does not keep your paper."
- Never: "encrypted by the app", "never leaves your device" (uploads do), "Google never sees it".

### 9.6 What the vault never contains

Immigration status (no field exists), full ZIP, GPS, free-text feedback, server logs, anyone else's data. Notification bodies are generic unless the user opts in (§10).

---

## 10. Deadline reminders (S14, D-22)

### 10.1 Eligibility

Only demands with `reminder_eligible: true` (= `verified && date.kind == "stated" && date.value_iso` set) get `btn.remind_me`. `estimated` and `unresolved` dates show `btn.verify_date` and `reminders.estimate_blocked` instead. Unverified facts never get reminders. Past dates cannot be scheduled (`reminders.past`).

### 10.2 Schedule

| Rule | Value |
|---|---|
| Default fires | 7, 3 and 1 day(s) before `value_iso` at **09:00 local device time**; skipped if already past; every future 7/3/1-day 09:00 slot is kept; only when all of them have passed (date today or tomorrow after 09:00) does one reminder fire in 1 minute, with `notif.today_body` only when the date is today (the generic body otherwise — `schedule.computeFireTimes`, CL-047(b)) |
| Time zone | Device local; recomputed on `timezone` change events at app start |
| Clock skew | If the device clock differs from `ServerConfig.server_time` by more than 24 h, show `reminders.clock_warning` "Your phone's clock looks wrong. Reminders may fire at the wrong time." |
| Native mechanism | `expo-notifications` local scheduling; Android channel id `dates` named `notif.channel_name` "Dates to remember"; iOS `UNCalendarNotificationTrigger` equivalent via `scheduleNotificationAsync({trigger: {date}})` |
| Body | `notif.generic_body` **"You have a date coming up."**, title `app.name`; with `detail_opt_in`: `notif.detail_body` "{document_title}: {demand_text} on {date}" |
| Tap | Opens `/reminders?doc=<analysis_id>` |
| Persistence | `reminders` table with `notification_id`; rescheduled from the table on app start if the OS lost them |
| Permission | Explanation card first (`reminders.permission_explain` "I can remind you 7, 3 and 1 days before this date. The reminder text is generic unless you choose otherwise."), then the system prompt; denied → in-app list still works, `reminders.permission_denied` |
| Web | No scheduled notifications. `btn.download_ics` per reminder and `btn.download_all_ics`; `lib/ics.ts` writes RFC 5545 with one `VEVENT` per reminder, `DTSTART` = date at 09:00 local as floating time, `SUMMARY` = generic unless `detail_opt_in`, no `DESCRIPTION` content from the paper; native also offers the same `.ics` via the share sheet (`btn.add_to_calendar`) |
| "Add my own date" | `reminders.add_own`: title ≤ 60 chars, date, optional note ≤ 100 chars; stored with `document_id = null`; same schedule rules |
| Deletion | Deleting a paper or member cancels and removes its reminders; "Delete everything" cancels all |

### 10.3 UI

S14 list grouped by document with member dot; toggle per reminder (`reminders.on`/`off`); `value_verbatim` in `<Bidi>` plus `localized_line`; `reminders.lockscreen_detail` toggle + `reminders.lockscreen_explain` ("Off: the reminder only says a date is coming. On: it shows the paper and the date on your lock screen."); Home next-date card; `tabs.papers` badge count for the next 7 days. Live region announces additions (`reminders.added` "Reminder set for {date}, and 7, 3 and 1 days before.").

---

## 11. Translation-feedback loop (D-31)

### 11.1 Surfaces

`FeedbackRow` appears under: Card 1 (`summary`), each demand row (`demands`, `card_id = demand.id`), Card 3 (`plan`, `card_id = step.id`), Details (`details`), glossary (`glossary`, `card_id = index`), red flags (`red_flags`), clerk card (`clerk`), every chat bubble (`chat`), troubleshoot result (`troubleshoot`), every resource card (`resource`, with `resource_id`), the language banner (`language_pack`), the quick sheet (`quicksheet`).

### 11.2 Interaction

"Was this clear?" `feedback.question` with `btn.yes` / `btn.no` (56 pt). **Yes** → `POST /v1/feedback {kind: "clear", surface, language_tag, document_category, document_type, card_id, resource_id, app_version, platform, model_id}` → tiny check. **No** → sheet `feedback.what_wrong` "What was wrong?" with one-tap kinds: `feedback.kind.unclear` "Hard to understand", `feedback.kind.wrong_word` "A word is wrong", `feedback.kind.wrong_fact` "A date, amount or fact is wrong", `feedback.kind.offensive` "This is rude or offensive", `feedback.kind.scam_missed` "This looks like a scam but the app did not say so", and on resource cards `feedback.kind.resource_problem` "The phone number or website does not work". One tap sends the counter and closes with `feedback.thanks` "Thank you. We count your answer only. We never send your paper." The "Report" affordance (`btn.report_problem`) required by Google Play is this same sheet, reachable on every AI output without leaving the screen.

### 11.3 What is and is not sent

Sent: enums and ids only (`FeedbackRequest`). Never: the sentence, the paper's text, free text, install id linkage beyond the header used for rate limiting. Offline: feedback is queued in `kv` and flushed later (counts only, so duplicates are harmless).

### 11.4 How counts drive quality

Operators read `var/feedback_counts.sqlite` grouped by `language_tag × surface × kind`. A language whose `clear` share falls below 70% or whose `wrong_word` count exceeds 20 in a week goes to a human reviewer (SHOULD S5 tooling); a `scam_missed` count adds the fixture to the scam regex review; `wrong_fact` spikes per `document_type` trigger a golden-set check. `missing-key` reports from `useT()` are also counts (`kind: unclear`, `surface: language_pack`, `card_id = key`).

### 11.5 Banners that make machine translation honest

`banner.machine_translated` on every `machine_translated` pack; English source lines under every AI sentence for Tier 3 / `x-` packs and whenever `translation_confidence == low`; `banner.partial_pack` when keys fell back; `btn.hear_it` always adjacent.

---

## 12. Demo mode and sample papers (D-01, D-29)

### 12.1 Modes

| Situation | `data_use_tier` | What the user sees | What runs |
|---|---|---|---|
| `AI_PROVIDER=mock` (zero keys; default when `.env` is absent) | `demo` | Badge "Sample mode"; `consent.line2.demo` tells the truth that a photographed page is posted for sample matching only; `banner.sample_mode` on Home; scan works | `MockProvider`: `demo_sample_id` → fixture output; else 16×16 dHash of page 1 vs fixture images (Hamming ≤ 10) → fixture output; else generic `quality.readable=false` with `state.sample_not_recognised` "I can only read sample papers in this mode. Try a sample paper from the list."; latency 300–900 ms |
| Gemini with any `billing:false` slot | `unpaid`/`mixed` | Red badge and line; real scans disabled; sample tile promoted | Samples run through Gemini with fixture bytes from disk; real uploads → `403` |
| Gemini, all billed | `paid` | Normal; sample tile is a small link | Real papers allowed; samples still available |
| API unreachable | unknown | Scan needs consent recorded earlier (S2 Continue is disabled while the tier is unknown); with it, scans are queued offline (`capture.offline_queue`); samples from the bundled manifest | `offline.ts` serves bundled fixture results for sample ids only; a queued scan is held in memory (`session.offlineQueue`) and nothing sends it automatically yet (drain on reconnect, or copy that matches, is a code request in CL-064) |
| `EXPO_PUBLIC_DEFAULT_SAMPLE_MODE=true` (judging builds) or Settings `settings.sample_toggle` | any | App starts with the sample picker open on Home | Requests carry `demo_sample_id` |

Mock is never a silent fallback for a real request: quota exhaustion shows `err.quota_exhausted` and the user chooses "Try a sample paper" (D-01).

### 12.2 Sample picker (component `features/demo/SamplePicker`, a bottom sheet — no route)

Opened by `home.tile_sample`, `consent.try_sample`, `btn.try_sample` in error states, and Settings. Lists `GET /v1/demo/fixtures` (cached; bundled `assets/fixtures/manifest.json` offline): thumbnail (`thumbnail_url` or bundled PNG, watermarked SAMPLE), `t(title_key)` (fallback `title_en`), category icon, `pages`, `kind` (documents vs. the screenshot, which opens **S16** instead of **S5**). Tapping a document opens **S5** with `?sample=<id>`; the pages are display-only; masks and member selector hidden; `banner.demo_sample`. **S6** posts `demo_sample_id` with `pages: []` (API_CONTRACT §3.5; the server loads fixture bytes from disk on Gemini and resolves by id on mock). Results carry `model_meta.demo: true`; saving a sample to the vault is allowed and labelled `vault.sample_tag` "Sample".

### 12.3 Fixture set and what each one demonstrates

| `id` | `document_type` / `category` | Expected on S7 | Demo point |
|---|---|---|---|
| `medicaid_address_confirmation` | `medicaid_renewal` / benefits | `high`, stated date 2026-10-14, 2 demands, HHS interpreter line on clerk card | the canonical first scan (J-A) |
| `uscis_i797c_receipt_i765` | `uscis_receipt` / immigration | `info`; red flag `ead_receipt_not_work_authorization` → `fixed.uscis_receipt_i765` (high) | fixed notice, receipt number handling |
| `uscis_rfe_87d` | `uscis_rfe` / immigration | `high`/`critical` by date; `prepare.yaml` item "the RFE notice itself on top of your response" | stated date beats any rule |
| `nta_hearing_date` | `nta` / immigration | `critical` (hearing ≤ 7 days) or floor `high`; `btn.verify_date` → EOIR ACIS/hotline; `fixed.address_change_multi_agency` | Verify this date; floors |
| `inova_final_notice` | `medical_bill` / medical | `medium`; red flag `urgency_pressure`; Inova FA first when `state=VA` | institution bonus, charity care |
| `insurance_denial_180d` | `insurance_denial` / medical | `medium`; `estimated` date via `aca_internal_appeal_180d` with formula and rule link | date math shown, not hidden |
| `prescription_label` | `prescription_label` / medical | `info`; glossary; medical disclaimer; no interpretation | describe, don't interpret |
| `school_immunization_notice` | `immunization_notice` / school | `medium`; CDC IIS resource | school module for parents |
| `va_pay_or_quit_14d` | `pay_or_quit` / housing | printed pay-by date → `stated`; `high` (date or doc-type floor — D-12 as revised); `fixed.pay_or_quit`; eviction resources | housing boundary (J-C) |
| `snap_interview_notice` | `snap_notice` / benefits | `high` appointment; bring list | appointment role |
| `irs_cp_notice` | `irs_notice` / tax | `medium`; IRS notice resource | tax module |
| `jury_summons` | `jury_summons` / civic | `medium`; `fixed.jury_summons` (high) | never check "citizen" |
| `scam_gift_card_letter` | `other_notice` / immigration | `scam_risk: likely`; scam card; DHS OIG + FTC first | scam path (J-F) |
| `blurry_unreadable_page` | `unknown` | `quality.readable=false` | unreadable state without re-spending quota |
| `spanish_lease` | `lease` / housing | `info`; `detected_language: es`; `document_language_differs` when UI ≠ es | translation direction |
| `w2_form` | `w2_1099` / employment | `info`; glossary (EIN, withholding); ITIN resource | employment/tax breadth |
| `traffic_court_notice` | `traffic_court` / court | `high`/`critical` court date; legal disclaimer | court breadth |
| `portal_file_too_large` (screenshot) | — / benefits | steps quoting "Back", "Choose File", "Upload"; caution about "Submit Application" | troubleshoot (J-D) |

Expected outputs: `out.en.json` for every fixture; `out.es.json`, `out.prs.json`, `out.ar.json` for the eight demo fixtures listed in BUILD_PLAN §4.5 (`medicaid_address_confirmation`, `uscis_rfe_87d`, `nta_hearing_date`, `inova_final_notice`, `va_pay_or_quit_14d`, `scam_gift_card_letter`, `jury_summons`, `portal_file_too_large`); any other target language gets the `en` output with a `⟦xx⟧` pseudo-translation marker in mock mode (visible, honest). `DemoFixture.available_target_languages` tells the client which is which.

Pinned sample "today" (CL-067(a)): every fixture `manifest.yaml` records `today: '2026-10-02'`, and for a sample paper only — a request with `demo_sample_id`, or an upload the mock matched to a fixture by dHash — the server computes dates, `days_until` and urgency as of `apps/api/proxyhealth_api/demo/as_of.py` `DEMO_AS_OF` (2026-10-02), never the wall clock, so the urgencies in this table hold on any day (Medicaid 2026-10-14 is 12 days out → `high`). Chat pins its prompt date the same way when `demo_sample_id` is set. Real papers always use the real clock. The goldens and the offline bundle (`sync_to_mobile.py`) use the same date. A sample result that carries a date shows one fixed line under the urgency banner, `demo.as_of_note` "Sample dates are shown as if today were October 2, 2026."; the app shows the server's `days_until` as is and never recomputes it from the device clock. `DEMO_AS_OF` and that copy change together.

### 12.4 Rules for keyed demos (binding)

Keyed demos use fixtures or a photographed *printed SAMPLE sheet* only — never a real personal letter, regardless of consent (D-29). The 403 gate blocks non-demo uploads on any unpaid slot even with `ALLOW_UNPAID_KEYS=1`. `ALLOW_UNPAID_REAL_DOCUMENTS=true` is for developer testing with synthetic scans only and fails to boot in production.

---

## 13. Three-minute demo script

Setup (both variants): API on `http://127.0.0.1:8000` (or the demo instance), web build at `http://localhost:8081`, an Android EAS development build on a phone (Expo Go for smoke only), Settings → region `VA` / `220` preset, text size L, a printed copy of the `medicaid_address_confirmation` fixture page. Have `/health` open in a browser tab.

### 13.1 Zero keys (`AI_PROVIDER=mock`, `data_use_tier: demo`)

| Time | Screen | Do | Say / point at | Expected |
|---|---|---|---|---|
| 0:00 | S1 | Tap دری (Dari) | "Any language, one tap; right-to-left flips immediately." | Grid mirrors; native shows the restart prompt → "Later" |
| 0:10 | S2 | Point at the badge; tap "Try a sample paper first" | "The consent screen tells the truth per tier: this build contacts no AI service." | Badge "Sample mode"; sample picker opens |
| 0:20 | S5 → S6 | Pick "Medicaid letter asking to confirm your address" → "Read this paper" | "Three honest steps; the mock adds 300–900 ms so you see them." | S6 steps, then S7 |
| 0:30 | S7 | Scroll slowly; tap the crop on the date; tap a speaker; tap "Remind me" | "Every fact is a quotation with its crop and confidence. The date is 'stated', so it can become a reminder. No Dari voice → honest Farsi offer." | Banner "Soon… October 14, 2026"; S8 opens on the block; `tts.fallback_offer`; permission card → reminder toast |
| 1:05 | S7 → S10 | Tap "Show the clerk"; hand the phone to a colleague; long-press "Back to me" | "The card is English, LTR, fixed template; the interpreter line appears only because Medicaid is HHS-funded." | Card with "I may ask for a free interpreter."; exit needs 1.5 s hold |
| 1:25 | S7 → S11 | Tap "Get help nearby" → see all | "Only humans we verified, with the date we checked; a bring-this checklist; national fallbacks always." | Medicaid.gov state finder (with "You can ask for a free interpreter here."), HealthCare.gov, Fairfax CSP with "Verified on 2026-09-27", 211 under "Always available" |
| 1:45 | S7 → S12 | Save → "Me"; open My papers; Add someone "Layla" | "Saving is opt-in; the vault is on the phone; per-member." | Row appears; member chip |
| 2:00 | S3 → S16 | "Stuck on a website?" → sample screenshot | "Portal rescue: steps name buttons exactly as written; the credential guard is always there." | Steps "Back", "Choose File", "Upload"; caution on "Submit Application" |
| 2:20 | S16 scam mode or S5 | Sample "Letter claiming to be USCIS and demanding gift cards" | "Scam risk is scored in code; reporting numbers come from the database, never the model." | Scam card; DHS OIG 1-800-323-8603, ReportFraud.ftc.gov |
| 2:40 | S17 → S1 → S1b | "My language is not here" → type "Rohingya" | "The requested loading copy, verbatim. Mock returns a pseudo-localized pack; with a key it is generated in 60-key chunks and cached." | "Adapting system environment to your language..." → Hanifi RTL pack + machine-translation banner |
| 2:55 | Browser | Show `/health` | "provider mock, keys_configured 0, nothing stored." | `{"provider":"mock","keys_configured":0,"data_use_tier":"demo",...}` |

If time allows: airplane mode → open the saved paper, quick sheet, reminders (all work offline); photograph the printed SAMPLE sheet with the phone → dHash match returns the same result.

### 13.2 With keys (`AI_PROVIDER=gemini`, ≥ 2 slots, all `billing:true`, distinct projects, `ENV=staging`)

| Time | Do | Point at | Expected |
|---|---|---|---|
| 0:00 | S1 Dari → S2 | Badge "Paid service"; line 2 paid copy; header `X-Data-Use-Tier: paid` in dev tools | Consent recorded |
| 0:20 | Phone camera → photograph the **printed SAMPLE sheet** (never a real letter) → "Read this paper" | S6 real latency; at 20 s "Long letters take longer." | 15–40 s → S7 |
| 1:00 | S7 | `model_meta.model_id = gemini-3.8-flash`, `thinking_level: high`, `analysis_mode` single/two_call; open **S8** to show highlighted spans; if any fact failed verification, show "I saw these but could not confirm them on the page" | Verified facts with crops; unverified struck through |
| 1:40 | Terminal | The access log line: `request_id, route, status, model, tier, slot_index, latency_ms, tokens, document_type, urgency_level` — no content | Content-free log |
| 2:00 | `GET /v1/admin/keys` with `X-Admin-Token` | Per-slot per-tier state with `project` label and `key_last4` | JSON |
| 2:20 | Set one slot's key to an invalid value and restart, or exhaust its RPM | Failover: slot `disabled` (401/403) or `cooling` (429) → next slot serves; if all cool → S6 shows `err.quota_exhausted` with "Try a sample paper" | Live rotation |
| 2:45 | Flip one slot to `billing:false` and restart | S2 now shows the red unpaid badge; real scan disabled; a sample still runs through Gemini via `demo_sample_id` (fixture bytes from disk) | 403 gate visible |

Fallbacks: if the network dies, switch the client to the mock instance (`EXPO_PUBLIC_API_URL`) and continue the zero-key script; if the camera match fails, use the sample picker.

---

## 14. Platform matrix

| Capability | iOS / Android (EAS dev build) | Web | Expo Go |
|---|---|---|---|
| Camera capture | `expo-camera` `CameraView` (S4) | `expo-image-picker` `launchCameraAsync` inside the click handler (no S4 preview) | works (permission strings generic) |
| Photo / PDF pick | system pickers (`expo-image-picker`, `expo-document-picker`) | same, inside the gesture; `file`/`base64` fields used directly | works |
| Compression | `expo-image-manipulator` 1600 px JPEG 0.8 | same (web supported) | works |
| Hide parts | send `masks` → server Pillow | canvas burn, `masks_applied_client_side: true` | as native |
| Vault | `expo-sqlite` + files in `Paths.document/vault/` | memory; IndexedDB opt-in | sqlite works; SQLCipher not testable |
| Secrets / PIN | `expo-secure-store` | none (shim); PIN unavailable | works (no `requireAuthentication`) |
| Reminders | `expo-notifications` local | `.ics` download | limited; use dev build |
| Quick sheet | `expo-print` → `expo-sharing` | `POST /v1/quicksheet/pdf` download + print dialog | works |
| Clipboard | `expo-clipboard` | same, synchronous in handler | works |
| TTS | `expo-speech` device voices | browser `SpeechSynthesis` voices | works |
| RTL | `useDirection()` row-reverse + `I18nManager` restart prompt | `useDirection()` + `document.documentElement.dir` | row-reverse works; forceRTL needs restart |
| Fonts | `expo-font` static Noto TTFs from `assets/fonts/` (subsetting LATER) | same | works |
| Offline | vault, quick sheets, reminders, bundled packs, bundled fallbacks, capture queue | same minus reminders | same |
| Haptics | `expo-haptics` | vibration API where allowed | works |

---

## 15. Acceptance criteria (implementation-ready checklist)

Each line is testable; the test file names are those in `ARCHITECTURE.md`.

**Onboarding and consent**
- [ ] First run with device locale `fa-AF` shows S1 in Dari, RTL, with no network (`i18n.test.ts`).
- [ ] S2 renders the exact tier copy for `paid`, `unpaid`, `mixed` (as unpaid), `demo`, `unknown`; on `unpaid`/`mixed` the continue button is absent and "Try a sample paper first" is primary; on `unknown` continue is disabled; "Not now" lands on Home with scan disabled; the consent record has exactly `{consent_version, accepted_at, tier_seen, platform}` and lives in `kv` (`consent.test.tsx`).
- [ ] A `428` from any AI endpoint opens S2 and retries once after acceptance (`api-client.test.ts`).

**Scan**
- [ ] 13th page is refused in UI with `state.page_cap`; images + PDF cannot be mixed; PDF > `max_pdf_bytes` is refused before upload.
- [ ] Every page is ≤ 4 MB after compression; EXIF removed; rotation applied server-side via `PageInput.rotation`.
- [ ] Web: pickers are invoked as the first statement of the handler; masks are burned on canvas; request has `masks: []` and `masks_applied_client_side: true`.
- [ ] Offline capture shows `home.offline_line`/`review.read_later_cta` and queues in session.

**Result**
- [ ] Cards render from the RFE golden JSON in LTR and RTL at 200% font scale with no clipped verbatim values (`result-cards.test.tsx`).
- [ ] Every `demands[]` row shows `value_verbatim` in `<Bidi dir="ltr">`, a crop (or full page + quote when `bbox` is null), a `ConfidenceChip`; `unverified[]` rows are struck through under the exact heading and have no "Remind me".
- [ ] `UrgencyBanner` shows icon + word + color for all five levels (`urgency-banner.test.tsx`); `past_date` shows `btn.verify_date`.
- [ ] `estimated` dates render formula, anchor quote, rule link and "Confirm with the sender."; `unresolved` render the phrase verbatim + "Ask the sender which date this means."
- [ ] Fixed notices render from `fixed_copy_key`; scam `likely` shows the fixed card before Card 1; `safety.emergency` shows S19 content first and announces it.
- [ ] No string from the model is displayed without passing through the API (the client never calls Gemini) and the client never fabricates a phone number, URL or organization (quick-sheet builder test excludes stripped contacts — `quicksheet.test.ts`).

**Chat, clerk, help**
- [ ] `AnalysisContext` is capped at 60 000 chars of `original_text`; history ≤ 8; refusal templates render per `refusal_kind`; referral per `refer_to_professional`.
- [ ] Clerk card is LTR in an RTL UI, ≥ 24 pt, hides tabs and blocks vault routes, exits only after a 1.5 s hold; `clerk.interpreter_hhs` appears only when present in `appended_line_keys`.
- [ ] S11 shows `status_note.lsc_restricted` with the alternative link; national fallbacks always present; `verified_on` chip on every card; broken links hidden.

**Vault, reminders, quick sheet**
- [ ] Nothing is written to the vault before Save; Save asks "Whose paper is this?"; "Delete everything" leaves no DB, files, kv, secure items or scheduled notifications (`storage.native.test.ts`, `storage.web.test.ts`).
- [ ] Reminders fire 7/3/1 days before at 09:00 local with the generic body; `.ics` output is valid RFC 5545 with a generic `SUMMARY` unless opted in (`reminders.test.ts`).
- [ ] Web default storage is memory; IndexedDB requires the explicit opt-in with the exact "not encrypted by the app" label.
- [ ] Quick-sheet HTML has `dir` and embedded fonts; web uses the server PDF; sharing is gated by `isAvailableAsync()`.

**Language and accessibility**
- [ ] `langpack.adapting` equals "Adapting system environment to your language..." in `en.json`; the S1b headline renders it verbatim.
- [ ] Machine-translated packs show the banner on every screen; Tier 3 shows English source lines; `fallback_keys` shows the partial-pack banner.
- [ ] `t()` falls back to English and reports missing keys as counts (`i18n.test.ts`); `Bidi` isolates verbatim values (`bidi.test.tsx`).
- [ ] Every control has `role` + `accessibilityLabel`; cards are regions; live regions announce progress, results and emergency; VoiceOver/TalkBack full-flow pass on the manual matrix; WCAG 2.2 AA on web (axe clean on S1–S3, S7, S11).

**Errors and demo**
- [ ] Every `ErrorCode` in §5.4 maps to its key and actions (`api-client.test.ts`); `quota_exhausted` shows Retry countdown, Save to read later, Call 211, Try a sample paper.
- [ ] `AI_PROVIDER=mock` passes the full §13.1 script; photographing the printed Medicaid SAMPLE sheet returns its fixture result; an unknown photo returns `state.sample_not_recognised`.
- [ ] With `unpaid` tier, real scans are disabled in UI and the API answers `403`; samples still work with `demo_sample_id`.

**Copy**
- [ ] All base strings in Appendix A exist in `en.json`, pass the grade-5 readability script, contain no emoji, and every privacy sentence is in the approved list (`test_privacy_claims.py`, `test_readability.py`).

---

## 16. Open questions and conflicts

### 16.1 Open questions (owned by the user; see DECISIONS §12)

Billing owner and number of distinct projects (Q1); developer accounts and legal entity (Q2); counsel review of UPL framing per document type and privacy policy (Q3); bundle id and web host (Q4); pilot geography beyond Northern Virginia (Q5); language reviewers for Tier 1/2 packs and emergency lists (Q6/Q7); per-device budget (Q8); web positioning (Q9 — this spec treats web as a *companion* surface: session-only storage, no notifications, server PDF); Interactions timing (Q10); hosting (Q11).

Product-level questions this spec adds:
- **Q12 Hear-it default.** Should `settings.hear_mode_default` be ON when a Tier 3 pack is active (oral-literacy communities)? This spec defaults it OFF everywhere and shows `tts.earbuds_tip` once.
- **Q13 "Read later" member.** Should "Save to read later" skip "Whose paper is this?" and default to "Me" to shorten the error path? This spec asks.
- **Q14 Sample picker prominence on paid tier.** Tile vs. text link on Home for returning users.

### 16.2 Conflicts and gaps noticed in the backbone — status after the 2026-09-27 consistency pass (DECISIONS §14 CL-001/CL-002)

1. **Clerk card without a document.** *Resolved in ARCHITECTURE §3:* `result/[id]/clerk.tsx` renders the no-analysis card for the reserved id `generic` (§8.4); no new route.
2. **Brightness.** *Resolved in D-18 and ARCHITECTURE §3:* clerk mode shows the `clerk.brightness_tip` line; `expo-brightness` is not installed and brightness is never changed or claimed.
3. **Two-way clerk mode** (user-first SHOULD) has no endpoint in `API_CONTRACT.md` v1 (chat is document-scoped; there is no translate endpoint). Stays LATER (L1) — would need `POST /v1/translate` and a contract bump.
4. **`include_page_thumbnails` default.** *Resolved in API_CONTRACT §3.5:* server default `false`; the client always sets it explicitly (`true` for PDFs).
5. **`TroubleshootResult.safety`.** *Resolved in API_CONTRACT §3.6:* the field exists; `troubleshoot_pipeline.py` runs the D-14 lexicon over `screen_text` + `user_goal`; S16 opens S19 first when `emergency` is true.
6. **Pay-or-quit urgency.** *Resolved in D-12:* `pay_or_quit` is in the `high` floor, so a notice without a printed pay-by date renders `urgency.high.floor`, never `info`. The date itself stays `unresolved` (D-11 seeds no eviction period). The `va_pay_or_quit_14d` fixture still prints an explicit pay-by date.
7. **Demo requests and `pages`.** *Resolved in API_CONTRACT §3.5:* `pages: []` is allowed when `demo_sample_id` is set; the client sends no page bytes for samples.
8. **`err.quota_exhausted` placeholder.** *Resolved in D-07:* `{minutes}`.
9. **Resource detail route.** builder-first had a resource detail screen; ARCHITECTURE has none. This spec renders details inline as expandable cards on S11 with `?focus=` deep links (no change needed).
10. **`consent.line4.masks` visibility.** *Resolved in D-19:* shown only when `features.hide_parts_server_masking` is true; web shows `consent.line4.masks_web`.
11. **Consent on unpaid/mixed.** COMPLIANCE_PRIVACY §4.2 hides "I understand, continue" on `unpaid`/`mixed`; an earlier draft of this spec kept it enabled. This spec now follows COMPLIANCE (S2, J-J) because sample requests are exempt from consent and real papers are blocked server-side.
12. **Demo consent line.** D-02's "Nothing leaves this device" was not literally true in mock mode (a photographed page is posted for dHash matching); D-02 now reads "Your photo is only compared with our sample papers and is not kept." and this spec uses that string everywhere (`consent.line2.demo`).

---

## Appendix A — Base-string inventory (seed for `apps/api/data/langpacks/en.json`, WP0-owned)

Flat keys; `{placeholders}` preserved by packs; grade ≤ 5. Keys already fixed in the backbone are marked ✱.

### App, tabs, generic buttons
| Key | English |
|---|---|
| `app.name` | ProxyHealth AI |
| `app.tagline` | Your paper, explained. |
| `tabs.home` / `tabs.papers` / `tabs.help` / `tabs.settings` | Home / My papers / Get help / Settings |
| `home.need_help_now` | Need help now? |
| `btn.continue` / `btn.cancel` / `btn.retry` / `btn.close` / `btn.yes` / `btn.no` | Continue / Cancel / Try again / Close / Yes / No |
| `btn.go_home` / `btn.open_settings` / `btn.copy` / `btn.copy_text` / `btn.stop` | Go home / Open Settings / Copy / Copy text / Stop |
| `btn.save` / `btn.show_clerk` / `btn.quick_sheet` / `btn.read_all` / `btn.ask` | Save / Show the clerk / Quick sheet / Read all aloud / Ask about this paper |
| `btn.remind_me` / `btn.verify_date` / `btn.rescan_part` / `btn.retake` | Remind me / Verify this date / Re-scan this part / Take the photo again |
| `btn.call` / `btn.website` / `btn.call_211` / `btn.call_printed` | Call / Website / Call 211 / Call (number from your paper) |
| `btn.save_to_read_later` / `btn.try_sample` / `btn.read_now` / `btn.get_help` | Save to read later / Try a sample paper / Read it now / Get help nearby |
| `btn.hide_and_retry` / `btn.pick_instead` / `btn.allow_camera` / `btn.choose_bundled` | Hide parts and try again / Pick a photo instead / Allow the camera / Choose a language from the list |
| `btn.report_problem` / `btn.move_member` / `btn.delete_paper` / `btn.scan` | Report a problem / Move to another person / Delete this paper / Take a photo |
| `btn.share_pdf` / `btn.download_pdf` / `btn.print` / `btn.read_aloud` / `btn.read_aloud_en` | Share PDF / Download PDF / Print or save as PDF / Read aloud / Read aloud in English |
| `btn.download_ics` / `btn.download_all_ics` / `btn.add_to_calendar` / `btn.reminders` | Add to calendar (.ics) / Add all to calendar / Add to calendar / Reminders |
| `btn.save_evidence` / `btn.save_quick_sheet` / `btn.hear_it` / `btn.test_voice` | Save as proof / Save as quick sheet / Hear it / Test the voice |
| `btn.restart_now` / `btn.restart_later` / `btn.delete_everything` / `btn.reread` | Restart now / Later / Delete everything on this phone / Read this paper again |
| `btn.read_privacy` / `btn.review_consent` / `btn.withdraw_consent` / `btn.privacy` / `btn.clear_region` / `btn.rotate_install_id` / `btn.move_all` | Read the privacy notice / Read how your paper is handled / Stop sending papers / Privacy / Clear / New device id / Move all papers |

### Onboarding, language, consent
| Key | English |
|---|---|
| `a11y.app_starting` / `a11y.pack_reset` | ProxyHealth AI is starting. / The language file was reset to English. |
| `lang.title` / `lang.suggested` / `lang.not_here` / `lang.type_hint` / `lang.machine_translated_dot` | Which language? / Suggested for this phone / My language is not here / Type the name of your language, in any language. / Translated by a computer |
| `state.lang_needs_internet` | I need internet to add a new language. Choose one of these for now. |
| `langpack.adapting` ✱ | Adapting system environment to your language... |
| `langpack.about_20s` / `langpack.english_meanwhile` | About 20 seconds / The app stays in English until this finishes. |
| `langpack.step_find` / `langpack.step_translate` / `langpack.step_check` | Finding your language / Translating the app / Checking the words |
| `direction.restart_prompt` / `direction.restart_pending` | Restart the app to finish switching. / A restart will finish switching the layout. |
| `consent.title` ✱ | What happens to your paper |
| `consent.badge.paid` / `consent.badge.unpaid` / `consent.badge.demo` / `consent.badge.unknown` | Paid service / Test build — free AI key / Sample mode / Cannot confirm |
| `consent.line1` ✱ | Your photo is sent to Google's AI (Gemini) to be read. Our server does not keep it. |
| `consent.line2.paid` ✱ | Google does not use your paper to improve its products. Google keeps a short safety log for a limited time, then deletes it. |
| `consent.line2.unpaid` ✱ | This test build uses a free AI key. Google may read and use what is sent. Do not send real papers. Sample papers only. |
| `consent.line2.demo` ✱ | Sample mode. No AI service is contacted. Your photo is only compared with our sample papers and is not kept. |
| `consent.line2.unknown` ✱ | I cannot confirm how your paper would be handled right now. You can try a sample paper or come back later. |
| `consent.line3` ✱ / `consent.line3.web` ✱ | Papers you save stay only on this phone. You can delete everything any time. / Papers you save stay only in this browser, if you choose to keep them. |
| `consent.line4.masks` ✱ / `consent.line4.masks_web` ✱ | Parts you hide are blacked out on our server before Google's AI sees them. / Parts you hide are blacked out on your device before anything is sent. |
| `consent.adults_only` ✱ | This app is for adults 18 and older. |
| `consent.btn_continue` ✱ / `consent.btn_not_now` ✱ / `consent.try_sample` ✱ / `consent.read_more` | I understand, continue / Not now / Try a sample paper first / Read more |
| `consent.changed` / `consent.unknown_hint` | This has changed: / Come back when you have internet to confirm this. |
| `consent.pictogram1_alt` / `consent.pictogram2_alt` / `consent.pictogram3_alt` | A photo going to a cloud / A server with no saved copy / A phone with a lock |
| `privacy.notice.sent` | When you read a paper, the photo goes to our server and then to Google's AI (Gemini). Our server does not keep it. |
| `privacy.notice.what_we_keep` | Our server keeps only counts: how many papers were read, how long it took, and which language. It does not keep your photos, your words, or the AI's words. |
| `privacy.notice.device` / `privacy.notice.device_web` | Papers you choose to save stay on this phone, protected by your phone's own encryption. Turn on a phone passcode. / In this browser, papers are kept only while the tab is open, unless you turn on 'Keep on this device'. The app does not encrypt them. |
| `privacy.notice.hide_parts` / `privacy.notice.no_status` | You can black out parts of a page before it is read. / We never ask about your immigration status. We do not ask for your exact address. Only your state and the first 3 digits of your ZIP code, if you choose to give them. |
| `privacy.notice.no_ads` / `privacy.notice.settings_sent` | We do not sell your information. There are no ads and no trackers. / Your language, your state, your ZIP prefix and your calendar notes (like Ramadan) are sent with each paper so the answer fits you. They are not kept on our server. |
| `privacy.notice.install_id` / `privacy.notice.feedback` | Your phone sends a random code so one phone cannot use the service too much. The code is scrambled and forgotten after 30 days. You can reset it with 'Delete everything'. / When you tap 'Was this clear?' or 'Report a problem', we count it. We do not receive the text of your paper. |
| `privacy.notice.delete` / `privacy.notice.full_policy` | You can delete one paper, one family member's papers, or everything, any time. / Read the full privacy policy |
| `demo.explainer` | Sample papers are made up. They are not real people's papers. You can try everything with them. None of your papers or photos are sent. |
| `perm.camera` / `perm.photos` / `perm.notifications` | ProxyHealth AI uses the camera only to photograph the paper you want explained. Photos are not saved on our servers. / ProxyHealth AI lets you choose a photo of a paper to explain. We do not access your other photos. / ProxyHealth AI reminds you about dates it found on your papers. Reminder text is generic unless you choose otherwise. |

### Home, capture, review, reading
| Key | English |
|---|---|
| `home.scan_cta` ✱ / `home.scan_hint` | Take a photo of a paper / Opens the camera to photograph a paper. |
| `home.tile_pick` / `home.tile_pick_sub` | Pick a photo or PDF / Use a photo you already have, or a PDF file. |
| `home.tile_troubleshoot` / `home.tile_troubleshoot_sub` | Stuck on a website? / Show me a screenshot. I will explain the screen. |
| `home.tile_clerk` / `home.tile_clerk_sub` | Show the clerk / A card in English to hand to the person at the counter. |
| `home.tile_sample` / `home.tile_sample_sub` | Try a sample paper / See how it works. Nothing of yours is sent. |
| `home.next_date` | Date soon: {date} — {document_title} |
| `home.trust_footer` / `home.trust_footer.web` | Our server does not keep your paper. Papers you save stay only on this phone. / Our server does not keep your paper. Papers you keep stay only in this browser. |
| `home.offline_line` | No internet. I can take the photo now and read it later. |
| `home.consent_needed` | Scanning is off until you accept how your paper is handled. Tap to read it. |
| `home.unpaid_disabled` | Real papers are off in this test build. Try a sample paper. |
| `home.busy_until` | The helper is busy. Try again at {time}. |
| `capture.guide_fit` / `capture.guide_dark` / `capture.guide_added` | Fit the whole page. Hold still. / Too dark. Tap the light. / Page {n} added. |
| `capture.shutter_label` / `capture.add_page` / `capture.done` | Take photo of page {n} / Add another page / Done |
| `capture.pick_from_photos` / `capture.pick_pdf` | Pick from photos / Pick a PDF |
| `capture.permission_rationale` | I need the camera to photograph your paper. The photo is sent only to be read, and our server does not keep it. |
| `state.camera_denied` | The camera is turned off for this app. You can turn it on in Settings, or pick a photo instead. |
| `state.page_cap` / `state.pdf_or_photos` | That is the most pages I can read at once ({max_pages}). Tap Done, or remove a page. / Choose photos or one PDF, not both. |
| `capture.offline_queue` | No internet. I saved the photo. I will read it when internet is back. |
| `a11y.page_added` | Page {n} added. |
| `review.retake` / `review.rotate` / `review.remove` / `review.hide_parts` | Take again / Turn / Remove / Hide parts |
| `review.hide_tip` / `review.hide_note_receipt` | Hide ID numbers or anything you do not want read. I can still explain the rest. / If you hide a case or receipt number, I cannot help you track that case. |
| `review.read_cta` / `review.read_hint` / `review.read_later_cta` / `review.wait_for_internet` | Read this paper / Sends {n} pages to be read. Takes about a minute. / Save to read later / I will read it when internet is back |
| `review.pdf_summary` / `review.blur_hint` / `review.document_hint` | PDF · {size} MB / Page {n} looks blurry. Take it again? / I think this is a… |
| `vault.whose_paper_optional` | Whose paper is this? (you can choose later) |
| `reading.step1` / `reading.step2` / `reading.step3` | Reading the words / Understanding / Writing it for you |
| `reading.trust_line` / `reading.eta` / `reading.tip_long` / `reading.tip_still` | Our server does not keep your paper. / Usually under a minute / Long letters take longer. You can keep waiting. / Still working. Thank you for waiting. |
| `a11y.reading_finished` | Reading finished. {n} dates found. |
| `state.unreadable` / `state.page_unreadable` | I could not read this page. Try again in brighter light, and flatten the page. / Page {n} was hard to read. |
| `state.sample_not_recognised` | I can only read sample papers in this mode. Try a sample paper from the list. |

### Result cards
| Key | English |
|---|---|
| `card.what_is_this` / `card.asking_for` / `card.plan` | What is this? / What is it asking for? / Your step-by-step plan |
| `card.details` / `card.glossary` / `card.questions` / `card.questions_sub` / `card.red_flags` / `card.help_preview` | Details and quotes / Words explained / Questions you can ask them / Ask the office that sent this paper. / Red flags / Get help nearby |
| `card.unverified` ✱ | I saw these but could not confirm them on the page. |
| `card.sender_as_written` / `card.found_on_page` / `card.asking_nothing` | From: {sender} / Found on page {page} / This paper does not ask you to do anything. It is for your information. |
| `confidence.high` / `confidence.medium` / `confidence.low` | Clear / Probably / Unclear — re-scan this part |
| `role.hearing_date` / `role.response_due` / `role.payment_due` / `role.appointment` / `role.notice_date` / `role.decision_date` / `role.move_date` / `role.expiry` | Hearing date / Answer by / Pay by / Appointment / Date of this notice / Decision date / Move date / Expires |
| `demand.estimate_prefix` / `demand.anchor` / `demand.confirm_with_sender` / `demand.rule_link` / `demand.rule_likely` / `demand.ask_sender_date` | Estimate: / from: {anchor_quote} / Confirm with the sender. / rule ↗ / Rule not yet re-checked / Ask the sender which date this means. |
| `plan.find_help` | Find help for this → |
| `help.see_all` / `help.set_region_prompt` | See all help / Tell me your state to find help near you. |
| `footer.ai_generated` / `footer.verify_with_sender` | Made by a computer from your paper. It can be wrong. Check the highlighted words. / Confirm dates and amounts with the sender. |
| `vault.saved_to` | Saved for {member} |
| `a11y.emergency_shown` | An emergency card is shown at the top. |

### Urgency, disclaimers, banners, warnings
| Key | English |
|---|---|
| `urgency.word.emergency` / `.critical` / `.high` / `.medium` / `.info` | Emergency / Very soon / Soon / Coming up / For your information |
| `urgency.emergency.headline` | Someone may need help right now. See the card above. |
| `urgency.critical.date_soon` / `urgency.critical.date_today` / `urgency.critical.date_passed` / `urgency.critical.floor` | A very important date is close: {date}. / A very important date is today: {date}. / This date may have passed: {date}. Contact them today. / This paper is very important. Act this week, even if no date is printed. |
| `urgency.high.date_soon` ✱ / `urgency.high.floor` | There is a date soon: {date}. / This paper is important. Act soon, even if no date is printed. |
| `urgency.medium.date_soon` / `urgency.medium.estimated` | There is a date coming up: {date}. / There may be a date around {date}. This is an estimate. Confirm with the sender. |
| `urgency.info.date_later` / `urgency.info.no_date` / `urgency.info.no_action` | There is a date later: {date}. / I did not find a date on this paper. / Nothing to do right now. Keep this paper. |
| `urgency.days_until` / `urgency.days_ago` / `urgency.floor_note` | In {days} days / {days} days ago / This kind of paper is important even without a date. |
| `disclaimer.legal_information_only` ✱ | This is general information about this type of paper, not legal advice about your case. Only a licensed lawyer or a DOJ-accredited representative can advise you. |
| `disclaimer.medical_information_only` ✱ | This explains what your paper says. It is not medical advice. Ask your doctor, nurse or pharmacist what it means for you. |
| `disclaimer.benefits_information_only` | This explains what your paper says. It is not a decision about your benefits. Only the office that sent it can tell you what happens next. |
| `disclaimer.housing_information_only` | This is general information about this type of paper, not legal advice. A housing lawyer or counselor can advise you about your home. |
| `disclaimer.general_information` | This is general information from your paper. It can be wrong. Check the highlighted words and confirm with the sender. |
| `banner.machine_translated` | This language was translated by a computer. It may have mistakes. Numbers and dates are kept as printed. Tap the speaker to hear it. |
| `banner.partial_pack` / `banner.low_confidence_translation` | Some words are in English. / This translation may have mistakes. Check the English words under each line, or ask someone who reads both. |
| `banner.doc_language_differs` | Your paper is in {doc_language}. I explained it in {ui_language}. |
| `banner.degraded_model` / `banner.demo_sample` / `banner.unpaid_tier` / `banner.sample_mode` | A faster helper read this paper. Check the highlighted words carefully. / This is a sample paper. Nothing of yours was sent. / Test build with a free AI key. Sample papers only. / Sample mode: the helper is not connected. Try the sample papers. |
| `banner.offline` / `banner.web_session_only` | No internet. Saved papers, quick sheets and reminders still work. / This paper is kept only while this tab is open, unless you turn on keeping in Settings. |
| `state.offline_disabled` / `state.cached` | Not available without internet. / Last known |
| `warning.low_quality_image` / `warning.partial_pages` / `warning.page_edge_crop` / `warning.translation_partial` / `warning.blocked_partial` / `warning.checks_unavailable` / `warning.injection_masked` / `warning.contacts_stripped` | The photo was hard to read. Some words may be wrong. / Some pages could not be read. / Part of a page may be cut off. Check the edges. / Only the important parts were translated. The rest is in the original language. / Part of this paper could not be read safely. / Some safety checks are not available in this language yet. / This paper contained text meant for computers. I ignored it. / A phone number or link was removed because it was not printed on your paper. See Get help nearby. |

### Fixed notices, scam, emergency
| Key | English |
|---|---|
| `fixed.jury_summons` ✱ | You must answer this form. If you are not a U.S. citizen, mark *not a citizen* and send it back. Never check 'citizen' and never register to vote — it can permanently harm your immigration case. |
| `fixed.uscis_receipt_i765` ✱ | A receipt for a work-permit renewal filed on or after October 30, 2025 is **not** proof you can work. Ask a lawyer or DOJ-accredited representative about a possible work gap. |
| `fixed.pay_or_quit` ✱ / `fixed.eviction_summons` ✱ / `fixed.asylum_fee_notice` ✱ | This is not a court order. Only a court can make you leave. / The court date on this paper is the date that matters. Go, or you can lose automatically. / There is no fee waiver for this fee. |
| `fixed.address_change_multi_agency` ✱ | If you move, the court needs its own address form (EOIR-33). USPS forwarding does not update the court or USCIS. |
| `fixed.multiple_documents` | These pages look like two different papers. I explained the first one. Scan the other one on its own. |
| `scam.card.likely` ✱ | Scam risk: likely — ICE, USCIS, SSA and the IRS never demand payment by phone, gift card, wire, or app. Do not pay. Report it: |
| `scam.card.possible` | Some things in this paper look like a scam. Be careful. Do not pay or share ID numbers until you check with the real office. |
| `scam.gift_card` / `scam.wire_transfer` / `scam.payment_app` / `scam.crypto` / `scam.arrest_threat` / `scam.deportation_threat` / `scam.guaranteed` / `scam.notario` / `scam.non_gov_domain` / `scam.expedite_fee` / `scam.fee_for_free_form` / `scam.urgency_pressure` / `scam.impersonation` | Asks for gift cards / Asks for a wire transfer / Asks for a payment app / Asks for cryptocurrency / Threatens arrest / Threatens deportation / Promises a guaranteed result / Mentions a "notario" / Website is not .gov / Charges to go faster / Charges for a free form / Pushes you to hurry / Pretends to be a government office |
| `vault.title_scam_check` | Scam check |
| `emergency.title` / `emergency.free_us` / `emergency.more_help` / `emergency.desktop_note` | Need help now? / These numbers are free and work anywhere in the U.S. / More help near you / Use a phone to call. |
| `emergency.911` / `btn.call_911` | If someone is in danger or very sick, call 911. / Call 911 |
| `emergency.988` / `btn.call_988` / `btn.text_988` | If you are thinking about hurting yourself, call or text 988. It is free and private. / Call 988 / Text 988 |
| `emergency.poison` / `btn.call_poison` | If someone swallowed something dangerous, call Poison Help 1-800-222-1222. / Call Poison Help |
| `emergency.dv` / `btn.call_dv` / `btn.text_dv` | If someone at home is hurting you, call 1-800-799-7233 or text START to 88788. / Call the helpline / Text START to 88788 |
| `emergency.triggered_by` | I saw words about {kinds} on this paper. If this is happening now, use these numbers. |
| `emergency.kind.chest_pain` / `.breathing` / `.overdose` / `.poison` / `.self_harm` / `.stroke` / `.bleeding` / `.allergic` / `.violence` | chest pain / trouble breathing / overdose / poison / hurting yourself / stroke / heavy bleeding / a severe allergic reaction / violence |

### Source viewer, chat, clerk
| Key | English |
|---|---|
| `source.mode_original` / `source.mode_both` / `source.mode_translation` | Original / Both / Translation |
| `source.not_translated` / `source.unclear` / `source.handwriting` / `source.no_box` / `source.no_image` | Not translated / [unclear] / Handwriting / Position on the page not available; the words are: {quote} / Page images were not kept for this paper. Only the words are shown. |
| `chat.scope` / `chat.input_label` / `chat.history_cap` / `chat.not_in_document` / `chat.from_your_paper` | I can only answer from this paper. This is information, not legal or medical advice. / Your question / I remember the last 8 messages. / The paper does not say. / From your paper, page {page}: “{text}” |
| `chat.starter.miss_date` / `chat.starter.pay_now` / `chat.starter.bring` | What happens if I miss the date? / Do I have to pay this now? / What should I bring? |
| `chat.refusal.eligibility` | I cannot say whether you qualify. The paper says what it says; a professional can tell you what it means for you. |
| `chat.refusal.filing_advice` / `chat.refusal.outcome` / `chat.refusal.medical_interpretation` | I cannot tell you what to file or send. I can explain what the paper asks for. / I cannot predict what will happen. No one can promise a result. / I cannot say what this means for your health. Ask your doctor, nurse or pharmacist. |
| `chat.refusal.drafting` / `chat.refusal.contact_request` / `chat.refusal.out_of_scope` | I cannot write letters or fill in forms. A professional or the office itself can help with that. / I only share phone numbers and websites printed on your paper or checked by a person. See Get help nearby. / That is outside this paper. I can only help with what is written here. |
| `chat.refer.lawyer_or_accredited_rep` / `chat.refer.clinician` / `chat.refer.housing_counselor` / `chat.refer.benefits_office` / `chat.refer.sender` | A licensed lawyer or a DOJ-accredited representative can advise you about your case. Find one in Get help. / Ask your doctor, nurse or pharmacist what this means for you. / A housing lawyer or counselor can advise you. Find one in Get help. / The office that sent this paper can tell you what happens next. Its number is on the paper. / Ask the sender. Their contact is on the paper. |
| `clerk.back_to_me` / `clerk.what_it_says` / `clerk.brightness_tip` / `clerk.own_words` | Back to me / What this card says / Turn your screen brightness up. / Your words |
| `clerk.interpreter_hhs` ✱ | I may ask for a free interpreter. |
| `clerk.generic_need` / `clerk.preset.appointment` / `clerk.preset.bill` / `clerk.preset.form` / `clerk.preset.address` / `clerk.preset.benefits` | understanding a paper I received / an appointment / a bill / filling out a form — I need an interpreter / changing my address / my benefits |
| `tts.fallback_offer` / `tts.earbuds_tip` | No {language} voice on this phone. Hear it in {fallback} or English? / Plug in earbuds to listen privately. |

### Help (Action Hub)
| Key | English |
|---|---|
| `help.region` / `help.near_you` / `help.anywhere_in_us` / `help.always` / `help.offline_cached` / `help.lsc_alternative` | Where you live: {state} {zip3} / Near you / Anywhere in the U.S. / Always available / No internet. This is the last list I found for this paper. / If that is not you, try these instead |
| `state.no_local` | Nothing verified near you yet. These national services can help. |
| `need.legal` / `need.court` / `need.medical_bill` / `need.insurance` / `need.clinic` / `need.food` / `need.housing` / `need.utilities` / `need.benefits` / `need.school` / `need.work` / `need.tax` / `need.scam` / `need.crisis` / `need.interpreter` | Legal help / Court papers / Medical bills / Insurance letters / A doctor without insurance / Food / Housing or eviction / Utility shutoff / Benefits letters / School / Work and pay / Tax letters / Report a scam / Someone is in danger / An interpreter |
| `resource.free` / `resource.sliding` / `resource.paid` / `resource.unknown_cost` | Free / Pay what you can / Costs money / Cost not known |
| `resource.languages` / `resource.interpreters` / `resource.verified_on` / `resource.stale` / `resource.link_unknown` / `resource.link_unverified` | Speaks: {list} / Interpreters for 200+ languages / Verified on {date} / Last checked over 4 months ago / Website could not be auto-checked / Not yet checked by us |
| `status_note.lsc_restricted` ✱ | This organization usually cannot help people without immigration papers, except survivors of violence or trafficking. |
| `status_note.residency_required` / `.waitlist` / `.appointment_required` / `.hhs_funded_health` / `.not_endorsed` / `.manual_verify` (copy source: RESOURCE_DB §3.3; rendered from `ResourceMatch.eligibility_note_key`) | You must live in their service area. Bring proof of your address. / There is a waiting list right now. Ask to be added. / Call first to make an appointment. / You can ask for a free interpreter here. / The government publishes this list but does not endorse anyone on it. / We could not confirm every detail of this listing. Check before you go. |
| `notes.set_region_for_local_help` ✱ / `notes.county_unknown` / `notes.no_local_results` / `notes.lsc_restricted_explained` ✱ / `notes.resource_text_english_only` / `notes.verify_before_going` (copy source: RESOURCE_DB §4.3) | Set your state in Settings to see help near you. / Add the first 3 digits of your ZIP code in Settings to see more local help. / We do not have local listings for your area yet. These national services help anyone. / Some legal aid offices can only help people with certain immigration papers. / Some listing details are in English. / Hours and phone numbers change. Call before you go. |
| `warn.<key>` for every key in the RESOURCE_DB §4.3 registry (21 keys), e.g. `warn.jury_never_check_citizen` ✱ / `warn.jury_never_register_to_vote` ✱ / `warn.ask_for_plain_language_summary` ✱ | Never check 'citizen' on a jury form if you are not a U.S. citizen. / Never register to vote unless you are a U.S. citizen. It can permanently harm your immigration case. / Ask for the plain-language summary of financial assistance in your language. (the other 18 strings are in RESOURCE_DB §4.3) |
| `prepare.<key>` for every key in the RESOURCE_DB §4.4 checklist vocabulary (30 keys; `ChecklistItem.key` is the unprefixed key), e.g. `prepare.bring_notice` / `prepare.bring_case_number` / `prepare.bring_proof_income` / `prepare.bring_proof_va_address` / `prepare.bring_the_bill` / `prepare.bring_household_ids` / `prepare.bring_itemized_bill_request` / `prepare.bring_the_summons` | This letter or notice / Your case number (printed on the letter) / Proof of income (pay stubs or last tax return) / Proof of your Virginia address / The bill or account number / ID for everyone in your household / Ask for an itemized bill / The summons or court paper (the other 22 strings are in RESOURCE_DB §4.4) |

### Vault, reminders, quick sheet, feedback
| Key | English |
|---|---|
| `vault.whose_paper` / `vault.me` / `vault.add_member` / `vault.saved` / `vault.not_read_yet` / `vault.empty` / `vault.title_fallback` / `vault.sample_tag` / `vault.web_kept` | Whose paper is this? / Me / Add someone / Saved. It stays on this phone. / Not read yet / Papers you save stay only on this phone. Nothing is saved until you tap Save. / {type} · {date} / Sample / Kept in this browser (not encrypted by the app) |
| `vault.delete_confirm` / `vault.web_keep_confirm` | Delete this paper from this phone? / This browser will keep your papers. Anyone who uses this browser could open them. The app does not encrypt them. |
| `vault.privacy_native` / `vault.privacy_web` / `vault.privacy_server` | Papers you save stay on this phone, protected by your phone's own encryption. Turn on a phone passcode. / Papers you keep stay in this browser. The app does not encrypt them. / Our server does not keep your paper. |
| `member.rename` / `member.color` / `member.delete` / `member.delete_confirm` | Change name / Change color / Delete {name} and all their papers / This removes {name} and every paper saved for them. It cannot be undone. |
| `wipe.title` / `wipe.body` / `wipe.confirm` | Delete everything on this phone? / This removes all saved papers, members, reminders and settings from this phone. It cannot be undone. / Yes, delete everything |
| `settings.wipe_offer` / `settings.keep_saved` / `btn.delete_everything_web` | Do you also want to delete everything saved on this phone? / Keep my saved papers / Delete everything in this browser |
| `reminders.permission_explain` / `reminders.permission_denied` / `reminders.added` / `reminders.empty` / `reminders.past` / `reminders.estimate_blocked` / `reminders.add_own` / `reminders.on` / `reminders.off` | I can remind you 7, 3 and 1 days before this date. The reminder text is generic unless you choose otherwise. / Reminders are off for this app. The list still works here. You can turn them on in Settings. / Reminder set for {date}, and 7, 3 and 1 days before. / No dates saved yet. When I find a date on a paper, tap Remind me. / Passed / This date is an estimate. Confirm it with the sender, then add your own date. / Add my own date / On / Off |
| `reminders.lockscreen_detail` / `reminders.lockscreen_explain` / `reminders.web_explain` / `reminders.clock_warning` | Show details on the lock screen / Off: the reminder only says a date is coming. On: it shows the paper and the date on your lock screen. / Your browser cannot remind you. Add this date to your calendar instead. / Your phone's clock looks wrong. Reminders may fire at the wrong time. |
| `notif.channel_name` / `notif.generic_body` ✱ / `notif.today_body` / `notif.detail_body` | Dates to remember / You have a date coming up. / You have a date today. / {document_title}: {demand_text} on {date} |
| `quicksheet.title_suffix` / `quicksheet.dates` / `quicksheet.bring` / `quicksheet.help` / `quicksheet.questions` / `quicksheet.truncated` | — quick sheet / Dates / Bring / Who can help / Questions to ask / …and more in the app |
| `quicksheet.footer` | Made with a computer from your paper. It can be wrong. Confirm dates with the sender. Made on {date}. |
| `state.share_unavailable` | Sharing is not available here. Copy the text instead. |
| `feedback.question` / `feedback.what_wrong` / `feedback.thanks` | Was this clear? / What was wrong? / Thank you. We count your answer only. We never send your paper. |
| `feedback.kind.unclear` / `.wrong_word` / `.wrong_fact` / `.offensive` / `.scam_missed` / `.resource_problem` | Hard to understand / A word is wrong / A date, amount or fact is wrong / This is rude or offensive / This looks like a scam but the app did not say so / The phone number or website does not work |

### Troubleshoot
| Key | English |
|---|---|
| `troubleshoot.mode_portal` / `troubleshoot.mode_scam` / `troubleshoot.pick_screenshot` / `troubleshoot.goal_label` / `troubleshoot.cta` / `troubleshoot.cta_scam` | Stuck on a website / Is this a scam? / Pick a screenshot / What were you trying to do? / Explain this screen / Check this for me |
| `troubleshoot.credential_guard` / `troubleshoot.credential_detected` | Never type passwords, card numbers or ID numbers into this app. I will never ask for them. / This screen asks for a password or payment. Only type them on the official website, never here. |
| `troubleshoot.card_screen` / `troubleshoot.card_error` / `troubleshoot.card_steps` / `troubleshoot.card_cautions` / `troubleshoot.ask_person` | What this screen is / What the red text means / Do this next / Careful / Ask a person |
| `troubleshoot.step_read` / `troubleshoot.step_explain` / `state.cannot_tell` / `state.unreadable_screenshot` | Reading the screen / Explaining / I am not sure what this screen wants. Ask a person. / I could not read this screenshot. Take it again with the whole screen visible. |
| `portal.benefits_portal` / `.uscis_account` / `.eoir_portal` / `.school_portal` / `.hospital_portal` / `.insurer_portal` / `.irs_portal` / `.bank` / `.other` | Benefits website / USCIS account / Immigration court site / School site / Hospital or clinic site / Insurance site / IRS site / Bank / Other |

### Settings and errors
| Key | English |
|---|---|
| `settings.language` / `settings.voice` / `settings.hear_mode_default` / `settings.machine_translated` / `settings.reviewed_by` | Language / Voice / Read results aloud automatically / Translated by a computer / Reviewed by {name} |
| `settings.reading` / `settings.high_contrast` / `settings.region` / `settings.state_none` / `settings.zip3` / `settings.zip3_why` | Reading / High contrast / Where you live / Not set / First 3 digits of your ZIP (optional) / Only the first 3 digits. Enough to find help near you, not enough to find your home. |
| `settings.tone` / `settings.tone_plain` / `settings.tone_formal` / `settings.calendar_notes` / `settings.date_format` / `settings.tone_why` | Tone and calendar / Plain / Formal / Holidays and fasts to keep in mind / Date format / Used only to word your steps kindly, for example around a fast or a holiday. Never saved on our server. |
| `settings.papers` / `settings.keep_pages` / `settings.keep_pages_why` / `settings.hide_ids` / `settings.hide_ids_why` / `settings.lockscreen_detail` / `settings.pin` / `settings.web_keep` / `settings.web_clear_on_close` | Your saved papers / Keep page images / Keeps the photos so you can see the highlighted words later. Uses more space. / Hide ID numbers in saved copies / Hides A-numbers and receipt numbers. Turn on only if you do not need them to check your case. / Show details on the lock screen / App PIN / Keep on this device (not encrypted by the app) / Clear when I close this tab |
| `settings.data` / `settings.consent_accepted_on` / `settings.consent_not_given` | How your paper is handled / You agreed on {date} / You have not agreed yet |
| `settings.sample_mode` / `settings.sample_toggle` / `settings.sample_why` / `settings.sample_forced` | Sample mode / Sample mode / Use sample papers with a pretend helper. Nothing of yours is sent. / This server only has sample papers. |
| `settings.delete_everything` / `settings.about` / `settings.models` / `settings.developer` / `settings.developer_api_url` ✱ | Delete everything / About / Helper models: {pro}, {fast} / Developer / API address |
| `notfound.title` / `notfound.body` | I could not find that page. / Nothing was lost. Your saved papers are still here. |
| `err.invalid_request` | Something went wrong with this request. Please try again. |
| `err.too_many_pages` / `err.pdf_too_long` | You can send up to {max_pages} pages at a time. Remove some pages, or split the paper into two scans. / This PDF has too many pages. The limit is {max_pdf_pages} pages. |
| `err.unauthorized` / `err.not_found` | This app is not allowed to use the server right now. Please update the app. / I could not find that. It may have been removed. |
| `err.unpaid_tier` | This test build uses a free AI key. Real papers cannot be sent. Try a sample paper instead. |
| `err.pack_mismatch` / `err.language_unresolved` | The app needs an update before it can add this language. Choose one of these languages for now. / I could not find that language. Check the spelling, or choose one of these. |
| `err.payload_too_large` / `err.unsupported_media_type` | This file is too big. Take photos of the pages instead, or choose a smaller PDF (up to {max_pdf_mb} MB). / I can read photos (JPG, PNG, HEIC, WebP) and PDF files. This file is a different kind. |
| `err.content_blocked` | I could not read this paper safely. Try again with only the part you need, or ask a helper. |
| `err.consent_required` | Please read how your paper is handled, then try again. |
| `err.rate_limited` | You have read many papers today. Please wait {minutes} minutes, or open a saved paper. |
| `err.quota_exhausted` ✱ | Our helper is very busy right now. Try again in {minutes} minutes, or see what you can do offline. |
| `err.internal` / `err.model_output_invalid` | Something went wrong on our side. Your paper was not saved anywhere. Please try again. / I could not finish reading this paper. Please try again. If it happens again, try fewer pages. |
| `err.provider_not_configured` / `err.upstream_unavailable` | This server has no helper set up. Sample papers still work. / Our helper is not answering right now. Try again in {minutes} minutes, or see what you can do offline. |
| `err.network` / `err.timeout` | No internet. Check your connection and try again. Nothing was sent. / This is taking too long. Check your connection and try again. Your paper was not saved anywhere. |
| `fixture.<id>` (18 keys) | English titles as in `DemoFixture.title_en` (e.g. `fixture.medicaid_address_confirmation` "Medicaid letter asking to confirm your address") |
| `why.*` ✱ (matcher reason keys; copy source RESOURCE_DB §3.1 and §4.2) | `why.for_<tag>` for all 49 `ResourceTag`s (e.g. `why.for_medical_bill` "For hospital and doctor bills", `why.for_medicaid_renewal` "For Medicaid letters") plus `why.institution_match` "Named on your paper ({institution})", `why.serves_your_county` "Serves {county}", `why.serves_your_area` "Serves your area", `why.serves_your_state` "Serves {state}", `why.check_service_area` "Check that they serve your area", `why.anywhere_in_us` "Anywhere in the U.S.", `why.speaks_your_language` "Help in your language", `why.for_this_paper` "Made for this kind of paper", `why.report_scam` "To report a scam", `why.crisis_line` "Help right now" |
