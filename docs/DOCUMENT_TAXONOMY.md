# ProxyHealth AI — Document Taxonomy (WP2-owned)

Status: **implementation-ready**. Conforms to `docs/DECISIONS.md` (D-09…D-20), `docs/API_CONTRACT.md` §1 enums and `docs/ARCHITECTURE.md` §2 (file tree). When this file and those three disagree, the backbone wins and the disagreement is filed in `docs/DECISIONS.md` §14 "Change log". Research basis: `docs/research/resources.md` §3–4 (verified 2026-09-23) and `docs/research/compliance.md` §3, §7. Today: 2026-09-27. `taxonomy_version = "2026-09-27"` (served in `GET /v1/config.taxonomy_version`).

This document is the single reference for **what each kind of paper is, what to pull out of it, how urgent it is, what usually goes wrong, how to explain it at a 4th-grade level, what the app refuses to say, and which vetted resources it points to.** Coding agents build the following from it without asking questions:

| Consumer | Path (ARCHITECTURE §2) | What it takes from this file |
|---|---|---|
| Analysis prompt | `ai/prompts/analyze.md`, `explain.md` via `prompt_loader.py` `{taxonomy_ids}` | §2 master table (type ids), §3 recognition cues, §4 per-type "what to extract" |
| Urgency engine | `analysis/urgency.py` | §5.2 roles that drive urgency, doc-type floors, `verify_resource_id` selection |
| Deadline rules | `data/rules/deadlines.yaml`, `analysis/deadline_rules.py` | §5.3 rule → doc-type applicability, anchors, patterns |
| Fixed notices | `data/rules/fixed_notices.yaml`, `analysis/fixed_notices.py` | §7 fixed red-flag cards with exact copy |
| Clerk fallback lines | `data/rules/clerk_needs.yaml`, `analysis/clerk.py` | §4 per-type "Clerk need line (fallback)" |
| Prepare checklists | `data/rules/prepare.yaml` (WP3-owned; seed in RESOURCE_DB §4.8), `resources/checklist.py` | §4 per-type "Prepare checklist keys" are WP2's recommendations to WP3; keys must exist in `data/resources/_meta.yaml.checklist` |
| Scam scorer | `data/safety/scam.yaml`, `analysis/scam.py` | §6 signal list, reason keys, scoring, copy |
| Phrasing lint | `data/safety/phrasing.yaml`, `analysis/phrasing.py` | §8 forbidden phrasings per domain, rewrite templates |
| Tagging | `analysis/tagging.py` | §4 per-type `resource_tags` |
| Disclaimers | `analysis/disclaimers.py` | §2 category → `DisclaimerKind` |
| Mock/fixtures | `data/fixtures/*/manifest.yaml`, `tests/golden/` | §2 fixture column, §4 expected urgency/date kinds |
| Base pack strings | `data/langpacks/en.json` (WP0 adds keys; WP2 requests them in the change log) | every quoted key in §5–§8 |

---

## 1. Conventions

### 1.1 Enums used (from API_CONTRACT §1; never invent a value)

- `DocumentCategory`: `immigration · court · medical · benefits · housing · school · employment · tax · civic · other`
- `DocumentType`: the 51 ids in §2 (exactly the `DocumentType` enum in API_CONTRACT §1; CI asserts the count). `other_notice` = a real notice we cannot fit into a finer type; `unknown` = we cannot tell what the paper is (blurry, fragment, non-document).
- `UrgencyLevel`: `emergency · critical · high · medium · info` (computed in code only, D-12)
- `DemandKind`: `deadline · relative_deadline · amount · document_requested · appointment · action · contact`
- `Demand.role` (string, closed list from API_CONTRACT §3.5): `hearing_date · response_due · payment_due · appointment · notice_date · decision_date · move_date · expiry · other`
- `DateKind`: `stated · estimated · unresolved`; `RuleVerification`: `verified · likely`
- `PlanStepKind`: `call · mail · bring · gather · ask · visit · submit_online · wait · professional · verify`
- `RedFlagKind`: `scam_payment_method · urgency_pressure · impersonation · notario · fee_for_free_form · guaranteed_result · unusual_contact · missing_pages · contradiction · expired_date · jury_citizenship_warning · ead_receipt_not_work_authorization · not_a_court_order · court_date_is_the_deadline · no_fee_waiver · address_change_multi_agency · injection_suspected · other`
- `Severity`: `low · medium · high`; `ScamRisk`: `none · possible · likely`
- `DisclaimerKind` (primary, by category — D-17): `legal_information_only` (immigration, court, civic, employment) · `medical_information_only` (medical) · `benefits_information_only` (benefits) · `housing_information_only` (housing) · `general_information` (school, tax, other)
- `SenderKind`: `federal_agency · state_agency · local_agency · court · hospital_or_clinic · insurer · pharmacy · landlord · school · employer · utility · bank_or_collector · unknown`
- `ResourceTag`: closed vocabulary in API_CONTRACT §1; §4 lists the tags per type. Anything else the model emits is dropped by `tagging.py`.
- `RefusalKind` / `ReferTo` (chat): `none · eligibility · filing_advice · outcome · medical_interpretation · drafting · contact_request · out_of_scope` / `none · lawyer_or_accredited_rep · clinician · housing_counselor · benefits_office · sender`

### 1.2 How to read a §4 entry

Every document type has the same eight blocks:

1. **Recognize by** — form numbers, headings and phrases printed on the paper. The model classifies from these; `document_hint` from the user only breaks ties (§3).
2. **Key fields → Demand** — what to extract, as `DemandKind` + `role`. "Verbatim" means `value_verbatim` must be an exact substring of `source_quote` (D-09). Identifiers (A-number, receipt number, case number, account number) are **not** Demands; they set `entities.has_case_number` / `has_receipt_number` and appear in `original_text` only.
3. **Deadline and urgency** — which roles drive `Urgency`, the doc-type floor, and which `deadlines.yaml` rule ids may apply (only when the paper prints the matching relative phrase **and** a verified anchor exists; D-11). "Printed date only" means no seeded rule applies: a printed date is `stated`, a relative phrase without a rule is `unresolved` and rendered "Ask the sender which date this means."
4. **Common pitfalls** — what people get wrong; each becomes a fixed notice (§7), a glossary term, a plan step or a `questions_to_ask` item.
5. **Plain-language guidance** — the shape of Card 1 / Card 2 / Card 3 at grade ≤ 4, plus the glossary terms the model should define. Card 1 always answers: *what is this paper, who sent it, and is anything cancelled, denied, approved, or only requested*.
6. **The app does / refuses** — the information-not-advice boundary for that type (D-17). Every immigration, court and civic type ends the plan with a `professional` step naming the type's professional (§8.6: "a licensed lawyer or a DOJ-accredited representative" for immigration papers and the immigration-court types `nta`, `hearing_notice`, `ij_decision`, `bia_notice`, `ice_checkin`; "a licensed lawyer" for other court and civic papers — DOJ-accredited representatives practise immigration law only) and never a specific organization (the matcher supplies those).
7. **Resource tags** — `resource_tags` the pipeline sets for the type (model proposal validated against this list; `tagging.py` appends the type's primary tags the model left out, after the model's own). A model `crisis`/`poison` tag stays only when code detected an emergency (D-14); a model `domestic_violence`/`trafficking` tag stays with an emergency **or** when the transcript prints an abuse context (a protective/restraining order, family abuse, VAWA, a U/T visa, I-914/I-918/I-360, trafficking; en and es lists in `tagging.ABUSE_CONTEXT` — a paper in another language keeps the model's tag); `scam_report` stays only when `scam_risk != none` or a verified scam red flag exists (D-13). Any of them stays when it is one of the type's own primary tags — code-authoritative since 2026-10-22.
8. **Clerk need line (fallback)** and **Prepare checklist keys** — the English need line used when the AI line fails lint (D-18; ≤ 200 chars, no contacts), and the `prepare.yaml` keys the matcher adds to every resource shown for this type.

### 1.3 Copy rules that apply to every string in this file

- Grade ≤ 4 English: short sentences, one idea each, everyday words, agency names kept as printed with a short explanation the first time.
- Never dramatize ("You may be deported"), never CAPS-only, never emoji. Never minimize a real date.
- Verbs: "the paper says", "usually", "you can", "ask", "before the date". Never "you should file/appeal/pay/sign", "you qualify", "you will win/lose", "this means you have".
- Contacts appear only when printed on the paper (labelled "from your paper") or from the resource DB. Emergency numbers live only in the fixed emergency card.
- Fixed copy in §6–§7 is reviewed copy and bypasses the phrasing linter; AI-generated text never bypasses it.

---

## 2. Master table

Column key: **Floor** = doc-type urgency floor from D-12 (blank = none; urgency comes only from verified dates). **Roles** = `Demand.role` values that feed `urgency.py` for the type. **Rules** = `deadlines.yaml` ids that may apply (§5.3). **Verify** = `Urgency.verify_resource_id` family (§5.2). **Fixture** = `data/fixtures/<id>` (D-29).

| `document_type` | Category | Typical `sender_kind` | `disclaimer_kind` | Floor | Roles → urgency | Rules | Verify | Primary `resource_tags` | Fixture |
|---|---|---|---|---|---|---|---|---|---|
| `uscis_receipt` | immigration | federal_agency | legal_information_only | — | `expiry` (card validity), `notice_date` (info) | `ar11_10d` | uscis | `immigration_legal_help`, +`work_permit`/`green_card`/`naturalization` by form | `uscis_i797c_receipt_i765` |
| `uscis_rfe` | immigration | federal_agency | legal_information_only | — | `response_due` | `ar11_10d` | uscis | `immigration_legal_help` (+ case tag) | `uscis_rfe_87d` |
| `uscis_noid` | immigration | federal_agency | legal_information_only | **high** | `response_due` | `ar11_10d` | uscis | `immigration_legal_help` | — |
| `uscis_biometrics` | immigration | federal_agency | legal_information_only | — | `appointment` | `ar11_10d` | uscis | `immigration_legal_help` | — |
| `uscis_interview` | immigration | federal_agency | legal_information_only | — | `appointment`, `response_due` (evidence due) | `ar11_10d` | uscis | `immigration_legal_help`, +`asylum`/`naturalization`/`green_card` | — |
| `uscis_approval` | immigration | federal_agency | legal_information_only | — | `expiry` | `ar11_10d` | uscis | `immigration_legal_help` (+ case tag) | — |
| `uscis_denial` | immigration | federal_agency | legal_information_only | — | `response_due` (appeal/motion date if printed), `decision_date` | — (printed date only) | uscis | `immigration_legal_help`, `removal_proceedings` if NTA referenced | — |
| `ead_related` | immigration | federal_agency / employer | legal_information_only | — | `expiry`, `response_due` | `ar11_10d` | uscis | `work_permit`, `immigration_legal_help` | — |
| `green_card_related` | immigration | federal_agency | legal_information_only | — | `expiry`, `response_due` | `ar11_10d` | uscis | `green_card`, `immigration_legal_help` | — |
| `tps_related` | immigration | federal_agency | legal_information_only | — | `response_due` (re-registration window end), `expiry` | `ar11_10d` | uscis | `daca_tps`, `work_permit`, `immigration_legal_help` | — |
| `asylum_fee_notice` | immigration | federal_agency | legal_information_only | — | `payment_due` (critical rule) | `asylum_annual_fee_30d` | uscis | `asylum`, `immigration_legal_help` | — |
| `parole_related` | immigration | federal_agency | legal_information_only | — | `expiry`, `response_due` | `ar11_10d` | uscis | `afghan_specific` (when Afghan), `refugee_services`, `immigration_legal_help` | — |
| `ice_checkin` | immigration | federal_agency | legal_information_only | — | `appointment` (critical rule) | — | sender (printed) | `removal_proceedings`, `immigration_legal_help` | — |
| `nta` | court | court / federal_agency | legal_information_only | **high** | `hearing_date` | `eoir33_5bd` | eoir | `removal_proceedings`, `court_notice`, `change_of_address` | `nta_hearing_date` |
| `hearing_notice` | court | court | legal_information_only | **high** | `hearing_date` | `eoir33_5bd` | eoir | `removal_proceedings`, `court_notice`, `change_of_address` | — |
| `ij_decision` | court | court | legal_information_only | — | `response_due` (appeal), `decision_date` | `bia_appeal_30d`, `in_absentia_rescission_180d`, `eoir33_5bd` | eoir | `removal_proceedings`, `immigration_legal_help` | — |
| `bia_notice` | court | court | legal_information_only | — | `response_due` (brief due), `decision_date` | `eoir33_5bd` | eoir | `removal_proceedings`, `immigration_legal_help` | — |
| `traffic_court` | court | court / local_agency | legal_information_only | — | `hearing_date`, `payment_due` | — | sender (printed) | `traffic_court`, `immigration_legal_help` | `traffic_court_notice` |
| `medical_bill` | medical | hospital_or_clinic / bank_or_collector | medical_information_only | — | `payment_due` | `gfe_dispute_120d` | sender | `medical_bill`, `charity_care` | `inova_final_notice` |
| `eob` | medical | insurer | medical_information_only | — | `response_due` (appeal date if printed) | `aca_internal_appeal_180d` | sender | `insurance_denial` (only when a denial code is present), `medical_bill` | — |
| `insurance_denial` | medical | insurer / state_agency | medical_information_only | — | `response_due` | `aca_internal_appeal_180d`, `aca_external_review_4mo`, `medicare_advantage_65d`, `medicaid_fair_hearing_90d_max` | sender | `insurance_denial`, +`medicare_appeal`/`medicaid_renewal` | `insurance_denial_180d` |
| `prior_auth` | medical | insurer | medical_information_only | — | `expiry`, `response_due` | `aca_internal_appeal_180d` (denials) | sender | `insurance_denial` (denied), `prescription_help` (drug) | — |
| `lab_result` | medical | hospital_or_clinic | medical_information_only | — | `appointment` (follow-up if printed) | — | sender | `lab_results`, `primary_care_uninsured` | — |
| `prescription_label` | medical | pharmacy | medical_information_only | — | `expiry` (discard date), `other` | — | sender | `prescription_help`, `language_access` | `prescription_label` |
| `discharge_instructions` | medical | hospital_or_clinic | medical_information_only | — | `appointment` | — | sender | `primary_care_uninsured`, `language_access`, `medical_bill` | — |
| `vaccine_record` | medical | hospital_or_clinic / school | medical_information_only | — | `response_due` (school deadline if printed) | — | sender | `vaccine_records`, `school_enrollment` | — |
| `appointment_reminder` | medical | hospital_or_clinic | medical_information_only | — | `appointment` | — | sender | `language_access` | — |
| `medicaid_renewal` | benefits | state_agency | benefits_information_only | — | `response_due` | `medicaid_fair_hearing_90d_max` | sender | `medicaid_renewal`, `benefits_navigation` | `medicaid_address_confirmation` |
| `snap_notice` | benefits | state_agency / local_agency | benefits_information_only | — | `appointment` (interview), `response_due` | — | sender | `snap`, `food`, `benefits_navigation` | `snap_interview_notice` |
| `wic_notice` | benefits | state_agency / local_agency | benefits_information_only | — | `appointment`, `response_due` | — | sender | `wic`, `food` | — |
| `ssa_letter` | benefits | federal_agency | benefits_information_only | — | `response_due` | — (printed date only) | sender | `ssa_benefits`, `benefits_navigation` | — |
| `pay_or_quit` | housing | landlord | housing_information_only | **high** (D-12 as revised 2026-09-27) | `response_due` | — (never seeded, D-11) | sender | `eviction`, `housing_counseling`, `rent_assistance` | `va_pay_or_quit_14d` |
| `eviction_summons` | housing | court | housing_information_only | **high** | `hearing_date` | — (never seeded) | sender (court printed) | `eviction`, `housing_counseling` | — |
| `lease` | housing | landlord | housing_information_only | — | `move_date`, `payment_due`, `expiry` | — | sender | `housing_counseling` | `spanish_lease` |
| `rent_increase` | housing | landlord | housing_information_only | — | `move_date` (effective date) | — | sender | `housing_counseling`, `rent_assistance` | — |
| `section8_recert` | housing | local_agency | housing_information_only | — | `response_due`, `appointment` | — | sender | `section8`, `housing_counseling` | — |
| `utility_shutoff` | housing | utility | housing_information_only | **high** | `payment_due` (shutoff date as `response_due`) | — | sender | `utility_shutoff`, `rent_assistance` | — |
| `school_enrollment` | school | school | general_information | — | `response_due`, `appointment` | — | sender | `school_enrollment`, `homeless_students` | — |
| `immunization_notice` | school | school / local_agency | general_information | — | `response_due` | — | sender | `vaccine_records`, `school_enrollment` | `school_immunization_notice` |
| `iep_504_notice` | school | school | general_information | — | `appointment`, `response_due` | — | sender | `special_education` | — |
| `school_meals` | school | school | general_information | — | `response_due` | — | sender | `school_meals`, `food` | — |
| `report_card` | school | school | general_information | — | — | — | sender | `language_access` | — |
| `w2_1099` | employment | employer | legal_information_only | — | — (info) | — | sender | `tax_notice`, `itin` (when no SSN shown) | `w2_form` |
| `i9` | employment | employer | legal_information_only | — | `response_due` (re-verification date), `expiry` | — | sender | `work_permit`, `workers_rights` | — |
| `offer_letter` | employment | employer | legal_information_only | — | `response_due`, `other` (start date) | — | sender | `workers_rights` | — |
| `pay_stub` | employment | employer | legal_information_only | — | — | `eeoc_180_300d`, `osha_retaliation_30d` (only via printed phrase) | sender | `wage_theft`, `workers_rights` | — |
| `irs_notice` | tax | federal_agency | general_information | — | `response_due`, `payment_due` | — (printed date only) | sender | `tax_notice` | `irs_cp_notice` |
| `itin` | tax | federal_agency | general_information | — | `response_due`, `expiry` | — | sender | `itin`, `tax_notice` | — |
| `jury_summons` | civic | court | legal_information_only | — | `response_due`, `appointment` (report date) | — | sender | `jury_summons` | `jury_summons` |
| `other_notice` | any | any | by category | — | any printed | `eeoc_180_300d`, `osha_retaliation_30d` (employment only) | sender | by category (§4.10) | `scam_gift_card_letter` |
| `unknown` | other | unknown | general_information | — | none | — | — | none (Help tiles only) | `blurry_unreadable_page` |

"uscis" verify = the USCIS Contact Center resource; "eoir" = the EOIR Automated Case Information resource (ACIS / hotline); "sender" = the phone printed on the paper (the banner reads "Call the number on your paper to confirm this date") with `verify_resource_id = null`. Resource **ids** are defined in `docs/RESOURCE_DB.md` (WP3); this file names them only where D-12 does.

---

## 3. Classification rules (`document_type`, `category`, `sender_kind`)

1. **Form number beats heading beats sender.** A printed form number (I-797E, I-862, EOIR-33, N-445, CP2000, W-2) decides the type. If none, the largest heading ("Request for Evidence", "Notice to Appear", "Explanation of Benefits", "Unlawful Detainer", "Disconnection Notice") decides. Sender alone never decides (USCIS sends receipts, RFEs and appointments on the same I-797C letterhead).
2. **I-797C is not one type.** Read the first bold line: "Receipt Notice" → `uscis_receipt`; "ASC Appointment Notice"/"Biometrics" → `uscis_biometrics`; "Interview Notice"/"Request for Applicant to Appear" → `uscis_interview`; "Rejection Notice" → `uscis_denial` with `document_type_confidence=medium`; "Transfer Notice" → `uscis_receipt` with glossary term "transfer".
3. **Denial vs NOID vs RFE.** "Request for Evidence" → `uscis_rfe`; "Notice of Intent to Deny" → `uscis_noid`; "Decision"/"Denial"/"Your application has been denied" → `uscis_denial`. Never merge them; urgency floors differ.
4. **Court vs immigration.** Papers from an immigration court (EOIR, "Executive Office for Immigration Review", "Immigration Judge", "Board of Immigration Appeals") are `court` category even when DHS/ICE is the issuer of the NTA. Papers from USCIS are `immigration`. ICE check-in/release papers are `immigration` (`ice_checkin`).
5. **Bill vs EOB vs denial.** "THIS IS NOT A BILL" or "Explanation of Benefits" → `eob`, even if a "patient responsibility" amount is printed. "Amount due" + "pay by" + a provider or collector sender → `medical_bill`. A letter whose subject is a denied claim, service or drug with appeal instructions → `insurance_denial` (from an insurer) or `insurance_denial` with `sender_kind=state_agency` (Medicaid managed-care or state notice of adverse action). "Prior authorization"/"pre-authorization"/"coverage determination" for a future service → `prior_auth`.
6. **Benefits letters.** Medicaid/CHIP renewal, redetermination, "confirm your address", "return this form to keep your coverage" → `medicaid_renewal`. Any Medicaid *termination/denial with hearing rights* → `insurance_denial` with `sender_kind=state_agency` and tag `medicaid_renewal` (so the fair-hearing rule can apply). SNAP/"food assistance"/EBT interview or verification → `snap_notice`. WIC → `wic_notice`. Social Security/SSI/SSDI award, denial, overpayment, redetermination, benefit verification → `ssa_letter`.
7. **Housing.** From a landlord/property manager: "pay or quit", "notice to pay", "notice to cure", "notice to vacate", "termination of tenancy" → `pay_or_quit`; a lease or lease renewal → `lease`; "rent will increase" → `rent_increase`. From a court: "Summons", "Unlawful Detainer", "Eviction", "Complaint for Possession" → `eviction_summons`. From a housing authority: "annual reexamination", "recertification", "HCV", "Section 8" → `section8_recert`. From a utility: "disconnect", "shut-off", "termination of service" → `utility_shutoff`.
8. **School.** Enrollment/registration packets → `school_enrollment`; vaccine/immunization compliance or exclusion → `immunization_notice`; IEP, 504, "eligibility meeting", "prior written notice", "procedural safeguards" → `iep_504_notice`; free/reduced meal application or direct-certification letter → `school_meals`; grades/progress → `report_card`.
9. **Employment and tax.** W-2, 1099-NEC/MISC/K → `w2_1099` (category `employment`); Form I-9 or "re-verification of work authorization" → `i9`; offer/hiring letter → `offer_letter`; pay stub/earnings statement → `pay_stub`. IRS letters with a CP/LTR number top-right → `irs_notice`; ITIN assignment, renewal or W-7 rejection (CP565/CP566/CP567) → `itin`.
10. **Civic and traffic.** Juror qualification questionnaire or jury summons → `jury_summons`; traffic citation, court reminder, "failure to appear", DMV suspension notice → `traffic_court`.
11. **`other_notice` vs `unknown`.** A readable official-looking paper that fits no type → `other_notice` with the best `category` (e.g. a scam letter impersonating USCIS is `other_notice` / `immigration`). If legibility is `poor`, fewer than two lines are readable, or the image is not a document → `unknown`, `quality.readable=false`, and the client offers a re-scan (no quota spent again automatically).
12. **`document_hint`.** The user's hint is a tie-breaker only. If the paper's form number contradicts the hint, the paper wins and `warnings` stays empty (no "you were wrong" copy). If the paper is ambiguous and the hint matches one candidate, use it and set `document_type_confidence=medium`.
13. **Multiple documents in one upload.** Classify by the first page's dominant document; if a later page clearly belongs to a different paper (different sender letterhead and subject), the model adds a red flag `kind=other` whose `text` is exactly `[multiple_documents]` with the second letterhead as `source_quote` (`RedFlagOut` has no `fixed_copy_key`, so this sentinel is the channel — AI_PROMPTS §4.3) and takes no facts from that page; `analysis/fixed_notices.py` swaps in the fixed copy key `fixed.multiple_documents` ("These pages look like two different papers. I explained the first one. Scan the other one on its own." — same `fixed.*` prefix as every other `fixed_copy_key`, PRODUCT_SPEC Appendix A; §7.1).
14. **Language of the paper.** `detected_language` is the paper's language; when it differs from `target_language` and from `en`, set `warnings: [document_language_differs]` and the client shows "Your paper is in {Language}; I explained it in {Target}."
15. **`sender_as_written`** is copied exactly from the letterhead or signature block; never normalized ("Virginia Department of Medical Assistance Services", not "Virginia Medicaid"). If no sender is printed, `null` and `sender_kind=unknown` (a red flag `unusual_contact` if the paper demands money or data).
16. **Code check (`analysis/classify.py`, code-authoritative since 2026-10-22).** The model classifies; code then applies rules 1, 2 and 9 to the transcript. A **form label** is a page-1 header line (≤ 10 words, in one of the first three blocks of page 1 or in a block whose top edge is in the top quarter of the page) that *is* a label: it starts with the form number, alone or after "Form"/"Notice"/"Letter" ("Form I-862", "I-797C, Notice of Action", "Notice CP14"), ends without sentence punctuation and holds no sentence word ("you", "your", "bring", "send", "complete", "must", "if" …) — "Send proof of income, such as your W-2" or "On day one, complete Form I-9." mentions a form and labels nothing. Label → type: I-862 → `nta`; I-797A/I-797B → `uscis_approval`; N-445 → `uscis_interview`; I-220A/I-220B → `ice_checkin`; W-2, 1099-NEC/MISC/K → `w2_1099`; Form I-9 → `i9`; W-7, CP565/CP566/CP567 → `itin`; any other CP/LTR number → `irs_notice` when "Internal Revenue Service" is printed; I-797C → by its page-1 first-line heading (rule 2); I-797E → by its heading ("Request for Evidence" → `uscis_rfe`, "Notice of Intent to Deny" → `uscis_noid`; with neither, `uscis_rfe` unless the model said `uscis_noid` — USCIS prints both on I-797E). EOIR-33 and a bare I-797 decide nothing. A label upgrades `other_notice`/`unknown` and replaces a type the model gave with `document_type_confidence=low`; a type the model was sure of (`medium`/`high`) only from a strong label ("Form …", "Notice …", "…, Notice of Action") of a type in the same §2 category that keeps every urgency protection of the model's type — its floor (§5.2 step 6), never-estimate and past-date rules (§5.3, §5.2), critical roles and driving roles — so `hearing_notice` → `nta` may happen and `uscis_noid` → `uscis_rfe` never. Only when the model said `other_notice` or `unknown`, a **heading** (a page-1 block's first line of ≤ 8 words) from the §4 "Recognize by" lines that names exactly one type upgrades it ("Notice of Interview" needs a SNAP cue, "Notice to Appear" an EOIR cue, the USCIS headings a USCIS cue); a later page may be another paper (rule 13) and decides nothing. Never when the model said `other_notice` with `document_type_confidence=high` or flagged `[multiple_documents]`; a correction sets `medium`. A correction is a label only: the scam scorer (§6) reads the model's own type, so it never lowers `scam_risk`, and a type the code chose reverts to the model's when `scam_risk == likely` (§6.5). Phrases are English; form labels work in any language. Then the **§2 master table fixes `category`** for every type but `other_notice` (best fit, §4.10), and an **unreadable** paper (§11 above) is always `unknown` / `other` whatever the model guessed. `entities.form_numbers` keep the printed form number only ("Form W-2 Wage and Tax Statement 2025" → `W-2`), and only when the transcript prints it as a whole number ("HI 96817" prints no I-9, "Room W 2B" no W-2).

