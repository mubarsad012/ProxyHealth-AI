# Free AI providers for testing with real papers (decision document)

_Status: proposal for the developer, 2026-10-01. No code has been written. The lead engineer built this from four research agents' findings (each checked against official pages on 2026-10-01) and re-checked the key pages that same day. A separate fact-checker then re-fetched the cited official pages (including most [R] ones) on 2026-10-01 and corrected this file in place; facts it confirmed are upgraded to [V]. Input to a future DECISIONS entry, not a spec._

**Question asked:** "Find free APIs I can use, maybe some Chinese models, so we can test with real docs."

**Confidence marks used in every section**

- **[V] verified:** the lead or the fact-checker re-fetched the official page on 2026-10-01 and it says this. The `Sx` number points to §7 Sources.
- **[L/R] research-verified:** a research agent fetched the official page on 2026-10-01 and marked the fact verified, but neither the lead nor the fact-checker re-fetched it. Treat it as one step below [V].
- **[L] likely:** from a credible secondary source, a summary of an official page, an unofficial mirror of an official text, or a figure derived from official numbers.
- **[U] unverified:** the official page does not state it ("not stated"), or nobody checked it.
- **[E] estimate:** my own arithmetic. The assumptions are given next to the number.

**Gaps in what the research agents handed over.** The "Western free tiers" findings were cut off after NVIDIA, and the fourth research agent's output never arrived. I re-fetched the affected official pages myself: Groq, Cerebras, Cloudflare, OpenRouter, Mistral, NVIDIA, GitHub Models, Hugging Face, the Google Cloud trial, Vertex data governance, Vertex Express terms, the Gemini terms, billing and pricing pages, and the US Department of Justice (DOJ) data-security rule. Azure, SambaNova and Together AI originally rested only on the research summary; the fact-checker has since fetched their official pages (S114–S118), and only the Azure model-quota question is still [U].

**This machine.** MacBook Air M4 (10-core CPU, 8-core GPU), 16 GB unified memory, macOS 26.5.1, no Homebrew, no Ollama or LM Studio installed, `jq` 1.7.1 at `/usr/bin/jq` (all re-checked locally by the fact-checker). Free disk was 9.3 GiB when the research agent checked, 10.07 GiB when this was written, and **8.6 GiB when the fact-checker ran `df -h /System/Volumes/Data`** later the same day. Free space moves; plan for about 8.5 GiB.

---

## 1. TL;DR

### 1.1 The answer in five lines

