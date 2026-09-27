# Research: resources

_Verified by a research agent on 2026-09-23 against official sources. Input to the ProxyHealth design; not a spec._

# ProxyHealth AI — Verified Resource Router Seed + Document Taxonomy (verified 2026-09-23)

**Verification method.** Every URL below was loaded today. "Verified" = fetched and relevant content read (WebFetch, headless browser pane, or curl with a browser User-Agent and page text grepped). "Likely" = HTTP 200 confirmed but page is JS-rendered/bot-protected so content was not machine-readable, or a specific number is sourced from an official page I could not load. "Unverified" = could not load (only travel.state.gov, behind a Cloudflare JS challenge). Many .gov sites (medicaid.gov, cdc.gov, ed.gov, hhs.gov, ssa.gov, acf.gov, fna.usda.gov, ecfr.gov, dol.gov, parts of justice.gov) return **403 to plain fetchers** — see Warnings.

---

## 1. NATIONAL RESOURCE DIRECTORIES

### 1A. Free / low-cost immigration legal help
| Resource | URL (verified) | What it does | Who qualifies | Languages | Prepare |
|---|---|---|---|---|---|
| ImmigrationLawHelp.org (Justicia Lab / probono.net; formerly Immigration Advocates Network) | https://www.immigrationlawhelp.org/ | Directory of nonprofit immigration legal providers; search by state/county, ZIP, or detention facility; filter by case type (asylum, DACA, TPS, VAWA, etc.) | Low-income immigrants | 13 languages incl. Spanish, Vietnamese, Chinese, Arabic, Haitian Creole | Any USCIS/court notices, A-number, income info |
| DOJ EOIR List of Pro Bono Legal Service Providers | https://www.justice.gov/eoir/list-pro-bono-legal-service-providers | Providers committing ≥50 hrs/yr pro bono before each immigration court; updated quarterly (Jan/Apr/Jul/Oct); organized by court location | People in removal proceedings (some providers detained-only) | Varies | NTA / hearing notice; A-number. EOIR does not endorse providers |
| DOJ Recognized Organizations & Accredited Representatives roster | https://www.justice.gov/eoir/recognition-accreditation-roster-reports | PDFs: Recognized Organizations, Accredited Representatives, state-by-state list — the way to confirm a non-lawyer is legally allowed to help | Anyone checking a provider | EN | Name of org/rep to look up |
| USCIS "Find Legal Services" | https://www.uscis.gov/scams-fraud-and-misconduct/avoid-scams/find-legal-services | Explains the only 4 categories who may represent you (US attorneys in good standing, DOJ-accredited reps, supervised law students, foreign attorneys outside US); "notary publics are not attorneys" | All | EN/ES | — |
| AILA Immigration Lawyer Search | https://www.ailalawyer.com/ | Private (paid) attorneys; filters by practice area, location, 100+ languages | Anyone (fee-based) | 100+ language filter | — |
| USCIS Contact Center | https://www.uscis.gov/contactcenter | 800-375-5283, TTY 800-767-1833; Mon–Fri 8am–8pm ET; case status online | All | EN/ES | Receipt number |
| EOIR Immigration Court Online Resource (ICOR) | https://www.justice.gov/eoir/immigration-court-online-resource | Plain-language guides to removal proceedings (NTA, hearings, representation) | People in court | EN (+ other languages inside) | — |
| EOIR Automated Case Information (ACIS) | https://acis.eoir.justice.gov/en/ | Enter A-number → next hearing date/time/court, judge decision, BIA status | People in court | EN/ES | A-number |
| EOIR Case Information Hotline | https://www.justice.gov/eoir/customer-service-initiatives | 1-800-898-7180, 24/7, EN/ES; next hearing, decision, BIA appeal/brief due dates | People in court | EN/ES | A-number (enter 9 digits, pad 8-digit with 0) |
| EOIR court finder + WebEx hearing links | https://www.justice.gov/eoir/find-immigration-court-and-access-internet-based-hearings | Court addresses; internet-based hearing links per judge | — | EN | Hearing notice |
| EOIR forms (EOIR-33/IC, -26, -26A, -28) | https://www.justice.gov/eoir/eoir-forms | EOIR-33/IC change of address (filable online via Respondent Access); EOIR-26 appeal ($1,030 fee) ; EOIR-26A fee waiver; multiple language versions | — | Multi | — |
| Board of Immigration Appeals | https://www.justice.gov/eoir/board-of-immigration-appeals | Appeals body; 30-calendar-day receipt deadline for EOIR-26 (deadline sourced from BIA Practice Manual §4.4 via search; page itself blocked) | — | EN | — |

### 1B. General civil legal aid
- **LawHelp.org** (Pro Bono Net) — https://www.lawhelp.org/ — state-by-state legal aid finder + self-help guides; immigration and housing topics.
- **LSC "Find Legal Aid"** — https://www.lsc.gov/about-lsc/what-legal-aid/get-legal-help — map of 129 LSC-funded programs. **Critical limit:** 45 CFR Part 1626 (verified: https://www.ecfr.gov/current/title-45/subtitle-B/chapter-XVI/part-1626) restricts LSC grantees to citizens and "eligible aliens" (LPRs, refugees, asylees, conditional entrants, withholding, certain H-2A/H-2B matters) plus VAWA/T/U/trafficking survivors — most undocumented users must be routed to 1A instead.
- **LSC Eviction Laws Database** — https://www.lsc.gov/initiatives/effect-state-local-laws-evictions/lsc-eviction-laws-database — state/territory + 30-locality dataset of notice periods, answer deadlines, post-judgment steps (use this instead of hardcoding eviction timelines).

### 1C. Health care
- **HRSA Find a Health Center (FQHCs)** — https://findahealthcenter.hrsa.gov/ — ZIP search; health centers serve regardless of insurance or immigration status with sliding-fee discounts (page is a JS app; title loaded).
- **HealthCare.gov** — https://www.healthcare.gov/ — 1-800-318-2596; "Find Local Help"; Spanish site; 16+ footer languages. Medicaid/CHIP year-round: https://www.healthcare.gov/medicaid-chip/ . Immigrant eligibility page https://www.healthcare.gov/immigrants/lawfully-present-immigrants/ (verified, but **not yet updated for H.R.1** — see Warnings).
- **Medicaid.gov state agency finder** — https://www.medicaid.gov/about-us/where-can-people-get-help-medicaid-chip — every state's Medicaid agency, phones, eligibility/enrollment links; also where to check renewal status. (The old `/renew-your-medicaid-or-chip-coverage` URL redirects here; adding `/index.html` returns 404.)
- **InsureKidsNow.gov** — https://www.insurekidsnow.gov/ — children's Medicaid/CHIP by state; 1-877-KIDS-NOW (877-543-7669); EN/ES.
- **Hospital financial assistance (IRS §501(r)(4))** — https://www.irs.gov/charities-non-profits/financial-assistance-policy-and-emergency-medical-care-policy-section-501r4 — nonprofit hospitals must have a written FAP, plain-language summary, application process, and translations for LEP groups ≥1,000 people or 5% of service area. **Dollar For** — https://dollarfor.org/ — free help screening/applying for charity care.
- **No Surprises Act / Medical Bill Rights** — https://www.cms.gov/initiatives/your-patient-rights/medical-bill-rights (also https://www.cms.gov/nosurprises) — out-of-network emergency protections; Good Faith Estimate for uninsured/self-pay; dispute if bill ≥$400 over estimate within 120 days; Help Desk 1-800-985-3059 in 350+ languages.
- **Insurance appeals** — internal: https://www.healthcare.gov/appeal-insurance-company-decision/internal-appeals/ (file within 180 days; insurer decides 30 days pre-service / 60 days post-service / 72 hours urgent); external review: https://www.healthcare.gov/appeal-insurance-company-decision/external-review/ (request within 4 months of final internal denial; decision 45 days, expedited 72 hours; state or HHS-run).
- **Medicare appeals** — overview https://www.medicare.gov/providers-services/claims-appeals-complaints/appeals (5 levels); Original Medicare https://www.medicare.gov/providers-services/claims-appeals-complaints/appeals/original-medicare (file by date on MSN; MAC decides ~60 days); Medicare Advantage https://www.medicare.gov/providers-services/claims-appeals-complaints/appeals/medicare-health-plans (**65 days**, expedited 72 h); Part D https://www.medicare.gov/providers-services/claims-appeals-complaints/appeals/drug-plans (65 days, 72 h).
- **Medicaid fair hearing** — 42 CFR 431.221(d): state must allow up to 90 days from notice mailing to request a hearing — https://www.ecfr.gov/current/title-42/section-431.221
- **Rx help** — NeedyMeds https://www.needymeds.org/ (HTTP 200, JS-rendered), GoodRx https://www.goodrx.com/ (HTTP 200, blocks bots), PhRMA's Medicine Assistance Tool now **AmericasMedicines.com** https://americasmedicines.com/ (mat.org and medicineassistancetool.org redirect/dead; TLS chain error in fetcher, curl 200).
- **Lab results explainer** — https://medlineplus.gov/lab-tests/how-to-understand-your-lab-results/
- **Vaccine records** — CDC state IIS registry contacts https://www.cdc.gov/iis/contacts-locate-records/index.html ; school requirements by state https://www.cdc.gov/vaccines/php/requirements-laws/state-vaccination-requirements.html ; Immunize.org state requirement/exemption tables https://www.immunize.org/official-guidance/state-policies/
- **Language access in health care** — HHS OCR LEP page https://www.hhs.gov/civil-rights/for-individuals/special-topics/limited-english-proficiency/index.html — right to interpreter/translation in HHS-funded programs (pharmacy, ER, nursing home, insurance application); OCR complaint process.

