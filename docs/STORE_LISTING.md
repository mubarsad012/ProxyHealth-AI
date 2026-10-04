# ProxyHealth AI — Store listing (App Store Connect + Google Play Console)

Status: **draft, pending counsel** (DECISIONS §12 Q3; COMPLIANCE_PRIVACY §18.6). Owner: WP8. Written 2026-09-29 from `docs/research/compliance.md` §1 (the declaration checklist), `docs/COMPLIANCE_PRIVACY.md` §5.4, §10–§12, §16–§17 and DECISIONS §13. Nothing here may be pasted into a console until the blockers in §0 are cleared.

Rules for every word below (COMPLIANCE_PRIVACY §5.4, §17):
- Store copy is literally true for a **paid-tier** build — the only tier a store build may point at (COMPLIANCE_PRIVACY §3). A build whose `EXPO_PUBLIC_API_URL` answers `data_use_tier` ≠ `paid` is a release blocker — that includes the test-build tiers `local` and `attested` of `AI_PROVIDER=openai_compat`, which production refuses anyway (D-32).
- Boundary sentences are the §5.1 disclaimers **verbatim**; otherwise never "advice", "diagnosis", "eligible", "guaranteed", "certified", "lawyer-reviewed", "doctor-approved" or "HIPAA".
- Copy meant for a console field lives in ```` ```text ```` blocks. `apps/api/tests/unit/test_privacy_claims.py::test_store_listing_copy_has_no_forbidden_phrase` scans those blocks for the §17 `forbidden_phrases`.
- Screenshots come from the synthetic fixtures only (SAMPLE watermark visible). Never a real person's paper.
- Store field length limits quoted here (name/title 30, Apple subtitle 30, Apple keywords 100 bytes, Play short description 80, descriptions 4,000 characters) are general knowledge, not from the research files — **check them in each console before pasting**.

---

## 0. Blockers and open questions (clear before any submission)

| # | Blocker | Store | Owner / question | Evidence when cleared |
|---|---|---|---|---|
| B1 | Organization developer account (legal entity, not an individual) | Apple 5.1.1(ix) (launch blocker); Play (recommended for the same reason) | user — DECISIONS Q2 | Team ID of the organization in `apps/mobile/eas.json` `submit.production.ios.appleTeamId` |
| B2 | Operator legal name, postal address, privacy e-mail in the policy | both | user — COMPLIANCE_PRIVACY Q15 | `apps/mobile/public/privacy/index.html` has no `TODO` left |
| B3 | Bundle id / package and web host confirmed (placeholders `org.proxyhealth.app`, `https://proxyhealth.expo.app/privacy`) | both | user — DECISIONS Q4 | `app.json` `ios.bundleIdentifier` / `android.package`; `PRIVACY_POLICY_URL` |
| B4 | Paid tier live: every `GEMINI_KEYS` slot `billing:true`, distinct projects; `GET /v1/config` on the production API returns `data_use_tier: "paid"` | both | user — DECISIONS Q1 | dated screenshot of Cloud Billing per project in `docs/RUNBOOK.md` |
| B5 | iOS vault excluded from iCloud backup and verified on a dev build | Apple 5.1.3(ii) | user — COMPLIANCE_PRIVACY Q16 | RUNBOOK dev-build log; until then ship Android first. **Open on 2026-10-01**: not implemented (SDK 57 has no API; needs a config plugin/native module — COMPLIANCE_PRIVACY §10.2). The App Store description's "Papers you save stay only on this phone" becomes true on iOS only when B5 closes. |
| B6 | Counsel review: UPL framing, FDA display exclusion, HBNR memo, state paragraphs, this listing | both | user — Q3 | COMPLIANCE_PRIVACY §18.1–§18.6 ticked with names and dates |
| B7 | Title length: DECISIONS §13 title is 37 characters; both consoles cap the name at 30 (verify) | both | architect — DECISIONS §14 CL-060 | the fallback in §1 is accepted or the title is shortened |
| B8 | SDK 58 upgrade before store submission (ARCHITECTURE §5.3) | both | WP0 install window | `npx expo config --type prebuild` green on SDK 58 |

