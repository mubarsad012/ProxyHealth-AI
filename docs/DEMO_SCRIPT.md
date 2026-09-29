# ProxyHealth AI — Demo script (what shipped)

Owner: WP7. Source: `docs/PRODUCT_SPEC.md` §13, adapted to the fixture set, mock provider and
offline bundle that exist in the repo. Every sample paper is synthetic, carries a diagonal
**SAMPLE** watermark and the footer "SAMPLE — synthetic document made for demonstration. Not a
real letter." Keyed demos use these samples or a photographed printout of one — **never a real
personal letter** (D-29, PRODUCT_SPEC §12.4).

## 0. Setup (both variants)

| Item | How |
|---|---|
| API (zero keys) | `cd apps/api && .venv/bin/uvicorn proxyhealth_api.main:app --port 8000` with no `.env` → `AI_PROVIDER=mock`, `data_use_tier: demo` |
| Web app | `cd apps/mobile && EXPO_PUBLIC_API_URL=http://127.0.0.1:8000 npx expo start --web` (or `make dev` once WP8 lands it) |
| Phone | Android EAS development build; Expo Go for smoke only |
| Settings | region `VA`, ZIP3 `220`, text size L |
| Printout | `apps/api/data/fixtures/medicaid_address_confirmation/page-1.png` printed on letter paper (for the camera match) |
| Browser tab | `http://127.0.0.1:8000/health` |

Check before going on stage:

```
apps/api/.venv/bin/python apps/api/scripts/make_fixtures.py --check     # fixtures in sync (18 fixtures)
apps/api/.venv/bin/python apps/api/scripts/sync_to_mobile.py --check    # offline bundle matches
curl -s http://127.0.0.1:8000/v1/demo/fixtures | python3 -m json.tool | head
```

## 1. The sample set (`GET /v1/demo/fixtures`, 18 entries)

Recorded languages: **en, es, prs (Dari), ar** for the eight demo samples marked ★; English only
for the rest. Any other target language returns the English output with a visible `⟦tag⟧`
marker on every sentence — honest, not a fake translation.

| Sample (`id`) | Type / category | What the result shows (frozen `today` 2026-10-02) |
|---|---|---|
| ★ `medicaid_address_confirmation` | `medicaid_renewal` / benefits | `high`, stated **October 14, 2026**, 2 demands, clerk card adds the free-interpreter line |
| `uscis_i797c_receipt_i765` | `uscis_receipt` / immigration | `info`; fixed notice `fixed.uscis_receipt_i765` (receipt is not work authorization) |
| ★ `uscis_rfe_87d` | `uscis_rfe` / immigration | `high`, stated **October 13, 2026** (87-day window printed), 3-item evidence list, "notice on top" |
| ★ `nta_hearing_date` | `nta` / court | `critical` (hearing **October 7, 2026 8:30 AM**), Verify-this-date → EOIR hotline, address-change fixed notice |
| ★ `inova_final_notice` | `medical_bill` / medical | `medium` (pay by October 28, 2026), `urgency_pressure` flag on "FINAL NOTICE", `scam_risk: none`, Inova financial assistance first in VA; Spanish + Arabic taglines rendered on the page |
| `insurance_denial_180d` | `insurance_denial` / medical | `medium`, **estimated** October 17, 2026 via `aca_internal_appeal_180d` with its formula and source link |
| `prescription_label` | `prescription_label` / medical | `info`; glossary; medical disclaimer; describes, never interprets |
| `school_immunization_notice` | `immunization_notice` / school | `medium` (record due October 23, 2026); vaccine-records resource |
| ★ `va_pay_or_quit_14d` | `pay_or_quit` / housing | `high`, stated **October 8, 2026**; "within 14 days" stays unresolved; `fixed.pay_or_quit` |
| `snap_interview_notice` | `snap_notice` / benefits | `high` phone interview October 9, 2026 10:00 AM; bring list |
| `irs_cp_notice` | `irs_notice` / tax | `medium` (CP14, pay by October 26, 2026); IRS notice lookup resource |
| ★ `jury_summons` | `jury_summons` / civic | `medium` (questionnaire by October 23, 2026); `fixed.jury_summons` |
| ★ `scam_gift_card_letter` | `other_notice` / immigration | `scam_risk: likely` (gift cards + deportation threat + non-.gov site), `scam_report` first, DHS OIG leads the list with FTC |
| `blurry_unreadable_page` | `unknown` / other | `quality.readable=false`, one model call, re-scan tips |
| `spanish_lease` | `lease` / housing | `info`; `detected_language: es`; `document_language_differs` when the UI is not Spanish |
| `w2_form` | `w2_1099` / employment | `info`; glossary (EIN, federal income tax withheld); ITIN resource |
| `traffic_court_notice` | `traffic_court` / court | `high` (prepay by October 9, court October 13, 2026); legal disclaimer |
| ★ `portal_file_too_large` (screenshot) | — / benefits | steps name "Choose File", "Upload", "Back" exactly; caution about "Submit Application"; no emergency |

