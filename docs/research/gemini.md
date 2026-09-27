# Research: gemini

_Verified by a research agent on 2026-09-23 against official sources. Input to the ProxyHealth design; not a spec._

# Gemini API research for a Python 3.13 FastAPI backend (verified 2026-09-23)

All claims below were checked against ai.google.dev, googleapis.github.io/python-genai, github.com/googleapis/python-genai (source on `main`), and pypi.org. Where the official docs are silent I say so explicitly.

---

## 1. Current model IDs and tiers

### The landscape has changed a lot since 1.5/2.x

| Fact | Status | Source |
|---|---|---|
| `gemini-1.5-pro`, `gemini-1.5-flash`, `gemini-1.5-flash-8b` | **SHUT DOWN 2025-09-29** — changelog: "The following Gemini 1.5 models are now shut down". Not listed anywhere on the models page. | https://ai.google.dev/gemini-api/docs/changelog |
| `gemini-2.0-flash`, `gemini-2.0-flash-lite` (+ `-001`) | **SHUT DOWN 2026-06-01** | https://ai.google.dev/gemini-api/docs/deprecations |
| `gemini-2.5-pro` / `gemini-2.5-flash` / `gemini-2.5-flash-lite` | GA but **access-restricted since 2026-09-18**: "we are limiting access to the 2.5 models to users who have actively used them in the past ... For any new projects, use our latest models: 3.5 Flash-Lite or 3.8 Flash." A new project will not be able to use them. | https://ai.google.dev/gemini-api/docs/models |
| Only Pro-class model | `gemini-3.1-pro-preview` — **preview only, no GA Pro exists, and NOT on the free tier** ($2.00 in / $12.00 out per 1M ≤200k). | https://ai.google.dev/gemini-api/docs/pricing |

### Recommended tiers for this app (all GA, all have a free tier per the pricing page)

**(a) Cheap/fast text tier — UI-string translation, chat follow-ups**

- **`gemini-3.5-flash-lite`** (GA 2026-07-21). Official description: "A low-latency, cost-effective multimodal model optimized for high-throughput, low-cost execution for subagent tasks and document parsing." Inputs: Text, Image, Video, Audio, PDF. 1,048,576 in / 65,536 out. Thinking default `minimal`, supports `minimal|low|medium|high`. Paid price $0.30 in / $2.50 out per 1M. https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite
- Alternative, even cheaper: **`gemini-3.1-flash-lite`** (GA 2026-05-07) — the model page explicitly lists "translation, transcription, data extraction, document summarization" as its target tasks. $0.25 in / $1.50 out per 1M. Same modalities and token limits. https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite

**(b) High-reasoning multimodal tier — OCR of photos, screenshots, legal/medical reasoning**

- **`gemini-3.8-flash`** (GA 2026-09-02): "our most intelligent Flash model". Inputs: Text, Image, Video, Audio, PDF. 1,048,576 in / 65,536 out. Thinking default `medium`, supports `low|medium|high` (**`minimal` returns an error on 3.8 Flash**). Structured outputs, function calling, caching, file search supported. Introductory price $0.75 in / $3.75 out per 1M through 2026-12-31, then $1.50 / $7.50. Free tier: yes. https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash , https://ai.google.dev/gemini-api/docs/latest-model
- Use `thinking_level: "high"` for the legal/medical reasoning calls and `"medium"` (default) for plain OCR.
- `gemini-3.1-pro-preview` is the only "Pro" and is paid-only + preview; do not build the free tier on it.

**Aliases:** `gemini-flash-latest` currently points to `gemini-3.5-flash` (changelog 2026-05-19; not re-pointed at 3.8 in any later entry). The models page warns the `latest` alias "will get hot-swapped with every new release" with only a 2-week email notice for breaking changes, and "Most production apps should use a specific stable model." Pin the stable IDs above.

### Free-tier rate limits (RPM / TPM / RPD)

**The official rate-limits page no longer publishes per-model numbers.** I fetched both the HTML and the `.md.txt` mirror: there are zero `gemini-*` rows in the RPM/TPM/RPD section. The page says: "Rate limits depend on a variety of factors (such as your usage tier) and can be viewed in Google AI Studio" → https://aistudio.google.com/rate-limit?timeRange=last-28-days. The page also says "Specified rate limits are not guaranteed and actual capacity may vary" and "Rate limits are more restricted for experimental and preview models."

What the page does state (verified):
- Dimensions: RPM, TPM (input tokens), RPD. Exceeding any one → `429 RESOURCE_EXHAUSTED`.
- "Rate limits are applied per project, not per API key. Requests per day (RPD) quotas reset at midnight Pacific time."
- Tiers: **Free** = "Active project or free trial", no spend cap. **Tier 1** = "Set up and link an active billing account", $250 billing cap, **$10 per rolling 10-minute spend limit**. Tier 2 = $100 paid + 3 days. Tier 3 = $1,000 paid + 30 days. Free→Tier 1 upgrade "will typically take effect instantly."
- Only the **Batch API** enqueued-token table is still published (Tier 1: 3.8 Flash 3,000,000; 3.5 Flash-Lite 10,000,000; 3.1 Flash Lite 10,000,000; 3.1 Pro Preview 5,000,000).