---

## 1. Identity (both stores)

| Field | Value |
|---|---|
| App name (as decided, DECISIONS §13) | ProxyHealth AI: Your paper, explained |
| Fallback if the 30-character name limit applies | Name "ProxyHealth AI"; Apple subtitle "Your paper, explained"; Play title "ProxyHealth AI" |
| Apple subtitle (as decided) | Understand letters, bills and notices in your language. (55 characters — use "Your paper, explained" if the 30-character limit applies) |
| Apple primary / secondary category | Reference / Utilities — deliberately **not** Medical (DECISIONS §13) |
| Google Play category | Tools — deliberately **not** Medical; still under the Health Content and Services policy (COMPLIANCE_PRIVACY §11) |
| Age | 18+ on both stores (§2.4, §3.6) |
| Storefronts | United States only (D-03; the resource DB, rules and copy are US-only) |
| Price | Free; no in-app purchases; no ads |
| Support URL | `<web host>/privacy#contact` until a support page exists (B2, B3) |
| Privacy policy URL | `PRIVACY_POLICY_URL` = `https://proxyhealth.expo.app/privacy` (placeholder, B3) — public HTML, not a PDF, not geofenced (served from `apps/mobile/public/privacy/index.html`) |
| Marketing URL | none in v1 |
| Copyright | `<operator legal name>` (B2) |

Apple keywords (comma-separated, no spaces after commas; ≤ 100 bytes — 99 as written):

```text
letter,bill,notice,translate,explain,read aloud,immigrant,paperwork,mail,Dari,Arabic,Spanish,Pashto
```

Google Play short description (≤ 80 characters — 78 as written):

```text
Your paper, explained. Understand letters, bills and notices in your language.
```

Apple promotional text (≤ 170 characters):

```text
Take a photo of a letter, bill or notice. Get three calm cards in your language, with the exact words from the page next to every date and amount.
```

## 1.1 Full description (both stores; ≤ 4,000 characters)

```text
ProxyHealth AI — Your paper, explained.

Take a photo of a letter, bill, notice or form. In about a minute you get three calm cards in your own language:
• What is this?
• What is it asking for?
• Your step-by-step plan

Every date, amount and document on those cards is shown next to the exact words on the page it came from, with a note on how sure the app is. Anything the app could not find on the page is listed separately so you can check it.

What else it does
• Show the clerk: a short card in English you can hand over at a counter.
• Read aloud: a speaker button after every paragraph, so you can listen with earbuds.
• Get help nearby: groups and hotlines from a list that a person checked, with the date they were checked.
• Reminders for the dates it found, and a text-only quick sheet you can print or share.
• Stuck on a website? Send a screenshot and get the next taps, named as they appear on the screen.
• Is this a scam? It warns you when a letter asks for gift cards, wire transfers or app payments.
• Many languages, including Spanish, Dari, Pashto and Arabic, with right-to-left layouts. Languages translated by a computer are labelled.
• Sample papers: try everything with made-up sample papers first.

What happens to your paper
Your photo is sent to Google's AI (Gemini) to be read. Our server does not keep it. Google does not use your paper to improve its products. Google keeps a short safety log for a limited time, then deletes it. Papers you save stay only on this phone. You can delete everything any time. You see this before your first photo is sent, and you can say "Not now".

What it does not do
It does not decide anything for you. It does not fill in forms, invent phone numbers or guess dates. For legal papers: This is general information about this type of paper, not legal advice about your case. Only a licensed lawyer can advise you. For an immigration case, a DOJ-accredited representative can too. For medical papers: This explains what your paper says. It is not medical advice. Ask your doctor, nurse or pharmacist what it means for you.

No account. No ads. No trackers. This app is for adults 18 and older.
```