All phone numbers on the samples are fictional `555-01xx` numbers; the only real web address
printed is `irs.gov/payments` on the IRS sample. The scam letter's site is a subdomain of the
reserved `example.com`.

## 2. Zero keys (`AI_PROVIDER=mock`) — three minutes

| Time | Screen | Do | Say / point at | Expected |
|---|---|---|---|---|
| 0:00 | S1 | Tap دری (Dari) | "Any language, one tap; right-to-left flips immediately." | Grid mirrors |
| 0:10 | S2 | Point at the badge; tap "Try a sample paper first" | "This build contacts no AI service; the consent screen says so." | Badge "Sample mode"; sample picker opens with 18 samples |
| 0:20 | S5 → S6 | Pick "Medicaid letter asking to confirm your address" → "Read this paper" | "The mock adds 300–900 ms so the reading steps are visible." | S6 steps, then S7 |
| 0:30 | S7 | Scroll; tap the crop on the date; tap a speaker; tap "Remind me" | "Every fact is a quotation with its crop. The date is `stated`, so it can become a reminder." | Banner for October 14, 2026 (`high`); Dari text from `out.prs.json` |
| 1:05 | S7 → S10 | "Show the clerk"; long-press "Back to me" | "English card, fixed template; the interpreter line appears because Medicaid is HHS-funded." | Card with the interpreter line |
| 1:25 | S7 → S11 | "Get help nearby" | "Only resources from our database, with the date we checked them." | Medicaid resources, national fallbacks |
| 2:00 | S16 | "Stuck on a website?" → sample screenshot | "Steps name the buttons exactly as the screen writes them." | "Choose File", "Upload", "Back"; caution on "Submit Application" |
| 2:20 | S5 | Sample "Letter claiming to be USCIS and demanding gift cards" | "Scam risk is scored in code; reporting contacts come from the database, never the model." | Scam card first; DHS OIG and FTC in the list |
| 2:40 | S17 | "My language is not here" → type "Rohingya" | "The mock returns a pseudo-localized pack; with a key it is generated and cached." | Loading copy, then an RTL pack with `⟦rhg⟧` markers and the machine-translation banner |
| 2:55 | Browser | Show `/health` | "provider mock, keys_configured 0." | `{"provider":"mock","keys_configured":0,...}` |

If time allows:
- **Camera match.** Photograph the printed Medicaid page with the phone and read it. The mock
  computes a 16×16 difference hash of the photo and matches it to the sample (Hamming ≤ 10); the
  same result appears. A photo of anything else — a real letter, a blank page — gets "I can only
  read sample papers in this mode", never a made-up reading.
- **Offline.** Stop the API (or airplane mode): the sample list and every recorded result still
  open from the app bundle (`assets/fixtures/`, generated by `sync_to_mobile.py`).
- **Another language.** Switch to Vietnamese and open the W-2: every sentence carries `⟦vi⟧`,
  quotes and numbers stay exactly as printed.
- **Chat.** Ask "When is it due?" — the mock quotes the date line from the paper; ask "Will I
  win?" on the court notice — it refuses and points to a lawyer or accredited representative.

## 3. With keys (`AI_PROVIDER=gemini`, billed slots, `ENV=staging`)

Follow PRODUCT_SPEC §13.2 unchanged, with one rule: the only paper photographed is the printed
SAMPLE sheet above. Samples chosen from the picker send `demo_sample_id`; on Gemini the server
reads the fixture PNG from disk, so no user bytes are involved. If the network fails, point the
app at the mock instance and continue with §2.

## 4. Refreshing the samples (developers)

1. Edit `apps/api/data/fixtures/<id>/template.yaml` (page lines, per-language outputs).
2. `apps/api/.venv/bin/python apps/api/scripts/make_fixtures.py` — re-renders pages, transcript,
   manifest (dHash) and `out.<lang>.json`, and refuses a template whose quotes are not verbatim,
   whose contacts are not printed, or whose page hash is within 10 bits of another sample.
3. `apps/api/.venv/bin/python apps/api/scripts/sync_to_mobile.py` — rebuilds the mobile bundle.
4. `apps/api/.venv/bin/pytest apps/api -k "golden or demo or mock or phash"`.

Live recordings (`RECORD_FIXTURES=1`, `ENV=development`, `AI_PROVIDER=gemini`) are written by
`ai/recording.py` to `out.<lang>.json` for sample ids only; a reviewer folds them into the
template before commit (step 2 reports them as drift until then).