### 1D. Food
- **Feeding America food bank locator** — https://www.feedingamerica.org/find-your-local-foodbank — ZIP/state; "anyone who needs extra help" — no ID requirement stated; Spanish site.
- **SNAP state directory** — https://www.fna.usda.gov/snap/state-directory (USDA FNS renamed **Food and Nutrition Administration**, fna.usda.gov, June 1 2026; fns URLs redirect). SNAP eligibility/interview: https://www.fna.usda.gov/snap/recipient/eligibility — 30-day processing, interview (phone/in-person), expedited 7 days; undocumented never eligible; qualified non-citizens generally 5-year rule with exceptions.
- **WIC** — https://www.fna.usda.gov/wic ; eligibility https://www.fna.usda.gov/wic/eligibility (pregnant/postpartum/breastfeeding, infants, kids <5; income ≤ WIC limits or adjunctive via Medicaid/SNAP/TANF; **no immigration-status requirement**); **SignUpWIC.com** https://signupwic.com/ (National WIC Association; find clinic; EN/ES).
- **School meals (households)** — https://www.fna.usda.gov/nslp/household — apply through the child's school/district; income guidelines https://www.fna.usda.gov/schoolmeals/income-eligibility-guidelines

### 1E. Housing / eviction / utilities
- **HUD-approved housing counselors** — https://www.hud.gov/findacounselor — free/low-cost rental, eviction-prevention, foreclosure counseling; hotline 800-569-4287 (number confirmed on CFPB page https://www.consumerfinance.gov/coronavirus/mortgage-and-housing-assistance/renter-protections/).
- **Public Housing Agency contacts (Section 8/HCV)** — https://www.hud.gov/program_offices/public_indian_housing/pha/contacts ; HCV program https://www.hud.gov/topics/housing_choice_voucher_program_section_8
- **USA.gov housing help** — https://www.usa.gov/housing-help (eviction/foreclosure, rental assistance, emergency housing) (`/eviction` is 404).
- **211** — https://www.211.org/ — dial 211; food, rent/utility help, health, mental health, disaster; EN/ES; confidential.
- **LIHEAP (utility shutoff)** — https://acf.gov/ocs/programs/liheap — heating/cooling bills, shutoff prevention/reconnection; referral line 1-866-674-6327; local office search https://liheapch.acf.gov/search-tool

### 1F. Benefits navigation
- **USA.gov Benefit Finder** — https://www.usa.gov/benefit-finder — 12-category questionnaire; **Benefits.gov now redirects here** (redirect confirmed).
- 211 (above).

### 1G. Crisis lines
- **988 Suicide & Crisis Lifeline** — https://988lifeline.org/ — call/text 988, chat; Spanish; 240+ languages via interpretation; ASL; 24/7 free confidential.
- **National Domestic Violence Hotline** — https://www.thehotline.org/ — 1-800-799-7233; text START to 88788; chat; Spanish + 200+ languages; 24/7.
- **Poison Control** — https://www.poison.org/ — 1-800-222-1222; webPOISONCONTROL online tool; free, expert, confidential (24/7 not stated on home page).
- **National Human Trafficking Hotline** — https://humantraffickinghotline.org/ — 1-888-373-7888; text 233733; 24/7.

### 1H. Interpreters / language-access rights
- **Title VI** (DOJ) — https://www.justice.gov/crt/fcs/TitleVI — bars national-origin discrimination by federally funded programs; page notes **EO 13166 rescinded** and guidance under review; complaints via civilrights.justice.gov.
- **DOJ LEP page** — https://www.justice.gov/crt/limited-english-proficiency — **LEP.gov is suspended** "pending internal review" to implement EO 14224 (English as official language); lep.gov redirects here.
- **HHS OCR LEP** (above, 1C) — still states right to language assistance in HHS-funded programs. CMS No Surprises Help Desk 350+ languages.

### 1I. Anti-fraud
- **USCIS Common Scams** — https://www.uscis.gov/scams-fraud-and-misconduct/avoid-scams/common-scams — notario/unauthorized practitioners, government impersonators, phishing, job-offer, DV lottery, "pay to jump the line"; USCIS never asks you to transfer money to an individual; only official myUSCIS/.gov payment; never Western Union/MoneyGram/PayPal/Venmo/gift cards; emails come from .gov. Parent page https://www.uscis.gov/scams-fraud-misconduct (old `/avoid-scams` parent URL is 404). USCIS forms are always free: https://www.uscis.gov/forms/all-forms
- **FTC Scams Against Immigrants hub** — https://consumer.ftc.gov/features/scams-against-immigrants (12 languages; phone 877-382-4357) and article https://consumer.ftc.gov/articles/how-avoid-immigration-scams-and-get-real-help ; report at https://reportfraud.ftc.gov/ (Spanish: ReporteFraude.ftc.gov). Gift-card rule: https://consumer.ftc.gov/articles/avoiding-and-reporting-gift-card-scams ; job scams: https://consumer.ftc.gov/articles/job-scams
- **DHS OIG Hotline** (ICE/USCIS impersonation) — https://www.oig.dhs.gov/hotline — 1-800-323-8603. ICE ERO official page/tip line 1-866-DHS-2-ICE: https://www.ice.gov/ero
- **IRS scams** — https://www.irs.gov/help/tax-scams/recognize-tax-scams-and-fraud ; **SSA scams** — https://www.ssa.gov/scam/ (four signs; SSA never demands gift cards/crypto or threatens arrest).

### 1J. Refugee-specific
- **ORR** — https://acf.gov/orr ; **Key State Contacts (State Refugee Coordinators + Refugee Health Coordinators)** — https://acf.gov/orr/programs-services/refugees/contacts/state-contacts (the old `/orr/map/find-resources-and-contacts-your-state` is 404).
- National resettlement agencies (all verified live): IRC https://www.rescue.org/ (25+ US cities); USCRI https://refugees.org/ ; HIAS https://hias.org/ ; Global Refuge (ex-LIRS) https://www.globalrefuge.org/ (410-983-4000); Church World Service https://cwsglobal.org/ (1-800-297-1516; office map at /our-work/united-states/map-of-cws-offices/); World Relief https://worldrelief.org/ (worldrelief.org/us-locations/); ECDC https://www.ecdcus.org/ . Coalition: Refugee Council USA https://rcusa.org/ . ORR TA hub Switchboard https://www.switchboardta.org/ (newcomer info "SettleIn" in 10+ languages). USCIS USRAP page https://www.uscis.gov/humanitarian/refugees-and-asylum/usrap

### 1K. Afghan-specific
- **USCIS Information for Afghan Nationals** — https://www.uscis.gov/humanitarian/information-for-afghan-nationals — parole/re-parole, expedited asylum (interview within 45 days, decision 150 days), SIV adjustment, EAD.
- **ORR Benefits for Afghan Humanitarian Parolees** — https://acf.gov/orr/fact-sheet/benefits-afghan-humanitarian-parolees — cash/medical assistance, RSS employment services up to 5 years, Matching Grant. (APA program page is archived: acf.gov/archive/…)
- **#AfghanEvac** — https://afghanevac.org/ — coalition; Battle Buddies volunteer program; pipeline tracking.
- State Dept Afghan SIV page — https://travel.state.gov/content/travel/en/us-visas/immigrate/special-immg-visa-afghans-employed-us-gov.html — **UNVERIFIED** (Cloudflare challenge blocked every method).

### 1L. Asylum
- **ASAP (Asylum Seeker Advocacy Project)** — https://asaptogether.org/en/ (asylumadvocacy.org redirects) — free membership; work-permit, court, fee guides in EN/ES/Haitian Creole/Russian/Mandarin. Annual Asylum Fee explainer https://asaptogether.org/en/new-fees/
- **USCIS Asylum** — https://www.uscis.gov/humanitarian/refugees-and-asylum/asylum ; affirmative process https://www.uscis.gov/humanitarian/refugees-and-asylum/asylum/the-affirmative-asylum-process ; Form I-589 https://www.uscis.gov/i-589 ; **H.R.1 fees alert** https://www.uscis.gov/newsroom/alerts/uscis-updates-fees-based-on-hr-1
- Clinic directories: use ImmigrationLawHelp.org (filter: asylum) + EOIR pro bono list.

### 1M. Workers' rights (regardless of status)
- **DOL Wage & Hour complaints** — https://www.dol.gov/agencies/whd/contact/complaints — 1-866-487-9243; free; confidential; status not a barrier; gather pay stubs/hours/employer info. (WHD immigration page https://www.dol.gov/agencies/whd/immigration lists visa programs only.)
- **EEOC** — https://www.eeoc.gov/employees-job-applicants (1-800-669-4000; 11+ languages); filing deadlines 180 days / 300 days https://www.eeoc.gov/how-file-charge-employment-discrimination ; national origin/accent/English-only https://www.eeoc.gov/national-origin-discrimination
- **OSHA** — https://www.osha.gov/workers — 1-800-321-OSHA; confidential complaint; retaliation complaint within 30 days; file https://www.osha.gov/workers/file-complaint

### 1N. School
- **McKinney-Vento / NCHE** — https://nche.ed.gov/ and https://nche.ed.gov/mckinney-vento/ — immediate enrollment without records/immunizations/residency proof; local liaison in every district; school of origin + transport; dispute process. **Find your liaison/state coordinator:** https://schoolhouseconnection.org/homeless-education-directory
- **Plyler v. Doe** — https://www.americanimmigrationcouncil.org/fact-sheet/plyler-v-doe-public-education-noncitizen-students/ — all children may enroll K-12 regardless of status; schools may not ask status or require SSNs; notes 2025-26 state bills challenging it. (ED/DOJ fact-sheet PDFs on ed.gov are 403/404.)
- **Free/reduced meals** — https://www.fna.usda.gov/nslp/household (apply via school).
- **IDEA / IEP** — https://sites.ed.gov/idea/ ; IEP overview https://www.parentcenterhub.org/iep-overview/ (IEP meeting within 30 days of eligibility; annual review); **free Parent Training & Information Centers by state** https://www.parentcenterhub.org/find-your-center/ ; **Section 504 parent guide (OCR)** https://www.parentcenterhub.org/ocr-guide-to-section504/
- Immunization requirements: CDC + Immunize.org (1C).