## 1.2 What's new (first release)

```text
First release: read a letter, bill or notice in your language, with the words from the page next to every fact.
```

## 1.3 Screenshot list (fixtures only; SAMPLE watermark visible; English and Dari sets)

Capture on a production-profile build pointed at the **staging paid-tier API** using the built-in sample papers only (the consent badge must read "Paid service", not "Sample mode"). Sizes: whatever App Store Connect and Play Console require at submission time (phone sets are mandatory; tablet sets for iPad only if `supportsTablet` stays true).

| # | Screen | Fixture / state | Caption (≤ 1 line, pack-translated for the Dari set) |
|---|---|---|---|
| 1 | S1 language grid, Dari highlighted | — | "Choose your language" |
| 2 | S2 "What happens to your paper" with the Paid service badge | — | "You see how your paper is handled first" |
| 3 | S7 result: urgency banner + three cards | `medicaid_address_confirmation` | "Three calm cards: what, asking for, plan" |
| 4 | S8 source view with the highlighted words | `uscis_rfe_87d` | "Every fact shows the words on the page" |
| 5 | S10 "Show the clerk" card | `medicaid_address_confirmation` | "A card in English for the counter" |
| 6 | S11 Get help nearby with "Verified on" dates | `inova_final_notice` (state VA) | "Help from a list a person checked" |
| 7 | S16 "Is this a scam?" result | `scam_gift_card_letter` | "Warnings about gift-card and wire scams" |
| 8 | S7 in Dari (right to left) with speaker buttons | `va_pay_or_quit_14d` | "Right-to-left languages, read aloud" |

No screenshot may show a chat answer that sounds like advice, an unverified fact without its label, or the developer section.

---

## 2. Apple App Store Connect

### 2.1 Guideline answers (COMPLIANCE_PRIVACY §10.1; compliance.md §1)

| Guideline | Our answer | Where to verify |
|---|---|---|
| 5.1.1(ix) regulated field | Submitted by the organization account (B1). Individual accounts are not used. | Membership details page |
| 5.1.2(i) third-party AI | In-app consent **before the first photo is sent**, naming Google Gemini: S2 "What happens to your paper" shows "Your photo is sent to Google's AI (Gemini) to be read. Our server does not keep it." plus the paid line, the 18+ line, "I understand, continue", "Not now" and "Try a sample paper first". The server refuses analyze/troubleshoot/chat without the consent header (`428 consent_required`). Consent is re-asked when the consent version or tier changes; "Stop sending papers" in Settings withdraws it. | `consent.test.tsx`; `tests/contract/test_errors.py::test_428_without_consent`, `::test_428_stale_or_malformed_consent` |
| 5.1.1(i) privacy policy | Linked in App Store Connect and in the app (S2 "Read more" → notice → "Read the full privacy policy"; Settings → Privacy). Covers data, uses, Gemini as processor, retention, deletion, revocation. | `make export-web && test -f apps/mobile/dist/privacy/index.html` |
| 5.1.1(ii) consent for any data | S2 before any upload; the install id is optional on pre-consent calls. | as 5.1.2(i) |
| 5.1.1(iii) minimization | Camera + the system photo picker; no full Photos access. | `app.json` plugin strings |
| 5.1.1(v) login | No accounts, no login — nothing to delete server-side. | — |
| 5.1.2(vi), 5.1.3(i) | No analytics, advertising, attribution or crash SDKs; camera and health data go only to inference. | `apps/mobile/package.json` |
| 5.1.3(ii) iCloud | Vault excluded from iCloud backup before iOS submission (B5). | RUNBOOK |
| 1.4.1 medical | The medical disclaimer is visible without scrolling above the first card for medical papers; chat refuses medical interpretation with a clinician referral. | fixtures `prescription_label`, `insurance_denial_180d` |
| 2.3.1 metadata | Notes for Review (§2.5) describe each feature specifically. | this file |
| Privacy manifest | `ios.privacyManifests`: UserDefaults `CA92.1`, FileTimestamp `C617.1`, SystemBootTime `35F9.1`, `NSPrivacyTracking: false`, no tracking domains. | `npx expo config --type prebuild` |
| Export compliance | `ios.config.usesNonExemptEncryption: false` (HTTPS only). | `app.json` |