---

## 4. Per-type reference

Sections 4.1–4.10 follow the eight-block layout of §1.2. The **Does / Refuses** block is present on every legal type (immigration, court, civic, employment) and on any type where the boundary is not obvious.

### 4.0 Rules common to every type

- **Extraction is quotation** (D-09): every Demand has `source_quote`, `span_ids`, `page`, `confidence`, `verified`. Fields the model cannot quote are not extracted.
- **Dates**: `date_text` as printed; the model never writes `value_iso`. A relative phrase ("within 30 days of this notice") becomes `kind=relative_deadline` with `relative_rule_text` and `anchor_span_id` pointing at the printed notice/decision date. `deadline_rules.py` decides `stated | estimated | unresolved` (§5.3).
- **Amounts**: `amount_text` as printed with currency; `AmountInfo.amount_minor` is parsed in code only when the text is unambiguous (`$1,240.00` → 124000). "Balance forward", "previous balance" and "total charges" are separate Demands only when the paper labels a **due** amount; otherwise only the amount labelled due/owed/"pay this amount" is a Demand and the rest stays in the transcript.
- **Documents requested** become one `document_requested` Demand with `documents[]` listing each item as printed.
- **Contacts**: a phone/URL/address printed on the paper may be a `contact` Demand ("from your paper"); anything not printed is stripped (D-10).
- **`questions_to_ask`** (≤ 5) are questions for the **sender**, never for the app, and never contain contacts.
- **Identifiers**: A-number (`A` + 8–9 digits), receipt number (3 letters + 10 digits), case/docket/account numbers set `entities.has_case_number`/`has_receipt_number`. SSN patterns are always masked (`***-**-1234`); A-numbers and receipt numbers are masked only when `hide_id_numbers=true`.
- **Reminders** are offered only for `reminder_eligible` Demands (`verified && date.kind=="stated" && value_iso`). Estimated or unverified dates never schedule a reminder.
- **`Verify this date` CTA** appears on every urgency banner driven by a date (§5.2).

**How the ten groups are cut.** §4.1 USCIS notices (7 types) · §4.2 immigration status and ICE papers (6) · §4.3 immigration court and other courts (5) · §4.4 medical (9) · §4.5 benefits (4) · §4.6 housing (6) · §4.7 school (5) · §4.8 employment (4) · §4.9 tax and civic (3) · §4.10 `other_notice` and `unknown` (2) = 51. Each group opens with **Common to this group** so per-type entries state only what differs. Abbreviations inside entries: **RB** Recognize by · **KF** Key fields → Demand · **DU** Deadline and urgency · **PF** Pitfalls · **PL** Plain-language guidance · **DR** Does / refuses · **RT** Resource tags · **CL/PK** Clerk need line (fallback) / Prepare checklist keys. Clerk lines complete the D-18 template "I need help with: {need line}." and are the `data/rules/clerk_needs.yaml` values (English, ≤ 200 chars, no contacts). Prepare keys marked **(rec.)** are WP2 recommendations to WP3 beyond the RESOURCE_DB §4.8 seed; every key already exists in `_meta.yaml.checklist` (§4.4 there). Research citations: `resources.md §3A…§3I`, `§4` and its *Warnings for builders*; `compliance.md §3`, `§7`.

### 4.1 USCIS notices — the I-797 family (7 types)