---

## 2. NORTHERN VIRGINIA / DC-METRO EXEMPLAR SET (all verified)
| Org | URL | Key facts |
|---|---|---|
| Inova Financial Assistance | https://www.inova.org/patient-and-visitor-information/financial-assistance | Uninsured with income ≤400% FPL → 100% discount (tiers above); must live in Inova service area (VA residency proof); apply via MyChart, mail (8095 Innovation Park Dr, Fairfax VA 22031) or in person (Fairfax/Annandale/Herndon, M–F 8:30–3); docs: income + residency; **571-472-5880** M–F 8–4:30; plain-language summary in EN/ES/Amharic/Arabic/Dari/Farsi/Korean/Mandarin/Urdu/Vietnamese |
| Fairfax County Community Health Care Network (CHCN) | https://www.fairfaxcounty.gov/health/community-health-care-network | Primary care for uninsured residents of Fairfax County/Fairfax City/Falls Church, income ≤200% FPL, no other primary-care access, 9 months residency proof; **currently a waitlist**; apply in person: Merrifield 703-237-3446, North County/Reston 703-689-2180, South County/Alexandria 703-704-5333; docs: pay stubs, employer insurance verification, unearned income, tax return, ID for household, residency |
| Neighborhood Health (FQHC) | https://www.neighborhoodhealthva.org/ | Alexandria/Arlington/Fairfax; family medicine, peds, OB/GYN, dental, behavioral health, pharmacy, HIV; sliding fee; **703-535-5568** |
| Legal Aid Justice Center | https://www.justice4all.org/ | Immigrant advocacy, housing, workers' rights; offices Falls Church (NoVA), Charlottesville, Richmond, Petersburg; EN/ES; "Get Help" portal |
| Ayuda | https://www.ayuda.com/ | Immigration + family/DV legal, social services, language access for low-income immigrants in DC/MD/VA; DC 202-387-4848, Fairfax 703-444-7009, Silver Spring 240-594-0600 |
| Just Neighbors | https://www.justneighbors.org/ | Immigration legal services (family, DACA/TPS, DV protections) for low-income immigrants in DC/MD/VA; 703-979-1240 / 703-991-4576; info@justneighbors.org |
| Tahirih Justice Center | https://www.tahirih.org/ | Free legal + social services for immigrant survivors of gender-based violence; Falls Church, Baltimore, Atlanta, Houston, SF Bay Area; **866-575-0071** |
| Capital Area Food Bank | https://www.capitalareafoodbank.org/find-food-assistance/ | Address-search map of partner pantries in DC/MD/NoVA; Hunger Lifeline **202-644-9807**; Spanish help section; no ID requirement stated |
| Northern Virginia Family Service | https://www.nvfs.org/ · https://www.nvfs.org/find-support | Immigration legal, community health access, housing/food (Hunger Resource Center), workforce, mental health; **571-748-2500**; info@nvfs.org; ES/Arabic/French/Amharic/Vietnamese |
| Fairfax County Coordinated Services Planning (CSP) | https://www.fairfaxcounty.gov/neighborhood-community-services/coordinated-services-planning | Single point of entry for rent/utility/food/medical emergency help and county program enrollment; **703-222-0880**, TTY 711, M–F 8–4:30; 15+ languages |
| Virginia eviction exemplar | https://selfhelp.vacourts.gov/page/10/landlord-tenant · https://law.lis.virginia.gov/vacode/title55.1/chapter12/section55.1-1245/ · https://www.fairfaxcounty.gov/sheriff/eviction-process · https://fightmyeviction.org/ | Unlawful detainer cases in General District Court; nonpayment notice now **14 days** (§55.1-1245(F)); other breaches 30-day notice / 21 days to cure; after judgment 10-day appeal, writ, Sheriff gives ≥72 h notice; VA Eviction Legal Helpline 1-833-NOEVICT (number from search; site verified) |

---

## 3. DOCUMENT-TYPE TAXONOMY (fields to extract → action/deadline → pitfalls)