### 2.2 App Privacy ("nutrition label") — paid tier, conservative stance (COMPLIANCE_PRIVACY §10.3)

Tracking: **No** ("Data Used to Track You": none). Linked to you: **nothing** (no account, no persistent identifier). We do not rely on the "sent to your servers then immediately discarded" exemption for paper content, because the paper also transits Google's abuse-detection log. Counsel may approve the minimal variant (Q17); the conservative answers are never false, so they are the default.

| Apple data type | Collected | Linked to user | Tracking | Purposes | Why |
|---|---|---|---|---|---|
| Photos or Videos | Yes | No | No | App Functionality | page photos are sent to be read |
| Health & Fitness → Health | Yes | No | No | App Functionality | medical papers contain health data |
| Sensitive Info | Yes | No | No | App Functionality | papers can reveal religion (calendar notes), ethnicity; immigration status is inferable |
| User Content → Other User Content | Yes | No | No | App Functionality | chat questions, "what are you trying to do" on screenshots |
| Location → Coarse Location | Yes | No | No | App Functionality | state and first 3 ZIP digits the user types (never GPS) |
| Identifiers → Device ID | Yes | No | No | App Functionality | app-generated random install id, hashed server-side, forgotten after 30 days (abuse prevention) |
| Usage Data → Product Interaction | Yes | No | No | Analytics, App Functionality | "Was this clear?" / "Report a problem" counts |
| Diagnostics → Performance Data | Yes | No | No | App Functionality | latency and token counts, content-free |
| Contact Info, Financial Info, Contacts, Browsing History, Search History, Purchases, Precise Location, Crash Data, Other Diagnostic Data, Advertising Data | No | — | — | — | not collected; no crash or analytics SDK |

Any new SDK, account system, cloud sync or crash reporter re-opens this table before the next build.

### 2.3 Age rating

