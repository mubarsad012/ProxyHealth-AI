# ProxyHealth AI — Resource DB (vetted "Get help nearby" directory)

Status: **implementation spec for WP3** (`apps/api/proxyhealth_api/resources/**`, `apps/api/data/resources/**`, `scripts/check_links.py`). Conforms to `docs/DECISIONS.md` (D-10, D-12, D-13, D-14, D-18, D-24), `docs/API_CONTRACT.md` §1 (`ResourceTag`, `OrgType`, `GeoScope`, `Cost`, `StatusNoteKey`, `LinkHealth`, `VerificationMethod`) and §3.8–3.9 (`Resource`, `Serves`, `ResourceMatchRequest`, `ResourceMatch`, `ChecklistItem`, `ResourceMatchResponse`, `ResourceList`), and `docs/ARCHITECTURE.md` §2 (file tree) and §2.1 "Resource DB". Where this document and the Pydantic models disagree, the models win and this file is fixed.

Written 2026-09-27. Every URL in the seed was re-fetched on 2026-09-27 (see §12 "Verification log"). Research input: `docs/research/resources.md` (verified 2026-09-23). Only URLs that research file marks `confidence=verified` are seeded; everything else is listed in §13 "Deferred candidates" with the reason.

Binding principles (from the backbone):
1. **The model never emits a contact.** Phone numbers, URLs, addresses and organization names reach the user only from the paper (verbatim) or from this DB (D-10). The model emits `resource_tags` from the closed `ResourceTag` vocabulary; the matcher turns tags into entries.
2. **Nothing here asks or infers immigration status** (D-24). Eligibility limits are shown as plain one-sentence notes (`status_note_key`), never as filters on the user.
3. **Every entry is verifiable by a human**: `url`, `verified_on`, `verification_method`, `link_health`, and an editorial `x_meta.source` line. Unverified phone numbers are *not* stored in `phone`.
4. **Emergency numbers also live in fixed copy** (`en.json`, D-10/D-14). The DB copies of 911-adjacent lines exist so the Help tab, the quick sheet re-validation (`POST /v1/quicksheet/pdf`) and the matcher can reference them by id.
5. **Information, not advice.** `what_it_does` and `eligibility_plain` describe what an organization does and who it serves; they never say "you qualify" (D-17 phrasing rules apply to DB copy too; CI lints these strings with the same `data/safety/phrasing.yaml` patterns).

---

## 0. How the brief's field names map onto the contract

The task brief described the YAML as `id, name, org, url, phone, kind, tags[], geography{level,state,county,city}, languages[], eligibility, cost, hours, what_to_prepare[], verified_on, source, notes`. `API_CONTRACT.md` §3.8 already fixes the `Resource` model, so the YAML uses **the contract's names** and this table is the translation:

| Brief field | Contract / YAML field | Notes |
|---|---|---|
| `org` | `name` + `name_note` | `name_note` carries "formerly …" / "a project of …" |
| `kind` | `org_type: OrgType` | closed enum (§3) |
| `geography {level, state, county, city}` | `serves: Serves {scope: GeoScope, states[], counties[], cities[], zip3[]}` | lists, not scalars — one entry can serve several counties/states |
| `eligibility` | `eligibility_plain: {en: …}` | i18n map, `en` required |
| `what_to_prepare[]` | `prepare_checklist_keys: [key…]` | i18n keys; English text in `_meta.yaml` (§4.4); merged with `data/rules/prepare.yaml` per document type |
| `source`, `notes` | `x_meta: {source, notes, expect_text[]}` | **YAML-only editorial block, stripped by the loader** (§2.3); never serialized into `Resource` |
| `phone` | `phone` (E.164 or N11), plus `tty`, `text_line` | §2.2 formats |
| `hours`, `cost`, `languages`, `url`, `tags`, `verified_on` | same names | |

---

## 1. Files and layout

```
apps/api/data/resources/
  _meta.yaml                      resource_db_version, checklist vocabulary (key → text_en), why/notes templates,
                                  warning-key registry, doc_type_pins, urgent_doc_boost, well_known_ids
  national_immigration.yaml       legal help, EOIR, USCIS, ICE, asylum, Afghan/refugee, anti-fraud (USCIS/FTC/DHS OIG), Title VI
  national_health.yaml            FQHC finder, HealthCare.gov, Medicaid/CHIP, charity care, No Surprises, appeals, Medicare, labs, vaccines, HHS OCR LEP
  national_benefits_food.yaml     211, Benefit Finder, SNAP, WIC, school meals, Feeding America, SSA appeals/scams, LIHEAP
  national_housing.yaml           HUD counselors, PHA contacts, USA.gov housing, LawHelp/LSC (lsc_restricted), LSC eviction DB (staff reference)
  national_crisis.yaml            988, National DV Hotline, Poison Control, National Human Trafficking Hotline
  national_school_work_tax.yaml   NCHE/McKinney-Vento, liaison directory, Plyler, PTI centers, IDEA, DOL WHD, EEOC, OSHA, IRS notices/ITIN/scams, US Courts jury
  regional/va_nova.yaml           Northern Virginia / DC-metro exemplar set (14 entries)
```

Rules:
- Every `*.yaml` that does not start with `_` is a **YAML list of resource maps** (top-level sequence). Files starting with `_` are configuration (`_meta.yaml`) and are never parsed as resources.
- `regional/<state>_<area>.yaml` is the naming pattern for future pilot geographies (open question Q5 in DECISIONS §12). File placement is editorial only; **matching uses `serves`, never the file name**.
- The loader globs `data/resources/**/*.yaml` recursively (excluding `_*.yaml`), so adding a region needs no code change.
- `apps/api/data/resources` is the canonical copy. A small JSON subset (`well_known_ids.offline_subset`, §4.7/§7) is synced to `apps/mobile/assets/resources/national_fallbacks.json` for offline Help by `scripts/sync_to_mobile.py` (WP7; DECISIONS §14 CL-004; path listed in ARCHITECTURE §3).

---

## 2. Resource entry schema (YAML ⇄ `contracts/resources.py::Resource`)

### 2.1 Fields

| Field | Type | Required | Constraints / meaning |
|---|---|---|---|
| `id` | `str` | yes | `^[a-z0-9][a-z0-9_]{1,39}$`; unique across all files; **stable forever** (other modules reference ids, §7.4). Rename = new id + `x_meta.notes: "was <old>"`. |
| `name` | `str` | yes | ≤ 80 chars, as the organization writes it. |
| `name_note` | `str \| null` | no (null) | ≤ 120 chars, e.g. `"a Justicia Lab project, powered by probono.net (formerly Immigration Advocates Network)"`. |
| `org_type` | `OrgType` | yes | §3.2. |
| `what_it_does` | `dict[str, str]` | yes, `en` required | One or two plain sentences (grade ≤ 5). Other keys are BCP-47 tags. May contain the organization's own phone numbers/addresses as text (DB copy is trusted; the contact filter runs only on model output). |
| `url` | `str` | yes | `https://` only; the exact URL fetched at `verified_on`. No tracking parameters. |
| `alt_urls` | `list[str]` | no (`[]`) | Additional verified pages of the same organization (sub-pages, Spanish site). Same rules as `url`. |
| `phone` | `str \| null` | no (null) | E.164 (`+18003755283`) **or** a bare N11/short code (`211`, `988`, `911`). Vanity numbers are stored as digits (`+18003216742`, not `1-800-321-OSHA`); the vanity form may appear in `what_it_does`. **Only numbers read on the fetched page or on an `alt_urls` page** — otherwise `null` and the number goes to `x_meta.notes`. |
| `tty` | `str \| null` | no (null) | Same format; `"711"` allowed. |
| `text_line` | `str \| null` | no (null) | Human sentence, ≤ 60 chars: `"Text START to 88788"`. |
| `hours` | `str \| null` | no (null) | ≤ 80 chars, English, as printed: `"Mon–Fri 8:00–20:00 Eastern"`, `"24/7"`. Unknown → `null` (never guess). |
| `languages` | `list[str]` | yes (may be `["en"]`) | BCP-47 tags (`en`, `es`, `zh-Hans`, `prs`, `yue`, `hmn`, `km`…) or the literal `interpreters_200+` (organization states interpreters/200+ languages). Only what the page states. |
| `cost` | `Cost` | yes | `free \| sliding \| paid \| unknown`. |
| `serves` | `Serves` | yes | §5. |
| `tags` | `list[ResourceTag]` | yes (may be `[]` only if the id appears in `_meta.yaml.doc_type_pins`) | Closed vocabulary §3.1; ≤ 8 tags (broad entries score low anyway). |
| `status_note_key` | `StatusNoteKey \| null` | no (null) | One plain note shown under the card (§3.3). Single slot — see §3.3 for the `hhs_funded_health` derivation rule. |
| `eligibility_plain` | `dict[str, str]` | yes, `en` required | Who they serve, ≤ 2 sentences, never "you qualify". |
| `prepare_checklist_keys` | `list[str]` | no (`[]`) | Keys from `_meta.yaml.checklist` (§4.4). Order = display order. |
| `verified_on` | `date` | yes | The day a human/agent **read the page content** and confirmed the facts in this entry. An HTTP 200 alone never updates it (§8.2). |
| `verification_method` | `VerificationMethod` | yes | `fetched` (content read by fetcher) · `browser` (content read in a real browser because the site blocks fetchers) · `curl_ua` (curl with browser UA, text grepped) · `manual_verify` (facts entered from a non-web source; entry shows the `manual_verify` note). |
| `link_health` | `LinkHealth` | yes | `ok` · `unknown_403` (site blocks fetchers; page confirmed in browser) · `js_rendered` (HTTP 200, no machine-readable text) · `unverified` (Cloudflare challenge / could not load) · `broken` (404/410/DNS — excluded from matching). |
| `warnings` | `list[str]` | no (`[]`) | Fixed warning keys from `_meta.yaml.warning_keys` (§4.3), written **unprefixed** in YAML (`[ask_for_plain_language_summary]`). `_apply_defaults()` prefixes each with `warn.` so the wire value in `Resource.warnings` is the pack key (`warn.ask_for_plain_language_summary`), matching the API_CONTRACT §3.8 example; the client renders `t(key)`. |
| `priority` | `int` | yes | 0–100 editorial boost (`priority/100` is added to the score). Guidance: 90–100 crisis lines and "always-right" official pages; 70–89 primary routes per tag; 40–69 secondary/explainers; 10–39 staff references and paid directories. |
| `never_show_with_tags` | `list[ResourceTag]` | no (`[]`) | Hard exclusion when the request contains any of these tags (e.g. a paid directory never appears with `scam_report`). |
| `x_meta` | map | no | **YAML-only.** `source` (str, required when present: where each fact came from), `notes` (str), `expect_text` (list[str]: phrases/phone digits `check_links.py` greps for to detect content drift), `fetch` (str: last fetch outcome). Stripped before `Resource.model_validate`. |