### 3A. USCIS notices (Form I-797 family — https://www.uscis.gov/forms/filing-guidance/form-i-797-types-and-functions)
- **I-797C Receipt Notice** — fields: receipt # (3 letters+10 digits), form type, received/priority/notice dates, applicant & beneficiary, A-number, office. Action: keep; track at Case Status. No deadline. Pitfalls: for **I-90** the receipt extends green-card validity **36 months** (https://www.uscis.gov/green-card/after-we-grant-your-green-card/replace-your-green-card); for **I-765 renewals filed on/after Oct 30 2025 the receipt is NOT work authorization** (auto-extension ended: https://www.uscis.gov/newsroom/news-releases/dhs-ends-automatic-extension-of-employment-authorization). I-797C is also used for rejections and transfers — read the first line.
- **I-797 / I-797A / I-797B Approval** — fields: classification, validity dates, I-94 (797A). Action: card follows (I-797D accompanies cards). Pitfall: approval ≠ card in hand; check validity dates.
- **I-797E Request for Evidence (RFE)** — fields: response due date, itemized evidence list, mailing address, "return this notice on top". Deadline: USCIS may give up to **84 days (+3 for mail = 87)**, **no extensions**; non-response → denial as abandoned or on the record (https://www.uscis.gov/policy-manual/volume-1-part-e-chapter-6). Pitfall: must be *received* by the date; send everything in one package.
- **Notice of Intent to Deny (NOID)** — same fields; **30 days (+3 mail)**, no extension; more serious than RFE. Get counsel.
- **ASC Biometrics appointment (I-797C)** — fields: date/time/location, code. Bring notice + photo ID; reschedule via online account *before* the time; missing without good cause → request may be treated as abandoned (https://www.uscis.gov/forms/filing-guidance/preparing-for-your-biometric-services-appointment).
- **Interview notice (I-797C)** — fields: date/time/office, documents checklist, interpreter rules. Asylum interviews: bring family members and (if needed) your own interpreter; evidence due **14 days before** interview and rescheduling requires exceptional circumstances (rules effective Aug 21 2026 per USCIS asylum page); no-show can lead to dismissal/referral. Naturalization interview: bring notice, green card, IDs, passports; English test + civics (N-400 filed ≥ Oct 20 2025 → 2025 test, 20 Qs, pass 12; before → 2008 test, 10 Qs, pass 6); 2 attempts, retest 60–90 days (https://www.uscis.gov/citizenship/learn-about-citizenship/the-naturalization-interview-and-test); oath notice = N-445.
- **Change of address** — all noncitizens must report within **10 days** (AR-11/online; USPS forwarding does NOT update USCIS: https://www.uscis.gov/addresschange). Court cases need a *separate* EOIR-33/IC (Respondent Access); practice manual says within 5 working days (likely).

### 3B. Immigration court / ICE
- **Notice to Appear (I-862)** — fields: A-number, allegations/charges, hearing date/time/court ("to be set" is common), DHS attorney. Action: verify hearing via ACIS/1-800-898-7180; find counsel (EOIR pro bono list); file EOIR-33 on any move. Pitfall: missing a hearing → in-absentia removal order.
- **Hearing Notice** — master vs individual (merits) hearing; WebEx link; pitfall: notices come only by mail to the address on file.
- **EOIR-33** change of address (court) — file with the specific court + BIA version if on appeal; also update ICE and USCIS separately.
- **IJ decision / BIA** — EOIR-26 must be **received within 30 calendar days**; fee $1,030 or EOIR-26A waiver; BIA briefing schedule dates on the notice; hotline gives brief due dates.
- **ICE check-in / release paperwork (Order of Recognizance/Supervision, ATD)** — fields: Subject ID, birthplace, report date, field office. Schedule at https://www.ice.gov/check-in (checkin.ice.gov / ICE Portal); making an online appointment satisfies release terms even if later than the paper date; missing = violation of release conditions.
- **EAD (I-765) renewal** — file up to **180 days** before expiration (https://www.uscis.gov/i-765); no automatic extension for renewals filed on/after Oct 30 2025 (TPS Federal Register extensions excepted); H.R.1 fees for asylum/parole/TPS categories $550 initial / $275 renewal, not waivable.
- **Green card renewal** — I-90 when expired or expiring within **6 months**; receipt extends 36 months; **2-year conditional cards cannot be renewed** — file I-751/I-829 in the 90 days before expiry (https://www.uscis.gov/green-card/after-we-grant-your-green-card).
- **TPS re-registration** — windows set per country in Federal Register notices; I-821 (+ I-765); missing the window → loss of TPS and work authorization; several 2025–26 terminations under litigation; TPS fee up to $500 under H.R.1 (https://www.uscis.gov/humanitarian/temporary-protected-status).
- **Parole / re-parole (Afghan, others)** — check USCIS Afghan page; H.R.1 parole fee ~$1,000 (likely; alert notes lower re-parole rate).
- **Annual Asylum Fee notice** — $100 (indexed; ASAP shows $102) per year pending after Oct 1 2024; **30 days to pay** after notice; non-payment → rejection/EAD cancellation/removal referral; **no waiver**; ASAP warns notices sometimes never arrive → prompt users with I-589 pending >1 year to check.

### 3C. Medical documents
- **Itemized bill vs. summary statement** — fields: account #, dates of service, CPT/HCPCS codes, charges, insurance adjustments, patient balance, due date, financial-assistance notice. Action: request itemized bill; reconcile with EOB; ask for FAP/charity care *before paying* (501(r) hospitals must screen; many honor applications after billing); No Surprises Act protections; Good-Faith-Estimate dispute (≥$400 over, within 120 days). Pitfall: a "statement" may be pre-insurance; "final notice" language pressure.
- **Explanation of Benefits (EOB)** — "THIS IS NOT A BILL"; fields: claim #, billed, allowed, plan paid, deductible/coinsurance, patient responsibility, remark/denial codes, appeal rights & deadline (https://www.healthinsurance.org/glossary/explanation-of-benefits/). Action: compare to provider bill; if denied, start clock.
- **Insurance denial letter** — fields: denial reason/code, service, appeal deadline, internal vs external review instructions, urgent-care option. Deadlines: ACA/employer plans — internal appeal within **180 days**; insurer decides 30/60 days (72 h urgent); external review within **4 months** of final internal denial (45 days / 72 h). Medicaid — fair hearing request window ≤ **90 days** from notice (state sets exact); Medicare Original — by date on MSN (120 days, likely); MA/Part D — **65 days**. Pitfall: "final adverse determination" triggers the external-review clock; keep call logs.
- **Prior-authorization letter** — fields: approved/denied, service/drug, units, valid dates, auth #. Pitfall: approval is not a payment guarantee; auths expire; denial → appeal as above (https://www.healthcare.gov/glossary/prior-authorization/).
- **Lab results** — fields: test, value, units, reference range, H/L flags, collection date. Pitfall: out-of-range ≠ disease and in-range ≠ healthy; portal may show results before clinician review; discuss with provider (MedlinePlus).
- **Prescription label** — fields: patient, drug/strength, sig (directions), quantity, refills, prescriber, Rx #, fill/discard dates, pharmacy phone, warnings. Pitfalls: "as directed" ambiguity, teaspoon vs mL, brand vs generic naming, 0 refills → call prescriber; ask pharmacy for interpreter/translated label (HHS LEP rights).
- **Discharge instructions** — fields: diagnosis, new/changed/stopped meds, follow-up appointments, warning signs / when to call 911, activity/diet limits, who to call. Ask for interpreter + translated copy.
- **Vaccine records** — school entry requires state-specific vaccines; obtain from state IIS registry; McKinney-Vento students enroll immediately anyway; catch-up schedules available at health centers.

### 3D. Benefits documents
- **Medicaid renewal / redetermination packet** — fields: due date, requested proofs (income, residency, household, immigration docs), how to return (online/mail/phone). Action: return by due date; contact state agency (medicaid.gov state page); if terminated for paperwork, ask about reconsideration/reinstatement. Pitfall: H.R.1 restricts federal Medicaid/CHIP eligibility for many lawfully present immigrants from **Oct 1 2026** and adds more frequent redeterminations (likely) — expect more notices.
- **SNAP interview notice** — interview (phone/in-person) required within the 30-day processing window; expedited 7 days; missing the interview → denial; verification list (ID, income, rent, utilities). Non-citizen eligibility rules apply per household member; ineligible parents can still apply for eligible children.
- **WIC appointment / packet** — bring ID, proof of residency, proof of income (or Medicaid/SNAP/TANF card), the child; no immigration-status question.
- **SSA letters** (award, denial, overpayment, SSI redetermination, benefit verification) — appeal levels: reconsideration → ALJ hearing → Appeals Council → federal court (https://www.ssa.gov/apply/appeal-decision-we-made); appeal within 60 days of receipt (likely); pitfall: SSA does not threaten arrest or demand gift cards — scam letters/calls common.

### 3E. Housing documents
- **Pay-or-quit / notice to cure** — fields: amount owed, days to pay/cure, landlord contact, date served. It is *not* an eviction; only a court can evict. Periods vary by state (LSC database) — Virginia: **14 days** nonpayment; 30-day termination / 21-day cure for other breaches.
- **Eviction summons / unlawful detainer** — fields: court, return/hearing date, case #, plaintiff. **Appear on the date or lose by default**; answer periods vary by state; after judgment (VA) 10-day appeal → writ → Sheriff ≥72 h notice. Route to legal aid immediately (LawHelp, LAJC, 1-833-NOEVICT in VA).
- **Lease** — term, rent/due date/late fee, notice periods, auto-renewal, deposit, occupancy rules.
- **Rent increase notice** — check lease + state notice period (often 30–60 days; not verified per state).
- **Section 8 / HCV recertification** — annual reexamination; report income/household changes; missed paperwork → termination; contact PHA (HUD PHA contacts).

### 3F. School documents
- **Enrollment forms** — schools may not ask immigration status or require SSNs (Plyler); residency proof required but McKinney-Vento allows immediate enrollment without it; birth-certificate alternatives accepted.
- **Immunization requirement notices** — state-specific list and provisional-enrollment deadlines; exemptions vary (CDC/Immunize.org pages).
- **IEP / 504 meeting notices** — parent must be invited; right to interpreter/translated safeguards; IEP meeting within 30 days of eligibility; annual review; 504 = accommodations under civil-rights law vs IEP = specialized instruction under IDEA; free PTI centers help prepare.
- **Report cards / progress reports** — no deadline; request conference/interpreter.
- **Free/reduced-price meal application** — via school; direct certification if on SNAP/Medicaid.

### 3G. Employment documents
- **W-2 / 1099-NEC** — issued by Jan 31; fields: EIN, wages, withholding; 1099 = contractor (self-employment tax); ITIN filers can still file. (https://www.irs.gov/forms-pubs/about-form-w-2, https://www.irs.gov/forms-pubs/about-form-1099-nec)
- **I-9** — employer form; re-verification when EAD expires; employers may no longer accept I-797C alone for renewals filed on/after Oct 30 2025 (https://www.uscis.gov/i-9-central).
- **Offer letters** — wage, schedule, at-will, start date; pitfall: fake job offers demanding fees/personal data.
- **Wage theft** — pay stubs, hours log → WHD 1-866-487-9243 or state labor agency; EEOC 180/300 days; OSHA retaliation 30 days.

### 3H. Tax documents
- **IRS notices (CP/LTR)** — number in top-right; look up at https://www.irs.gov/individuals/understanding-your-irs-notice-or-letter ; respond by the date; if not found in lookup call 800-829-1040; IRS contacts by mail first, never gift cards/threats of deportation.
- **ITIN (Form W-7)** — https://www.irs.gov/individuals/individual-taxpayer-identification-number ; passport or two ID docs; Certifying Acceptance Agents; ITINs expire if unused; ~7 weeks (9–11 in peak).

### 3I. Other notices
- **Utility shutoff notice** — fields: shutoff date, amount, payment-plan option, medical-certificate protections (state). Action: call utility, LIHEAP crisis funds (1-866-674-6327), 211, CSP (Fairfax).
- **Jury summons** — federal (and generally state) jurors must be **US citizens** (https://www.uscourts.gov/court-programs/jury-service/juror-qualifications-exemptions-and-excuses). Non-citizens must **return the qualification form marking non-citizen** — never ignore it and **never check "citizen"** (false claim to citizenship has severe immigration consequences).
- **Traffic / court notices** — appear or pay by the date; failure to appear → license suspension/warrant; anything criminal (including some misdemeanors/DUI) can affect immigration status — consult immigration counsel before pleading. State-specific; no single verified national URL.

---

## 4. SCAM / RED-FLAG PATTERNS (official sources)
1. **Notario / unauthorized practitioner** — "notario público" is not a lawyer in the US; only attorneys and DOJ-accredited reps may give legal advice (USCIS common scams; FTC how-to-avoid; DOJ roster to verify).
2. **Fake ICE/USCIS/SSA/IRS calls or texts demanding payment** (gift cards, wire, crypto, Venmo, "immigration payment" to avoid arrest/deportation; spoofed .gov numbers, real officer names) — no agency demands phone payment; USCIS pays only via .gov account; hang up, verify via official numbers; report DHS OIG 1-800-323-8603, SSA OIG, FTC.
3. **"Guaranteed" visa/green card, "pay to jump the line", special government connections** — no one can guarantee or speed outcomes (USCIS).
4. **Fake job offers / visa-sponsorship jobs** requiring fees, check deposits, or personal data up front (FTC job scams; USCIS).
5. **Charging for free USCIS forms / fake ".com" USCIS look-alike sites** — forms and online accounts are always free; real sites/emails end in .gov (USCIS all-forms; FTC).
6. **Diversity Visa lottery scams** — no fee to enter; only dvprogram.state.gov; no email "you won" notices (FTC).
7. **Fake sponsor/I-134A or "supporter" offers** and student-targeted scams (USCIS common scams).
8. **Fake call transfers to SSA/OIG** (SSA July 29 2026 alert), fake SSA social accounts (ssa.gov/scam).
9. **Payment red flags** — any request for gift card, wire, crypto, or payment app = scam (FTC gift-card rule).
10. **Where to report** — ReportFraud.ftc.gov / ReporteFraude.ftc.gov; state attorney general; DHS OIG; state bar for lawyer misconduct; DHS Disciplinary Counsel (USCIS find-legal-services).

## Warnings for builders

- BOT PROTECTION: medicaid.gov, cdc.gov, ed.gov/sites.ed.gov, hhs.gov, ssa.gov, acf.gov (some pages), fns/fna.usda.gov, ecfr.gov, federalregister.gov, dol.gov (some), justice.gov (some EOIR reference-material pages) and insurekidsnow.gov return HTTP 403 to plain HTTP fetchers. The app's link-health checker must send a real browser User-Agent or use a headless browser, and must treat 403 as 'unknown', not 'dead'. travel.state.gov sits behind a Cloudflare JS challenge that blocked even the headless browser — its URLs cannot be auto-verified; store as 'manual-verify' and route Afghan SIV questions to the USCIS Afghan page instead.
- URL DRIFT — commonly cited URLs that are now 404 and were replaced in this list: uscis.gov/scams-fraud-and-misconduct/avoid-scams (parent), consumer.ftc.gov/articles/scams-against-immigrants, eeoc.gov/immigrants-employment-rights, acf.gov/orr/map/find-resources-and-contacts-your-state, usa.gov/eviction, healthcare.gov/glossary/explanation-of-benefits, ed.gov 504 FAQ, justice.gov/eoir/form-eoir-33-…, justice.gov/eoir/form-eoir-26-…, uscis.gov/citizenship/apply-for-citizenship/the-naturalization-interview-and-test, cdc.gov/vaccines-adults/…/vaccination-records.html, fns.usda.gov/wic/wic-how-apply, fns.usda.gov/school-meals/applying-…. Re-verify quarterly; government sites re-organized heavily in 2025–2026.
- medicaid.gov: the canonical state-help page is https://www.medicaid.gov/about-us/where-can-people-get-help-medicaid-chip — appending /index.html returns 404. The old 'renew your Medicaid or CHIP coverage' unwinding URL now redirects to this page.
- USDA FNS was renamed the Food and Nutrition Administration (FNA) on June 1 2026; fns.usda.gov redirects to fna.usda.gov. Store fna.usda.gov URLs and display 'USDA Food and Nutrition Administration (formerly FNS)'. Some legacy sub-paths do not redirect.
- LANGUAGE ACCESS IS IN FLUX: LEP.gov is suspended and redirects to a DOJ notice implementing EO 14224 (English as official language); EO 13166 was rescinded. Title VI itself still bars national-origin discrimination and the HHS OCR LEP page still describes the right to interpreters in HHS-funded settings — cite the statute + HHS OCR page, never lep.gov, and avoid promising interpreters in non-HHS federal programs without checking.
- EAD AUTO-EXTENSION IS OVER: for I-765 renewals filed on/after Oct 30 2025 there is no 180/540-day automatic extension (TPS Federal-Register extensions excepted) and the I-797C receipt is not work authorization. Any copy referencing the 540-day extension is stale. Advise filing up to 180 days before expiration and warn of a possible work gap.
- H.R.1 FEES (effective July 22 2025): $100 asylum filing fee, $100 Annual Asylum Fee (indexed; ASAP shows $102) with a 30-day payment window and no waiver; EAD $550/$275 for asylum/parole/TPS categories; TPS up to $500; EOIR-26 appeal fee $1,030. The USCIS asylum overview page still reads as if no fee applies — use the USCIS fee alert, not the overview, as the source of truth. ASAP reports fee notices sometimes never arrive: prompt any user with an I-589 pending >1 year to check.
- H.R.1 HEALTH COVERAGE: Marketplace subsidies end for <100% FPL lawfully present immigrants Jan 1 2026 and, from Jan 1 2027, only citizens/LPRs/Cuban-Haitian entrants/COFA migrants qualify; federal Medicaid/CHIP eligibility narrows Oct 1 2026; DACA ineligible since Aug 25 2025. HealthCare.gov's immigrant pages have NOT been updated. Do not tell refugees/asylees/TPS/parolees they qualify for 2027 subsidies; route to FQHCs, hospital FAP and state-funded programs.
- MEDICARE APPEAL WINDOWS CHANGED: Medicare Advantage and Part D plan appeals are now 65 days (not 60) per medicare.gov. Original Medicare's page says 'file by the date on your MSN' — the 120-day figure is standard but not printed there.
- LSC-FUNDED LEGAL AID (LawHelp/LSC finder results) generally cannot serve undocumented immigrants except VAWA/T/U/trafficking survivors (45 CFR 1626). Route undocumented users to ImmigrationLawHelp.org, the DOJ pro bono list and DOJ-accredited organizations instead, and say so in the UI to avoid wasted trips.
- EVICTION RULES ARE STATE- AND YEAR-SPECIFIC. Virginia moved from 5-day to 14-day pay-or-quit (Va. Code §55.1-1245) with more amendments effective July 1 2027 and 2028. Never hardcode notice/answer periods; pull from the LSC Eviction Laws Database and the state statute, and always tell users the court date on a summons is the deadline that matters.
- REFUGEE RESETTLEMENT CAPACITY IS UNSTABLE: FY2026 admissions ceiling is a historic-low 7,500 and USRAP was largely suspended in 2025; national agencies' local affiliate networks have shrunk and at least two former agencies (USCCB Migration & Refugee Services, Episcopal Migration Ministries) reportedly exited resettlement — not verified here. Verify a local affiliate is still operating before routing; use ORR Key State Contacts (State Refugee Coordinator) as the stable entry point.
- TPS: multiple designations were terminated or are in litigation in 2025–26 (page lists El Salvador, Lebanon, Sudan, Ukraine, Venezuela as designated; Ethiopia, Somalia, South Sudan, Burma, Yemen, Syria, Haiti terminated/litigated). Re-registration windows come only from Federal Register notices — never hardcode dates; link to the USCIS TPS country pages and refresh weekly.
- ASYLUM PROCEDURE CHANGES effective Aug 21 2026 (per USCIS asylum page): evidence must be submitted 14 days before the interview, rescheduling requires exceptional circumstances, and failure to appear can result in dismissal. Interview-notice explanations must surface these.
- IMPERSONATION SCAMS: USCIS/ICE/SSA/IRS never demand payment by phone, gift card, wire, crypto or payment app; USCIS payments only via .gov accounts. ICE does not phone people to warn of arrest. Report impersonation to DHS OIG 1-800-323-8603 and ReportFraud.ftc.gov. SSA flagged (July 29 2026) fake 'call transfers' to SSA/OIG as a new pattern.
- JURY SUMMONS: noncitizens must respond by marking non-citizen on the qualification form — ignoring it can bring fines, and falsely claiming citizenship (checking 'citizen', registering to vote) can permanently bar immigration benefits. Build this into the jury-summons explainer as a high-severity warning.
- CHANGE-OF-ADDRESS IS MULTI-AGENCY: USCIS (10 days, AR-11/online), the immigration court (EOIR-33/IC, separate; practice manual says 5 working days — not verified on a live page), the BIA (EOIR-33/BIA) and ICE each need their own update; USPS forwarding does not carry USCIS mail. Missing court mail leads to in-absentia removal orders.
- BIA 30-DAY APPEAL RULE could only be sourced via search of the BIA Practice Manual (§4.4) because that page returned 403/404; treat as likely and confirm before surfacing as a hard deadline.
- JS-RENDERED SITES (NeedyMeds, GoodRx, ReportFraud.ftc.gov, HRSA Find a Health Center, AmericasMedicines.com) returned HTTP 200 but their content could not be machine-read; descriptions come from general knowledge. AmericasMedicines.com also had a TLS-chain error in the fetcher (fine in curl).
- NoVA specifics that change: Fairfax CHCN currently has a waitlist and requires 9 months' residency proof; Inova FA requires Virginia service-area residency; CSP hours are Mon–Fri 8:00–4:30. Re-verify phone numbers and hours every 90 days.
- ImmigrationLawHelp.org is now branded as a Justicia Lab project (probono.net), not 'Immigration Advocates Network' — label accordingly to avoid confusing users who see the new branding.
- Poison Control's 24/7 availability and interpreter access are not stated on poison.org's home page (only 'free, expert, confidential'); state 24/7 as general knowledge, not as sourced.
- Some facts in the taxonomy (e.g., Medicaid 90-day post-termination reconsideration, SSA 60-day appeal + 5 mail days, FLSA 2/3-year statute of limitations, rent-increase notice periods) are standard practice but were not verified on a live page in this pass — mark them 'general guidance, confirm with counsel/agency' in the UI.

## Key facts

| Fact | Source | Confidence |
|---|---|---|
| ImmigrationLawHelp.org (Justicia Lab/probono.net) — directory of nonprofit immigration legal help searchable by state/county, ZIP or detention facility; 13 languages | https://www.immigrationlawhelp.org/ | verified |
| DOJ EOIR List of Pro Bono Legal Service Providers — organized by immigration court, updated quarterly (Jan/Apr/Jul/Oct); providers commit ≥50 pro bono hours/yr; EOIR does not endorse | https://www.justice.gov/eoir/list-pro-bono-legal-service-providers | verified |
| DOJ Recognized Organizations & Accredited Representatives roster (PDF lists incl. state-by-state) — use to verify a non-attorney is authorized | https://www.justice.gov/eoir/recognition-accreditation-roster-reports | verified |
| USCIS Find Legal Services — only US attorneys in good standing, DOJ-accredited reps, supervised law students, and foreign attorneys (outside US) may represent you; notaries are not attorneys | https://www.uscis.gov/scams-fraud-and-misconduct/avoid-scams/find-legal-services | verified |
| AILA Immigration Lawyer Search — private attorneys; filters by practice area, location and 100+ languages | https://www.ailalawyer.com/ | verified |
| USCIS Contact Center 800-375-5283 (TTY 800-767-1833), Mon–Fri 8am–8pm ET, English/Spanish | https://www.uscis.gov/contactcenter | verified |
| EOIR Immigration Court Online Resource (ICOR) — plain-language guides on NTA, hearings, representation (icor.eoir.justice.gov redirects here) | https://www.justice.gov/eoir/immigration-court-online-resource | verified |
| EOIR Automated Case Information (ACIS) — enter A-number for next hearing date/location, judge decision, BIA status; English/Spanish | https://acis.eoir.justice.gov/en/ | verified |
| EOIR Automated Case Information Hotline 1-800-898-7180, 24/7, English/Spanish — next hearing, decision, BIA appeal and brief due dates | https://www.justice.gov/eoir/customer-service-initiatives | verified |
| EOIR court finder with addresses and internet-based (WebEx) hearing links per judge | https://www.justice.gov/eoir/find-immigration-court-and-access-internet-based-hearings | verified |
| EOIR forms page — EOIR-33/IC change of address (filable via Respondent Access), EOIR-26 appeal ($1,030 fee), EOIR-26A fee waiver, EOIR-28; multiple language versions | https://www.justice.gov/eoir/eoir-forms | verified |
| Board of Immigration Appeals page loads; the 30-calendar-day receipt deadline for EOIR-26 is stated in BIA Practice Manual §4.4 (that page returned 403/404 to my tools) | https://www.justice.gov/eoir/board-of-immigration-appeals | likely |
| LawHelp.org (Pro Bono Net) — find free legal aid by state; self-help guides | https://www.lawhelp.org/ | verified |
| LSC Find Legal Aid — map/address search of 129 LSC-funded legal aid organizations | https://www.lsc.gov/about-lsc/what-legal-aid/get-legal-help | verified |
| 45 CFR Part 1626 — LSC-funded programs may serve only citizens and eligible aliens (LPRs, refugees, asylees, etc.) plus VAWA/T/U/trafficking survivors; most undocumented people are excluded | https://www.ecfr.gov/current/title-45/subtitle-B/chapter-XVI/part-1626 | verified |
| LSC Eviction Laws Database — state/territory + 30-community datasets covering the full eviction process (notice periods, answer deadlines, post-judgment) | https://www.lsc.gov/initiatives/effect-state-local-laws-evictions/lsc-eviction-laws-database | verified |
| HRSA Find a Health Center — FQHC locator (page is a JS app; title 'Find a Health Center' confirmed, HTTP 200) | https://findahealthcenter.hrsa.gov/ | verified |
| HealthCare.gov — Marketplace; 1-800-318-2596; Find Local Help; Spanish site; 16+ languages in footer; note about DACA court decisions | https://www.healthcare.gov/ | verified |
| HealthCare.gov Medicaid & CHIP — apply year-round via Marketplace or state agency | https://www.healthcare.gov/medicaid-chip/ | verified |
| HealthCare.gov lawfully-present immigrants page — lists qualified non-citizen statuses and 5-year Medicaid bar (refugees/asylees exempt); NOT updated for H.R.1 2026/2027 restrictions | https://www.healthcare.gov/immigrants/lawfully-present-immigrants/ | verified |
| Medicaid.gov 'Where Can People Get Help With Medicaid & CHIP' — every state agency's contacts/eligibility/enrollment links; also where to check renewal status (URL with /index.html returns 404) | https://www.medicaid.gov/about-us/where-can-people-get-help-medicaid-chip | verified |
| InsureKidsNow.gov — children's Medicaid/CHIP state finder; 1-877-KIDS-NOW (877-543-7669); English/Spanish | https://www.insurekidsnow.gov/ | verified |
| IRS §501(r)(4) — charitable hospitals must have a written Financial Assistance Policy, plain-language summary, application process, and translations for LEP groups of 1,000 people or 5% of community (whichever less) | https://www.irs.gov/charities-non-profits/financial-assistance-policy-and-emergency-medical-care-policy-section-501r4 | verified |
| Dollar For — nonprofit, free help applying for hospital charity care/financial assistance | https://dollarfor.org/ | verified |
| CMS Medical Bill Rights (No Surprises Act) — OON emergency protections; Good Faith Estimate for uninsured/self-pay; dispute bills ≥$400 over estimate within 120 days; Help Desk 1-800-985-3059 in 350+ languages | https://www.cms.gov/initiatives/your-patient-rights/medical-bill-rights | verified |
| CMS No Surprises hub — consumer protections and Help Desk 1-800-985-3059 | https://www.cms.gov/nosurprises | verified |
| Internal appeal: file within 180 days of denial; insurer decides in 30 days (pre-service), 60 days (post-service), 72 hours (urgent) | https://www.healthcare.gov/appeal-insurance-company-decision/internal-appeals/ | verified |
| External review: request within 4 months of final internal denial; decision within 45 days (72 hours expedited); state or HHS-administered; binding on insurer | https://www.healthcare.gov/appeal-insurance-company-decision/external-review/ | verified |
| Prior authorization definition — health-plan approval that may be required before a service/prescription is covered | https://www.healthcare.gov/glossary/prior-authorization/ | verified |
| EOB definition — insurer's written explanation of a claim (what they paid, what you owe); it is not a bill (non-government glossary; HealthCare.gov EOB glossary URL is 404) | https://www.healthinsurance.org/glossary/explanation-of-benefits/ | verified |
| Medicare appeals overview — 5 levels; 2026 judicial-review minimum $1,960 | https://www.medicare.gov/providers-services/claims-appeals-complaints/appeals | verified |
| Original Medicare redetermination — file by the date printed on the Medicare Summary Notice; MAC decides within ~60 days (120-day window is standard but not stated on page) | https://www.medicare.gov/providers-services/claims-appeals-complaints/appeals/original-medicare | verified |
| Medicare Advantage appeal — 65 days from the denial notice; expedited decision within 72 hours | https://www.medicare.gov/providers-services/claims-appeals-complaints/appeals/medicare-health-plans | verified |
| Medicare Part D appeal — 65 days from coverage determination; expedited 72 hours; coverage determination/exception via form, letter or phone | https://www.medicare.gov/providers-services/claims-appeals-complaints/appeals/drug-plans | verified |
| 42 CFR 431.221(d) — Medicaid agency must allow a reasonable time, not to exceed 90 days from mailing of notice, to request a fair hearing | https://www.ecfr.gov/current/title-42/section-431.221 | verified |
| NeedyMeds — patient assistance program database, drug discount card, free/low-cost clinic finder (HTTP 200; JS-rendered, content not machine-read) | https://www.needymeds.org/ | likely |
| GoodRx — free prescription discount coupons/price comparison (HTTP 200 via browser UA; blocks fetchers) | https://www.goodrx.com/ | likely |
| PhRMA Medicine Assistance Tool has become AmericasMedicines.com (mat.org redirects; medicineassistancetool.org connection refused); curl HTTP 200, TLS chain error in fetcher | https://americasmedicines.com/ | likely |
| MedlinePlus — how to understand lab results (reference ranges; out-of-range may not mean a problem) | https://medlineplus.gov/lab-tests/how-to-understand-your-lab-results/ | verified |
| CDC Contacts for IIS Immunization Records — find your/your child's vaccine record via your state's Immunization Information System (updated July 13 2026) | https://www.cdc.gov/iis/contacts-locate-records/index.html | verified |
| CDC State Vaccination Requirements (school/childcare) — current URL; old /vaccines/imz-managers/laws/state-reqs.html redirects | https://www.cdc.gov/vaccines/php/requirements-laws/state-vaccination-requirements.html | verified |
| Immunize.org state policies — school/childcare vaccine requirements and exemption policies by state | https://www.immunize.org/official-guidance/state-policies/ | verified |
| HHS OCR Limited English Proficiency — right to interpreter/translation in HHS-funded programs (pharmacy, ER, nursing home, insurance application); complaint process | https://www.hhs.gov/civil-rights/for-individuals/special-topics/limited-english-proficiency/index.html | verified |
| Feeding America food bank locator — ZIP/state search; anyone who needs help may visit; Spanish site; no ID requirement stated | https://www.feedingamerica.org/find-your-local-foodbank | verified |
| USDA FNS was renamed Food and Nutrition Administration (FNA) effective June 1 2026; fns.usda.gov redirects to fna.usda.gov | https://www.fna.usda.gov/reorganization | likely |
| SNAP State Directory of Resources — state agency hotlines and application links | https://www.fna.usda.gov/snap/state-directory | verified |
| SNAP eligibility — 30-day processing with required interview (phone/in-person) and verification; expedited within 7 days; undocumented non-citizens never eligible; qualified non-citizens generally need 5 years or an exception | https://www.fna.usda.gov/snap/recipient/eligibility | verified |
| WIC program page — for pregnant/recently pregnant/breastfeeding women and children under 5; anyone raising kids under 5 can apply | https://www.fna.usda.gov/wic | verified |
| WIC eligibility — income at/below WIC limits or adjunctive eligibility via Medicaid/SNAP/TANF; no immigration-status requirement | https://www.fna.usda.gov/wic/eligibility | verified |
| SignUpWIC.com (National WIC Association) — eligibility prescreen and local WIC clinic finder; English/Spanish | https://signupwic.com/ | verified |
| School meals for households — apply for free/reduced-price meals through your child's school/district | https://www.fna.usda.gov/nslp/household | verified |
| Child Nutrition Income Eligibility Guidelines page (HTTP 200 via redirect from /cn/income-eligibility-guidelines) | https://www.fna.usda.gov/schoolmeals/income-eligibility-guidelines | likely |
| HUD Find a Housing Counselor — free/low-cost HUD-approved agencies for rental, eviction prevention, foreclosure, homebuying | https://www.hud.gov/findacounselor | verified |
| HUD housing counseling hotline 800-569-4287 and renter protections/eviction help links (CFPB) | https://www.consumerfinance.gov/coronavirus/mortgage-and-housing-assistance/renter-protections/ | verified |
| HUD Public Housing Agency contact directory (Section 8/HCV, public housing) | https://www.hud.gov/program_offices/public_indian_housing/pha/contacts | verified |
| HUD Housing Choice Voucher (Section 8) program page | https://www.hud.gov/topics/housing_choice_voucher_program_section_8 | verified |
| USA.gov Housing help — emergency housing, eviction/foreclosure, rental assistance (usa.gov/eviction is 404) | https://www.usa.gov/housing-help | verified |
| 211 (United Way) — dial 211 for housing, utilities, food, health, mental health, disaster help; English/Spanish; confidential | https://www.211.org/ | verified |
| LIHEAP — heating/cooling bill help, shutoff prevention/reconnection; referral hotline 1-866-674-6327 (acf.hhs.gov redirects to acf.gov) | https://acf.gov/ocs/programs/liheap | verified |
| LIHEAP local office search tool (energyhelp.us redirects here) | https://liheapch.acf.gov/search-tool | likely |
| USA.gov Benefit Finder — 12-category questionnaire; Benefits.gov now redirects to this page (redirect confirmed) | https://www.usa.gov/benefit-finder | verified |
| 988 Suicide & Crisis Lifeline — call/text 988 or chat; Spanish; 240+ languages via interpretation; Deaf/HoH options; 24/7 free confidential | https://988lifeline.org/ | verified |
| National Domestic Violence Hotline — 1-800-799-7233, text START to 88788, live chat; Spanish + 200+ languages; 24/7 confidential | https://www.thehotline.org/ | verified |
| Poison Control — 1-800-222-1222 and webPOISONCONTROL online tool; free, expert, confidential | https://www.poison.org/ | verified |
| National Human Trafficking Hotline — 1-888-373-7888, text 233733; 24/7 confidential | https://humantraffickinghotline.org/ | verified |
| DOJ Title VI page — prohibits race/color/national-origin discrimination by federal fund recipients; notes EO 13166 (LEP) rescinded and guidance under review; report via civilrights.justice.gov | https://www.justice.gov/crt/fcs/TitleVI | verified |
| DOJ LEP page — LEP.gov operations suspended pending review to implement EO 14224 (English as official language), updated July 17 2025; lep.gov redirects here | https://www.justice.gov/crt/limited-english-proficiency | verified |
| USCIS Common Scams — notario, unauthorized practitioners, government impersonators, phishing, job offers, visa lottery, 'pay to jump the line'; USCIS never asks you to transfer money to an individual; pays only via .gov accounts, never Western Union/MoneyGram/PayPal/Venmo/gift cards | https://www.uscis.gov/scams-fraud-and-misconduct/avoid-scams/common-scams | verified |
| USCIS Scams, Fraud and Misconduct hub (old /scams-fraud-and-misconduct/avoid-scams parent URL is 404) | https://www.uscis.gov/scams-fraud-misconduct | likely |
| USCIS forms and online accounts are always free; fees apply only when filing | https://www.uscis.gov/forms/all-forms | verified |
| FTC Scams Against Immigrants hub — materials in 12 languages; report at ReportFraud.ftc.gov / ReporteFraude.ftc.gov or 877-382-4357 (consumer.ftc.gov/immigration redirects here) | https://consumer.ftc.gov/features/scams-against-immigrants | verified |
| FTC How To Avoid Immigration Scams — only attorneys/DOJ-accredited reps may give legal advice; never pay for free forms, sign blank forms, or pay by gift card/wire/crypto; DV lottery is free and only at dvprogram.state.gov | https://consumer.ftc.gov/articles/how-avoid-immigration-scams-and-get-real-help | verified |
| ReportFraud.ftc.gov — FTC fraud reporting portal (HTTP 200; JS app) | https://reportfraud.ftc.gov/ | verified |
| FTC gift card scams — no real business or government agency will ever tell you to pay with a gift card; steps if you paid | https://consumer.ftc.gov/articles/avoiding-and-reporting-gift-card-scams | verified |
| FTC job scams — honest employers never ask you to pay to get a job; fake-check and reshipping schemes; report to FTC/state AG | https://consumer.ftc.gov/articles/job-scams | verified |
| IRS Recognize tax scams — IRS contacts by mail first; never demands gift cards/prepaid cards/wire or threatens arrest/deportation; report to phishing@irs.gov / TIGTA | https://www.irs.gov/help/tax-scams/recognize-tax-scams-and-fraud | verified |
| SSA Protect Yourself from Scams — four signs of a scam; July 29 2026 alert on fake call transfers; report to SSA OIG | https://www.ssa.gov/scam/ | verified |
| DHS OIG Hotline — report fraud/impersonation involving DHS (ICE/USCIS) personnel: 1-800-323-8603 or online form | https://www.oig.dhs.gov/hotline | verified |
| ICE ERO — 24 field offices; ATD/check-in oversight; official tip line 1-866-DHS-2-ICE | https://www.ice.gov/ero | verified |
| Office of Refugee Resettlement home (acf.gov; returns 403 to non-browser fetchers) | https://acf.gov/orr | verified |
| ORR Key State Contacts — State Refugee Coordinators and State Refugee Health Coordinators with phone numbers by state (replaces the 404'd /orr/map/find-resources-and-contacts-your-state) | https://acf.gov/orr/programs-services/refugees/contacts/state-contacts | verified |
| ORR Benefits for Afghan Humanitarian Parolees — cash and medical assistance, Refugee Support Services (employment, ESL, case management up to 5 years), Matching Grant | https://acf.gov/orr/fact-sheet/benefits-afghan-humanitarian-parolees | verified |
| International Rescue Committee — US resettlement/asylum/integration; offices in 25+ US cities | https://www.rescue.org/ | verified |
| USCRI — legal, health, anti-trafficking and resettlement services; 'Find Us' office list | https://refugees.org/ | verified |
| HIAS — US legal services (NY, MD) and resettlement partner network | https://hias.org/ | verified |
| Global Refuge (formerly LIRS) — resettlement, legal, mental health, family reunification; 410-983-4000 | https://www.globalrefuge.org/ | verified |
| Church World Service — resettlement, asylum/border, legal and children's services; 1-800-297-1516; office map at cwsglobal.org/our-work/united-states/map-of-cws-offices/ | https://cwsglobal.org/ | verified |
| World Relief — resettlement and immigration legal services; US locations at worldrelief.org/us-locations/ | https://worldrelief.org/ | verified |
| Ethiopian Community Development Council (ECDC) — national resettlement agency with 7 branches and 17 affiliates | https://www.ecdcus.org/ | verified |
| Refugee Council USA — coalition of 40+ refugee organizations (members page separate) | https://rcusa.org/ | verified |
| Switchboard (ORR-funded TA hub) — provider resources plus SettleIn newcomer information in 10+ languages | https://www.switchboardta.org/ | verified |
| USCIS USRAP page loads (last reviewed 04/24/2026); FY2026 ceiling not shown on page (7,500 per press reports) | https://www.uscis.gov/humanitarian/refugees-and-asylum/usrap | verified |
| USCIS Information for Afghan Nationals — parole/re-parole (streamlined), expedited asylum (interview within 45 days, decision within 150), SIV adjustment, EADs | https://www.uscis.gov/humanitarian/information-for-afghan-nationals | verified |
| #AfghanEvac — coalition; Battle Buddies volunteer accompaniment for immigration appointments; pipeline trackers | https://afghanevac.org/ | verified |
| State Department Afghan SIV page — could not be loaded (Cloudflare bot challenge blocked fetcher, curl and headless browser) | https://travel.state.gov/content/travel/en/us-visas/immigrate/special-immg-visa-afghans-employed-us-gov.html | unverified |
| ASAP (Asylum Seeker Advocacy Project) — free membership; asylum, work permit, court and fee guides in English, Spanish, Haitian Creole, Russian, Mandarin (asylumadvocacy.org redirects here) | https://asaptogether.org/en/ | verified |
| ASAP Annual Asylum Fee explainer — ~$102 (indexed) per year pending; 30 days to pay after notice; no fee waiver; some people never receive the notice; non-payment can lead to rejection/EAD cancellation | https://asaptogether.org/en/new-fees/ | verified |
| USCIS Asylum — affirmative vs defensive; file I-589 within 1 year of arrival; EAD eligible after 180 days pending (file I-765 at 150); new rules effective Aug 21 2026: evidence 14 days before interview, exceptional circumstances to reschedule, dismissal for no-show | https://www.uscis.gov/humanitarian/refugees-and-asylum/asylum | verified |
| USCIS Affirmative Asylum Process — steps: I-589, biometrics, interview notice (bring family; interpreter if needed), decision pickup ~2 weeks later, referral to court if not granted | https://www.uscis.gov/humanitarian/refugees-and-asylum/asylum/the-affirmative-asylum-process | verified |
| Form I-589 page — Annual Asylum Fee must be paid online with A-number and receipt number each year pending; one-year filing deadline; Ms. L. class members must file on paper | https://www.uscis.gov/i-589 | verified |
| USCIS H.R.1 fees (postmarked on/after July 22 2025): $100 asylum application fee; $100 Annual Asylum Fee; EAD for asylum applicants/parolees/TPS $550 initial / $275 renewal; TPS up to $500; fees cannot be waived or reduced; unpaid forms rejected after Aug 21 2025 | https://www.uscis.gov/newsroom/alerts/uscis-updates-fees-based-on-hr-1 | verified |
| DOL Wage and Hour complaints — 1-866-487-9243; free; confidential; immigration status not a barrier; gather pay records, hours, employer info | https://www.dol.gov/agencies/whd/contact/complaints | verified |
| DOL WHD immigration page — lists visa programs WHD administers (H-1B, H-2A, H-2B); does not state enforcement stance on status | https://www.dol.gov/agencies/whd/immigration | verified |
| EEOC Employees & Job Applicants — file a charge; 1-800-669-4000; resources in 11+ languages; protected bases incl. national origin | https://www.eeoc.gov/employees-job-applicants | verified |
| EEOC charge deadline 180 calendar days, extended to 300 days where a state/local agency enforces a similar law; file via Public Portal, phone, in person at 53 offices, or mail | https://www.eeoc.gov/how-file-charge-employment-discrimination | verified |
| EEOC national origin discrimination — covers ethnicity, accent, perceived background; file via Public Portal or 1-800-669-4000 (eeoc.gov/immigrants-employment-rights is 404) | https://www.eeoc.gov/national-origin-discrimination | verified |
| OSHA Workers — confidential complaints; 1-800-321-OSHA; retaliation complaint within 30 days | https://www.osha.gov/workers | verified |
| OSHA file a safety complaint page (HTTP 200) | https://www.osha.gov/workers/file-complaint | likely |
| National Center for Homeless Education — ED's technical assistance center for the McKinney-Vento EHCY program | https://nche.ed.gov/ | verified |
| NCHE McKinney-Vento page — immediate enrollment without immunization/residency records, school of origin, transportation, local liaison in every district, dispute process | https://nche.ed.gov/mckinney-vento/ | verified |
| SchoolHouse Connection Homeless Education Directory — McKinney-Vento state coordinators and local district liaisons by state | https://schoolhouseconnection.org/homeless-education-directory | verified |
| Plyler v. Doe fact sheet (American Immigration Council) — K-12 access regardless of status; schools may not ask status or require SSNs; 8 states introduced 15+ bills since 2025 challenging it | https://www.americanimmigrationcouncil.org/fact-sheet/plyler-v-doe-public-education-noncitizen-students/ | verified |
| US Department of Education IDEA site (403 to fetchers; loads in browser) | https://sites.ed.gov/idea/ | verified |
| Parent Center Hub — find your state's free Parent Training and Information Center (nearly 100 PTIs/CPRCs, birth to 26) | https://www.parentcenterhub.org/find-your-center/ | verified |
| IEP overview — IEP meeting within 30 calendar days of eligibility determination; annual review required | https://www.parentcenterhub.org/iep-overview/ | verified |
| OCR Parent and Educator Resource Guide to Section 504 (identification, evaluation, placement, dispute procedures) hosted by Parent Center Hub (ed.gov 504 FAQ URL is 404) | https://www.parentcenterhub.org/ocr-guide-to-section504/ | verified |
| Inova Financial Assistance — uninsured with income ≤400% FPL get 100% discount; VA service-area residency; apply via MyChart/mail/in person; 571-472-5880 M–F 8–4:30; summaries in 10 languages | https://www.inova.org/patient-and-visitor-information/financial-assistance | verified |
| Fairfax County CHCN — uninsured residents of Fairfax County/Fairfax City/Falls Church, ≤200% FPL, 9 months residency; currently waitlist; Merrifield 703-237-3446, North County 703-689-2180, South County 703-704-5333 | https://www.fairfaxcounty.gov/health/community-health-care-network | verified |
| Neighborhood Health — FQHC serving Alexandria/Arlington/Fairfax; sliding fee; 703-535-5568 | https://www.neighborhoodhealthva.org/ | verified |
| Legal Aid Justice Center — immigration, housing, workplace; offices Falls Church/NoVA, Charlottesville, Richmond, Petersburg; EN/ES | https://www.justice4all.org/ | verified |
| Ayuda — immigration/DV legal, social and language services for low-income immigrants in DC/MD/VA; DC 202-387-4848, Fairfax 703-444-7009, Silver Spring 240-594-0600 | https://www.ayuda.com/ | verified |
| Just Neighbors — immigration legal services for low-income immigrants in DC/MD/VA; 703-979-1240 / 703-991-4576 | https://www.justneighbors.org/ | verified |
| Tahirih Justice Center — free legal + social services for immigrant survivors of gender-based violence; Falls Church, Baltimore, Atlanta, Houston, SF Bay Area; 866-575-0071 | https://www.tahirih.org/ | verified |
| Capital Area Food Bank Find Food — address-search partner map for DC/MD/NoVA; Hunger Lifeline 202-644-9807 | https://www.capitalareafoodbank.org/find-food-assistance/ | verified |
| Northern Virginia Family Service — immigration legal, health access, housing/food, workforce, mental health; 571-748-2500; multilingual | https://www.nvfs.org/ | verified |
| NVFS Find Support page — program list and intake contact 571-748-2500 / info@nvfs.org | https://www.nvfs.org/find-support | verified |
| Fairfax County Coordinated Services Planning — single point of entry for basic-needs help; 703-222-0880, TTY 711, M–F 8–4:30; 15+ languages | https://www.fairfaxcounty.gov/neighborhood-community-services/coordinated-services-planning | verified |
| Virginia Court Self-Help Landlord-Tenant — eviction (unlawful detainer) cases heard in General District Court; strict deadlines; forms page | https://selfhelp.vacourts.gov/page/10/landlord-tenant | verified |
| Va. Code §55.1-1245 — 14 days' written notice to pay before termination for nonpayment; 30-day termination notice with 21 days to cure for other breaches; further amendments effective July 1 2027/2028 | https://law.lis.virginia.gov/vacode/title55.1/chapter12/section55.1-1245/ | verified |
| Fairfax County Sheriff eviction process — summons/hearing, 10-day appeal period, writ of eviction, minimum 72 hours' notice before eviction | https://www.fairfaxcounty.gov/sheriff/eviction-process | verified |
| Virginia Eviction Legal Helpline site (evictionhelpline.org redirects); helpline number 1-833-NOEVICT per search, not shown on fetched text | https://fightmyeviction.org/ | likely |
| USCIS Form I-797 types — I-797 approval/receipt; I-797A with I-94; I-797B worker petition approval; I-797C receipt/rejection/transfer/biometrics/interview appointments; I-797D with cards; I-797E Request for Evidence; I-797F transportation letter | https://www.uscis.gov/forms/filing-guidance/form-i-797-types-and-functions | verified |
| USCIS Policy Manual Vol.1 Pt.E Ch.6 — RFE response period up to 12 weeks/84 days (+3 days if mailed = 87); NOID 30 days (+3 = 33); no extensions; non-response → denial as abandoned or on the record | https://www.uscis.gov/policy-manual/volume-1-part-e-chapter-6 | verified |
| Biometrics (ASC) appointment — bring I-797C notice and photo ID; reschedule via online account before the appointment; missing without good cause may be treated as abandonment | https://www.uscis.gov/forms/filing-guidance/preparing-for-your-biometric-services-appointment | verified |
| USCIS change of address — required within 10 days of moving (online/AR-11); USPS will not forward USCIS mail | https://www.uscis.gov/addresschange | verified |
| 10 Steps to Naturalization — receipt notice, biometrics notice, interview notice (bring it), oath ceremony notice N-445 | https://www.uscis.gov/citizenship/learn-about-citizenship/10-steps-to-naturalization | verified |
| Naturalization interview & test — N-400 filed on/after Oct 20 2025 → 2025 civics test (20 questions, pass 12); earlier → 2008 test (10/6); two attempts; retest 60–90 days later | https://www.uscis.gov/citizenship/learn-about-citizenship/the-naturalization-interview-and-test | verified |
| Form N-400 — eligibility 5 years LPR or 3 years married to citizen; fee $760 paper / $710 online / $380 reduced fee; fee waiver paper-only | https://www.uscis.gov/n-400 | verified |
| Replace Your Green Card — file I-90 if card is expired or expires within 6 months; I-797C receipt extends validity 36 months and serves as proof of status/work authorization with the expired card | https://www.uscis.gov/green-card/after-we-grant-your-green-card/replace-your-green-card | verified |
| After We Grant Your Green Card — conditional 2-year cards cannot be renewed; file removal-of-conditions petition in the 90 days before expiration | https://www.uscis.gov/green-card/after-we-grant-your-green-card | verified |
| Form I-90 page (HTTP 200) | https://www.uscis.gov/i-90 | verified |
| Form I-765 — file EAD renewal up to 180 days before expiration | https://www.uscis.gov/i-765 | verified |
| DHS ended automatic EAD extensions for renewals filed on/after Oct 30 2025 (exceptions only by law/TPS Federal Register notices); file up to 180 days early | https://www.uscis.gov/newsroom/news-releases/dhs-ends-automatic-extension-of-employment-authorization | verified |
| Archived USCIS 540-day auto-extension page — marked historical; policy ended Oct 30 2025 (uscis.gov/eadautoextend redirects here) | https://www.uscis.gov/archive/automatic-employment-authorization-document-ead-extension | verified |
| I-797C receipts for I-765 renewals filed on/after Oct 30 2025 state they are not evidence of employment authorization (from USCIS/E-Verify releases via search) | https://www.uscis.gov/i-9-central/form-i-9-related-news/interim-final-rule-published-to-end-the-practice-of-automatically-extending-certain-employment | likely |
| USCIS TPS — re-register during each Federal Register period with I-821 (+I-765) or lose TPS/work authorization; page lists current designations and 2025–26 terminations (some in litigation) | https://www.uscis.gov/humanitarian/temporary-protected-status | verified |
| ICE Check-In — schedule at checkin.ice.gov / ICE Portal with Subject ID and birthplace; making an online appointment satisfies release requirements even if the date is later than the paperwork | https://www.ice.gov/check-in | verified |
| SSA Appeal a decision — four levels: reconsideration, ALJ hearing, Appeals Council, federal court (60-day deadline not shown on this page) | https://www.ssa.gov/apply/appeal-decision-we-made | verified |
| IRS Understanding Your Notice — look up CP/LTR number (top right); respond by the date; if not found call 800-829-1040; IRS never demands gift cards | https://www.irs.gov/individuals/understanding-your-irs-notice-or-letter | verified |
| ITIN — for those ineligible for SSN regardless of status; Form W-7 with passport or two documents; Certifying Acceptance Agents; ITINs expire; ~7 weeks (9–11 peak) | https://www.irs.gov/individuals/individual-taxpayer-identification-number | verified |
| About Form W-7 (HTTP 200) | https://www.irs.gov/forms-pubs/about-form-w-7 | likely |
| About Form W-2 (HTTP 200) | https://www.irs.gov/forms-pubs/about-form-w-2 | likely |
| About Form 1099-NEC (HTTP 200) | https://www.irs.gov/forms-pubs/about-form-1099-nec | likely |
| USCIS I-9 Central (HTTP 200) | https://www.uscis.gov/i-9-central | likely |
| Federal juror qualifications — must be a US citizen (plus age 18+, residency, English, no disqualifying felony); noncitizens should return the form/contact the court rather than ignore a summons | https://www.uscourts.gov/court-programs/jury-service/juror-qualifications-exemptions-and-excuses | verified |
| H.R.1 (P.L. 119-21) health coverage changes — Marketplace subsidies: Jan 1 2026 none below 100% FPL; Jan 1 2027 only citizens/LPRs/Cuban-Haitian entrants/COFA; Medicaid/CHIP federal funding limited to same groups from Oct 1 2026; DACA ineligible since Aug 25 2025; refugees, asylees, TPS, parolees lose eligibility (CBPP explainer) | https://www.healthreformbeyondthebasics.org/new-immigration-related-restrictions-for-medicaid-chip-medicare-and-marketplace/ | verified |
| USCIS 'Find Legal Services' and 'Common Scams' both direct reporting to state bars, DHS Disciplinary Counsel, FTC and state AGs | https://www.uscis.gov/scams-fraud-and-misconduct/avoid-scams/common-scams | verified |