Unofficial signal only: a Google AI Developers Forum thread titled "Gemini 3.8 Flash Free Tier 20 RPD Is Too Limited" (https://discuss.ai.google.dev/t/gemini-3-8-flash-free-tier-20-rpd-is-too-limited-for-practical-evaluation/180609) suggests the free-tier RPD for 3.8 Flash is very low (~20/day). Treat as unverified; read the real number from AI Studio for your project.

---

## 2. `google-genai` Python SDK

- PyPI package **`google-genai`**, version **2.25.0**, released **2026-09-22** (`pip install google-genai`). `Requires-Python >=3.10`; classifiers list 3.10–3.14 (3.13 supported). Core deps: httpx, pydantic>=2.12.5, anyio, tenacity, websockets, google-auth. https://pypi.org/project/google-genai/
- Import: `from google import genai`; `from google.genai import types, errors`.
- **Two API surfaces coexist.** `client.models.generate_content` (generateContent) "is now considered legacy" but "remains fully supported". The **Interactions API** (`client.interactions.create`) is "Generally Available and recommended for all new projects" as of June 2026, and "all new models, multimodal capabilities, tools, and agentic features will launch on the Interactions API." Every current doc page shows Interactions code only. https://ai.google.dev/gemini-api/docs/interactions , https://ai.google.dev/gemini-api/docs/migrate-to-interactions

### 2.1 Client creation (both surfaces)

```python
import os
from google import genai
from google.genai import types, errors

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
# genai.Client() with no args auto-reads GEMINI_API_KEY or GOOGLE_API_KEY
# (GOOGLE_API_KEY takes precedence if both are set).

# Optional: built-in retry for 408/429/5xx (defaults: attempts=5, initial_delay=1.0s,
# max_delay=60s, exp_base=2.0, jitter=1.0, codes 408/429/5xx) -- verified in types.py
client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"],
    http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(
            attempts=4, initial_delay=1.0, max_delay=30.0, exp_base=2.0, jitter=1.0,
            http_status_codes=[408, 429, 500, 502, 503, 504],
        ),
    ),
)
```
Sources: README https://github.com/googleapis/python-genai ; `HttpRetryOptions` fields from https://github.com/googleapis/python-genai/blob/main/google/genai/types.py

### 2.2 Legacy `generate_content` path (fully supported; Pydantic-native)

```python
from pydantic import BaseModel

class ExtractedDoc(BaseModel):
    document_type: str
    full_text: str
    key_fields: dict[str, str]

# (a) cheap text tier: system instruction + minimal thinking
resp = client.models.generate_content(
    model="gemini-3.5-flash-lite",
    contents="Translate this UI string to Spanish: 'Save changes'",
    config=types.GenerateContentConfig(
        system_instruction="You translate short UI strings. Return only the translation.",
        max_output_tokens=256,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
    ),
)
print(resp.text)

# (b) OCR / document tier: image bytes + PDF bytes + structured JSON
img_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")

resp = client.models.generate_content(
    model="gemini-3.8-flash",
    contents=["Extract every field from these documents.", img_part, pdf_part],  # text BEFORE image
    config=types.GenerateContentConfig(
        system_instruction="You are a careful document transcriber...",
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,  # best for OCR/dense text
        thinking_config=types.ThinkingConfig(thinking_level="high", include_thoughts=False),
        response_mime_type="application/json",
        response_schema=ExtractedDoc,            # Pydantic class accepted DIRECTLY
    ),
)
doc: ExtractedDoc = resp.parsed                  # populated via model_validate_json
# alternative: response_json_schema=ExtractedDoc.model_json_schema() -> resp.parsed is a dict
```
Verified in SDK source: `GenerateContentConfig` has `system_instruction`, `max_output_tokens`, `response_mime_type`, `response_schema: SchemaUnion` (Union includes `type`, i.e. a Pydantic class), `response_json_schema`, `thinking_config`, `media_resolution`, `safety_settings`, `http_options`. `GenerateContentResponse.parsed: Optional[Union[pydantic.BaseModel, dict, Enum]]` is filled with `response_schema.model_validate_json(...)`. `ThinkingConfig` fields: `include_thoughts: bool`, `thinking_budget: int` ("0 is DISABLED. -1 is AUTOMATIC" — legacy), `thinking_level: ThinkingLevel` (enum `MINIMAL|LOW|MEDIUM|HIGH`). `MediaResolution` enum: `MEDIA_RESOLUTION_LOW|MEDIUM|HIGH`. "You cannot use both `thinking_level` and the legacy `thinking_budget` parameter in the same request" (https://ai.google.dev/gemini-api/docs/gemini-3).

Async (README-verified):
```python
resp = await client.aio.models.generate_content(model="gemini-3.5-flash-lite", contents="...", config=...)
async for chunk in await client.aio.models.generate_content_stream(model="gemini-3.5-flash-lite", contents="..."):
    print(chunk.text, end="")
```

Errors on this path (`google/genai/errors.py`, verified):
```python
from google.genai import errors
try:
    resp = client.models.generate_content(...)
except errors.ClientError as e:      # 400-499
    if e.code == 429: ...            # RESOURCE_EXHAUSTED -> back off / return 429 to caller
    elif e.code in (400, 403, 404): ...  # do not retry
except errors.ServerError as e:      # 500-599
    if e.code == 503: ...            # UNAVAILABLE -> exponential backoff retry
except errors.APIError as e:         # anything else
    ...
# attributes: e.code (int), e.message, e.status (e.g. "RESOURCE_EXHAUSTED"), e.details, e.response
```
There are **no** 429- or 503-specific subclasses; `raise_for_response` routes 4xx→`ClientError`, 5xx→`ServerError`, else `APIError`. Other classes: `UnknownFunctionCallArgumentError`, `UnsupportedFunctionError`, `FunctionInvocationError`, `UnknownApiResponseError` (all `ValueError`). Source: https://github.com/googleapis/python-genai/blob/main/google/genai/errors.py

### 2.3 Interactions API path (Google's recommended surface for new projects)

Accepted keyword args of `client.interactions.create(...)` (from `CreateModelInteractionParam` in SDK source): `model`, `input`, `system_instruction: str`, `generation_config`, `response_format`, `response_mime_type`, `response_modalities`, `safety_settings`, `tools`, `previous_interaction_id`, `store: bool`, `stream: bool`, `background: bool`, `cached_content`, `service_tier`, `labels`, `webhook_config`, `environment`. `generation_config` fields: `thinking_level`, `thinking_summaries`, `max_output_tokens`, `seed`, `stop_sequences`, `tool_choice`, `speech_config`, `image_config`, `video_config`, `transcription_config` — **there is no `temperature`/`top_p`/`top_k`** (deprecated 2026-07-21).

```python
import base64, io
from google import genai

client = genai.Client()  # env key

interaction = await client.aio.interactions.create(       # sync: client.interactions.create
    model="gemini-3.8-flash",
    system_instruction="You are a careful document transcriber...",
    input=[
        {"type": "text", "text": "Extract every field from these documents."},
        {"type": "image",
         "data": base64.b64encode(image_bytes).decode("ascii"),   # or io.BytesIO(image_bytes): IO[bytes]/PathLike are auto-base64'd
         "mime_type": "image/jpeg",
         "resolution": "high"},                                    # per-item media resolution (Gemini 3 only)
        {"type": "document",
         "data": base64.b64encode(pdf_bytes).decode("ascii"),
         "mime_type": "application/pdf"},
    ],
    response_format={
        "type": "text",
        "mime_type": "application/json",
        "schema": ExtractedDoc.model_json_schema(),   # must be a dict; Pydantic class NOT accepted here
    },
    generation_config={"thinking_level": "high", "max_output_tokens": 8192},
    store=False,   # do NOT persist medical/legal uploads server-side (see section 3)
)
doc = ExtractedDoc.model_validate_json(interaction.output_text)
# also: interaction.outputs[-1].text ; interaction.id ; streaming via stream=True and event.event_type == "step.delta"
```
Sources: https://ai.google.dev/gemini-api/docs/text-generation , https://ai.google.dev/gemini-api/docs/image-understanding , https://ai.google.dev/gemini-api/docs/document-processing , https://ai.google.dev/gemini-api/docs/structured-output , https://ai.google.dev/gemini-api/docs/thinking , https://ai.google.dev/gemini-api/docs/media-resolution ; SDK: `google/genai/_gaos/types/interactions/{createmodelinteraction,imagecontent,textresponseformat,generationconfig}.py`, `google/genai/_gaos/types/base64fileinput.py`.

**Errors on the Interactions path are a DIFFERENT hierarchy** (verified in `google/genai/_gaos/lib/compat_errors.py` and the wrapper in `_gaos/google_genai.py`): the generated client's `GenAiError` is translated via `wrap_sdk_call` into `APIError(GeminiNextGenAPIClientError(Exception))` → `APIStatusError(.status_code, .response)` → `BadRequestError` 400, `AuthenticationError` 401, `PermissionDeniedError` 403, `NotFoundError` 404, `ConflictError` 409, `UnprocessableEntityError` 422, **`RateLimitError` 429**, **`InternalServerError` for any 5xx (503 arrives as `InternalServerError` with `status_code == 503`)**, plus `APIConnectionError` / `APITimeoutError`. These do **not** inherit from `google.genai.errors.APIError`, so an `except errors.APIError` block will miss them. The module docstring says they back `google.genai._interactions` imports, but that module does not exist on `main` (404), so today the only import path is private:

```python
from google.genai._gaos.lib.compat_errors import APIStatusError, RateLimitError, InternalServerError, APIConnectionError
```
Safer, version-proof pattern for FastAPI:
```python
def upstream_status(exc: Exception) -> int | None:
    return getattr(exc, "status_code", None) or getattr(exc, "code", None)   # Interactions vs legacy

try:
    ...
except Exception as exc:
    s = upstream_status(exc)
    if s == 429:   raise HTTPException(429, "Upstream quota exhausted; retry later", headers={"Retry-After": "30"})
    if s == 503:   ... retry with backoff, then HTTPException(503)
    raise
```

HTTP code semantics (official): 429 = "You have exceeded the per-minute or per-second request or token limit" → "Wait and retry with exponential backoff"; 503 = "The service is temporarily overloaded or down" → "Wait and retry with exponential backoff"; 402 = Prepay credit depleted; 504 = deadline exceeded. Generation may be *blocked* (not an HTTP error) with reasons `safety`, `recitation`, `prohibited_content`, **`spii`** ("Sensitive PII restrictions"), `blocklist`. https://ai.google.dev/gemini-api/docs/api-errors , https://ai.google.dev/gemini-api/docs/troubleshooting

### 2.4 Thinking / reasoning budget

- Gemini 3.x uses **`thinking_level`** (`minimal|low|medium|high`); `thinking_budget` is legacy for 2.5. Table (https://ai.google.dev/gemini-api/docs/thinking): `gemini-3.8-flash` default medium, levels low/medium/high; `gemini-3.7-flash` same; `gemini-3.6-flash` minimal..high; `gemini-3.5-flash-lite` default minimal, minimal..high; `gemini-3.1-pro-preview` default high, low/medium/high.
- Billing: "response pricing is the sum of output tokens and thinking tokens"; `max_output_tokens` "including thought tokens" is a hard cutoff — hitting it returns status `"incomplete"` with truncated/empty output while still billing thoughts. Lower `thinking_level` instead of squeezing `max_output_tokens`.
- `generation_config={"thinking_summaries": "auto"}` returns thought summaries.

---

## 3. Data-usage terms — free tier vs paid (critical for medical/legal uploads)

Gemini API Additional Terms of Service, **effective March 23, 2026** (https://ai.google.dev/gemini-api/terms), verbatim:

- **Unpaid Services** ("Any Services that are offered free of charge like direct interactions with Google AI Studio or unpaid quota in Gemini API"): "Google uses the content you submit to the Services and any generated responses to provide, improve, and develop Google products and services and machine learning technologies ... To help with quality and improve our products, human reviewers may read, annotate, and process your API input and output ... **Do not submit sensitive, confidential, or personal information to the Unpaid Services.**"
- **Paid Services**: "Google doesn't use your prompts (including associated system instructions, cached content, and files such as images, videos, or documents) or responses to improve our products". Definition: "**Your access to Gemini API is a 'Paid Service' only when accessing the API through a Cloud Project associated with an active billing account.**" The Billing page confirms the lever: "To access higher rate limits, use advanced models, and ensure your prompts and responses are not used to improve Google products, you can link a billing account and Prepay to move to the Paid Tiers." (https://ai.google.dev/gemini-api/docs/billing). The pricing page marks free tier as "Content used to improve our products" and paid as "Content **not** used to improve our products" (https://ai.google.dev/gemini-api/docs/pricing).
- **EEA/Switzerland/UK**: "the terms under 'How Google uses Your Data' in 'Paid Services' apply to all Services" for users there, and "You may use only Paid Services when making API Clients available to users in the European Economic Area, Switzerland, or the United Kingdom."
- **Medical restriction** (Use Restrictions): "**You may not use the Services in clinical practice, to provide medical advice, or in any manner that is overseen by or requires clearance or approval from a medical device regulatory agency.**" Also 18+ only and "not for consumer use" by the developer account. No HIPAA language anywhere on the page.
- Generative AI Prohibited Use Policy (https://policies.google.com/terms/generative-ai/use-policy, last modified 2024-12-17): prohibits "automated decisions that have a material detrimental impact on individual rights without human supervision in high-risk domains -- for example, in employment, healthcare, finance, legal..." and "misleading claims of expertise or capability in sensitive areas -- for example in health, finance, government services, or the law".
- **Interactions API server-side storage**: "By default, the API stores all Interaction objects (`store=true`) ... Paid Tier: 55 days. Free Tier: 1 day." Set `store=false` to opt out (loses `previous_interaction_id` and `background=true`). Stored interactions are viewable at https://aistudio.google.com/logs and deletable via the API. https://ai.google.dev/gemini-api/docs/interactions
- **Files API**: "Uploaded files are stored for 48 hours"; 2 GB/file, 20 GB/project; free; user uploads cannot be downloaded back. https://ai.google.dev/gemini-api/docs/files

---

## 4. Per-request limits and MIME types

- **Image MIME types** (exhaustive list): `image/png`, `image/jpeg`, `image/webp`, `image/heic`, `image/heif`. (No GIF/TIFF/BMP.) https://ai.google.dev/gemini-api/docs/image-understanding
- **Images per request**: "Gemini models support a maximum of 3,600 image files per request."
- **Inline size**: "Inline image data limits your total request size (text prompts, system instructions, and inline bytes) to 20MB. For larger requests, upload image files using the File API." (The Files page separately says to always use the Files API when total request > 100 MB; treat 20 MB as the inline ceiling.)
- **PDF**: "Gemini supports PDF files up to 50MB or 1000 pages." Pages are scaled down to fit the context window / up to 768×768; PDF page tokens are counted under the `IMAGE` modality. Only PDFs get vision processing; TXT/MD/HTML/XML are "extracted as pure text". Best practices: "Rotate pages to the correct orientation before uploading. Avoid blurry pages." https://ai.google.dev/gemini-api/docs/document-processing
- **Token cost with `media_resolution` (Gemini 3)**: images low 280 / medium 560 / high 1120 / ultra_high 2240 tokens; PDF pages 280/560/1120 + native text. Defaults when unspecified: 1120 per image, 560 per PDF page. Recommendation: **OCR/dense text → `high`**; PDFs → `medium` ("quality typically saturates at medium"). https://ai.google.dev/gemini-api/docs/media-resolution
- Prompt placement: "When using a single image with text, place the text prompt before the image in the `input` array."

---

## 5. Built-in TTS and translation

**Text-to-speech: yes, GA since 2026-09-22.** Models `gemini-3.8-flash-tts` (130 languages) and `gemini-3.8-flash-lite-tts` (101 languages); preview: `gemini-3.1-flash-tts-preview`, `gemini-2.5-pro-preview-tts`. Interactions API only; output is WAV (`audio/wav`, 24 kHz mono 16-bit LE PCM) for unary calls, headerless `audio/l16` chunks when streaming. Text-only input; max 2 speakers. Pricing $0.50/1M text in, $9.00/1M audio out through 2026-12-31 (then $1.00 / $18.00); listed with a free tier on the pricing page. https://ai.google.dev/gemini-api/docs/speech-generation
```python
import base64
interaction = client.interactions.create(
    model="gemini-3.8-flash-tts",
    input=[{"type": "user_input", "content": [{"type": "text", "text": "Have a wonderful day!",
             "annotations": [{"type": "speech_metadata", "style": "cheerful and friendly"}]}]}],
    response_format={"type": "audio"},
    generation_config={"speech_config": [{"voice": "Kore"}]},
)
open("out.wav", "wb").write(base64.b64decode(interaction.output_audio.data))
```
Verdict: server-side Gemini TTS is viable if you need consistent multilingual voices (130 languages) and can afford ~$9/1M audio tokens; it costs one API round-trip per utterance and counts against rate limits. For read-aloud of on-screen text in a mobile app, on-device TTS (AVSpeechSynthesizer / Android TextToSpeech) is free, offline, and adds no PHI to the wire — prefer it unless voice quality is a product requirement.

**Translation: no text-translation endpoint exists.** The only translation-specific model, `gemini-3.5-live-translate-preview`, is audio-to-audio over the Live API WebSocket ("Only audio input is supported for translation. Text input is not supported."), 70+ languages, preview. For UI-string translation use `gemini-3.5-flash-lite`/`gemini-3.1-flash-lite` with a system instruction and a JSON `response_format` mapping keys→strings, and cache results server-side. https://ai.google.dev/gemini-api/docs/live-api/live-translate

---

## Suggested FastAPI wiring (summary)

- One `genai.Client` singleton (async via `client.aio`), key from `GEMINI_API_KEY`, `HttpRetryOptions` for 408/429/5xx with a low attempt count so the request thread is not held for minutes.
- Text tier → `gemini-3.5-flash-lite`, `thinking_level="minimal"`; Document tier → `gemini-3.8-flash`, `thinking_level="high"`, `media_resolution=high` for photographed documents, `store=False`.
- Validate MIME type against the five allowed image types + `application/pdf` before calling; reject >20 MB inline payloads or route them through `client.files.upload` (auto-deleted after 48 h).
- Map upstream 429 → HTTP 429 with `Retry-After`; upstream 503 → bounded backoff then HTTP 503; upstream `spii`/`safety` block → HTTP 422 with a user-facing message.
- Do not send `temperature`/`top_p`/`top_k`; pin stable model IDs, not `-latest` aliases.

## Warnings for builders

- FREE TIER = TRAINING DATA + HUMAN REVIEW. The Gemini API terms say unpaid-quota prompts, uploaded files and responses are used to 'improve and develop Google products' and 'human reviewers may read, annotate, and process your API input and output', and explicitly: 'Do not submit sensitive, confidential, or personal information to the Unpaid Services.' Uploading users' medical/legal documents on the free tier violates this. The only fix is to attach an active Cloud Billing account to the project (then even zero-cost usage counts as 'Paid Services' and is excluded from product improvement).
- MEDICAL USE RESTRICTION. The terms state: 'You may not use the Services in clinical practice, to provide medical advice, or in any manner that is overseen by or requires clearance or approval from a medical device regulatory agency.' The Prohibited Use Policy also bars unsupervised automated decisions in healthcare/legal domains and misleading claims of medical/legal expertise. Scope the product to document transcription/summarization and information, with human oversight, and get counsel to review before launch. There is no HIPAA/BAA offering on the Gemini Developer API.
- DO NOT BUILD ON gemini-2.5-* OR ANY 1.5/2.0 ID. 1.5 models were shut down 2025-09-29, 2.0 on 2026-06-01, and since 2026-09-18 new projects cannot access 2.5 models. Use gemini-3.8-flash and gemini-3.5-flash-lite (or gemini-3.1-flash-lite). There is no GA Pro model; gemini-3.1-pro-preview is paid-only.
- PER-MODEL FREE-TIER RPM/TPM/RPD ARE NO LONGER PUBLISHED. The official rate-limits page only points to AI Studio (aistudio.google.com/rate-limit). Read the live numbers for your project before designing quotas; a forum report puts gemini-3.8-flash free tier at ~20 requests/day (unverified), which would make the free tier unusable for a multi-user document service. RPD resets midnight Pacific; limits are per project, not per key.
- TWO DIFFERENT EXCEPTION HIERARCHIES. client.models.generate_content raises google.genai.errors.ClientError/ServerError (check e.code == 429 / 503). client.interactions.create raises a separate hierarchy (RateLimitError for 429, InternalServerError for all 5xx including 503, attribute .status_code) defined in the private module google.genai._gaos.lib.compat_errors; these do NOT inherit from google.genai.errors.APIError, and the docstring's public path google.genai._interactions does not exist. Catch broadly and read getattr(exc, 'status_code', None) or getattr(exc, 'code', None).
- INTERACTIONS API STORES EVERYTHING BY DEFAULT (store=true): 1 day on free tier, 55 days on paid. Pass store=False for every call that carries user documents; note this disables previous_interaction_id and background execution, so implement chat history client-side.
- temperature / top_p / top_k WERE DEPRECATED 2026-07-21 and the Interactions GenerationConfig has no such fields. Google says to keep temperature at its default 1.0 on Gemini 3 (lower values 'may lead to unexpected behavior, such as looping'). Control determinism with structured output schemas and `seed`, not temperature. candidate_count is unsupported on Gemini 3+.
- thinking_level='minimal' returns an ERROR on gemini-3.8-flash (only low/medium/high). Use minimal on gemini-3.5-flash-lite / 3.1-flash-lite. Never combine thinking_level with the legacy thinking_budget. Thinking tokens are billed and count toward max_output_tokens; a too-small max_output_tokens yields status 'incomplete' with empty output while still charging for thoughts.
- Pydantic classes are accepted directly ONLY on the legacy path (GenerateContentConfig.response_schema -> response.parsed). On the Interactions path response_format['schema'] must be a plain dict (Model.model_json_schema()) and you parse interaction.output_text yourself. Structured-output supports only a JSON-Schema subset; deeply nested schemas may be rejected.
- Interactions `data` fields take a base64 STRING or an IO[bytes]/PathLike (auto-encoded); raw `bytes` are not accepted -- wrap with io.BytesIO or base64-encode. Legacy types.Part.from_bytes takes raw bytes.
- Enforce upload validation server-side: only image/png, image/jpeg, image/webp, image/heic, image/heif and application/pdf; inline request total <= 20 MB (route bigger files through client.files.upload, which auto-deletes after 48 h and cannot be downloaded back); PDFs <= 50 MB / 1000 pages. Photographed documents: set media_resolution high (1120 tokens/image) and put the text prompt BEFORE the image; rotate/deblur client-side.
- Generation can be silently blocked (not an HTTP error) with reason `spii` (sensitive PII) or `safety` -- likely with medical/legal documents. Inspect the finish/blocked status on every response and surface a clear message instead of an empty result.
- Do not use `gemini-flash-latest` / `-latest` aliases in production: they hot-swap on every release (currently 3.5 Flash, not 3.8) with only 2 weeks' notice for breaking changes.
- EEA/Switzerland/UK: the terms require Paid Services for any API Client serving users there, and apply paid data terms to all usage from those regions. If you have EU/UK users, billing is mandatory, not optional.
- Retries: use types.HttpRetryOptions with a small attempts count (the default is 5 with up to 60 s delays, which will hang FastAPI request handlers) and return 429 with Retry-After to your clients when the upstream quota is exhausted rather than retrying indefinitely.

## Key facts

| Fact | Source | Confidence |
|---|---|---|
| gemini-1.5-pro, gemini-1.5-flash and gemini-1.5-flash-8b were shut down on 2025-09-29 (changelog: 'The following Gemini 1.5 models are now shut down'). | https://ai.google.dev/gemini-api/docs/changelog | verified |
| gemini-2.0-flash and gemini-2.0-flash-lite (and -001 variants) were shut down 2026-06-01. | https://ai.google.dev/gemini-api/docs/deprecations | verified |
| Since 2026-09-18 access to gemini-2.5-pro/flash/flash-lite is limited to projects that used them before; Google says 'For any new projects, use our latest models: 3.5 Flash-Lite or 3.8 Flash.' | https://ai.google.dev/gemini-api/docs/models | verified |
| gemini-3.8-flash is GA (released 2026-09-02); inputs Text/Image/Video/Audio/PDF; 1,048,576 input / 65,536 output tokens; thinking levels low/medium/high (default medium; 'minimal' returns an error); structured outputs supported. | https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash | verified |
| gemini-3.5-flash-lite is GA (2026-07-21), 'optimized for high-throughput, low-cost execution for subagent tasks and document parsing'; same modalities and token limits; thinking default minimal. | https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite | verified |
| gemini-3.1-flash-lite is GA (2026-05-07) and its model page names translation, transcription, data extraction and document summarization as target tasks; $0.25 in / $1.50 out per 1M. | https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite | verified |
| The only Pro-class model is gemini-3.1-pro-preview (preview, no GA Pro exists); it has NO free tier and costs $2.00 in / $12.00 out per 1M (<=200k tokens). | https://ai.google.dev/gemini-api/docs/pricing | verified |
| Pricing page lists a free tier ('Free of charge') for gemini-3.8-flash, 3.7/3.6/3.5 Flash, 3.5 Flash-Lite, 3.1 Flash-Lite, 2.5 Pro/Flash/Flash-Lite, and the 3.8 Flash TTS models. 3.8 Flash paid: $0.75/$3.75 per 1M through 2026-12-31, then $1.50/$7.50. 3.5 Flash-Lite: $0.30/$2.50. | https://ai.google.dev/gemini-api/docs/pricing | verified |
| The official rate-limits page no longer publishes per-model Free/Tier-1 RPM/TPM/RPD tables; it says limits 'can be viewed in Google AI Studio' (aistudio.google.com/rate-limit). Only Batch-API enqueued-token tables remain. Limits are per project, RPD resets midnight Pacific, exceeding any returns 429 RESOURCE_EXHAUSTED, and 'Specified rate limits are not guaranteed'. | https://ai.google.dev/gemini-api/docs/rate-limits | verified |
| Tier definitions: Free = active project or free trial (no spend cap); Tier 1 = linked active billing account, $250 billing cap, $10 per rolling 10-minute spend limit; Free->Tier 1 upgrade is typically instant. | https://ai.google.dev/gemini-api/docs/rate-limits | verified |
| A community forum thread reports the free-tier RPD for gemini-3.8-flash is about 20 requests/day; this is NOT confirmed by any official page. | https://discuss.ai.google.dev/t/gemini-3-8-flash-free-tier-20-rpd-is-too-limited-for-practical-evaluation/180609 | unverified |
| google-genai on PyPI is version 2.25.0, released 2026-09-22; Requires-Python >=3.10 with classifiers for 3.10-3.14 (Python 3.13 supported). | https://pypi.org/project/google-genai/ | verified |
| genai.Client(api_key=...) or genai.Client() reading GEMINI_API_KEY / GOOGLE_API_KEY (GOOGLE_API_KEY takes precedence); async via client.aio.models.generate_content and client.aio.models.generate_content_stream. | https://github.com/googleapis/python-genai | verified |
| client.models.generate_content (generateContent) 'is now considered legacy' but 'remains fully supported'; the Interactions API (client.interactions.create) is GA since June 2026 and 'recommended for all new projects'; all new features launch on Interactions. | https://ai.google.dev/gemini-api/docs/interactions | verified |
| GenerateContentConfig.response_schema accepts a Pydantic BaseModel class directly (SchemaUnion includes `type`) and GenerateContentResponse.parsed is populated via response_schema.model_validate_json(); response_json_schema (dict) is the alternative. | https://github.com/googleapis/python-genai/blob/main/google/genai/types.py | verified |
| types.ThinkingConfig has fields include_thoughts, thinking_budget (legacy: '0 is DISABLED. -1 is AUTOMATIC'), and thinking_level (enum MINIMAL/LOW/MEDIUM/HIGH); thinking_level and thinking_budget cannot be combined in one request. | https://ai.google.dev/gemini-api/docs/gemini-3 | verified |
| types.HttpRetryOptions defaults: attempts 5, initial_delay 1.0s, max_delay 60s, exp_base 2.0, jitter 1.0, retryable codes 408/429/5xx; set via types.HttpOptions(retry_options=...) on the Client. | https://github.com/googleapis/python-genai/blob/main/google/genai/types.py | verified |
| Legacy-path exceptions: google.genai.errors.APIError (attrs code, message, status, details, response); ClientError for 400-499, ServerError for 500-599; no 429/503-specific subclasses, so check e.code. | https://github.com/googleapis/python-genai/blob/main/google/genai/errors.py | verified |
| Interactions-path exceptions are a separate hierarchy in google/genai/_gaos/lib/compat_errors.py: APIStatusError(.status_code) with RateLimitError (429), InternalServerError (any 5xx incl. 503), BadRequestError, AuthenticationError, PermissionDeniedError, NotFoundError, plus APIConnectionError/APITimeoutError; they do NOT subclass google.genai.errors.APIError, and the documented public path google.genai._interactions does not exist on main. | https://github.com/googleapis/python-genai/blob/main/google/genai/_gaos/lib/compat_errors.py | verified |
| Interactions create() body fields (SDK CreateModelInteractionParam): model, input, system_instruction (str), generation_config, response_format, response_mime_type, response_modalities, safety_settings, tools, previous_interaction_id, store, stream, background, cached_content, service_tier, labels, webhook_config, environment. GenerationConfig has thinking_level, thinking_summaries, max_output_tokens, seed, stop_sequences, tool_choice, speech_config, image_config, video_config, transcription_config and NO temperature/top_p/top_k. | https://github.com/googleapis/python-genai/tree/main/google/genai/_gaos/types/interactions | verified |
| Interactions image/document content `data` must be a base64 string, or an IO[bytes]/PathLike which the SDK auto-base64-encodes (raw `bytes` are not accepted); response_format schema must be a dict (use Model.model_json_schema()), parse with Model.model_validate_json(interaction.output_text). | https://ai.google.dev/gemini-api/docs/structured-output | verified |
| Sampling parameters temperature, top_p and top_k were deprecated on 2026-07-21; Google says for Gemini 3 'we strongly recommend keeping the temperature parameter at its default value of 1.0' and the 3.8 migration checklist says to strip them and remove candidate_count. | https://ai.google.dev/gemini-api/docs/latest-model | verified |
| Terms (effective 2026-03-23): on Unpaid Services Google uses submitted content and responses to 'provide, improve, and develop Google products and services and machine learning technologies'; 'human reviewers may read, annotate, and process your API input and output'; 'Do not submit sensitive, confidential, or personal information to the Unpaid Services.' | https://ai.google.dev/gemini-api/terms | verified |
| On Paid Services 'Google doesn't use your prompts (including associated system instructions, cached content, and files such as images, videos, or documents) or responses to improve our products'; 'Your access to Gemini API is a Paid Service only when accessing the API through a Cloud Project associated with an active billing account.' | https://ai.google.dev/gemini-api/terms | verified |
| Terms Use Restrictions: 'You may not use the Services in clinical practice, to provide medical advice, or in any manner that is overseen by or requires clearance or approval from a medical device regulatory agency.' Users must be 18+. API Clients for EEA/Switzerland/UK users may only use Paid Services. | https://ai.google.dev/gemini-api/terms | verified |
| Interactions API stores every interaction by default (store=true): retention 55 days on paid tier, 1 day on free tier; store=false opts out but disables previous_interaction_id and background=true; stored logs visible in AI Studio and deletable via API. | https://ai.google.dev/gemini-api/docs/interactions | verified |
| Supported image MIME types are exactly image/png, image/jpeg, image/webp, image/heic, image/heif; max 3,600 image files per request; inline data limits total request size to 20MB (use Files API above that). | https://ai.google.dev/gemini-api/docs/image-understanding | verified |
| PDF limit: 'Gemini supports PDF files up to 50MB or 1000 pages'; PDF page tokens are counted under the IMAGE modality; only PDFs get vision processing (TXT/MD/HTML/XML are text-extracted). | https://ai.google.dev/gemini-api/docs/document-processing | verified |
| Gemini 3 media_resolution token costs: images low 280 / medium 560 / high 1120 / ultra_high 2240; PDF pages 280/560/1120 plus native text; default (unspecified) is 1120 per image and 560 per PDF page; recommended: OCR/dense text -> high, PDFs -> medium. | https://ai.google.dev/gemini-api/docs/media-resolution | verified |
| Files API: 2 GB per file, 20 GB per project, files stored 48 hours, free in all regions; user-uploaded files cannot be downloaded back. | https://ai.google.dev/gemini-api/docs/files | verified |
| TTS models gemini-3.8-flash-tts (130 languages) and gemini-3.8-flash-lite-tts (101 languages) went GA 2026-09-22; Interactions API with response_format={'type':'audio'} and generation_config speech_config; output WAV 24 kHz mono 16-bit PCM (unary) or audio/l16 chunks (streaming); text-only input, max 2 speakers; paid price $0.50/1M text in and $9.00/1M audio out through 2026-12-31. | https://ai.google.dev/gemini-api/docs/speech-generation | verified |
| There is no text-translation endpoint; gemini-3.5-live-translate-preview is audio-to-audio only over the Live API WebSocket ('Text input is not supported'), 70+ languages, preview. | https://ai.google.dev/gemini-api/docs/live-api/live-translate | verified |
| HTTP 429: 'You have exceeded the per-minute or per-second request or token limit' -> 'Wait and retry with exponential backoff'; 503: 'The service is temporarily overloaded or down' -> same; 402 = prepay credits depleted; generation can be blocked with reasons safety, recitation, prohibited_content, spii, blocklist. | https://ai.google.dev/gemini-api/docs/api-errors | verified |
| gemini-flash-latest currently points to gemini-3.5-flash (changelog 2026-05-19, not re-pointed since); 'latest' aliases hot-swap with each release with only 2-week notice for breaking changes; 'Most production apps should use a specific stable model.' | https://ai.google.dev/gemini-api/docs/models | verified |
| The Generative AI Prohibited Use Policy bars 'automated decisions that have a material detrimental impact on individual rights without human supervision in high-risk domains -- for example, in employment, healthcare, finance, legal...' and 'misleading claims of expertise or capability in sensitive areas -- for example in health, finance, government services, or the law'. | https://policies.google.com/terms/generative-ai/use-policy | verified |
| types.HttpOptions has a `timeout: Optional[int]` field; the unit was not confirmed in this research (check the field docstring in types.py before relying on it). | https://github.com/googleapis/python-genai/blob/main/google/genai/types.py | unverified |
