"""``GeminiProvider`` — the legacy ``client.aio.models.generate_content`` path (D-05; AI_PROMPTS
§9).

One ``genai.Client`` per key slot. Upstream exceptions are **not** caught here: ``failover.py``
reads ``getattr(exc, "status_code", None) or getattr(exc, "code", None)``. Nothing from a
request or response is logged or stored; ``resp`` is read once and dropped.
"""

import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from proxyhealth_api.ai.failover import UnconfiguredGeminiProvider
from proxyhealth_api.ai.keypool import KeyPool
from proxyhealth_api.ai.provider import AIProvider, Part, StructuredResult, Task, Usage
from proxyhealth_api.ai.routing import guard_thinking
from proxyhealth_api.contracts.enums import ModelTier, Provider, ThinkingLevel
from proxyhealth_api.settings import KeySlotConfig, Settings

# The SDK documents ``HttpOptions.timeout`` in milliseconds (verified 2026-09-27, google-genai
# 2.25.0). ``tests/unit/test_gemini_timeout_unit.py`` re-checks this; fail loudly if it changes.
HTTP_TIMEOUT_DOC: str = types.HttpOptions.model_fields["timeout"].description or ""
if "millisecond" not in HTTP_TIMEOUT_DOC.lower():
    raise RuntimeError(
        "google-genai changed the unit of HttpOptions.timeout; "
        f"gemini.py assumes milliseconds but the SDK says: {HTTP_TIMEOUT_DOC!r}"
    )

# D-05 / AI_PROMPTS §9.1: never 429 — the key pool owns 429 (D-07).
RETRY_STATUS_CODES: tuple[int, ...] = (408, 500, 502, 503, 504)
RETRY_ATTEMPTS = 2
RETRY_INITIAL_DELAY_S = 1.0
RETRY_MAX_DELAY_S = 4.0

# Candidate finish reasons that mean "blocked" (D-07; AI_PROMPTS §9.3). The two ``IMAGE_*``
# variants beyond §9.3's list exist in the installed SDK's ``FinishReason`` and map onto the same
# contract reasons (``prohibited_content`` / ``recitation``) via ``contract_block_reason``.
BLOCK_FINISH: frozenset[str] = frozenset(
    {
        "SAFETY", "RECITATION", "PROHIBITED_CONTENT", "SPII", "BLOCKLIST", "IMAGE_SAFETY",
        "IMAGE_PROHIBITED_CONTENT", "IMAGE_RECITATION",
    }
)  # fmt: skip
# ``prompt_feedback.block_reason`` values that do not mean "blocked" ("Default value. Unused.").
_NOT_BLOCKED = frozenset({"BLOCKED_REASON_UNSPECIFIED"})
# API_CONTRACT 422 ``details.block_reason`` vocabulary; anything else → "other".
CONTRACT_REASONS: frozenset[str] = frozenset(
    {"safety", "spii", "prohibited_content", "recitation", "blocklist"}
)

_MEDIA: dict[str, types.MediaResolution] = {
    "high": types.MediaResolution.MEDIA_RESOLUTION_HIGH,
    "medium": types.MediaResolution.MEDIA_RESOLUTION_MEDIUM,
}

# ``client_factory(api_key, http_options)`` → an object exposing ``.aio.models.generate_content``.
# Production uses ``genai.Client``; unit tests inject a fake (AI_PROMPTS §9.5).
ClientFactory = Callable[[str, types.HttpOptions], Any]


def default_client_factory(api_key: str, http_options: types.HttpOptions) -> genai.Client:
    return genai.Client(api_key=api_key, http_options=http_options)


def build_http_options(settings: Settings) -> types.HttpOptions:
    """``HttpOptions`` per D-05: bounded retries on transient codes, timeout in milliseconds."""
    return types.HttpOptions(
        timeout=settings.upstream_timeout_s * 1000,
        retry_options=types.HttpRetryOptions(
            attempts=RETRY_ATTEMPTS,
            initial_delay=RETRY_INITIAL_DELAY_S,
            max_delay=RETRY_MAX_DELAY_S,
            http_status_codes=list(RETRY_STATUS_CODES),
        ),
    )


def contract_block_reason(name: str) -> str:
    """Map an SDK ``FinishReason``/``BlockedReason`` name onto the API_CONTRACT vocabulary."""
    reason = name.lower().removeprefix("image_")
    return reason if reason in CONTRACT_REASONS else "other"


def build_config(
    *,
    system: str,
    schema: type[BaseModel],
    model_id: str,
    thinking: ThinkingLevel | None,
    media_resolution: Literal["high", "medium"] | None,
    max_output_tokens: int,
) -> types.GenerateContentConfig:
    """The only ``GenerateContentConfig`` we ever send (D-04: no sampling knobs, no budget)."""
    guarded = guard_thinking(model_id, thinking)
    thinking_config = (
        types.ThinkingConfig(
            thinking_level=types.ThinkingLevel[guarded.value.upper()], include_thoughts=False
        )
        if guarded is not None
        else None
    )
    return types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_schema=schema,
        thinking_config=thinking_config,
        media_resolution=_MEDIA[media_resolution] if media_resolution else None,
        max_output_tokens=max_output_tokens,
    )