Defaults: the loader fills omitted optional fields with the defaults above **before** validation, so seed YAML can omit `alt_urls`, `phone`, `tty`, `text_line`, `hours`, `name_note`, `status_note_key`, `prepare_checklist_keys`, `warnings`, `never_show_with_tags`, and `serves` sub-lists. (Cross-WP note for WP0: `contracts/resources.py` should declare the same defaults; if it does not, the loader's `_apply_defaults()` guarantees the contract is met either way.)

### 2.2 Formats the loader enforces

- `phone`, `tty`: `^(\+[1-9]\d{6,14}|211|311|911|988|711)$`.
- `languages[]`: `^(interpreters_200\+|[a-z]{2,3}(-[A-Za-z0-9]{2,8})*)$` (same shape as `LanguageTag`, lowercase primary subtag).
- `url`, `alt_urls[]`: `^https://[^\s]+$`, no `#fragment`, no `utm_` query parameters.
- `serves.states[]`: two uppercase letters from the 50 states + `DC` + `PR` + `GU` + `VI` + `AS` + `MP`.
- `serves.counties[]`: canonical form **without** the word "County" (`Fairfax`, `Loudoun`, `Prince George's`); Virginia independent cities and the District carry an explicit suffix/name: `Alexandria City`, `Fairfax City`, `Falls Church City`, `Manassas City`, `District of Columbia`. Matching normalizes case, apostrophes (`'`/`’`) and strips a trailing ` county`.
- `serves.zip3[]`: `^\d{3}$` (D-24: zip3, never full ZIP).
- `verified_on` ≤ today (server clock) and ≥ 2026-01-01.
- `what_it_does.en`, `eligibility_plain.en`: 1–300 chars; must not match `data/safety/phrasing.yaml` forbidden patterns ("you qualify", "you are eligible", "you should file", …) — the DB is user-facing copy and follows D-17.

### 2.3 Example entry (full form, then the compact form the seed uses)

```yaml
- id: inova_fa
  name: Inova Financial Assistance
  name_note: null
  org_type: hospital_program
  what_it_does:
    en: "Helps people who cannot pay an Inova hospital bill apply for free or reduced-cost care. Apply online (MyChart), by mail, or in person."
  url: https://www.inova.org/patient-and-visitor-information/financial-assistance
  alt_urls: []
  phone: "+15714725880"
  tty: null
  text_line: null
  hours: "Mon–Fri 8:00–16:30"
  languages: [en, es, am, ar, prs, fa, ko, zh-Hans, ur, vi]
  cost: free
  serves:
    scope: county
    states: [VA]
    counties: [Fairfax, Loudoun, Arlington, Alexandria City, Fairfax City, Falls Church City]
    cities: []
    zip3: ["201", "220", "221", "222", "223"]
  tags: [medical_bill, charity_care]
  status_note_key: residency_required
  eligibility_plain:
    en: "You must live in the Inova service area in Virginia. Uninsured people with lower incomes often pay nothing. Ask for the plain-language summary in your language."
  prepare_checklist_keys: [bring_proof_income, bring_proof_va_address, bring_the_bill, bring_household_ids]
  verified_on: 2026-09-27
  verification_method: fetched
  link_health: ok
  warnings: [ask_for_plain_language_summary]
  priority: 80
  never_show_with_tags: []
  x_meta:
    source: "resources.md §2 row 1 (2026-09-23); re-fetched 2026-09-27: phone + hours + 10 summary languages confirmed on page; 400% FPL tier not visible in main text today"
    expect_text: ["571-472-5880", "Financial Assistance"]
```

The seed in §11 uses YAML flow style and omits defaulted fields; both forms load identically.

---

## 3. Closed vocabularies

### 3.1 `ResourceTag` (must equal `contracts/enums.py::ResourceTag` — 49 values, CI-asserted)

The matcher, the prompts (`ai/prompts/tag.md`, `analyze.md`) and the DB share this list. `analysis/tagging.py` drops any model tag not in it. Column "why (en)" is the English `why.for_<tag>` template served in `ResourceMatch.why`; column "primary seed ids" is what the loader asserts exists (a tag with **zero** active entries fails boot; the two marked *fallback-only* are carried only by broad entries and are allow-listed so the boot check warns instead of failing if those entries are retired).

| Tag | Meaning (routing intent) | why (en) `why.for_<tag>` | Primary seed ids |
|---|---|---|---|
| `immigration_legal_help` | find a free/low-cost immigration lawyer or DOJ-accredited rep | "For immigration legal help" | immlawhelp, eoir_probono, eoir_roster, uscis_find_legal, lajc, ayuda, just_neighbors, nvfs |
| `removal_proceedings` | in immigration court (NTA, hearings, ICE) | "For immigration court cases" | eoir_probono, eoir_hotline, eoir_acis, eoir_icor, eoir_court_finder, ice_checkin |
| `asylum` | asylum applicants (I-589, fees, interviews) | "For asylum cases" | asap, uscis_asylum, uscis_hr1_fees, immlawhelp |
| `daca_tps` | DACA / TPS re-registration | "For DACA and TPS" | uscis_tps, immlawhelp, just_neighbors |
| `work_permit` | EAD (I-765) questions | "For work permits" | uscis_i765, uscis_contact, asap |
| `green_card` | I-90 / I-751 / permanent-resident cards | "For Green Card questions" | uscis_replace_green_card, uscis_contact |
| `naturalization` | N-400, interview, oath | "For citizenship forms" | uscis_naturalization, uscis_contact |
| `change_of_address` | AR-11 / EOIR-33 moves | "For reporting a move" | uscis_address, eoir_forms |
| `fee_waiver` | fee questions and waivers (incl. "no waiver" notices) | "For fee questions" | eoir_forms, uscis_hr1_fees, uscis_forms_free |
| `afghan_specific` | Afghan parolees / SIV / re-parole | "For Afghan newcomers" | uscis_afghan, orr_afghan_benefits, afghanevac |
| `refugee_services` | resettlement agencies, ORR contacts | "For refugee services" | orr_state_contacts, irc, uscri, hias, global_refuge, cws, world_relief, ecdc, switchboard, nvfs |
| `court_notice` | verify a court date, find the court, court forms | "For court dates and notices" | eoir_hotline, eoir_acis, eoir_court_finder, eoir_forms, eoir_icor |
| `jury_summons` | jury qualification forms | "For jury summons questions" | uscourts_jury |
| `traffic_court` | traffic/criminal court notices (*fallback-only*: no verified national resource) | "For court notices" | lawhelp, immlawhelp (via pins) |
| `medical_bill` | hospital/doctor bills, statements | "For hospital and doctor bills" | cms_medical_bill_rights, dollarfor, irs_501r, inova_fa, lajc |
| `charity_care` | hospital financial assistance | "For free or reduced-cost hospital care" | dollarfor, irs_501r, inova_fa |
| `insurance_denial` | denials, prior auth, EOB disputes | "For insurance denials and appeals" | healthcare_appeals, cms_medical_bill_rights, medicare_appeals, healthcare_gov |
| `medicare_appeal` | Medicare/MA/Part D appeals | "For Medicare appeals" | medicare_appeals |
| `medicaid_renewal` | Medicaid/CHIP renewals and notices | "For Medicaid letters" | medicaid_state, healthcare_gov, insurekidsnow |
| `prescription_help` | prescription labels, cost, interpreter at pharmacy (*fallback-only* for cost help; see §13) | "For prescriptions" | hrsa_fqhc, neighborhood_health, hhs_ocr_lep (via pins) |
| `primary_care_uninsured` | low-cost clinics | "For low-cost clinics" | hrsa_fqhc, neighborhood_health, fairfax_chcn |
| `lab_results` | understanding lab reports | "For questions about lab results" | medlineplus_labs |
| `vaccine_records` | find/replace vaccine records; school requirements | "For vaccine records" | cdc_iis, school_vaccine_requirements, hrsa_fqhc |
| `language_access` | interpreter rights, discrimination by language | "For interpreter rights" | hhs_ocr_lep, doj_title_vi, ayuda |
| `food` | food banks, pantries | "For food help" | feeding_america, cafb, 211, snap_state, nvfs, fairfax_csp |
| `wic` | WIC | "For WIC" | signupwic, wic |
| `school_meals` | free/reduced school meals | "For school meals" | school_meals |
| `snap` | SNAP notices/interviews | "For SNAP (food stamps)" | snap_state |
| `ssa_benefits` | SSA letters and appeals | "For Social Security letters" | ssa_appeals, ssa_scams |
| `benefits_navigation` | "where do I start" benefits help | "For help finding benefits" | 211, usa_benefit_finder, medicaid_state, fairfax_csp, orr_state_contacts |
| `housing_counseling` | HUD counselors, tenant rights | "For housing counseling" | hud_counselor, usa_housing_help, va_eviction_helpline, nvfs |
| `eviction` | pay-or-quit, summons, unlawful detainer | "For eviction notices" | hud_counselor, lawhelp, lsc_find, va_courts_landlord_tenant, va_eviction_helpline, lajc, fairfax_sheriff_eviction |
| `rent_assistance` | emergency rent help | "For rent help" | 211, fairfax_csp, nvfs, usa_housing_help |
| `utility_shutoff` | shutoff notices, LIHEAP | "For power, gas or water shutoff notices" | liheap, 211, fairfax_csp |
| `section8` | HCV/PHA recertification | "For Section 8 and housing vouchers" | hud_pha |
| `school_enrollment` | enrolling a child, records, residency | "For school enrollment" | plyler_explainer, nche_mckinney_vento, shc_liaison_directory, cdc_iis |
| `special_education` | IEP / 504 | "For IEP and 504 plans" | pti_centers, ed_idea |
| `homeless_students` | McKinney-Vento rights | "For students without stable housing" | nche_mckinney_vento, shc_liaison_directory |
| `workers_rights` | general workplace problems | "For workplace problems" | dol_whd, eeoc, osha, lajc, lawhelp |
| `wage_theft` | unpaid wages/overtime | "For unpaid wages" | dol_whd, lajc |
| `discrimination` | national-origin/other discrimination | "For discrimination at work" | eeoc, doj_title_vi |
| `workplace_safety` | OSHA | "For unsafe work conditions" | osha |
| `tax_notice` | IRS letters | "For IRS letters" | irs_notice_lookup, irs_scams |
| `itin` | ITIN / W-7 | "For ITIN questions" | irs_itin |
| `scam_report` | report or check a scam | "To report a scam" | dhs_oig, ftc_reportfraud, ftc_immigrant_scams, uscis_scams, irs_scams, ssa_scams, eoir_roster, uscis_find_legal, uscis_forms_free, ftc_gift_card_scams, ftc_job_scams |
| `crisis` | mental-health crisis, general crisis line | "Help right now" | 988, 211, dv_hotline, poison, trafficking |
| `domestic_violence` | DV hotline and survivor legal help | "For domestic violence" | dv_hotline, tahirih, ayuda, just_neighbors, trafficking |
| `trafficking` | trafficking hotline | "For human trafficking" | trafficking, tahirih |
| `poison` | poison control | "For poison emergencies" | poison |

Tag groups used by `national_fallbacks` (§6.9): **immigration group** = {immigration_legal_help, removal_proceedings, asylum, daca_tps, work_permit, green_card, naturalization, change_of_address, fee_waiver, afghan_specific, refugee_services, court_notice}; **health group** = {medical_bill, charity_care, insurance_denial, medicare_appeal, medicaid_renewal, prescription_help, primary_care_uninsured, lab_results, vaccine_records}.

### 3.2 `OrgType` usage in the seed

| OrgType | Use for |
|---|---|
| `government` | agency information/contact pages (USCIS, EOIR, CMS, IRS, county programs) |
| `court` | court self-help pages, US Courts |
| `nonprofit` | nonprofits that are not primarily a legal-aid program (ASAP, Dollar For, NVFS, Plyler explainer, #AfghanEvac, Switchboard, VPLC eviction site) |
| `legal_aid_lsc` | LSC-funded programs (none seeded individually; LawHelp/LSC finders are `directory` + `lsc_restricted`) |
| `legal_aid_nonlsc` | reserved for legal-aid programs confirmed not LSC-funded (none asserted in v1 — LAJC/Ayuda/Just Neighbors are `nonprofit` until confirmed) |
| `doj_accredited` | reserved for a specific DOJ-recognized organization (none seeded; the roster is a `directory`) |
| `hospital_program` | hospital financial assistance (Inova) |
| `fqhc` | federally qualified health centers (Neighborhood Health) |
| `hotline` | phone-first services (988, DV, Poison, Trafficking, 211, EOIR hotline, DHS OIG) |
| `directory` | finders/lists (ImmigrationLawHelp, EOIR lists, LawHelp, LSC, HRSA, Medicaid state list, SNAP directory, HUD finders, ORR contacts, CDC IIS, PTI finder, SignUpWIC, Feeding America, Benefit Finder, liaison directory) |
| `food_bank` | Capital Area Food Bank |
| `resettlement` | national resettlement agencies |
| `utility_program` | LIHEAP |
| `private_directory` | paid-attorney directories (AILA) |

The diversity cap (§6.7) is ≤ 2 results per `org_type`, so keep `directory` for true finders only.

### 3.3 `StatusNoteKey` — plain copy and semantics

Rendered by the client from the pack (`status_note.<key>`); English base strings (WP0 adds to `en.json`; listed here as the reviewed source):

| Key | English copy | Matcher effect |
|---|---|---|
| `lsc_restricted` | "This organization usually cannot help people without immigration papers, except survivors of violence or trafficking." + link line "If that is not you, try these instead" → `immlawhelp`, `eoir_probono` (D-24) | −0.2; never hidden; adds `notes.lsc_restricted_explained` |
| `residency_required` | "You must live in their service area. Bring proof of your address." | none |
| `waitlist` | "There is a waiting list right now. Ask to be added." | none |
| `appointment_required` | "Call first to make an appointment." | none |
| `hhs_funded_health` | "You can ask for a free interpreter here." | none; used by `analysis/clerk.py` (D-18) |
| `not_endorsed` | "The government publishes this list but does not endorse anyone on it." | none |
| `manual_verify` | "We could not confirm every detail of this listing. Check before you go." | −0.2 |

**HHS-funded derivation rule (D-18).** `status_note_key` is a single slot, and Inova needs `residency_required`. Therefore `resources/loader.py` exposes `Resource.is_hhs_funded_health` **as a computed helper, not a field**: `status_note_key == "hhs_funded_health" or org_type in {"fqhc", "hospital_program"}` (hospitals and FQHCs take Medicare/Medicaid/HRSA funds; HHS OCR LEP rights apply). `clerk.py` calls `repo.is_hhs_funded(resource_id)`. For the *sender* side (a letter from a hospital, pharmacy, insurer or state Medicaid agency) `clerk.py` uses `sender_kind ∈ {hospital_or_clinic, pharmacy, insurer}` or `document_type == medicaid_renewal` — WP2's rule; noted here so both halves agree. Reported as a backbone gap in the summary.

### 3.4 `LinkHealth` / `VerificationMethod` — how the seed assigns them

| Fetch outcome on 2026-09-27 | `verification_method` | `link_health` | `verified_on` |
|---|---|---|---|
| 200 with readable content matching the research facts | `fetched` | `ok` | `2026-09-27` |
| 403 to the fetcher (site confirmed 2026-09-23 in a browser by the research pass) | `browser` | `unknown_403` | `2026-09-23` |
| 200 but a JavaScript shell with no readable text (content confirmed 2026-09-23 in a browser) | `browser` | `js_rendered` | `2026-09-23` |
| Cloudflare challenge / could not load | `manual_verify` | `unverified` | research date |
| 404/410/DNS | — | `broken` | entry **dropped** from the seed |

No seed entry is `broken` or `unverified` today. travel.state.gov (Afghan SIV) stays out of the seed entirely (§13).

---

## 4. Server-side copy registry: `data/resources/_meta.yaml`

The matcher returns English strings in three places (`ResourceMatch.why`, `ChecklistItem.text_en`, and — via keys — `notes_keys`/`why_keys`/`eligibility_note_key`/`warnings`). All English text the **server** needs lives in `_meta.yaml`; the **client** renders the same keys from the language pack (`prepare.<key>`, `why.<key>`, `notes.<key>`, `status_note.<key>`, `warn.<key>`). CI (`tests/unit/test_loader.py::test_meta_keys_in_en_json`) asserts every key below exists in `apps/api/data/langpacks/en.json` with identical English text (WP0 adds them; until then the test is marked `xfail(strict=False)` and logs the missing keys).

### 4.1 `resource_db_version`

`resource_db_version: "2026-09-27"` — bump on every seed change (ISO date; append `-2`, `-3` for same-day changes). Served in `ServerConfig.resource_db_version`, `ResourceMatchResponse.resource_db_version`, `ResourceList.resource_db_version`.

### 4.2 `why` templates (`why_keys` → `why`)

| Key | English (`{placeholders}` filled by the matcher) |
|---|---|
| `why.for_<tag>` | see §3.1 column "why (en)" (49 entries) |
| `why.institution_match` | "Named on your paper ({institution})" |
| `why.serves_your_county` | "Serves {county}" |
| `why.serves_your_area` | "Serves your area" (zip3 match without a county name) |
| `why.serves_your_state` | "Serves {state}" |
| `why.check_service_area` | "Check that they serve your area" |
| `why.anywhere_in_us` | "Anywhere in the U.S." |
| `why.speaks_your_language` | "Help in your language" |
| `why.for_this_paper` | "Made for this kind of paper" |
| `why.report_scam` | "To report a scam" |
| `why.crisis_line` | "Help right now" |

`{state}` renders the full state name from a 51-row table in `_meta.yaml` (`state_names`), `{county}` the canonical county string (with " County" appended unless it ends in "City" or is "District of Columbia").

### 4.3 `notes_keys` and warning keys

`notes_keys` (response-level):

| Key | English |
|---|---|
| `notes.set_region_for_local_help` | "Set your state in Settings to see help near you." |
| `notes.county_unknown` | "Add the first 3 digits of your ZIP code in Settings. Then you will see more local help." |
| `notes.no_local_results` | "We do not have local listings for your area yet. These national services help anyone." |
| `notes.lsc_restricted_explained` | "Some legal aid offices can only help people with certain immigration papers." (response-level line; the per-card `status_note.lsc_restricted` sentence and the `help.lsc_alternative` link are rendered on the card itself — PRODUCT_SPEC S11) |
| `notes.resource_text_english_only` | "Some listing details are in English." |
| `notes.verify_before_going` | "Hours and phone numbers change. Call before you go." |

`warning_keys` registry (entry-level `warnings[]`; client copy `warn.<key>`):

| Key | English |
|---|---|
| `jury_never_check_citizen` | "Never check 'citizen' on a jury form if you are not a U.S. citizen." |
| `jury_never_register_to_vote` | "Never register to vote unless you are a U.S. citizen. It can permanently harm your immigration case." |
| `ask_for_plain_language_summary` | "Ask for the plain-language summary of financial assistance in your language." |
| `address_change_multi_agency` | "USCIS, the immigration court, the BIA and ICE each need their own address form." |
| `usps_does_not_forward_uscis` | "The post office does not forward USCIS mail." |
| `ead_receipt_not_work_authorization` | "A receipt for a work-permit renewal filed on or after October 30, 2025 is not proof you can work." |
| `tps_dates_from_federal_register` | "TPS dates come from official notices and change often. Check the country page." |
| `forms_are_free` | "USCIS forms and online accounts are always free." |
| `asylum_rules_aug_2026` | "Since August 21, 2026, evidence is due 14 days before an asylum interview, and rescheduling needs a strong reason." |
| `no_fee_waiver_hr1` | "There is no fee waiver for this fee." |
| `verify_local_office_open` | "Check that the local office is still open before you go. Some offices closed in 2025–2026." |
| `hr1_coverage_changes` | "Health coverage rules for many immigrants changed in 2026 and 2027. Ask a navigator what applies to you." |
| `staff_reference` | "For helpers and caseworkers." |
| `schools_may_not_ask_status` | "Public schools may not ask about immigration status or require a Social Security number to enroll a child." |
| `eeoc_deadline_180_300` | "Discrimination charges usually must be filed within 180 days (300 in some states)." |
| `osha_retaliation_30d` | "Retaliation complaints to OSHA must be filed within 30 days." |
| `court_date_is_the_deadline` | "The court date on this paper is the date that matters. Go, or you can lose automatically." |
| `not_a_court_order` | "This is not a court order. Only a court can make you leave." |
| `law_changes_2027` | "This law changes again on July 1, 2027. Confirm with the court or a legal helpline." |
| `lsc_eviction_db_2021` | "This database describes laws as of January 1, 2021. Confirm current rules with a legal helpline." |
| `medicare_windows_changed` | "Medicare plan appeal windows changed in 2026. Use the date printed on your notice." |

### 4.4 Checklist vocabulary (`checklist`: key → `text_en`)

| Key | text_en |
|---|---|
| `bring_notice` | "This letter or notice" |
| `bring_case_number` | "Your case number (printed on the letter)" |
| `bring_receipt_number` | "Your receipt number (3 letters, then 10 digits)" |
| `bring_a_number` | "Your A-number (Alien Registration Number, 8 or 9 digits)" |
| `bring_hearing_notice` | "Your hearing notice" |
| `bring_subject_id` | "The Subject ID and place of birth printed on your ICE paperwork" |
| `bring_photo_id` | "A photo ID (passport, driver's license, or Green Card)" |
| `bring_household_ids` | "ID for everyone in your household" |
| `bring_proof_income` | "Proof of income (pay stubs or last tax return)" |
| `bring_pay_stubs` | "Your pay stubs" |
| `bring_tax_return` | "Your last tax return, if you have one" |
| `bring_proof_address` | "Proof of where you live (a bill or lease with your name)" |
| `bring_proof_va_address` | "Proof of your Virginia address" |
| `bring_proof_rent_utilities` | "Your rent, power, gas and water bills" |
| `bring_the_bill` | "The bill or account number" |
| `bring_itemized_bill_request` | "Ask for an itemized bill" |
| `bring_insurance_card` | "Your insurance card, if you have one" |
| `bring_denial_letter` | "The denial letter" |
| `bring_the_summons` | "The summons or court paper" |
| `bring_lease` | "Your lease" |
| `bring_shutoff_notice` | "The shutoff notice" |
| `bring_hours_log` | "A list of the days and hours you worked" |
| `bring_employer_info` | "Your employer's name, address, and phone" |
| `bring_school_records` | "Your child's school papers (report cards, test results)" |
| `bring_vaccine_record` | "Your child's vaccine record, if you have it" |
| `bring_passport_or_two_ids` | "Your passport, or two other ID documents" |
| `bring_name_of_helper` | "The full name of the person or office you want to check" |
| `bring_proof_income_or_benefit_card` | "Proof of income, or your Medicaid, SNAP or TANF card" |
| `bring_the_child` | "Bring the child" |
| `bring_medication_list` | "All your medicine bottles or a list of them" |

Rule: checklist text names documents and actions only; it never names an agency by phone/URL (those come from the entry itself).

### 4.5 `doc_type_pins` (document type → resource ids added to the candidate set)

Explainers that belong to one document type would otherwise need tag pollution (there is no `uscis_notice` tag in `ResourceTag`). Pinned ids enter the candidate set with `+0.5` and `why.for_this_paper`; **geo filters still apply** (a Virginia-only pin is dropped for a Texas user), diversity and `limit` still apply.

```yaml
doc_type_pins:
  uscis_receipt:       [uscis_i797_types, uscis_contact]
  uscis_rfe:           [uscis_i797_types, uscis_contact, immlawhelp]
  uscis_noid:          [immlawhelp, eoir_roster]
  uscis_biometrics:    [uscis_biometrics_page, uscis_contact]
  uscis_interview:     [uscis_contact]
  uscis_approval:      [uscis_i797_types]
  uscis_denial:        [immlawhelp, eoir_probono]
  nta:                 [eoir_hotline, eoir_acis, eoir_probono, eoir_icor]
  hearing_notice:      [eoir_hotline, eoir_acis, eoir_court_finder]
  ij_decision:         [eoir_probono, eoir_forms, eoir_hotline]
  bia_notice:          [eoir_hotline, eoir_probono]
  ice_checkin:         [ice_checkin]
  ead_related:         [uscis_i765, uscis_contact]
  green_card_related:  [uscis_replace_green_card, uscis_contact]
  tps_related:         [uscis_tps]
  asylum_fee_notice:   [asap, uscis_hr1_fees]
  parole_related:      [uscis_contact, uscis_afghan]
  medical_bill:        [cms_medical_bill_rights, dollarfor]
  eob:                 [healthcare_appeals]
  insurance_denial:    [healthcare_appeals]
  prior_auth:          [healthcare_appeals]
  lab_result:          [medlineplus_labs]
  prescription_label:  [hhs_ocr_lep, hrsa_fqhc]
  discharge_instructions: [hhs_ocr_lep]
  vaccine_record:      [cdc_iis]
  appointment_reminder: []
  medicaid_renewal:    [medicaid_state]
  snap_notice:         [snap_state]
  wic_notice:          [signupwic]
  ssa_letter:          [ssa_appeals, ssa_scams]
  pay_or_quit:         [hud_counselor, va_code_pay_or_quit, va_courts_landlord_tenant]
  eviction_summons:    [va_courts_landlord_tenant, va_eviction_helpline, lawhelp, hud_counselor]
  lease:               [hud_counselor]
  rent_increase:       [hud_counselor]
  section8_recert:     [hud_pha]
  utility_shutoff:     [liheap, "211"]
  school_enrollment:   [plyler_explainer, nche_mckinney_vento]
  immunization_notice: [school_vaccine_requirements, cdc_iis]
  iep_504_notice:      [pti_centers]
  school_meals:        [school_meals]
  report_card:         []
  w2_1099:             []
  i9:                  [uscis_i765]
  offer_letter:        [ftc_job_scams]
  pay_stub:            [dol_whd]
  irs_notice:          [irs_notice_lookup, irs_scams]
  itin:                [irs_itin]
  jury_summons:        [uscourts_jury]
  traffic_court:       [immlawhelp, lawhelp]
  other_notice:        []
  unknown:             []
```

The loader asserts every key is a `DocumentType` and every id exists.

### 4.6 `urgent_doc_boost` (the brief's "urgency boost")

`ResourceMatchRequest` carries no urgency field (by contract), so the boost keys off `document_type`, mirroring the D-12 urgency floors. Entries carrying any listed tag get `+0.5`.

```yaml
urgent_doc_boost:
  nta:              [court_notice, removal_proceedings]
  hearing_notice:   [court_notice, removal_proceedings]
  uscis_noid:       [immigration_legal_help]
  eviction_summons: [eviction]
  pay_or_quit:      [eviction, rent_assistance]
  utility_shutoff:  [utility_shutoff]
  asylum_fee_notice: [asylum]
  ice_checkin:      [removal_proceedings]
```

### 4.7 `well_known_ids` (asserted at boot; other modules reference them)

```yaml
well_known_ids:
  fallback_always: ["211"]
  fallback_immigration: [immlawhelp]
  fallback_health: [hrsa_fqhc]
  fallback_scam: [ftc_reportfraud, dhs_oig]
  fallback_emergency: ["988", dv_hotline, poison]
  lsc_alternative: [immlawhelp, eoir_probono]          # D-24 "If that is not you, try these instead"
  verify_court_date: eoir_hotline                       # D-12 verify_resource_id for hearing dates
  verify_uscis_date: uscis_contact                      # D-12 verify_resource_id for USCIS dates
  scam_card_phone: dhs_oig                              # D-13 fixed scam card pulls phone from this id
  scam_card_url: ftc_reportfraud                        # D-13 fixed scam card pulls URL from this id
  emergency_card: ["988", poison, dv_hotline]           # D-14 (numbers also in fixed copy)
  offline_subset: ["211", "988", dv_hotline, poison, trafficking, immlawhelp, eoir_probono, hrsa_fqhc, dhs_oig, ftc_reportfraud, eoir_hotline, uscis_contact, lawhelp, feeding_america, liheap, hud_counselor]
```

### 4.8 `data/rules/prepare.yaml` (WP3-owned since the 2026-09-27 consistency pass — DECISIONS §14 CL-003; the only file under `data/rules/` not owned by WP2, because its keys must exist in §4.4)

`resources/checklist.py` merges `resource.prepare_checklist_keys` with `prepare.yaml[document_type]` (resource items first, then document items, de-duplicated, max 8). Format and seed (WP3 places it; `DOCUMENT_TAXONOMY.md` §4 may recommend additions per type; keys must exist in §4.4):

```yaml
# data/rules/prepare.yaml  — document type → extra checklist keys (must exist in data/resources/_meta.yaml.checklist)
uscis_rfe:        [bring_notice, bring_receipt_number]      # "the RFE notice itself on top of your response" is fixed copy in fixed_notices.yaml
uscis_noid:       [bring_notice, bring_receipt_number]
uscis_biometrics: [bring_notice, bring_photo_id]
uscis_interview:  [bring_notice, bring_photo_id]
nta:              [bring_notice, bring_a_number]
hearing_notice:   [bring_hearing_notice, bring_a_number]
ice_checkin:      [bring_notice, bring_subject_id, bring_photo_id]
asylum_fee_notice: [bring_notice, bring_a_number, bring_receipt_number]
medical_bill:     [bring_the_bill, bring_itemized_bill_request, bring_insurance_card, bring_proof_income]
eob:              [bring_notice, bring_the_bill]
insurance_denial: [bring_denial_letter, bring_insurance_card]
prior_auth:       [bring_notice, bring_insurance_card]
prescription_label: [bring_medication_list]
medicaid_renewal: [bring_notice, bring_case_number, bring_proof_address, bring_proof_income]
snap_notice:      [bring_notice, bring_household_ids, bring_proof_income, bring_proof_rent_utilities]
wic_notice:       [bring_household_ids, bring_proof_address, bring_proof_income_or_benefit_card, bring_the_child]
ssa_letter:       [bring_notice, bring_photo_id]
pay_or_quit:      [bring_notice, bring_lease]
eviction_summons: [bring_the_summons, bring_lease, bring_proof_rent_utilities]
section8_recert:  [bring_notice, bring_proof_income, bring_household_ids]
utility_shutoff:  [bring_shutoff_notice, bring_proof_income, bring_household_ids]
school_enrollment: [bring_proof_address, bring_vaccine_record]
immunization_notice: [bring_notice, bring_vaccine_record]
iep_504_notice:   [bring_notice, bring_school_records]
pay_stub:         [bring_pay_stubs, bring_hours_log, bring_employer_info]
irs_notice:       [bring_notice, bring_tax_return]
itin:             [bring_passport_or_two_ids, bring_tax_return]
jury_summons:     [bring_the_summons]
```

---

## 5. Geography model

`Serves { scope: GeoScope, states: list[str], counties: list[str], cities: list[str], zip3: list[str] }` describes **where the organization serves**, not where it sits. The request supplies `state` (2 letters, from Settings, never inferred), optional `county` (string) and optional `zip3` (3 digits). No GPS, no full ZIP, no city on the request (D-24).

| `scope` | Required lists | Meaning |
|---|---|---|
| `national` | all lists empty | anyone in the U.S. (phone/web services, federal pages) |
| `state` | `states` ≥ 1; others empty | statewide programs (Virginia courts self-help; multi-state nonprofits list each state) |
| `county` | `states` ≥ 1, `counties` ≥ 1; `zip3` recommended | county-level programs; `counties` names in the canonical form of §2.2 |
| `city` | `states` ≥ 1, `cities` ≥ 1, **and** `counties` ≥ 1 or `zip3` ≥ 1 | city programs; because the request has no city, city-scoped entries must also list the containing counties or zip3s or they can never match |

Northern Virginia zip3 reference used by the seed: `201` (Loudoun/Herndon/Reston/Prince William/Manassas), `220`–`221` (Fairfax County and Fairfax City, Falls Church), `222` (Arlington), `223` (Alexandria City). DC is `200`, `202`–`205`; Maryland suburbs `207`–`209`. A county-scoped entry should list **both** counties and zip3s so it matches whichever the user supplied.

Geo credit (used in §6.3):

| Situation | `geo` | `why_keys` |
|---|---|---|
| resource `national` | 0.5 | `why.anywhere_in_us` |
| resource `state` and user's state ∈ `states` | 0.7 | `why.serves_your_state` |
| resource `county`/`city`, user's state ∈ `states`, and (user county ∈ `counties` or user zip3 ∈ `zip3`) | 1.0 | `why.serves_your_county` (county known) else `why.serves_your_area` |
| resource `county`/`city`, user's state ∈ `states`, user gave **no** county and **no** zip3 | 0.9 | `why.check_service_area`; response adds `notes.county_unknown` |
| resource `county`/`city`, user's state ∈ `states`, user county/zip3 known but **not** listed | excluded | — |
| resource `state`/`county`/`city`, user's state ∉ `states` | excluded | — |
| user state unknown | only `national` eligible | response adds `notes.set_region_for_local_help` |

Fallback order is therefore **county → state → national**, expressed as a score gradient rather than a hard tier switch, so a strong national resource can still outrank a weak local one, and the `national_fallbacks` list guarantees national coverage even when local results fill `results`.

---

## 6. Matching algorithm (`resources/matcher.py`, deterministic, pure functions, unit-tested)

Signature: `match(req: ResourceMatchRequest, repo: ResourceRepo, meta: Meta, today: date) -> ResourceMatchResponse`. No randomness, no model calls, no I/O; identical results for identical input (the golden tests depend on it).

### 6.1 Candidate set

`candidates = {r ∈ repo.active : r.link_health != broken and r.stale_days(today) ≤ 365}` where
- `r ∈ tag_candidates` if `set(r.tags) ∩ set(req.tags) ≠ ∅`, **or**
- `r.id ∈ meta.doc_type_pins[req.document_type]` (when `document_type` given), **or**
- forced entries (§6.6).

Then remove any `r` with `set(r.never_show_with_tags) ∩ set(req.tags) ≠ ∅`, and apply the geo exclusions of §5.

### 6.2 Tag score

`primary = req.tags[0]` (the client puts the analysis' first `resource_tag` first; Help tiles send a single tag).

```
J = |R ∩ S| / |R ∪ S|            # R = request tags, S = resource tags (Jaccard)
tag_score = 2.0 * J + (1.0 if primary in S else 0.0)
```
Pinned-only entries (no tag overlap) get `tag_score = 0`.

### 6.3 Geo, language, institution, priority, pins, boosts

- `geo` from §5 (0.5 / 0.7 / 0.9 / 1.0).
- `language`: `1.0` if `req.language ∈ r.languages` or `"interpreters_200+" ∈ r.languages`; `0.9` if the primary subtag matches (`zh` vs `zh-Hans`; `fa` vs `prs` are **not** treated as the same language — the pack tables decide, `_meta.yaml.language_families` lists the few allowed pairs: `zh/zh-Hans/zh-Hant/yue`, `pt/pt-BR`, `prs/fa`); `0.8` otherwise. Language never excludes. Adds `why.speaks_your_language` at 1.0.
- `institution`: `+0.5` when any `institutions_as_written` item fuzzy-matches `r.name` or `r.name_note` (normalize: NFKC, lowercase, strip punctuation and the words "the", "inc", "health system", "hospital"; match if one normalized string contains the other or `difflib.SequenceMatcher.ratio() ≥ 0.85`). Adds `why.institution_match`. The request strings are untrusted and the contract bounds only the list (≤ 10), so each item is trimmed, cut to **200 characters** (`MAX_INSTITUTION_CHARS`), normalized **once per request** and de-duplicated before it is compared with the DB names (which are normalized once per entry); the echoed `{institution}` is that bounded string. One request therefore costs the same small, fixed work whatever its size (code-authoritative, §15 item 13).
- `priority_score = r.priority / 100`.
- `pin = +0.5` if pinned for `req.document_type` (adds `why.for_this_paper`).
- `doc_boost = +0.5` if `req.document_type ∈ meta.urgent_doc_boost` and `set(r.tags) ∩ boost_tags ≠ ∅`.

### 6.4 Penalties

| Condition | Penalty |
|---|---|
| `status_note_key == lsc_restricted` | −0.2 (shown, never hidden; sets `eligibility_note_key`, adds `notes.lsc_restricted_explained`) |
| `status_note_key == manual_verify` or `verification_method == manual_verify` | −0.2 (once) |
| `link_health ∈ {unknown_403, js_rendered}` | −0.1 |
| `link_health == unverified` | −0.3 |
| `today − verified_on > 120 days` | −0.3 |
| `today − verified_on > 365 days` | excluded (§6.1) |

### 6.5 Total

```
score = tag_score + geo + language + institution + priority_score + pin + doc_boost − penalties
```
rounded to 2 decimals in the response. **`score` is for ordering only**; the client never shows it. The literal numbers in `API_CONTRACT.md` §3.8 examples (6.4 / 3.8 / 2.9) are illustrative; matcher tests assert **order**, not those values.

### 6.6 Forced ordering

1. `req.emergency == true` → the **dedicated** crisis lines — entries whose tags **all** lie in `{crisis, poison, domestic_violence, trafficking}` — come first, each with `why.crisis_line` prepended; inside the block the order is the `well_known_ids.emergency_card` slot, then `priority`, then score. Multi-purpose entries that carry only one of those tags (`211`, DV legal nonprofits) rank normally, so example E's bill resources still follow the hotlines (code-authoritative, CL-025(c)).
2. `req.scam_risk == likely` → entries tagged `scam_report` come first (after crisis entries if both), ordered by `priority`, then score (so `dhs_oig` leads), each with `why.report_scam` prepended; the D-13 fixed card separately reads `dhs_oig.phone` and `ftc_reportfraud.url` by id.
3. Everything else by `score` desc, then `priority` desc, then `id` asc (stable).

### 6.7 Diversity cap and limit

Walk the ordered list; keep an entry only while fewer than **2** results share its `org_type` (crisis-forced entries are exempt from the cap; scam-forced entries stay capped, as example D and §12.2 require — CL-025(c)). Stop at `req.limit` (default 8, max 12).

### 6.8 Per-result fields

- `why_keys`: in this order — the §6.6 forced key (`why.crisis_line` / `why.report_scam`) → `why.for_this_paper` (pinned) → `why.institution_match` → `why.for_<primary>` if primary ∈ tags else `why.for_<first shared tag>` → geo key → `why.speaks_your_language` (if 1.0). Max 4. `why` = the English renderings. No card repeats a chip: a forced key replaces the tag key it duplicates (`why.report_scam` ≡ `why.for_scam_report`, `why.crisis_line` ≡ `why.for_crisis` — same copy in every pack), so the tag slot names the next shared tag if there is one; and any later key whose English rendering equals an earlier one is dropped before the cap of 4 (§15 item 14).
- `eligibility_note_key` = `r.status_note_key` (any value, including `hhs_funded_health`, which renders "You can ask for a free interpreter here.").
- `checklist` = `checklist.build(r, req.document_type)` (§4.8), ≤ 8 items, `ChecklistItem{key, text_en}`.

### 6.9 `national_fallbacks`

Ordered, de-duplicated against `results`:
1. `211` always;
2. `immlawhelp` if any request tag ∈ immigration group (§3.1);
3. `hrsa_fqhc` if any request tag ∈ health group;
4. `ftc_reportfraud` and `dhs_oig` if `scam_risk ≠ none`;
5. `988` if `emergency`.

**Offline client list (code-authoritative, CL-045(b)).** With no server there is no §6.6 forced ordering, so the app's `features/help/request.ts` `offlineFallbacksFor` deliberately orders the bundled subset differently: `988` (when `emergency` or tag `crisis`), `dv_hotline`, `trafficking`, `poison` for the request's matching tags first, then `ftc_reportfraud` + `dhs_oig` (when `scam_risk ≠ none` or tag `scam_report`), then `211`, `immlawhelp` (immigration group), `hrsa_fqhc` (health group), de-duplicated against ids already shown.

### 6.10 `notes_keys`

`notes.set_region_for_local_help` (state unknown) · `notes.county_unknown` (state known, no county/zip3, and ≥ 1 county-scoped candidate was eligible at 0.9) · `notes.no_local_results` (state known, zero non-national results) · `notes.lsc_restricted_explained` (any result has `lsc_restricted`) · `notes.resource_text_english_only` (`req.language ≠ en` and any result lacks `what_it_does[req.language]`) · `notes.verify_before_going` always. `disclaimer_kind = general_information`.

### 6.11 Worked examples (seed of §11, today = 2026-09-27)

**Code-authoritative (CL-025(c)).** These tables were computed by hand before the seed was loaded; on the loaded seed the §6.2–§6.10 formula differs in places and `tests/unit/test_matcher.py` asserts the formula: A and B also carry `notes.resource_text_english_only` (non-English request, §6.10); B scores `healthcare_gov` 4.38; C returns **7** results (`va_eviction_helpline`, `hud_counselor`, `va_courts_landlord_tenant`, `fairfax_sheriff_eviction`, `usa_housing_help`, `lawhelp`, `lajc` — the table scored three `es`-listing entries at language 0.8 and gave `nvfs` a tag it does not carry); D's `national_fallbacks` is `[211, immlawhelp]` because `immlawhelp` is not in the capped results. The API_CONTRACT §3.8 example follows the tables, not the formula.

**A. `API_CONTRACT` §3.8 request** — tags `[medical_bill, charity_care]`, `document_type=medical_bill`, VA / Fairfax / 220, language `fr`, institutions `["Inova Health System"]`, limit 4.

| id | tag | geo | lang | inst | prio | pin | score | why |
|---|---|---|---|---|---|---|---|---|
| `inova_fa` | 3.00 | 1.0 | 0.8 | 0.5 | 0.80 | 0 | **6.10** | Named on your paper (Inova) · For hospital and doctor bills · Serves Fairfax County |
| `dollarfor` | 3.00 | 0.5 | 0.8 | 0 | 0.75 | 0.5 | **5.55** | Made for this kind of paper · For hospital and doctor bills · Anywhere in the U.S. |
| `irs_501r` | 3.00 | 0.5 | 0.8 | 0 | 0.40 | 0 | **4.70** | For hospital and doctor bills · Anywhere in the U.S. |
| `cms_medical_bill_rights` | 1.67 | 0.5 | 1.0 | 0 | 0.65 | 0.5 | **4.32** | Made for this kind of paper · For hospital and doctor bills · Anywhere in the U.S. · Help in your language |
| `lajc` | 1.29 | 0.7 | 0.8 | 0 | 0.75 | 0 | 3.54 | (cut by limit) |

`national_fallbacks = [211, hrsa_fqhc]`; `notes_keys = [notes.verify_before_going]`. Checklist for `inova_fa`: its four keys + `bring_itemized_bill_request`, `bring_insurance_card` from `prepare.yaml[medical_bill]` (de-duplicated, ≤ 8).

**B. Medicaid letter, Dari, VA / 220, tags `[medicaid_renewal, benefits_navigation]`, `document_type=medicaid_renewal`, limit 3** → `medicaid_state` 5.65 (pinned; `hhs_funded_health` note), `healthcare_gov` 4.18, `insurekidsnow` 3.90; cut by `limit`: `fairfax_csp` 3.25 (county 1.0, Dari listed 1.0, but only one shared tag), `usa_benefit_finder` 2.80, `211` 2.23. This is the `resource_preview` the analyze pipeline attaches (`limit=3`).

**C. Eviction summons, Spanish, VA / Fairfax, tags `[eviction, housing_counseling]`, `document_type=eviction_summons`, limit 8**

| id | tag | geo | lang | prio | pin | boost | pen | score |
|---|---|---|---|---|---|---|---|---|
| `va_eviction_helpline` | 3.00 | 0.7 | 0.8 | 0.65 | 0.5 | 0.5 | −0.2 | **5.95** |
| `hud_counselor` | 2.33 | 0.5 | 1.0 | 0.75 | 0.5 | 0.5 | −0.1 | **5.48** |
| `va_courts_landlord_tenant` | 2.00 | 0.7 | 0.8 | 0.70 | 0.5 | 0.5 | 0 | **5.20** |
| `fairfax_sheriff_eviction` | 2.00 | 1.0 | 0.8 | 0.50 | 0 | 0.5 | 0 | **4.80** |
| `usa_housing_help` | 2.33 | 0.5 | 0.8 | 0.45 | 0 | 0.5 | 0 | **4.58** |
| `va_code_pay_or_quit` | 2.00 | 0.7 | 0.8 | 0.30 | 0 | 0.5 | 0 | 4.30 → **capped** (3rd `government`) |
| `lajc` | 1.29 | 0.7 | 1.0 | 0.75 | 0 | 0.5 | 0 | **4.24** |
| `lawhelp` | 1.40 | 0.5 | 0.8 | 0.60 | 0.5 | 0.5 | −0.2 | **4.10** (`lsc_restricted` note) |
| `lsc_find` | 1.50 | 0.5 | 0.8 | 0.55 | 0 | 0.5 | −0.2 | 3.65 → capped (3rd `directory`) |
| `nvfs` | 0.29 | 1.0 | 1.0 | 0.70 | 0 | 0 | 0 | **2.99** |

Results (8): helpline, hud_counselor, va_courts, sheriff, usa_housing_help, lajc, lawhelp, nvfs. `notes_keys` = `[notes.lsc_restricted_explained, notes.verify_before_going]`; `national_fallbacks = [211]`. The fixed `court_date_is_the_deadline` card comes from `fixed_notices.yaml` (D-20), and the same key appears in `warnings` on the two court-process entries.

**D. Scam letter, `scam_risk=likely`, tags `[scam_report, immigration_legal_help]`** → forced block first, ordered by score: `dhs_oig` (priority 95, hotline), `uscis_scams` (90), `ftc_reportfraud` (90, −0.1 js), `ftc_immigrant_scams` (85), `eoir_roster` (70; also `immigration_legal_help`), `uscis_find_legal` (60) … each with `why.report_scam` first; then `immlawhelp`. Diversity: the cap allows only two `government` scam pages, so `uscis_scams` and `ftc_reportfraud` stay and `ftc_immigrant_scams`/`irs_scams`/`ssa_scams` drop unless `limit` still has room after other org types. `national_fallbacks = [211]` (`immlawhelp`, `ftc_reportfraud`, `dhs_oig` already in results are skipped).

**E. Emergency lexicon hit (`emergency=true`) with tags `[medical_bill]`** → `988`, `poison`, `dv_hotline`, `trafficking` first (crisis group), then bill resources; `national_fallbacks` gains `988` only if it was cut by `limit`.

### 6.12 Non-goals

No fuzzy geo (no "nearby counties"), no distance, no opening-hours logic, no personalization, no model calls, no immigration-status filter of any kind (D-24).

---

## 7. Where the DB is used (API surfaces and other modules)

| Consumer | What it reads | Rule |
|---|---|---|
| `POST /v1/resources/match` (`routers/resources.py`) | `matcher.match()` | §6; 200 always (empty `results` is fine); validation errors → `400 invalid_request` (unknown tag is a Pydantic enum error). |
| `GET /v1/resources` | `repo.list(tag, state, language, q, limit, offset)` | Filters: `tag` exact; `state` keeps national entries **plus** entries whose `serves.states` contains it; `language` keeps entries listing it or `interpreters_200+`; `q` case-insensitive substring of `name`/`name_note`/`id`. Sort `priority` desc, then `name`. `total` counts before paging. `broken` entries are never listed. |
| `GET /v1/resources/{id}` | `repo.get(id)` | `404 not_found` for unknown or `broken`. |
| `analysis/pipeline.py` → `resource_preview` | `matcher.match(limit=3)` with the analysis' `resource_tags`, `document_type`, `category`, `state`, `zip3`, `institutions_as_written`, `scam_risk`, `emergency` | Only when `state` was supplied (`API_CONTRACT` §3.5); otherwise `[]`. |
| `analysis/contacts_filter.py` (D-10) | `repo.org_names()` = normalized set of `name` + `name_note` + `alt` names in `x_meta.aliases` | Organization names in model text are kept only if in the transcript **or** in this set. |
| `analysis/urgency.py` (D-12) | `well_known_ids.verify_court_date` / `verify_uscis_date` | `Urgency.verify_resource_id`. |
| `analysis/scam.py` (D-13) | `well_known_ids.scam_card_phone` / `scam_card_url` | Fixed card text + `dhs_oig.phone` + `ftc_reportfraud.url`. |
| `analysis/clerk.py` (D-18) | `repo.is_hhs_funded(resource_id)` (§3.3) | Interpreter line only when true. |
| `quicksheet/render.py` (§3.11 of the contract) | `repo.get(id)`, `repo.phone_index()` | `QuickSheetResource{name, phone, url}` is accepted only if `name`/`url` match an entry **and** `phone` equals that entry's `phone`/`tty` (or is null); anything else is dropped silently and counted in the log field `quicksheet_resources_dropped`. The client therefore sends the entry's own `name`/`phone`/`url` verbatim. |
| `GET /health` | `repo.count()` | `resources_loaded` (101 with this seed). |
| `GET /v1/config` | `meta.resource_db_version` | |
| `scripts/sync_to_mobile.py` (WP7) | `well_known_ids.offline_subset` | Writes `apps/mobile/assets/resources/national_fallbacks.json` = `list[Resource]` for those ids (English-only `what_it_does`), used by the Help tab offline (ARCHITECTURE §3.1 "Offline behaviors"). |
| Feedback `resource_problem` (D-31) | none | Counted by `resource_id`; WP3 reviews counts during the 90-day re-verification. |

### 7.1 Translating `what_it_does` / `eligibility_plain`

v1 ships **English only** in the YAML. `scripts/gen_resource_i18n.py` (WP3, run by one agent with keys, `MODEL_FAST`, `thinking_level=minimal`, 60 strings per call using `LanguagePackModelOut`-style `list[KeyValue]`) generates the Tier 1+2 languages into a sidecar `data/resources/i18n/<tag>.yaml` (`{resource_id: {what_it_does, eligibility_plain}}`), QA'd like packs (no digits changed, no URLs/phones introduced, length ratio ≤ 1.8). The loader merges sidecars into the dicts at boot. Until generated, the client shows English and the matcher emits `notes.resource_text_english_only`. Never generated at request time.

---

## 8. Loader / validator (`resources/loader.py`)

### 8.1 Boot sequence

```
load(data_dir, today) -> ResourceRepo
  1. meta = load_meta(data_dir/_meta.yaml)             # schema below; fail on any missing section
  2. for path in sorted(glob("**/*.yaml") excluding "_*.yaml"):
       doc = yaml.safe_load(path)   (+ yaml.compose() once to map entry index → start line for messages)
       assert doc is a list
       for i, raw in enumerate(doc):
          x_meta = raw.pop("x_meta", None)
          raw = _apply_defaults(raw)
          try: res = Resource.model_validate(raw)       # extra="forbid"
          except ValidationError as e: die(f"{path}:{line(i)}: {e}")   # boot refusal
          _extra_checks(res, path, line)                 # 8.2
          repo.add(res, x_meta)
  3. _cross_checks(repo, meta)                            # 8.3
  4. repo.freeze(); log resources_loaded, per-file counts, stale_count
```

Failure = process exit with the path and line printed (ARCHITECTURE §2: "refuses to boot on invalid file"). Freshness problems are **warnings** at boot (they must not take the API down on day 121) and **failures** in CI via `scripts/check_links.py --freshness` (§9).

### 8.2 Per-entry checks (beyond Pydantic types)

1. `id` regex; duplicates across files → fail.
2. `url`/`alt_urls` scheme and no `utm_`/fragment; `url ∉ alt_urls`.
3. `phone`/`tty` regex; `text_line` ≤ 60.
4. `languages` regex; `en` need not be present (a Spanish-only line is legitimate).
5. `serves` scope consistency table (§5); states in the allowed set; counties canonical (no trailing " County"; apostrophes normalized to `'`); zip3 regex; `national` ⇒ all lists empty.
6. `tags` ⊆ `ResourceTag`; `len(tags) ≤ 8`; `tags == []` only if the id appears in `meta.doc_type_pins`.
7. `never_show_with_tags ∩ tags == ∅`.
8. `prepare_checklist_keys ⊆ meta.checklist`; `warnings ⊆ meta.warning_keys` (checked on the unprefixed YAML values, before `_apply_defaults()` adds the `warn.` prefix).
9. `status_note_key ∈ StatusNoteKey`.
10. `what_it_does.en`, `eligibility_plain.en` present, 1–300 chars, grade ≤ 5 by the same `textstat`-free heuristic the readability CI uses (`scripts/readability.py` — WP2/WP8), and clean against `data/safety/phrasing.yaml` (the DB may not say "you qualify").
11. `verified_on` in `[2026-01-01, today]`; `priority` 0–100.
12. `link_health == broken` → entry loaded as **inactive** (excluded from matching and listing) with a boot warning; the weekly link job files the issue.
13. `verification_method == manual_verify` ⇒ `status_note_key == manual_verify` (so the UI shows the caution), and vice-versa when the only unverified fact is the phone (`phone` must then be `null`).
14. If `x_meta` present: `source` non-empty; `expect_text` list of strings.

### 8.3 Cross-entry checks

1. Every `ResourceTag` has ≥ 1 active entry. `traffic_court` and `prescription_help` are allow-listed in `meta.fallback_only_tags` because only broad entries carry them today (`lawhelp`; `hrsa_fqhc`/`neighborhood_health`) — if those entries are ever retired the boot logs a warning instead of failing, and §14 lists the dedicated resources still to be admitted.
2. Every id in `meta.doc_type_pins`, `meta.well_known_ids`, `meta.urgent_doc_boost` exists and is active; every pin key is a `DocumentType`; every boost tag is a `ResourceTag`.
3. `meta.checklist` keys are `^[a-z0-9_]+$`; `meta.why` contains `why.for_<tag>` for all 49 tags.
4. `repo.org_names()` is non-empty and contains no phone-like digit runs.
5. Stale entries (`today − verified_on > 120 d`) → warning list; `> 365 d` → excluded from matching and from `national_fallbacks` (still browsable) with a warning.
6. Checks 1–2 run against **non-broken** entries: a tag or `_meta.yaml` reference carried only by entries `> 365 d` old is a boot **warning**, not a refusal (freshness never takes the API down, §8.1); a `broken` sole carrier still refuses boot (CL-025(b)).

### 8.4 `ResourceRepo` API (used by the consumers in §7)

`get(id) -> Resource | None` · `active() -> list[Resource]` · `count() -> int` · `list(tag, state, language, q, limit, offset) -> (items, total)` · `org_names() -> frozenset[str]` · `phone_index() -> dict[str, str]` (E.164/N11 → id) · `is_hhs_funded(id) -> bool` · `well_known(name) -> str | list[str]` · `version -> str`. All read-only after `freeze()`; the repo is a process singleton created in `main.create_app()` and injected via `deps.py`.

### 8.5 `_meta.yaml` schema

```yaml
resource_db_version: "2026-09-27"
fallback_only_tags: [traffic_court, prescription_help]
language_families: [[zh, zh-Hans, zh-Hant, yue], [pt, pt-BR], [prs, fa]]
state_names: {AL: Alabama, ..., DC: District of Columbia, PR: Puerto Rico, ...}   # 56 rows
checklist: {bring_notice: "This letter or notice", ...}                            # §4.4
why: {why.for_immigration_legal_help: "For immigration legal help", ..., why.institution_match: "Named on your paper ({institution})", ...}   # §3.1 + §4.2
notes: {notes.set_region_for_local_help: "...", ...}                               # §4.3
warning_keys: [jury_never_check_citizen, ...]                                       # §4.3 (keys only; copy lives in the pack)
doc_type_pins: {...}                                                                # §4.5
urgent_doc_boost: {...}                                                             # §4.6
well_known_ids: {...}                                                               # §4.7
```

---

## 9. Link-health checker (`scripts/check_links.py`, weekly CI + on demand)

```
usage: check_links.py [--write] [--freshness] [--only <id>] [--json report.json]
```

Behaviour:
1. Loads the repo exactly like the server (so a broken YAML fails here first).
2. For every `url` and `alt_urls` item: `httpx` GET with a real browser User-Agent (Chrome on Windows), `Accept-Language: en-US`, timeout 20 s, ≤ 5 redirects **within the same registrable domain**; a cross-domain redirect is reported as `redirected_offsite` for human review (not auto-followed, not auto-written).
3. Classification → proposed `link_health`: `200` with ≥ 500 chars of visible text → `ok`; `200` with a body that contains `<noscript>`/`id="root"`/`ng-app` and < 500 chars of text → `js_rendered`; `401/403` → `unknown_403`; Cloudflare/Akamai challenge markers (`cf-chl`, `_Incapsula_`, `Just a moment`) → `unverified`; `404/410`, DNS failure, TLS failure → `broken`; `5xx`/timeout → `transient` (retried once next run; never written).
4. `x_meta.expect_text[]`: each phrase is searched in the visible text (digits compared after stripping punctuation); a miss on an `ok` page → `content_drift` finding (the phone/hours may have changed) — an issue, not a status change.
5. `--write` updates **only** `link_health` (never `verified_on`, never `phone`) and rewrites the file preserving key order and comments (uses `ruamel`-free approach: regex-replace the single `link_health:` line inside the entry block identified by `- id:`).
6. `--freshness` exits non-zero if any active entry has `verified_on` older than 120 days (`manual_verify` entries: 90 days), printing the ids grouped by file — this is the quarterly re-verification trigger (RUNBOOK task; DECISIONS Q5 asks who owns it).
7. Output: table on stdout + `--json` report `{checked, ok, unknown_403, js_rendered, unverified, broken, redirected_offsite, content_drift, stale}`; CI opens one issue per `broken`/`redirected_offsite`/`content_drift` id (WP8 workflow "links").

Manual re-verification protocol (human, every 90 days per region and for every `unknown_403`/`js_rendered` entry): open `url` in a browser, confirm `what_it_does`, `phone`, `hours`, `languages`, `eligibility_plain`; set `verified_on` to today, `verification_method: browser`, update `x_meta.source` with the date, bump `resource_db_version`.

---

## 10. Tests (WP3 definition of done)

`tests/unit/test_loader.py`
- loads the real `data/resources` → `count() == 101`, zero errors, stale list empty as of the seed date;
- invalid fixtures under `tests/fixtures/resources_bad/` each fail with path:line — duplicate id, bad tag, county with " County", national with states, phone `800-375-5283`, missing `en`, `tags: []` without a pin, unknown checklist key, `url` with `utm_`, `manual_verify` without the status note;
- `_apply_defaults` produces a valid `Resource` from the minimal compact form;
- `test_meta_keys_in_en_json` (xfail until WP0 adds the keys).

`tests/unit/test_matcher.py`
- examples A–E of §6.11 assert **order** and `why_keys`, `national_fallbacks`, `notes_keys`;
- state unknown → only national + `notes.set_region_for_local_help`;
- county mismatch excludes Inova; zip3 `220` alone matches Inova at 1.0; state-only matches at 0.9 with `why.check_service_area`;
- `never_show_with_tags` (AILA never with `scam_report`);
- `lsc_restricted` shown with penalty and note, never hidden;
- diversity cap ≤ 2 per `org_type`; forced entries exempt;
- `emergency=true` puts `988` first even with unrelated tags; `scam_risk=likely` puts `dhs_oig` first;
- determinism: shuffled repo order → identical output;
- language `zh-Hant` vs entry `zh-Hans` → 0.9; `prs` vs `fa` → 0.9; `ar` vs `[en]` → 0.8.

`tests/unit/test_checklist.py` — merge order, de-dup, cap 8, unknown doc type → resource keys only.

`tests/contract/test_resources.py` — `POST /v1/resources/match` with the §3.8 example body returns `inova_fa` first; `GET /v1/resources?tag=jury_summons` returns `uscourts_jury`; `GET /v1/resources/nope` → 404 envelope; `GET /v1/resources?state=VA&q=inova` → 1 item.

`tests/unit/test_quicksheet.py` (shared with the PDF renderer) — a `QuickSheetResource` with a phone that is not the entry's phone is dropped.

`scripts/smoke.py` asserts no `"[contact removed"` in `resource_preview` and that every fixture's `resource_preview` is non-empty when `state=VA`.

---

## 11. Seed data (paste-ready)

Conventions: entries use YAML flow style to stay compact; the block form of §2.3 is equivalent. URLs are quoted (flow-style safety). Omitted optional fields take the defaults of §2.1. `verified_on: 2026-09-27` = content re-read by fetch today; `2026-09-23` = research browser pass (site blocks fetchers or is a JS shell). Phone numbers appear **only** when they were read on the entry's own page today or in the cited research row that fetched them.

### 11.1 `data/resources/_meta.yaml`

```yaml
resource_db_version: "2026-09-27"
fallback_only_tags: [traffic_court, prescription_help]
language_families: [[zh, zh-Hans, zh-Hant, yue], [pt, pt-BR], [prs, fa]]
state_names: {AL: Alabama, AK: Alaska, AZ: Arizona, AR: Arkansas, CA: California, CO: Colorado, CT: Connecticut, DE: Delaware, DC: District of Columbia, FL: Florida, GA: Georgia, HI: Hawaii, ID: Idaho, IL: Illinois, IN: Indiana, IA: Iowa, KS: Kansas, KY: Kentucky, LA: Louisiana, ME: Maine, MD: Maryland, MA: Massachusetts, MI: Michigan, MN: Minnesota, MS: Mississippi, MO: Missouri, MT: Montana, NE: Nebraska, NV: Nevada, NH: New Hampshire, NJ: New Jersey, NM: New Mexico, NY: New York, NC: North Carolina, ND: North Dakota, OH: Ohio, OK: Oklahoma, OR: Oregon, PA: Pennsylvania, RI: Rhode Island, SC: South Carolina, SD: South Dakota, TN: Tennessee, TX: Texas, UT: Utah, VT: Vermont, VA: Virginia, WA: Washington, WV: West Virginia, WI: Wisconsin, WY: Wyoming, PR: Puerto Rico, GU: Guam, VI: U.S. Virgin Islands, AS: American Samoa, MP: Northern Mariana Islands}
checklist:
  bring_notice: "This letter or notice"
  bring_case_number: "Your case number (printed on the letter)"
  bring_receipt_number: "Your receipt number (3 letters, then 10 digits)"
  bring_a_number: "Your A-number (Alien Registration Number, 8 or 9 digits)"
  bring_hearing_notice: "Your hearing notice"
  bring_subject_id: "The Subject ID and place of birth printed on your ICE paperwork"
  bring_photo_id: "A photo ID (passport, driver's license, or Green Card)"
  bring_household_ids: "ID for everyone in your household"
  bring_proof_income: "Proof of income (pay stubs or last tax return)"
  bring_pay_stubs: "Your pay stubs"
  bring_tax_return: "Your last tax return, if you have one"
  bring_proof_address: "Proof of where you live (a bill or lease with your name)"
  bring_proof_va_address: "Proof of your Virginia address"
  bring_proof_rent_utilities: "Your rent, power, gas and water bills"
  bring_the_bill: "The bill or account number"
  bring_itemized_bill_request: "Ask for an itemized bill"
  bring_insurance_card: "Your insurance card, if you have one"
  bring_denial_letter: "The denial letter"
  bring_the_summons: "The summons or court paper"
  bring_lease: "Your lease"
  bring_shutoff_notice: "The shutoff notice"
  bring_hours_log: "A list of the days and hours you worked"
  bring_employer_info: "Your employer's name, address, and phone"
  bring_school_records: "Your child's school papers (report cards, test results)"
  bring_vaccine_record: "Your child's vaccine record, if you have it"
  bring_passport_or_two_ids: "Your passport, or two other ID documents"
  bring_name_of_helper: "The full name of the person or office you want to check"
  bring_proof_income_or_benefit_card: "Proof of income, or your Medicaid, SNAP or TANF card"
  bring_the_child: "Bring the child"
  bring_medication_list: "All your medicine bottles or a list of them"
why:
  why.for_immigration_legal_help: "For immigration legal help"
  why.for_removal_proceedings: "For immigration court cases"
  why.for_asylum: "For asylum cases"
  why.for_daca_tps: "For DACA and TPS"
  why.for_work_permit: "For work permits"
  why.for_green_card: "For Green Card questions"
  why.for_naturalization: "For citizenship forms"
  why.for_change_of_address: "For reporting a move"
  why.for_fee_waiver: "For fee questions"
  why.for_afghan_specific: "For Afghan newcomers"
  why.for_refugee_services: "For refugee services"
  why.for_court_notice: "For court dates and notices"
  why.for_jury_summons: "For jury summons questions"
  why.for_traffic_court: "For court notices"
  why.for_medical_bill: "For hospital and doctor bills"
  why.for_charity_care: "For free or reduced-cost hospital care"
  why.for_insurance_denial: "For insurance denials and appeals"
  why.for_medicare_appeal: "For Medicare appeals"
  why.for_medicaid_renewal: "For Medicaid letters"
  why.for_prescription_help: "For prescriptions"
  why.for_primary_care_uninsured: "For low-cost clinics"
  why.for_lab_results: "For questions about lab results"
  why.for_vaccine_records: "For vaccine records"
  why.for_language_access: "For interpreter rights"
  why.for_food: "For food help"
  why.for_wic: "For WIC"
  why.for_school_meals: "For school meals"
  why.for_snap: "For SNAP (food stamps)"
  why.for_ssa_benefits: "For Social Security letters"
  why.for_benefits_navigation: "For help finding benefits"
  why.for_housing_counseling: "For housing counseling"
  why.for_eviction: "For eviction notices"
  why.for_rent_assistance: "For rent help"
  why.for_utility_shutoff: "For power, gas or water shutoff notices"
  why.for_section8: "For Section 8 and housing vouchers"
  why.for_school_enrollment: "For school enrollment"
  why.for_special_education: "For IEP and 504 plans"
  why.for_homeless_students: "For students without stable housing"
  why.for_workers_rights: "For workplace problems"
  why.for_wage_theft: "For unpaid wages"
  why.for_discrimination: "For discrimination at work"
  why.for_workplace_safety: "For unsafe work conditions"
  why.for_tax_notice: "For IRS letters"
  why.for_itin: "For ITIN questions"
  why.for_scam_report: "To report a scam"
  why.for_crisis: "Help right now"
  why.for_domestic_violence: "For domestic violence"
  why.for_trafficking: "For human trafficking"
  why.for_poison: "For poison emergencies"
  why.institution_match: "Named on your paper ({institution})"
  why.serves_your_county: "Serves {county}"
  why.serves_your_area: "Serves your area"
  why.serves_your_state: "Serves {state}"
  why.check_service_area: "Check that they serve your area"
  why.anywhere_in_us: "Anywhere in the U.S."
  why.speaks_your_language: "Help in your language"
  why.for_this_paper: "Made for this kind of paper"
  why.report_scam: "To report a scam"
  why.crisis_line: "Help right now"
notes:
  notes.set_region_for_local_help: "Set your state in Settings to see help near you."
  notes.county_unknown: "Add the first 3 digits of your ZIP code in Settings. Then you will see more local help."
  notes.no_local_results: "We do not have local listings for your area yet. These national services help anyone."
  notes.lsc_restricted_explained: "Some legal aid offices can only help people with certain immigration papers."
  notes.resource_text_english_only: "Some listing details are in English."
  notes.verify_before_going: "Hours and phone numbers change. Call before you go."
warning_keys: [jury_never_check_citizen, jury_never_register_to_vote, ask_for_plain_language_summary, address_change_multi_agency, usps_does_not_forward_uscis, ead_receipt_not_work_authorization, tps_dates_from_federal_register, forms_are_free, asylum_rules_aug_2026, no_fee_waiver_hr1, verify_local_office_open, hr1_coverage_changes, staff_reference, schools_may_not_ask_status, eeoc_deadline_180_300, osha_retaliation_30d, court_date_is_the_deadline, not_a_court_order, law_changes_2027, lsc_eviction_db_2021, medicare_windows_changed]
doc_type_pins:            # §4.5 verbatim
  uscis_receipt: [uscis_i797_types, uscis_contact]
  uscis_rfe: [uscis_i797_types, uscis_contact, immlawhelp]
  uscis_noid: [immlawhelp, eoir_roster]
  uscis_biometrics: [uscis_biometrics_page, uscis_contact]
  uscis_interview: [uscis_contact]
  uscis_approval: [uscis_i797_types]
  uscis_denial: [immlawhelp, eoir_probono]
  nta: [eoir_hotline, eoir_acis, eoir_probono, eoir_icor]
  hearing_notice: [eoir_hotline, eoir_acis, eoir_court_finder]
  ij_decision: [eoir_probono, eoir_forms, eoir_hotline]
  bia_notice: [eoir_hotline, eoir_probono]
  ice_checkin: [ice_checkin]
  ead_related: [uscis_i765, uscis_contact]
  green_card_related: [uscis_replace_green_card, uscis_contact]
  tps_related: [uscis_tps]
  asylum_fee_notice: [asap, uscis_hr1_fees]
  parole_related: [uscis_contact, uscis_afghan]
  medical_bill: [cms_medical_bill_rights, dollarfor]
  eob: [healthcare_appeals]
  insurance_denial: [healthcare_appeals]
  prior_auth: [healthcare_appeals]
  lab_result: [medlineplus_labs]
  prescription_label: [hhs_ocr_lep, hrsa_fqhc]
  discharge_instructions: [hhs_ocr_lep]
  vaccine_record: [cdc_iis]
  appointment_reminder: []
  medicaid_renewal: [medicaid_state]
  snap_notice: [snap_state]
  wic_notice: [signupwic]
  ssa_letter: [ssa_appeals, ssa_scams]
  pay_or_quit: [hud_counselor, va_code_pay_or_quit, va_courts_landlord_tenant]
  eviction_summons: [va_courts_landlord_tenant, va_eviction_helpline, lawhelp, hud_counselor]
  lease: [hud_counselor]
  rent_increase: [hud_counselor]
  section8_recert: [hud_pha]
  utility_shutoff: [liheap, "211"]
  school_enrollment: [plyler_explainer, nche_mckinney_vento]
  immunization_notice: [school_vaccine_requirements, cdc_iis]
  iep_504_notice: [pti_centers]
  school_meals: [school_meals]
  report_card: []
  w2_1099: []
  i9: [uscis_i765]
  offer_letter: [ftc_job_scams]
  pay_stub: [dol_whd]
  irs_notice: [irs_notice_lookup, irs_scams]
  itin: [irs_itin]
  jury_summons: [uscourts_jury]
  traffic_court: [immlawhelp, lawhelp]
  other_notice: []
  unknown: []
urgent_doc_boost:         # §4.6 verbatim
  nta: [court_notice, removal_proceedings]
  hearing_notice: [court_notice, removal_proceedings]
  uscis_noid: [immigration_legal_help]
  eviction_summons: [eviction]
  pay_or_quit: [eviction, rent_assistance]
  utility_shutoff: [utility_shutoff]
  asylum_fee_notice: [asylum]
  ice_checkin: [removal_proceedings]
well_known_ids:           # §4.7 verbatim
  fallback_always: ["211"]
  fallback_immigration: [immlawhelp]
  fallback_health: [hrsa_fqhc]
  fallback_scam: [ftc_reportfraud, dhs_oig]
  fallback_emergency: ["988", dv_hotline, poison]
  lsc_alternative: [immlawhelp, eoir_probono]
  verify_court_date: eoir_hotline
  verify_uscis_date: uscis_contact
  scam_card_phone: dhs_oig
  scam_card_url: ftc_reportfraud
  emergency_card: ["988", poison, dv_hotline]
  offline_subset: ["211", "988", dv_hotline, poison, trafficking, immlawhelp, eoir_probono, hrsa_fqhc, dhs_oig, ftc_reportfraud, eoir_hotline, uscis_contact, lawhelp, feeding_america, liheap, hud_counselor]
```

### 11.2 `data/resources/national_immigration.yaml` (42 entries)

```yaml
# Free/low-cost immigration legal help, verification of representatives, USCIS/EOIR/ICE official pages,
# asylum, Afghan and refugee services, anti-fraud reporting (USCIS, FTC, DHS OIG), Title VI.
- {id: immlawhelp, name: "ImmigrationLawHelp.org", org_type: directory, cost: free, priority: 90,
   name_note: "a Justicia Lab project, powered by probono.net (formerly Immigration Advocates Network)",
   url: "https://www.immigrationlawhelp.org/", languages: [en, es, ar, my, zh, fa, fr, ht, hmn, km, ko, ru, vi],
   serves: {scope: national}, tags: [immigration_legal_help, asylum, daca_tps, removal_proceedings, work_permit, green_card],
   what_it_does: {en: "Finds free or low-cost nonprofit immigration legal help near you. Search by state, county, ZIP code or detention center, and by case type."},
   eligibility_plain: {en: "Low-income immigrants. Each office sets its own rules."},
   prepare_checklist_keys: [bring_notice, bring_a_number, bring_proof_income],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1A; fetched 2026-09-27 (13 languages listed)", expect_text: ["Justicia Lab"]}}
- {id: eoir_probono, name: "EOIR List of Pro Bono Legal Service Providers", org_type: directory, cost: free, priority: 85,
   url: "https://www.justice.gov/eoir/list-pro-bono-legal-service-providers", languages: [en],
   serves: {scope: national}, tags: [removal_proceedings, court_notice, immigration_legal_help], status_note_key: not_endorsed,
   what_it_does: {en: "The government's list of lawyers and groups that take free immigration court cases, organized by court. Updated every January, April, July and October."},
   eligibility_plain: {en: "People with a case in immigration court. Some providers only help people who are detained."},
   prepare_checklist_keys: [bring_hearing_notice, bring_a_number],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1A; fetched 2026-09-27 (quarterly schedule + 'does not endorse' confirmed)", expect_text: ["does not endorse"]}}
- {id: eoir_roster, name: "DOJ Recognized Organizations and Accredited Representatives", org_type: directory, cost: free, priority: 70,
   url: "https://www.justice.gov/eoir/recognition-accreditation-roster-reports", languages: [en],
   serves: {scope: national}, tags: [immigration_legal_help, scam_report],
   what_it_does: {en: "Official lists that show whether a non-lawyer or an organization is allowed to help with immigration cases. Use it to check a helper before you pay."},
   eligibility_plain: {en: "Anyone checking a provider."},
   prepare_checklist_keys: [bring_name_of_helper],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1A; fetched 2026-09-27", expect_text: ["Accredited Representatives"]}}
- {id: uscis_find_legal, name: "USCIS: Find Legal Services", org_type: government, cost: free, priority: 60,
   url: "https://www.uscis.gov/scams-fraud-and-misconduct/avoid-scams/find-legal-services", languages: [en, es],
   serves: {scope: national}, tags: [immigration_legal_help, scam_report],
   what_it_does: {en: "Explains who is allowed to represent you: a licensed attorney, a DOJ-accredited representative, or a supervised law student. A notario is not a lawyer."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1A; fetched 2026-09-27", expect_text: ["accredited representative"]}}
- {id: aila, name: "AILA Immigration Lawyer Search", org_type: private_directory, cost: paid, priority: 25,
   url: "https://www.ailalawyer.com/", languages: [en],
   serves: {scope: national}, tags: [immigration_legal_help], never_show_with_tags: [scam_report],
   what_it_does: {en: "A directory of private immigration lawyers. Lawyers here charge fees. You can filter by the language the lawyer speaks."},
   eligibility_plain: {en: "Anyone who can pay a lawyer. Ask about the fee before you start."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1A; fetched 2026-09-27 (100+ language filters)", notes: "Never surfaced with scam_report; paid directory."}}
- {id: uscis_contact, name: "USCIS Contact Center", org_type: government, cost: free, priority: 75,
   url: "https://www.uscis.gov/contactcenter", phone: "+18003755283", tty: "+18007671833", hours: "Mon–Fri 8:00–20:00 Eastern", languages: [en, es],
   serves: {scope: national}, tags: [work_permit, green_card, naturalization, daca_tps, fee_waiver],
   what_it_does: {en: "The official phone line for questions about a USCIS case or notice, and for checking a case with your receipt number."},
   eligibility_plain: {en: "Anyone with a USCIS case or notice."},
   prepare_checklist_keys: [bring_receipt_number, bring_notice],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1A; fetched 2026-09-27 (phone, TTY, hours confirmed)", expect_text: ["800-375-5283", "800-767-1833"]}}
- {id: eoir_icor, name: "EOIR Immigration Court Online Resource", org_type: government, cost: free, priority: 55,
   url: "https://www.justice.gov/eoir/immigration-court-online-resource", languages: [en],
   serves: {scope: national}, tags: [removal_proceedings, court_notice],
   what_it_does: {en: "Plain-language guides from the immigration courts about hearings, notices and finding a representative."},
   eligibility_plain: {en: "Anyone with an immigration court case."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1A; fetched 2026-09-27"}}
- {id: eoir_acis, name: "EOIR Automated Case Information (online)", org_type: government, cost: free, priority: 80,
   url: "https://acis.eoir.justice.gov/en/", languages: [en, es],
   serves: {scope: national}, tags: [court_notice, removal_proceedings],
   what_it_does: {en: "Enter your A-number to see your next immigration court date, time and court, and any decision."},
   eligibility_plain: {en: "Anyone with an immigration court case."},
   prepare_checklist_keys: [bring_a_number],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1A; fetched 2026-09-27 (A-number entry; English/Español)", expect_text: ["A-Number"]}}
- {id: eoir_hotline, name: "EOIR Automated Case Information Hotline", org_type: hotline, cost: free, priority: 85,
   url: "https://www.justice.gov/eoir/customer-service-initiatives", phone: "+18008987180", hours: "24/7", languages: [en, es],
   serves: {scope: national}, tags: [court_notice, removal_proceedings],
   what_it_does: {en: "Call and enter your A-number to hear your next court date, the judge's decision, and appeal due dates. Works day and night."},
   eligibility_plain: {en: "Anyone with an immigration court case. If your A-number has 8 digits, add a 0 in front."},
   prepare_checklist_keys: [bring_a_number],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1A; fetched 2026-09-27 (1-800-898-7180, 24/7, EN/ES confirmed)", expect_text: ["1-800-898-7180"]}}
- {id: eoir_court_finder, name: "EOIR: Find an Immigration Court and Internet-Based Hearings", org_type: government, cost: free, priority: 60,
   url: "https://www.justice.gov/eoir/find-immigration-court-and-access-internet-based-hearings", languages: [en],
   serves: {scope: national}, tags: [court_notice, removal_proceedings],
   what_it_does: {en: "Addresses of every immigration court and the links for online (WebEx) hearings."},
   eligibility_plain: {en: "Anyone with a hearing notice."},
   prepare_checklist_keys: [bring_hearing_notice],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1A; fetched 2026-09-27"}}
- {id: eoir_forms, name: "EOIR Forms (EOIR-33 address change, EOIR-26 appeal, EOIR-26A fee waiver)", org_type: government, cost: free, priority: 65,
   url: "https://www.justice.gov/eoir/eoir-forms", languages: [en],
   serves: {scope: national}, tags: [change_of_address, fee_waiver, court_notice, removal_proceedings], warnings: [address_change_multi_agency],
   what_it_does: {en: "Official immigration court forms: change of address (EOIR-33), appeal (EOIR-26) and appeal fee waiver (EOIR-26A). Some forms come in several languages."},
   eligibility_plain: {en: "Anyone with an immigration court or BIA case."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1A; fetched 2026-09-27", expect_text: ["EOIR-33", "EOIR-26"]}}
- {id: uscis_address, name: "USCIS: How to Change Your Address", org_type: government, cost: free, priority: 85,
   url: "https://www.uscis.gov/addresschange", languages: [en, es],
   serves: {scope: national}, tags: [change_of_address], warnings: [usps_does_not_forward_uscis, address_change_multi_agency],
   what_it_does: {en: "How to tell USCIS you moved. Most people must report a move within 10 days, online or with Form AR-11."},
   eligibility_plain: {en: "Anyone who is not a U.S. citizen and moves."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §3A; fetched 2026-09-27 ('within 10 days', 'USPS will not forward' confirmed)", expect_text: ["10 days"]}}
- {id: uscis_i765, name: "USCIS Form I-765 (work permit)", org_type: government, cost: free, priority: 60,
   url: "https://www.uscis.gov/i-765", alt_urls: ["https://www.uscis.gov/newsroom/news-releases/dhs-ends-automatic-extension-of-employment-authorization"], languages: [en, es],
   serves: {scope: national}, tags: [work_permit], warnings: [ead_receipt_not_work_authorization],
   what_it_does: {en: "The official work permit form page. A renewal can be filed up to 180 days before the card expires. Since October 30, 2025 renewals no longer get an automatic extension."},
   eligibility_plain: {en: "People who have or need an Employment Authorization Document."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §3B; both URLs fetched 2026-09-27", expect_text: ["180 days"]}}
- {id: uscis_replace_green_card, name: "USCIS: Replace Your Green Card (Form I-90)", org_type: government, cost: free, priority: 55,
   url: "https://www.uscis.gov/green-card/after-we-grant-your-green-card/replace-your-green-card",
   alt_urls: ["https://www.uscis.gov/green-card/after-we-grant-your-green-card", "https://www.uscis.gov/i-90"], languages: [en, es],
   serves: {scope: national}, tags: [green_card],
   what_it_does: {en: "When and how to replace or renew a Green Card. The I-90 receipt extends an expiring card for 36 months. A 2-year conditional card cannot be renewed; a different petition is needed 90 days before it expires."},
   eligibility_plain: {en: "Permanent residents."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §3B; three URLs fetched 2026-09-27", expect_text: ["36 months"]}}
- {id: uscis_tps, name: "USCIS Temporary Protected Status", org_type: government, cost: free, priority: 65,
   url: "https://www.uscis.gov/humanitarian/temporary-protected-status", languages: [en, es],
   serves: {scope: national}, tags: [daca_tps], warnings: [tps_dates_from_federal_register],
   what_it_does: {en: "Official TPS page with each country's status and re-registration dates. Dates change; always check the country page."},
   eligibility_plain: {en: "People with or applying for TPS."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §3B; fetched 2026-09-27 (lists 5 designated countries today)"}}
- {id: ice_checkin, name: "ICE Check-In (schedule online)", org_type: government, cost: free, priority: 60,
   url: "https://www.ice.gov/check-in", alt_urls: ["https://www.ice.gov/ero"], languages: [en, es],
   serves: {scope: national}, tags: [removal_proceedings],
   what_it_does: {en: "Schedule or confirm an ICE check-in appointment online with the Subject ID and place of birth printed on your paperwork."},
   eligibility_plain: {en: "People told to report to ICE."},
   prepare_checklist_keys: [bring_notice, bring_subject_id, bring_photo_id],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §3B; fetched 2026-09-27", expect_text: ["Subject ID"]}}
- {id: uscis_naturalization, name: "USCIS: The Naturalization Interview and Test", org_type: government, cost: free, priority: 50,
   url: "https://www.uscis.gov/citizenship/learn-about-citizenship/the-naturalization-interview-and-test", alt_urls: ["https://www.uscis.gov/n-400"], languages: [en, es],
   serves: {scope: national}, tags: [naturalization],
   what_it_does: {en: "What happens at the citizenship interview and test, and which test you take depending on when you filed Form N-400."},
   eligibility_plain: {en: "People who filed or plan to file for citizenship."},
   prepare_checklist_keys: [bring_notice, bring_photo_id],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §3A; both URLs fetched 2026-09-27"}}
- {id: uscis_i797_types, name: "USCIS: Form I-797 Types and Functions", org_type: government, cost: free, priority: 45,
   url: "https://www.uscis.gov/forms/filing-guidance/form-i-797-types-and-functions", languages: [en],
   serves: {scope: national}, tags: [],
   what_it_does: {en: "Explains the different USCIS notices: receipt, approval, appointment, request for evidence and more."},
   eligibility_plain: {en: "Anyone who received a USCIS notice."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §3A; fetched 2026-09-27", notes: "Pinned-only entry (doc_type_pins); no tags by design."}}
- {id: uscis_biometrics_page, name: "USCIS: Preparing for Your Biometric Services Appointment", org_type: government, cost: free, priority: 45,
   url: "https://www.uscis.gov/forms/filing-guidance/preparing-for-your-biometric-services-appointment", languages: [en],
   serves: {scope: national}, tags: [],
   what_it_does: {en: "What to bring to a fingerprint (biometrics) appointment and how to reschedule before the date. Missing it without a good reason can end your application."},
   eligibility_plain: {en: "Anyone with a biometrics appointment notice."},
   prepare_checklist_keys: [bring_notice, bring_photo_id],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §3A; fetched 2026-09-27", notes: "Pinned-only entry."}}
- {id: uscis_forms_free, name: "USCIS: All Forms (always free)", org_type: government, cost: free, priority: 50,
   url: "https://www.uscis.gov/forms/all-forms", languages: [en, es],
   serves: {scope: national}, tags: [scam_report, fee_waiver], warnings: [forms_are_free],
   what_it_does: {en: "Every USCIS form, free to download. Anyone selling you a blank form is not official."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1I; fetched 2026-09-27", expect_text: ["always free"]}}
- {id: uscis_scams, name: "USCIS: Common Scams", org_type: government, cost: free, priority: 90,
   url: "https://www.uscis.gov/scams-fraud-and-misconduct/avoid-scams/common-scams", languages: [en, es],
   serves: {scope: national}, tags: [scam_report],
   what_it_does: {en: "Official list of immigration scams. USCIS never asks for payment by Western Union, MoneyGram, PayPal, Venmo or gift cards, and only accepts fees through its .gov accounts."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1I/§4; fetched 2026-09-27 (payment-method sentence confirmed)", expect_text: ["gift cards"]}}
- {id: uscis_asylum, name: "USCIS Asylum", org_type: government, cost: free, priority: 60,
   url: "https://www.uscis.gov/humanitarian/refugees-and-asylum/asylum",
   alt_urls: ["https://www.uscis.gov/humanitarian/refugees-and-asylum/asylum/the-affirmative-asylum-process", "https://www.uscis.gov/i-589"], languages: [en, es],
   serves: {scope: national}, tags: [asylum], warnings: [asylum_rules_aug_2026],
   what_it_does: {en: "Official asylum pages: the steps, the interview, and Form I-589. Since August 21, 2026 evidence is due 14 days before the interview."},
   eligibility_plain: {en: "People applying for asylum."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1L; three URLs fetched 2026-09-27", expect_text: ["14 calendar days"]}}
- {id: uscis_hr1_fees, name: "USCIS: Fees Based on H.R. 1", org_type: government, cost: free, priority: 55,
   url: "https://www.uscis.gov/newsroom/alerts/uscis-updates-fees-based-on-hr-1", languages: [en],
   serves: {scope: national}, tags: [asylum, work_permit, daca_tps, fee_waiver], warnings: [no_fee_waiver_hr1],
   what_it_does: {en: "The official notice of the new fees: $100 asylum filing fee, $100 yearly asylum fee, $550/$275 work permit fee for asylum, parole and TPS applicants, TPS up to $500. These fees cannot be waived."},
   eligibility_plain: {en: "People with asylum, parole or TPS cases."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1L; fetched 2026-09-27 (all amounts + 'cannot be waived' confirmed)", expect_text: ["cannot be waived"]}}
- {id: asap, name: "ASAP (Asylum Seeker Advocacy Project)", org_type: nonprofit, cost: free, priority: 80,
   url: "https://asaptogether.org/en/", alt_urls: ["https://asaptogether.org/en/new-fees/"], languages: [en, es, ht, ru, zh],
   serves: {scope: national}, tags: [asylum, work_permit, fee_waiver], warnings: [no_fee_waiver_hr1],
   what_it_does: {en: "Free membership for asylum seekers with plain guides on work permits, court, and the yearly asylum fee (about $102, due 30 days after the notice; no waiver). Some people never get the fee notice, so check if your case has been pending more than a year."},
   eligibility_plain: {en: "Asylum seekers anywhere in the U.S."},
   prepare_checklist_keys: [bring_notice, bring_a_number, bring_receipt_number],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1L; both URLs fetched 2026-09-27 ($102, 30 days, no waiver confirmed)", expect_text: ["fee waiver"]}}
- {id: uscis_afghan, name: "USCIS: Information for Afghan Nationals", org_type: government, cost: free, priority: 80,
   url: "https://www.uscis.gov/humanitarian/information-for-afghan-nationals", languages: [en],
   serves: {scope: national}, tags: [afghan_specific, refugee_services],
   what_it_does: {en: "Official page for Afghans in the U.S.: re-parole, work permits, asylum, Special Immigrant Visa adjustment and Green Card paths."},
   eligibility_plain: {en: "Afghan nationals and their families."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1K; fetched 2026-09-27", notes: "travel.state.gov SIV page is NOT seeded (Cloudflare; §13). Route SIV questions here."}}
- {id: orr_afghan_benefits, name: "ORR: Benefits for Afghan Humanitarian Parolees", org_type: government, cost: free, priority: 60,
   url: "https://acf.gov/orr/fact-sheet/benefits-afghan-humanitarian-parolees", languages: [en],
   serves: {scope: national}, tags: [afghan_specific, refugee_services, benefits_navigation],
   what_it_does: {en: "Explains the cash, medical and job-support help Afghan parolees can get through refugee programs."},
   eligibility_plain: {en: "Afghan humanitarian parolees. Your State Refugee Coordinator can confirm what applies."},
   verified_on: 2026-09-23, verification_method: browser, link_health: unknown_403,
   x_meta: {source: "resources.md §1K (browser 2026-09-23); fetch 2026-09-27 → HTTP 403 (acf.gov blocks fetchers)"}}
- {id: afghanevac, name: "#AfghanEvac", org_type: nonprofit, cost: free, priority: 50,
   url: "https://afghanevac.org/", languages: [en],
   serves: {scope: national}, tags: [afghan_specific],
   what_it_does: {en: "A coalition helping Afghan wartime allies with relocation and resettlement, including volunteers who go with people to immigration appointments."},
   eligibility_plain: {en: "Afghan allies and their families."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1K; fetched 2026-09-27"}}
- {id: orr_state_contacts, name: "ORR Key State Contacts (State Refugee Coordinators)", org_type: directory, cost: free, priority: 75,
   url: "https://acf.gov/orr/programs-services/refugees/contacts/state-contacts", alt_urls: ["https://acf.gov/orr"], languages: [en],
   serves: {scope: national}, tags: [refugee_services, afghan_specific, benefits_navigation],
   what_it_does: {en: "Phone numbers for each state's Refugee Coordinator and Refugee Health Coordinator. The stable starting point when a local resettlement office has closed."},
   eligibility_plain: {en: "Refugees, asylees, parolees and others served by refugee programs."},
   verified_on: 2026-09-23, verification_method: browser, link_health: unknown_403,
   x_meta: {source: "resources.md §1J (browser 2026-09-23); fetch 2026-09-27 → HTTP 403 on both URLs"}}
- {id: irc, name: "International Rescue Committee (IRC)", org_type: resettlement, cost: free, priority: 40,
   url: "https://www.rescue.org/", languages: [en, es],
   serves: {scope: national}, tags: [refugee_services], warnings: [verify_local_office_open],
   what_it_does: {en: "Resettlement, asylum and integration services in about 30 U.S. cities. Find the nearest office under 'Where We Work'."},
   eligibility_plain: {en: "Refugees, asylees and other newcomers; each office sets its programs."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1J; fetched 2026-09-27"}}
- {id: uscri, name: "USCRI (U.S. Committee for Refugees and Immigrants)", org_type: resettlement, cost: free, priority: 40,
   url: "https://refugees.org/", languages: [en, es],
   serves: {scope: national}, tags: [refugee_services, trafficking], warnings: [verify_local_office_open],
   what_it_does: {en: "Legal, health, anti-trafficking and resettlement services with local offices ('Find Us')."},
   eligibility_plain: {en: "Refugees and immigrants; each office sets its programs."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1J; fetched 2026-09-27"}}
- {id: hias, name: "HIAS", org_type: resettlement, cost: free, priority: 35,
   url: "https://hias.org/", languages: [en],
   serves: {scope: national}, tags: [refugee_services, asylum], warnings: [verify_local_office_open],
   what_it_does: {en: "Refugee protection organization with U.S. legal services for refugees and asylum seekers (New York and Maryland) and a resettlement partner network."},
   eligibility_plain: {en: "Refugees and asylum seekers; legal help depends on location."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1J; fetched 2026-09-27"}}
- {id: global_refuge, name: "Global Refuge (formerly LIRS)", org_type: resettlement, cost: free, priority: 40,
   url: "https://www.globalrefuge.org/", phone: "+14109834000", languages: [en],
   serves: {scope: national}, tags: [refugee_services], warnings: [verify_local_office_open],
   what_it_does: {en: "Resettlement, legal help, mental health and family reunification for refugees and immigrants."},
   eligibility_plain: {en: "Refugees and immigrants; programs vary by location."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1J; fetched 2026-09-27 (410-983-4000 on page)", expect_text: ["410-983-4000"]}}
- {id: cws, name: "Church World Service", org_type: resettlement, cost: free, priority: 40,
   url: "https://cwsglobal.org/", phone: "+18002971516", languages: [en],
   serves: {scope: national}, tags: [refugee_services, asylum], warnings: [verify_local_office_open],
   what_it_does: {en: "Resettlement, asylum, legal and children's services through local offices (map on the site)."},
   eligibility_plain: {en: "Refugees, asylum seekers and immigrants; programs vary by office."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1J; fetched 2026-09-27 (1.800.297.1516 on page)", expect_text: ["297.1516"]}}
- {id: world_relief, name: "World Relief", org_type: resettlement, cost: free, priority: 40,
   url: "https://worldrelief.org/", languages: [en],
   serves: {scope: national}, tags: [refugee_services, immigration_legal_help], warnings: [verify_local_office_open],
   what_it_does: {en: "Resettlement and immigration legal services through U.S. offices (see 'Our Locations')."},
   eligibility_plain: {en: "Refugees and immigrants; programs vary by office."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1J; fetched 2026-09-27"}}
- {id: ecdc, name: "Ethiopian Community Development Council (ECDC)", org_type: resettlement, cost: free, priority: 40,
   url: "https://www.ecdcus.org/", languages: [en, am],
   serves: {scope: national}, tags: [refugee_services], warnings: [verify_local_office_open],
   what_it_does: {en: "National refugee resettlement agency with branches and affiliates across the U.S."},
   eligibility_plain: {en: "Refugees and immigrants; programs vary by office."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1J; fetched 2026-09-27", notes: "Amharic listed from ECDC's community focus; confirm on re-verification."}}
- {id: switchboard, name: "Switchboard / SettleIn newcomer information", org_type: nonprofit, cost: free, priority: 35,
   url: "https://www.switchboardta.org/", languages: [en, es, ar, prs, ps, uk, ru, fr, sw, my],
   serves: {scope: national}, tags: [refugee_services],
   what_it_does: {en: "Trusted information for newcomers about life in the U.S. (SettleIn), in more than 10 languages, from the refugee-program support hub."},
   eligibility_plain: {en: "Anyone new to the U.S."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1J; fetched 2026-09-27 (SettleIn in 10+ languages)", notes: "Exact SettleIn language list to be confirmed on re-verification; the 10 listed are the common resettlement languages."}}
- {id: dhs_oig, name: "DHS Office of Inspector General Hotline", org_type: hotline, cost: free, priority: 95,
   url: "https://www.oig.dhs.gov/hotline", phone: "+18003238603", languages: [en],
   serves: {scope: national}, tags: [scam_report],
   what_it_does: {en: "Report anyone pretending to be ICE or USCIS, or asking for money to avoid arrest or deportation."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1I; fetched 2026-09-27 (1-800-323-8603 on page)", expect_text: ["1-800-323-8603"]}}
- {id: doj_title_vi, name: "DOJ: Title VI (discrimination by national origin)", org_type: government, cost: free, priority: 40,
   url: "https://www.justice.gov/crt/fcs/TitleVI", languages: [en],
   serves: {scope: national}, tags: [language_access, discrimination],
   what_it_does: {en: "Programs that get federal money may not discriminate by race, color or national origin. Explains how to file a complaint. Note: the older language-access order (EO 13166) was revoked in 2025."},
   eligibility_plain: {en: "Anyone treated unfairly by a federally funded program."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1H; fetched 2026-09-27 (EO 13166 revocation note confirmed)", notes: "Never cite lep.gov (suspended)."}}
- {id: ftc_immigrant_scams, name: "FTC: Scams Against Immigrants", org_type: government, cost: free, priority: 85,
   url: "https://consumer.ftc.gov/features/scams-against-immigrants", alt_urls: ["https://consumer.ftc.gov/articles/how-avoid-immigration-scams-and-get-real-help"],
   phone: "+18773824357", languages: [en, es, am, ar, zh-Hans, zh-Hant, fr, hmn, ko, ru, so, tl, uk, vi],
   serves: {scope: national}, tags: [scam_report],
   what_it_does: {en: "How to spot immigration scams and get real help, in 14 languages. Report by phone at 877-382-4357 (press 3 for other languages)."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1I; both URLs fetched 2026-09-27 (14 languages, 877-382-4357 press 3)", expect_text: ["382-4357"]}}
- {id: ftc_reportfraud, name: "ReportFraud.ftc.gov", org_type: government, cost: free, priority: 90,
   url: "https://reportfraud.ftc.gov/", languages: [en, es],
   serves: {scope: national}, tags: [scam_report],
   what_it_does: {en: "The government's online form to report a scam. Spanish version: ReporteFraude.ftc.gov."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-23, verification_method: browser, link_health: js_rendered,
   x_meta: {source: "resources.md §1I (HTTP 200, JS app); fetch 2026-09-27 → shell only", notes: "Used by the D-13 fixed scam card (scam_card_url)."}}
- {id: ftc_gift_card_scams, name: "FTC: Avoiding and Reporting Gift Card Scams", org_type: government, cost: free, priority: 50,
   url: "https://consumer.ftc.gov/articles/avoiding-and-reporting-gift-card-scams", languages: [en, es],
   serves: {scope: national}, tags: [scam_report],
   what_it_does: {en: "No real business or government agency will ever tell you to pay with a gift card. What to do if you already paid."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1I; fetched 2026-09-27", expect_text: ["gift card"]}}
- {id: ftc_job_scams, name: "FTC: Job Scams", org_type: government, cost: free, priority: 45,
   url: "https://consumer.ftc.gov/articles/job-scams", languages: [en, es],
   serves: {scope: national}, tags: [scam_report, workers_rights],
   what_it_does: {en: "Honest employers never ask you to pay to get a job. Signs of fake job offers and how to report them."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1I; fetched 2026-09-27", expect_text: ["pay to get a job"]}}
```

### 11.3 `data/resources/national_health.yaml` (13 entries)

```yaml
# Clinics for the uninsured, coverage, hospital bills/charity care, appeals, Medicare, labs, vaccines, language rights in health care.
- {id: hrsa_fqhc, name: "HRSA Find a Health Center", org_type: directory, cost: sliding, priority: 80,
   url: "https://findahealthcenter.hrsa.gov/", languages: [en, es],
   serves: {scope: national}, tags: [primary_care_uninsured, prescription_help, vaccine_records], status_note_key: hhs_funded_health,
   what_it_does: {en: "Find a community health center near you by ZIP code. Health centers see everyone, with or without insurance or papers, and charge based on income."},
   eligibility_plain: {en: "Anyone. Fees depend on income."},
   prepare_checklist_keys: [bring_proof_income, bring_photo_id],
   verified_on: 2026-09-23, verification_method: browser, link_health: js_rendered,
   x_meta: {source: "resources.md §1C (browser 2026-09-23); fetch 2026-09-27 → HTTP 200 shell, title 'Find a Health Center'", notes: "Well-known id: fallback_health."}}
- {id: healthcare_gov, name: "HealthCare.gov (Health Insurance Marketplace)", org_type: government, cost: free, priority: 55,
   url: "https://www.healthcare.gov/", alt_urls: ["https://www.healthcare.gov/medicaid-chip/"], phone: "+18003182596", tty: "+18558894325", hours: "24/7", languages: [en, es, interpreters_200+],
   serves: {scope: national}, tags: [medicaid_renewal, insurance_denial, benefits_navigation], warnings: [hr1_coverage_changes],
   what_it_does: {en: "Apply for health coverage, find local help (navigators), and apply for Medicaid or CHIP any time of year. Call center 1-800-318-2596."},
   eligibility_plain: {en: "Anyone. Coverage rules for many immigrants changed in 2026 and 2027; a navigator can say what applies."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1C; both URLs fetched 2026-09-27; phone+TTY re-confirmed on healthcare.gov/contact-us 2026-09-29 (phone field had a 5596 typo)", notes: "Hours 24/7 and interpreter line are HealthCare.gov's long-standing call-center facts; confirm on re-verification. Do NOT link the lawfully-present-immigrants page (stale for H.R.1).", expect_text: ["1-800-318-2596"]}}
- {id: medicaid_state, name: "Medicaid.gov: Where Can People Get Help With Medicaid & CHIP", org_type: directory, cost: free, priority: 85,
   url: "https://www.medicaid.gov/about-us/where-can-people-get-help-medicaid-chip", languages: [en, es],
   serves: {scope: national}, tags: [medicaid_renewal, benefits_navigation], status_note_key: hhs_funded_health,
   what_it_does: {en: "Every state's Medicaid office with phone numbers and links to check a renewal or ask about a notice."},
   eligibility_plain: {en: "Anyone with Medicaid or CHIP, or a letter about it."},
   prepare_checklist_keys: [bring_notice, bring_case_number],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1C; fetched 2026-09-27 (served content today; historically 403 to fetchers)", notes: "Do not append /index.html (404)."}}
- {id: insurekidsnow, name: "InsureKidsNow.gov", org_type: government, cost: free, priority: 60,
   url: "https://www.insurekidsnow.gov/", phone: "+18775437669", languages: [en, es],
   serves: {scope: national}, tags: [medicaid_renewal],
   what_it_does: {en: "Free or low-cost health coverage for children (Medicaid and CHIP), by state. Call 1-877-KIDS-NOW."},
   eligibility_plain: {en: "Families with children."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1C; fetched 2026-09-27 (1-877-543-7669 on page)", expect_text: ["877-543-7669"]}}
- {id: irs_501r, name: "IRS: Hospital Financial Assistance Policy rules (Section 501(r)(4))", org_type: government, cost: free, priority: 40,
   url: "https://www.irs.gov/charities-non-profits/financial-assistance-policy-and-emergency-medical-care-policy-section-501r4", languages: [en],
   serves: {scope: national}, tags: [charity_care, medical_bill],
   what_it_does: {en: "Nonprofit hospitals must have a written financial assistance policy, a plain-language summary and an application. This page explains the rule you can point to when you ask for help with a bill."},
   eligibility_plain: {en: "Anyone with a bill from a nonprofit hospital."},
   prepare_checklist_keys: [bring_the_bill],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1C; fetched 2026-09-27"}}
- {id: dollarfor, name: "Dollar For", org_type: nonprofit, cost: free, priority: 75,
   url: "https://dollarfor.org/", languages: [en, es],
   serves: {scope: national}, tags: [charity_care, medical_bill],
   what_it_does: {en: "Free help checking if a hospital must reduce or forgive your bill, and help filling out the charity care application."},
   eligibility_plain: {en: "Anyone with a nonprofit hospital bill."},
   prepare_checklist_keys: [bring_the_bill, bring_proof_income],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1C; fetched 2026-09-27 (English/Spanish)"}}
- {id: cms_medical_bill_rights, name: "Medical Bill Rights / No Surprises Help Desk", org_type: government, cost: free, priority: 65,
   url: "https://www.cms.gov/initiatives/your-patient-rights/medical-bill-rights", alt_urls: ["https://www.cms.gov/nosurprises"],
   phone: "+18009853059", hours: "7 days a week", languages: [interpreters_200+],
   serves: {scope: national}, tags: [medical_bill, insurance_denial],
   what_it_does: {en: "Your rights about surprise bills and cost estimates. If a bill is at least $400 more than your good faith estimate, you can dispute it. Help Desk in more than 200 languages."},
   eligibility_plain: {en: "Anyone with a medical bill."},
   prepare_checklist_keys: [bring_the_bill, bring_itemized_bill_request],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1C; both URLs fetched 2026-09-27 (phone, '7 days a week', $400 confirmed; 120-day window not printed on page today)", expect_text: ["1-800-985-3059"]}}
- {id: healthcare_appeals, name: "HealthCare.gov: Appealing a health plan decision", org_type: government, cost: free, priority: 70,
   url: "https://www.healthcare.gov/appeal-insurance-company-decision/internal-appeals/",
   alt_urls: ["https://www.healthcare.gov/appeal-insurance-company-decision/external-review/"], languages: [en, es],
   serves: {scope: national}, tags: [insurance_denial],
   what_it_does: {en: "How to appeal when insurance says no: an internal appeal within 180 days, then an outside review within 4 months of the final denial."},
   eligibility_plain: {en: "People with Marketplace or job-based health plans. Medicaid and Medicare have their own appeal rules."},
   prepare_checklist_keys: [bring_denial_letter, bring_insurance_card],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1C; both URLs fetched 2026-09-27 (180 days / 4 months confirmed)", expect_text: ["180 days"]}}
- {id: medicare_appeals, name: "Medicare.gov: Filing an appeal", org_type: government, cost: free, priority: 70,
   url: "https://www.medicare.gov/providers-services/claims-appeals-complaints/appeals",
   alt_urls: ["https://www.medicare.gov/providers-services/claims-appeals-complaints/appeals/original-medicare", "https://www.medicare.gov/providers-services/claims-appeals-complaints/appeals/medicare-health-plans", "https://www.medicare.gov/providers-services/claims-appeals-complaints/appeals/drug-plans"],
   languages: [en, es],
   serves: {scope: national}, tags: [medicare_appeal, insurance_denial], warnings: [medicare_windows_changed],
   what_it_does: {en: "The steps to appeal a Medicare decision. Use the date printed on your notice; plan appeals have their own windows."},
   eligibility_plain: {en: "People with Medicare, a Medicare Advantage plan or a Part D drug plan."},
   prepare_checklist_keys: [bring_denial_letter, bring_insurance_card],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1C; four URLs fetched 2026-09-27 (MA page: 65 days Level 1; Part D page text read today shows the 60-day Level 2 window — human to re-read the Level 1 window)", expect_text: ["65 days"]}}
- {id: medlineplus_labs, name: "MedlinePlus: How to Understand Your Lab Results", org_type: government, cost: free, priority: 80,
   url: "https://medlineplus.gov/lab-tests/how-to-understand-your-lab-results/", languages: [en, es],
   serves: {scope: national}, tags: [lab_results],
   what_it_does: {en: "Plain explanation of reference ranges. A result outside the range may or may not mean a health problem; ask the person who ordered the test."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1C; fetched 2026-09-27", expect_text: ["reference range"]}}
- {id: cdc_iis, name: "CDC: Contacts for Immunization Records (state registries)", org_type: directory, cost: free, priority: 75,
   url: "https://www.cdc.gov/iis/contacts-locate-records/index.html", languages: [en],
   serves: {scope: national}, tags: [vaccine_records, school_enrollment],
   what_it_does: {en: "Phone numbers and websites for each state's vaccine registry, where you can ask for a copy of your or your child's shot record."},
   eligibility_plain: {en: "Anyone who got vaccines in that state."},
   prepare_checklist_keys: [bring_photo_id],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1C; fetched 2026-09-27 (served content today; historically 403)"}}
- {id: school_vaccine_requirements, name: "CDC: State Vaccination Requirements for school and child care", org_type: government, cost: free, priority: 55,
   url: "https://www.cdc.gov/vaccines/php/requirements-laws/state-vaccination-requirements.html", alt_urls: ["https://www.immunize.org/official-guidance/state-policies/"], languages: [en],
   serves: {scope: national}, tags: [vaccine_records, school_enrollment],
   what_it_does: {en: "Which vaccines each state requires for school and child care, and the exemption rules (Immunize.org tables)."},
   eligibility_plain: {en: "Families enrolling a child."},
   prepare_checklist_keys: [bring_vaccine_record],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1C; both URLs fetched 2026-09-27"}}
- {id: hhs_ocr_lep, name: "HHS Office for Civil Rights: Limited English Proficiency (language access rights)", org_type: government, cost: free, priority: 70,
   url: "https://www.hhs.gov/civil-rights/for-individuals/special-topics/limited-english-proficiency/index.html", languages: [en],
   serves: {scope: national}, tags: [language_access], status_note_key: hhs_funded_health,
   what_it_does: {en: "Hospitals, pharmacies, clinics and insurance programs that get federal health money must offer free language help. Explains the right and how to complain."},
   eligibility_plain: {en: "Anyone who needs an interpreter in a health setting."},
   verified_on: 2026-09-23, verification_method: browser, link_health: unknown_403,
   x_meta: {source: "resources.md §1C/§1H (browser 2026-09-23); fetch 2026-09-27 → HTTP 403", notes: "The D-18 interpreter line cites this page; never lep.gov."}}
```

### 11.4 `data/resources/national_benefits_food.yaml` (10 entries)

```yaml
# 211, benefit finder, SNAP, WIC, school meals, food banks, SSA appeals and scams, LIHEAP.
- {id: "211", name: "211", org_type: hotline, cost: free, priority: 40,
   url: "https://www.211.org/", phone: "211", hours: "Varies by area; many lines are 24/7", languages: [en, es, interpreters_200+],
   serves: {scope: national}, tags: [benefits_navigation, food, rent_assistance, utility_shutoff, crisis],
   what_it_does: {en: "Dial 211 for free, confidential help finding local food, rent and utility help, health care and crisis support."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1E; fetched 2026-09-27 (English/Spanish, 'find your local 211')", notes: "Hours and interpreter access vary by local 211; wording kept general. Well-known id: fallback_always."}}
- {id: usa_benefit_finder, name: "USA.gov Benefit Finder", org_type: government, cost: free, priority: 50,
   url: "https://www.usa.gov/benefit-finder", languages: [en, es],
   serves: {scope: national}, tags: [benefits_navigation],
   what_it_does: {en: "Pick a category and answer questions to see government benefits you may be able to apply for. Benefits.gov now points here."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1F; fetched 2026-09-27"}}
- {id: snap_state, name: "SNAP State Directory of Resources", org_type: directory, cost: free, priority: 85,
   name_note: "USDA Food and Nutrition Administration (formerly Food and Nutrition Service)",
   url: "https://www.fna.usda.gov/snap/state-directory", alt_urls: ["https://www.fna.usda.gov/snap/recipient/eligibility"], languages: [en, es],
   serves: {scope: national}, tags: [snap, food],
   what_it_does: {en: "Each state's SNAP (food stamps) hotline and application website. States decide within 30 days and require an interview; emergency cases within 7 days."},
   eligibility_plain: {en: "Anyone with a SNAP case or notice. Rules differ for each person in the household; parents can apply for eligible children."},
   prepare_checklist_keys: [bring_notice, bring_household_ids, bring_proof_income, bring_proof_rent_utilities],
   verified_on: 2026-09-23, verification_method: browser, link_health: unknown_403,
   x_meta: {source: "resources.md §1D (browser 2026-09-23); fetch 2026-09-27 → HTTP 403 on both URLs", notes: "Store fna.usda.gov URLs only; fns.usda.gov legacy paths do not all redirect."}}
- {id: wic, name: "WIC (Women, Infants, and Children)", org_type: government, cost: free, priority: 60,
   name_note: "USDA Food and Nutrition Administration",
   url: "https://www.fna.usda.gov/wic", alt_urls: ["https://www.fna.usda.gov/wic/eligibility"], languages: [en, es],
   serves: {scope: national}, tags: [wic, food],
   what_it_does: {en: "Healthy food, nutrition help and referrals for pregnant or breastfeeding women, infants and children under 5. There is no immigration-status requirement."},
   eligibility_plain: {en: "Pregnant or recently pregnant women, and anyone raising a child under 5, within income limits or already on Medicaid, SNAP or TANF."},
   prepare_checklist_keys: [bring_household_ids, bring_proof_address, bring_proof_income_or_benefit_card, bring_the_child],
   verified_on: 2026-09-23, verification_method: browser, link_health: unknown_403,
   x_meta: {source: "resources.md §1D (browser 2026-09-23); fetch 2026-09-27 → HTTP 403 on both URLs"}}
- {id: signupwic, name: "SignUpWIC.com (find a WIC clinic)", org_type: directory, cost: free, priority: 80,
   name_note: "National WIC Association",
   url: "https://signupwic.com/", languages: [en, es],
   serves: {scope: national}, tags: [wic, food],
   what_it_does: {en: "Check if you may qualify for WIC and find the WIC clinic nearest you."},
   eligibility_plain: {en: "Pregnant women and families with children under 5."},
   prepare_checklist_keys: [bring_household_ids, bring_proof_address, bring_proof_income_or_benefit_card],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1D; fetched 2026-09-27 (eligibility assessment + Spanish site)"}}
- {id: school_meals, name: "Free and reduced-price school meals (how households apply)", org_type: government, cost: free, priority: 75,
   name_note: "USDA Food and Nutrition Administration",
   url: "https://www.fna.usda.gov/nslp/household", languages: [en, es],
   serves: {scope: national}, tags: [school_meals, food],
   what_it_does: {en: "Apply for free or reduced-price school meals through your child's school or district. Families on SNAP or Medicaid may be signed up automatically."},
   eligibility_plain: {en: "Families with children in school, within income limits."},
   prepare_checklist_keys: [bring_proof_income],
   verified_on: 2026-09-23, verification_method: browser, link_health: unknown_403,
   x_meta: {source: "resources.md §1D (browser 2026-09-23); fetch 2026-09-27 → HTTP 403"}}
- {id: feeding_america, name: "Feeding America: Find Your Local Food Bank", org_type: directory, cost: free, priority: 70,
   url: "https://www.feedingamerica.org/find-your-local-foodbank", languages: [en, es],
   serves: {scope: national}, tags: [food],
   what_it_does: {en: "Enter your ZIP code or state to find the food bank that serves your area and its pantries."},
   eligibility_plain: {en: "Anyone who needs food. No ID requirement is stated."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1D; fetched 2026-09-27"}}
- {id: ssa_appeals, name: "Social Security: Appeal a decision we made", org_type: government, cost: free, priority: 75,
   url: "https://www.ssa.gov/apply/appeal-decision-we-made", languages: [en, es],
   serves: {scope: national}, tags: [ssa_benefits],
   what_it_does: {en: "How to ask Social Security to look at a decision again: reconsideration, a hearing, the Appeals Council, then court. Use the deadline printed on your letter."},
   eligibility_plain: {en: "Anyone who got a Social Security decision letter."},
   prepare_checklist_keys: [bring_notice, bring_photo_id],
   verified_on: 2026-09-23, verification_method: browser, link_health: unknown_403,
   x_meta: {source: "resources.md §3D (browser 2026-09-23); fetch 2026-09-27 → HTTP 403", notes: "The 60-day appeal window is not printed on the page; deadline_rules.yaml treats it as 'likely'."}}
- {id: ssa_scams, name: "Social Security: Protect Yourself from Scams", org_type: government, cost: free, priority: 60,
   url: "https://www.ssa.gov/scam/", languages: [en, es],
   serves: {scope: national}, tags: [scam_report, ssa_benefits],
   what_it_does: {en: "Social Security never threatens arrest or demands gift cards, wire transfers or crypto. The four signs of a scam and how to report one."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-23, verification_method: browser, link_health: unknown_403,
   x_meta: {source: "resources.md §1I (browser 2026-09-23); fetch 2026-09-27 → HTTP 403"}}
- {id: liheap, name: "LIHEAP (help with heating, cooling and shutoff notices)", org_type: utility_program, cost: free, priority: 80,
   url: "https://acf.gov/ocs/programs/liheap", phone: "+18666746327", languages: [en, es],
   serves: {scope: national}, tags: [utility_shutoff],
   what_it_does: {en: "Help paying heating and cooling bills and stopping or reversing a shutoff. The referral line 1-866-674-6327 points you to your local office."},
   eligibility_plain: {en: "Households within income limits; each state runs its own program."},
   prepare_checklist_keys: [bring_shutoff_notice, bring_proof_income, bring_household_ids],
   verified_on: 2026-09-23, verification_method: browser, link_health: unknown_403,
   x_meta: {source: "resources.md §1E (browser 2026-09-23; phone from that page); fetch 2026-09-27 → HTTP 403", notes: "Local-office search tool (liheapch.acf.gov) is only 'likely' in research → not in alt_urls."}}
```

### 11.5 `data/resources/national_housing.yaml` (6 entries)

```yaml
# HUD counselors, PHA contacts, USA.gov housing help, civil legal aid finders (LSC-restricted), LSC eviction laws database (staff reference).
- {id: hud_counselor, name: "HUD: Find a Housing Counselor", org_type: directory, cost: free, priority: 75,
   url: "https://www.hud.gov/findacounselor", alt_urls: ["https://www.consumerfinance.gov/coronavirus/mortgage-and-housing-assistance/renter-protections/"],
   phone: "+18005694287", languages: [en, es],
   serves: {scope: national}, tags: [housing_counseling, eviction, rent_assistance],
   what_it_does: {en: "Free or low-cost HUD-approved counselors for rent problems, eviction prevention and housing questions. Call 800-569-4287 to find one."},
   eligibility_plain: {en: "Anyone."},
   prepare_checklist_keys: [bring_notice, bring_lease],
   verified_on: 2026-09-23, verification_method: browser, link_health: js_rendered,
   x_meta: {source: "resources.md §1E; hud.gov page is a redirect/shell to fetchers (2026-09-27); phone confirmed on the CFPB alt_url fetched 2026-09-27", expect_text: ["800-569-4287"]}}
- {id: hud_pha, name: "HUD: Public Housing Agency contacts (Section 8 / vouchers)", org_type: directory, cost: free, priority: 80,
   url: "https://www.hud.gov/program_offices/public_indian_housing/pha/contacts", alt_urls: ["https://www.hud.gov/topics/housing_choice_voucher_program_section_8"], languages: [en],
   serves: {scope: national}, tags: [section8],
   what_it_does: {en: "Find the housing agency that runs your voucher or public housing, by state, to ask about a recertification letter."},
   eligibility_plain: {en: "People with a housing voucher or in public housing."},
   prepare_checklist_keys: [bring_notice, bring_proof_income, bring_household_ids],
   verified_on: 2026-09-23, verification_method: browser, link_health: js_rendered,
   x_meta: {source: "resources.md §1E (browser 2026-09-23); fetch 2026-09-27 → title ok, list not in readable text"}}
- {id: usa_housing_help, name: "USA.gov: Housing help", org_type: government, cost: free, priority: 45,
   url: "https://www.usa.gov/housing-help", languages: [en, es],
   serves: {scope: national}, tags: [rent_assistance, eviction, housing_counseling],
   what_it_does: {en: "Government overview of rental assistance, emergency housing and eviction help, with links to programs."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1E; fetched 2026-09-27", notes: "usa.gov/eviction is 404 — never link it."}}
- {id: lawhelp, name: "LawHelp.org", org_type: directory, cost: free, priority: 60,
   name_note: "Pro Bono Net",
   url: "https://www.lawhelp.org/", languages: [en, es],
   serves: {scope: national}, tags: [eviction, benefits_navigation, workers_rights, traffic_court], status_note_key: lsc_restricted,
   what_it_does: {en: "Find free legal aid in your state and read self-help guides about housing, benefits and more."},
   eligibility_plain: {en: "Low-income people. Many listed offices get federal legal-aid funding and can only help certain immigrants."},
   prepare_checklist_keys: [bring_notice, bring_proof_income],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1B; fetched 2026-09-27", notes: "lsc_restricted per 45 CFR 1626 (https://www.ecfr.gov/current/title-45/subtitle-B/chapter-XVI/part-1626, research verified). LawHelp lists some non-LSC providers too; the note stays because the user cannot tell which."}}
- {id: lsc_find, name: "LSC: Find Legal Aid", org_type: directory, cost: free, priority: 55,
   name_note: "Legal Services Corporation",
   url: "https://www.lsc.gov/about-lsc/what-legal-aid/get-legal-help", languages: [en],
   serves: {scope: national}, tags: [eviction, benefits_navigation, workers_rights], status_note_key: lsc_restricted,
   what_it_does: {en: "Map of federally funded legal aid offices. Enter an address or city to find the one that covers you."},
   eligibility_plain: {en: "Low-income people. These offices can only help citizens and certain immigrants, plus survivors of violence or trafficking."},
   prepare_checklist_keys: [bring_notice, bring_proof_income],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1B; fetched 2026-09-27"}}
- {id: lsc_eviction_db, name: "LSC Eviction Laws Database (for helpers)", org_type: directory, cost: free, priority: 10,
   url: "https://www.lsc.gov/initiatives/effect-state-local-laws-evictions/lsc-eviction-laws-database", languages: [en],
   serves: {scope: national}, tags: [eviction], warnings: [staff_reference, lsc_eviction_db_2021],
   what_it_does: {en: "A research database of each state's eviction steps, notice periods and deadlines. For caseworkers and helpers; confirm current rules with a legal helpline."},
   eligibility_plain: {en: "Anyone; written for professionals."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1B; fetched 2026-09-27 — page states data reflect laws effective as of January 1, 2021", notes: "Never used for date math (D-11); staff reference only."}}
```

### 11.6 `data/resources/national_crisis.yaml` (4 entries)

These numbers also live in fixed copy (`en.json` emergency card, D-14). The DB copies exist so the Help tab, the matcher (forced ordering) and the quick-sheet validator can reference them by id. `hours: "24/7"` is stated on 988, DV and Trafficking pages today; Poison Control's page leads with the online tool and does not print "24/7" (kept in `x_meta`, not claimed in `hours`).

```yaml
- {id: "988", name: "988 Suicide & Crisis Lifeline", org_type: hotline, cost: free, priority: 100,
   url: "https://988lifeline.org/", phone: "988", text_line: "Text 988", hours: "24/7", languages: [en, es, interpreters_200+],
   serves: {scope: national}, tags: [crisis],
   what_it_does: {en: "Call or text 988, or chat online, any time you or someone you love is in crisis or thinking about suicide. Free and confidential. Spanish line and interpreters available."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1G; fetched 2026-09-27 (call/text 988, chat, English/Español)", notes: "240+ languages via interpretation per research 2026-09-23.", expect_text: ["988"]}}
- {id: dv_hotline, name: "National Domestic Violence Hotline", org_type: hotline, cost: free, priority: 100,
   url: "https://www.thehotline.org/", phone: "+18007997233", text_line: "Text START to 88788", hours: "24/7", languages: [en, es, interpreters_200+],
   serves: {scope: national}, tags: [domestic_violence, crisis],
   what_it_does: {en: "Call 1-800-799-7233, text START to 88788, or chat online for confidential help with abuse at home, any time. Spanish site: espanol.thehotline.org."},
   eligibility_plain: {en: "Anyone. You do not have to give your name."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1G; fetched 2026-09-27 (phone, text, 24/7, Spanish confirmed; 200+ languages per research)", expect_text: ["799", "88788"]}}
- {id: poison, name: "Poison Control (Poison Help)", org_type: hotline, cost: free, priority: 100,
   url: "https://www.poison.org/", phone: "+18002221222", languages: [en],
   serves: {scope: national}, tags: [poison, crisis],
   what_it_does: {en: "Call 1-800-222-1222 right away if someone swallowed, breathed or touched something that may be poison, or use the webPOISONCONTROL online tool. Free, expert and confidential."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1G; fetched 2026-09-27 (number + online tool confirmed)", notes: "24/7 and interpreter access are general knowledge, not printed on the home page — hours left null; the fixed emergency card may say 'any time' from its own reviewed copy.", expect_text: ["1-800-222-1222"]}}
- {id: trafficking, name: "National Human Trafficking Hotline", org_type: hotline, cost: free, priority: 95,
   url: "https://humantraffickinghotline.org/", phone: "+18883737888", tty: "711", text_line: "Text 233733", hours: "24/7", languages: [en, es],
   serves: {scope: national}, tags: [trafficking, crisis, domestic_violence],
   what_it_does: {en: "Call 1-888-373-7888 or text 233733 if you or someone you know is being forced to work or have sex, or is being controlled through debt or threats. Confidential, any time."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1G; fetched 2026-09-27 (phone, TTY 711, text, 24/7 confirmed)", expect_text: ["1-888-373-7888", "233733"]}}
```

### 11.7 `data/resources/national_school_work_tax.yaml` (12 entries)

```yaml
# School rights (McKinney-Vento, Plyler, IEP/504), workers' rights (WHD, EEOC, OSHA), IRS notices/ITIN/scams, jury summons.
- {id: nche_mckinney_vento, name: "National Center for Homeless Education: McKinney-Vento rights", org_type: government, cost: free, priority: 70,
   url: "https://nche.ed.gov/mckinney-vento/", alt_urls: ["https://nche.ed.gov/"], languages: [en],
   serves: {scope: national}, tags: [homeless_students, school_enrollment],
   what_it_does: {en: "Children without a fixed home (shelters, doubled-up, motels) can enroll in school right away without records or proof of address, and every district has a liaison to help."},
   eligibility_plain: {en: "Families and youth without stable housing."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1N; both URLs fetched 2026-09-27"}}
- {id: shc_liaison_directory, name: "SchoolHouse Connection: Homeless Education Directory (find your liaison)", org_type: directory, cost: free, priority: 75,
   url: "https://schoolhouseconnection.org/homeless-education-directory", languages: [en],
   serves: {scope: national}, tags: [homeless_students, school_enrollment],
   what_it_does: {en: "Find the McKinney-Vento coordinator for your state and the liaison for your school district."},
   eligibility_plain: {en: "Families and youth without stable housing."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1N; fetched 2026-09-27"}}
- {id: plyler_explainer, name: "Plyler v. Doe: public education for noncitizen students", org_type: nonprofit, cost: free, priority: 60,
   name_note: "American Immigration Council fact sheet",
   url: "https://www.americanimmigrationcouncil.org/fact-sheet/plyler-v-doe-public-education-noncitizen-students/", languages: [en],
   serves: {scope: national}, tags: [school_enrollment], warnings: [schools_may_not_ask_status],
   what_it_does: {en: "Every child can attend public school K-12 regardless of immigration status. Schools may not ask about status or require a Social Security number to enroll."},
   eligibility_plain: {en: "All families with school-age children."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1N; fetched 2026-09-27", notes: "ED/DOJ fact-sheet PDFs on ed.gov are 403/404 — this is the verified substitute."}}
- {id: pti_centers, name: "Parent Center Hub: Find Your Parent Center (free IEP/504 help)", org_type: directory, cost: free, priority: 80,
   url: "https://www.parentcenterhub.org/find-your-center/",
   alt_urls: ["https://www.parentcenterhub.org/iep-overview/", "https://www.parentcenterhub.org/ocr-guide-to-section504/"], languages: [en, es],
   serves: {scope: national}, tags: [special_education],
   what_it_does: {en: "Every state has free Parent Training and Information Centers that help families prepare for IEP and 504 meetings. Also hosts a plain IEP overview and the official Section 504 parent guide."},
   eligibility_plain: {en: "Parents of children with disabilities, birth to 26."},
   prepare_checklist_keys: [bring_notice, bring_school_records],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1N; three URLs fetched 2026-09-27 (IEP within 30 calendar days confirmed)"}}
- {id: ed_idea, name: "U.S. Department of Education: IDEA (special education law)", org_type: government, cost: free, priority: 40,
   url: "https://sites.ed.gov/idea/", languages: [en],
   serves: {scope: national}, tags: [special_education],
   what_it_does: {en: "The official site for the special education law (IDEA), including parent rights."},
   eligibility_plain: {en: "Parents of children who receive or may need special education."},
   verified_on: 2026-09-23, verification_method: browser, link_health: unknown_403,
   x_meta: {source: "resources.md §1N (browser 2026-09-23); fetch 2026-09-27 → HTTP 403"}}
- {id: dol_whd, name: "U.S. Department of Labor Wage and Hour Division: How to File a Complaint", org_type: government, cost: free, priority: 85,
   url: "https://www.dol.gov/agencies/whd/contact/complaints", phone: "+18664879243", languages: [en, es, interpreters_200+],
   serves: {scope: national}, tags: [wage_theft, workers_rights],
   what_it_does: {en: "Free, confidential help when an employer does not pay wages or overtime. Call 1-866-487-9243."},
   eligibility_plain: {en: "Any worker."},
   prepare_checklist_keys: [bring_pay_stubs, bring_hours_log, bring_employer_info],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1M; fetched 2026-09-27 (phone confirmed)", notes: "Research 2026-09-23 read 'immigration status is not a barrier' on this page; not visible in today's fetch text — eligibility kept neutral ('Any worker'). Interpreter line is WHD's stated practice; confirm on re-verification.", expect_text: ["1-866-487-9243"]}}
- {id: eeoc, name: "EEOC (Equal Employment Opportunity Commission)", org_type: government, cost: free, priority: 80,
   url: "https://www.eeoc.gov/employees-job-applicants",
   alt_urls: ["https://www.eeoc.gov/how-file-charge-employment-discrimination", "https://www.eeoc.gov/national-origin-discrimination"], phone: "+18006694000", languages: [en, es],
   serves: {scope: national}, tags: [discrimination, workers_rights], warnings: [eeoc_deadline_180_300],
   what_it_does: {en: "Report discrimination at work because of where you are from, your accent, religion, sex, disability or age. Call 1-800-669-4000. Charges usually must be filed within 180 days (300 in many states)."},
   eligibility_plain: {en: "Workers and job applicants."},
   prepare_checklist_keys: [bring_employer_info, bring_pay_stubs],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1M; three URLs fetched 2026-09-27 (phone, 180/300 days confirmed)", expect_text: ["1-800-669-4000"]}}
- {id: osha, name: "OSHA: Worker Rights and Protections", org_type: government, cost: free, priority: 75,
   url: "https://www.osha.gov/workers", phone: "+18003216742", languages: [en, es],
   serves: {scope: national}, tags: [workplace_safety, workers_rights], warnings: [osha_retaliation_30d],
   what_it_does: {en: "Report unsafe work conditions confidentially: 1-800-321-OSHA (6742). If you are punished for speaking up, file a retaliation complaint within 30 days."},
   eligibility_plain: {en: "Any worker."},
   prepare_checklist_keys: [bring_employer_info],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1M; fetched 2026-09-27 (phone, 30 days confirmed)", notes: "/workers/file-complaint is only 'likely' in research → not in alt_urls.", expect_text: ["321-OSHA"]}}
- {id: irs_notice_lookup, name: "IRS: Understanding your IRS notice or letter", org_type: government, cost: free, priority: 90,
   url: "https://www.irs.gov/individuals/understanding-your-irs-notice-or-letter", phone: "+18008291040", languages: [en, es, zh-Hans, ko, ru, vi, ht],
   serves: {scope: national}, tags: [tax_notice],
   what_it_does: {en: "Look up the CP or LTR number printed in the top right corner of your IRS letter to see what it means and what to do. If it is not listed, call 800-829-1040."},
   eligibility_plain: {en: "Anyone who got an IRS letter."},
   prepare_checklist_keys: [bring_notice, bring_tax_return],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §3H; fetched 2026-09-27 (lookup + 800-829-1040 confirmed)", notes: "Language list = IRS.gov site languages; confirm on re-verification.", expect_text: ["800-829-1040"]}}
- {id: irs_itin, name: "IRS: Individual Taxpayer Identification Number (ITIN)", org_type: government, cost: free, priority: 80,
   url: "https://www.irs.gov/individuals/individual-taxpayer-identification-number", languages: [en, es],
   serves: {scope: national}, tags: [itin, tax_notice],
   what_it_does: {en: "An ITIN is a tax number for people who cannot get a Social Security number. Apply with Form W-7, your passport or two other IDs, and your tax return."},
   eligibility_plain: {en: "People who must file taxes but cannot get a Social Security number, regardless of status."},
   prepare_checklist_keys: [bring_passport_or_two_ids, bring_tax_return],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §3H; fetched 2026-09-27"}}
- {id: irs_scams, name: "IRS: Recognize tax scams and fraud", org_type: government, cost: free, priority: 60,
   url: "https://www.irs.gov/help/tax-scams/recognize-tax-scams-and-fraud", languages: [en, es],
   serves: {scope: national}, tags: [scam_report, tax_notice],
   what_it_does: {en: "The IRS writes first by mail, never demands gift cards or wire transfers, and never threatens arrest or deportation. How to report a fake IRS call or letter."},
   eligibility_plain: {en: "Anyone."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §1I; fetched 2026-09-27", expect_text: ["deportation"]}}
- {id: uscourts_jury, name: "U.S. Courts: Juror Qualifications, Exemptions and Excuses", org_type: court, cost: free, priority: 90,
   url: "https://www.uscourts.gov/court-programs/jury-service/juror-qualifications-exemptions-and-excuses", languages: [en],
   serves: {scope: national}, tags: [jury_summons], warnings: [jury_never_check_citizen, jury_never_register_to_vote],
   what_it_does: {en: "Federal jurors must be U.S. citizens. If you are not a citizen, answer the form, mark that you are not a citizen, and send it back. Never ignore it and never check 'citizen'."},
   eligibility_plain: {en: "Anyone who received a jury summons."},
   prepare_checklist_keys: [bring_the_summons],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §3I; fetched 2026-09-27 (citizenship requirement confirmed)", notes: "State courts have similar rules; this is the verified federal page."}}
```

### 11.8 `data/resources/regional/va_nova.yaml` (14 entries — Northern Virginia / DC-metro exemplar)

```yaml
# Pilot geography (DECISIONS Q5). County names in canonical form; zip3 201/220/221/222/223 = NoVA, 200/202-205 = DC, 207-209 = MD suburbs.
- {id: inova_fa, name: "Inova Financial Assistance", org_type: hospital_program, cost: free, priority: 80,
   url: "https://www.inova.org/patient-and-visitor-information/financial-assistance", phone: "+15714725880", hours: "Mon–Fri 8:00–16:30",
   languages: [en, es, am, ar, prs, fa, ko, zh-Hans, ur, vi],
   serves: {scope: county, states: [VA], counties: [Fairfax, Loudoun, Arlington, Alexandria City, Fairfax City, Falls Church City], zip3: ["201", "220", "221", "222", "223"]},
   tags: [medical_bill, charity_care], status_note_key: residency_required, warnings: [ask_for_plain_language_summary],
   what_it_does: {en: "Helps people who cannot pay an Inova hospital bill apply for free or reduced-cost care. Apply online (MyChart), by mail, or in person."},
   eligibility_plain: {en: "You must live in the Inova service area in Virginia. Uninsured people with lower incomes often pay nothing. Ask for the plain-language summary in your language."},
   prepare_checklist_keys: [bring_proof_income, bring_proof_va_address, bring_the_bill, bring_household_ids],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §2; fetched 2026-09-27 (phone, hours, 10 summary languages confirmed; ≤400% FPL → 100% discount was read 2026-09-23 but not visible in main text today)", expect_text: ["571-472-5880"]}}
- {id: fairfax_chcn, name: "Fairfax County Community Health Care Network (CHCN)", org_type: government, cost: sliding, priority: 70,
   url: "https://www.fairfaxcounty.gov/health/community-health-care-network", phone: "+17032373446", languages: [en, es, interpreters_200+],
   serves: {scope: county, states: [VA], counties: [Fairfax, Fairfax City, Falls Church City], zip3: ["220", "221", "201"]},
   tags: [primary_care_uninsured], status_note_key: waitlist,
   what_it_does: {en: "Primary care for uninsured, lower-income residents of Fairfax County, Fairfax City and Falls Church. Three centers: Merrifield 703-237-3446, North County (Reston) 703-689-2180, South County (Alexandria area) 703-704-5333. There is a waitlist right now."},
   eligibility_plain: {en: "Uninsured residents of Fairfax County, Fairfax City or Falls Church with income at or below 200% of the poverty level and 9 months of local residency."},
   prepare_checklist_keys: [bring_pay_stubs, bring_proof_income, bring_tax_return, bring_household_ids, bring_proof_va_address],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §2; fetched 2026-09-27 (waitlist, 200% FPL, 9 months, three phones confirmed)", notes: "Interpreter access via county language line (Fairfax County practice) — confirm on re-verification.", expect_text: ["703-237-3446", "waitlist"]}}
- {id: neighborhood_health, name: "Neighborhood Health", org_type: fqhc, cost: sliding, priority: 80,
   url: "https://www.neighborhoodhealthva.org/", phone: "+17035355568", languages: [en, es, interpreters_200+],
   serves: {scope: county, states: [VA], counties: [Alexandria City, Arlington, Fairfax], zip3: ["222", "223", "220", "221"]},
   tags: [primary_care_uninsured, prescription_help, vaccine_records], status_note_key: hhs_funded_health,
   what_it_does: {en: "Community health center in Alexandria, Arlington and Fairfax: family medicine, children, pregnancy care, dental, mental health and pharmacy. Fees slide with income; no one is turned away for lack of insurance."},
   eligibility_plain: {en: "Anyone living in the service area. Fees depend on family income."},
   prepare_checklist_keys: [bring_proof_income, bring_photo_id, bring_proof_address],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §2; fetched 2026-09-27 (phone, service areas, sliding fee confirmed)", notes: "FQHC → HHS-funded (interpreter line applies). Interpreter availability is FQHC practice; confirm on re-verification.", expect_text: ["535-5568"]}}
- {id: lajc, name: "Legal Aid Justice Center", org_type: nonprofit, cost: free, priority: 75,
   url: "https://www.justice4all.org/", languages: [en, es],
   serves: {scope: state, states: [VA]},
   tags: [eviction, workers_rights, immigration_legal_help, medical_bill, benefits_navigation, wage_theft],
   what_it_does: {en: "Free legal help in Virginia on immigration, housing and eviction, workplace problems, medical debt, public benefits and schools. Offices in Northern Virginia (Falls Church), Charlottesville, Richmond and Petersburg. Use the 'Get Help' form on the site."},
   eligibility_plain: {en: "Low-income Virginians. LAJC serves immigrants regardless of status."},
   prepare_checklist_keys: [bring_notice, bring_proof_income],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §2; fetched 2026-09-27 (offices + practice areas confirmed)", notes: "No public phone on the fetched page → phone null; intake is via the Get Help portal. org_type kept 'nonprofit' (LSC funding status not asserted)."}}
- {id: ayuda, name: "Ayuda", org_type: nonprofit, cost: free, priority: 80,
   url: "https://www.ayuda.com/", phone: "+17034447009", languages: [en, es, interpreters_200+],
   serves: {scope: state, states: [VA, DC, MD]},
   tags: [immigration_legal_help, domestic_violence, language_access],
   what_it_does: {en: "Immigration and family/domestic-violence legal help, social services and interpreter help for low-income immigrants in DC, Maryland and Virginia. Virginia (Fairfax) 703-444-7009; DC 202-387-4848; Maryland 240-594-0600."},
   eligibility_plain: {en: "Low-income immigrants in DC, Maryland and Virginia."},
   prepare_checklist_keys: [bring_notice, bring_a_number, bring_proof_income],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §2; fetched 2026-09-27 (three office numbers confirmed)", notes: "Ayuda runs a language-access program (interpreters); scope 'state' over three jurisdictions.", expect_text: ["703-444-7009"]}}
- {id: just_neighbors, name: "Just Neighbors", org_type: nonprofit, cost: free, priority: 75,
   url: "https://www.justneighbors.org/", phone: "+17039791240", languages: [en, es],
   serves: {scope: state, states: [VA, DC, MD]},
   tags: [immigration_legal_help, daca_tps, domestic_violence],
   what_it_does: {en: "Immigration legal services (family cases, DACA/TPS, protections for abuse survivors) for low-income immigrants in DC, Maryland and Virginia. 703-979-1240 or 703-991-4576; info@justneighbors.org."},
   eligibility_plain: {en: "Low-income immigrants in DC, Maryland and Virginia."},
   prepare_checklist_keys: [bring_notice, bring_a_number, bring_proof_income],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §2; fetched 2026-09-27 (both numbers + email confirmed)", expect_text: ["703-979-1240"]}}
- {id: tahirih, name: "Tahirih Justice Center", org_type: nonprofit, cost: free, priority: 60,
   url: "https://www.tahirih.org/", phone: "+18665750071", languages: [en, es, interpreters_200+],
   serves: {scope: national},
   tags: [domestic_violence, trafficking, immigration_legal_help],
   what_it_does: {en: "Free legal and social services for immigrant survivors of gender-based violence (abuse, forced marriage, trafficking). Offices in Falls Church VA, Baltimore, Atlanta, Houston and the San Francisco Bay Area. 866-575-0071."},
   eligibility_plain: {en: "Immigrant survivors of gender-based violence, any status."},
   prepare_checklist_keys: [bring_notice],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §2; fetched 2026-09-27 (phone + 5 offices confirmed)", notes: "National scope because intake is by phone; the Falls Church office serves NoVA. Interpreter access is Tahirih's stated practice; confirm on re-verification.", expect_text: ["575-0071"]}}
- {id: cafb, name: "Capital Area Food Bank: Get Help (Hunger Lifeline)", org_type: food_bank, cost: free, priority: 75,
   url: "https://www.capitalareafoodbank.org/find-food-assistance/", phone: "+12026449807", languages: [en, es],
   serves: {scope: county, states: [VA, DC, MD],
            counties: [Fairfax, Arlington, Alexandria City, Fairfax City, Falls Church City, Loudoun, Prince William, Manassas City, Manassas Park City, District of Columbia, Montgomery, "Prince George's"],
            zip3: ["200", "201", "202", "203", "204", "205", "207", "208", "209", "220", "221", "222", "223"]},
   tags: [food],
   what_it_does: {en: "Find a free food pantry near you in DC, Maryland or Northern Virginia with the address map, or call the Hunger Lifeline 202-644-9807. No ID requirement is stated."},
   eligibility_plain: {en: "Anyone who needs food in the DC area."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §2; fetched 2026-09-27 (Hunger Lifeline + DC/MD/VA service area confirmed)", expect_text: ["644-9807"]}}
- {id: nvfs, name: "Northern Virginia Family Service (NVFS)", org_type: nonprofit, cost: free, priority: 70,
   url: "https://www.nvfs.org/", alt_urls: ["https://www.nvfs.org/find-support"], phone: "+15717482500", languages: [en, es, ar, fr, am, vi],
   serves: {scope: county, states: [VA],
            counties: [Fairfax, Prince William, Loudoun, Arlington, Alexandria City, Fairfax City, Falls Church City, Manassas City, Manassas Park City],
            zip3: ["201", "220", "221", "222", "223"]},
   tags: [immigration_legal_help, refugee_services, food, rent_assistance, benefits_navigation],
   what_it_does: {en: "Immigration legal services, health access, housing and food help (Hunger Resource Center), job training and mental health for Northern Virginia families. Intake 571-748-2500 or info@nvfs.org."},
   eligibility_plain: {en: "Northern Virginia residents; each program has its own rules."},
   prepare_checklist_keys: [bring_notice, bring_photo_id],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §2; both URLs fetched 2026-09-27 (phone, 6 site languages, program list confirmed)", expect_text: ["748.2500"]}}
- {id: fairfax_csp, name: "Fairfax County Coordinated Services Planning (CSP)", org_type: government, cost: free, priority: 85,
   url: "https://www.fairfaxcounty.gov/neighborhood-community-services/coordinated-services-planning", phone: "+17032220880", tty: "711", hours: "Mon–Fri 8:00–16:30",
   languages: [en, es, am, yue, prs, tl, ht, hi, it, kn, ko, ps, pa, so, ta, ur, interpreters_200+],
   serves: {scope: county, states: [VA], counties: [Fairfax, Fairfax City, Falls Church City], zip3: ["220", "221", "201"]},
   tags: [rent_assistance, utility_shutoff, food, benefits_navigation],
   what_it_does: {en: "One phone call for emergency help with rent, utilities, food and medical needs in Fairfax County, and for signing up for county programs. 703-222-0880 (TTY 711), Mon–Fri 8:00–4:30, with interpreters."},
   eligibility_plain: {en: "Residents of Fairfax County, Fairfax City and Falls Church."},
   prepare_checklist_keys: [bring_notice, bring_household_ids, bring_proof_income],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §2; fetched 2026-09-27 (phone, TTY, hours, 15+ languages incl. Dari and Pashto confirmed)", expect_text: ["703-222-0880"]}}
- {id: va_courts_landlord_tenant, name: "Virginia Courts Self-Help: Landlord–Tenant (eviction cases)", org_type: court, cost: free, priority: 70,
   url: "https://selfhelp.vacourts.gov/page/10/landlord-tenant", languages: [en, es],
   serves: {scope: state, states: [VA]},
   tags: [eviction], warnings: [court_date_is_the_deadline],
   what_it_does: {en: "Official Virginia court information about eviction (unlawful detainer) cases, which are heard in General District Court. Forms and what to expect on your court date."},
   eligibility_plain: {en: "Tenants and landlords in Virginia."},
   prepare_checklist_keys: [bring_the_summons, bring_lease, bring_proof_rent_utilities],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §2; fetched 2026-09-27 ('unlawful detainer … General District Court' confirmed)", notes: "Spanish availability = vacourts self-help site language toggle; confirm on re-verification."}}
- {id: va_code_pay_or_quit, name: "Virginia Code § 55.1-1245 (notice before eviction for unpaid rent)", org_type: government, cost: free, priority: 30,
   url: "https://law.lis.virginia.gov/vacode/title55.1/chapter12/section55.1-1245/", languages: [en],
   serves: {scope: state, states: [VA]},
   tags: [eviction], warnings: [not_a_court_order, law_changes_2027],
   what_it_does: {en: "The Virginia law that says a landlord must give 14 days' written notice to pay before ending a lease for unpaid rent (30 days for other problems, with 21 days to fix them). A notice is not an eviction; only a court can order one."},
   eligibility_plain: {en: "Tenants in Virginia."},
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §2; fetched 2026-09-27 (subsection F: 14 days confirmed)", notes: "Never used for date math (D-11 forbids seeded eviction periods); informational link only. Amendments effective 2027-07-01 and 2028."}}
- {id: fairfax_sheriff_eviction, name: "Fairfax County Sheriff: Eviction Process", org_type: government, cost: free, priority: 50,
   url: "https://www.fairfaxcounty.gov/sheriff/eviction-process", languages: [en],
   serves: {scope: county, states: [VA], counties: [Fairfax, Fairfax City, Falls Church City], zip3: ["220", "221", "201"]},
   tags: [eviction], warnings: [court_date_is_the_deadline],
   what_it_does: {en: "Step by step, what happens in a Fairfax County eviction after the court date: a 10-day appeal period, then a writ, then at least 72 hours' notice from the Sheriff before anyone is moved out."},
   eligibility_plain: {en: "Tenants in Fairfax County with an eviction case."},
   prepare_checklist_keys: [bring_the_summons],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §2; fetched 2026-09-27 (summons → judgment → 10-day appeal → writ → 72 h confirmed)"}}
- {id: va_eviction_helpline, name: "Virginia Eviction Defense Center (Virginia Poverty Law Center)", org_type: nonprofit, cost: free, priority: 65,
   url: "https://fightmyeviction.org/", languages: [en, es],
   serves: {scope: state, states: [VA]},
   tags: [eviction, housing_counseling], status_note_key: manual_verify,
   what_it_does: {en: "Free legal information and a helpline for Virginia tenants facing eviction, run by the Virginia Poverty Law Center. Find the helpline number on the site."},
   eligibility_plain: {en: "Tenants in Virginia."},
   prepare_checklist_keys: [bring_the_summons, bring_lease],
   verified_on: 2026-09-27, verification_method: fetched, link_health: ok,
   x_meta: {source: "resources.md §2 (site 'likely' 2026-09-23; ARCHITECTURE names it with 1-833-NOEVICT manual_verify); fetched 2026-09-27: page loads (VPLC, Richmond), helpline number NOT printed on the page", notes: "1-833-NOEVICT (= +18336638428) comes from search only. A human must call it, then set phone and clear status_note_key. Spanish per VPLC practice; confirm."}}
```

Entry count: 42 + 13 + 10 + 6 + 4 + 12 + 14 = **101** (`/health.resources_loaded = 101`).

---

## 12. Hotlines and anti-fraud entries — special handling

### 12.1 Crisis hotlines (`988`, `dv_hotline`, `poison`, `trafficking`)

| Rule | Detail |
|---|---|
| Two homes, one truth | The numbers live in fixed copy (`en.json` keys `emergency.911`, `emergency.988`, `emergency.poison`, `emergency.dv` — PRODUCT_SPEC S19 / Appendix A, WP0) **and** in `national_crisis.yaml`. `tests/unit/test_loader.py::test_emergency_numbers_match_fixed_copy` asserts the digits in the DB entries equal the digits in those `en.json` strings, so a future number change cannot drift. |
| Forced first | `emergency=true` → forced block (§6.6); the analyze pipeline also renders the fixed emergency card *before* any resource (D-14). |
| Rendering | Client shows `phone` as a `tel:` button (56 pt), `text_line` as an `sms:` button where the platform supports it (`988` → `sms:988`, DV → `sms:88788?body=START`, trafficking → `sms:233733`), `tty` as a secondary line. Web shows the numbers as text plus `tel:` links. |
| Language | `interpreters_200+` is stated only for 988 and the DV hotline (their pages/research state it); Poison Control lists `[en]` (interpreter access not printed on its page) and trafficking `[en, es]`. |
| Quick sheet | These four ids are always offered in the quick-sheet resource picker when `safety.emergency` was true, and pass the §7 re-validation because `phone`/`url` match the DB. |
| Never by model | If model output contains any of these digits, `contacts_filter.py` still strips them (D-10) — the card is fixed copy, the Help tab uses the DB. |

### 12.2 Anti-fraud entries (`scam_report` tag)

Seeded: `dhs_oig` (phone for the D-13 card), `ftc_reportfraud` (URL for the D-13 card), `uscis_scams`, `ftc_immigrant_scams` (14 languages, 877-382-4357), `ftc_gift_card_scams`, `ftc_job_scams`, `irs_scams`, `ssa_scams`, `uscis_find_legal`, `eoir_roster`, `uscis_forms_free`.

| Rule | Detail |
|---|---|
| D-13 fixed card | Copy is fixed: "Scam risk: likely — ICE, USCIS, SSA and the IRS never demand payment by phone, gift card, wire, or app. Do not pay. Report it:" followed by `dhs_oig.phone` and `ftc_reportfraud.url` read from the repo by `well_known_ids`. If either id were missing the loader fails boot (§8.3). |
| Forced first | `scam_risk == likely` → `scam_report` entries first (§6.6); `possible` → no forcing, but `national_fallbacks` gains `ftc_reportfraud`, `dhs_oig`. |
| Troubleshoot | `POST /v1/troubleshoot` with `mode=scam_check` uses the same tag; the client calls `/v1/resources/match` with `tags=[scam_report]`, `scam_risk` from the result. |
| Sender-specific | `document_type` pins add the matching agency's scam page (`irs_notice` → `irs_scams`, `ssa_letter` → `ssa_scams`); the matcher's tag score puts `uscis_scams` first for immigration papers via `red_flags[kind ∈ {scam_payment_method, impersonation, notario}]` → `scam_report` + the paper's category tag. |
| Never paid directories | `aila.never_show_with_tags = [scam_report]` so a "find a lawyer" tile during a scam warning never routes to fee-charging listings. |
| Verify-a-helper flow | `notario` red flag → `eoir_roster` + `uscis_find_legal` (checklist `bring_name_of_helper`). |

---

## 13. Verification log (2026-09-27 fetch pass)

127 URLs (every `url` and `alt_urls` item in §11) were fetched today with the WebFetch tool. No URL returned 404/410 or failed DNS; nothing was dropped for a dead link.

| Outcome | Count | URLs |
|---|---|---|
| HTTP 200, content read and consistent with `docs/research/resources.md` | 110 | all others |
| HTTP 403 to the fetcher (site blocks non-browser clients; kept as `unknown_403` / `browser` / `verified_on 2026-09-23`) | 13 | acf.gov/orr, acf.gov/orr/…/state-contacts, acf.gov/orr/fact-sheet/…afghan…, acf.gov/ocs/programs/liheap, hhs.gov/…/limited-english-proficiency, fna.usda.gov/snap/state-directory, fna.usda.gov/snap/recipient/eligibility, fna.usda.gov/wic, fna.usda.gov/wic/eligibility, fna.usda.gov/nslp/household, ssa.gov/apply/appeal-decision-we-made, ssa.gov/scam/, sites.ed.gov/idea/ |
| HTTP 200 but JavaScript shell / redirect page with no readable list (kept as `js_rendered` / `browser`) | 4 | findahealthcenter.hrsa.gov, reportfraud.ftc.gov, hud.gov/findacounselor, hud.gov/program_offices/public_indian_housing/pha/contacts |

Content notes captured during the pass (all reflected in `x_meta`): medicaid.gov, insurekidsnow.gov and cdc.gov served full content today although the research pass saw 403s (their `link_health` is `ok`); Medicare Part D page text read today shows the 60-day Level 2 window (Level 1 window to be re-read by a human; warning `medicare_windows_changed` attached); CMS Medical Bill Rights page confirms the $400 threshold but not the 120-day window in visible text (the deadline rule keeps its own source); Inova's ≤ 400 % FPL tier was not in today's main text (eligibility copy softened); DOL WHD page text did not show the "status is not a barrier" sentence today (eligibility kept neutral); fightmyeviction.org loads (VPLC Eviction Defense Center, Richmond) but does not print 1-833-NOEVICT (phone withheld, `manual_verify`); LSC Eviction Laws Database states its data reflect laws effective January 1, 2021 (staff reference only, warning attached); USA.gov Benefit Finder is a category-selection landing page rather than a questionnaire (copy adjusted).

**Correction 2026-09-29 (DECISIONS §14 CL-055, orchestrator → WP3).** `healthcare_gov.phone` read `+18003185596` while its own `what_it_does` text and healthcare.gov/contact-us say 1-800-318-2596; the seed (§11.3) and `national_health.yaml` now carry `phone: "+18003182596"` and the TTY `+18558894325` (re-verified on healthcare.gov/contact-us 2026-09-29). A scan of all 101 entries found no other phone/text mismatch.

Re-verification cadence: every 90 days per region, and before any store submission; `scripts/check_links.py --freshness` enforces 120 days (90 for `manual_verify`).

---

## 14. Deferred candidates (not seeded, and why)

| Candidate | Research confidence | Why not seeded / what would admit it |
|---|---|---|
| BIA page `justice.gov/eoir/board-of-immigration-appeals` | likely | Page loads but the 30-day rule could not be read there; the rule lives in `deadlines.yaml` as `likely`. Admit as a `court_notice` explainer after a browser read. |
| USCIS scams hub `uscis.gov/scams-fraud-misconduct` | likely | `uscis_scams` (Common Scams) covers it. |
| NeedyMeds, GoodRx, AmericasMedicines.com | likely (JS/bot-blocked) | Would fill the `prescription_help` cost gap; admit after a browser read with `js_rendered`. Until then `prescription_help` is fallback-only (health centers + interpreter rights). |
| FNA income eligibility guidelines; LIHEAP local office search tool; OSHA file-complaint page; IRS W-7/W-2/1099-NEC pages; USCIS I-9 Central; USCIS EAD-receipt I-9 news item | likely (HTTP 200 only) | Sub-pages whose content was not read; parents are seeded. Admit as `alt_urls` after a content read. |
| State Department Afghan SIV page | unverified (Cloudflare) | Cannot be auto-verified; SIV questions route to `uscis_afghan` (D-11/resources.md warning). Store as `manual_verify` only if a human confirms quarterly. |
| HealthCare.gov "lawfully present immigrants" page | verified but stale for H.R.1 | Would mislead refugees/asylees/TPS holders about 2027 subsidies; excluded on purpose. |
| healthinsurance.org EOB glossary | verified (commercial site) | "THIS IS NOT A BILL" is fixed copy in `DOCUMENT_TAXONOMY.md`; no commercial explainers in v1. |
| 45 CFR 1626, 42 CFR 431.221, USCIS Policy Manual Vol. 1 Pt. E Ch. 6, CBPP H.R.1 explainer, DOJ LEP notice | verified | Rule/source citations, not help resources: referenced from `deadlines.yaml`, `x_meta.source` and `COMPLIANCE_PRIVACY.md`. |
| USCIS USRAP page, Refugee Council USA, USCIS 10 Steps to Naturalization | verified | Not actionable for a user with a paper (policy/coalition/duplicate). |
| Virginia Eviction Legal Helpline number 1-833-NOEVICT | search-only | Entry `va_eviction_helpline` is seeded without the phone; a human call promotes it. |
| Any resource outside Virginia/DC-metro | — | Open question Q5 (pilot geography). New regions: copy `regional/va_nova.yaml`, keep ids unique, run `check_links.py`. |

Known routing gaps (fallback-only): `traffic_court` (no verified national resource; pins `immlawhelp` + `lawhelp` and the fixed "talk to an immigration lawyer before pleading" copy), `prescription_help` cost assistance, an EOB explainer, statewide legal aid outside Virginia.

---

## 15. Conflicts, interpretations and cross-WP requests (for DECISIONS §14 change log)

1. **Single-slot `status_note_key` vs. D-18 "tagged `hhs_funded_health`".** `Resource.status_note_key` is one value; Inova needs `residency_required` and is also HHS-funded. Resolved without a schema change by the derivation rule in §3.3 (`status_note_key == hhs_funded_health or org_type ∈ {fqhc, hospital_program}`); WP0 may later add a boolean if preferred.
2. **`Resource` defaults.** Seed YAML omits optional fields; the loader applies defaults (§2.1). Request to WP0: declare the same defaults on the Pydantic model so hand-written JSON in tests matches.
3. **Pack keys.** Request to WP0 (DECISIONS §14 CL-005, open): add `prepare.*` (30), `why.*` (59), `notes.*` (6), `status_note.*` (7), `warn.*` (21) to `en.json` with the English in §3.3/§4; the loader test cross-checks. PRODUCT_SPEC Appendix A now points at these sections as the copy source (the earlier `eligibility_note.*` / unprefixed `bring_*` names there were replaced).
4. **Mobile offline subset.** *Resolved:* ARCHITECTURE §3 now lists `assets/resources/national_fallbacks.json` (WP7-generated by `sync_to_mobile.py`; CL-004).
5. **`data/rules/prepare.yaml` ownership.** *Resolved:* WP3-owned (ARCHITECTURE §4, BUILD_PLAN §3; CL-003).
6. **API example scores.** *Resolved:* `API_CONTRACT.md` §3.8 now says scores are illustrative/order-only and its example values follow §6.11 example A.
7. **Phone format.** *Resolved:* `API_CONTRACT.md` §3.8 states E.164 **or** N11/`988`/`711` with the §2.2 regex.
8. **Freshness.** *Resolved:* ARCHITECTURE §2 `loader.py` line now says boot warning + CI failure (`check_links.py --freshness`), > 365 days excluded (§8.1).
9. **LSC Eviction Laws Database** describes law as of 2021-01-01 (read today); it stays a staff reference with a warning and is never used for date math (consistent with D-11).
10. **Two tags are fallback-only** (`traffic_court`, `prescription_help`) — the boot check allow-lists them (§8.3) instead of failing.
11. **`211` hours.** *Resolved:* the contract example now reads "Varies by area; many lines are 24/7" like the seed.
12. **Tag vocabulary gaps** noticed while seeding (not changed here; for WP0 to consider in a later contract bump): no general `uscis_notice` tag (solved with `doc_type_pins`), no `hospital_program`-style tag for FQHC/hospital distinctions (solved via `org_type`).
13. **Unbounded `institutions_as_written` (Phase 2B hardening, 2026-09-30).** `ResourceMatchRequest.institutions_as_written` has no per-item length bound in the contract, and the matcher used to re-normalize every request string for every resource and run `SequenceMatcher` on it on the event loop: one anonymous 1.9 MB request stalled the single-worker API for ~15 s (a 20 MB one for ~2.3 min). *Resolved in the matcher* (§6.3): items are cut to 200 characters and normalized once per request (a 20 MB body now answers in ~15 ms). The route stays un-rate-limited as API_CONTRACT §3 lists it (tier none, auth none): the D-08 buckets are sized for model calls and would spend a user's analyze quota on every Help screen. Request to WP0: add a per-item `max_length` (e.g. 200) to the contract model in a later contract bump.
14. **Duplicate forced / tag chips (Phase 2B hardening, 2026-09-30).** §6.6 prepends `why.report_scam` / `why.crisis_line`, and §6.8 then added `why.for_scam_report` / `why.for_crisis` for the same shared tag — identical copy, so every scam-report card said "To report a scam" twice. *Resolved* per §6.8 above. The mobile `ResourceCard` also keys chips by their text (`key={w}`); that is a WP5 fix (key plus index).
