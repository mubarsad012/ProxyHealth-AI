# ProxyHealth AI — Congressional App Challenge 2026 submission kit

Source of every rule below: the official **2026 CAC Rules** (congressionalappchallenge.us, `2026-CAC-Rules.pdf`, fetched 2026-10-22). Quotes are verbatim.

> **Deadline: 12:00 pm EDT, Monday, October 26, 2026.** After the deadline "the Submission cannot be modified in any way." Leave a day of margin for the video upload and the registration emails.

---

## 1. Read this first: eligibility and authorship

These two rules decide whether this project can be entered as it stands. Decide this before spending time on the video.

### 1.1 Who can enter

> "Students must be enrolled in middle school or high school on October 26th, 2026."

> "Students may compete in either the district in which they reside, or the district in which they attend school … Participants are only allowed to submit an app in one district."

A college student cannot enter. If the person entering is a middle- or high-school student, the authorship rules below apply to **that student's own work**.

### 1.2 Who must write the code

> **ORIGINALITY:** "The app must be original and solely created by the contestant. All coding and technical development must be done by the student or student team. While participants may use open-source libraries, frameworks, and external tools, they must clearly document any such usage and ensure their project reflects significant personal effort and technical understanding."

> **AI USAGE:** "The use of AI tools in app development for the Congressional App Challenge is permitted, provided that all AI usage is fully disclosed in the submission materials. AI may only be used to support specific aspects of the project and must not constitute the entirety of the technical development. Participants are expected to demonstrate significant individual contributions and technical understanding of their app."

### 1.3 Honest assessment of this repository