1. **Your own real papers:** run Alibaba's open Qwen model on this Mac with Ollama (`ollama pull qwen3.5:4b`, 3.4 GB) [V S10]. Nothing leaves the laptop ("We don't see your prompts or data when you run locally" [V S4]). No account, no quota, $0.
2. **Synthetic (made-up) papers:** anything works. Keep `AI_PROVIDER=mock` for UI work. The Gemini free tier, which the app already supports as `unpaid`, is fine for synthetic fixtures only [V S80].
3. **A hosted model for your own papers:** the best free option is Alibaba Cloud Model Studio International (Singapore). It gives about 1M free tokens per model for 90 days, and its contract says it will not train on your content [V S40, S44]. But Alibaba is a group headquartered in mainland China (the PRC), so read §1.5 first. US-hosted options with no-training or no-retention terms also exist (Groq and Cloudflare Workers AI: no training; the Cerebras trial: no retention, training not stated), but their limits are small.
4. **Production (other people's papers):** none of the free options qualifies. Stay on the Gemini paid tier, which is already built; linking an active billing account with a $5 prepay is enough to put a project on Paid Services [V S80, S82]. The $300 Google Cloud free trial does **not** do this (§1.4). Vertex AI is the other choice.
5. **Build:** add one `openai_compat` provider and one new data-use tier, `local`. No new packages are needed (`httpx` and `pypdfium2` are already in the venv). That single provider can reach Ollama, LM Studio, Alibaba, Z.ai, Groq, Cerebras, OpenRouter, Mistral and Cloudflare. GitHub Models was on the original list, but it was retired on 2026-07-30 [V S101].

### 1.2 (a) Testing with synthetic samples

| Need | Use | Why |
|---|---|---|
| UI, flows, CI | `AI_PROVIDER=mock` (default) | Zero keys, already built (CLAUDE.md rule 6). |
| A live model on the synthetic fixtures | A Gemini free-tier key with `billing:false` (today's setup) | Free. The terms only forbid "sensitive, confidential, or personal information" [V S80], and the fixtures in `apps/api/data/fixtures/` are made up. D-01 already limits `unpaid` to samples. |
| A non-Google comparison on fixtures | Ollama + `qwen3.5:4b` locally, or any hosted free endpoint in §2 | Shows whether prompts and schemas are Gemini-specific. |

### 1.3 (b) Testing with your OWN real papers

**Recommendation: Ollama + `qwen3.5:4b`.** When quality matters more than speed, swap it for `qwen3.5:9b` (6.6 GB). Swap the models; don't keep both, because 3.4 GB + 6.6 GB is more than the free disk. **At the fact-checker's 8.6 GiB reading, even the 9B alone would leave only about 1.5–1.8 GiB, below the 2–3 GB safety margin in §3.1, so free about 2 GB more before trying it.**

- **Why this model:** Apache-2.0 license [V S11]. Takes images natively, 256K context (262,144 tokens on the card) [V S10, S11]. "Expanded support to 201 languages and dialects" [V S11, S12]; the card gives no per-language list. On its model card the 4B scores OCRBench 85.0, OmniDocBench1.5 86.2 and CC-OCR 76.7, and the 9B scores 89.2 / 87.7 / 79.3 [V S11, S12]. The cards say Qwen3.5 thinks by default [V S11, S12] but do not say which mode the scores used; non-thinking quality is not stated [U].
- **Honest costs:**
  - **Slower:** about 1–4 minutes per full analyze call on this fanless Air [E, from S27: an M4 with a **10-core** GPU runs LLaMA-7B Q4_0 at about 24 tok/s output and about 221 tok/s prompt processing. The 8-core-GPU M4 row in S27 has no results, so this Air may be somewhat slower; the 4B model should be faster than a 7B].
  - **Weaker than `gemini-3.8-flash`** at reasoning and at writing in less common languages.
  - **Pashto:** not on Qwen3's official 119-language list, which does list Persian, Dari, Haitian and Vietnamese [V S14]. Whether Qwen3.5 handles Pashto is unverified [U].
  - **What these runs prove:** treat them as a privacy-safe test of the whole pipeline on real layouts, not as a quality benchmark. Have a native speaker check Dari, Pashto and Haitian Creole output.
- **Whose papers:** use only your own papers, or papers from someone who said yes. That holds even locally.

**A hosted second opinion (optional), best first:**

1. **Alibaba Model Studio International, Singapore region.**
   - **Quota:** "typically 1,000,000 tokens" free per model, valid 90 days from Model Studio activation, the model's release or your request's approval, whichever is later. Only Singapore-region models with the International deployment scope qualify [V S40]; the price list shows 1 million tokens for each of qwen3-vl-plus, qwen3-vl-flash, qwen-vl-ocr, qwen3.7-flash and qwen3.8-flash [V S41].
   - **Terms:** "Alibaba Cloud will not use your Member Content to develop or improve the models on Model Studio, unless you separately provide your consent" [V S44]. The same section says output must not be treated as "a substitute for, any professional, medical, legal ... advice" or used as "a basis for making any professional, medical, legal ... decisions" [V S44].
   - **Before you start:** turn on "Free Quota Only" (it is "disabled by default") so nothing is billed when the quota runs out [V S40]. Activate only when you are ready, because the countdown starts at activation and "is not paused by inactivity" [V S40].
   - **Limit:** JSON-schema mode does not work with images; it falls back to plain JSON mode [V S43].
   - **How many calls:** about 125–165 calls per model per 1M tokens [E: 6–8k tokens per call].
2. **Groq Free with `qwen/qwen3.8-27b`.**
   - **Terms:** the contract says no training on inputs or outputs [V S90]. Data is kept in US Google Cloud buckets, and Zero Data Retention (ZDR) can be switched on by any customer [V S89].
   - **Limits:** at most 3 images per request, each counted as 2,048 input tokens [V S87]. Free plan: 30 requests/min, 1,000/day, 8K tokens/min, 200K tokens/day [V S86]. That is about 28 calls/day [E: about 7K tokens per call].
   - **Status:** it is listed under "Preview Models", which "are intended for evaluation purposes only and should not be used in production environments" [V S107].
3. **Cerebras free trial.**
   - **Cost:** $5 of credit for 30 days, and you must add a payment method; "You will not be charged or automatically enrolled in paid usage" [V S91].
   - **Model:** Qwen 3.8 27B with images (2 per request on the free tier), `strict: true` structured outputs, 64K context on the trial, 5 requests/min, 1M tokens/day [V S92].
   - **Data:** "We do not retain inputs and outputs associated with our ... inference ... Services" [V S93].
4. **Cloudflare Workers AI.**
   - **Quota:** 10,000 Neurons/day free [V S94]. That buys about 13 calls/day on Qwen 3.8 27B or about 110/day on Gemma 4 26B [E: 4K tokens in, 2K out, using the per-model Neuron rates in S94].
   - **Data:** no training on your content without explicit consent [V S95].
   - **Limit:** "Workers AI can't guarantee that the model responds according to the requested JSON Schema", and neither Qwen 3.8 nor Gemma 4 is on its JSON-mode model list [V S108].

**Never send real papers to:**

- **Training or personal-data bans:**
  - Gemini free tier: trains on content, has human review, and says not to submit personal information [V S80].
  - Vertex Express mode: "Customer will not use the Express Mode Offerings to process personal data" [V S85].
  - NVIDIA build.nvidia.com: no personal data or protected health information (PHI), uses your content "to improve NVIDIA products", trial use only [V S100].
- **Only safe after changing settings:**
  - Mistral free mode, until you opt out: "we may use your data (input and output) to train" [V S98]. The opt-out is a toggle under Admin panel → Privacy [V S112]; the page does not say whether it covers free mode [U].
  - OpenRouter `:free`, unless you turn off training for free models (OpenRouter has "separate settings for paid and free models" [V S110]) and pin a no-training endpoint. Whether the ModelRun free endpoint trains or retains is not stated on any page fetched [U].
- **Mainland China storage, training clauses, or bans on health data:**
  - Zhipu bigmodel.cn: stored in China, and anonymised data may be used for "machine learning or model algorithm training" [V S57].
  - DeepSeek: stored in the PRC; its policy says the service is not designed for sensitive data including health, citizenship and immigration status, and inputs are used to "train and improve our technology" (an opt-out exists) [V S63].
  - Moonshot Kimi: "We may use Content to provide, maintain, develop, support, and improve the Services" unless you sign a separate enterprise agreement [V S65].
  - MiniMax: may use inputs to "provide, maintain, develop, and improve our Services", and bans HIPAA data [V S66].
  - StepFun: takes a perpetual, irrevocable licence to prompts, outputs and API call logs "for any purpose", including model training [V S68].
- **Other reasons:**
  - SiliconFlow: its terms ban use "for any commercial purposes" (clause 3.4(p)) [V S60].
  - Baidu Qianfan: individual real-name verification accepts only a mainland ID card, a PRC foreign permanent-residence card, a passport of a Chinese citizen settled abroad, or a Hong Kong/Macau/Taiwan travel permit [V S71]. The free-quota page does not say whether verification is needed to use it [U].

(The fact-checker re-fetched these official pages on 2026-10-01; marks were L/R before.)

### 1.4 (c) What production needs

- **The Gemini paid tier**, as designed today (D-01).
  - **Cost:** prepay is at least $5 and at most $5,000 [V S82] (the billing FAQ adds that the setup UI shows the minimum "required for your region and tier level" [V S82]). New billing accounts default to Prepay [V S82]. `gemini-3.8-flash` costs $0.75 in / $3.75 out per 1M tokens through 2026-12-31, and **$1.50 / $7.50 from 2027-01-01**. `gemini-3.5-flash-lite` costs $0.30 / $2.50 [V S81].
  - **How far $5 goes:** about 475 calls on 3.8 Flash or about 800 on 3.5 Flash-Lite [E: 4K tokens in and 2K out per call, before thinking tokens].
  - **Terms:** paid prompts are not used to improve Google's products, and Google keeps a safety log "for a limited period of time" [V S80].
- **Or Vertex AI (Gemini Enterprise Agent Platform).**
  - **Terms:** "Google won't use your data to train or fine-tune any AI/ML models without your prior permission or instruction" [V S84]. Abuse-monitoring prompt logging applies unless you get an exception [V S84].
  - **The $300 Google Cloud trial:** it cannot pay for the Gemini API in AI Studio ("starting March 2026, Gemini API usage costs are specifically excluded") [V S83, S82]. **It also does not make the Gemini API a Paid Service.** The billing page puts "Active project or free trial" in the Free tier and names "Free trial account" as a billing-account type that is ineligible for the Paid Tier until billing is activated [V S82]. So real papers stay forbidden on a trial-only project. The trial page's exclusion list names only the Gemini API in AI Studio and partner models offered as a service [V S83]; it does not say outright that Gemini on Vertex is covered [L]. Check this in the Billing console before relying on it.
- **A local open model in production** is technically possible. It would need a GPU server, a quality evaluation with native speakers, and a new DECISIONS entry. Not recommended for v1.
- **Not for production:**
  - any free tier;
  - Z.ai, whose terms forbid use "as a substitute for professional services, including ... medical care, legal services" and forbid HIPAA data [V S54];
  - Alibaba Model Studio, whose terms say output must not be "a basis for making any professional, medical, legal ... decisions" [V S44] (on top of the DOJ point below);
  - MiniMax, which bans HIPAA data [V S66];
  - any vendor with a PRC parent for US users' papers at scale (the DOJ rule, §1.5).

### 1.5 Privacy and jurisdiction, plainly

**Who trains on your content or has people read it**

| Service | Uses your content for training | Human review / logs | Source |
|---|---|---|---|
| Local Ollama / LM Studio | No: runs on your Mac | None ("Nothing you enter into LM Studio when chatting with LLMs leaves your device") | [V S4], [V S25] |
| Gemini free tier | Yes | "Human reviewers may read, annotate, and process" | [V S80] |
| Gemini paid / Vertex | No | Short abuse-monitoring log | [V S80, S84] |
| Alibaba Model Studio International | No, unless you consent ("will never use your data for model training", says the privacy notice) | Model Studio "stores data generated from model and application calls"; how long is not stated | [V S44, S48] |
| Z.ai (Singapore) | No for "enterprises and developers using API Services" unless you explicitly agree; "individual users" grant broader rights | Says API content is "not saved on our servers" | [V S54, S53] |
| Groq | No (contract) | Logs up to 30 days for system reliability and abuse monitoring unless ZDR is on | [V S89, S90] |
| Cerebras | Not stated | Does not retain inputs or outputs | [V S93] |
| Cloudflare Workers AI | No | Stored only if you use a Cloudflare storage product | [V S95] |
| Mistral free mode | Yes, until you opt out | ZDR "only with pay-as-you-go", on request [V S111] | [V S98] |
| NVIDIA build | Yes ("to improve NVIDIA products and services, including AI models") | Logged and shared with third parties for abuse monitoring | [V S100] |
| Azure OpenAI / Foundry (paid or credit-funded) | No ("NOT used to train any generative AI foundation models without your permission") | Abuse-monitoring store with human review unless modified monitoring is approved | [V S118] |
| DeepSeek, bigmodel.cn, Kimi, MiniMax, StepFun | Yes, or may (DeepSeek offers an opt-out) | Varies | [V S57, S63, S65, S66, S68] |

**PRC jurisdiction**

- **Data stored in mainland China:**
  - DeepSeek: "we directly collect, process and store your Personal Data in People's Republic of China" [V S63].
  - Zhipu bigmodel.cn stores personal information in China and does not transfer it abroad [V S57], may disclose it when government authorities' mandatory requirements say so [V S57], and its service agreement mentions disclosure to "state organs" [L/R S58].
  - The PRC Data Security Law, Art. 35, says that when a public security or national security organ needs data, "the relevant organizations and individuals shall cooperate" [V S72]. The National Intelligence Law, Art. 7, requires support for intelligence work [L S73].
- **Offshore subsidiaries of PRC groups:**
  - With a US billing address you contract with Alibaba Cloud US LLC, under Singapore law. Alibaba may disclose data for "lawful government requests" [V S47]. Content may be "transferred to, stored, and processed in the country where Alibaba Cloud, its affiliates, or its sub-contractors maintain facilities for Model Studio Service" [V S44]. For the Singapore region, static data is stored in Singapore and inference runs on "global nodes excluding Chinese mainland" [V S46].
  - Z.ai's operator is JINGSHENG HENGXING TECHNOLOGY PTE. LTD., a Singapore company [V S53, S54]. That it is a subsidiary of Beijing Zhipu Huazhang is [L/R]; Beijing Zhipu Huazhang Technology Co., Ltd. has been on the US Entity List since 2025-01-16 [V S55].
  - Whether PRC data and intelligence laws reach these subsidiaries is **not stated by any provider** [U].
- **Pentagon "1260H" list:** Alibaba and Baidu were added on 2026-06-08. That limits Defense Department contracting, not private use [L S50: law-firm alerts and press reports agree; no official DoD page was fetched].

**The DOJ Data Security Program (28 CFR Part 202)**

- **What it is:** in effect since 2025-04-08 [V S102]. It works like an export control that "prohibit[s] or restrict[s]" countries of concern from getting Americans' bulk "health, financial, or other sensitive personal data" [V S102].
- **Countries of concern:** China, Cuba, Iran, North Korea, Russia and Venezuela [V S102b: 28 CFR 202.601].
- **"Bulk" means more than** 10,000 US persons for personal health data (or personal financial data), 100,000 for covered personal identifiers, and 1,000 for biometric identifiers, at any point in the preceding 12 months [V S103]. **"Combined data"** (more than one category, or a listed identifier linked to health data) uses the lowest threshold among the categories present [V S103]. Facial images count as biometric identifiers only when "enrolled in a biometric system" [V S103b: 202.204]. Personal health data includes diagnoses, test results, immunizations, medications and payment for care [V S103c: 202.241].
- **Who is a "covered person":** a foreign entity that is 50% or more owned by a country of concern, is organized under its laws, or has its principal place of business there. Foreign entities 50% or more owned by such a company count too, and the Attorney General can designate others [V S104]. The regulation's own example treats a company "headquartered in China" as a covered person [V S104].
- **Vendor agreements** (which expressly include "cloud-computing services" [V S105b: 202.258]) with covered persons are "restricted": you may enter one only if you meet the CISA security requirements (CISA is the federal cybersecurity agency) [V S105]. A company organized solely under US law is a "U.S. person"; the rule's Example 8 says a US-organized subsidiary of a country-of-concern parent "is a U.S. person regardless of the degree of ownership by the parent company" [V S106].
- **What this means for ProxyHealth** [my reading, not legal advice]:
  - You testing your own papers is far below every bulk threshold, so this rule does not block option (b).
  - In production, sending US users' medical papers to a covered person could cross the 10,000-person health threshold within a year. Doing that lawfully needs counsel and the CISA controls. So: no production plans on Alibaba, Z.ai, DeepSeek, Moonshot, MiniMax, StepFun or Baidu.
  - Alibaba Cloud US LLC: if it is organized solely under US law (not verified [U]), Example 8 makes it a U.S. person unless designated [V S104, S106]. But Alibaba's terms let Model Studio content be processed by its affiliates wherever they "maintain facilities" [V S44], and the Singapore region's facilities belong to non-US affiliates of a PRC-headquartered group, which fits the covered-person test on its face [my reading of S104]. Whether that turns the arrangement into a restricted transaction is a question for counsel. Don't assume either answer.
  - Immigration papers also carry identity numbers (A-numbers, passport numbers), and a passport number linked to another listed identifier is a "covered personal identifier" [V S103d: 202.212]. Be careful with them either way.

**Two more traps**

- Ollama cloud model tags (named `:cloud` or `-cloud`, for example `gemma4:cloud`, `gemma4:31b-cloud`, `glm-5.3:cloud` [V S21, S4b]) send prompts to Ollama's servers. Ollama says it does "not store or log that content and never train[s] on it" [V S4], but the prompt still leaves the Mac. Never use them with real papers. (The `qwen3.5` and `qwen3-vl` tag lists show no cloud tags today [V S10, S15].)
- No provider here offers a HIPAA Business Associate Agreement (BAA) on its free tier [U]. COMPLIANCE_PRIVACY §13.1 says HIPAA does not attach to ProxyHealth today, but the Z.ai and MiniMax terms forbid HIPAA-regulated data anyway.

---

## 2. Comparison table

Verdicts: **good**, **ok**, **avoid**. "Own real" means the developer's own papers during testing. "Fits Mac" applies to local options only: 16 GB RAM and about 9 GiB of free disk. Each cell carries the mark of its weakest fact. Source numbers are in §7.

### 2.1 Local, open-weight (nothing leaves the Mac)

| Option | Models (size on disk) | Free quota | Vision | JSON / structured | API style | Data use / training | Data location | Fits this Mac | Synthetic | Own real | Production | Sources |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Ollama + Qwen3.5 (RECOMMENDED)** | `qwen3.5:4b` 3.4 GB; `qwen3.5:9b` 6.6 GB (`latest` = 9b); `2b` 2.7 GB; `0.8b` 1.0 GB [V] | Unlimited: Apache-2.0 weights; the only cost is the Mac's time [V S11] | Yes, Text+Image on every tag; 256K ctx [V] | JSON schema via native `format` or `/v1` `response_format` [V S6, S8]. Thinks by default [V S11]: send `think:false` [V S6] / `reasoning_effort:"none"` [V S7] | Native `/api/chat` + OpenAI-compatible `/v1/chat/completions`, base64 images only [V] | None: "We don't see your prompts or data when you run locally" [V S4] | On the Mac; only the weights are downloaded [L/R] | 4b: yes, about 5–6 GB RAM [E], about 4.7–5.0 GiB disk left from today's 8.6 GiB. 9b: about 8–9 GB RAM [E], but only about 1.5–1.8 GiB disk left at 8.6 GiB, which is below the §3.1 margin: free about 2 GB first, one model at a time | good | **good** | ok (needs a GPU host plus evals) | S4 S6 S7 S8 S10 S11 S12 |
| Ollama + Qwen3-VL-8B-Instruct | `qwen3-vl:8b-instruct` 6.1 GB; `4b-instruct` 3.3 GB. **Not** the bare `8b`/`latest`: same hash (`901cae732162`) as `8b-thinking` [V S15] | Unlimited, Apache-2.0 [V S17] | Yes; best published small-model document scores: DocVQA 96.1, OCRBench 896 [L/R S16; the fact-checker could not find these as text: the model card shows benchmarks only as images] | Same as above; the Instruct tag is a different build from the thinking one [V S15] | Same | None | On the Mac | Yes, but tight: KV cache about 144 KiB/token, about 9–10 GB RAM at 16k [E]; about 2.0–2.3 GiB disk left at 8.6 GiB (below the margin) | good | good | ok | S15 S16 S17 |
| Ollama + MiniCPM-V 4.5 (OpenBMB, China) | `minicpm-v4.5:8b` 6.1 GB, 40K ctx [V S18] | Unlimited, Apache-2.0 [L/R] | Yes, up to 1.8 MP images [V S18]; OCRBench 89.0 [L/R] | Generic `format`; no model-specific claim [U] | Same | None | On the Mac | Yes, one at a time | good | ok | ok | S18 S19 S20 |
| Ollama + Gemma 4 E4B (Google) | `gemma4:e4b-it-qat` 6.1 GB, 128K ctx, Text+Image [V S21] | Unlimited, Apache-2.0 [L/R] | Yes; OmniDocBench edit distance 0.181 [L/R] | Yes; the Ollama vision+schema doc example uses `gemma4` [V S8]. Thinking is off by default [L/R] | Same | None | On the Mac | Yes, one at a time | good | ok | ok | S8 S21 S22 |
| LM Studio (MLX/GGUF) | e.g. `Qwen3.5-4B-MLX-4bit` 3.06 GB; app DMG 570 MB [L/R] | Unlimited [L/R] | Chat Completions takes "text and images" [L/R] | `json_schema` strict; docs warn "Not all models are capable of structured output, particularly LLMs below 7B parameters" [V S24] | OpenAI-compatible at `localhost:1234/v1` [L/R] | "Nothing you enter into LM Studio when chatting with LLMs leaves your device"; model search, downloads and update checks still go online [V S25] | On the Mac | Fits, but costs about 0.4 GB more disk than Ollama | ok | ok | avoid (proprietary freeware app) | S23 S24 S25 S26 |
| Poor fits (do not pull) | GLM-OCR (OCR only, no Arabic/Persian), DeepSeek-OCR (6.7 GB, 8K ctx, OCR only), Llama 3.2 Vision 11B (images English-only, 7.8 GB), Granite Vision (English only), Moondream (2K ctx), Qwen2.5-VL-3B (non-commercial license), Gemma 3 4B (DocVQA 75.8), Ministral 3 (no fa/ps/vi), InternVL3.5 (community tag only) [L/R] | — | — | — | — | — | — | Some fit; none is worth the disk | avoid | avoid | avoid | S28–S36 |

### 2.2 Hosted by Chinese companies

| Option | Models | Free quota | Vision | JSON / structured | API style | Data use / training | Data location | Fits this Mac | Synthetic | Own real | Production | Sources |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Alibaba Cloud Model Studio International (Singapore)** | qwen3-vl-flash, qwen3-vl-plus, qwen-vl-ocr, qwen3.7-flash, qwen3.8-flash and others, each with a 1M-token free quota [V S41] | "Typically" 1M tokens **per model**, 90 days from activation (or model release / approval, whichever is later), Singapore + International scope only; "Free Quota Only" switch, off by default [V] | Yes, base64 images: original file ≤20 MB for Qwen3.5–3.8 and Qwen3-VL, data URI ≤20 MB [V S42] | `json_object` on vision (the prompt must contain "JSON"); `json_schema` only on Qwen3.7-Plus/Flash/Max and Qwen3.8-Max/Flash **text** input. Multimodal inputs "will automatically fall back to `json_object`" [V S43] | OpenAI-compatible `https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1`, or the DashScope endpoint `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` [V S46] | "will not use your Member Content to develop or improve the models ... unless you separately provide your consent" [V S44] | Singapore storage; inference on "global nodes excluding Chinese mainland" [V S46]; content may be processed wherever Alibaba or its affiliates "maintain facilities" [V S44]. PRC-headquartered parent | n/a | good | ok (only after reading §1.5) | avoid (DOJ rule, §1.5; terms also say output is not a basis for medical or legal decisions [V S44]) | S40–S49 |
| Z.ai (Zhipu international) | glm-4.6v-flash (vision, free), glm-4.7-flash / glm-4.5-flash (text, free) [V S51] | Listed as "Free"; no quota or rate limit published [V S51] | Yes (GLM-4.6V-Flash; images under 5 MB, jpg/png, ≤6000×6000 px) [V S52] | `response_format`: "Only text models support this field" (`text` or `json_object`): vision output must be validated by hand [V S52] | OpenAI-compatible `https://api.z.ai/api/paas/v4/chat/completions` [V S52] | API users: no training unless you "explicitly agree" [V S54]. API content "is not saved on our servers" [V S53] | "Generally processed in Singapore" [V S53]. Parent on the US Entity List [V S55; parent link L/R] | n/a | good | ok | **avoid**: terms ban medical/legal-substitute use and HIPAA data [V S54] | S51–S55 |
| Zhipu bigmodel.cn (mainland) | GLM-4.6V-Flash, GLM-4.1V-Thinking-Flash (free) [L/R] | Free, no quota published [L/R] | Yes [L/R] | json_object on text models [L/R] | OpenAI-style [L/R] | Anonymised data may be used for model training [V S57] | Mainland China, no cross-border transfer; disclosure on mandatory government request [V S57]; "state organs" wording [L/R S58] | n/a | ok | avoid | avoid | S56–S58 |
| SiliconFlow (.com) | Qwen3-VL-8B/32B (paid) [L] | $1 free credit [V S59]; no free vision models shown on the pricing page [V S59] | Yes [L/R] | json_object [L/R] | OpenAI-compatible [L/R] | Terms: "We will not access your Interaction Data" except as law, product rules or your troubleshooting request require; no explicit training clause [V S60] | Not stated [U]; Singapore law (SILICONFLOW LABS PTE. LTD.) [V S60] | n/a | ok | ok | avoid (terms: no use "for any commercial purposes") [V S60] | S59–S61 |
| DeepSeek | deepseek-flash (the only vision model; deepseek-v4-pro has none) [V S62] | No free credit mentioned [V S62] | Yes [V S62] | JSON output [V S62] | OpenAI-format [L/R] | Used "to train and improve our technology", with an opt-out [V S63] | PRC [V S63] | n/a | ok | avoid | avoid | S62 S63 |
| Moonshot Kimi | kimi-k3, k2.6 [L/R] | None; "recharge at least $1 to start"; a $5 voucher after $5 cumulative top-ups [V S64] | Yes [L/R] | json_schema [L/R] | OpenAI-compatible [L/R] | "We may use Content to ... improve the Services" unless a separate enterprise agreement says otherwise [V S65] | Singapore law (Moonshot AI Pte. Ltd.); storage location not stated in the terms [V S65 / U] | n/a | ok | avoid | avoid | S64 S65 |
| MiniMax | MiniMax-M3 [L/R] | No new-user credit stated [L/R] | Yes [L/R] | Not stated [U] | OpenAI-compatible [L/R] | May use input and generated content to "improve our Services" [V S66] | "Data center located in the United States" [V S67]; Singapore law; bans HIPAA data [V S66] | n/a | ok | avoid | avoid | S66 S67 |
| StepFun | step-1o-turbo-vision [L/R] | Only occasional "Trial Credits" [L/R] | Yes [L/R] | Not stated [U] | OpenAI-compatible [L/R] | Perpetual, irrevocable licence to prompts, outputs and API logs "for any purpose", including training [V S68] | Hong Kong law (STEPFUN TECHNOLOGY (HK) LIMITED); storage not stated [V S68] | n/a | ok | avoid | avoid | S68 S69 |
| Baidu Qianfan | ERNIE-4.5-Turbo-VL among 17 free-quota models [V S70] | 1M tokens per model for 3 months [V S70] | Yes [L/R] | Not stated [U] | Not verified [U] | Not verified [U] | Mainland [L/R] | n/a | avoid (individual real-name verification accepts only PRC-issued IDs, a PRC permanent-residence card, an overseas-Chinese passport or HK/Macau/Taiwan permits [V S71]) | avoid | avoid | S70 S71 |

### 2.3 Hosted by US and EU companies

| Option | Models | Free quota | Vision | JSON / structured | API style | Data use / training | Data location | Fits this Mac | Synthetic | Own real | Production | Sources |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemini API free tier (today's `unpaid`) | gemini-3.8-flash, gemini-3.5-flash-lite [V] | "Free of charge"; limits shown only in AI Studio [V], [L/R] | Yes, plus native PDF [L/R] | JSON schema (already used) | google-genai (already built) | **Trains**; human reviewers; "Do not submit ... personal information" [V] | Google, US | n/a | **good** | avoid | avoid | S80 S81 |
| Gemini API paid via $5 prepay | Same [V] | Not free: $5 minimum [V] | Yes | JSON schema | No code change | Not used to improve products; limited safety log [V] | Google, US | n/a | good | **good** | **good** | S80 S81 S82 |
| Vertex AI on the $300 Google Cloud trial | Gemini on Vertex [L] | $300 for 90 days, "No automatic charges"; card needed [V]. The trial's exclusions name only the Gemini API in AI Studio and partner models-as-a-service, so Vertex Gemini is likely covered, but not stated [L] | Yes | JSON schema | google-genai with `vertexai=True` (new auth path) | Training restriction [V]; abuse logging unless exempted [V] | Google Cloud regions | n/a | good | good | ok | S83 S84 |
| Vertex Express mode | Gemini 2.5/3 previews [L] | Free 90 days, no card [L] | Yes | JSON schema | API key | "Customer will not use the Express Mode Offerings to process personal data or other data subject to legal or regulatory compliance requirements" [V] | Google | n/a | good | avoid | avoid | S85 |
| Groq Free | `qwen/qwen3.8-27b` (the only vision model) [V] | 30 RPM, 1K RPD, 8K TPM, 200K TPD [V]; about 28 calls/day [E] | Yes; at most 3 images; each counts as 2,048 tokens [V] | `json_schema` + `strict:true` on this model; no streaming or tools with it [V]. JSON object mode with images is documented [V S87]; images + strict together: not stated [U] | OpenAI-compatible | No training (contract) [V]; logs up to 30 days unless ZDR [V] | US (GCP) [V] | n/a | good | **good** (with ZDR on) | avoid (Preview model "should not be used in production" [V S107]; free limits) | S86–S90 S107 |
| Cerebras free trial | Qwen 3.8 27B (`qwen-3.8-27b`) [V] | $5 for 30 days; payment method required; no automatic paid enrolment [V]. 5 RPM, 1M tokens/day, 64K ctx (128K paid) [V] | Yes; base64 PNG/JPEG data URIs only, 2 images on the free tier [V] | `strict: true` structured outputs [V] | OpenAI-compatible | Does not retain inputs or outputs [V]; training not stated [U] | Not stated [U] | n/a | good | good | ok (paid later) | S91–S93 |
| Cloudflare Workers AI | `@cf/qwen/qwen3.8-27b`, `@cf/google/gemma-4-26b-a4b-it`, llama-4-scout, llama-3.2-11b-vision [V] | 10,000 Neurons/day on Free and Paid plans [V]; about 13 calls/day (Qwen) or about 110 (Gemma 4) [E, recomputed from the per-model Neuron rates in S94] | Yes [L/R] | `response_format` json_schema exists, but "Workers AI can't guarantee" compliance; Qwen 3.8 and Gemma 4 are not on the JSON-mode model list [V S108] | OpenAI-compatible `/ai/v1` + Workers binding [L/R] | No training, no improvement use [V] | Not stated [U] | n/a | good | good | ok | S94 S95 S108 |
| OpenRouter `:free` | `qwen/qwen3.8-27b:free` (ModelRun, fp4, 262K ctx), Gemma 4 free, others [V] | 20 RPM; 50 req/day, or 1,000/day after $10 in purchases [V] | Yes (text/image/video on the Qwen free model) [V] | `structured_outputs` on the ModelRun endpoint [V] | OpenAI-compatible | Varies by upstream. ModelRun's training/retention policy: not found on any page fetched [U]. `provider.data_collection:"deny"` = "use only providers which do not collect user data"; `zdr:true` = ZDR endpoints only [V S109]; separate account training settings for free models [V S110] | US router; upstream varies | n/a | good | ok (only when configured) | avoid | S96 S97 S109 S110 |
| Mistral free mode | mistral-small (vision), mistral-ocr [L] | Free; limits shown only in the Admin panel, not published [V S113] | Yes [L] | json_schema strict [L] | Mistral REST (OpenAI-like) | **Trains** until you opt out [V S98]; opt out under Admin → Privacy [V S112]; ZDR "only with pay-as-you-go", by request [V S111] | EU [L] | n/a | good | ok (after opting out) | avoid | S98 S111–S113 |
| Hugging Face Inference Providers | Routed VLMs | $0.10/month for free users, "subject to change" [V] | Depends on provider | Depends | OpenAI-compatible router | HF stores no bodies; the provider's policy applies [L] | Varies | n/a | ok | ok | ok | S99 |
| NVIDIA build.nvidia.com | Many | Trial [L] | Yes | Varies | OpenAI-compatible | Uses "User Content and Generated Content to improve NVIDIA products ... including AI models"; no personal data or PHI; no production use [V] | US | n/a | ok | avoid | avoid | S100 |
| GitHub Models | — | **Retired 2026-07-30** [V] | — | — | — | — | — | n/a | avoid | avoid | avoid | S101 |
| Azure free / Azure for Students | Azure OpenAI / Foundry models | $200 for 30 days (card for identity check), or Azure for Students: $100 within 12 months, "No credit card required" [V S116, S117] | — | — | — | Prompts and completions "are NOT used to train any generative AI foundation models without your permission"; "NOT available to OpenAI"; abuse-monitoring human review unless modified monitoring is approved [V S118] | Customer-chosen Azure geography (Global/DataZone deployments may process elsewhere) [V S118] | n/a | ok | ok [U: quota] | ok | Whether trial or student subscriptions get any Azure OpenAI model quota is not stated on the offer pages [U]; an unofficial Q&A says it is 0 or restricted. Worth one check, since the developer is a student |

Also considered: SambaNova free tier ("RPM: 20, RPD: 20, TPD: 200000", text models only: no vision model on the free tier) [V S114], and Together AI ("does not currently offer free trials"; "minimum $5 credit purchase") [V S115]. Neither is worth pursuing for this purpose.

---

## 3. Local setup guide: Ollama + Qwen3.5-4B on this Mac (16 GB M4, about 8.6 GiB free)

**Do not start until the developer says yes (§6).** The install needs your admin password, which you type yourself; an agent must never type it. Per CLAUDE.md rule 1, nobody else should be installing anything at the same time.

### 3.1 Disk budget

| Step | Disk used | Free afterwards (start: 8.6 GiB at fact-check; 9.3–10.1 GiB earlier the same day) |
|---|---|---|
| Download `Ollama.dmg` (v0.35.0, 199,580,406 bytes, released 2026-09-28) [V S2] | +0.2 GB | about 8.4 (8.4–9.9) |
| Install `Ollama.app`, then delete the `.dmg` | Installed size not stated [U]; the zip is 198,866,136 bytes [V S2], so about +0.2–0.5 GB [E] | about 8.1–8.4 (up to 9.7) |
| `ollama pull qwen3.5:4b` [V S10] | +3.4 GB | **about 4.7–5.0** (up to 6.3) |
| (Instead of the 4B) `ollama pull qwen3.5:9b` [V S10] | +6.6 GB | about 1.5–1.8 at today's 8.6 GiB start: **below the 2–3 GB margin; free disk first** (up to 3.1) |

Sizes here are subtracted as if Ollama's "GB" were GiB, which slightly overstates disk use (by about 7% if Ollama means decimal GB, which its pages do not say [U]).

Rules that keep you within disk:

- **One model at a time.** To try the 9B: `ollama rm qwen3.5:4b && ollama pull qwen3.5:9b`. To try Qwen3-VL: `ollama rm qwen3.5:9b && ollama pull qwen3-vl:8b-instruct` (6.1 GB) [V S15]. Never pull the bare `qwen3-vl:8b` or `qwen3-vl:latest`: they point to the slower Thinking variant (same hash `901cae732162` as `8b-thinking`) [V S15]. Note that `qwen3.5:latest` is the 9B (6.6 GB) [V S10], so always type the size tag.
- Keep **at least 2–3 GB free** for macOS swap and updates. Never pull `-mlx` (the 9b-mlx is 8.9 GB) [V S10], `q8_0` or `bf16` tags here.
- Models live in `~/.ollama/models` [V S3, S4]. Check with `du -sh ~/.ollama` and `ollama list`. `OLLAMA_MODELS` can point the store at an external drive [V S4].
- **Never use cloud tags** (`:cloud` or `-cloud`, for example `gemma4:cloud` or `gemma4:31b-cloud`). They send prompts to Ollama's servers [V S4, S21].

### 3.2 Install (no Homebrew)

```bash
# 0) Check free space first (want ≥ 6 GiB before the model pull)
df -h /System/Volumes/Data

# 1) Download (official link from https://ollama.com/download/mac; needs macOS 14+) [V S1]
curl -L -o ~/Downloads/Ollama.dmg https://ollama.com/download/Ollama.dmg
#    pinned alternative: https://github.com/ollama/ollama/releases/download/v0.35.0/Ollama.dmg  [V S2]
ls -lh ~/Downloads/Ollama.dmg        # expect about 200 MB

# 2) Install: open, drag Ollama into Applications, eject, then reclaim the space
open ~/Downloads/Ollama.dmg
#    (drag Ollama.app to /Applications in the Finder window, then eject the disk image)
rm ~/Downloads/Ollama.dmg
```

3. Launch **Ollama** from `/Applications`. On first launch it "will prompt for permission to create a link in `/usr/local/bin`" [V S3]. Accept. If macOS asks for your admin password (S3 does not say it will [U], but `/usr/local/bin` usually needs it), **type it yourself**.
4. Check that it works:

```bash
ollama --version                                   # expect 0.35.0
curl -s http://localhost:11434/v1/models | jq .    # OpenAI-compatible endpoint is up [V S7]
```

(Also on the official page: `curl -fsSL https://ollama.com/install.sh | sh` [V S1]. Prefer the DMG so you can see what is being installed.)

### 3.3 Settings before the first real call

Ollama's default context is **4k tokens on machines with under 24 GiB of VRAM** [V S5] (on Apple Silicon that is the shared unified memory [L]). ProxyHealth's analyze prompt files alone are about 10 KB, before the image and the schema, so without this change document prompts are silently cut short.

```bash
launchctl setenv OLLAMA_CONTEXT_LENGTH 16384   # 32768 for multi-page tests
launchctl setenv OLLAMA_FLASH_ATTENTION 1      # memory saver
launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0     # halves KV-cache memory vs f16 default
launchctl setenv OLLAMA_KEEP_ALIVE 10m         # keep the model loaded between test calls
# then Quit Ollama from the menu-bar icon and open it again
```

- Variable names, `launchctl setenv`, "restart the app", and `q8_0` using "approximately 1/2 the memory of `f16`" all come from the FAQ [V S4]. Context length and the Settings-slider alternative come from S5 [V].
- Values set with `launchctl setenv` are lost on reboot [L]. Re-run them, or set context with the app's Settings slider.
- **The OpenAI-compatible endpoint cannot set `num_ctx` per request** [V S7]. That is why the global setting matters for the provider in §4.
- Leave `OLLAMA_HOST` alone. "Ollama binds 127.0.0.1 port 11434 by default" [V S4]. The phone talks to the ProxyHealth API, never to Ollama.

### 3.4 Pull the model

```bash
ollama pull qwen3.5:4b        # 3.4 GB, Text+Image, 256K ctx  [V S10]
ollama list
du -sh ~/.ollama
```

### 3.5 Server URLs

| API | URL | Notes |
|---|---|---|
| Native | `http://127.0.0.1:11434/api/chat` | `images: [base64]`, `format: <JSON schema>`, `think`, `options.num_ctx`, `keep_alive`, `stream` [V S6] |
| OpenAI-compatible | `http://localhost:11434/v1/chat/completions` | API key required but ignored; base64 images only, no image URLs; `response_format`; `reasoning_effort` [V S7, S8] |

### 3.6 Smoke test A: OpenAI-compatible endpoint with a base64 image and a JSON schema

This uses a **synthetic** repo fixture: a made-up USCIS receipt notice. `jq` 1.7.1 ships with macOS at `/usr/bin/jq`. The text part comes before the image, as D-04 requires.

```bash
cd ~/Desktop/ProxyHealth
IMG=apps/api/data/fixtures/uscis_i797c_receipt_i765/page-1.png
base64 -i "$IMG" -o "$TMPDIR/page.b64"

jq -n --rawfile b64 "$TMPDIR/page.b64" '{
  model: "qwen3.5:4b",
  reasoning_effort: "none",
  temperature: 0,
  max_tokens: 800,
  stream: false,
  messages: [
    {role: "system", content: "You read photographed letters. Reply with JSON only."},
    {role: "user", content: [
      {type: "text", text: "Who sent this letter, what is it about, and which dates are printed on it? Copy each date exactly as printed."},
      {type: "image_url", image_url: {url: ("data:image/png;base64," + ($b64 | rtrimstr("\n")))}}
    ]}
  ],
  response_format: {type: "json_schema", json_schema: {name: "smoke", strict: true, schema: {
    type: "object",
    properties: {
      sender: {type: "string"},
      topic: {type: "string"},
      dates_verbatim: {type: "array", items: {type: "string"}}
    },
    required: ["sender", "topic", "dates_verbatim"],
    additionalProperties: false
  }}}
}' > "$TMPDIR/req-openai.json"

time curl -s http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer ollama" \
  -d @"$TMPDIR/req-openai.json" | tee "$TMPDIR/resp-openai.json" \
  | jq -r '.choices[0].message.content' | jq .
```

**It passes if** the output is valid JSON with these three keys, `sender` names U.S. Citizenship and Immigration Services, and `dates_verbatim` holds `08/17/2026` and `08/24/2026` (see that fixture's `transcript.txt`).

### 3.7 Smoke test B: native `/api/chat` with Ollama structured outputs

```bash
jq -n --rawfile b64 "$TMPDIR/page.b64" '{
  model: "qwen3.5:4b",
  stream: false,
  think: false,
  keep_alive: "10m",
  options: {num_ctx: 16384, temperature: 0},
  messages: [
    {role: "system", content: "You read photographed letters. Reply with JSON only."},
    {role: "user",
     content: "Who sent this letter, what is it about, and which dates are printed on it? Copy each date exactly as printed. Answer the topic in Spanish.",
     images: [($b64 | rtrimstr("\n"))]}
  ],
  format: {type: "object",
           properties: {sender: {type: "string"}, topic: {type: "string"},
                        dates_verbatim: {type: "array", items: {type: "string"}}},
           required: ["sender", "topic", "dates_verbatim"]}
}' > "$TMPDIR/req-native.json"

time curl -s http://127.0.0.1:11434/api/chat -d @"$TMPDIR/req-native.json" \
  | tee "$TMPDIR/resp-native.json" | jq -r '.message.content' | jq .

# speed on this Mac (field names per the native API response; eval_duration is in nanoseconds) [V S6]
jq '{prompt_tokens: .prompt_eval_count, output_tokens: .eval_count,
     output_tok_per_s: (.eval_count / (.eval_duration / 1e9))}' "$TMPDIR/resp-native.json"
ollama ps    # CONTEXT should read 16384; PROCESSOR should be GPU
```

Clean up the scratch files with `rm "$TMPDIR"/req-*.json "$TMPDIR"/resp-*.json "$TMPDIR/page.b64"`.

**What to write down from the smoke tests:** whether both calls return valid JSON, the output speed in tokens per second, and the wall-clock time. These numbers replace the [E] speed estimates in this document. Only after both pass on the synthetic fixture should you try one of **your own** papers. Repeat test B with your own photo in place of `$IMG`.

---

## 4. Integration plan for ProxyHealth: an `openai_compat` provider (no code yet)

**Goal.** One new provider that implements the existing `AIProvider` protocol (`apps/api/proxyhealth_api/ai/provider.py`) and talks to any OpenAI-compatible `/chat/completions` endpoint: Ollama, LM Studio, Alibaba DashScope International, Z.ai, SiliconFlow, OpenRouter, Groq, Cerebras, Mistral, Cloudflare. (GitHub Models is retired [V S101].)

It is built with `httpx`, which is already in the venv. No `openai` SDK and no new packages (CLAUDE.md rule 1). `AI_PROVIDER=mock` stays the default (rule 6).

### 4.1 Files and owners (BUILD_PLAN ownership; WP0 owns shared contract files)

| Change | File | Owner |
|---|---|---|
| New provider + stack builder | `apps/api/proxyhealth_api/ai/openai_compat.py` (new) | AI-provider work package |
| Wire into `build_provider()` | `apps/api/proxyhealth_api/main.py` | same |
| New settings + boot rules | `apps/api/proxyhealth_api/settings.py`, `apps/api/.env.example` | same |
| `Provider.openai_compat`, `DataUseTier.local` / `.attested` | `apps/api/proxyhealth_api/contracts/enums.py`, `docs/API_CONTRACT.md` §1, regenerated `apps/mobile/src/api/schema.d.ts` | **WP0** (contract change; adding enum values breaks strict clients, so bump `CONTRACT_VERSION`) |
| New consent / banner strings (§5) | `apps/api/data/langpacks/en.json`, `docs/COMPLIANCE_PRIVACY.md` §3, §4, §17 | **WP0** + WP8 review |
| Badge + consent line selection per tier | `apps/mobile/src/features/onboarding/*`, `TierBadge` | mobile work package |
| Decision record | `docs/DECISIONS.md` (new D-xx: "openai_compat provider and the local tier") | lead |
| Live tests | `apps/api/scripts/spike_schema.py`, `apps/api/scripts/eval_golden.py` gain `--provider openai_compat` | AI-provider work package |

### 4.2 Settings and environment variables

The required variables, as specified:

```dotenv
AI_PROVIDER=openai_compat                       # mock | gemini | openai_compat
OPENAI_COMPAT_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_COMPAT_API_KEY=ollama                    # SecretStr; ignored by Ollama, required by hosted endpoints
OPENAI_COMPAT_MODEL_PRO=qwen3.5:4b
OPENAI_COMPAT_MODEL_FAST=qwen3.5:4b             # same model locally: two models would double RAM and disk
OPENAI_COMPAT_DATA_TIER=local                   # local | attested | unpaid   (default: unpaid)
```

Proposed optional variables, with defaults:

```dotenv
OPENAI_COMPAT_MODEL_LABEL=Qwen                  # shown in consent copy as {model} (§5); required for local
OPENAI_COMPAT_VENDOR_NAME=                      # shown as {vendor}; required for attested and unpaid
OPENAI_COMPAT_JSON_MODE=auto                    # auto | json_schema | json_object | prompt
OPENAI_COMPAT_REASONING=none                    # none | mapped  (mapped: ThinkingLevel → reasoning_effort)
OPENAI_COMPAT_TIMEOUT_S=300                     # default 300 for loopback hosts, 90 otherwise
OPENAI_COMPAT_MAX_OUTPUT_TOKENS=6144            # cap on top of AI_PROMPTS §3 (16384 is too slow locally)
OPENAI_COMPAT_MAX_IMAGES=12                     # Groq free: 3; Cerebras free: 2 [V S87, S92]
OPENAI_COMPAT_CONCURRENCY=1                     # loopback default 1 (16 GB RAM); hosted default 4
```

Boot rules for `Settings._runtime_rules` and `validate_runtime()`:

1. **`local` requires a loopback host.** That means `127.0.0.0/8`, `::1` or `localhost` in `OPENAI_COMPAT_BASE_URL`; anything else is a boot error. This check is what makes the §5 sentence "runs on our server" literally true.
2. **`attested` only in `ENV=development`.** It also needs `OPENAI_COMPAT_VENDOR_NAME`. It is refused for these hosts: `*.cn`, `api.deepseek.com`, `open.bigmodel.cn`, `*.moonshot.*`, `*.kimi.ai`, `*.minimax.io`, `*.stepfun.ai`, `integrate.api.nvidia.com`, and `generativelanguage.googleapis.com` (the Gemini free tier must go through `AI_PROVIDER=gemini` with `billing:false`). These hosts either store data in mainland China, train by default, or ban personal data (§1.5).
3. **`unpaid`** behaves exactly like today's Gemini `unpaid`: real papers get a 403; samples are allowed. `ALLOW_UNPAID_REAL_DOCUMENTS` keeps working as the dev-only bypass.
4. **`ENV=production` refuses `AI_PROVIDER=openai_compat`** until a DECISIONS entry approves a named deployment.
5. **`FAILOVER_DEADLINE_S` must be at least `OPENAI_COMPAT_TIMEOUT_S + 10`.** Today it is 100 s, which a 300 s local call would break.
6. **Gemini-only validators stay Gemini-only.** That covers `FORBIDDEN_MODEL_RE`, the paid-only model check and `GEMINI_KEYS` distinctness. `route()` must take its model ids from the active provider (new `Settings.active_model_pro/fast`), not from `MODEL_PRO`/`MODEL_FAST`; otherwise logs report the wrong model.
7. **`Settings.data_use_tier` returns the configured `OPENAI_COMPAT_DATA_TIER`.** `real_documents_allowed` becomes `tier in {paid, local}`, plus `attested` in development, plus the existing dev bypass. `KeyPool.data_use_tier()` must not recompute the tier from billing flags for this provider.

### 4.3 Request mapping

`POST {OPENAI_COMPAT_BASE_URL}/chat/completions`, `Authorization: Bearer <key>`, `stream: false`:

```jsonc
{
  "model": "<OPENAI_COMPAT_MODEL_PRO or _FAST by tier>",
  "messages": [
    {"role": "system", "content": "<system> + (schema text when JSON mode is not json_schema)"},
    {"role": "user", "content": [
      {"type": "text", "text": "<every text Part, in order>"},            // text before media (D-04)
      {"type": "image_url", "image_url": {"url": "data:image/png;base64,<...>"}}   // every bytes Part
    ]}
  ],
  "response_format": { /* §4.4 */ },
  "max_tokens": "min(max_output_tokens, OPENAI_COMPAT_MAX_OUTPUT_TOKENS)",
  "temperature": 0,
  "reasoning_effort": "none"          // only where the endpoint accepts it (Ollama: yes [V S7])
}
```

- **Images:** always base64 data URLs. Ollama refuses image URLs on `/v1` [V S7], and some endpoints take base64 only (Cerebras: "base64-encoded PNG or JPEG data URIs" [V S92]; Kimi was reported as base64-only, but S64 does not say so [U]). Images are already redacted and size-capped by `analysis/uploads.py` and `redaction.py` before any model call; that stays as it is. For local models, add a downscale step to at most 1,600 px on the long edge to bound image tokens and latency [E]. Alibaba's own default cap for Qwen3.5–3.8 and Qwen3-VL is about 1,600 × 1,600 px (`max_pixels` default 2,621,440; 32×32 pixels per token) [V S42].
- **`media_resolution`** is Gemini-only. Ignore it, except to send `detail: "high"` where the endpoint documents it (SiliconFlow [L/R]).
- **`temperature: 0`** follows Ollama's structured-output advice [V S8]. This is a deliberate, provider-specific exception to D-04's "no sampling knobs" for Gemini. Record it in the D-xx entry.
- **`max_tokens` vs `max_completion_tokens`:** send `max_tokens`. Ollama lists it as supported [V S7] and the OpenRouter ModelRun endpoint lists it [V S97]; the other endpoints are [U]: verify in the spike.

### 4.4 Structured-output strategy by endpoint

`OPENAI_COMPAT_JSON_MODE=auto` picks the mode from a host-pattern capability table, and the variable overrides it. **Every** mode then goes through the same safety net:

1. Strip any `<think>…</think>` block and any ```` ```json ```` fences.
2. Validate with `schema.model_validate_json` (Pydantic v2).
3. If validation fails, make **one repair retry** inside the same deadline. Append the model's raw reply as an assistant turn, then a user turn: "Your JSON did not match the schema. Problems: `<loc>`: `<error type>` … Return only the corrected JSON." The retry carries Pydantic `loc`/`type` only, never input values.
4. If it still fails, return `StructuredResult(parsed=None, incomplete=True)`. The existing `SchemaFallbackNeeded` / `two_call` path takes over (AI_PROMPTS §9.4).

| Endpoint | Image + schema | Text-only tasks | Notes |
|---|---|---|---|
| Ollama `/v1` | `response_format: {type: "json_schema", json_schema: {name, schema, strict: true}}`: S8 says structured outputs "work through the OpenAI-compatible API via `response_format`" [V S8]; the exact `json_schema` envelope is not shown on S7 or S8 [U] | same | Set context globally (§3.3). "Ollama's Cloud currently does not support structured outputs" [V S8]. Support for `$ref`/`anyOf` in its grammar is not documented [U], so send a flattened schema. |
| LM Studio | `json_schema` strict [V S24] | same | "Not all models are capable of structured output, particularly LLMs below 7B parameters" [V S24]. |
| Alibaba DashScope International | `json_object` only: multimodal inputs "will automatically fall back to `json_object`". The prompt **must** contain the word "JSON" [V S43] | `json_schema` on Qwen3.7-Plus/Flash/Max and Qwen3.8-Max/Flash [V S43] | Put the schema text in the system prompt for image calls. |
| Z.ai | **prompt-only** ("Only text models support this field") [V S52] | `json_object` [V S52] | Option: two calls, with GLM-4.6V-Flash transcribing and GLM-4.7-Flash writing JSON. |
| SiliconFlow | `json_object` [L/R S61] | `json_object` | No `json_schema` documented. |
| OpenRouter | `json_schema` when the endpoint lists `structured_outputs` (the ModelRun Qwen free endpoint does [V S97]); also send `provider.require_parameters: true` ("only use providers that support all parameters in your request") [V S109] | same | Pin the endpoint (`provider.only` / `order`); send `provider.data_collection: "deny"` [V S109]. |
| Groq | `json_schema` + `strict: true` on `qwen/qwen3.8-27b` [V S88] | same | "Streaming and tool use are not currently supported with Structured Outputs" [V S88]. Images + strict together: not stated [U], so fall back to `json_object`, which the vision page documents with images [V S87]. |
| Cerebras | `strict: true` structured outputs [V S92] | same | Free tier: 2 images per request [V S92]. |
| Mistral | `json_schema` strict [L] | same | — |
| Cloudflare | `json_schema`, not guaranteed [V S108] | same | On a "JSON Mode couldn't be met" error [V S108], retry once with `prompt` mode [E]. |

**Schema transform (one helper used by every mode):**

- Inline the `$defs`/`$ref` references.
- Keep `X | None` as `anyOf [X, null]`. `schema_guard.py` already restricts unions to that shape and nesting to depth 3.
- For `strict: true` endpoints, add `additionalProperties: false` and list every property in `required`. OpenAI-style strict mode needs that, and Pydantic leaves optional fields out of `required` [L].

Run this through `spike_schema.py --provider openai_compat` against every fixture **before** building the pipeline glue. That is the riskiest assumption here.

### 4.5 Model tiers and thinking

| Setting | Local (Ollama) | Alibaba International | Groq | Cerebras |
|---|---|---|---|---|
| `OPENAI_COMPAT_MODEL_PRO` | `qwen3.5:4b` (or `qwen3.5:9b`) | `qwen3-vl-plus` [V S41] | `qwen/qwen3.8-27b` [V S87] | `qwen-3.8-27b` [V S92] |
| `OPENAI_COMPAT_MODEL_FAST` | same as PRO | `qwen3.8-flash` or `qwen3.7-flash` (text; both take `json_schema` [V S43]) or `qwen3-vl-flash` [V S41] | same | same |

- **Degraded path:** when PRO equals FAST, the D-07 degraded path has nothing to fall back to. Treat `allow_degraded` as false for this provider.
- **Thinking:** with `OPENAI_COMPAT_REASONING=none` (the default) every call sends `reasoning_effort: "none"`. Qwen3.5 thinks by default, and thinking would multiply local latency [V S7, S11]. With `mapped`, `ThinkingLevel` maps to `low`/`medium`/`high`, and `minimal` maps to `none`.
- **`guard_thinking()`** only applies to `gemini-3.8*` ids, so it does nothing here.

### 4.6 Timeouts, concurrency, client limits

- **httpx timeouts:** `httpx.AsyncClient(timeout=httpx.Timeout(connect=5, read=OPENAI_COMPAT_TIMEOUT_S, write=30, pool=5))`. `failover._is_timeout()` already recognizes `httpx.TimeoutException`.
- **Concurrency:** a per-process `asyncio.Semaphore(OPENAI_COMPAT_CONCURRENCY)`. On 16 GB, two parallel local requests would compete for memory.
- **The mobile client gives up first.** Its timeouts are fixed at 120 s for analyze, 60 s for troubleshoot and language-pack posts, and 30 s for everything else, chat included (`TIMEOUT_MS` in `apps/mobile/src/api/client.ts`, re-read by the fact-checker). A local analyze call will often take longer [E]. So:
  - test local models through `eval_golden.py --provider openai_compat` and the curl smoke tests, which have no client timeout;
  - keep `OPENAI_COMPAT_MAX_OUTPUT_TOKENS` low;
  - optionally, add a dev-only mobile override such as `EXPO_PUBLIC_SLOW_AI=1` that triples the timeouts. That belongs to the mobile work package, and production builds must ignore it.

### 4.7 Error mapping to the existing failover and key pool

The provider raises `OpenAICompatError(status_code: int | None, message: str, response: httpx.Response | None)`. With those attribute names, the existing `status_of()`, `message_of()` and `parse_retry_after()` work unchanged. `message` holds only the upstream `error.message`/`error.code`, cut to 300 characters. It is used in memory for the regexes and never logged; the logs stay on the allow-list.

- **Key pool:** synthesize one `KeySlotConfig(key=OPENAI_COMPAT_API_KEY or "local", project=f"openai_compat:{host}", billing=<tier is local>)`, so the pool's 429 backoff, `Retry-After` handling and RPD soft caps apply. `RPD_SOFT_CAP_PRO/FAST` can guard free quotas, for example 1,000 for Groq or 50 for OpenRouter.

| Upstream | Maps to | Existing behaviour |
|---|---|---|
| 429 | `_NextSlot("429")`; cooldown with `Retry-After` or backoff. A message containing "per day" (Groq "tokens per day (TPD)" [U wording]) benches the slot to Pacific midnight, approximating the daily reset | D-07 |
| Alibaba `AllocationQuota.FreeTierOnly` (free quota used up with the switch on) [V S40] | Treat as a daily 429; HTTP status not stated [U] | D-07 |
| 402 (OpenRouter negative balance [V S96]) | `4xx_fatal` → slot disabled | D-07 |
| 401 / 403 | `4xx_fatal` | D-07 |
| 400 naming the schema / `response_format` | `SchemaFallbackNeeded` (analyze_single) or `invalid_request` | AI_PROMPTS §9.4 |
| 500 / 502 → next slot; 503 / 504 → one same-slot retry | as today | D-07 |
| Connection refused on a loopback host (Ollama not running) | `ApiError(provider_not_configured, 503, "Local AI server is not running.", retry_after=30)` | new, content-free |
| `finish_reason: "length"` | `incomplete=True` | like Gemini `MAX_TOKENS` |
| `finish_reason: "content_filter"` or a `refusal` field | `blocked_reason="other"` → 422 | AI_PROMPTS §9.3 |
| `usage.prompt_tokens` / `completion_tokens` / `completion_tokens_details.reasoning_tokens` | `Usage(input, output, thought)` | logged counts only |

### 4.8 PDF handling

Most of these endpoints take **images only**. Ollama documents no PDF input (neither S4 nor S7 mentions PDF) [V S4, S7]; Groq's vision page documents images only [V S87]; Z.ai's `file_url` is "Only GLM-5.3-Flash series, GLM-4.6V, GLM-4.5V supported", so it excludes the free GLM-4.6V-Flash [V S52]. So the provider must never send `application/pdf`:

1. **Rasterize.** Reuse `analysis/pdf_pages.py`, which already does pypdfium2 in memory. Render each page at about 150–200 DPI, capped at a 1,600 px long edge for local models [E], as PNG (or JPEG quality 85 for photo-like pages), in memory only.
2. **Respect the image cap.** Honor `MAX_PDF_PAGES` and `OPENAI_COMPAT_MAX_IMAGES`. Above the cap, return the existing page-limit error (413/400 per API_CONTRACT); never silently drop pages.
3. **Order.** Keep text parts first, then pages in order (D-04). Set `is_pdf=True` so `route()` keeps its page-count rules.

### 4.9 Privacy invariants (unchanged, restated for this provider)

- Nothing from a request or response is logged; `log_event`'s allow-list is unchanged; `provider="openai_compat"`.
- Never log `OPENAI_COMPAT_BASE_URL` together with the key, and never log upstream error bodies, because some endpoints echo the prompt.
- No temp files: requests are built in memory.
- The recording provider (`RECORD_FIXTURES`) stays dev-only and must refuse to record when the tier is `local` or `attested` and the request is not a `demo_sample_id`. Real papers must never become fixtures.
- **Before shipping the §5 sentence "Our server does not keep it" on the `local` tier:** prove that Ollama does not write API prompts to disk. Run a call with a unique marker string, then `grep -r` for it in `~/.ollama` (logs included) with `OLLAMA_DEBUG` unset. Not stated by Ollama [U].

### 4.10 Order of work

1. **Spike** (0.5 day): `spike_schema.py --provider openai_compat` against local `qwen3.5:4b` on all fixtures (needs §3 done first).
2. **Provider + settings + boot rules + unit tests.** Use a fake transport with `httpx.MockTransport`, so no network is needed.
3. **Contract and copy (WP0):** the enums, the `/v1/config` fields `ai_model_label` and `ai_vendor_name`, the §5 strings, the `CONSENT_VERSION` bump, `test_privacy_claims.py` and readability tests passing.
4. **Mobile:** badge and consent-line selection for `local` / `attested`.
5. **`eval_golden.py --provider openai_compat`** on fixtures, then the developer's own papers. Record precision/recall and latency in a follow-up note.

---

## 5. Data-use tier design

### 5.1 Why the current tiers are not enough

D-01 computes the tier from Gemini billing flags, and every consent sentence names Google. Here is where the current copy breaks for a local model:

- `consent.line1` ("Your photo is sent to Google's AI (Gemini) to be read.") would be **false**.
- `consent.line2.unpaid` ("Google may read and use what is sent.") would be **false** for any other vendor.
- On the `unpaid` tier the "I understand, continue" button is hidden, so you could never test your own papers in the app.

The fix: two new tier values and a provider-aware choice of consent line. Every sentence below must stay literally true on every tier where it can appear (COMPLIANCE_PRIVACY §17 rule).

### 5.2 Tier table (proposed; contract change owned by WP0)

| Tier | How the server gets it | Real papers | S2 "I understand, continue" | Badge key | Line 1 key | Line 2 key | Allowed `ENV` | Store build may use |
|---|---|---|---|---|---|---|---|---|
| `paid` | `AI_PROVIDER=gemini`, every slot `billing:true` | yes | shown | `consent.badge.paid` | `consent.line1` | `consent.line2.paid` | all | **yes (only this)** |
| `unpaid` / `mixed` | Gemini unbilled slot(s), **or** `openai_compat` with `OPENAI_COMPAT_DATA_TIER=unpaid` | no (403); samples only | hidden | `consent.badge.unpaid` | Gemini: `consent.line1`; other: `consent.line1.vendor` | Gemini: `consent.line2.unpaid`; other: `consent.line2.unpaid_vendor` | development, staging (production only with `ALLOW_UNPAID_KEYS`, samples) | no |
| **`local` (new)** | `openai_compat`, `OPENAI_COMPAT_DATA_TIER=local`, base URL on loopback (boot-checked) | **yes** | shown | `consent.badge.local` | `consent.line1.local` | `consent.line2.local` | development, staging; production refused until a D-xx approves it | no |
| **`attested` (new)** | `openai_compat`, `OPENAI_COMPAT_DATA_TIER=attested`, vendor name set, host not on the denylist (§4.2); the operator states that the vendor's API terms say "no training on API content" | **yes, development only** | shown | `consent.badge.attested` | `consent.line1.vendor` | `consent.line2.attested` | **development only** | no |
| `demo` | `AI_PROVIDER=mock` | samples (and the mock photo match) | unchanged | unchanged | unchanged | `consent.line2.demo` | all | demo instance only |
| `none` | Gemini with zero slots | no | unchanged | unchanged | unchanged | unchanged | development | no |

**The operator's statement is a human claim, like `billing` in `GEMINI_KEYS` today.**

- If `attested` is set falsely, every `attested` sentence becomes false. Treat that as a reportable incident (COMPLIANCE_PRIVACY §3, §13.2).
- The D-xx entry should list which vendors' terms were checked, the clause, and the date. From §1.5 those are: Alibaba International §4.48(e) [V S44], Groq §4.2 [V S90], Cloudflare [V S95], Z.ai (the API-user clause; "individual users" grant broader rights) [V S54], and Cerebras, where retention is covered but training is not stated [V S93, U].
- Mistral qualifies only after opting out [V S98, S112]. OpenRouter qualifies only with a pinned endpoint whose no-training policy you have confirmed; no fetched page confirms one for the ModelRun free endpoint [U].

### 5.3 Exact new sentences (English base copy, `en.json`)

Written for COMPLIANCE_PRIVACY's grade-5 rule: average sentence of 12 words or fewer, no word over 3 syllables. `{model}` and `{vendor}` come from the new `/v1/config` fields `ai_model_label` and `ai_vendor_name`. The server sets them from `OPENAI_COMPAT_MODEL_LABEL` and `OPENAI_COMPAT_VENDOR_NAME`, for example "Qwen" and "Alibaba Cloud".

**`local` tier**

- `consent.badge.local`: "Test build — AI on our server"
- `consent.line1.local`: "Your photo is read by {model}, an AI program that runs on our server. Our server does not keep it."
  _True because:_ the boot rule allows `local` only when the model endpoint is loopback on the API host. "Does not keep it" also needs the Ollama on-disk check in §4.9.
- `consent.line2.local`: "No other company's AI sees your paper. This is a test build. Check every answer against your paper."
  _True because:_ one provider per process, and the only AI called is the local one (fast-tier tasks and language packs included).
- `consent.line4.masks_local`: "Parts you hide are blacked out on our server before the AI reads the paper."
- `privacy.notice.sent.local`: "When you read a paper, the photo goes to our server. An AI program on our server reads it. Our server does not keep it."
- `privacy.notice.model.local`: "{model} is an open AI model. The company that made it does not get your paper."
  _True because:_ open weights run locally, and Alibaba receives nothing at inference time [V S4].
- `banner.local_tier`: "Test build. The AI runs on our server."

**`attested` tier (development only)**

- `consent.badge.attested`: "Test build — outside AI"
- `consent.line1.vendor`: "Your photo is sent to {vendor}'s AI to be read. Our server does not keep it."
- `consent.line2.attested`: "{vendor} says it will not use your paper to train its AI. It may still keep a copy. This is a test build. Send only your own papers."
  _True because:_ "says" reports the vendor's own terms. "May still keep a copy" covers Groq's logs of up to 30 days [V S89] and Alibaba's unstated retention [V S48].
- `banner.attested_tier`: "Test build with an outside AI. Send only your own papers."

**`unpaid` tier with a non-Google vendor (mirrors today's Gemini sentence)**

- `consent.line2.unpaid_vendor`: "This test build uses a free AI service. {vendor} may read and use what is sent. Do not send real papers. Sample papers only."
- `banner.unpaid_tier` is already vendor-neutral and does not change: "Test build with a free AI key. Sample papers only."

**Phrases that must NOT be used, even on `local`**

- "never leaves your device" and "nothing leaves this device" are already forbidden (§17). On a phone the photo **does** leave the device: it goes to our server.
- "Nothing leaves the laptop" (§1.1) is true only when the developer runs the API, the model and the test client all on the Mac. If the phone reaches the Mac through a tunnel, the tunnel provider carries the traffic. Never say "private AI" or "100% private" either.

**Required process (COMPLIANCE_PRIVACY §4.7)**

1. Bump `CONSENT_VERSION`.
2. Add the new keys to §17 `approved_keys`.
3. Add "AI program", "runs on our server", "outside AI" and "says it will not" to `claim_markers`.
4. Update the privacy policy's data-flow section.
5. Regenerate the packs for the new keys, and run `test_privacy_claims.py` and the readability test.

---

## 6. Open questions for the developer

1. **Install Ollama now?**
   - **Cost:** about 0.2 GB download (deleted after install), plus about 0.2–0.5 GB installed [E], plus 3.4 GB for `qwen3.5:4b`. From the fact-checker's 8.6 GiB reading, that leaves about 4.7–5.0 GiB free.
   - **What you do:** type your admin password once for the CLI link.
   - **Yes or no?**
2. **Which model first?** Options:
   - (a) `qwen3.5:4b`: recommended; fastest; best multilingual quality per GB.
   - (b) `qwen3.5:9b`: better on every published score, 6.6 GB, leaves only about 1.5–1.8 GiB at today's 8.6 GiB, which is below the safety margin: free about 2 GB first.
   - (c) `qwen3-vl:8b-instruct`: best published small-model document-reading (OCR) scores [L/R], weaker at writing in other languages, 6.1 GB, leaves about 2.0–2.3 GiB at today's 8.6 GiB.
3. **Can you free more disk?**
   - **With about 15 GB free:** you could keep the 4B and the 9B side by side, or add Gemma 4 E4B (6.1 GB) as a non-Chinese control.
   - **An external SSD also works:** point `OLLAMA_MODELS` at it.
4. **A hosted model for your own papers, too?** If yes, which one:
   - Alibaba International: best free quota, but it needs an Alibaba Cloud international account and you accept the PRC-parent caveats in §1.5;
   - Groq: US, no-training contract, small limits;
   - Cerebras: US, no retention, needs a card for the $5 trial;
   - Azure for Students: $100 with no card, strong no-training terms [V S116, S118], but whether a student subscription gets any Azure OpenAI model quota is unverified [U]. Worth a five-minute check in the Azure portal.
5. **Tier design scope.**
   - **Full:** both `local` and `attested` (two enum values, a WP0 contract bump, a new consent version).
   - **Minimal:** only `local`, with every third-party endpoint treated as `unpaid` (samples only).
6. **Production budget and owner.** Who will pay the $5+ Gemini prepay, or set up Vertex billing, before any beta? This is the D-01 open question #1 in DECISIONS. Note that 3.8 Flash prices double on 2027-01-01 [V S81].
7. **Language checks.** Do you have native speakers for Dari, Pashto and Haitian Creole? Qwen3's official list has no Pashto [V S14], and no model card here proves Pashto quality [U].
8. **OK to add a dev-only slow-AI timeout override in the mobile app** (§4.6)? The alternative is testing local models only through `eval_golden.py` and curl.

---

## 7. Sources

Tags: **[V]** = the lead or the fact-checker re-fetched this page on 2026-10-01 and it says what is cited. **[R]** = a research agent fetched it on 2026-10-01 and marked the fact verified; nobody re-fetched it, and the body text shows these as L/R. **[R-L]** = a research agent marked it "likely" (a secondary source or a summary). Sources the fact-checker re-fetched are marked "[V] (FC)".

**Local runtimes and models**

- S1 [V] https://ollama.com/download/mac ("Requires macOS 14 Sonoma or later"; DMG link; `install.sh` command) (FC)
- S2 [V] https://api.github.com/repos/ollama/ollama/releases/latest (returned v0.35.0, 2026-09-28T21:23Z; Ollama.dmg 199,580,406 bytes; Ollama-darwin.zip 198,866,136 bytes) and https://github.com/ollama/ollama/releases/download/v0.35.0/Ollama.dmg (FC)
- S3 [V] https://docs.ollama.com/macos (macOS 14+; `~/.ollama`; CLI-link permission prompt; no installed size, no mention of a password) (FC)
- S4 [V] https://docs.ollama.com/faq (the local-privacy and cloud-model quotes; env vars; default bind; `OLLAMA_MODELS`; KV-cache types; nothing about prompts in logs or PDFs) (FC). S4b [V] https://ollama.com/search?c=cloud and the per-model tag pages (cloud tags such as `glm-5.3:cloud`, `gemma4:cloud`, `gemma4:31b-cloud`) (FC)
- S5 [V] https://docs.ollama.com/context-length (FC)
- S6 [V] https://docs.ollama.com/api/chat (FC)
- S7 [V] https://docs.ollama.com/api/openai-compatibility (`reasoning_effort` incl. "none"; base64 only; `max_tokens`; no per-request context size) (FC)
- S8 [V] https://docs.ollama.com/capabilities/structured-outputs (FC)
- S9 [R] https://ollama.com/blog/structured-outputs
- S10 [V] https://ollama.com/library/qwen3.5/tags (FC)
- S11 [V] https://huggingface.co/Qwen/Qwen3.5-4B (FC)
- S12 [V] https://huggingface.co/Qwen/Qwen3.5-9B (FC)
- S13 [R-L] https://huggingface.co/Qwen/Qwen3.5-4B/raw/main/config.json (KV-cache size derived)
- S14 [V] https://qwenlm.github.io/blog/qwen3/ (119 languages; Persian, Dari, Haitian, Vietnamese listed; no Pashto) (FC)
- S15 [V] https://ollama.com/library/qwen3-vl/tags (FC)
- S16 [R] https://arxiv.org/pdf/2511.21631 (Qwen3-VL report; the fact-checker could not locate the 8B DocVQA/OCRBench figures in the HTML text)
- S17 [V] https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct (Apache-2.0; benchmarks shown only as images) (FC)
- S18 [V] https://ollama.com/library/minicpm-v4.5 (FC)
- S19 [R] https://arxiv.org/html/2509.18154v1
- S20 [R] https://huggingface.co/openbmb/MiniCPM-V-4_5
- S21 [V] https://ollama.com/library/gemma4/tags (FC)
- S22 [R] https://huggingface.co/google/gemma-4-E4B-it
- S23 [R] https://lmstudio.ai/docs/developer/openai-compat
- S24 [V] https://lmstudio.ai/docs/developer/openai-compat/structured-output (FC)
- S25 [V] https://lmstudio.ai/docs/app/offline (FC)
- S26 [R] https://installers.lmstudio.ai/darwin/arm64/0.4.25-1/LM-Studio-0.4.25-1-arm64.dmg
- S27 [R-L] https://github.com/ggml-org/llama.cpp/discussions/4167 (community Apple Silicon benchmarks; the fact-checker re-read it: M4 10-core GPU, LLaMA-7B Q4_0 PP 221.29 / TG 24.11 tok/s; the 8-core-GPU M4 row is empty)
- S28 [R] https://huggingface.co/zai-org/GLM-OCR
- S29 [R] https://ollama.com/library/deepseek-ocr
- S30 [R] https://huggingface.co/meta-llama/Llama-3.2-11B-Vision-Instruct
- S31 [R] https://huggingface.co/ibm-granite/granite-vision-3.3-2b
- S32 [R] https://ollama.com/library/moondream
- S33 [R] https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct/raw/main/LICENSE
- S34 [R] https://ai.google.dev/gemma/docs/core/model_card_3
- S35 [R] https://huggingface.co/api/models/mistralai/Ministral-3-8B-Instruct-2512
- S36 [R] https://ollama.com/blaifa/InternVL3_5

**Chinese hosted providers and PRC law**

- S40 [V] https://www.alibabacloud.com/help/en/model-studio/new-free-quota (FC)
- S41 [V] https://www.alibabacloud.com/help/en/model-studio/model-pricing (model IDs and 1M-token free quotas, International) (FC)
- S42 [V] https://www.alibabacloud.com/help/en/model-studio/vision (image size limits; `max_pixels` default 2,621,440) (FC)
- S43 [V] https://www.alibabacloud.com/help/en/model-studio/json-mode (FC)
- S44 [V] https://www.alibabacloud.com/help/en/legal/latest/alibaba-cloud-international-website-product-terms-of-service-v-3-8-0 (§4.48, Model Studio: 4.48.1(e) no-training clause; facilities clause; medical/legal-advice disclaimer) (FC)
- S45 [V] https://www.alibabacloud.com/help/en/model-studio/regions (Singapore supports only the International scope) (FC)
- S46 [V] https://help.aliyun.com/en/model-studio/singapore-regional-access-information ("International (global nodes excluding Chinese mainland)"; endpoints) (FC)
- S47 [V] https://www.alibabacloud.com/help/en/legal/latest/alibaba-cloud-international-website-membership-agreement (FC)
- S48 [V] https://www.alibabacloud.com/help/en/model-studio/privacy-notice (FC)
- S49 [R] https://help.aliyun.com/en/model-studio/bailian-service-notes
- S50 [R-L] https://www.wilmerhale.com/en/insights/client-alerts/20260611-pentagon-adds-65-new-entities-to-the-1260h-list-of-chinese-military-companies (the fact-checker's web search found matching Holland & Knight, Dentons and CNBC reports; still secondary)
- S51 [V] https://docs.z.ai/guides/overview/pricing (FC)
- S52 [V] https://docs.z.ai/api-reference/llm/chat-completion (FC)
- S53 [V] https://docs.z.ai/legal-agreement/privacy-policy (FC)
- S54 [V] https://docs.z.ai/legal-agreement/terms-of-use (last update 2026-04-14) (FC)
- S55 [V] https://www.govinfo.gov/content/pkg/FR-2025-01-16/pdf/2025-00704.pdf (adds Beijing Zhipu Huazhang Technology Co., Ltd.; effective 2025-01-16) (FC)
- S56 [R] https://docs.bigmodel.cn/cn/guide/start/pricing
- S57 [V] https://docs.bigmodel.cn/cn/terms/privacy-policy (FC)
- S58 [R] https://docs.bigmodel.cn/cn/terms/service-agreement
- S59 [V] https://www.siliconflow.com/pricing (FC)
- S60 [V] https://docs.siliconflow.com/en/legals/terms-of-service (clauses 3.4(p), 7.4, 14.1) (FC)
- S61 [R] https://docs.siliconflow.com/en/userguide/guides/json-mode
- S62 [V] https://api-docs.deepseek.com/quick_start/pricing (FC)
- S63 [V] https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html (updated 2026-02-10) (FC)
- S64 [V] https://platform.kimi.ai/docs/pricing/limits (FC)
- S65 [V] https://platform.kimi.ai/docs/agreement/modeluse (FC)
- S66 [V] https://platform.minimax.io/docs/guides/terms-of-service (operator Nanonoble Pte. Ltd.; text read from the page's embedded data) (FC)
- S67 [V] https://platform.minimax.io/docs/guides/privacy-policy (FC)
- S68 [V] https://platform.stepfun.ai/docs/en/agreement/userservice (FC)
- S69 [R] https://platform.stepfun.ai/docs/en/guides/pricing/details
- S70 [V] https://cloud.baidu.com/doc/qianfan/s/Imi2rpirg (FC)
- S71 [V] https://cloud.baidu.com/doc/UserGuide/s/vl28nlti4 (FC)
- S72 [V] http://www.npc.gov.cn/englishnpc/c2759/c23934/202112/t20211209_385109.html (PRC Data Security Law, Art. 35; fetched over plain HTTP because HTTPS failed the TLS handshake) (FC)
- S73 [R-L] https://en.wikipedia.org/wiki/National_Intelligence_Law_of_the_People's_Republic_of_China

**US / EU hosted providers**

- S80 [V] https://ai.google.dev/gemini-api/terms (last updated 2026-04-28 UTC; "Your access to Gemini API is a 'Paid Service' only when accessing the API through a Cloud Project associated with an active billing account"; COMPLIANCE_PRIVACY §1 cites a 2026-03-23 version, so re-check the wording there) (FC)
- S81 [V] https://ai.google.dev/gemini-api/docs/pricing (FC)
- S82 [V] https://ai.google.dev/gemini-api/docs/billing (last updated 2026-09-28 UTC; tier table "Free: Active project or free trial"; "Free trial account" ineligible for the Paid Tier; $5 minimum / $5,000 maximum prepay; free-trial credit excluded since March 2026) (FC)
- S83 [V] https://docs.cloud.google.com/free/docs/free-cloud-features (last updated 2026-09-24 UTC) (FC)
- S84 [V] https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/zero-data-retention (last updated 2026-10-01 UTC) (FC)
- S85 [V] https://cloud.google.com/terms/google-cloud-express (§3.2 "No Personal Data") (FC)
- S86 [V] https://console.groq.com/docs/rate-limits (FC)
- S87 [V] https://console.groq.com/docs/vision (FC)
- S88 [V] https://console.groq.com/docs/structured-outputs (FC)
- S89 [V] https://console.groq.com/docs/your-data (FC)
- S90 [V] https://console.groq.com/docs/legal/services-agreement (§4.2) (FC)
- S91 [V] https://www.cerebras.ai/pricing (FC)
- S92 [V] https://inference-docs.cerebras.ai/models/qwen-3.8-27b (FC)
- S93 [V] https://www.cerebras.ai/privacy-policy (FC)
- S94 [V] https://developers.cloudflare.com/workers-ai/platform/pricing/ (Qwen 3.8 27B: 40,909 / 290,909 Neurons per M in/out; Gemma 4 26B: 9,091 / 27,273) (FC)
- S95 [V] https://developers.cloudflare.com/workers-ai/platform/data-usage/ (FC)
- S96 [V] https://openrouter.ai/docs/api/reference/limits (FC)
- S97 [V] https://openrouter.ai/api/v1/models/qwen/qwen3.8-27b:free/endpoints (modalities, `structured_outputs`, `max_tokens`, fp4, 262,144 ctx; this response has no data-policy fields) (FC)
- S98 [V] https://help.mistral.ai/en/articles/323757-do-you-use-my-user-data-to-train-your-artificial-intelligence-models (FC)
- S99 [V] https://huggingface.co/docs/inference-providers/pricing (FC)
- S100 [V] https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf (§1.2, §2.6, §3.3) (FC)
- S101 [V] https://github.blog/changelog/2026-07-30-github-models-is-now-retired/ (FC)
- S107 [V] https://console.groq.com/docs/models (`qwen/qwen3.8-27b` under "Preview Models") (FC)
- S108 [V] https://developers.cloudflare.com/workers-ai/features/json-mode/ (FC)
- S109 [V] https://openrouter.ai/docs/guides/routing/provider-selection (`data_collection`, `zdr`, `require_parameters`, `only`, `order`) (FC)
- S110 [V] https://openrouter.ai/docs/guides/privacy/provider-logging ("separate settings for paid and free models") (FC)
- S111 [V] https://help.mistral.ai/en/articles/347612-can-i-activate-zero-data-retention-zdr (FC)
- S112 [V] https://help.mistral.ai/en/articles/455207-can-i-opt-out-of-my-input-or-output-data-being-used-for-training (FC)
- S113 [V] https://docs.mistral.ai/admin/billing-usage/usage-limits (FC)
- S114 [V] https://docs.sambanova.ai/docs/en/models/rate-limits (FC)
- S115 [V] https://docs.together.ai/docs/billing (FC)
- S116 [V] https://azure.microsoft.com/en-us/free/students (FC)
- S117 [V] https://azure.microsoft.com/en-us/pricing/purchase-options/azure-account (FC)
- S118 [V] https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/openai/data-privacy (FC)

**US data-security rule**

All 28 CFR Part 202 text below was fetched from the official eCFR versioner API (version date 2026-09-29), e.g. `https://www.ecfr.gov/api/versioner/v1/full/2026-09-29/title-28.xml?part=202&section=202.205` (it needs an `Accept-Encoding` header that allows compression). This replaces the earlier unofficial govregs.com mirror.

- S102 [V] https://www.justice.gov/nsd/data-security (effective 2025-04-08; subpart J due-diligence/audit and reporting duties effective 2025-10-05) (FC). S102b [V] 28 CFR 202.601 (countries of concern) (FC)
- S103 [V] 28 CFR 202.205 "Bulk" (FC). S103b [V] 202.204 "Biometric identifiers". S103c [V] 202.241 "Personal health data". S103d [V] 202.212 "Covered personal identifiers" (FC)
- S104 [V] 28 CFR 202.211 "Covered person" (Example 4: a company "headquartered in China") (FC)
- S105 [V] 28 CFR 202.401 restricted transactions (FC). S105b [V] 202.258 "Vendor agreement" (includes "cloud-computing services") (FC)
- S106 [V] 28 CFR 202.256 "U.S. person" (Example 8: a US-organized subsidiary of a country-of-concern parent is a U.S. person) (FC)

**Repository facts used (read 2026-10-01)**

- `apps/api/proxyhealth_api/ai/provider.py`, `failover.py`, `keypool.py`, `routing.py`, `gemini.py`, `schema_guard.py`
- `apps/api/proxyhealth_api/settings.py`, `apps/api/.env.example`
- `apps/api/proxyhealth_api/analysis/pdf_pages.py`
- `apps/mobile/src/api/client.ts` (client timeouts)
- `docs/COMPLIANCE_PRIVACY.md` §3, §4, §17
- `apps/api/data/fixtures/uscis_i797c_receipt_i765/`