def build_contents(parts: Sequence[Part]) -> list[types.Part]:
    """Text parts first, media after, preserving order within each group (D-04)."""
    text = [types.Part.from_text(text=p.text or "") for p in parts if p.kind == "text"]
    media = [
        types.Part.from_bytes(
            data=p.data or b"", mime_type=p.mime_type or "application/octet-stream"
        )
        for p in parts
        if p.kind == "bytes"
    ]
    return [*text, *media]


def to_result(
    resp: types.GenerateContentResponse, model_id: str, schema: type[BaseModel]
) -> StructuredResult:
    """Blocked → ``blocked_reason``; ``MAX_TOKENS`` → ``incomplete``; ``resp.parsed`` → parsed."""
    um = resp.usage_metadata
    usage = Usage(
        input_tokens=(um.prompt_token_count or 0) if um else 0,
        output_tokens=(um.candidates_token_count or 0) if um else 0,
        thought_tokens=(um.thoughts_token_count or 0) if um else 0,
    )
    pf = resp.prompt_feedback
    if pf is not None and pf.block_reason and pf.block_reason.name not in _NOT_BLOCKED:
        return StructuredResult(
            parsed=None, raw_text=None, model_id=model_id, usage=usage,
            blocked_reason=contract_block_reason(pf.block_reason.name),
        )  # fmt: skip
    if not resp.candidates:
        return StructuredResult(
            parsed=None, raw_text=None, model_id=model_id, usage=usage, blocked_reason="other"
        )
    cand = resp.candidates[0]
    finish = cand.finish_reason.name if cand.finish_reason else None
    if finish in BLOCK_FINISH:
        return StructuredResult(
            parsed=None, raw_text=None, model_id=model_id, usage=usage,
            blocked_reason=contract_block_reason(finish), finish_reason=finish,
        )  # fmt: skip
    raw = resp.text if (cand.content and cand.content.parts) else None
    parsed: BaseModel | None = resp.parsed if isinstance(resp.parsed, schema) else None
    if parsed is None and raw:
        try:
            parsed = schema.model_validate_json(raw)
        except ValidationError:
            parsed = None
    incomplete = finish == "MAX_TOKENS" or (parsed is None and finish != "STOP")
    return StructuredResult(
        parsed=parsed,
        raw_text=None if parsed is not None else raw,
        model_id=model_id,
        usage=usage,
        blocked_reason=None,
        finish_reason=finish,
        incomplete=incomplete,
    )


class GeminiProvider:
    """``AIProvider`` for ``AI_PROVIDER=gemini`` (legacy path, D-05)."""

    name: Provider = Provider.gemini

    def __init__(
        self,
        slots: list[KeySlotConfig],
        settings: Settings,
        *,
        client_factory: ClientFactory | None = None,
    ) -> None:
        if not slots:
            raise ValueError("GeminiProvider needs at least one GEMINI_KEYS slot")
        self._settings = settings
        self.http_options = build_http_options(settings)
        factory = client_factory or default_client_factory
        self._clients: list[Any] = [
            factory(slot.key.get_secret_value(), self.http_options) for slot in slots
        ]
        self.last_latency_ms: int | None = None

    def model_for(self, tier: ModelTier) -> str:
        """Model ids come only from ``MODEL_PRO`` / ``MODEL_FAST`` (D-04)."""
        return self._settings.model_pro if tier is ModelTier.pro else self._settings.model_fast

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
        index = slot_index or 0
        if not 0 <= index < len(self._clients):
            raise ValueError(f"slot_index {index} out of range (0..{len(self._clients) - 1})")
        client = self._clients[index]
        model_id = self.model_for(tier)
        config = build_config(
            system=system,
            schema=schema,
            model_id=model_id,
            thinking=thinking,
            media_resolution=media_resolution,
            max_output_tokens=max_output_tokens,
        )
        t0 = time.monotonic()
        resp: types.GenerateContentResponse = await client.aio.models.generate_content(
            model=model_id, contents=build_contents(parts), config=config
        )
        self.last_latency_ms = int((time.monotonic() - t0) * 1000)
        return to_result(resp, model_id, schema)


def build_gemini_stack(
    settings: Settings,
    *,
    clock: Callable[[], datetime] | None = None,
    client_factory: ClientFactory | None = None,
) -> tuple[AIProvider, KeyPool | None]:
    """Provider + key pool for the lifespan (ARCHITECTURE §2.1 order: provider → keypool).

    ``AI_PROVIDER=gemini`` with ``GEMINI_KEYS`` → ``GeminiProvider`` + ``KeyPool`` (restored from
    ``var/keypool.json``). Zero slots, or ``gemini_interactions`` (LATER per D-05), →
    ``UnconfiguredGeminiProvider`` (every call 503 ``provider_not_configured``) and no pool.
    ``AI_PROVIDER=mock`` is not handled here (``MockProvider`` needs the fixture store).
    """
    if settings.ai_provider != "gemini" or not settings.gemini_keys:
        return UnconfiguredGeminiProvider(), None
    provider = GeminiProvider(list(settings.gemini_keys), settings, client_factory=client_factory)
    keypool = KeyPool.from_settings(settings, clock or (lambda: datetime.now(UTC)))
    return provider, keypool