**Common to this group.** Letterhead "U.S. Citizenship and Immigration Services" / "Department of Homeland Security"; form label top-right (`I-797`, `I-797A`, `I-797B`, `I-797C`, `I-797E`); receipt number (3 letters + 10 digits → `has_receipt_number`); "Received Date", "Notice Date", "Priority Date", "Case Type", "Applicant/Petitioner", "Beneficiary"; A-number when present. `I-797C` prints "THIS NOTICE DOES NOT GRANT ANY IMMIGRATION STATUS OR BENEFIT" — define it in the glossary, never dramatize it. **Every type here:** `sender_kind=federal_agency`, `disclaimer_kind=legal_information_only`, `verify_resource_id = "uscis_contact"` whenever a date drives the banner (RESOURCE_DB §4.7 `verify_uscis_date`), rule `ar11_10d` for the eight types §5.3 lists (§5.3 also explains why it almost never yields an `estimated` date: the anchor is the user's move, which is not printed), plan ends with a `professional` step ("a licensed lawyer or a DOJ-accredited representative", never a named organization), and the model never states whether the case will be approved, whether the person may work or travel, or which form to file. A USCIS letter that asks for gift cards, wire, an app or crypto, or that points to a non-.gov site, is re-typed in code to `other_notice` (§6.5). Mailed-response arithmetic ("33 days if mailed") is never computed: the printed date is `stated`; a bare "within 30 days of this notice" is `unresolved` because no USCIS response rule is seeded (§9 lists the candidates). Research: `resources.md §3A`.

#### `uscis_receipt` — I-797C Receipt Notice (also Transfer Notice)
- **RB** first bold line "Receipt Notice" (or "Notice Type: Receipt Notice"), "We received your…", "Your case has been transferred to…" (transfer → glossary term *transfer*, still this type, §3.2). Case types: `I765`, `I485`, `I90`, `I751`, `I130`, `N400`, `I821`, `I589`.
- **KF** `expiry` only when the notice itself prints an extension sentence (I-90: "extends the validity of your card for 36 months"; I-751: "extends your conditional resident status…") — quote it verbatim; `notice_date` (info, anchor); `contact` only when a phone/URL is printed ("from your paper"); no `payment_due`. Receipt number is an identifier, not a Demand.
- **DU** roles `expiry`, `notice_date`; no floor; usually `info` with `urgency.info.no_action`. Rule: `ar11_10d` (documentary). Verify: `uscis_contact`.
- **PF** an I-765 renewal receipt filed on/after 2025-10-30 is **not** work authorization (auto-extension ended); an I-90 receipt *does* extend the card — only if printed; a "Rejection Notice" on I-797C is a `uscis_denial` (§3.2); people read "does not grant any status" as bad news; the receipt is the key to case status.
- **PL** Card 1: "This is a receipt from USCIS (the immigration office). It says they received your {form} on {date}. Nothing is approved or denied yet." Card 2: extension sentence if printed; otherwise `card.asking_nothing`. Card 3: `gather` keep the notice with the receipt number · `verify` check the case status with the receipt number (resource `uscis_contact`) · `professional`. Glossary: *receipt number*, *priority date*, *transfer*, *notice of action*.
- **DR** does: explain what was received and any printed extension. Refuses: to say the person can work or keep working, when a decision will come, or that an extension applies when it is not printed.
- **RT** `immigration_legal_help` + by case type: `I765` → `work_permit`; `I90`/`I751` → `green_card`; `N400` → `naturalization`; `I821` → `daca_tps`; `I589` → `asylum`.
- **CL/PK** "understanding a USCIS receipt notice and checking my case status" / `bring_notice`, `bring_receipt_number` **(rec.)**. Fixed notice §7: `fixed.uscis_receipt_i765` when `form_numbers` ∋ `I-765`.

#### `uscis_rfe` — I-797E Request for Evidence
- **RB** "I-797E", "REQUEST FOR EVIDENCE", "Request for Initial/Additional Evidence", "You must submit the requested evidence by…" / "within 87 days", "Please place this notice on top of your response", itemized evidence list, mailing address for the response, "If you do not respond… considered abandoned".
- **KF** `response_due` (`deadline` when a date is printed; `relative_deadline` for "within 87 days" → `unresolved`, §5.3); `document_requested` with `documents[]` = each requested item as printed; `contact` = the printed response address ("from your paper", `kind=contact`); `missing_pages` red flag when "Page 1 of N" pages are absent.
- **DU** role `response_due`; no floor; `high` ≤ 14 days, `medium` ≤ 30, `info` later; past ≤ 60 days → `critical` "This date may have passed" (§5.1). Verify: `uscis_contact`. Fixture `uscis_rfe_87d` expects `high`/`critical` by days-until.
- **PF** the response must be *received*, not mailed, by the date; one package only (USCIS does not merge later mailings); no extensions; sending part of the list is treated as a full response; the notice itself must go on top (that sentence is on the paper — extract as `action`).
- **PL** Card 1: "USCIS is asking for more papers before it decides. Your case is not denied." Card 2: the date, the list, the address as printed. Card 3: `gather` each item · `ask` (questions for a helper about items you do not have) · `mail` "in one package, with this notice on top, so it arrives before {date}" · `professional`. Glossary: *evidence*, *abandoned*, *initial vs additional evidence*.
- **DR** does: list exactly what is requested and the printed date. Refuses: to judge whether a document "counts", to say the case is weak, to draft a cover letter or statement (`drafting`).
- **RT** `immigration_legal_help` + the case-type tag as in `uscis_receipt`.
- **CL/PK** "a USCIS request for evidence and what I must send before the date on it" / `bring_notice`, `bring_receipt_number` (seed).

#### `uscis_noid` — Notice of Intent to Deny
- **RB** "NOTICE OF INTENT TO DENY", "we intend to deny", "You have 30 days (33 days if this notice was mailed) to respond", reasons/derogatory information paragraphs, rebuttal instructions.
- **KF** `response_due` (printed date `stated`; "within 30 days" `unresolved`); `document_requested` when a rebuttal list is printed; `contact` printed address.
- **DU** role `response_due`; **floor `high`** (D-12) → `urgency.high.floor` when no date; `critical` only via a past date (≤ 60 days). Verify: `uscis_contact`.
- **PF** more serious than an RFE and often confused with it; no extension; silence leads to denial on the record; the "33 days if mailed" clause is arithmetic the app never performs.
- **PL** Card 1: "USCIS says it plans to deny your {form} unless it hears from you. It is not denied yet." (never "you will be denied"). Card 2: date, items. Card 3: `professional` **first** ("Talk to a licensed lawyer or a DOJ-accredited representative this week") · `gather` · `mail`. Glossary: *intent to deny*, *rebuttal*, *derogatory information*.
- **DR** refuses: to explain how to rebut, to weigh the reasons, to predict the outcome.
- **RT** `immigration_legal_help` (+ case-type tag). Pins (RESOURCE_DB §4.5): `immlawhelp`, `eoir_roster`.
- **CL/PK** "a USCIS notice of intent to deny and finding legal help before the response date" / `bring_notice`, `bring_receipt_number` (seed).

#### `uscis_biometrics` — ASC Appointment Notice
- **RB** "ASC Appointment Notice" / "Biometrics Appointment", "APPLICATION SUPPORT CENTER", "PLEASE APPEAR AT", "DATE AND TIME OF APPOINTMENT", "CODE 3" (fingerprints, photo, signature), "If you cannot appear… reschedule through your USCIS online account", "Bring this notice and a valid photo ID".
- **KF** `appointment` (date + `time_text`), `contact` = the ASC street address as printed; `document_requested` = "this notice", "photo identification" as printed.
- **DU** role `appointment` (USCIS appointment → `critical` ≤ 7 days, D-12); past ≤ 60 days → `critical` date-passed; no floor. Verify: `uscis_contact`.
- **PF** missing it without rescheduling can lead to the case being treated as abandoned (resources.md §3A); rescheduling is done online *before* the time; the notice is for one named person (family members have their own).
- **PL** Card 1: "This is an appointment to take your fingerprints and photo for your {form}." Card 2: date, time, place. Card 3: `bring` this notice + photo ID · `visit` · `verify` (reschedule online before the time if you cannot go) · `professional` only if other papers are pending. Glossary: *biometrics*, *ASC*.
- **DR** refuses: to say what happens to the case if missed beyond quoting the notice; to say which ID "counts" beyond what is printed.
- **RT** `immigration_legal_help`. Pins: `uscis_biometrics_page`, `uscis_contact`.
- **CL/PK** "my fingerprint appointment notice from USCIS — the date, time and place" / `bring_notice`, `bring_photo_id` (seed).

#### `uscis_interview` — Interview / oath notice
- **RB** "Interview Notice", "Request for Applicant to Appear for Initial Interview", "Notice of Asylum Interview", "Naturalization Interview" (N-400), "N-445 Notice of Naturalization Oath Ceremony" (classified here: it is an appointment), documents checklist, interpreter paragraph, "evidence must be received 14 days before the interview" (asylum, rules effective 2026-08-21).
- **KF** `appointment` (date, time, office address `contact`); `response_due` when an evidence-due date is printed (asylum); `document_requested` = the checklist as printed; `action` for interpreter instructions as printed.
- **DU** roles `appointment` (`critical` ≤ 7 days), `response_due`; no floor. Verify: `uscis_contact`.
- **PF** asylum: rescheduling now requires exceptional circumstances and no-show can end in dismissal or referral (resources.md §3A — quote only what the paper prints; the resource warning `warn.asylum_rules_aug_2026` carries the rule); asylum applicants may need to bring their own interpreter for some languages; naturalization: the civics test version depends on the N-400 filing date (information only, glossary); bring the green card and all passports (as printed).
- **PL** Card 1: "USCIS wants to meet you about your {form} on {date}." Card 2: date/time/place, evidence-due date, bring list. Card 3: `gather` · `bring` · `visit` · `professional` ("before the interview"). Glossary: *interview*, *oath ceremony*, *interpreter*.
- **DR** refuses: to coach answers, predict the result, or say whether the person can skip the interpreter.
- **RT** `immigration_legal_help` + `asylum` / `naturalization` / `green_card` by form.
- **CL/PK** "my USCIS interview notice — what to bring and the date" / `bring_notice`, `bring_photo_id` (seed).

#### `uscis_approval` — I-797 / I-797A / I-797B Approval Notice
- **RB** "Notice Type: Approval Notice", "The above petition/application has been approved", "Valid from … to …", "Class", I-94 tear-off (I-797A), "Consulate notified" (I-797B), "Your card will be mailed".
- **KF** `expiry` (validity end, `role=expiry`), `notice_date`; nothing owed.
- **DU** role `expiry` (thresholds by days-until; a validity end 6 months out is `info.date_later`); no floor. Verify: `uscis_contact`.
- **PF** approval ≠ card in hand (the card follows by mail); an I-797B needs a visa step abroad; validity dates on the notice are the ones that matter for planning; people mistake I-797C "does not grant" language for this notice.
- **PL** Card 1: "Good news is printed here: USCIS approved your {form}. The paper says it is valid from {date} to {date}." Card 2: dates; `card.asking_nothing` if none. Card 3: `gather` keep it safe · `verify` if a card does not arrive · `professional` before the validity end.
- **DR** refuses: to say what the approval lets the person do beyond quoting the class/validity; to advise on travel or work.
- **RT** `immigration_legal_help` + case-type tag. Pin `uscis_i797_types`.
- **CL/PK** "understanding a USCIS approval notice and the dates on it" / `bring_notice` **(rec.)**.

#### `uscis_denial` — Decision / denial / rejection
- **RB** "DECISION", "Notice of Decision", "is denied", "You may appeal… Form I-290B… within 30 days (33 if mailed)", "motion to reopen or reconsider", "Rejection Notice" (I-797C: fee, signature, wrong form — `document_type_confidence=medium`, glossary *rejection ≠ denial*), "You are not authorized to remain… you may be placed in removal proceedings" (→ tag `removal_proceedings`).
- **KF** `decision_date` (anchor), `response_due` (appeal/motion date **only when printed**; "within 30 days" → `unresolved` with "Ask the sender which date this means" — and the plan's `professional` step says a lawyer can confirm it); `contact` printed address.
- **DU** roles `response_due`, `decision_date`; printed date only; no floor; past ≤ 60 days → `critical`. Verify: `uscis_contact`.
- **PF** appeal vs motion are different remedies (glossary only); the 30/33-day window is short and the app never computes it; a rejection is fixable (missing fee/signature) while a denial is a decision; some denials mention an NTA — do not dramatize.
- **PL** Card 1: "USCIS decided not to approve your {form}. The letter gives its reasons on page {n}." Card 2: dates as printed. Card 3: `professional` **first, this week** · `gather` the whole letter · `verify`. Glossary: *appeal*, *motion to reopen*, *motion to reconsider*, *rejection*.
- **DR** refuses: to say whether to appeal, whether an appeal would win, or to explain the legal reasons beyond quoting them.
- **RT** `immigration_legal_help`; `removal_proceedings` when an NTA or removal proceedings are referenced. Pins `immlawhelp`, `eoir_probono`.
- **CL/PK** "a USCIS decision letter and finding legal help before any deadline in it" / `bring_notice`, `bring_receipt_number` **(rec.)**.

### 4.2 Immigration status and ICE papers (6 types)

**Common to this group.** Same USCIS conventions as §4.1 (receipt numbers, `legal_information_only`, `professional` step, `uscis_contact` verify) except `ice_checkin`, whose sender is ICE and whose verify resource is the phone printed on the paper. Expiry dates are the main urgency driver here; the app states the printed dates and never says whether the person "still has status", "can work", or "can travel". H.R.1 fee amounts (EAD $550/$275, TPS ≤ $500, parole ~$1,000 *likely*) are **never quoted from memory** — only when printed on the paper; the resource `uscis_hr1_fees` carries them (resources.md *Warnings*: "H.R.1 FEES").

#### `ead_related` — work permit (Form I-766 card, I-765 papers, employer letters about it)
- **RB** "EMPLOYMENT AUTHORIZATION CARD", "Card Expires", "Category" (A05, C08, C09, A12/C19…), "USCIS#", "Employment Authorization Document", "I-765"; employer letters "your work authorization expires on…"; stale text about a "180-day/540-day automatic extension".
- **KF** `expiry` (card expiry), `response_due` (an employer's "provide updated documents by"), `document_requested` as printed.
- **DU** roles `expiry`, `response_due`; no floor; past expiry ≤ 60 days → `critical` date-passed (USCIS paper). Rule `ar11_10d`.
- **PF** for I-765 renewals filed on/after 2025-10-30 there is no automatic extension and the I-797C receipt is not proof of work authorization (TPS Federal-Register extensions excepted) — fixed notice §7 when a receipt is referenced; any "540-day" sentence on the paper is quoted but the glossary notes the rule changed (fixed copy, not model prose); USCIS says a renewal may be filed up to 180 days before expiry (information via resource `uscis_i765`, not a plan instruction).
- **PL** Card 1: "This is about your work permit. It says the card is valid until {date}." Card 3: `gather` · `verify` (case status) · `professional` "well before the expiry date". Glossary: *EAD*, *category code*, *automatic extension*.
- **DR** refuses: to say the person may keep working after expiry, when to file, or how an employer must treat the receipt.
- **RT** `work_permit`, `immigration_legal_help` (+ `daca_tps` when A12/C19 or TPS is printed).
- **CL/PK** "my work permit — its dates and the paper about it" / `bring_notice`, `bring_photo_id` **(rec.)**.

#### `green_card_related` — permanent-resident card, I-90, I-751/I-829
- **RB** "PERMANENT RESIDENT CARD", "Resident Since", "Card Expires", category codes (IR1, CR1, CR2, RE…), "I-90 Application to Replace Permanent Resident Card", "I-751 Petition to Remove Conditions on Residence", "conditional resident", "2-year card".
- **KF** `expiry` (card expiry; an I-751 receipt's printed extension sentence as a second `expiry` when printed), `response_due` as printed.
- **DU** roles `expiry`, `response_due`; no floor. Rule `ar11_10d`.
- **PF** a 2-year conditional card **cannot** be renewed with I-90 (the I-751/I-829 window is the 90 days before expiry — resources.md §3B); an expired card does not end residence (say so only as glossary information, never as reassurance about this person); an I-90 receipt extends the card 36 months only if printed.
- **PL** Card 1: "This is about your Green Card. It says the card expires on {date}." Card 3: `gather` · `professional` "before the date on the card". Glossary: *conditional resident*, *Green Card*, *I-90*.
- **DR** refuses: to say which form to file or whether residence is at risk.
- **RT** `green_card`, `immigration_legal_help`. Proposed fixed notice §7.2 (`fixed.conditional_card`) when "conditional"/CR category/2-year card is printed.
- **CL/PK** "my Green Card paper — its dates and what it asks for" / `bring_notice`, `bring_photo_id` **(rec.)**.

#### `tps_related` — Temporary Protected Status
- **RB** "Temporary Protected Status", "TPS", "I-821", "re-registration period", "Federal Register", a country name and designation dates, "EAD automatically extended through".
- **KF** `response_due` (re-registration window end), `expiry` (designation end / EAD extension end), `document_requested` (I-821, I-765, fee or fee-waiver items as printed).
- **DU** roles `response_due`, `expiry`; no floor; past window end ≤ 60 days → `critical` date-passed. Rule `ar11_10d`.
- **PF** windows and extensions come only from Federal Register notices and change often (resources.md *Warnings*: "TPS"); several designations are terminated or in litigation — the app never says whether a country is "still designated"; missing the window can end TPS and work authorization (quote the paper's own warning if printed).
- **PL** Card 1: "This is about your Temporary Protected Status (TPS). It gives dates for re-registering." Card 3: `verify` the country page (resource `uscis_tps`, warning `warn.tps_dates_from_federal_register`) · `professional` "before the window closes".
- **DR** refuses: to say whether the person is eligible to re-register or what happens to a pending case.
- **RT** `daca_tps`, `work_permit`, `immigration_legal_help`.
- **CL/PK** "a Temporary Protected Status paper and its re-registration dates" / `bring_notice`, `bring_a_number` **(rec.)**.

#### `asylum_fee_notice` — Annual Asylum Fee notice
- **RB** "Annual Asylum Fee", "Form I-589 pending", "$100" (indexed; ASAP reports $102), "must be paid within 30 days of this notice", "pay through your USCIS online account", "failure to pay may result in…".
- **KF** `payment_due` (`amount` with the printed figure; `deadline` when a date is printed, else `relative_deadline` → `estimated` via `asylum_annual_fee_30d` when the notice date is a verified anchor); `notice_date`.
- **DU** role `payment_due` → **`critical` ≤ 7 days** (D-12 names this type); `estimated` dates cap at `medium` (§5.1). Verify: `uscis_contact`.
- **PF** no fee waiver exists for this fee (fixed notice `fixed.asylum_fee_notice`); ASAP reports notices sometimes never arrive — the resource `asap` carries that warning; payment is only through a .gov account (a letter directing payment elsewhere is a scam signal, §6).
- **PL** Card 1: "USCIS is asking for the yearly asylum fee. The paper says {amount} by {date}." Card 3: `submit_online` (as printed) · `verify` · `professional`. Glossary: *annual asylum fee*, *pending*.
- **DR** refuses: to say what happens to the asylum case if unpaid beyond quoting the notice; to say whether the fee applies to this person.
- **RT** `asylum`, `immigration_legal_help` (+ `fee_waiver` so the "no waiver" resources surface).
- **CL/PK** "a USCIS notice about the annual asylum fee and the date to pay by" / `bring_notice`, `bring_a_number`, `bring_receipt_number` (seed).

#### `parole_related` — parole, re-parole, Afghan and other parolees
- **RB** "Parole", "PAROLED", I-94 with class "PAR"/"DT", "Humanitarian Parole", "Re-Parole", "I-131", "Operation Allies Welcome" / "OAW", "Uniting for Ukraine", "CHNV", "parole expires/terminates on".
- **KF** `expiry` (parole end), `response_due` as printed, `document_requested`.
- **DU** roles `expiry`, `response_due`; no floor. Rule `ar11_10d`.
- **PF** parole is time-limited and re-parole is not automatic; program pages change quickly — route to `uscis_afghan` for Afghans (State Department SIV pages cannot be auto-verified, RESOURCE_DB §14); benefits eligibility for parolees changed under H.R.1 — never state it (resource warning `warn.hr1_coverage_changes`).
- **PL** Card 1: "This is about your parole (permission to be in the U.S. for a time). It says it ends on {date}." Card 3: `professional` "well before {date}" · `verify`.
- **DR** refuses: to say whether re-parole or another status is available.
- **RT** `afghan_specific` (when Afghan nationality, OAW or SIV is printed), `refugee_services`, `immigration_legal_help`.
- **CL/PK** "my parole paper — its dates and what it asks for" / `bring_notice`, `bring_a_number`, `bring_photo_id` **(rec.)**.

#### `ice_checkin` — ICE check-in, release and supervision papers
- **RB** "U.S. Immigration and Customs Enforcement", "Enforcement and Removal Operations", "Order of Release on Recognizance" (I-220A), "Order of Supervision" (I-220B), "Notice to Report", "Alternatives to Detention" / "ISAP", "You must report to… on…", field office address, "Subject ID", conditions list.
- **KF** `appointment` (report date/time/place → `contact` for the printed office), `action` for each printed condition (report, notify of moves, no travel) as quoted; `document_requested` (ID, this paper).
- **DU** role `appointment` → **`critical` ≤ 7 days** (ICE appointment, D-12); past ≤ 60 days → `critical` date-passed; no floor. Verify: the printed field-office phone (`verify_resource_id=null`, banner "Call the number on your paper"); resource `ice_checkin` for online scheduling.
- **PF** missing a report date is a violation of release conditions (quote the paper); ICE's page says an online appointment can be scheduled — the app links it and never promises it replaces the printed date (general guidance, §9); ICE does not phone to warn of arrest — a call or text demanding payment is a scam (§6); moves must be reported to ICE *and* the court *and* USCIS separately (`warn.address_change_multi_agency`).
- **PL** Card 1: "This paper is from ICE. It tells you when and where to report, and the rules you agreed to." Card 2: date/time/place, conditions. Card 3: `bring` this paper + ID · `visit` · `verify` (call the printed number / online check-in) · `professional` (`removal_proceedings`). Glossary: *recognizance*, *supervision*, *report*.
- **DR** refuses: to say what happens if a date is missed beyond the paper's words, whether conditions can be changed, or anything about the court case.
- **RT** `removal_proceedings`, `immigration_legal_help`. Pin `ice_checkin`.
- **CL/PK** "my ICE check-in paper — the report date, time and place" / `bring_notice`, `bring_subject_id`, `bring_photo_id` (seed).

### 4.3 Immigration court and other courts (5 types)

**Common to this group.** Category `court`, `disclaimer_kind=legal_information_only`. EOIR papers: letterhead "U.S. Department of Justice — Executive Office for Immigration Review — Immigration Court" or "Board of Immigration Appeals" (Falls Church, VA); A-number ("A" + 8–9 digits → `has_case_number`); "Respondent"; "In removal proceedings". For the four EOIR types `verify_resource_id = "eoir_hotline"` (RESOURCE_DB §4.7 `verify_court_date`; the ACIS site is the pinned companion), the fixed notice `fixed.address_change_multi_agency` applies to `nta`/`hearing_notice` (D-20), and the plan's `professional` step names "a licensed lawyer or a DOJ-accredited representative" with tags `removal_proceedings` (EOIR pro bono list). A hearing date is the strongest urgency signal in the whole taxonomy (`critical` ≤ 7 days, floor `high` on `nta`/`hearing_notice`). The stakes sentence the app may print is the paper's own warning, quoted — never a model paraphrase of "you will be deported" (compliance.md §7: in-absentia removal has no appeal). `traffic_court` is a state/local court: verify = the printed clerk's phone. Research: `resources.md §3B`, `§3I`; `compliance.md §7`.

#### `nta` — Notice to Appear (Form I-862)
- **RB** "NOTICE TO APPEAR", "Form I-862", "In removal proceedings under section 240 of the Immigration and Nationality Act", numbered allegations ("1. You are not a citizen or national of the United States"), charge(s), "YOU ARE ORDERED to appear before an immigration judge… at [court address] on [date] at [time]" — often "to be set" / "TBD"; DHS officer signature; a "Notice to Respondent"/"Warning" section about failing to appear and about address changes.
- **KF** `hearing_date` (`deadline` when a real date is printed; "to be set"/"TBD" → **no date Demand**, an `action` "Watch for a hearing notice; check the case-information line" with the quote, and `ambiguity_note`); `contact` = court address as printed; `action` = the address-change duty as printed (kind `action`, `role=other`, quoted — the multi-agency point is the fixed notice); `missing_pages` when allegations pages are absent.
- **DU** role `hearing_date` → `critical` ≤ 7 days; **floor `high`** (`urgency.high.floor` when the date is TBD or absent); past ≤ 60 days → `critical` date-passed. Rules: `eoir33_5bd` (documentary, move-anchored). Verify: `eoir_hotline`. Fixture `nta_hearing_date`.
- **PF** hearing dates printed on NTAs are frequently rescheduled — the ACIS/hotline date wins, so the banner CTA matters; missing a hearing → in-absentia removal order (quote the paper's warning; proposed fixed notice §7.2); the court's address form (EOIR-33) is separate from USCIS's and from ICE's; the allegations are not findings — glossary *allegation*, *charge*; an NTA does not by itself say the person must leave.
- **PL** Card 1: "This paper starts a case in immigration court. It lists what the government says about you and tells you to appear before a judge{ on {date}}. Nothing is decided yet." Card 2: date/time/court; the address-change duty. Card 3: `verify` the date with the court's case line (`court_notice`) · `professional` "before the hearing — the EOIR list has free lawyers" · `gather` this paper + A-number · `visit` "Go to every hearing, even without a lawyer yet". Glossary: *respondent*, *removal proceedings*, *master calendar*, *A-number*.
- **DR** does: explain the parts of the NTA and the printed date. Refuses: to evaluate the allegations, say whether relief exists, or predict the outcome (`outcome`, `eligibility`); to draft anything for the court (`drafting`).
- **RT** `removal_proceedings`, `court_notice`, `change_of_address`. Pins `eoir_hotline`, `eoir_acis`, `eoir_probono`, `eoir_icor`.
- **CL/PK** "a Notice to Appear in immigration court — confirming the hearing date and finding a lawyer" / `bring_notice`, `bring_a_number` (seed).

#### `hearing_notice` — Notice of Hearing in Removal Proceedings
- **RB** "NOTICE OF HEARING IN REMOVAL PROCEEDINGS", "Please take notice that the above captioned case has been scheduled for a MASTER / INDIVIDUAL hearing before the Immigration Court on [date] at [time]", court address, judge, "internet-based hearing" / WebEx link, "A copy of this notice was served by mail", the standard failure-to-appear and address-change paragraphs.
- **KF** `hearing_date` (+ `time_text`), `contact` court address / WebEx link ("from your paper"), `action` for the address duty.
- **DU** role `hearing_date` → `critical` ≤ 7 days; **floor `high`**; past ≤ 60 days → `critical`. Rule `eoir33_5bd`. Verify: `eoir_hotline`.
- **PF** notices arrive only at the address on file (so mail loss = missed hearing); master vs individual (merits) hearings differ in length and preparation (glossary only); internet hearings need the link and a quiet place; rescheduled dates supersede older notices — always confirm.
- **PL** Card 1: "The immigration court set your hearing for {date} at {time}{, online / at {court}}." Card 3: `verify` · `bring` this notice + A-number · `visit` · `professional`. Glossary: *master calendar hearing*, *individual hearing*, *WebEx*.
- **DR** refuses: to say what to say at the hearing, whether to ask for a continuance, or what the judge will decide.
- **RT** `removal_proceedings`, `court_notice`, `change_of_address`. Pins `eoir_hotline`, `eoir_acis`, `eoir_court_finder`.
- **CL/PK** "an immigration court hearing notice — confirming the date, time and place" / `bring_hearing_notice`, `bring_a_number` (seed).

#### `ij_decision` — Immigration Judge decision or order
- **RB** "ORDER OF THE IMMIGRATION JUDGE", "Decision and Orders of the Immigration Judge", "ordered removed", "granted"/"denied", "in absentia", "Appeal: WAIVED / RESERVED", "Any appeal must be received by the Board of Immigration Appeals within 30 calendar days of this decision", certificate of service date.
- **KF** `decision_date` (anchor), `response_due` (appeal date when printed → `stated`; "within 30 calendar days" → `estimated` via `bia_appeal_30d`, *likely*, receipt-based; "within 180 days" on an in-absentia order → `estimated` via `in_absentia_rescission_180d`), `contact` as printed.
- **DU** roles `response_due`, `decision_date`; no floor; `estimated` caps at `medium` (so the `professional` step, not the banner, carries the urgency — say "this week" in the step); past ≤ 60 days → `critical`. Rules: `bia_appeal_30d`, `in_absentia_rescission_180d`, `eoir33_5bd`. Verify: `eoir_hotline`.
- **PF** the BIA deadline is by **receipt** and cannot be extended (`rule_verification: likely` → `demand.rule_likely` shows); "appeal waived" means the printed appeal window may not apply — never resolve that in copy; an in-absentia order has no appeal but different motions exist (glossary *motion to reopen*, no eligibility statement); the EOIR-26 fee and EOIR-26A waiver are on the resource `eoir_forms`, never quoted from memory.
- **PL** Card 1: "The immigration judge made a decision on {date}. The order says: '{quoted disposition}'." Card 2: the appeal sentence and its estimate ("Estimate: … Confirm with the sender."). Card 3: `professional` **first, today** · `verify` (hotline gives appeal/brief dates) · `gather`. Glossary: *in absentia*, *Board of Immigration Appeals*, *reserved appeal*.
- **DR** refuses: to say whether to appeal, whether a motion would succeed, or to compute the 30 days when no anchor is verified.
- **RT** `removal_proceedings`, `immigration_legal_help`. Pins `eoir_probono`, `eoir_forms`, `eoir_hotline`.
- **CL/PK** "an immigration judge's decision and the appeal date on it" / `bring_notice`, `bring_a_number` **(rec.)**.

#### `bia_notice` — Board of Immigration Appeals notices
- **RB** "Board of Immigration Appeals", "Filing Receipt for Appeal", "Notice of Appeal received", "BRIEFING SCHEDULE", "brief due on or before", "transcript", "DECISION of the Board", "Clerk's Office, 5107 Leesburg Pike".
- **KF** `response_due` (brief due), `decision_date` (Board decision), `contact` as printed.
- **DU** roles `response_due`, `decision_date`; no floor; past ≤ 60 days → `critical`. Rule `eoir33_5bd` (BIA has its own EOIR-33/BIA). Verify: `eoir_hotline` (states brief due dates).
- **PF** the brief deadline is also by receipt; a separate address form goes to the BIA; a Board decision may start further, court-specific clocks the app does not seed (federal petition for review — professional only).
- **PL** Card 1: "This is from the Board that reviews immigration judges' decisions. It {sets a due date for your written argument / gives its decision}." Card 3: `professional` first · `verify` · `gather`. Glossary: *brief*, *transcript*, *Board*.
- **DR** refuses: to say what the brief should argue or what the Board will decide.
- **RT** `removal_proceedings`, `immigration_legal_help`. Pins `eoir_hotline`, `eoir_probono`.
- **CL/PK** "a notice from the Board of Immigration Appeals and the due date on it" / `bring_notice`, `bring_a_number` **(rec.)**.

#### `traffic_court` — traffic citation, court reminder, failure-to-appear, DMV notice
- **RB** "Uniform Summons", "Traffic Citation", "Notice to Appear" on a police or General District Court letterhead (not EOIR — §3.4), "Court date", "You must appear in court on", "prepayable offense" / "you may prepay", "Failure to appear may result in suspension of your driver's license / a warrant", DMV "Order of Suspension".
- **KF** `hearing_date`, `payment_due` (prepay amount + date), `contact` clerk's office as printed, `action` (prepay option as printed).
- **DU** roles `hearing_date` (`critical` ≤ 7 days), `payment_due`; no floor; past ≤ 60 days → `critical` (court paper). Verify: printed clerk phone (`verify_resource_id=null`). Fixture `traffic_court_notice` expects `high`/`critical` by date.
- **PF** prepaying is a guilty plea in most states (information; never "you should/should not prepay"); some traffic and criminal matters affect immigration cases (proposed fixed notice §7.2 `fixed.traffic_court_immigration`); state rules vary and no national resource exists (`traffic_court` tag is fallback-only, RESOURCE_DB §3.1).
- **PL** Card 1: "This is a court paper about a traffic matter. It gives a court date{ and a way to pay instead}." Card 3: `verify` the date with the clerk (printed number) · `professional` "if you are not a U.S. citizen, talk to an immigration lawyer before you pay or plead" · `bring`. Glossary: *prepay*, *failure to appear*, *summons*.
- **DR** refuses: to say whether to pay, plead, or contest; to predict fines, points or license outcomes.
- **RT** `traffic_court`, `immigration_legal_help`. Pins `immlawhelp`, `lawhelp`.
- **CL/PK** "a traffic or court notice — the court date or payment date on it" / `bring_the_summons`, `bring_photo_id` **(rec.)**.

### 4.4 Medical (9 types)

**Common to this group.** `disclaimer_kind=medical_information_only`; verify = the sender's printed phone (`verify_resource_id=null`). **Describe, never interpret** (compliance.md *Warnings*: explaining what a value means for the user edges toward FDA "interpret or analyze" and Gemini's medical-advice ban): the app reads what is printed, defines words, and routes to "your doctor, nurse or pharmacist". The D-14 emergency lexicon runs on every transcript and *will* fire on discharge papers and labels that list warning symptoms — that is intended (the card says "If this is happening now"). Senders `hospital_or_clinic`, `pharmacy`, `insurer` are HHS-funded settings, so the clerk card appends `clerk.interpreter_hhs` (D-18). Payment-method scam signals on a private sender's bill (a hospital accepting PayPal) count half weight (§6.3). Research: `resources.md §3C`, `§1C`.

#### `medical_bill` — statement, itemized bill, collection letter
- **RB** "Statement", "Amount Due", "Pay by / Due date", "FINAL NOTICE", "Account number", "Date of service", "Patient balance", "Insurance pending", "Financial assistance is available" (501(r) notice); collector: "This is an attempt to collect a debt", `sender_kind=bank_or_collector`.
- **KF** `payment_due` (`amount` = only the figure labelled due; `deadline` if a pay-by date is printed); `contact` billing phone/portal as printed; `action` (financial-assistance sentence as printed); `document_requested` rarely (insurance card). Red flag `urgency_pressure` (model, verified quote) for "FINAL NOTICE"/"immediately" — severity `medium`, not a scam by itself (fixture `inova_final_notice`: `medium`, `scam_risk: none`).
- **DU** role `payment_due`; no floor; rule `gfe_dispute_120d` only when the paper prints a Good-Faith-Estimate dispute phrase with a verified anchor. Fixture expects `medium`.
- **PF** a "statement" may be pre-insurance; itemized bill vs summary; charity care (FAP) is often available after billing and before paying — as *information* ("hospitals with a financial-assistance policy let people apply; ask for it"), never "you qualify"; No Surprises Act rights and GFE disputes exist (resource `cms_medical_bill_rights`); collectors add urgency language.
- **PL** Card 1: "This is a bill from {sender} for care on {date}. It says the amount due is {amount} by {date}." Card 3: `ask` for an itemized bill (`bring_itemized_bill_request`) · `ask` about financial assistance (`charity_care`) · `call` the printed number with questions · `professional` = "your doctor's billing office or a hospital financial counselor". Glossary: *itemized*, *adjustment*, *patient responsibility*, *financial assistance*.
- **DR** refuses: "you owe this" / "do not pay this"; whether insurance should have paid; legal conclusions about surprise billing.
- **RT** `medical_bill`, `charity_care`. Pins `cms_medical_bill_rights`, `dollarfor`; institution bonus (Inova → `inova_fa`).
- **CL/PK** "a medical bill — the amount, what it is for, and help paying it" / seed `bring_the_bill`, `bring_itemized_bill_request`, `bring_insurance_card`, `bring_proof_income`.

#### `eob` — Explanation of Benefits
- **RB** "Explanation of Benefits", "THIS IS NOT A BILL", claim number, "Amount billed / Allowed amount / Plan paid / You may owe", remark or denial codes, "Appeal rights".
- **KF** `amount` labelled "you may owe" (role `other`, `ambiguity_note` "an estimate of what the provider may bill"); `response_due` only when an appeal date is printed or a denial code appears with a relative phrase (→ `aca_internal_appeal_180d`, anchor = EOB date); no `payment_due`.
- **DU** role `response_due`; no floor; usually `info`. Rule `aca_internal_appeal_180d`.
- **PF** people pay from EOBs (proposed fixed notice §7.2 `fixed.eob_not_a_bill`; RESOURCE_DB §14 expects that copy here); the provider's bill should match the EOB's patient amount — say "compare", never "the bill is wrong"; a denial code on an EOB starts the same appeal clock as a denial letter.
- **PL** Card 1: "This paper from your insurance explains what it paid for care on {date}. It is not a bill." Card 3: `gather` the matching bill · `verify` (compare the two) · `call` insurer with the claim number when a code is printed. Glossary: *allowed amount*, *deductible*, *coinsurance*, *claim*.
- **DR** refuses: to say whether the plan should have covered more or whether to appeal.
- **RT** `medical_bill`; `insurance_denial` only when a denial/remark code is present. Pin `healthcare_appeals`.
- **CL/PK** "an insurance statement (not a bill) — what my plan paid and what it says I may owe" / seed `bring_notice`, `bring_the_bill`.

#### `insurance_denial` — denial, adverse benefit determination, Medicaid/Medicare notices with appeal rights
- **RB** "Adverse Benefit Determination", "denied", "not medically necessary", "not a covered benefit", "out of network", "You have the right to appeal", "internal appeal… within 180 days", "external review… within 4 months", "expedited/urgent appeal… 72 hours", Medicaid: "Notice of Action", "fair hearing", "your coverage will end on"; Medicare Advantage/Part D: "Notice of Denial of Medical Coverage", "65 days"; Original Medicare: "Medicare Summary Notice", "by [date]".
- **KF** `response_due` (printed appeal date `stated`; relative phrase → `estimated` via the matching rule), `decision_date`/`notice_date` anchor, `document_requested` (appeal form items as printed), `contact` appeals address/phone as printed, `action` (continuation-of-benefits sentence when printed).
- **DU** role `response_due`; no floor; `estimated` caps at `medium` (fixture `insurance_denial_180d`: `medium`, `estimated` via `aca_internal_appeal_180d`). Rules: `aca_internal_appeal_180d`, `aca_external_review_4mo` (anchor = final internal denial date), `medicare_advantage_65d`, `medicaid_fair_hearing_90d_max` (*likely*, state sets the exact window).
- **PF** internal appeal precedes external review; "final adverse determination" starts the external clock; Medicaid hearing requests before the effective date may keep coverage running in many states — **general guidance, confirm with the agency** (§9), quote only if printed; Medicare windows changed in 2026 (`warn.medicare_windows_changed`); keep a call log (plan step `gather`).
- **PL** Card 1: "Your {insurer/Medicaid} decided not to pay for {service}. The letter gives a reason and says how to ask them to look again." Card 2: appeal date (estimate shown with formula and "Confirm with the sender."), items. Card 3: `call` the printed number · `gather` the letter, EOB, doctor's note · `ask` the doctor's office for a letter of support · `professional` = "a patient advocate, your state consumer-assistance program or a lawyer" (via `insurance_denial` resources). Glossary: *internal appeal*, *external review*, *medically necessary*, *fair hearing*.
- **DR** refuses: whether to appeal or whether it will succeed (`filing_advice`, `outcome`); whether the care was necessary; drafting the appeal (`drafting`).
- **RT** `insurance_denial` + `medicare_appeal` (Medicare) / `medicaid_renewal` (state agency).
- **CL/PK** "an insurance denial letter and the appeal date on it" / seed `bring_denial_letter`, `bring_insurance_card`.

#### `prior_auth` — prior authorization / coverage determination
- **RB** "Prior Authorization", "Pre-certification", "Authorization number", "Approved for {n} visits/units from {date} to {date}", "Denied", "Coverage determination" (Part D), "peer-to-peer".
- **KF** `expiry` (valid-through date), `response_due` (denial appeal date), `contact`.
- **DU** roles `expiry`, `response_due`; no floor. Rule `aca_internal_appeal_180d` on denials.
- **PF** approval is not a payment guarantee (quote the paper's own disclaimer if present); authorizations expire and count units; a denied drug may have an alternative the doctor can request — information for the `ask` step only.
- **PL** Card 1: "Your plan {approved/did not approve} {service or medicine} ahead of time. It is valid from {date} to {date}." Card 3: `gather` · `ask` your doctor's office (they usually handle appeals) · `call` the plan. Glossary: *prior authorization*, *units*, *coverage determination*.
- **DR** refuses: whether the treatment is needed or whether to appeal.
- **RT** `insurance_denial` (denied), `prescription_help` (drug). Pin `healthcare_appeals`.
- **CL/PK** "an insurance prior authorization letter for a treatment or medicine" / seed `bring_notice`, `bring_insurance_card`.

#### `lab_result` — laboratory report
- **RB** test names, result values with units, "Reference range", "H"/"L"/"Abnormal"/"Critical" flags, "Collected", "Reported", "Final", "Ordering provider".
- **KF** `appointment` only when a follow-up date is printed; otherwise no Demands (values are transcript, not Demands). `contact` = ordering provider's phone as printed.
- **DU** role `appointment`; no floor; usually `info`.
- **PF** out-of-range does not mean disease and in-range does not mean healthy (MedlinePlus, resource `medlineplus_labs`); portals show results before the clinician has reviewed them; flags are lab conventions, not diagnoses.
- **PL** Card 1: "This is a lab report from {date}. It lists tests, your numbers, and the lab's usual range. Your doctor will tell you what your numbers mean." Card 3: `ask` "Ask your doctor to explain the flagged lines" · `call` if no follow-up is scheduled. Glossary: *reference range*, *flag*, *units* — definitions only, never applied to this person's values.
- **DR** refuses (hard): "your {value} is high/low/normal", "you have…", any statement about what a result means (`medical_interpretation`). The phrasing linter's medical block (§8.2) exists mainly for this type.
- **RT** `lab_results`, `primary_care_uninsured`. Pin `medlineplus_labs`.
- **CL/PK** "a lab test report — I want the doctor to explain the results" / `bring_notice` **(rec.)**.

#### `prescription_label` — pharmacy label
- **RB** "Rx #", drug name and strength, directions ("Take 1 tablet by mouth twice daily"), "Qty", "Refills: 0", prescriber, "Discard after", pharmacy name/phone, auxiliary warning stickers.
- **KF** `expiry` (discard date), `other` (refills count as `action` "Refills: 0 — call the prescriber" only as printed), `contact` pharmacy phone ("from your paper").
- **DU** roles `expiry`, `other`; no floor; `info` (fixture `prescription_label`).
- **PF** "as directed" is ambiguous; teaspoon vs mL; brand vs generic names differ; 0 refills; pharmacies in HHS-funded settings can provide interpreters and translated labels (resource `hhs_ocr_lep`) — the clerk card is the tool for that.
- **PL** Card 1: "This is the label for {drug as printed}. It says: '{directions as printed}'." Card 3: `ask` the pharmacist to explain the directions in your language · `gather` all bottles (`bring_medication_list`). Glossary: *generic name*, *refill*, *as needed*.
- **DR** refuses (hard): dosing advice, interactions, "you can skip/stop", whether the medicine is right for the person.
- **RT** `prescription_help`, `language_access`. Pins `hhs_ocr_lep`, `hrsa_fqhc`.
- **CL/PK** "my medicine label — how to take it, and a label in my language" / seed `bring_medication_list`.

#### `discharge_instructions` — after-visit summary
- **RB** "Discharge Instructions", "After Visit Summary", "Follow up with… in {n} days", "Return to the emergency room if…", medication list ("New / Changed / Stopped"), "Activity", "Diet", "Who to call".
- **KF** `appointment` (follow-up date if printed; "in 7 days" → `unresolved`), `contact` printed clinic phone, `action` for each printed instruction category (quoted, not paraphrased into advice).
- **DU** role `appointment`; no floor. Emergency lexicon may fire on the warning-signs list (intended).
- **PF** medication changes are the most missed item; the "return if" list is not a prediction; ask for a translated copy and interpreter (HHS setting).
- **PL** Card 1: "This paper is from your hospital visit on {date}. It lists your medicines, when to come back, and warning signs to watch for." Card 3: `gather` medicines · `call` to book the follow-up · `ask` for a copy in your language. Glossary: *follow-up*, *discharge*.
- **DR** refuses: to judge whether a symptom is serious now (the fixed emergency card does that), to change or explain doses.
- **RT** `primary_care_uninsured`, `language_access`, `medical_bill` (a bill usually follows).
- **CL/PK** "my hospital discharge instructions — my medicines and follow-up visit" / `bring_notice`, `bring_medication_list` **(rec.)**.

#### `vaccine_record` — immunization record
- **RB** "Immunization Record", vaccine names (DTaP, MMR, Tdap, HepB, Varicella…), dates, lot numbers, provider, state registry (IIS) printout.
- **KF** `response_due` only when a school deadline is printed on the same paper; otherwise none.
- **DU** role `response_due`; no floor.
- **PF** school requirements are state-specific (resource `school_vaccine_requirements`); records can be retrieved from the state registry (`cdc_iis`); McKinney-Vento students enroll immediately anyway (information via `nche_mckinney_vento`).
- **PL** Card 1: "This is a list of the vaccines {name} received, with dates." Card 3: `bring` it to the school or clinic · `ask` the clinic which shots the school still needs. Glossary: vaccine abbreviations as printed.
- **DR** refuses: to say the child is "up to date" or which vaccines are missing (a clinical/schedule judgement).
- **RT** `vaccine_records`, `school_enrollment`. Pin `cdc_iis`.
- **CL/PK** "a vaccine record — what it shows and what the school needs" / `bring_vaccine_record` **(rec.)**.

#### `appointment_reminder` — appointment card or letter
- **RB** "Appointment Reminder", date/time/location/provider, "Arrive 15 minutes early", "Bring your insurance card and ID", "Call {n} hours ahead to cancel".
- **KF** `appointment` (+ `time_text`), `contact` printed phone, `document_requested` (insurance card, ID as printed).
- **DU** role `appointment` (medical appointment: `high` ≤ 14 days, never `critical` — D-12 reserves that for ICE/USCIS); no floor.
- **PF** cancellation windows and no-show fees are printed — quote them; arrival buffer.
- **PL** Card 1: "You have an appointment with {provider} on {date} at {time}." Card 3: `bring` · `visit` · `call` to change it. 
- **DR** nothing sensitive; still no medical interpretation of the visit's purpose.
- **RT** `language_access`.
- **CL/PK** "an appointment reminder — the date, time and place" / `bring_notice`, `bring_insurance_card`, `bring_photo_id` **(rec.)**.

### 4.5 Benefits (4 types)

**Common to this group.** `disclaimer_kind=benefits_information_only` ("It is not a decision about your benefits. Only the office that sent it can tell you what happens next."). Verify = the printed caseworker/agency phone. The app **never** states eligibility for any household member and never asks immigration status (D-24); H.R.1 changed Medicaid/CHIP and Marketplace eligibility for many lawfully present immigrants from 2026-10-01 / 2027-01-01 (resources.md *Warnings*: "H.R.1 HEALTH COVERAGE") — the only permitted sentence is the resource warning `warn.hr1_coverage_changes`. Termination or denial letters with hearing rights are `insurance_denial` with `sender_kind=state_agency` (§3.6), not these types. Impersonation is common for SSA (§6). Research: `resources.md §3D`, `§1D`, `§1F`.

#### `medicaid_renewal` — renewal, redetermination, address or information request
- **RB** "Renewal", "Redetermination", "It's time to renew your coverage", "Return this form by", "Address confirmation required", "We need more information", state Medicaid agency letterhead (e.g. "Department of Medical Assistance Services"), case number. A conditional warning ("if we do not hear from you, coverage may end on…") keeps this type; an actual termination with hearing rights → `insurance_denial`.
- **KF** `response_due` (return-by date), `document_requested` (proofs: income, address, household, immigration documents — quoted as printed), `contact` (portal/phone/mail address as printed), `action` (how to return).
- **DU** role `response_due`; no floor (fixture `medicaid_address_confirmation`: `high`, stated 2026-10-14). Rule `medicaid_fair_hearing_90d_max` only when a hearing sentence is printed.
- **PF** coverage lost for paperwork can often be reinstated if the packet arrives within the state's grace window — **general guidance, confirm with the agency** (§9); proofs need not be perfect (ask the office what they accept — a `questions_to_ask` item); more frequent redeterminations are expected under H.R.1.
- **PL** Card 1: "This letter is from {state} Medicaid. Your coverage is not cancelled. They need you to {return the form / confirm your address} by {date}." Card 3: `gather` proofs · `mail`/`submit_online` as printed · `call` with questions (`medicaid_renewal`). Glossary: *Medicaid*, *proof of address*, *redetermination*.
- **DR** refuses: whether the family still qualifies, which members count, what happens if late (beyond the printed sentence). Clerk card appends `clerk.interpreter_hhs` (D-18: `document_type == medicaid_renewal`).
- **RT** `medicaid_renewal`, `benefits_navigation`. Pin `medicaid_state`.
- **CL/PK** "a Medicaid letter — returning what it asks for before the date on it" / seed `bring_notice`, `bring_case_number`, `bring_proof_address`, `bring_proof_income`.

#### `snap_notice` — SNAP interview, verification, expiration, decision
- **RB** "Supplemental Nutrition Assistance Program", "SNAP", "food assistance", "EBT", "Notice of Interview" (phone or in person, date/time), "Notice of Missed Interview", "Request for Verification" (ID, income, rent, utilities), "Notice of Expiration", "Notice of Action". Sender `state_agency`/`local_agency`.
- **KF** `appointment` (interview), `response_due` (verification due), `document_requested` (the printed list), `contact`.
- **DU** roles `appointment`, `response_due`; no floor; an interview ≤ 14 days → `high` (fixture `snap_interview_notice`), never `critical`.
- **PF** a missed interview usually leads to denial (quote the notice); expedited 7-day processing exists (information); eligible children can receive SNAP even when a parent does not apply for themselves — say only "the office can tell you which family members can be included" (resources.md §3D).
- **PL** Card 1: "This is about your SNAP (food) benefits. It sets a phone interview on {date} at {time}." Card 3: `bring`/`gather` the list · `call` if you must reschedule · `ask`. Glossary: *interview*, *verification*, *EBT*.
- **DR** refuses: eligibility of any member, benefit amount predictions.
- **RT** `snap`, `food`, `benefits_navigation`. Pin `snap_state`.
- **CL/PK** "a SNAP (food assistance) notice — my interview or the papers it asks for" / seed `bring_notice`, `bring_household_ids`, `bring_proof_income`, `bring_proof_rent_utilities`.

#### `wic_notice` — WIC appointment or packet
- **RB** "WIC", "Women, Infants, and Children", "certification appointment", "bring", "benefits end / recertify by", clinic name.
- **KF** `appointment`, `response_due`, `document_requested` (ID, proof of residency, proof of income or Medicaid/SNAP/TANF card, the child — as printed).
- **DU** roles `appointment`, `response_due`; no floor.
- **PF** WIC has no immigration-status requirement (FNA, resources.md §1D — information, stated as a fact about the program, not about this person); bring the child; benefits are per certification period.
- **PL** Card 1: "This is from WIC, the food program for pregnant women, babies and young children. It gives your appointment on {date}." Card 3: `bring` list · `visit`. 
- **DR** refuses: income-limit conclusions.
- **RT** `wic`, `food`. Pin `signupwic`.
- **CL/PK** "a WIC notice — my appointment or the papers it asks for" / seed `bring_household_ids`, `bring_proof_address`, `bring_proof_income_or_benefit_card`, `bring_the_child`.

#### `ssa_letter` — Social Security award, denial, overpayment, redetermination, verification
- **RB** "Social Security Administration", "Notice of Award", "Notice of Disapproved Claim", "We paid you too much" / "Overpayment", "SSI Redetermination", "Benefit Verification Letter", "If you disagree… you have 60 days", local office address, ssa.gov.
- **KF** `response_due` (printed appeal/response date only; "60 days after you receive this letter" → `unresolved` — no SSA rule is seeded, the +5 mail days is general guidance), `payment_due` (overpayment amount), `document_requested`, `contact`.
- **DU** role `response_due`; no floor; printed date only.
- **PF** appeal levels (reconsideration → hearing → Appeals Council → court) are glossary information; overpayment letters have waiver and repayment-plan options (quote when printed; else `questions_to_ask`); SSA never threatens arrest or demands gift cards — a letter or call doing so is a scam (`ssa_scams` pinned).
- **PL** Card 1: "This letter is from Social Security. It says {award/denial/overpayment as printed}." Card 3: `call` the printed number · `gather` · `professional` "a legal-aid office or SSA itself can explain your options". Glossary: *reconsideration*, *overpayment*, *SSI vs SSDI*.
- **DR** refuses: whether to appeal or request a waiver, whether benefits will continue.
- **RT** `ssa_benefits`, `benefits_navigation`. Pins `ssa_appeals`, `ssa_scams`.
- **CL/PK** "a Social Security letter — what it says and the date to respond by" / seed `bring_notice`, `bring_photo_id`.

### 4.6 Housing (6 types)

**Common to this group.** `disclaimer_kind=housing_information_only`; verify = the printed landlord/court/agency phone. Eviction law is state- and year-specific and the rules table seeds **no** notice or answer period (D-11; resources.md *Warnings*: "EVICTION RULES ARE STATE- AND YEAR-SPECIFIC"; Va. Code §55.1-1245 changes again 2027-07-01). Any relative period printed by a landlord ("within 14 days") is `unresolved`; a printed pay-by or court date is `stated`. The one legal sentence the app may say is the D-17 template "In {state}, a landlord generally needs a court order before an eviction can happen. Confirm with the legal helpline today." (only when `state` is known); otherwise the fixed notice carries it. LSC-funded legal aid shows `status_note.lsc_restricted` with the alternative link (D-24). Research: `resources.md §3E`, `§1E`.

#### `pay_or_quit` — notice to pay or quit / cure / vacate / terminate tenancy
- **RB** "Notice to Pay Rent or Quit", "5-Day / 14-Day Notice", "Notice to Cure or Quit", "Notice to Vacate", "Termination of Tenancy", amount owed, "within {n} days of the date of this notice", date served, landlord or property-manager signature; `sender_kind=landlord`.
- **KF** `response_due` (`deadline` when a pay-by date is printed; `relative_deadline` for "within 14 days" → `unresolved`), `amount` (role `payment_due`), `contact` landlord phone/address as printed, `move_date` only when a vacate date is printed.
- **DU** role `response_due`; **floor `high`** (D-12 as revised 2026-09-27: `urgency.high.floor` with `floor_applied: true` when no date) — fixture `va_pay_or_quit_14d` prints a date → `stated`, `high`. Rules: none, ever.
- **PF** it is not a court order (fixed notice `fixed.pay_or_quit`); paying or curing within the period usually stops the process — say "the notice says paying by {date} stops it" only if printed; rent-assistance programs need the notice and the lease (`bring_notice`, `bring_lease`); notices are sometimes defective — only a lawyer can say so.
- **PL** Card 1: "Your landlord says you owe {amount} and must pay by {date} or move out. This is a warning, not a court order." Card 2: amount, date, phrase. Card 3: `professional` **first** ("Talk to a housing lawyer or counselor before the date on this paper", tags `eviction`, `housing_counseling`) · `call` rent assistance (`rent_assistance`) · `gather` lease, receipts. Glossary: *pay or quit*, *cure*, *terminate tenancy*.
- **DR** refuses (hard): "you have to leave by", "you do not have to leave", computing the period, whether the notice is valid.
- **RT** `eviction`, `housing_counseling`, `rent_assistance`. Pins `hud_counselor`, `va_code_pay_or_quit`, `va_courts_landlord_tenant` (geo-filtered).
- **CL/PK** "a notice from my landlord about rent — what it says and the date on it" / seed `bring_notice`, `bring_lease`.

#### `eviction_summons` — summons, unlawful detainer, complaint for possession
- **RB** "SUMMONS FOR UNLAWFUL DETAINER", "Summons", "Complaint for Possession", court name, case number, "Plaintiff / Defendant", "Return date" / "You are summoned to appear on", "If you fail to appear, judgment may be entered against you"; `sender_kind=court`.
- **KF** `hearing_date` (+ `time_text`, court address as `contact`), `amount` claimed (role `payment_due`, `ambiguity_note` "amount the landlord claims"), `document_requested` rarely.
- **DU** role `hearing_date` → **`critical` ≤ 7 days** (eviction court date, D-12); **floor `high`**; past ≤ 60 days → `critical` date-passed (it is a court paper, §5.1). Rules: none. Verify: printed clerk phone.
- **PF** the court date is the deadline that matters (fixed notice `fixed.eviction_summons`); answer periods, post-judgment appeal windows and sheriff notices vary by state (never computed; `warn.lsc_eviction_db_2021` marks the staff database); bring the lease and payment proof; legal aid should be called *today*.
- **PL** Card 1: "This is a court paper. Your landlord asked the court to end your tenancy. The court date is {date} at {time}." Card 3: `professional` **today** (`eviction`) · `bring` summons, lease, rent receipts · `visit` "Go to court on the date, even without a lawyer yet". Glossary: *unlawful detainer*, *summons*, *default judgment*, *plaintiff*.
- **DR** refuses: defenses, whether to move, what the judge will do, computing any period.
- **RT** `eviction`, `housing_counseling`. Pins `va_courts_landlord_tenant`, `va_eviction_helpline`, `lawhelp`, `hud_counselor`.
- **CL/PK** "a court paper about eviction — the court date and finding legal help" / seed `bring_the_summons`, `bring_lease`, `bring_proof_rent_utilities`.

#### `lease` — lease or renewal
- **RB** "Residential Lease Agreement", "Term", "Rent", "Due on the 1st", "Late fee", "Security deposit", "Notice to vacate {n} days", "Automatic renewal", "Occupants", "Pets". Often in Spanish (fixture `spanish_lease`: `detected_language: es`, `document_language_differs` when the UI language differs).
- **KF** `move_date` (term start), `expiry` (term end), `amount` (monthly rent, role `payment_due`, `ambiguity_note` "monthly; no single due date"), `action` for notice and renewal clauses as quoted.
- **DU** roles `move_date`, `payment_due`, `expiry`; no floor; usually `info` (a term end ≤ 30 days → `medium`).
- **PF** auto-renewal and notice clauses drive later surprises; deposits and late fees are quoted, never judged; the lease language may differ from the tenant's spoken language — the translation view (S8) is the tool.
- **PL** Card 1: "This is a lease for {address as printed}. It runs from {date} to {date}. Rent is {amount}." Card 3: `gather` a signed copy · `ask` the landlord about unclear clauses · `professional` "a housing counselor can review it". Glossary: *security deposit*, *late fee*, *auto-renewal*, *notice period*.
- **DR** refuses: whether terms are fair or legal, whether to sign.
- **RT** `housing_counseling`. Pin `hud_counselor`.
- **CL/PK** "a lease — the rent, the dates and the rules in it" / `bring_lease` **(rec.)**.

#### `rent_increase` — rent increase notice
- **RB** "Notice of Rent Increase", "effective {date}", "your new rent will be", "sign the renewal by", "if you do not wish to renew".
- **KF** `move_date` (effective date — the master table's role for this type), `amount` (new rent, `payment_due`), `response_due` (sign-by date if printed).
- **DU** roles `move_date` (thresholds), `response_due`; no floor.
- **PF** notice periods vary by state and lease (never stated — "general guidance", §9); rent-controlled or subsidized units have their own rules (professional).
- **PL** Card 1: "Your landlord says rent will go up to {amount} starting {date}." Card 3: `gather` the lease · `professional` "a housing counselor can tell you whether the notice follows your lease and local rules" · `call` rent assistance.
- **DR** refuses: whether the increase is allowed or how much notice is required.
- **RT** `housing_counseling`, `rent_assistance`. Pin `hud_counselor`.
- **CL/PK** "a rent increase notice — the new amount and the date it starts" / `bring_notice`, `bring_lease` **(rec.)**.

#### `section8_recert` — Housing Choice Voucher recertification
- **RB** "Annual Reexamination", "Recertification", "Housing Choice Voucher", "HCV", "Section 8", "Public Housing Agency"/"PHA", "return these forms by", "appointment", "failure to comply may result in termination of assistance"; `sender_kind=local_agency`.
- **KF** `response_due`, `appointment`, `document_requested` (income, household, ID as printed), `contact`.
- **DU** roles `response_due`, `appointment`; no floor.
- **PF** missed paperwork is the common reason for termination (quote the paper's sentence); household changes must be reported (as printed); interim recertifications exist (information).
- **PL** Card 1: "Your housing agency needs yearly paperwork to keep your voucher. Return it by {date}{ and come on {date}}." Card 3: `gather` · `mail`/`visit` · `call` the caseworker. Glossary: *voucher*, *reexamination*, *PHA*.
- **DR** refuses: eligibility or rent-share calculations.
- **RT** `section8`, `housing_counseling`. Pin `hud_pha`.
- **CL/PK** "my housing voucher recertification — the papers and the date" / seed `bring_notice`, `bring_proof_income`, `bring_household_ids`.

#### `utility_shutoff` — disconnection notice
- **RB** "Disconnection Notice", "Final Notice Before Disconnection", "Termination of Service", "service may be shut off on or after {date}", amount past due, "payment arrangement", "medical certificate", utility letterhead; `sender_kind=utility`.
- **KF** `response_due` (the shutoff date — master table: `payment_due` with the shutoff date as `response_due`), `amount` (`payment_due`), `action` (payment-plan / medical-certificate sentence as printed), `contact` utility phone.
- **DU** roles `payment_due`/`response_due`; **floor `high`**; no rule.
- **PF** payment plans and medical protections exist in many states — "ask the utility" (general guidance, §9); LIHEAP crisis funds (`liheap`, `211`); utility impersonation scams demand payment "within one hour" by prepaid card (§6: payment-method signal + `urgency_pressure` on a `utility` sender → `possible`; with a non-matching domain → `likely`).
- **PL** Card 1: "Your {utility} says it may shut off service on {date} unless {amount} is paid." Card 3: `call` the printed number today and ask about a payment plan · `call` LIHEAP/211 (`utility_shutoff`) · `gather` (`bring_shutoff_notice`, income proof). Glossary: *disconnection*, *payment arrangement*, *medical certificate*.
- **DR** refuses: whether the shutoff is lawful, whether protections apply to this household.
- **RT** `utility_shutoff`, `rent_assistance`. Pins `liheap`, `211`.
- **CL/PK** "a utility shutoff notice — the amount, the date, and a payment plan" / seed `bring_shutoff_notice`, `bring_proof_income`, `bring_household_ids`.

### 4.7 School (5 types)

**Common to this group.** `disclaimer_kind=general_information`; `sender_kind=school` (or `local_agency` for health departments); verify = the printed school phone. The app is for parents and guardians (18+; compliance.md *Warnings*: never market to students) and every sentence must be safe for a child to read aloud to a parent. Two fixed facts may appear only as resource warnings, never as model prose: `warn.schools_may_not_ask_status` (Plyler) and McKinney-Vento immediate enrollment (`nche_mckinney_vento`). Interpreter and translation rights in IDEA meetings are information routed to PTI centers. Research: `resources.md §3F`, `§1N`.

#### `school_enrollment` — registration packet
- **RB** "Registration", "Enrollment packet", "Proof of residency", "Birth certificate", "Immunization record", "Home language survey", "Emergency contacts", "Return by", "Registration appointment".
- **KF** `response_due`, `appointment`, `document_requested` (the printed list — quote alternatives the packet itself allows, e.g. "or other proof of age"), `contact`.
- **DU** roles `response_due`, `appointment`; no floor.
- **PF** families without a fixed address or records can still enroll immediately (McKinney-Vento — route to the liaison directory, tag `homeless_students` when the packet mentions residency proof and the user's paper or hint mentions a shelter, motel, or doubling up); SSNs are optional; interpreters can be requested (`ask` step).
- **PL** Card 1: "This is the paperwork to enroll {child} in school. It lists the papers the school asks for and the date." Card 3: `gather` · `visit` · `ask` "Ask for the forms in your language and an interpreter for the meeting". Glossary: *proof of residency*, *home language survey*.
- **DR** refuses: whether the family "qualifies" for a school or program.
- **RT** `school_enrollment`, `homeless_students`. Pins `plyler_explainer`, `nche_mckinney_vento`.
- **CL/PK** "enrolling my child in school — the forms and papers needed" / seed `bring_proof_address`, `bring_vaccine_record`.

#### `immunization_notice` — vaccine compliance or exclusion notice
- **RB** "Immunization compliance", "Your child is missing the following vaccines", "will be excluded from school on {date}", "conditional enrollment expires", vaccine list, school nurse signature or health-department letterhead.
- **KF** `response_due` (exclusion/compliance date), `document_requested` (the listed vaccines or the record), `contact` school nurse phone.
- **DU** role `response_due`; no floor (fixture `school_immunization_notice`: `medium`).
- **PF** requirements and exemptions are state-specific (`school_vaccine_requirements`); records may exist in the state registry (`cdc_iis`); catch-up shots are available at health centers and health departments (`hrsa_fqhc`).
- **PL** Card 1: "The school says {child} needs {n} vaccines on file by {date}." Card 3: `gather` the record · `call` the clinic or health department for the listed shots · `bring` the record to the school. Glossary: *exclusion*, *conditional enrollment*, vaccine abbreviations.
- **DR** refuses: medical statements about the vaccines themselves; whether an exemption applies.
- **RT** `vaccine_records`, `school_enrollment`. Pins `school_vaccine_requirements`, `cdc_iis`.
- **CL/PK** "a school vaccine notice — which vaccines it lists and the date" / seed `bring_notice`, `bring_vaccine_record`.

#### `iep_504_notice` — IEP / 504 meeting or prior written notice
- **RB** "Prior Written Notice", "Notice of Meeting", "Individualized Education Program (IEP)", "Section 504", "Eligibility determination", "Procedural Safeguards", "Consent for evaluation / initial services", meeting date/time/place, "you may bring".
- **KF** `appointment` (meeting), `response_due` (consent or reply-by date), `document_requested`, `contact` case manager.
- **DU** roles `appointment`, `response_due`; no floor.
- **PF** IEP (specialized instruction under IDEA) vs 504 (accommodations under civil-rights law) — glossary only; parents may ask for an interpreter and translated safeguards; signing "attended" is not consent (quote the form's own wording); free Parent Training and Information Centers help prepare (`pti_centers`).
- **PL** Card 1: "The school invites you to a meeting about {child}'s learning plan on {date}." Card 3: `ask` for an interpreter · `gather` reports (`bring_school_records`) · `professional` = "a parent center can help you prepare" (`special_education`). Glossary: *IEP*, *504 plan*, *evaluation*, *procedural safeguards*.
- **DR** refuses: whether the child needs services, whether to give consent.
- **RT** `special_education`. Pin `pti_centers`.
- **CL/PK** "a school meeting notice about my child's education plan — I need an interpreter at the meeting" / seed `bring_notice`, `bring_school_records`.

#### `school_meals` — free or reduced-price meal application or direct-certification letter
- **RB** "Application for Free and Reduced Price School Meals", household income grid, "Direct certification", "Your child has been approved for free meals" (the letter states the decision — quote it).
- **KF** `response_due`, `document_requested` (income or case number as printed), `contact`.
- **DU** role `response_due`; no floor.
- **PF** families on SNAP/Medicaid are often certified automatically (information); one application covers all children in the household (as printed).
- **PL** Card 1: "This is the school meals {application / approval letter}." Card 3: `gather` · `submit_online`/`mail` as printed.
- **DR** refuses: income-eligibility conclusions.
- **RT** `school_meals`, `food`. Pin `school_meals`.
- **CL/PK** "the school meals application or letter" / `bring_proof_income`, `bring_household_ids` **(rec.)**.

#### `report_card` — report card or progress report
- **RB** grades, "Progress report", "Marking period", teacher comments, "Parent-teacher conference".
- **KF** none drive urgency (master table); a printed conference date may be extracted as `appointment` for the user's benefit only.
- **DU** always `info` (`urgency.info.no_action` or `.no_date`).
- **PF** grading scales differ; comments carry the message; a conference with an interpreter can be requested.
- **PL** Card 1: "This is {child}'s report card for {period}." Card 3: `ask` for a meeting with an interpreter. Glossary: grading scale terms as printed.
- **DR** refuses: judgements about the child's progress.
- **RT** `language_access`.
- **CL/PK** "my child's report card — I would like a meeting with the teacher and an interpreter" / `bring_school_records` **(rec.)**.

### 4.8 Employment (4 types)

**Common to this group.** Category `employment`, `disclaimer_kind=legal_information_only`, `sender_kind=employer`; verify = the employer's printed contact. Workers' rights resources serve regardless of status (DOL WHD, EEOC, OSHA — resources.md §1M); the app never concludes "this is wage theft / discrimination / retaliation" — it shows the numbers and routes. EEOC (180/300 days) and OSHA retaliation (30 days) rules apply only when a paper prints the phrase and an anchor (§5.3). Research: `resources.md §3G`.

#### `w2_1099` — W-2, 1099-NEC/MISC/K
- **RB** "Wage and Tax Statement", "Form W-2", numbered boxes (1 Wages, 2 Federal income tax withheld, 12 codes…), "Employer identification number (EIN)", "Form 1099-NEC Nonemployee compensation", "1099-K".
- **KF** none (informational); amounts stay in the transcript; a missing/incorrect SSN or "APPLIED FOR" → tag `itin`.
- **DU** `info` (fixture `w2_form`).
- **PF** a 1099 means no tax was withheld (glossary, not advice); ITIN holders can file (information via `irs_itin`); the form is needed by the filing season, not "due" itself.
- **PL** Card 1: "This is your {W-2 / 1099} from {employer} for {year}. It shows what you were paid and what tax was taken out." Card 3: `gather` for tax filing · `professional` = "a free tax-help site or tax professional". Glossary: *EIN*, *withholding*, *nonemployee compensation*.
- **DR** refuses: refund predictions, whether to file, how to report income.
- **RT** `tax_notice`, `itin` (no SSN shown).
- **CL/PK** "a tax form from my employer (W-2 or 1099) — what the boxes mean" / `bring_notice` **(rec.)**.

#### `i9` — Form I-9 and re-verification requests
- **RB** "Employment Eligibility Verification", "Form I-9", "Section 1 / 2", "Supplement B, Reverification and Rehire", "List A / List B / List C", "document expiration date", employer letter "your work authorization document expires on {date}; provide updated documents by {date}".
- **KF** `response_due` (employer's date), `expiry` (document expiry), `document_requested` (the lists as printed), `contact`.
- **DU** roles `response_due`, `expiry`; no floor.
- **PF** employers may no longer accept an I-797C receipt alone for I-765 renewals filed on/after 2025-10-30 (fixed notice `fixed.uscis_receipt_i765` when such a receipt is referenced); the employee chooses which acceptable documents to show (quote the form's rule; never pick for them).
- **PL** Card 1: "Your employer is asking for proof that you may work, by {date}. The form lists the kinds of documents it accepts." Card 3: `gather` · `professional` "if your permit is being renewed" (`work_permit`) · `ask` HR. Glossary: *reverification*, *List A/B/C*.
- **DR** refuses: whether the person may keep working, which document to present.
- **RT** `work_permit`, `workers_rights`. Pin `uscis_i765`.
- **CL/PK** "the work eligibility form (I-9) — what documents it lists and the date" / `bring_notice`, `bring_photo_id` **(rec.)**.

#### `offer_letter` — job offer or hiring letter
- **RB** "Offer of Employment", position, pay rate, start date, "at-will", "contingent upon background check / E-Verify", "sign and return by".
- **KF** `response_due` (sign-by), `other` (start date), `amount` (pay as printed, role `other`), `document_requested` (onboarding items).
- **DU** roles `response_due`, `other`; no floor.
- **PF** fake job offers ask for fees, check deposits, or personal data before the first day (`ftc_job_scams` pinned; §6 signals: payment method, `scam.guaranteed` for "guaranteed visa sponsorship", `urgency_pressure`; an upfront-fee reason key is requested in §9).
- **PL** Card 1: "This is a job offer from {employer}: {position}, {pay}, starting {date}. They ask you to sign by {date}." Card 3: `gather` · `ask` about anything unclear · `verify` the company through its printed contact.
- **DR** refuses: whether to accept, whether the pay is legal, immigration effects of the job.
- **RT** `workers_rights`. Pin `ftc_job_scams`.
- **CL/PK** "a job offer letter — the pay, start date and what to sign" / `bring_notice` **(rec.)**.

#### `pay_stub` — earnings statement
- **RB** "Earnings Statement", "Pay period", "Gross pay", "Net pay", "Hours", "Rate", "Deductions" (federal, state, FICA, insurance), "YTD".
- **KF** none drive urgency; amounts and hours stay in the transcript. Rules `eeoc_180_300d`, `osha_retaliation_30d` only via a printed phrase on an accompanying employer letter (rare).
- **DU** `info`.
- **PF** hours × rate not matching gross is a *question*, not a conclusion (overtime, tips, salary); missing deductions or "cash" pay are worth asking about; keep stubs and a personal hours log (`bring_hours_log`) — that is what WHD asks for.
- **PL** Card 1: "This is your pay stub for {period}. It shows {hours} hours at {rate}, {gross} before deductions and {net} paid." Card 3: `gather` stubs + hours log · `professional` = "a workers' rights office can check your pay for free" (`wage_theft`). Glossary: *gross*, *net*, *FICA*, *YTD*.
- **DR** refuses: "you were underpaid", legal conclusions about status or overtime.
- **RT** `wage_theft`, `workers_rights`. Pin `dol_whd`.
- **CL/PK** "my pay stub — my hours, pay and deductions" / seed `bring_pay_stubs`, `bring_hours_log`, `bring_employer_info`.

### 4.9 Tax and civic (3 types)

**Common to this group.** `irs_notice` and `itin`: category `tax`, `disclaimer_kind=general_information`, `sender_kind=federal_agency`; the IRS contacts people by mail first and never demands gift cards or threatens deportation (resources.md §3H) — a letter doing so is re-typed `other_notice` (§6.5). `jury_summons`: category `civic`, `legal_information_only`, `sender_kind=court`, and the single most important fixed notice in the app (D-20). Research: `resources.md §3H`, `§3I`.

#### `irs_notice` — CP / LTR notices
- **RB** "Department of the Treasury — Internal Revenue Service", notice number top-right (CP14, CP2000, CP501/503/504, CP49, CP12, LTR 3172…), "Notice date", "Tax year", "Amount due", "Pay by", "Respond by", "If you agree / If you disagree".
- **KF** `response_due`, `payment_due` (amount + date), `document_requested`, `contact` (printed IRS number and irs.gov page as printed).
- **DU** roles `response_due`, `payment_due`; printed date only; no floor (fixture `irs_cp_notice`: `medium`).
- **PF** the notice number is the key to the IRS lookup page (`irs_notice_lookup`); "agree/disagree" is a filing decision the app never makes; payment plans exist (information); Low Income Taxpayer Clinics are not yet seeded (§9).
- **PL** Card 1: "This is IRS notice {number} about your {year} taxes. It says {amount due / a change / a request} by {date}." Card 3: `verify` the notice number on the IRS lookup page · `call` the printed number · `professional` "a free tax clinic or tax professional". Glossary: *notice number*, *tax year*, *proposed change*.
- **DR** refuses: whether the person owes the amount, whether to agree, refund/penalty predictions.
- **RT** `tax_notice`. Pins `irs_notice_lookup`, `irs_scams`.
- **CL/PK** "an IRS letter — what it says and the date to respond by" / seed `bring_notice`, `bring_tax_return`.

#### `itin` — ITIN assignment, renewal, rejection (W-7)
- **RB** "Individual Taxpayer Identification Number", "ITIN", "Form W-7", "CP565" (assigned), "CP566" (more information needed), "CP567" (rejected), "your ITIN will expire", "Certifying Acceptance Agent".
- **KF** `response_due` (CP566 reply date), `expiry` (ITIN expiry as printed), `document_requested` (passport or two IDs — as printed), `contact`.
- **DU** roles `response_due`, `expiry`; no floor.
- **PF** ITINs expire after years of non-use (general guidance, §9); original documents or certified copies are needed (quote); CAAs and VITA sites can help (`irs_itin`).
- **PL** Card 1: "This letter is about your ITIN (a tax ID number for people without a Social Security number). It says {assigned / needs more information / was rejected}." Card 3: `gather` (`bring_passport_or_two_ids`) · `professional` "a certifying acceptance agent or free tax site". Glossary: *ITIN*, *W-7*, *acceptance agent*.
- **DR** refuses: whether the person should get an ITIN or file taxes.
- **RT** `itin`, `tax_notice`. Pin `irs_itin`.
- **CL/PK** "my ITIN (tax ID number) letter or application" / seed `bring_passport_or_two_ids`, `bring_tax_return`.

#### `jury_summons` — summons or juror qualification questionnaire
- **RB** "Summons for Jury Service", "Juror Qualification Questionnaire", "You are hereby summoned", "Report date", "Complete and return within 10 days", "Are you a citizen of the United States?", penalties for failing to respond, court letterhead (federal district court or state court).
- **KF** `response_due` (questionnaire return date; "within 10 days" → `unresolved`), `appointment` (report date), `contact` jury office phone/site as printed.
- **DU** roles `response_due`, `appointment`; no floor (fixture `jury_summons`: `medium`).
- **PF** noncitizens must **answer** the form marking non-citizen, never ignore it, never check "citizen", never register to vote (fixed notice `fixed.jury_summons`, severity `high`; resource warnings `warn.jury_never_check_citizen`, `warn.jury_never_register_to_vote`; resources.md *Warnings*: "JURY SUMMONS"); exemptions and excuses are the court's decision.
- **PL** Card 1: "This is a jury summons from {court}. It asks you to answer a form by {date}{ and report on {date}}." Card 3: `submit_online`/`mail` the form as printed · `call` the jury office with questions · `professional` "if you are unsure about the citizenship question". Glossary: *juror*, *qualification questionnaire*, *excuse*.
- **DR** refuses: whether the person is excused or exempt; anything about voting beyond the fixed sentence.
- **RT** `jury_summons`. Pin `uscourts_jury`.
- **CL/PK** "a jury summons — answering the form before its due date" / seed `bring_the_summons`.

### 4.10 `other_notice` and `unknown` (2 types)

#### `other_notice` — a readable official-looking paper that fits no finer type
- **RB** legible, at least two lines, a sender or subject, but no §3 rule matches (bank letters, insurance marketing, debt collectors for non-medical debt, DMV renewals, court papers outside removal/traffic/eviction, scam letters impersonating any agency — §3.11). `category` = best fit; `sender_kind` as printed or `unknown` (§3.15 adds `unusual_contact` when money or data is demanded with no sender).
- **KF** any printed Demand kinds; roles as printed. **DU** thresholds only; no floor; rules `eeoc_180_300d`/`osha_retaliation_30d` when `category=employment`. Verify: printed phone.
- **PF** this is where scams land (fixture `scam_gift_card_letter`: `other_notice`/`immigration`, `scam_risk: likely`, `resource_tags[0] == scam_report`); the model must not "upgrade" an unclear paper to a finer type with `document_type_confidence=high`.
- **PL** Card 1 states the sender and subject as written and says plainly "I could not match this to a known kind of paper. Here is what it says." Card 3: `call` the printed number **only if the paper is not a suspected scam** · `professional` by category · `verify`.
- **DR** refuses everything the category's finer types refuse; with `scam_risk=likely` the plan never says "call the number on the paper" (the scam card carries reporting resources).
- **RT** by category: `immigration` → `immigration_legal_help`; `court` → `court_notice`, `immigration_legal_help`; `medical` → `language_access`; `benefits` → `benefits_navigation`; `housing` → `housing_counseling`; `school` → `school_enrollment`; `employment` → `workers_rights`; `tax` → `tax_notice`; `civic`/`other` → none (211 fallback). `scam_report` first whenever `scam_risk ≠ none`.
- **CL/PK** "reading a paper I got" (= `clerk.generic_need`) / none.

#### `unknown` — unreadable or not a document
- **RB** `quality.legibility=poor`, fewer than two readable lines, or not a document (a face, a room, a blank page). `quality.readable=false`, `reason` set; the pipeline stops after the first model call (fixture `blurry_unreadable_page`: exactly one call).
- **KF/DU/PF/PL** none — S6 shows the page with the re-scan tips ("Try again in brighter light / flatten the page"); no cards, no urgency (`info`), no clerk line (the generic card is offered), no tags (Help tiles only), `disclaimer_kind=general_information`.
- **DR** the app never guesses a type from a fragment; if part of a page is readable and clearly official, the model may return `other_notice` with `legibility=partial` and `warnings: [low_quality_image]` instead.
- **RT** none. **CL/PK** none.

---

## 5. Urgency: roles, floors, `verify_resource_id`, rule applicability

Owner: `analysis/urgency.py` (D-12) and `analysis/deadline_rules.py` + `data/rules/deadlines.yaml` (D-11). Everything here is computed in code from **verified** Demands; the model never sets a level, a date kind or a rule. Copy keys are PRODUCT_SPEC §5.5.

### 5.1 The algorithm (`compute_urgency(doc_type, category, demands, safety, today) -> Urgency`)

`today` is the server date in the user's state's time zone when `state` is supplied, else `America/New_York`; it is injected so tests are deterministic.

1. **Emergency.** `safety.emergency` → `level=emergency`, `headline_key=urgency.emergency.headline`, no date fields. Stop.
2. **Candidates.** Verified Demands (`verified=true`, never anything in `unverified[]`) with `date.kind=="stated"`, `value_iso` set, and `role` in the type's **driving roles** (§5.2). `estimated` dates form a second list. `notice_date`, `decision_date` and `other` never drive urgency (they are anchors).
3. **Future stated date** (`days_until ≥ 0`; each candidate is levelled and the **most severe** level wins, ties → the nearest date, then table order — code-authoritative, CL-021(a): a nearer non-critical date never hides a critical-set date ≤ 7 days away): `critical` when `days_until ≤ 7` **and** the Demand is in the type's **critical set** (§5.2); otherwise `high` ≤ 14, `medium` ≤ 30, `info` beyond. Headlines: `urgency.critical.date_today` (`days_until == 0`, critical set) · `urgency.critical.date_soon` · `urgency.high.date_soon` · `urgency.medium.date_soon` · `urgency.info.date_later`. `nearest_date_iso`, `days_until`, `driving_demand_id` are set; `past_date=false`.
4. **Past stated date only** (no future candidate; nearest `−60 ≤ days_until < 0`): `past_date=true`, `headline_key=urgency.critical.date_passed` (PRODUCT_SPEC §5.5: the headline is `date_passed` whenever `past_date`). Level: `critical` when `category ∈ {immigration, court}` (D-12: "past by ≤ 60 days on court/USCIS documents"; ICE and traffic papers included) or `doc_type == eviction_summons` (a court paper filed under `housing`; `urgency.PAST_CRITICAL_TYPES`, matching §5.2's "critical (court)" — CL-030(f)); otherwise **WP2 interpretation, flagged in §9.1**: `high` when the role is `response_due`, `payment_due`, `appointment` or `hearing_date`; `medium` when it is `expiry` or `move_date`. Code also appends `RedFlag{kind: expired_date, severity: medium, text: t_server("urgency.critical.date_passed", date=value_verbatim), source_quote, span_ids, page, fixed_copy_key: null, verified: true}`. Dates past by more than 60 days are ignored for urgency (they are usually notice dates).
5. **Estimated dates only.** Nearest future `estimated` date → thresholds as step 3 **capped at `medium`** (D-12: estimated never above medium); `headline_key=urgency.medium.estimated`; `driving_demand_id` = that Demand. A past estimated date is ignored.
6. **Floor.** If `doc_type ∈ FLOORS = {nta, hearing_notice, eviction_summons, uscis_noid, utility_shutoff, pay_or_quit}` and the level so far is below `high`: `level=high`, `floor_applied=true`; the headline becomes `urgency.high.floor` when no date drove the level, and stays the date headline (the client adds `urgency.floor_note`) when a date did. `urgency.critical.floor` is reserved — no rule emits it today (§9.1).
7. **Nothing found.** `demands` empty → `urgency.info.no_action`; demands without dates → `urgency.info.no_date`. `level=info`.
8. **Verify CTA.** `verify_resource_id` by §5.2: `"uscis_contact"` for USCIS types, `"eoir_hotline"` for EOIR types, `null` otherwise (the client falls back to a `contact` Demand's printed phone). Set whenever a date drives the banner (steps 3–5); `null` in steps 1, 6-without-date and 7.
9. **Scam interplay.** When `scam_risk == likely` the paper has been re-typed to `other_notice` (§6.5), so no floor and no USCIS/EOIR verify CTA apply; dates still compute, and the scam card renders above the banner (S7 order). A cap is proposed in §9.1.

`headline_params` always carries `{"date": value_verbatim}` for date headlines (LTR-isolated by the client). `days_until` is negative for past dates.

### 5.2 Driving roles, critical set, floors and verify resource per type

Only roles listed as **Roles → urgency** in §2 are driving roles; the table below adds the critical set and the verify family. "USCIS types" = `uscis_receipt`, `uscis_rfe`, `uscis_noid`, `uscis_biometrics`, `uscis_interview`, `uscis_approval`, `uscis_denial`, `ead_related`, `green_card_related`, `tps_related`, `asylum_fee_notice`, `parole_related`. "EOIR types" = `nta`, `hearing_notice`, `ij_decision`, `bia_notice`.

| Types | Driving roles | Critical set (≤ 7 days → `critical`) | Floor | Past ≤ 60 d | `verify_resource_id` |
|---|---|---|---|---|---|
| `uscis_receipt`, `uscis_approval`, `ead_related`, `green_card_related`, `parole_related` | `expiry`, `response_due` (where listed) | — | — | `critical` | `uscis_contact` |
| `uscis_rfe`, `uscis_denial`, `tps_related` | `response_due` (+ `expiry` for TPS) | — | — | `critical` | `uscis_contact` |
| `uscis_noid` | `response_due` | — | **`high`** | `critical` | `uscis_contact` |
| `uscis_biometrics`, `uscis_interview` | `appointment` (+ `response_due` interview evidence) | `appointment` | — | `critical` | `uscis_contact` |
| `asylum_fee_notice` | `payment_due` | `payment_due` | — | `critical` | `uscis_contact` |
| `ice_checkin` | `appointment` | `appointment` | — | `critical` | `null` (printed ICE office) |
| `nta`, `hearing_notice` | `hearing_date` | `hearing_date` | **`high`** | `critical` | `eoir_hotline` |
| `ij_decision`, `bia_notice` | `response_due` | — | — | `critical` | `eoir_hotline` |
| `traffic_court` | `hearing_date`, `payment_due` | `hearing_date` | — | `critical` | `null` (clerk) |
| `eviction_summons` | `hearing_date` | `hearing_date` | **`high`** | `critical` (court) | `null` (clerk) |
| `pay_or_quit` | `response_due`, `payment_due` (CL-021(a)) | — | **`high`** | `high` | `null` |
| `utility_shutoff` | `payment_due`/`response_due` | — | **`high`** | `high` | `null` |
| `medical_bill`, `eob`, `insurance_denial`, `prior_auth` | `payment_due` / `response_due` / `expiry` as listed | — | — | `high` (`expiry`: `medium`) | `null` |
| `lab_result`, `discharge_instructions`, `appointment_reminder`, `vaccine_record`, `prescription_label` | `appointment` / `response_due` / `expiry` as listed | — | — | `high` (`expiry`: `medium`) | `null` |
| `medicaid_renewal`, `snap_notice`, `wic_notice`, `ssa_letter` | `response_due`, `appointment` | — | — | `high` | `null` |
| `lease`, `rent_increase`, `section8_recert` | `move_date`, `payment_due`, `expiry`, `response_due`, `appointment` as listed | — | — | `high` / `medium` | `null` |
| `school_enrollment`, `immunization_notice`, `iep_504_notice`, `school_meals` | `response_due`, `appointment` | — | — | `high` | `null` |
| `i9`, `offer_letter`, `irs_notice`, `itin`, `jury_summons` | as listed in §2 | — | — | `high` / `medium` | `null` |
| `report_card`, `w2_1099`, `pay_stub`, `unknown` | none | — | — | — | `null` |
| `other_notice` | any printed | none | — | by category (`immigration`/`court` → `critical`) | `null` |

RESOURCE_DB §4.6 `urgent_doc_boost` mirrors the floors plus `asylum_fee_notice` and `ice_checkin`; keep the two lists in sync when a floor changes (a unit test in `test_urgency.py` reads `_meta.yaml`).

### 5.3 Rule → document-type applicability (`data/rules/deadlines.yaml`)

`deadline_rules.py` emits `kind=estimated` only when all four D-11 conditions hold: (a) the paper prints a relative phrase matching `pattern`; (b) the anchor is a **verified, stated** Demand whose `role == anchor_role`; (c) `doc_type ∈ applies_to_doc_types` — and, the **category gate**, on the catch-all `other_notice` (also the scam re-type target) the employment rules `eeoc_180_300d` and `osha_retaliation_30d` apply only when `category == employment` (`deadline_rules.OTHER_NOTICE_RULE_CATEGORY`), so a debt collector's "within 30 days" never gets an estimate cited to the OSHA retaliation rule; `pay_or_quit` and `eviction_summons` never get one at all (`NEVER_ESTIMATE_TYPES`); (d) `valid_until` is unset or in the future. Otherwise the phrase is `unresolved` and the client shows `demand.ask_sender_date`. A printed date on the same Demand always wins (`stated`). `formula` is rendered as "{anchor_quote} + {days} {calendar|business} days{ (+{mail_days} mail days)}"; `receipt_based: true` adds "must be *received* by" to `notes_en` ("of receiving …" phrases are not marked `receipt_based`; with the category gate that path is unreachable for non-employment letters). The estimate's `DateInfo.localized_line` is the readable date written like the printed anchor (`deadline_rules.estimate_text`: "October 17, 2026", or "11/13/2026" for a numeric anchor; Phase 2C). Numeric dates are read in the paper's order (an order cue on the page, else `paper_default_order` — month first for US-issued types); the reader's `Preferences.date_format` is never a parser input (AI_PROMPTS §11.4). Business days use the federal-holiday table in `deadline_rules.py` with `zoneinfo`. `rule_verification: likely` renders `demand.rule_likely` and never raises urgency above `medium` (it is `estimated` anyway).

| `id` | `applies_to_doc_types` | `pattern` (regex on `relative_rule_text`, case-insensitive) | days / basis | `anchor_role` | receipt / mail | `source_url` | `verification` / `valid_until` | notes |
|---|---|---|---|---|---|---|---|---|
| `ar11_10d` | the 8 types in the verbatim API_CONTRACT §3.10 entry: `uscis_receipt`, `uscis_rfe`, `uscis_biometrics`, `uscis_interview`, `uscis_approval`, `ead_related`, `green_card_related`, `tps_related` (§2 also marks `uscis_noid` and `parole_related` — §9.4 item 4) | `within (10\|ten) days of (moving\|your move\|the move)` | 10 / calendar | `move_date` | no / 0 | uscis.gov/addresschange | verified / — | Move-anchored: a paper never prints the user's move date, so this rule is documentary (`/v1/rules`, fixed notice) and yields `estimated` only if a letter prints both the phrase and a move date. |
| `bia_appeal_30d` | `ij_decision` | `(within\|no later than) (30\|thirty) (calendar )?days` | 30 / calendar | `decision_date` | **yes** / 0 | justice.gov/eoir/policy-manual-eoir/part-III/bia/chapter-3-5 | **likely** / 2027-03-31 | Verbatim entry in API_CONTRACT §3.10; the Board cannot extend. |
| `eoir33_5bd` | `nta`, `hearing_notice`, `ij_decision`, `bia_notice` | `within (5\|five) (working\|business) days` | 5 / business | `move_date` | no / 0 | justice.gov/eoir/update-respondent-or-alien-information (compliance.md §7, *likely*) | likely / 2027-03-31 | Move-anchored like `ar11_10d`; court, BIA and ICE each need their own form. |
| `aca_internal_appeal_180d` | `insurance_denial`, `eob`, `prior_auth` | `within (180\|one hundred eighty) days` | 180 / calendar | `notice_date` | no / 0 | healthcare.gov/appeal-insurance-company-decision/internal-appeals/ | verified / — | Fixture `insurance_denial_180d`. Anchor = the denial/EOB date as printed. |
| `aca_external_review_4mo` | `insurance_denial` | `within (4\|four) months` | 120 / calendar | `decision_date` (final internal denial) | no / 0 | healthcare.gov/appeal-insurance-company-decision/external-review/ | verified / — | "4 months" estimated as 120 days; `notes_en` says so and the card says "Confirm with the sender." |
| `medicare_advantage_65d` | `insurance_denial`, `eob` | `within (65\|sixty-five) days` | 65 / calendar | `notice_date` | no / 0 | medicare.gov/providers-services/claims-appeals-complaints/appeals | verified / — | RESOURCE_DB §13: the Part D page read showed 60 days at Level 2; Level 1 to be re-read (`warn.medicare_windows_changed`). |
| `medicaid_fair_hearing_90d_max` | `insurance_denial`, `medicaid_renewal` | `within (90\|ninety) days` | 90 / calendar | `notice_date` | no / 0 | ecfr.gov/current/title-42/section-431.221 | **likely** / 2027-03-31 | Federal *maximum*; states may allow fewer days — `notes_en`: "Your state may give less time. The printed date wins." |
| `asylum_annual_fee_30d` | `asylum_fee_notice` | `within (30\|thirty) days` | 30 / calendar | `notice_date` | no / 0 | uscis.gov/newsroom/alerts/uscis-updates-fees-based-on-hr-1 | verified / — | The only `payment_due` in the critical set. |
| `in_absentia_rescission_180d` | `ij_decision` | `within (180\|one hundred eighty) days` | 180 / calendar | `decision_date` | no / 0 | justice.gov/eoir/policy-manual-eoir/part-II/icpm/chapter-4-9 | verified / — | Applies only when the order says "in absentia"; a professional step is mandatory. |
| `eeoc_180_300d` | `pay_stub`, `other_notice` (category `employment`) | `within (180\|one hundred eighty) days` (a printed "within 300 days" stays `unresolved` rather than getting a 180-day estimate — CL-030(e)) | 180 / calendar | `other` (date of the act, if printed) | no / 0 | eeoc.gov/how-file-charge-employment-discrimination | verified / — | 300 days where a state agency exists; the estimate uses 180 and says so. |
| `osha_retaliation_30d` | `pay_stub`, `other_notice` (category `employment`) | `within (30\|thirty) days` | 30 / calendar | `other` | no / 0 | osha.gov/workers | verified / — | |
| `gfe_dispute_120d` | `medical_bill` | `within (120\|one hundred twenty) (calendar )?days` | 120 / calendar | `notice_date` (bill date) | no / 0 | cms.gov/initiatives/your-patient-rights/medical-bill-rights | verified / — | Only with the $400-over-estimate context printed; RESOURCE_DB §13 notes the page shows the threshold but not the window. |

**Not seeded, by decision (D-11):** any eviction notice or answer period (`va_pay_or_quit_14d` rejected), USCIS response windows (RFE "87 days", NOID "30/33 days", I-290B "30/33 days"), SSA "60 days + 5 mail days", Original Medicare 120 days, ITIN expiry, TPS windows, rent-increase notice periods, SNAP 30-day processing. Each surfaces as `unresolved` with the sender-question line; §9.2 lists them as "general guidance, confirm with counsel/agency". The two verbatim entries in API_CONTRACT §3.10 (`ar11_10d`, `bia_appeal_30d`) are copied into the YAML unchanged; `rules_version` bumps whenever a row changes.

### 5.4 Expected levels for the fixtures (must match BUILD_PLAN Appendix D)

`medicaid_address_confirmation` `high` (stated 2026-10-14 from the fixture's frozen `today`) · `uscis_i797c_receipt_i765` `info` · `uscis_rfe_87d` `high`/`critical` by days-until (critical only via the past-date rule) · `nta_hearing_date` `critical` (≤ 7 d) else floor `high`, `verify_resource_id="eoir_hotline"` · `inova_final_notice` `medium` · `insurance_denial_180d` `medium` (estimated) · `prescription_label` `info` · `school_immunization_notice` `medium` · `va_pay_or_quit_14d` `high` (stated date; floor otherwise) · `snap_interview_notice` `high` · `irs_cp_notice` `medium` · `jury_summons` `medium` · `scam_gift_card_letter` per its dates but `scam_risk=likely` and `resource_tags[0]=="scam_report"` · `blurry_unreadable_page` `info` with `readable=false` · `spanish_lease` `info` · `w2_form` `info` · `traffic_court_notice` `high`/`critical` by date. Golden tests freeze `today` per fixture manifest so these hold.

---

## 6. Scam signals and reason keys (`analysis/scam.py`, `data/safety/scam.yaml`)

D-13: scam risk is scored in code from **model red flags with verified quotes** plus **code regexes on the transcript**; the model's free-text `scam_signals[]` are logged as hints and never shown. Output: `scam_risk ∈ {none, possible, likely}`, `is_likely_scam = (scam_risk == likely)`, `scam_reasons[]` drawn only from the 15 fixed keys (the 13 prompt keys of AI_PROMPTS §5.1.3 plus the code-only `scam.upfront_fee` and `scam.asks_for_id_numbers`), code-added `RedFlag`s, `scam_report` forced first in `resource_tags`, and the fixed cards `scam.card.likely` / `scam.card.possible` (PRODUCT_SPEC Appendix A). Reporting contacts (DHS OIG phone, ReportFraud.ftc.gov) come from the resource DB by `well_known_ids.scam_card_phone/url` (RESOURCE_DB §4.7), never from copy or the model. Research: `resources.md §4` and *Warnings* "IMPERSONATION SCAMS"; `compliance.md §3` (USCIS: ".gov only; never Western Union, MoneyGram, PayPal, Venmo, or gift cards").

### 6.1 Signal table

Regexes are case-insensitive, applied to NFKC-normalized block text with whitespace collapsed (same normalizer as `verify.py`), in English and Spanish (`patterns.en`, `patterns.es`; other bundled languages inherit `en` + `es` until reviewed — scam letters and texts in the U.S. are overwhelmingly in those two). A model red flag of the same `RedFlagKind` with a verified quote counts as the same signal (max weight once). **Code-authoritative since 2026-10-22:** a model flag is matched on its printed `source_quote` only, outside negated sentences — never on its own `text` ("It does not ask for gift cards" is model prose, not a printed demand).

| Signal id | `scam_reasons` key (`scam.*`) | `RedFlagKind` | Weight | English cues (regex, abridged) | Guards |
|---|---|---|---|---|---|
| `gift_card` | `scam.gift_card` | `scam_payment_method` | 3 | `gift ?cards?`, `iTunes\|Google Play\|Steam\|Target\|Walmart card`, `prepaid (debit )?card`, `Green ?Dot\|MoneyPak\|Vanilla` | — |
| `wire_transfer` | `scam.wire_transfer` | `scam_payment_method` | 3 | `Western Union`, `MoneyGram`, `wire (transfer\|the money)`, `bank wire` | routine bill text "wire transfer accepted" on a `hospital_or_clinic`/`utility` sender → weight 1 |
| `payment_app` | `scam.payment_app` | `scam_payment_method` | 2 | `Zelle`, `Venmo`, `Cash ?App`, `PayPal`, `Apple Pay`, `Google Pay` | private senders (`landlord`, `hospital_or_clinic`, `utility`, `pharmacy`, `school`, `employer`) with a printed name → weight 1 |
| `crypto` | `scam.crypto` | `scam_payment_method` | 3 | `bitcoin\|BTC\|crypto(currency)?\|Ethereum\|USDT\|Tether`, `crypto ATM`, `wallet address` | — |
| `model_payment_method` | *(no key)* | `scam_payment_method` | 2 | none — a verified model `scam_payment_method` flag whose quote names none of the four methods above ("send cash in an envelope", "Settle the balance by purchasing vouchers"); counts as a payment-method signal | the flag neither scores nor shows, and counts as a rejected fact, only when its quote asks for no payment: anti-fraud boilerplate, the SAMPLE footer of a demo paper (or a piece of it), or an agency's own `.gov` payment portal — a `model_payment.portal` pay phrase pointing at the `.gov`/`.mil` address the quote prints ("Pay online at irs.gov/payments"), no other contact, no `in_hand` word. Every other quote stands, in every language. `payment_app`'s guards, read on the quote: that same `.gov` portal test → 0, a named private sender → 1 — neither when the quote names an `in_hand` payment (cash, a money order, a voucher, a courier or agent) |
| `arrest_threat` | `scam.arrest_threat` | `urgency_pressure` | 2 | `(warrant\|arrest(ed)?\|police\|sheriff\|jail\|law enforcement).{0,80}(today\|immediately\|within \d+ (hours\|minutes)\|unless you\|if you (do not\|don't\|fail))` | on a `court` sender or `traffic_court` type (genuine "a warrant may be issued" FTA text) → weight 0 unless a payment-method signal also fires |
| `deportation_threat` | `scam.deportation_threat` | `urgency_pressure` | 2 | `(deport(ed\|ation)\|removed from the (country\|United States)\|immigration (hold\|arrest)).{0,80}(pay\|payment\|unless\|fee\|immediately)` | requires the pay/fee coupling; never fires on the statutory warnings of `nta`/`hearing_notice`/`ij_decision` (excluded types) |
| `guaranteed` | `scam.guaranteed` | `guaranteed_result` | 2 | `guarantee(d\|s)?.{0,40}(approval\|visa\|green card\|result\|win\|citizenship)`, `100 ?% (approval\|success)`, `you (have )?won\|you have been selected.{0,60}(visa\|lottery\|green card)` | — |
| `notario` | `scam.notario` | `notario` | 2 | `notario( p[úu]blico)?`, `notary.{0,40}(immigration\|legal advice\|represent)`, `immigration consultant` | a plain notarization line on a lease or affidavit ("notary public" with a seal, no immigration words) → 0 |
| `non_gov_domain` | `scam.non_gov_domain` | `impersonation` | 3 | an agency name (`USCIS\|U\.?S\.? Citizenship\|ICE\|DHS\|Homeland Security\|Social Security\|SSA\|IRS\|Internal Revenue\|Medicare\|Medicaid\|EOIR\|Immigration Court\|Department of (State\|Justice\|Labor)`) within 120 characters of a URL, e-mail or domain whose registrable domain is not `.gov`/`.mil` | agency name absent → 0; a private sender's own domain (hospital, insurer, utility, landlord) is not an agency impersonation |
| `expedite_fee` | `scam.expedite_fee` | `fee_for_free_form` | 2 | `(expedite\|speed up\|faster\|jump the line\|priority handling\|special connection).{0,60}(fee\|\$\|pay\|payment)` | excludes `premium processing` and `Form I-907` (genuine USCIS service) |
| `fee_for_free_form` | `scam.fee_for_free_form` | `fee_for_free_form` | 2 | `(download\|access\|obtain\|get) (the\|a\|your) form.{0,40}(\$\|fee\|pay)`, `form (fee\|charge) payable to (?!U\.?S\.? Department\|USCIS\|Department of Homeland Security)` | genuine filing fees ("filing fee $550 payable to U.S. Department of Homeland Security") never match |
| `urgency_pressure` | `scam.urgency_pressure` | `urgency_pressure` | 1 (2 with secrecy) | `(act\|respond\|pay\|call) (now\|immediately\|today\|within (\d+\|one\|two\|24\|48\|72) (hours?\|minutes?))`, `last chance`, `final (warning\|notice) before (arrest\|legal action\|deportation\|suspension of your (SSN\|social security number))`; secrecy: `do not (tell\|discuss\|hang up)`, `keep this confidential` | plain "FINAL NOTICE" / "past due" on a bill is a **model** `urgency_pressure` flag with weight 1 and never reaches `possible` alone (fixture `inova_final_notice`: `scam_risk: none`) |
| `impersonation` | `scam.impersonation` | `impersonation` | 2 | misspelled or non-existent agencies (`U\.S\.C\.I\.S`, `Department of Immigration`, `US Immigration Services`, `Federal Immigration Agency`, `Deportation Department`, `Social Security Bureau`), `badge (number\|ID).{0,40}(pay\|fee)`, `officer .{0,30} will (arrest\|come to your home)` | model `impersonation` flags count here |
| `upfront_fee` | `scam.upfront_fee` | `fee_for_free_form` | 2 | `(pay\|payment\|deposit\|fee).{0,30}(up ?front\|in advance\|before (we\|they\|i) (start\|begin\|file)\|to (start\|begin\|open) your (case\|file\|application))`, `(processing\|registration\|release\|activation) fee.{0,40}(before\|first\|now)` | `filing fee`, `biometric services fee`, "payable to U.S. Department …"/"payable to USCIS" → 0 (CL-050(f)) |
| `id_or_payment_data_request` | `scam.asks_for_id_numbers` | `unusual_contact` | 1 (2 when combined with any threat) | `(send\|text\|reply with\|confirm) your (SSN\|social security\|A-?number\|alien number\|bank\|card\|PIN\|password)`; troubleshoot: `asks_for_credentials_or_payment=true` | genuine forms that *ask* for an SSN on the form itself (I-9, W-7, school forms) → 0 |
| `no_sender` | *(no key; §3.15)* | `unusual_contact` | 1 | `sender_as_written == null` **and** any `payment_due`/`amount` or data request | — |

### 6.2 Scoring and thresholds

`score = Σ weight(signal)` over distinct signal ids (model flag and regex for the same id count once). Then:

- **`likely`** when any of: `score ≥ 4`; a **payment-method** signal (weight ≥ 2 after guards) **and** `sender_kind ∈ {federal_agency, state_agency, local_agency, court, unknown}`; a payment-method signal **and** any threat/impersonation signal (`arrest_threat`, `deportation_threat`, `impersonation`, `non_gov_domain`); `non_gov_domain` **and** any payment or data request; `guaranteed` **and** any fee signal (DV-lottery and "pay to jump the line" pattern).
- **`possible`** when `2 ≤ score < 4`, or a single payment-app signal on a private sender with a threat-free text (a landlord asking for Zelle).
- **`none`** when `score < 2`.

Worked checks: `scam_gift_card_letter` = gift card (3) + deportation threat (2) + non-.gov domain (3) = 8 → `likely`. J-F SMS = gift card + arrest threat + non-.gov → `likely`. `inova_final_notice` = model `urgency_pressure` (1) → `none`. A utility impersonation text "pay within 1 hour by prepaid card or service is cut" on a `utility` sender = prepaid card (3) + urgency (1) = 4 → `likely`. A genuine IRS CP14 with "pay online at irs.gov" = 0 → `none`.

### 6.3 What never counts (false-positive guards, tested in `test_scam.py`)

Genuine bills with "FINAL NOTICE"; hospital, insurer, utility or landlord payment portals and their own `.com`/`.org` domains; USCIS filing-fee sentences and "premium processing"; statutory warnings on court papers ("may be ordered removed in your absence", "a warrant may be issued for failure to appear"); an I-9, W-7 or school form asking for an SSN on the form; a notary seal on a lease; SSA/IRS/USCIS letters that print only `.gov` contacts. Guards are `weight: 0` overrides keyed by `sender_kind`, `document_type` and negative regexes in `scam.yaml`. **The SAMPLE footer of a demo paper** ("SAMPLE — synthetic document made for demonstration. Not a real letter.", `demo/fixtures.py` `SAMPLE_FOOTER`): on a sample paper (`demo_sample_id`, or a mock dHash match — never a real upload) its block is not scored, and model red flags that quote it or rest only on its block, and plan steps that cite only that block or make its claim their condition ("Ask the office … if it is a real letter") without a scam warning, are dropped (`analysis/classify.py`, 2026-10-22). A model payment flag quoting the footer is set aside on any upload (§6.1 `model_payment_method`). Duplicate model flags (same kind, same quote) show once.

### 6.4 Outputs and copy

- `scam_reasons` = the fired keys in descending weight, then table order, max 6; only the 15 fixed keys ever appear (signals without a key contribute to the score but not to the chips).
- The model's free-text `scam_signals[]` are hints only and never score (this section wins over any AI_PROMPTS wording — CL-021(b)).
- Only when `scam_risk != none`, for every regex-only signal, code appends `RedFlag{kind: <table kind>, severity: high if likely else medium, text: t_server("scam.<reason>"), source_quote: <matched block text>, span_ids: [<block id>], page, fixed_copy_key: null, verified: true}` so the chip and the crop line up (`fixed_copy_key` stays reserved for `fixed.*` cards per §7.3; the client renders `text`, and the reason chips come from `scam_reasons`); model flags keep their own text (linted) and quote.
- `likely` → `tagging.py` inserts `scam_report` at index 0 of `resource_tags` (BUILD_PLAN §5.3 acceptance) and the client calls the matcher with `scam_risk=likely`, which forces `scam_report` entries first (RESOURCE_DB §6.6) and appends `ftc_reportfraud` + `dhs_oig` to `national_fallbacks` (also for `possible`, §6.9 there). `red_flags[kind ∈ {scam_payment_method, impersonation, notario}]` also add the paper's category tag so `uscis_scams`/`irs_scams`/`ssa_scams` rank (RESOURCE_DB §12.2); `notario` adds `eoir_roster` + `uscis_find_legal` with checklist `bring_name_of_helper`.
- Card copy (fixed, bypasses the linter): **`scam.card.likely`** "Scam risk: likely — ICE, USCIS, SSA and the IRS never demand payment by phone, gift card, wire, or app. Do not pay. Report it:" followed by `dhs_oig.phone` and `ftc_reportfraud.url`; **`scam.card.possible`** "Some things in this paper look like a scam. Be careful. Do not pay or share ID numbers until you check with the real office." Reason chips: `scam.gift_card` "Asks for gift cards" · `scam.wire_transfer` "Asks for a wire transfer" · `scam.payment_app` "Asks for a payment app" · `scam.crypto` "Asks for cryptocurrency" · `scam.arrest_threat` "Threatens arrest" · `scam.deportation_threat` "Threatens deportation" · `scam.guaranteed` "Promises a guaranteed result" · `scam.notario` "Mentions a \"notario\"" · `scam.non_gov_domain` "Website is not .gov" · `scam.expedite_fee` "Charges to go faster" · `scam.fee_for_free_form` "Charges for a free form" · `scam.urgency_pressure` "Pushes you to hurry" · `scam.impersonation` "Pretends to be a government office".
- Plan interplay: with `likely`, `pipeline.py` drops any `call`/`submit_online` step whose target is a printed contact (the scam's own number) and the `questions_to_ask` list; the plan becomes `verify` (call the real agency via Get help) → `professional` → `gather` (keep the letter as evidence, `btn.save_evidence` on S16).
- Facts the app may state, **only in fixed copy** (resources.md §4/Warnings): agencies never demand payment by phone, gift card, wire, crypto or app; USCIS payments only through a `.gov` account; USCIS forms and accounts are free (`warn.forms_are_free`); ICE does not phone to warn of arrest; official e-mails and sites end in `.gov`; SSA flagged fake "call transfers" to SSA/OIG (2026-07-29).

### 6.5 Re-typing rule and interplay with fixed notices and urgency

When `scam_risk == likely` **and** `document_type ∈ {USCIS types, ice_checkin, irs_notice, itin, ssa_letter}` (agency papers), `pipeline.py` sets `document_type = other_notice` (category unchanged, `document_type_confidence = low`) per §3.11 ("a scam letter impersonating USCIS is `other_notice` / `immigration`"). Consequences: no doc-type floor, no USCIS/EOIR `verify_resource_id` (the scam card's reporting resources take its place), no type-specific fixed notice, the generic clerk line. Printed dates still become verified Demands and may drive the banner; the scam card renders above it (S7 order). Court papers (`nta`, `hearing_notice`, `eviction_summons`, `traffic_court`) are **not** re-typed on scam signals — a forged summons is rare and a missed real hearing is catastrophic — they show the scam card *and* the court verify CTA ("call the court's own line"). As built (2026-10-22, `classify.after_scam`): the re-type sets `document_type_confidence = low` in code, and a type that the §3 rule 16 code check chose never survives a `likely` scam — the model's own type and category come back first, then this rule applies to them.

### 6.6 `scam.yaml` schema

As built (seed `version: "2026-09-30"`, `model_payment` added in `"2026-10-22"`; code-authoritative after Phase 2B; `analysis/scam.py`). Regexes are case-insensitive over NFKC-normalised, whitespace-collapsed block text (the `verify.py` normaliser), in **English, Spanish, Arabic, Dari and Pashto**; every pattern runs on every text, whatever the paper's language (brand names are Latin everywhere).

```yaml
version: "2026-10-22"
thresholds: {possible: 2, likely: 4}
gov_tlds: [".gov", ".mil"]
agency_names: ["USCIS", "U.S. Citizenship", "US Citizenship", "ICE", "DHS", "Homeland Security", "Social Security", "SSA", "IRS", "Internal Revenue", "Medicare", "Medicaid", "EOIR", "Immigration Court", "Department of State", "Department of Justice", "Department of Labor"]
agency_document_types: [uscis_receipt, uscis_rfe, uscis_noid, uscis_biometrics, uscis_interview, uscis_approval, uscis_denial, ead_related, green_card_related, tps_related, asylum_fee_notice, parole_related, ice_checkin, irs_notice, itin, ssa_letter]
agency_sender_kinds: [federal_agency, state_agency, local_agency, court, unknown]
private_sender_kinds: [landlord, hospital_or_clinic, utility, pharmacy, school, employer]
payment_signals: [gift_card, wire_transfer, payment_app, crypto]
threat_signals: [arrest_threat, deportation_threat, impersonation, non_gov_domain]
fee_signals: [expedite_fee, fee_for_free_form, upfront_fee]
request_signals: [id_or_payment_data_request, gift_card, wire_transfer, payment_app, crypto, upfront_fee]
likely_rules: [payment_and_agency_sender, payment_and_threat, nongov_and_request, guaranteed_and_fee]
negation_cues:                            # agency boilerplate ("USCIS will never ask you to pay with gift cards") is not a demand
  before: {en: [...], es: [...], ar: [...], prs: [...], ps: [...]}   # a cue before the match in the same sentence negates it ...
  after:  {en: [...], es: [...]}          # ... or one after it ("… is a scam")
  breaks: "\\b(only|just|instead|but|however|except|rather|solo|sólo|…)\\b|[,;:]\\s*(please |you must |…)?(pay|send|buy|…)"   # ... unless a break word stands between cue and match
model_payment:                            # §6.1 model_payment_method: when a model payment flag asks for no payment
  portal:                                 # a pay phrase ending right before the .gov/.mil address the quote prints
    en: ["\\b(pay|pays|paying|payment|payments|paid)\\b[^.!?;\\n]{0,40}\\b(at|on|through|via|to)\\s*$"]
    es: ["…"]
  in_hand:                                # cash, a money order, a voucher, a courier or agent: never a portal, keeps weight 2
    en: ["\\b(cash|money ?orders?|vouchers?|couriers?|agents?)\\b"]
    es: ["…"]
    ar: ["…"]
    prs: ["…"]
    ps: ["…"]                             # drafts, reviewed_by: null like the patterns
signals:
  - id: gift_card
    reason_key: scam.gift_card            # null = scores but shows no chip
    red_flag_kind: scam_payment_method
    weight: 3
    patterns:
      en: ["\\bgift ?cards?\\b", "\\b(itunes|google play|steam|target|walmart|amazon|ebay) (gift )?cards?\\b", "\\bprepaid (debit )?cards?\\b", "\\b(green ?dot|moneypak|vanilla) "]
      es: ["\\btarjetas? de regalo\\b", "\\btarjetas? prepaga(da)?s?\\b"]
      ar: ["بطاق(ة|ات|ه) (ال)?(هدية|هدايا|هديه)", "…"]
      prs: ["کارت[\\s\\u200c]*(های[\\s\\u200c]*)?(هدیه|تحفه)", "…"]
      ps: ["(ډالۍ|ډالئ|تحفه)[\\s\\u200c]*(کارت|کارډ)", "…"]
    negation: true                        # skip a match inside a negated / anti-fraud sentence (negation_cues)
    guards: []                            # first matching guard's weight replaces the signal weight
  - id: payment_app
    # …
    guards:
      - {gov_url_in_segment: true, weight: 0}   # the hit block prints a .gov/.mil address and no other contact: the agency's own portal
      - {sender_kind: [landlord, hospital_or_clinic, utility, pharmacy, school, employer], requires_sender_name: true, weight: 1}
reviewed_by: {en: null, es: null, ar: null, prs: null, ps: null}
```

Guard fields: `sender_kind`, `document_type`, `negative_regex` (must match every text the hit came from), `requires_sender_name` (the paper names its sender), `unless_any_of: [signal ids]` (the full weight stays when one of those also fires), `gov_url_in_segment`, `weight` (0 = the signal never counts on its own). `negation: true` is set on the four payment signals (`gift_card`, `wire_transfer`, `payment_app`, `crypto`), whose words agencies print in fraud warnings; a `before` cue counts only within the same sentence and only when no `breaks` match stands between it and the hit ("never pay with gift cards, only by check" negates; "we do not accept checks, pay with gift cards" does not). `prs`/`ps` `before` cues are the bare "never" words (هرگز, هېڅکله); their patterns and cues are machine-assisted drafts (`reviewed_by: null`, DECISIONS Q6).

### 6.7 Troubleshoot `mode=scam_check`

`troubleshoot_pipeline.py` runs the same table over `screen_text[]` + `error_text_quoted` + `user_goal`, with `TroubleshootModelOut.asks_for_credentials_or_payment` feeding `id_or_payment_data_request` (weight 2) and `safety.credential_or_payment_request`. `portal` mode runs it too (a phishing page pretending to be a benefits portal): `likely` → the scam card first, steps reduced to "close the page; use the address printed on your paper or from Get help". The model's `is_likely_scam` is a hint only; `scam_risk` is the code's.

---

## 7. Fixed high-severity notices (`analysis/fixed_notices.py`, `data/rules/fixed_notices.yaml`)

D-20 cards are **reviewed fixed copy**: the client renders `t(fixed_copy_key)`; the server fills `RedFlag.text` with `t_server(fixed_copy_key, target_language)` (English fallback), `source_quote: null` (or the triggering quote when a condition matched text), `span_ids: []`, `page: null`, `verified: true`. They bypass the phrasing linter and the contacts filter (they contain no contacts). They are appended **after** model flags are verified and sorted first by severity, so a `high` fixed card leads the *Red flags* card (S7 §14). Kinds used here are exactly the six fixed-notice `RedFlagKind`s the prompt loader withholds from the model (`AI_PROMPTS §2 {red_flag_kinds}`) plus `other` for the proposed additions. `RulesRepo.fixed_notices(doc_type)` returns `FixedNotice{kind, severity, fixed_copy_key}` (BUILD_PLAN §4.1); the condition evaluation lives in `fixed_notices.py`.

### 7.1 Seeded notices (keys exist in PRODUCT_SPEC Appendix A)

| id | Document types | Condition (`when`) | `kind` | `severity` | `fixed_copy_key` | Exact English copy |
|---|---|---|---|---|---|---|
| `jury_citizenship` | `jury_summons` | always | `jury_citizenship_warning` | `high` | `fixed.jury_summons` | "You must answer this form. If you are not a U.S. citizen, mark 'not a citizen' and send it back. Never check 'citizen' and never register to vote — it can permanently harm your immigration case." |
| `ead_receipt` | `uscis_receipt`, `ead_related`, `i9` | `form_numbers_any: [I-765]` **and** `text_regex_any: ["I-?797C", "receipt notice", "we received your"]` **and not** `text_regex_any: ["Temporary Protected Status", "\\bA12\\b", "\\bC19\\b"]` (TPS Federal-Register extensions are the exception); date test: a verified `notice_date`/received date **≥ 2025-10-30**, or no such date (fail-open: show it) | `ead_receipt_not_work_authorization` | `high` | `fixed.uscis_receipt_i765` | "A receipt for a work-permit renewal filed on or after October 30, 2025 is **not** proof you can work. Ask a lawyer or DOJ-accredited representative about a possible work gap." |
| `not_a_court_order` | `pay_or_quit` | always | `not_a_court_order` | `high` | `fixed.pay_or_quit` | "This is not a court order. Only a court can make you leave." |
| `court_date_deadline_eviction` | `eviction_summons` | always | `court_date_is_the_deadline` | `high` | `fixed.eviction_summons` | "The court date on this paper is the date that matters. Go, or you can lose automatically." |
| `no_fee_waiver` | `asylum_fee_notice` | always | `no_fee_waiver` | `high` | `fixed.asylum_fee_notice` | "There is no fee waiver for this fee." |
| `address_multi_agency` | `nta`, `hearing_notice` | always | `address_change_multi_agency` | `high` | `fixed.address_change_multi_agency` | "If you move, the court needs its own address form (EOIR-33). USPS forwarding does not update the court or USCIS." |
| `multiple_documents` | any | set by `pipeline.py` (§3.13), not by the YAML | `other` | `medium` | `fixed.multiple_documents` | "These pages look like two different papers. I explained the first one. Scan the other one on its own." |

`uscis_receipt` fixture `uscis_i797c_receipt_i765` must produce `ead_receipt` (`high`); `nta_hearing_date` must produce `address_multi_agency`; `va_pay_or_quit_14d` → `not_a_court_order`; `jury_summons` → `jury_citizenship` (BUILD_PLAN Appendix D).

### 7.2 Proposed additions (need `en.json` keys from WP0 — filed as §9.3 requests; kept commented out in the YAML until the keys exist, because `test_keys_exist.py` forbids emitting an absent key)

| id | Document types | Condition | `kind` | `severity` | proposed key | Proposed English copy (grade ≤ 4, no dramatizing) | Why |
|---|---|---|---|---|---|---|---|
| `court_date_deadline_immigration` | `nta` (only when a real hearing date is printed), `hearing_notice` | `has_verified_role: hearing_date` | `court_date_is_the_deadline` | `high` | `fixed.court_date_is_the_deadline` | "The court date on this paper is the date that matters. If you miss it, the judge can decide your case without you. Go, even if you do not have a lawyer yet." | in-absentia removal has no appeal (compliance.md §7); the brief names it; the kind already exists |
| `eob_not_a_bill` | `eob` | always | `other` | `medium` | `fixed.eob_not_a_bill` | "This is not a bill. Do not pay from this paper. Wait for the bill from the doctor or hospital, then compare the two." | RESOURCE_DB §14 already assumes this fixed copy lives here |
| `traffic_immigration` | `traffic_court` | always | `other` | `high` | `fixed.traffic_court_immigration` | "If you are not a U.S. citizen, talk to an immigration lawyer before you pay or plead guilty. Some tickets and court cases can affect an immigration case." | resources.md §3I; RESOURCE_DB §14 "fixed 'talk to an immigration lawyer before pleading' copy" |
| `conditional_card` | `green_card_related` | `text_regex_any: ["conditional", "\\bCR[1-9]\\b", "2-?year"]` | `other` | `medium` | `fixed.conditional_card` | "A 2-year Green Card cannot be renewed with Form I-90. Ask a lawyer or DOJ-accredited representative what to file well before it expires." (the 90-day I-751/I-829 window in resources.md §3B is a memorized period and stays out of fixed copy — D-11) | resources.md §3B |
| `notario_not_lawyer` | any with `red_flags[kind=notario]` | `has_red_flag: notario` | `notario` | `high` | `fixed.notario_not_a_lawyer` | "A notario is not a lawyer in the United States. Only a licensed lawyer or a DOJ-accredited representative can give legal advice. You can check a helper's name on the government list." | compliance.md §3; replaces the model's own notario sentence when it fails lint |
| `ice_scam_call` | `ice_checkin`, `other_notice` (immigration) | `scam_risk: likely` | `impersonation` | `high` | *(none — the scam card already says it)* | — | listed to record that no extra card is needed |

### 7.3 `fixed_notices.yaml` schema and condition grammar

```yaml
version: "2026-09-27"
notices:
  - id: ead_receipt
    document_types: [uscis_receipt, ead_related, i9]
    when:
      form_numbers_any: ["I-765"]
      text_regex_any: ["I-?797C", "receipt notice", "we received your"]
      text_regex_none: ["Temporary Protected Status", "\\bA12\\b", "\\bC19\\b"]
      date_on_or_after: {role: notice_date, iso: "2025-10-30", when_missing: show}
    kind: ead_receipt_not_work_authorization
    severity: high
    fixed_copy_key: fixed.uscis_receipt_i765
  - id: jury_citizenship
    document_types: [jury_summons]
    when: always
    kind: jury_citizenship_warning
    severity: high
    fixed_copy_key: fixed.jury_summons
  # - id: eob_not_a_bill   # enable when CL-nnn adds fixed.eob_not_a_bill
```

Grammar: `when: always` · `form_numbers_any` (against `entities.form_numbers`, hyphen-insensitive) · `text_regex_any` / `text_regex_none` (NFKC-normalized transcript) · `date_on_or_after: {role, iso, when_missing: show|hide}` (uses a **verified stated** Demand of that role) · `has_verified_role` · `has_red_flag` · `scam_risk` (`likely`/`possible`) · `document_type_confidence_min` (`medium` by default: a `low`-confidence classification shows no type-specific fixed notice, so a mis-typed paper never gets a frightening card). All listed keys must pass `test_keys_exist.py`; the loader rejects a `fixed_copy_key` that does not start with `fixed.`.

---

## 8. Phrasing lint (`analysis/phrasing.py`, `data/safety/phrasing.yaml`) and legal-module limit sentences

D-17: every model-authored user-facing sentence is linted against forbidden patterns; a hit triggers **one** `MODEL_FAST` rewrite (task `phrasing_rewrite`, `RewriteOut.sentence`, AI_PROMPTS §5.7) with the template **"The paper says X. A {professional} can tell you what it means for you."**; if the rewrite still matches, a **fixed hedge** replaces the sentence and `verification.phrasing_rewrites` increments. Fixed copy (§6, §7, disclaimers, chat templates) bypasses the linter; quotes (`source_quote`, `original_text`, `translated_text`, `value_verbatim`, `grounded_quotes`) are never linted — they are the paper's words. Research: `compliance.md §3` (UPL line, *Upsolve v. James*), `§7` item 9; PRODUCT_SPEC §7.1–§7.2.

### 8.1 Scope

Linted fields: `summary.title/body/body_en`, `Demand.text`, `Demand.ambiguity_note`, `PlanStep.text`, `GlossaryTerm.explanation`, `RedFlag.text` (model flags only), `questions_to_ask[]`, `clerk_need_en`, `ChatAnswer.answer`, `suggested_questions[]`, troubleshoot `screen_summary`, `error_meaning`, `steps[].text`, `cautions[]`. Lint runs on the English (`body_en`, the English chat draft) **and** on the target-language text when `phrasing.yaml` has a reviewed section for that language; otherwise English only and `warnings: [phrasing_lint_unavailable]`.

### 8.2 Pattern families (English seed; `family` → regex → `refusal_kind` used for the hedge → domains)

| family | regex (case-insensitive; `\b` boundaries implied) | hedge `RefusalKind` | domains |
|---|---|---|---|
| `eligibility` | `you (are\|aren't\|are not\|'re) (eligible\|not eligible\|ineligible\|entitled)`, `you (do\|don't\|do not) qualify`, `(your (child\|children\|family\|husband\|wife\|son\|daughter)) (qualif(y\|ies)\|is eligible\|are eligible\|will get\|won't get)`, `you (will\|won't\|will not\|can\|cannot\|can't) (get\|receive\|keep\|lose) (your )?(benefits\|coverage\|Medicaid\|SNAP\|WIC\|SSI\|asylum\|a green card\|your permit)` | `eligibility` | all |
| `outcome` | `you (will\|won't\|will not\|are going to\|are likely to\|are unlikely to) (win\|lose\|be (approved\|denied\|deported\|removed\|evicted\|arrested\|fined))`, `your (case\|appeal\|application) (will\|is likely to\|should) (be )?(approved\|denied\|succeed\|fail\|win\|lose)`, `you have (a strong\|a weak\|no\|a good) (case\|chance)`, `nothing (will happen\|to worry about)`, `(don't\|do not) worry`, `you('ll\| will) be (fine\|okay\|ok)` | `outcome` | all |
| `advice_verb` | `you (should\|must\|need to\|have to\|ought to\|had better\|are required to) (file\|appeal\|apply\|pay\|sign\|send\|submit\|plead\|accept\|refuse\|leave\|move( out)?\|stop\|start\|take\|register\|check the box)` **unless attributed** (§8.3) | `filing_advice` | all |
| `negated_duty` | `you (do not\|don't\|do not need to\|need not\|never) have to`, `(does not\|doesn't) require you to`, `you (can\|may) (ignore\|skip\|throw away)`, `this means (that )?you (have\|owe\|must\|are\|will\|can\|cannot)` | `filing_advice` | all |
| `dramatize` | `you (may\|might\|could\|will) be deported`, `(URGENT\|WARNING\|IMMEDIATELY)` as an all-caps token in model prose, `!` in prose, `(catastroph\|disaster\|ruin)` | `none` → rewrite only, hedge = the sentence with the clause removed | all |
| `medical_interpret` | `you (have\|might have\|may have\|probably have\|are suffering from\|are (diabetic\|anemic\|pregnant\|infected\|allergic\|contagious))`, `(your\|the) (results?\|levels?\|values?\|numbers?\|readings?) (are\|is\|show\|shows\|mean\|means\|indicate\|suggests?) (normal\|abnormal\|high\|low\|fine\|good\|bad\|healthy\|dangerous\|too (high\|low)\|that)`, `(is a sign of\|means you have\|points to) \w+`, `you (need\|should\|must\|can\|may) (take\|stop\|skip\|double\|increase\|decrease\|reduce\|mix) (the\|your\|this) (dose\|medicine\|medication\|pill\|tablet)`, `it is (safe\|not safe\|okay\|fine) to (take\|stop\|mix\|drink\|drive)` | `medical_interpretation` | `medical` (also runs on any type when the sentence names a medicine or test) |
| `legal_status` | `you (are\|are not\|aren't) (deportable\|removable\|in status\|out of status\|undocumented\|legal\|illegal\|authorized to work\|allowed to work\|allowed to travel)`, `you (can\|cannot\|can't\|may\|may not) (work\|stay\|travel\|be deported\|be removed\|vote)` unless attributed, `(plead\|you should plead) (guilty\|not guilty)`, `check (the box\|'citizen')` (not in fixed copy), `(file\|submit) (form \w+\|an appeal\|a motion)` as an imperative | `filing_advice` | `immigration`, `court`, `civic`, `employment` |
| `benefits_decision` | `your (benefits\|coverage\|case\|food stamps) (will\|won't\|will not) (end\|stop\|be cut\|continue\|be approved\|be renewed)` unless attributed, `you (are\|aren't\|are not) (over\|under) the (income )?limit`, `you (do\|don't\|do not) count`, `you (will\|won't) (get\|receive) (SNAP\|WIC\|Medicaid\|SSI\|a check\|back pay)` | `eligibility` | `benefits`, `medical` |
| `housing_law` | `you (have to\|must\|need to\|do not have to\|don't have to\|can\|cannot\|can't) (leave\|move out\|stay\|be evicted\|pay (the\|this) (fee\|increase))` unless attributed, `the landlord (can\|cannot\|can't\|has to\|must\|is allowed to\|is not allowed to)` unless attributed, `(illegal\|unlawful\|legal\|valid\|invalid) (eviction\|notice\|increase\|fee\|lease)`, `within \d+ days you (must\|have to)` | `filing_advice` | `housing` |
| `tax_work_conclusion` | `you (owe\|don't owe\|do not owe\|will get a refund\|are owed)` unless attributed, `you (should\|must) (agree\|disagree\|sign\|pay the IRS)`, `(this is\|it is\|that is) (wage theft\|illegal\|discrimination\|retaliation\|fraud)`, `you (can\|cannot\|can't) (be fired\|sue\|be paid less)`, `you were (underpaid\|cheated\|not paid enough)` | `filing_advice` | `tax`, `employment` |
| `school_decision` | `your child (needs\|does not need\|doesn't need\|qualifies for\|is eligible for\|should be in\|must be in) (special education\|an IEP\|a 504\|services\|this school)`, `the school (must\|cannot\|can't\|has to) (enroll\|exclude\|test\|evaluate)` unless attributed | `eligibility` | `school` |
| `contact_like` | any phone-like digit run, URL, e-mail or street address (handled by `contacts_filter.py`, listed here so a rewrite never re-introduces one) | `contact_request` | all |

**Code-authoritative (CL-021(d), CL-030(b)(c)).** `contact_like` never fails an original sentence for carrying a contact (scrubbing is `contacts_filter.py`'s job); it only rejects a rewrite candidate that adds a phone, URL, e-mail or address the original sentence lacked (`lint_sentence(..., original=)` via `contacts_filter.new_contacts`). `medical_interpret` narrows the bare `you (have\|…)` to "you have <condition>": it skips `you have to/until/<n> days/questions/them/an appointment …` and a sentence-final "you have" (otherwise the golden `prescription_label` plan step and ordinary appointment lines fail the D-16 lint gate); it adds "your <measure> (level\|count\|reading)? is (too\|very)? high/low/abnormal/normal/elevated/dangerous…" (bill words such as balance, amount, copay, rent excluded), "(which\|that\|this)? (can\|could\|may\|might) be (dangerous\|serious\|life-threatening)", and an optional modifier word before `results/levels/values/numbers/readings`, so PRODUCT_SPEC §7.2 row 3 is caught. **Phase 2B widenings (`phrasing.yaml` version 2026-09-30, code-authoritative):** `eligibility` also catches hedged forms ("you probably/likely/should/may/might/will/would qualify", "you're probably not eligible"); `outcome` adds "would" and adverbs ("you will probably be approved", "you would almost certainly lose"); `negated_duty` adds "you don't/never/won't/will not need to", "you need not" and "(there is) no need to (go\|attend\|appear\|answer\|respond\|reply\|pay\|show up\|come)"; `medical_interpret` adds up to two words before the measure ("your blood sugar levels are high"), a value in between ("your cholesterol is 260, which is high", "your A1C of 9.1 is above normal"; bill words excluded), "(is\|are\|was\|were) (above\|below\|outside\|out of) the normal/healthy/target/reference range", "of/at <number> means/shows/indicates" and dosing directives ("you should stop/skip/double/increase … your dose/medicine/insulin").

### 8.3 Attribution exemption and allowed phrasings

A sentence is **attributed** — and the `advice_verb`, `negated_duty`, `legal_status`, `benefits_decision`, `housing_law`, `tax_work_conclusion` families are skipped — when it begins with or contains `(The\|This\|Your) (paper\|letter\|notice\|form\|bill\|summons\|order\|lease\|label\|court\|judge\|office\|school\|landlord\|insurer\|plan\|IRS\|USCIS\|ICE\|Social Security) (says\|asks\|lists\|states\|tells you\|orders\|warns)` or `It says`. Allowed verbs (PRODUCT_SPEC §7.1): "the paper says", "usually", "you can ask", "before the date", "people often", "the office can tell you", "a lawyer can confirm". Allowed referral sentences: "Talk to a licensed lawyer or a DOJ-accredited representative before {date}.", "Ask your doctor, nurse or pharmacist what this means for you.", "A housing lawyer or counselor can advise you.", "The office that sent this paper can tell you what happens next." The one permitted state-law sentence (D-17): "In {state}, a landlord generally needs a court order before an eviction can happen. Confirm with the legal helpline today." — emitted by the rewrite only when `state` is known and the flagged sentence is about leaving/eviction.

### 8.4 Rewrite pass and fixed hedge

- Prompt: `ai/prompts/phrasing_rewrite.md` with `{sentence}` and `{professional}`; `{professional}` by document type first (`professional_by_document_type`), else by `DocumentCategory`, exactly as PRODUCT_SPEC §7.2 and AI_PROMPTS §5.7 (`phrasing.professional_for`): immigration and the immigration-court types → "a licensed lawyer or a DOJ-accredited representative" · other court/civic → "a licensed lawyer" · employment → "a licensed lawyer or a workers' rights office" (`w2_1099` → "a free tax helper or a tax professional", `itin` → "the IRS or a free tax helper") · medical → "your doctor, nurse or pharmacist" · housing → "a housing lawyer or counselor" · benefits → "the office that sent this paper" · school → "the school office or a parent center" · tax → "the IRS or a free tax helper" · other → "a professional" (in chat, by `refer_to_professional` when it is not `none`). Output ≤ 400 chars, one or two sentences, must re-pass the lint and the contacts filter.
- Fixed hedge when the rewrite fails: the existing chat templates are reused via `t_server` so no new key is needed — `chat.refusal.eligibility` "I cannot say whether you qualify. The paper says what it says; a professional can tell you what it means for you." · `chat.refusal.filing_advice` "I cannot tell you what to file or send. I can explain what the paper asks for." · `chat.refusal.outcome` "I cannot predict what will happen. No one can promise a result." · `chat.refusal.medical_interpretation` "I cannot say what this means for your health. Ask your doctor, nurse or pharmacist." · `chat.refusal.contact_request` "I only share phone numbers and websites printed on your paper or checked by a person. See Get help nearby." For `dramatize`, the clause is deleted and, if nothing remains, the sentence is dropped. In chat, the hedge also sets `refusal_kind` and `refer_to_professional` by category (§8.5) so the UI renders `chat.refer.*`.
- Every `PlanStep{kind: professional}` must name a professional; when the step names none at all (no lawyer/representative, clinician, counselor, office, helper or advocate word), `phrasing.py` appends the category's referral sentence `t_server("chat.refer.<ReferTo>")`: immigration/court/civic/employment → `lawyer_or_accredited_rep`; medical → `clinician`; housing → `housing_counselor`; benefits → `benefits_office`; tax/school/other → `sender`. Steps that already name the type-specific professional given in §4 (a hospital financial counselor, a workers' rights office, a free tax clinic, a parent center) are left as written.
- Mock provider parity (BUILD_PLAN §5.8): `phrasing_rewrite` returns "The paper says " + the sentence with its first character lower-cased; the pipeline re-lints and falls back to the hedge.

### 8.5 Legal-module limit sentences (exact copy the app may say, per category)

| Category / types | The app **says** (fixed, from PRODUCT_SPEC Appendix A unless noted) | The app **never says** | Always routes to |
|---|---|---|---|
| `immigration`, `court`, `civic` (all USCIS, EOIR, ICE, jury, traffic types) | Header `disclaimer.legal_information_only`: "This is general information about this type of paper, not legal advice about your case. Only a licensed lawyer can advise you. For an immigration case, a DOJ-accredited representative can too." · Referral `chat.refer.lawyer_or_accredited_rep`: "A licensed lawyer can advise you about your case. For an immigration case, a DOJ-accredited representative can too. Find one in Get help." · Notario line (proposed `fixed.notario_not_a_lawyer`, §7.2) · LSC line on restricted resources `status_note.lsc_restricted`: "This organization usually cannot help people without immigration papers, except survivors of violence or trafficking." + `help.lsc_alternative` "If that is not you, try these instead" | eligibility for any relief or status; what to file, argue or plead; outcome or timing predictions; whether the person may work, travel, vote or stay; any computed deadline without a seeded rule; any drafting | `immigration_legal_help` → ImmigrationLawHelp (`immlawhelp`), EOIR pro bono list (`eoir_probono`), DOJ roster (`eoir_roster`), USCIS Find Legal Services (`uscis_find_legal`); court dates → `eoir_hotline`/`eoir_acis`; never AILA when `scam_report` is active (`never_show_with_tags`) |
| `employment` (`legal_information_only`) | same header and referral; "A workers' rights office can check your pay for free." (model prose, lint-clean) | "you were underpaid", "this is wage theft/discrimination/retaliation", "you can/cannot be fired", immigration effects of a job | `workers_rights`, `wage_theft` → DOL WHD (`dol_whd`), EEOC, OSHA, `lawhelp` (LSC note shown) |
| `housing` (`housing_information_only`) | Header: "This is general information about this type of paper, not legal advice. A housing lawyer or counselor can advise you about your home." · Referral `chat.refer.housing_counselor` · Fixed `fixed.pay_or_quit`, `fixed.eviction_summons` · D-17 state sentence (§8.3) | "you have to leave by…", "you do not have to leave", notice/answer periods, validity of a notice, defenses | `eviction`, `housing_counseling`, `rent_assistance` → HUD counselors, Virginia court self-help and helpline (geo), `lawhelp`/`lsc_find` with the LSC note |
| `medical` (`medical_information_only`) | Header: "This explains what your paper says. It is not medical advice. Ask your doctor, nurse or pharmacist what it means for you." · Referral `chat.refer.clinician` · Fixed emergency card (S19) when the lexicon fires | diagnosis, interpretation of values, dosing, "you owe/do not pay", whether care was necessary, whether to appeal | `medical_bill`, `charity_care`, `insurance_denial`, `primary_care_uninsured`, `language_access` (HHS interpreter right via `hhs_ocr_lep`) |
| `benefits` (`benefits_information_only`) | Header: "This explains what your paper says. It is not a decision about your benefits. Only the office that sent it can tell you what happens next." · Referral `chat.refer.benefits_office`: "The office that sent this paper can tell you what happens next. Its number is on the paper." | eligibility of any member, benefit amounts, whether coverage continues, H.R.1 consequences for this person | `medicaid_renewal`, `snap`, `wic`, `ssa_benefits`, `benefits_navigation` (211) |
| `school`, `tax`, `other` (`general_information`) | Header: "This is general information from your paper. It can be wrong. Check the highlighted words and confirm with the sender." · Referral `chat.refer.sender`: "Ask the sender. Their contact is on the paper." · Fixed resource warnings (`warn.schools_may_not_ask_status`) | whether the child needs services or consent should be given; whether tax is owed; refund or penalty predictions | `school_enrollment`, `special_education`, `homeless_students`, `tax_notice`, `itin` |

Chat `refusal_kind` → `refer_to_professional` defaults by category when the model leaves `refer_to_professional=none` on a refusal: immigration/court/civic/employment → `lawyer_or_accredited_rep`; medical → `clinician`; housing → `housing_counselor`; benefits → `benefits_office`; school/tax/other → `sender`. `drafting` requests are always refused (D-17) with `chat.refusal.drafting`; `contact_request` with `chat.refusal.contact_request`.

### 8.6 `phrasing.yaml` schema

```yaml
version: "2026-09-30"
attribution_regex: "\\b(the|this|your|it) ?(paper|letter|notice|form|bill|summons|order|lease|label|court|judge|office|school|landlord|insurer|plan|irs|uscis|ice|social security)? ?(says|asks|lists|states|tells you|orders|warns)\\b"   # unanchored ("begins with or contains", §8.3); regexes are case-insensitive
professional_by_category:          # PRODUCT_SPEC §7.2; identical to AI_PROMPTS §5.7 (Phase 2B: DOJ-accredited reps practise immigration law only)
  immigration: "a licensed lawyer or a DOJ-accredited representative"
  court: "a licensed lawyer"
  civic: "a licensed lawyer"
  employment: "a licensed lawyer or a workers' rights office"
  medical: "your doctor, nurse or pharmacist"
  housing: "a housing lawyer or counselor"
  benefits: "the office that sent this paper"
  school: "the school office or a parent center"
  tax: "the IRS or a free tax helper"
  other: "a professional"
professional_by_document_type:     # wins over the category (court → immigration court; tax-like employment papers)
  nta: "a licensed lawyer or a DOJ-accredited representative"
  hearing_notice: "a licensed lawyer or a DOJ-accredited representative"
  ij_decision: "a licensed lawyer or a DOJ-accredited representative"
  bia_notice: "a licensed lawyer or a DOJ-accredited representative"
  ice_checkin: "a licensed lawyer or a DOJ-accredited representative"
  w2_1099: "a free tax helper or a tax professional"
  itin: "the IRS or a free tax helper"
refer_to_by_category: {immigration: lawyer_or_accredited_rep, court: lawyer_or_accredited_rep, civic: lawyer_or_accredited_rep, employment: lawyer_or_accredited_rep, medical: clinician, housing: housing_counselor, benefits: benefits_office, school: sender, tax: sender, other: sender}
professional_words: [lawyer, attorney, representative, "...", professional, preparer, tax help, tax-help, vita]   # a professional step naming one of these needs no appended referral (§8.4)
hedge_key_by_family: {eligibility: chat.refusal.eligibility, outcome: chat.refusal.outcome, advice_verb: chat.refusal.filing_advice, negated_duty: chat.refusal.filing_advice, medical_interpret: chat.refusal.medical_interpretation, legal_status: chat.refusal.filing_advice, benefits_decision: chat.refusal.eligibility, housing_law: chat.refusal.filing_advice, tax_work_conclusion: chat.refusal.filing_advice, school_decision: chat.refusal.eligibility, contact_like: chat.refusal.contact_request, dramatize: null}
languages:
  en:
    reviewed_by: null
    families:
      - id: eligibility
        domains: [all]
        skip_when_attributed: false
        patterns: ["\\byou (are|aren't|are not|'re) (eligible|not eligible|ineligible|entitled)\\b", "..."]
  es:
    reviewed_by: null
    families:
      - id: eligibility
        patterns: ["\\b(usted )?(es|no es) elegible\\b", "\\bcalifica(s)?\\b", "..."]
```

A `languages.<tag>` section may carry its own `attribution_regex` (the `es` section has one, including an appositive "Su arrendador, X, dice …"); it is applied on top of the top-level English one when that language is linted, and a target language other than English is linted only when its `reviewed_by` is set — English is always linted (CL-050(c)). As built (checked 2026-09-30): only a **Spanish** seed list is committed (`reviewed_by: null`, so it is not applied); **no Dari, Pashto or Arabic section exists yet**, although this section planned all four. Every non-English target language therefore lints English only (`body_en`, and for chat no English draft exists) and gets `warnings: [phrasing_lint_unavailable]`: model sentences written in Spanish, Arabic, Dari or Pashto reach the reader unlinted, and because the client shows the `warning.checks_unavailable` chip for Tier 3 packs only (`warningChipKeys`), readers of these Tier 1/2 languages see no chip either. Open (CL-073, WP2): commit the `ar`/`prs`/`ps` seed lists; apply drafted (`reviewed_by: null`) sections the way `emergency.yaml` does (CL-030(h)) while keeping the warning until a reviewer signs; and give chat an English shadow answer to lint. CI: `test_phrasing.py` asserts every example in D-17 and PRODUCT_SPEC §7.2 is caught, every allowed sentence in §8.3 passes, and the rewrite template output passes.

---

## 9. Open questions, "general guidance" items and cross-WP requests

### 9.1 Decisions this file had to make that the architect should confirm (D-11/D-12 gaps)

1. **Past dates on non-court/USCIS papers** (§5.1 step 4): D-12 defines `critical` only for court/USCIS papers; this file sets `high` for past `response_due`/`payment_due`/`appointment`/`hearing_date` and `medium` for past `expiry`/`move_date`, with the `date_passed` headline and an `expired_date` red flag. Alternative: `info` with the red flag only.
2. **`urgency.critical.floor`** exists in PRODUCT_SPEC §5.5 but no rule emits it (all D-12 floors are `high`). Either drop the key or assign it (candidate: `ice_checkin` with a past report date and no future one).
3. **Scam re-typing** (§6.5) sends agency-impersonation papers to `other_notice`; a cap of `medium` on urgency for `scam_risk=likely` papers is proposed but not applied (a forged date should not produce a `critical` banner above a scam card).
4. **Move-anchored rules** (`ar11_10d`, `eoir33_5bd`) can essentially never produce an `estimated` date from a paper (§5.3); they are kept for `/v1/rules` transparency and the fixed address notice. If the architect wants a visible "10 days after any move" line, `DateInfo` needs a `rule_id` on an `unresolved` kind or `PlanStep` needs a rule link (contract change).
5. **`aca_external_review_4mo`** is expressed as 120 days because `DeadlineRule.days` is an integer (§5.3); the card says "Confirm with the sender."
6. **Fixed-notice extension**: `fixed.address_change_multi_agency` could also apply to `ij_decision`/`bia_notice` at `medium` (case still active); D-20 names only `nta`/`hearing_notice`, so this file keeps D-20.
7. **Chat starters** (`chat.starter.miss_date` "What happens if I miss the date?") invite `outcome` refusals; the mock and the prompt should answer them with the paper's own consequence sentence when printed and `chat.refer.*` otherwise — noted for AI_PROMPTS §5.

### 9.2 Items marked "general guidance, confirm with counsel/agency" (resources.md *Warnings*, last bullet, plus items found while writing §4)

Shown in the UI only as `questions_to_ask` or as a `professional`/`ask` step — never as a date, amount or rule: Medicaid post-termination reconsideration/reinstatement window (§4.5) · SSA 60-day appeal window and +5 mail days (§4.5) · FLSA 2/3-year limitation period (§4.8, not surfaced at all) · rent-increase notice periods (§4.6) · Medicaid continuation of benefits when a hearing is requested before the effective date (§4.4) · Original Medicare 120-day window (§4.4; page says "by the date on your MSN") · RFE up to 84 (+3) days, NOID 30 (+3), I-290B 30 (+3) (§4.1) · ITIN expiry after unused years (§4.9) · ICE online check-in satisfying release terms when later than the printed date (§4.2) · SNAP 30-day / 7-day expedited processing (§4.5) · parole fee ~$1,000 (§4.2) · post-judgment eviction steps (VA 10-day appeal, writ, sheriff ≥ 72 h) (§4.6) · asylum-interview rules effective 2026-08-21 (surface only via `warn.asylum_rules_aug_2026` and the paper's own text) · BIA 30-day and EOIR-33 5-business-day rules stay `likely` until a live page read (§5.3) · Medicare Advantage/Part D 65-day Level-1 window pending a human re-read (RESOURCE_DB §13) · Poison Control 24/7 availability (fixed copy already avoids the claim).

### 9.3 Requests to other packages (filed as DECISIONS §14 CL-010 on 2026-09-27; status is set by the receiving package)

- **WP0 (`en.json` keys):** `fixed.court_date_is_the_deadline`, `fixed.eob_not_a_bill`, `fixed.traffic_court_immigration`, `fixed.conditional_card`, `fixed.notario_not_a_lawyer` with the copy in §7.2; scam reason keys `scam.asks_for_id_numbers` ("Asks for your ID or bank numbers") and `scam.upfront_fee` ("Asks you to pay before you start") for §6.1 signals that currently score without a chip. Until added, the YAML rows stay commented out and `scam_reasons` omits them.
- **WP3 (`data/rules/prepare.yaml` additions marked (rec.) in §4):** `uscis_receipt: [bring_notice, bring_receipt_number]` · `uscis_approval: [bring_notice]` · `uscis_denial: [bring_notice, bring_receipt_number]` · `ead_related`, `green_card_related`: `[bring_notice, bring_photo_id]` · `tps_related: [bring_notice, bring_a_number]` · `parole_related: [bring_notice, bring_a_number, bring_photo_id]` · `ij_decision`, `bia_notice`: `[bring_notice, bring_a_number]` · `traffic_court: [bring_the_summons, bring_photo_id]` · `lab_result: [bring_notice]` · `discharge_instructions: [bring_notice, bring_medication_list]` · `vaccine_record: [bring_vaccine_record]` · `appointment_reminder: [bring_notice, bring_insurance_card, bring_photo_id]` · `lease: [bring_lease]` · `rent_increase: [bring_notice, bring_lease]` · `school_meals: [bring_proof_income, bring_household_ids]` · `report_card: [bring_school_records]` · `w2_1099: [bring_notice]` · `i9: [bring_notice, bring_photo_id]` · `offer_letter: [bring_notice]`. All keys exist in `_meta.yaml.checklist`.
- **WP3 (resource gaps noticed):** Low Income Taxpayer Clinics (IRS LITC finder) for `tax_notice`/`itin`; a Medicaid fair-hearing explainer per state; an EOB explainer that is not commercial (RESOURCE_DB §14); any verified traffic-court self-help page (tag is fallback-only).
- **WP7 (fixtures):** `nta_hearing_date` manifest should record the frozen `today` that makes the hearing ≤ 7 days (`critical`) so §5.4 is deterministic; `scam_gift_card_letter` transcript must contain a gift-card phrase, a deportation-for-payment threat and a non-.gov URL near "USCIS" (§6.2 worked check).
- **Architect (DECISIONS):** the seven items in §9.1.

### 9.4 Conflicts and near-conflicts noticed across the authoritative docs (not edited here)

1. PRODUCT_SPEC §12.3 says `uscis_rfe_87d` renders `high`/`critical` "by date" while D-12's critical set excludes `response_due`; consistent only through the past-date rule — §5.4 states that reading.
2. Resolved 2026-09-27 (completion critic): the rewrite template's `{professional}` (§8.4, §8.6) and AI_PROMPTS §2/§5.7 now all use the seven `DocumentCategory` words of PRODUCT_SPEC §7.2; the PRODUCT_SPEC disclaimer sentences remain the headers.
3. RESOURCE_DB §14 and §13 assume two fixed-copy sentences live in this file ("THIS IS NOT A BILL" for EOBs; "talk to an immigration lawyer before pleading" for traffic court) but PRODUCT_SPEC Appendix A has no `fixed.*` keys for them — requested in §9.3.
4. `ar11_10d` applicability: the verbatim API_CONTRACT §3.10 entry lists eight USCIS types, while the §2 master table also marks the rule for `uscis_noid` and `parole_related`. Because BUILD_PLAN §5.3 requires the §3.10 entry to be copied verbatim into `deadlines.yaml`, the YAML uses the eight; WP0 may extend the contract example (a two-type addition, no schema change) if the architect wants the master table's reading.
5. The brief for this completion pass asked for "§7 legal-module boundaries" and "§8 open questions", while the file's own completion notice (and BUILD_PLAN §5.3) promised §7 fixed notices and §8 phrasing lint; per the completion instructions the notice wins, so legal boundaries live in §4 block **DR** and §8.5, and open questions in this §9.
6. **`nta` category.** This file (§2, §3.4) and the AI_PROMPTS classification rule put every immigration-court paper, including the DHS-issued Notice to Appear, in `category=court`; PRODUCT_SPEC §12.3 and BUILD_PLAN Appendix D list the fixture `nta_hearing_date` as `nta / immigration`. Behaviour is identical either way (`legal_information_only`, the past-date `critical` rule covers both categories, tags are per type), so this file keeps `court` and the architect decides which listing to align; the golden test asserts `document_type`, not `category` (DECISIONS §14 CL-010).