- The concept, the original product blueprint (the "ProxyHealth AI Master Product Blueprint": three-card layout, dynamic language box, screenshot troubleshooting, resource router, quick sheets, read-aloud, multi-key failover, legal help for immigrants) and the product decisions came from the developer.
- **The source code, tests, data files and most of the documentation in this repository were written by an AI coding assistant** (Anthropic's Claude, running in Claude Code), from 2026-09-23 to 2026-10-22, following that blueprint. Git history and `docs/DECISIONS.md` record this work.
- Under the rules quoted above, an entry whose code was written by AI almost entirely is at serious risk of disqualification: AI "must not constitute the entirety of the technical development", and "all coding and technical development must be done by the student".

### 1.4 Options (the entrant decides; none of these is legal advice)

1. **Do the coding yourself, then enter.** Before October 26, the student designs and codes real parts of the app themselves, and can explain every line of those parts. The AI-written parts are disclosed as AI-written (section 3). This is only honest if the student's part is real and significant, not a rename or a reformat. Four days is very little time for that.
2. **Enter with full disclosure and let the judges decide.** Fill section 3 truthfully, including that the AI wrote most of the code. The judges "have the right to request access to the App and source code … to verify", and may disqualify the entry.
3. **Skip 2026 and build your own entry for 2027.** Use this project as a reference and learning resource. The rules allow "any app they've created after October 30th, 2025", and a "2.0" entry must highlight only the new code.
4. **Ask the organisers.** Email the program administrator (Internet Education Foundation, via congressionalappchallenge.us) or your Member of Congress's office, describe how the app was made, and ask whether it is eligible. Their answer is the one that counts.

Do **not** describe AI-written code as your own anywhere in the video or the written answers. The rules require full disclosure, and judges can ask you to explain the code.

---

## 2. Submission checklist (from the rules)

**Registration** (congressionalappchallenge.us; each team member needs):
- [ ] a **personal** email address (not a school account)
- [ ] home address with **9-digit ZIP**, Congressional District and Member of Congress
- [ ] school address with 9-digit ZIP, district and Member of Congress
- [ ] a parent or guardian's name and email
- [ ] (optional) a coding teacher or mentor's name and email
- [ ] personal profile + **eligibility quiz** (you get an email to continue)
- [ ] your Member of Congress is **hosting** a challenge in your district (check the district page)
- [ ] team rule: up to 4 students; at least half live or attend school in the district

**Application:**
- [ ] demonstration video, **1–3 minutes**, uploaded to **YouTube or Vimeo**, set to **public** (section 5)
- [ ] answers to the written questions (section 6)
- [ ] source code link: a public GitHub repository (section 7)
- [ ] AI usage disclosure (section 3) and open-source documentation (section 4) in the submission materials
- [ ] one app per person per year

**After the deadline:** every team member completes the **Exit Questionnaire** individually.

---

## 3. AI usage disclosure (draft — check every sentence before using it)

> The rules require that "all AI usage is fully disclosed". Keep only sentences that are true for you; add anything missing.

**AI used to build the app (development):**
- **Anthropic Claude (via Claude Code)**, an AI coding assistant, wrote the source code (FastAPI backend in Python; Expo/React Native app in TypeScript), the automated tests, the sample documents, the resource database files, the build scripts and most of the design documentation. It also researched current AI models, the Expo SDK, privacy and app-store rules, and resource links, and ran the tests. It worked from the developer's written blueprint and instructions, from 2026-09-23 to 2026-10-22.
- **What the developer did:** _(fill in honestly — for example: wrote the original product blueprint and feature list; chose the target users and languages; directed the AI step by step; made product decisions; tested the app in the browser; set up the local AI model; wrote this submission. Add any code you wrote yourself, with file names.)_

**AI used inside the app (features, not development):**
- **Google Gemini API** (gemini-3.8-flash, gemini-3.5-flash-lite): reads a photographed paper and returns structured explanations, when the server is configured with keys.
- **Qwen3.5-4B** (Alibaba, open weights, Apache-2.0), run locally with **Ollama**, for testing with real papers on the developer's own computer.
- With no keys, the app runs on a built-in **sample mode** that uses pre-written outputs for 18 made-up sample papers.

---

## 4. Open-source libraries, tools and data (required documentation)

The full list, with versions, licenses and what each is used for, is in [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md): 43 runtime and 11 development npm packages, 24 Python packages, the Noto fonts (SIL OFL), one icon adapted from Feather Icons (MIT), and the external AI services. No GPL or AGPL code ships in the app. Link that file in the submission.

The main building blocks, for the video and the written answers:

- **App (iPhone, Android, web from one codebase):** TypeScript, React Native 0.86, Expo SDK 57, Expo Router, zustand, react-native-svg.
- **Server:** Python 3.13, FastAPI, Pydantic v2, google-genai (Gemini), httpx, Pillow, pypdfium2, reportlab, arabic-reshaper and python-bidi.
- **Testing:** pytest, Jest, Testing Library, ruff, mypy, ESLint.
- **AI at runtime:** Google Gemini (paid tier for real papers), or Qwen3.5-4B run locally with Ollama; zero-key sample mode needs neither.
- **AI used to build it:** Anthropic Claude via Claude Code (section 3).

Size of the repository on 2026-10-24, for reference:

| Item | Count |
|---|---|
| Commits | 47 |
| Tracked files | 871 |
| Server Python, excluding tests | 27,407 lines |
| App TypeScript, excluding tests | 28,924 lines |
| Server tests | 3,403 passing (28 live-only tests skip without keys) |
| App tests | 566 |
| Spec documents | 14 |

---

## 5. Demonstration video (1–3 minutes, public on YouTube or Vimeo)

The rules require the video to show: the participant names, the app name, the purpose **in one clear sentence**, the target audience, the tools and coding languages, and the app's functionality. The video should be the entrant speaking in their own words. The script below is a structure, not lines to read.

| Time | Show | Say (your own words) |
|---|---|---|
| 0:00–0:15 | Your face or a title card | Your name(s), the app name "ProxyHealth AI", and the one-sentence purpose, e.g. "ProxyHealth AI helps immigrants understand medical, legal and benefits papers in their own language." |
| 0:15–0:30 | Home screen | Who it is for: immigrant families, often reading a second language, with papers that have deadlines. Why it matters to you. |
| 0:30–1:45 | `make dev` → Try a sample → Medicaid letter | Three cards (What is this? / What is it asking for? / Step-by-step plan); the exact quote from the paper next to each deadline; the urgency banner; "Show the clerk"; Help nearby with "what to bring". |
| 1:45–2:15 | Switch to Dari (or type a rare language) | Right-to-left layout, "Adapting system environment to your language...", read-aloud, the scam-letter sample. |
| 2:15–2:45 | Code / architecture slide | Tools and languages: TypeScript + React Native (Expo) for iPhone, Android and web; Python + FastAPI for the server; Google Gemini or a local Qwen model for reading; **and the AI coding assistant used to build it (section 3)**. |
| 2:45–3:00 | Closing | What you would add in 2.0 (section 6, question 6). |

**How to record on this Mac (nothing to install):**
1. Switch the API to sample mode for a reliable demo: `scripts/use-local-ai.sh --off`, then `make dev`. (The local AI model works, but one paper takes 1½–7½ minutes on this Mac — too slow for a 3-minute video. You can say in the video that it can also read real papers with a model running on your own computer. `scripts/use-local-ai.sh --restore` switches back afterwards.)
2. Press **Shift-Command-5**, choose "Record Selected Portion" around the browser window, click **Options → Microphone → MacBook Pro Microphone**, then **Record**.
3. Stop with the stop button in the menu bar. The `.mov` file lands on the Desktop. You can trim it in QuickTime Player (**Edit → Trim**).
4. Upload to YouTube or Vimeo, set visibility to **Public** (the rules require public, not unlisted), and paste the link into the application.

Recording tips: run the app in **sample mode** (`AI_PROVIDER=mock`, no keys) so nothing depends on the internet or a model; use the browser's device toolbar for a phone-sized view; keep it under 3:00.

---

## 6. Written questions

The rules say the questions will be "similar to" the six below. Answer them in your own words and claim only what you did yourself. Notes after each question are facts you can check against the repo.

1. **Title:** ProxyHealth AI.
2. **Purpose:** Explains photographed papers (medical bills, USCIS notices, eviction notices, benefits letters, school forms) in the reader's language: what it is, what it asks for, and a step-by-step plan. Every deadline is quoted word for word from the paper, and the user is pointed to vetted local help. It explains; it does not give legal or medical advice.
3. **Inspiration:** Yours to answer.
4. **Technical difficulty:** Answer only from your own experience. Facts that may help you describe what was hard (they are documented in `docs/DECISIONS.md`):
   - stopping the AI from inventing phone numbers or dates (every fact must match a quote on the paper)
   - right-to-left languages
   - privacy, since free AI tiers may train on uploads
   - running with zero keys for judges
   - long tasks stalling when the computer slept
5. **What you learned / biggest takeaway:** Yours to answer.
6. **2.0 ideas** (from the open items in `docs/DECISIONS.md` §12–§14):
   - native-speaker review of the Dari, Pashto and Arabic text
   - an iOS build with saved papers excluded from iCloud backup
   - more local resources beyond Northern Virginia
   - app lock (PIN)
   - an offline scan queue
   - store release on the paid Gemini tier

---

## 7. Source code and running the app (for judges)

- **Repository:** push this repo to a **public** GitHub repository and give its link. Checklist first (section 7.1).
- **Run it with zero keys** (macOS/Linux, Python 3.13, Node 24): `make dev` → open http://localhost:8081 → "Try a sample paper". Full instructions: `README.md`.
- **Optional live demo for judges:** host the web build and the mock API (see `docs/DEPLOYMENT.md`); judges can then try the samples without installing anything.

### 7.1 Before making the repository public (audit of 2026-10-22)

The repository is safe to publish: no real keys, passwords or `.env` files anywhere in its history, no file over 1 MB, and every sample paper is synthetic and watermarked. Before the first push:

- [ ] **Choose a license** and add a root `LICENSE` file in the owner's name (for example MIT). Without one the code is "all rights reserved", which is allowed but means judges may only read it.
- [ ] **Check the author name and email in the history.** All commits are authored as the git identity set on this Mac (`git log --format='%an <%ae>' | sort -u`). That name and email become public. If they should not, change them before the first push (GitHub "noreply" address); the commits also name Claude as co-author, which is accurate and should stay.
- [ ] **Push with git**, not the GitHub web uploader (the uploader ignores `.gitignore`). If a source ZIP is ever needed: `git archive --format=zip -o ProxyHealth-source.zip HEAD`.
- [ ] After the first push, open the repository's **Actions** tab: the CI workflow runs for the first time. If it fails and there is no time to fix it, disable it until after judging.
- [ ] Optional: the sample USCIS receipt numbers use the real format (`IOE…`); they are made up, but could be swapped for obviously fake ones after the deadline.

### 7.2 Verified working (zero-key sample mode, web, 2026-10-22)

| Feature | Result |
|---|---|
| Language picker; rare-language box ("Rohingya" → "Adapting system environment to your language...") | works |
| Consent screen (Sample mode badge, 18+ line, "Not now") | works |
| Home tiles, tab bar, "Need help now?" emergency screen | works |
| Medicaid sample → urgency banner + three cards with word-for-word quotes, confidence and page | works |
| Source view (tap a quote → highlighted on the page) | works |
| Chat: date question answered with a quote; outcome question politely refused | works |
| Clerk card (English, high contrast, interpreter line, read aloud) | works |
| Get help nearby with the "what to bring" checklist (Virginia) | works |
| Quick sheet on screen + PDF download | works |
| Save → My papers → Delete everything | works |
| Portal screenshot troubleshooting (sample) | works |
| Scam sample → scam card first | works |
| Dari (right-to-left) end to end | works |
| Read aloud with an honest "no voice" fallback | works |
| Remind me (.ics) on sample papers | fixed after the audit (see `docs/DECISIONS.md` §14) |
| `make smoke` (224 end-to-end API checks) | passes |

### 7.3 Verified with the local AI model (qwen3.5:4b on this Mac, 2026-10-24)

All 17 sample papers in English, plus the Medicaid letter in Spanish and the court notice in Dari, went through the real API with the local model (`AI_PROVIDER=openai_compat`, `local` tier). Every one returned a full result: none timed out, and no fact the server showed was unverified.

| Check (against each sample's expected answer) | Result |
|---|---|
| Papers answered | 19 / 19 (81–454 s each; most 160–230 s) |
| Facts shown with a word-for-word quote that the server verified | 38 shown, 0 rejected |
| Scam verdict (gift-card letter "likely"; every genuine letter "none") | 19 / 19 |
| Category, disclaimer | 19 / 19 each |
| Nearest deadline date | 18 / 19 |
| Document type | 17 / 19 (the model read the insurance denial as a medical bill and the traffic notice as a general notice) |
| Urgency level | 16 / 19 before the final fix, which removed the false emergency on the prescription label (re-checked live) |

How this was reached, and what changed in the code, is in `docs/DECISIONS.md` §14 (CL-094 to CL-098 and the entries after them). A small 4-billion-parameter model makes mistakes a larger one does not. The server catches most of them: it checks every quote against the page, computes dates and urgency only in code, and decides scams and emergencies from the page text. Check every answer against the paper.