Answer the questionnaire truthfully — "Medical or wellness topics": **Yes** (infrequent/mild informational); AI assistant / chatbot: **Yes** (it answers only from the user's own paper and refuses advice); user-generated content shared with others: **No**; unrestricted web access: **No**. Then choose **18+** (the option to set a higher rating than computed). Reason for the reviewer: the Gemini API terms require adult users and forbid apps likely to be used by under-18s; the consent screen states "This app is for adults 18 and older."; school papers are explained to parents.

### 2.4 Accessibility Nutrition Labels (optional)

Claim only after the COMPLIANCE_PRIVACY §15 matrix passes on a dev build and is recorded in `docs/RUNBOOK.md` (Q24): proposed VoiceOver, Larger Text, Sufficient Contrast, Reduced Motion. Do **not** claim Voice Control or captions.

### 2.5 Notes for Review (paste into App Store Connect → App Review Information)

Sign-in required: **No** (no accounts). Demo account: not applicable. Contact: `<operator contact>` (B2).

```text
ProxyHealth AI photographs a letter, bill or notice and explains what it says in the reader's language. It does not diagnose, decide eligibility or fill in forms. Every screen that explains a paper carries a fixed boundary sentence; for medical papers: "This explains what your paper says. It is not medical advice. Ask your doctor, nurse or pharmacist what it means for you." There is no account and no login.

How to test: on first launch choose a language, then read the "What happens to your paper" screen. This is our disclosure and consent for sending the photo to Google's Gemini API (paid terms; our server does not keep the photo). Tap "Try a sample paper first" to use built-in sample documents without sending anything of your own, or tap "I understand, continue" and photograph any printed page. Sample papers are made up and marked SAMPLE.

Where things are: the boundary sentence appears above the first result card. "Need help now?" at the top of every screen opens a fixed emergency card. "Was this clear?" and "Report a problem" under every AI-made card are the flag control. Settings shows the consent status, the privacy notice and "Stop sending papers". Settings also has "Delete everything on this phone", which removes all saved papers. Saved papers stay on the device only.

Permissions: the camera (to photograph a paper) and the system photo picker (no photo-library access). Notifications are asked for only when the user sets a reminder. The app is rated 18+ because the AI provider's terms require adult users. Server status: GET {API_URL}/health returns data_use_tier: paid.
```

---

## 3. Google Play Console → App content

### 3.1 Health apps declaration (Health Content and Services policy)

| Question | Answer |
|---|---|
| Does the app have health features? | **Yes** — it explains medical papers (bills, insurance letters, prescription labels, immunization notices). |
| Health categories | Medical information / reference (educational explanation of the user's own document). Not: medical device, clinical decision support, disease management, Health Connect, human-subject research. |
| Is it a medical device / does it diagnose, treat, cure or prevent any condition? | **No.** Statement for the declaration and the description: "ProxyHealth AI is not a medical device. It explains what a paper says and does not diagnose, treat, cure, or prevent any medical condition." |
| In-app reminder to consult a healthcare professional | Yes — `disclaimer.medical_information_only` ("This explains what your paper says. It is not medical advice. Ask your doctor, nurse or pharmacist what it means for you.") above the first card of every medical result, in chat and on the quick sheet; chat refuses medical interpretation with a clinician referral. |
| Uses Health Connect | No |
| Government affiliation | None; the app is not affiliated with any agency it mentions |

### 3.2 Data safety form (paid tier; same stance as Apple, COMPLIANCE_PRIVACY §11.1)

Google Gemini on paid terms is treated as a **service provider** (no product-improvement use), so nothing is declared as *shared*. Paper content is declared as *collected* because it transits Google's abuse-detection log.

| Data type | Collected | Shared | Processed ephemerally | Required or optional | Purposes |
|---|---|---|---|---|---|
| Photos and videos → Photos | Yes | No | No (stance above) | Required | App functionality |
| Health and fitness → Health info | Yes | No | No | Required | App functionality |
| Personal info → Other info (names, dates printed on papers) | Yes | No | No | Required | App functionality |
| Location → Approximate location (typed state + ZIP prefix) | Yes | No | Yes | Optional | App functionality |
| Messages → Other in-app messages (chat questions, screenshot goal) | Yes | No | Yes | Optional | App functionality |
| App activity → App interactions (feedback counts) | Yes | No | No | Optional | Analytics, App functionality |
| App info and performance → Diagnostics (content-free) | Yes | No | No | Required | App functionality |
| Device or other IDs (app-generated install id, hashed) | Yes | No | No | Required | Fraud prevention, security, and compliance |
| Everything else (contacts, calendar, files other than the chosen photo or PDF, audio, financial info, precise location, web browsing, installed apps, crash logs) | No | — | — | — | — |

Security practices: data is encrypted in transit — **Yes** (HTTPS only; `preview`/`production` EAS profiles must use an `https://` API URL — `scripts/ci.sh` checks `eas.json`). Users can request that data be deleted — **Yes**: everything is on the device and deletable in the app ("Delete everything on this phone"); the server holds no paper to delete (the policy says so). Independent security review — **not claimed**. Committed to the Play Families policy — not applicable (18+).

### 3.3 Other App content declarations

| Item | Answer |
|---|---|
| Privacy policy | `PRIVACY_POLICY_URL` (public HTML; also linked in the app) |
| App access | "All functionality is available without special access." No login. Add the §2.5 testing paragraph as instructions. |
| Ads | No ads |
| Target audience and content | **18 and over only**. Not designed for children. Not appealing to children. |
| Content rating (IARC) | Answer truthfully: reference/education app; references to medical topics (informational); users interact only with the app's own AI answers, no user-to-user communication or sharing; no location sharing; no purchases. Accept the computed rating; the 18+ target audience and the consent line carry the age requirement. |
| News app | No |
| Government app | No |
| Financial features | None |
| COVID-19 contact tracing / status | No |
| Data deletion (account) | Not applicable — no accounts |
| Photo and Video Permissions | The app does **not** request `READ_MEDIA_IMAGES` or `READ_MEDIA_VIDEO` (both are in `android.blockedPermissions`, with `RECORD_AUDIO`). Photos are chosen with the system photo picker and PDFs with the system document picker; the camera uses `CAMERA`. Verify the merged manifest of every `.aab` (COMPLIANCE_PRIVACY §12.1) and record it in `docs/RUNBOOK.md`. |
| AI-Generated Content policy — in-app flag control | Every AI output (summary, demands, plan, details, glossary, red flags, clerk card, chat answers, troubleshoot steps, resources, language banner, quick sheet) has "Was this clear?" → No → reasons including "This is rude or offensive", "A date, amount or fact is wrong" and "This looks like a scam but the app did not say so", plus "Report a problem" — without leaving the screen. Reports are counted (no content) and reviewed by the operator weekly (RUNBOOK). The app never drafts official documents or forms (COMPLIANCE_PRIVACY §6.4). |
| Health apps declaration | §3.1 |
| Data safety | §3.2 |

---

## 4. The compliance.md §1 declaration checklist, answered

| # | Checklist item (`docs/research/compliance.md` §1) | Answer in this listing | Status |
|---|---|---|---|
| 1 | Privacy policy (web URL + in-app link) covering images/text, Gemini as processor, retention, deletion, revocation | §1 table; policy sections 3–5, 8, 12 (`apps/mobile/public/privacy/index.html`) | ready except B2/B3 |
| 2 | In-app consent before the first scan naming Google Gemini and what is sent | §2.1 row 5.1.2(i) (S2) | implemented and tested |
| 3 | Apple privacy label + Play Data safety answered consistently | §2.2 and §3.2 (same conservative stance, same data types) | ready; Q17 open |
| 4 | Play Health apps declaration; Apple Notes for Review | §3.1; §2.5 | ready, pending counsel |
| 5 | Camera purpose string; photo picker instead of library access | `app.json` strings (COMPLIANCE_PRIVACY §12); §3.3 Photo and Video Permissions | implemented; manifest check per build |
| 6 | In-app report/flag control on every AI output | §3.3 AI-Generated Content row | implemented (`FeedbackRow`) |
| 7 | Age 18+; "Medical or wellness topics" yes | §2.3; §3.3 target audience | ready |
| 8 | Account deletion if accounts exist, otherwise no login | no accounts, no login (§2.1 5.1.1(v); §3.3) | n/a by design |
| 9 | Organization developer account (Apple 5.1.1(ix)) | §0 B1 | **blocked on Q2** |

## 5. Localized listings

v1 listing languages: English (en-US) first. Spanish (es-US) and the Dari/Arabic screenshot sets are SHOULD once the packs have a named reviewer (DECISIONS Q6); a machine-translated store description is not published. Captions in §1.3 are pack strings, so the Dari set reuses the reviewed app copy.

## 6. Before pressing Submit

1. §0 blockers cleared; COMPLIANCE_PRIVACY §18 ticked with names and dates.
2. `scripts/ci.sh` green on the release commit; `apps/api/.venv/bin/pytest apps/api/tests/unit/test_privacy_claims.py` green (it scans the ```` ```text ```` blocks above).
3. `curl <prod API>/v1/config` → `data_use_tier: "paid"`; the store build's `EXPO_PUBLIC_API_URL` is that host (`eas.json` production profile).
4. The privacy policy at `PRIVACY_POLICY_URL` prints the same consent version as the production `CONSENT_VERSION`.
5. Screenshots re-captured if any copy on them changed.
