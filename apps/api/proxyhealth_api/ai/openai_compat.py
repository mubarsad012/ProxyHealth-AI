"""``OpenAICompatProvider`` — any OpenAI-compatible ``/chat/completions`` endpoint over ``httpx``
(free-ai-providers §4: Ollama, LM Studio, DashScope International, Groq, Cerebras, OpenRouter …).

Request (§4.3): one system message (+ the schema text when the JSON mode is not ``json_schema``),
one user message with every text ``Part`` first and every page after it as a base64
``image_url`` (D-04 order); PDFs are rasterised in memory (§4.8) and never sent as PDF; images
are capped at a 1,600 px long edge. ``temperature: 0`` (Ollama's structured-output advice, a
provider-specific exception to D-04), ``max_tokens`` capped by ``OPENAI_COMPAT_MAX_OUTPUT_TOKENS``
(4096 on loopback, so a runaway reply ends with ``length`` before the timeout; LOCAL_AI.md §5)
and ``reasoning_effort: "none"`` unless ``OPENAI_COMPAT_REASONING`` says otherwise (§4.5). The
OpenAI-compatible endpoint of Ollama cannot set the context length per request (§3.3): set
``OLLAMA_CONTEXT_LENGTH`` on the Ollama side.

Structured output (§4.4): ``json_schema`` (strict, flattened), ``json_object`` or ``prompt``
(schema in the system message) from a host table or ``OPENAI_COMPAT_JSON_MODE``; then
``<think>``/fence stripping, Pydantic validation and **one** repair retry carrying only error
``loc``/``type``; still invalid → ``incomplete`` so the existing ``two_call`` fallback runs.

Errors (§4.7) are raised as ``OpenAICompatError(status_code, message, response)`` so
``failover.status_of``/``message_of``/``parse_retry_after`` work unchanged; ``message`` holds the
upstream ``error.message``/``code`` cut to 300 characters, is used in memory only and is never
logged; ``response`` is a body-less stand-in that carries only ``Retry-After``. A call that runs
out of its ``OPENAI_COMPAT_TIMEOUT_S`` budget (a read timeout, or the whole post outlasting it) is
``503 upstream_unavailable`` with ``err.ai_too_slow`` for the paper-reading tasks (at temperature
0 a retry repeats it), or ``err.ai_busy`` when the call spent its budget queued behind another.

Privacy (§4.9): nothing from a request or response is logged or written anywhere; the key is only
ever placed in the ``Authorization`` header.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, SecretStr, ValidationError

from proxyhealth_api.ai.keypool import KeyPool
from proxyhealth_api.ai.provider import Part, StructuredResult, Task, Usage
from proxyhealth_api.ai.slow_errors import busy_error, too_slow_error
from proxyhealth_api.analysis import pdf_pages
from proxyhealth_api.analysis.redaction import MAX_PIXELS
from proxyhealth_api.analysis.redaction import _encode as encode_image
from proxyhealth_api.contracts.enums import ErrorCode, ModelTier, Provider, ThinkingLevel
from proxyhealth_api.errors import ApiError
from proxyhealth_api.settings import KeySlotConfig, Settings, host_is_denylisted

JsonMode = Literal["json_schema", "json_object", "prompt"]

PDF_MIME = "application/pdf"
# §4.3 / §4.8: long-edge cap for every page we send (Alibaba's own Qwen-VL default is ~1,600 px).
MAX_LONG_EDGE = 1600
_PASS_MIMES = frozenset({"image/png", "image/jpeg"})

MESSAGE_MAX_CHARS = 300  # §4.7: upstream error text kept in memory, never logged
REPAIR_MAX_ERRORS = 20
MIN_RETRY_BUDGET_S = 5.0  # a repair/protocol retry needs at least this much of the call budget
MAX_PROTOCOL_RETRIES = 2  # dropped reasoning_effort, downgraded JSON mode
CONNECT_TIMEOUT_S = 5.0
WRITE_TIMEOUT_S = 30.0
POOL_TIMEOUT_S = 5.0
LOCAL_DOWN_RETRY_AFTER_S = 30
MODEL_MISSING_RETRY_AFTER_S = 60
# A call that spent at least this share of its budget waiting for the semaphore and then ran out
# of time lost its budget to another request holding the one loopback slot: "busy", not "too
# slow on this paper" (§4.7). A shorter wait (a third is 100 s of 300 s; a loopback paper reads
# in ≈ 65–200 s) did not cause the timeout, so the paper itself is reported as too slow.
QUEUE_BUSY_SHARE = 1 / 3

# §4.4 capability table: host pattern → (mode with images, mode for text-only tasks). Patterns use
# the ``ATTESTED_HOST_DENYLIST`` syntax. Anything else (loopback Ollama/LM Studio included) gets
# ``json_schema``; ``OPENAI_COMPAT_JSON_MODE`` overrides the table.
HOST_JSON_MODES: tuple[tuple[str, JsonMode, JsonMode], ...] = (
    ("*.aliyuncs.com", "json_object", "json_schema"),  # multimodal falls back to json_object
    ("api.z.ai", "prompt", "json_object"),  # "Only text models support this field"
    ("*.siliconflow.com", "json_object", "json_object"),
    ("*.siliconflow.cn", "json_object", "json_object"),
    ("api.groq.com", "json_object", "json_schema"),  # images + strict: not stated
    ("openrouter.ai", "json_schema", "json_schema"),
    ("api.cerebras.ai", "json_schema", "json_schema"),
    ("api.mistral.ai", "json_schema", "json_schema"),
    ("api.cloudflare.com", "json_schema", "json_schema"),
)
OPENROUTER_HOST = "openrouter.ai"
DETAIL_HIGH_HOSTS = ("*.siliconflow.com", "*.siliconflow.cn")  # documents ``detail: "high"``

# A 400/422 that names the structured-output request (Cloudflare "JSON Mode couldn't be met" …).
SCHEMA_REJECTION_RE = re.compile(
    r"response_format|json[_ ]?schema|json[_ ]?object|json mode|structured|schema", re.I
)
REASONING_REJECTION_RE = re.compile(r"reasoning", re.I)
FREE_TIER_ONLY_RE = re.compile(r"FreeTierOnly", re.I)  # Alibaba: free quota used, switch on
_THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)
_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")

_EFFORT: dict[ThinkingLevel, str] = {
    ThinkingLevel.minimal: "none",
    ThinkingLevel.low: "low",
    ThinkingLevel.medium: "medium",
    ThinkingLevel.high: "high",
}
_META_KEYS = frozenset({"title", "description", "default", "examples"})


class OpenAICompatError(Exception):
    """An upstream HTTP error (§4.7). Attribute names match what ``failover`` reads."""

    def __init__(
        self, status_code: int | None, message: str, response: httpx.Response | None = None
    ) -> None:
        super().__init__(f"upstream {status_code}")
        self.status_code = status_code
        self.message = message[:MESSAGE_MAX_CHARS]
        self.response = response


# ------------------------------------------------------------------ JSON mode + schema text


def host_json_mode(host: str, *, has_images: bool) -> JsonMode:
    for pattern, image_mode, text_mode in HOST_JSON_MODES:
        if host_is_denylisted(host, (pattern,)):
            return image_mode if has_images else text_mode
    return "json_schema"


def pick_json_mode(settings: Settings, *, has_images: bool) -> JsonMode:
    """``OPENAI_COMPAT_JSON_MODE`` when set, else the host table (§4.4)."""
    if settings.openai_compat_json_mode != "auto":
        return settings.openai_compat_json_mode
    return host_json_mode(settings.openai_compat_host, has_images=has_images)


def flatten_schema(schema: type[BaseModel], *, strict: bool) -> dict[str, Any]:
    """The one schema helper (§4.4): ``$defs``/``$ref`` inlined, metadata keys dropped,
    ``X | None`` kept as ``anyOf [X, null]``; ``strict`` adds ``additionalProperties: false`` and
    lists every property in ``required`` (OpenAI-style strict mode)."""
    raw = schema.model_json_schema()
    defs: dict[str, Any] = raw.get("$defs", {})

    def node(value: Any, depth: int) -> Any:
        if depth > 40:  # schema_guard forbids recursion; this only guards a broken schema
            raise ValueError("schema too deep to flatten")
        if isinstance(value, list):
            return [node(v, depth + 1) for v in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            target = defs[str(value["$ref"]).rsplit("/", 1)[-1]]
            merged = {**target, **{k: v for k, v in value.items() if k != "$ref"}}
            return node(merged, depth + 1)
        out: dict[str, Any] = {}
        for key, sub in value.items():
            if key in _META_KEYS or key == "$defs":
                continue
            if key == "properties" and isinstance(sub, dict):
                out[key] = {name: node(prop, depth + 1) for name, prop in sub.items()}
            else:
                out[key] = node(sub, depth + 1)
        if strict and out.get("type") == "object" and isinstance(out.get("properties"), dict):
            out["additionalProperties"] = False
            out["required"] = list(out["properties"])
        return out

    flat: dict[str, Any] = node(raw, 0)
    return flat


def schema_instruction(schema: type[BaseModel]) -> str:
    """System-message suffix for ``json_object``/``prompt`` modes (contains the word "JSON",
    which DashScope requires for ``json_object``)."""
    text = json.dumps(flatten_schema(schema, strict=False), separators=(",", ":"))
    return (
        "Reply with one JSON object only, with no other text. It must match this JSON Schema:\n"
        f"{text}"
    )


def response_format(mode: JsonMode, schema: type[BaseModel]) -> dict[str, Any] | None:
    if mode == "json_schema":
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "schema": flatten_schema(schema, strict=True),
                "strict": True,
            },
        }
    if mode == "json_object":
        return {"type": "json_object"}
    return None


# ------------------------------------------------------------------------------- images


def _data_url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _unreadable() -> ApiError:
    return ApiError(
        ErrorCode.unsupported_media_type, 415, "This AI server reads JPEG, PNG and PDF pages only."
    )


def image_data_url(data: bytes, mime: str, *, long_edge: int = MAX_LONG_EDGE) -> str:
    """One page as a base64 data URL: JPEG/PNG within ``long_edge`` pass through unchanged;
    larger or other Pillow-readable formats are re-encoded in memory (PNG stays PNG, the rest
    become JPEG). Unreadable bytes (HEIC without a codec) → ``415``; a pixel bomb → ``413``."""
    try:
        image: Image.Image = Image.open(io.BytesIO(data))
    except Image.DecompressionBombError as exc:
        raise ApiError(ErrorCode.payload_too_large, 413, "The image has too many pixels.") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise _unreadable() from exc
    if image.width * image.height > MAX_PIXELS:
        raise ApiError(ErrorCode.payload_too_large, 413, "The image has too many pixels.")
    if mime in _PASS_MIMES and max(image.width, image.height) <= long_edge:
        return _data_url(data, mime)
    try:
        image.load()
    except (OSError, ValueError) as exc:
        raise _unreadable() from exc
    image = ImageOps.exif_transpose(image)
    image.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
    # redaction's encoder: in memory (an io.BytesIO), metadata dropped, JPEG quality 85.
    out, out_mime = encode_image(image, "image/png" if mime == "image/png" else "image/jpeg")
    return _data_url(out, out_mime)


def page_image_urls(parts: Sequence[Part], *, max_images: int) -> list[str]:
    """Every bytes ``Part`` as data URLs, in order; a PDF becomes one PNG per page (§4.8).

    More pages than ``max_images`` is the existing page-limit error — never a silent drop:
    ``400 pdf_too_long`` for a PDF, ``400 too_many_pages`` otherwise."""
    media = [p for p in parts if p.kind == "bytes"]
    pdf_counts = [
        pdf_pages.page_count(p.data or b"") if p.mime_type == PDF_MIME else 1 for p in media
    ]
    total = sum(pdf_counts)
    if total > max_images:
        details: dict[str, str | int | bool] = {"max_pages": max_images, "pages": total}
        if any(p.mime_type == PDF_MIME for p in media):
            raise ApiError(
                ErrorCode.pdf_too_long, 400,
                f"This AI server reads at most {max_images} pages at a time.",
                details={"max_pdf_pages": max_images, "pages": total},
            )  # fmt: skip
        raise ApiError(
            ErrorCode.too_many_pages, 400,
            f"This AI server reads at most {max_images} pages at a time.", details=details,
        )  # fmt: skip
    urls: list[str] = []
    for part, count in zip(media, pdf_counts, strict=True):
        data = part.data or b""
        if part.mime_type == PDF_MIME:
            thumbs = pdf_pages.rasterize(data, longest_edge=MAX_LONG_EDGE, max_pages=count)
            urls.extend(f"data:image/png;base64,{t.data_base64}" for t in thumbs)
        else:
            urls.append(image_data_url(data, part.mime_type or "application/octet-stream"))
    return urls


# ----------------------------------------------------------------------- request / response


def build_messages(
    system: str, parts: Sequence[Part], image_urls: Sequence[str], *, mode: JsonMode,
    schema: type[BaseModel], detail_high: bool = False,
) -> list[dict[str, Any]]:  # fmt: skip
    """§4.3: system (+ schema text unless ``json_schema``), then one user turn with the text of
    every text ``Part`` (in order) before every page (D-04). Text-only → plain string content."""
    system_text = system if mode == "json_schema" else f"{system}\n\n{schema_instruction(schema)}"
    text = "\n\n".join(p.text or "" for p in parts if p.kind == "text")
    user: str | list[dict[str, Any]]
    if image_urls:
        items: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for url in image_urls:
            image: dict[str, Any] = {"url": url}
            if detail_high:
                image["detail"] = "high"
            items.append({"type": "image_url", "image_url": image})
        user = items
    else:
        user = text
    return [{"role": "system", "content": system_text}, {"role": "user", "content": user}]


def reasoning_effort(settings: Settings, thinking: ThinkingLevel | None) -> str | None:
    """§4.5: ``none`` → always ``"none"``; ``mapped`` → ThinkingLevel (minimal → none);
    ``omit`` → the field is not sent."""
    mode = settings.openai_compat_reasoning
    if mode == "none":
        return "none"
    if mode == "mapped" and thinking is not None:
        return _EFFORT[thinking]
    return None


def strip_to_json(text: str) -> str:
    """§4.4 step 1: drop ``<think>…</think>`` (also an unclosed leading one) and code fences,
    then keep the outermost ``{…}``."""
    cleaned = _THINK_RE.sub("", text)
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>", 1)[1]
    cleaned = _FENCE_RE.sub("", cleaned.strip()).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    return cleaned


def repair_prompt(exc: ValidationError) -> str:
    """§4.4 step 3: only Pydantic ``loc``/``type`` — never input values or messages."""
    problems = [
        f"{'.'.join(str(x) for x in err['loc']) or '(root)'}: {err['type']}"
        for err in exc.errors(include_input=False, include_url=False)[:REPAIR_MAX_ERRORS]
    ]
    return (
        "Your JSON did not match the schema. Problems: "
        + "; ".join(problems)
        + ". Return only the corrected JSON."
    )


def upstream_message(resp: httpx.Response) -> str:
    """``error.message``/``error.code``(/``type``) from a JSON error body, ≤ 300 chars; never
    the raw body (some endpoints echo the prompt)."""
    try:
        data = resp.json()
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    err = data.get("error", data)
    if isinstance(err, str):
        return err[:MESSAGE_MAX_CHARS]
    if not isinstance(err, dict):
        return ""
    fields = (err.get("message"), err.get("code"), err.get("type"), err.get("detail"))
    text = " ".join(str(f) for f in fields if isinstance(f, str | int) and str(f))
    return text[:MESSAGE_MAX_CHARS]


def usage_of(data: Mapping[str, Any]) -> Usage:
    raw = data.get("usage")
    if not isinstance(raw, dict):
        return Usage()
    details = raw.get("completion_tokens_details")
    thought = details.get("reasoning_tokens") if isinstance(details, dict) else 0

    def num(value: Any) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    return Usage(num(raw.get("prompt_tokens")), num(raw.get("completion_tokens")), num(thought))


@dataclass(frozen=True)
class Choice:
    content: str | None
    finish_reason: str | None
    refused: bool


def first_choice(data: Mapping[str, Any]) -> Choice | None:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    choice = choices[0]
    raw_message = choice.get("message")
    message: dict[str, Any] = raw_message if isinstance(raw_message, dict) else {}
    content = message.get("content")
    if isinstance(content, list):  # some servers return content parts
        texts = [p for p in content if isinstance(p, dict) and p.get("type") == "text"]
        content = "".join(str(p.get("text", "")) for p in texts)
    finish = choice.get("finish_reason")
    return Choice(
        content=content if isinstance(content, str) else None,
        finish_reason=finish if isinstance(finish, str) else None,
        refused=bool(message.get("refusal")),
    )


def _retry_after_stub(resp: httpx.Response) -> httpx.Response:
    """A body-less response carrying only ``Retry-After`` for ``failover.parse_retry_after``."""
    value = resp.headers.get("Retry-After")
    headers = {"Retry-After": value} if value is not None else {}
    return httpx.Response(resp.status_code, headers=headers)


def add_usage(total: Usage, more: Usage) -> Usage:
    return Usage(
        total.input_tokens + more.input_tokens,
        total.output_tokens + more.output_tokens,
        total.thought_tokens + more.thought_tokens,
    )


# ------------------------------------------------------------------------------ provider


class OpenAICompatProvider:
    """``AIProvider`` for ``AI_PROVIDER=openai_compat``. One synthetic key-pool slot (index 0);
    a per-process semaphore (``OPENAI_COMPAT_CONCURRENCY``) bounds parallel calls, and each
    ``generate_structured`` call — queue wait and retries included — stays within
    ``OPENAI_COMPAT_TIMEOUT_S``."""

    name: Provider = Provider.openai_compat

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._endpoint = f"{settings.openai_compat_base_url}/chat/completions"
        self._host = settings.openai_compat_host
        self._loopback = settings.openai_compat_is_loopback
        self._timeout_s = float(settings.openai_compat_timeout)
        self._clock = clock
        headers = {"Content-Type": "application/json"}
        key = settings.openai_compat_api_key.get_secret_value()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        self._client = httpx.AsyncClient(
            headers=headers, transport=transport, timeout=self._httpx_timeout(self._timeout_s)
        )
        self._semaphore = asyncio.Semaphore(settings.openai_compat_concurrency_limit)
        # Learned once per process (content-free): the endpoint refused these request features.
        self._mode_override: dict[bool, JsonMode] = {}
        self._send_reasoning = True
        # Content-free facts about the last call, for scripts/provider_check.py.
        self.last_json_mode: JsonMode | None = None
        self.last_repaired = False
        self.last_latency_ms: int | None = None

    @staticmethod
    def _httpx_timeout(read_s: float) -> httpx.Timeout:
        return httpx.Timeout(
            connect=CONNECT_TIMEOUT_S, read=read_s, write=WRITE_TIMEOUT_S, pool=POOL_TIMEOUT_S
        )

    def model_for(self, tier: ModelTier) -> str:
        """Model ids only from ``OPENAI_COMPAT_MODEL_PRO`` / ``_FAST`` (§4.5)."""
        s = self._settings
        return s.openai_compat_model_pro if tier is ModelTier.pro else s.openai_compat_model_fast

    async def aclose(self) -> None:
        await self._client.aclose()

    async def generate_structured(
        self,
        *,
        task: Task,
        tier: ModelTier,
        parts: Sequence[Part],
        system: str,
        schema: type[BaseModel],
        thinking: ThinkingLevel | None,
        media_resolution: Literal["high", "medium"] | None,
        max_output_tokens: int,
        request_id: str,
        slot_index: int | None = None,
        hints: Mapping[str, str] | None = None,
    ) -> StructuredResult:
        if slot_index not in (None, 0):
            raise ValueError(f"slot_index {slot_index} out of range (0..0)")
        started = self._clock()
        # One budget for the whole call: the queue wait counts against OPENAI_COMPAT_TIMEOUT_S,
        # so a call can never outlast the client_timeouts the server advertises (CL-092(a)).
        deadline = started + self._timeout_s
        try:
            async with asyncio.timeout(self._timeout_s):
                await self._semaphore.acquire()
        except TimeoutError:
            raise busy_error(self._clock() - started) from None
        waited = self._clock() - started
        try:
            urls = await asyncio.to_thread(
                page_image_urls, parts, max_images=self._settings.openai_compat_image_cap
            )
            return await self._generate(
                tier=tier, parts=parts, urls=urls, system=system, schema=schema,
                thinking=thinking, max_output_tokens=max_output_tokens, deadline=deadline,
            )  # fmt: skip
        except (httpx.ReadTimeout, TimeoutError):
            if waited >= self._timeout_s * QUEUE_BUSY_SHARE:
                raise busy_error(waited) from None
            raise too_slow_error(
                task, self._timeout_s, reason="ai_timeout", local=self._loopback
            ) from None
        finally:
            self._semaphore.release()
            self.last_latency_ms = int((self._clock() - started) * 1000)

    async def _generate(
        self, *, tier: ModelTier, parts: Sequence[Part], urls: list[str], system: str,
        schema: type[BaseModel], thinking: ThinkingLevel | None, max_output_tokens: int,
        deadline: float | None = None,
    ) -> StructuredResult:  # fmt: skip
        has_images = bool(urls)
        mode = self._mode_override.get(has_images) or pick_json_mode(
            self._settings, has_images=has_images
        )
        model_id = self.model_for(tier)
        detail_high = any(host_is_denylisted(self._host, (p,)) for p in DETAIL_HIGH_HOSTS)
        messages = build_messages(
            system, parts, urls, mode=mode, schema=schema, detail_high=detail_high
        )
        max_tokens = min(max_output_tokens, self._settings.openai_compat_output_cap)
        effort = reasoning_effort(self._settings, thinking)
        if deadline is None:
            deadline = self._clock() + self._timeout_s
        usage = Usage()
        protocol_retries = 0
        repaired = False
        self.last_repaired = False
        while True:
            body = self._body(model_id, messages, mode, schema, max_tokens, effort)
            resp = await self._post(body, deadline)
            if resp.status_code != 200:
                message = upstream_message(resp)
                retry = self._protocol_retry(resp.status_code, message, mode, effort)
                if retry is not None and protocol_retries < MAX_PROTOCOL_RETRIES:
                    protocol_retries += 1
                    if retry == "reasoning":
                        self._send_reasoning = False
                    else:
                        mode = "prompt"
                        self._mode_override[has_images] = mode
                        messages = build_messages(
                            system, parts, urls, mode=mode, schema=schema, detail_high=detail_high
                        )
                    if self._remaining(deadline) >= MIN_RETRY_BUDGET_S:
                        continue
                self._raise_for(resp, message)
            try:
                data = resp.json()
            except ValueError:
                data = {}
            usage = add_usage(usage, usage_of(data if isinstance(data, dict) else {}))
            self.last_json_mode = mode
            choice = first_choice(data if isinstance(data, dict) else {})
            if choice is None:
                return self._result(None, model_id, usage, None, incomplete=True)
            if choice.refused or choice.finish_reason == "content_filter":
                return StructuredResult(
                    parsed=None, raw_text=None, model_id=model_id, usage=usage,
                    blocked_reason="other", finish_reason=choice.finish_reason,
                )  # fmt: skip
            candidate = strip_to_json(choice.content or "")
            try:
                parsed = schema.model_validate_json(candidate)
            except ValidationError as exc:
                truncated = choice.finish_reason == "length"
                if truncated or repaired or self._remaining(deadline) < MIN_RETRY_BUDGET_S:
                    return self._result(None, model_id, usage, choice.finish_reason, True)
                repaired = True
                self.last_repaired = True
                messages = [
                    *messages,
                    {"role": "assistant", "content": candidate},
                    {"role": "user", "content": repair_prompt(exc)},
                ]
                continue
            incomplete = choice.finish_reason == "length"
            return self._result(parsed, model_id, usage, choice.finish_reason, incomplete)

    def _body(
        self, model_id: str, messages: list[dict[str, Any]], mode: JsonMode,
        schema: type[BaseModel], max_tokens: int, effort: str | None,
    ) -> dict[str, Any]:  # fmt: skip
        body: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0,
            "stream": False,
        }
        fmt = response_format(mode, schema)
        if fmt is not None:
            body["response_format"] = fmt
        if effort is not None and self._send_reasoning:
            body["reasoning_effort"] = effort
        if self._host == OPENROUTER_HOST:  # §4.4: only providers that honour every parameter
            body["provider"] = {"require_parameters": True, "data_collection": "deny"}
        return body

    def _remaining(self, deadline: float) -> float:
        return deadline - self._clock()

    async def _post(self, body: dict[str, Any], deadline: float) -> httpx.Response:
        read_s = max(self._remaining(deadline), 1.0)
        try:
            # httpx's read timeout bounds each read, not the response: an endpoint that trickles
            # bytes could outlast the budget, so the whole post is bounded as well (CL-092(a)).
            async with asyncio.timeout(read_s):
                return await self._client.post(
                    self._endpoint, json=body, timeout=self._httpx_timeout(read_s)
                )
        except httpx.ConnectError:
            if self._loopback:  # §4.7: Ollama/LM Studio is not running
                raise ApiError(
                    ErrorCode.provider_not_configured, 503, "Local AI server is not running.",
                    retry_after=LOCAL_DOWN_RETRY_AFTER_S,
                ) from None  # fmt: skip
            raise

    def _protocol_retry(
        self, status: int, message: str, mode: JsonMode, effort: str | None
    ) -> Literal["reasoning", "json_mode"] | None:
        """A 400/422 that names a request feature this endpoint lacks → retry once without it."""
        if status not in (400, 422):
            return None
        if effort is not None and self._send_reasoning and REASONING_REJECTION_RE.search(message):
            return "reasoning"
        auto = self._settings.openai_compat_json_mode == "auto"
        if auto and mode != "prompt" and SCHEMA_REJECTION_RE.search(message):
            return "json_mode"
        return None

    def _raise_for(self, resp: httpx.Response, message: str) -> None:
        status = resp.status_code
        if FREE_TIER_ONLY_RE.search(message):  # §4.7: a daily 429 whatever the status says
            raise OpenAICompatError(429, f"{message} (free quota used up per day)")
        if status == 404:
            raise ApiError(
                ErrorCode.provider_not_configured, 503,
                "The AI model is not available on the AI server.",
                retry_after=MODEL_MISSING_RETRY_AFTER_S,
            )  # fmt: skip
        if status == 413:
            raise ApiError(
                ErrorCode.payload_too_large, 413, "The pages are too large for this AI server."
            )
        raise OpenAICompatError(400 if status == 422 else status, message, _retry_after_stub(resp))

    @staticmethod
    def _result(
        parsed: BaseModel | None, model_id: str, usage: Usage, finish: str | None,
        incomplete: bool = False,
    ) -> StructuredResult:  # fmt: skip
        return StructuredResult(
            parsed=parsed, raw_text=None, model_id=model_id, usage=usage, blocked_reason=None,
            finish_reason=finish, incomplete=incomplete or parsed is None,
        )  # fmt: skip


def synthetic_slot(settings: Settings) -> KeySlotConfig:
    """§4.7: the one key-pool slot, so 429 backoff, ``Retry-After`` and RPD soft caps apply."""
    key = settings.openai_compat_api_key.get_secret_value() or "local"
    return KeySlotConfig(
        key=SecretStr(key),
        project=f"openai_compat:{settings.openai_compat_host}",
        billing=settings.openai_compat_data_tier == "local",
    )


def build_openai_compat_stack(
    settings: Settings,
    *,
    clock: Callable[[], datetime] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[OpenAICompatProvider, KeyPool]:
    """Provider + one-slot key pool whose tier is ``OPENAI_COMPAT_DATA_TIER`` (§4.2 rule 7)."""
    provider = OpenAICompatProvider(settings, transport=transport)
    keypool = KeyPool(
        [synthetic_slot(settings)],
        settings.var_dir,
        clock or (lambda: datetime.now(UTC)),
        soft_caps=settings.soft_caps,
        data_use_tier=settings.data_use_tier,
    )
    return provider, keypool
