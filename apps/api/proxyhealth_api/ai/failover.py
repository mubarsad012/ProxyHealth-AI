"""The only path from pipelines to providers (BUILD_PLAN §4.1; AI_PROMPTS §8.4; D-07).

``AIService.generate`` applies the per-request budget (≤ 3 slot attempts, ``FAILOVER_DEADLINE_S``),
the D-07 transitions (429 rotation, 503/504 same-slot retry, 500/502 next slot, 400 abort,
401/403 disable), the degraded path (``quality="degraded"``, ``warnings=[degraded_model]``) and the
result checks (blocked → 422, incomplete → ``SchemaFallbackNeeded`` / 502). Every attempt logs
allow-listed fields only — never content, never a key.
"""

import asyncio
import re
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx
from pydantic import BaseModel

from proxyhealth_api.ai.keypool import KeyPool, Slot
from proxyhealth_api.ai.provider import AIProvider, Part, StructuredResult, Task
from proxyhealth_api.ai.routing import DEGRADABLE_TASKS, RouteConfig, route
from proxyhealth_api.contracts.enums import (
    ErrorCode,
    ModelQuality,
    ModelTier,
    Provider,
    ThinkingLevel,
    WarningCode,
)
from proxyhealth_api.errors import ApiError
from proxyhealth_api.logging_ import log_event
from proxyhealth_api.settings import Settings

MAX_SLOT_ATTEMPTS = 3
SAME_SLOT_RETRY_DELAY_S = 1.5
UPSTREAM_UNAVAILABLE_RETRY_AFTER_S = 30
DEFAULT_QUOTA_RETRY_AFTER_S = 60

# AI_PROMPTS §9.4: an upstream 400 that names the schema → two-call fallback (analyze_single).
SCHEMA_REJECTION_RE = re.compile(
    r"schema|response_schema|Unsupported|too many states|nesting", re.I
)
# D-04: the API refused the degraded thinking level → one retry with ``low``.
THINKING_REJECTION_RE = re.compile(r"thinking[_ ]?level|thinking_config|thinkingLevel", re.I)
_RETRY_DELAY_RE = re.compile(r"retry(?:Delay|[ _-]?in)\D{0,4}(\d+(?:\.\d+)?)\s*s", re.I)

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], datetime]


@dataclass
class GenerateOutcome:
    result: StructuredResult
    route: RouteConfig
    quality: ModelQuality
    slot_index: int | None
    attempts: int
    warnings: list[WarningCode] = field(default_factory=list)


class SchemaFallbackNeeded(Exception):
    """Single-call output rejected/incomplete → the pipeline switches to ``two_call``."""


class UnconfiguredGeminiProvider:
    """``AI_PROVIDER=gemini`` without a usable ``GeminiProvider``/``KeyPool``: every call → 503."""

    name: Provider = Provider.gemini

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
        raise ApiError(
            ErrorCode.provider_not_configured,
            503,
            "AI_PROVIDER=gemini but no usable provider is configured (GEMINI_KEYS is empty).",
            retry_after=60,
        )


# ------------------------------------------------------------------ error introspection


def status_of(exc: BaseException) -> int | None:
    """Upstream HTTP status from either SDK hierarchy (D-05); ``None`` for timeouts etc."""
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    return code if isinstance(code, int) and not isinstance(code, bool) else None


def message_of(exc: BaseException) -> str:
    message = getattr(exc, "message", None)
    return message if isinstance(message, str) and message else str(exc)


def quota_text_of(exc: BaseException) -> str:
    """Message plus ``details`` for the daily-quota regex (D-07): Gemini names the quota id
    (e.g. ``GenerateRequestsPerDayPerProjectPerModel``) in ``details``, not always in the message.
    Used only in memory for that match; never logged or persisted."""
    details = getattr(exc, "details", None)
    text = message_of(exc)
    return f"{text} {details}" if details is not None else text


def parse_retry_after(exc: BaseException) -> int | None:
    """``Retry-After`` header (integer seconds) or a ``retryDelay: "17s"`` detail; else ``None``."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        try:
            value = headers.get("Retry-After")
        except (AttributeError, TypeError):
            value = None
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    details = getattr(exc, "details", None)
    if details is not None:
        match = _RETRY_DELAY_RE.search(str(details))
        if match:
            return max(int(float(match.group(1)) + 0.999), 1)
    return None


def is_schema_rejection(text: str) -> bool:
    return bool(SCHEMA_REJECTION_RE.search(text))


def is_thinking_level_rejection(text: str) -> bool:
    return bool(THINKING_REJECTION_RE.search(text))


def _is_timeout(exc: BaseException) -> bool:
    return isinstance(exc, TimeoutError | asyncio.TimeoutError | httpx.TimeoutException)


class _NextSlot(Exception):
    """Internal: this slot failed in a way that moves the request to the next slot."""

    def __init__(self, kind: Literal["429", "5xx", "4xx_fatal"]) -> None:
        super().__init__(kind)
        self.kind = kind


# ------------------------------------------------------------------------------ service


class AIService:
    def __init__(
        self,
        provider: AIProvider,
        keypool: KeyPool | None,
        settings: Settings,
        *,
        clock: Clock | None = None,
        sleep: Sleep | None = None,
    ) -> None:
        self.provider = provider
        self.keypool = keypool
        self.settings = settings
        self._clock: Clock = clock or (lambda: datetime.now(UTC))
        self._sleep: Sleep = sleep or asyncio.sleep

    # ------------------------------------------------------------------- public API

    def request_deadline(self) -> datetime:
        """``now + FAILOVER_DEADLINE_S`` on this service's clock. A pipeline that makes several
        ``generate`` calls for one request (two-call fallback, injection re-run; AI_PROMPTS §8.4,
        §9.4) takes this once and passes it as ``deadline_at`` so they share one budget."""
        return self._clock() + timedelta(seconds=self.settings.failover_deadline_s)

    async def generate(
        self,
        *,
        task: Task,
        parts: Sequence[Part],
        system: str,
        schema: type[BaseModel],
        pages: int = 1,
        is_pdf: bool = False,
        request_id: str,
        hints: Mapping[str, str] | None = None,
        deadline_at: datetime | None = None,
    ) -> GenerateOutcome:
        cfg = route(task, pages=pages, is_pdf=is_pdf, degraded=False, settings=self.settings)
        call = _Call(task, parts, system, schema, request_id, hints)
        if self.keypool is None or self.provider.name is Provider.mock:
            slot_index = None if self.provider.name is Provider.mock else 0
            res = await self._invoke(call, cfg, slot_index)
            return self._finish(task, res, cfg, slot_index, 1, ModelQuality.full, [])

        keypool = self.keypool
        deadline = deadline_at if deadline_at is not None else self.request_deadline()
        attempts = 0
        tried: set[int] = set()
        failures: list[str] = []
        while attempts < MAX_SLOT_ATTEMPTS and self._clock() < deadline:
            slot = keypool.acquire(cfg.tier, exclude=tried)
            if slot is None:
                break
            tried.add(slot.index)
            attempts += 1
            try:
                res, cfg = await self._attempt(call, cfg, slot, degraded=False)
            except _NextSlot as nxt:
                failures.append(nxt.kind)
                continue
            keypool.report(slot, cfg.tier, outcome="ok")
            return self._finish(task, res, cfg, slot.index, attempts, ModelQuality.full, [])

        # No slot served us: degraded path (D-07), then the honest error.
        if (
            cfg.tier is ModelTier.pro
            and self.settings.allow_degraded
            and task in DEGRADABLE_TASKS
            and self._clock() < deadline
        ):
            dcfg = route(task, pages=pages, is_pdf=is_pdf, degraded=True, settings=self.settings)
            fast_slot = keypool.acquire(dcfg.tier)
            if fast_slot is not None:
                attempts += 1
                try:
                    res, dcfg = await self._attempt(call, dcfg, fast_slot, degraded=True)
                except _NextSlot as nxt:
                    failures.append(nxt.kind)
                else:
                    keypool.report(fast_slot, dcfg.tier, outcome="ok")
                    return self._finish(
                        task, res, dcfg, fast_slot.index, attempts, ModelQuality.degraded,
                        [WarningCode.degraded_model],
                    )  # fmt: skip
        raise self._exhausted_error(cfg.tier, failures, timed_out=self._clock() >= deadline)

    # ------------------------------------------------------------------- one slot

    async def _attempt(
        self, call: "_Call", cfg: RouteConfig, slot: Slot, *, degraded: bool
    ) -> tuple[StructuredResult, RouteConfig]:
        """One slot attempt with the D-07 error mapping; raises ``_NextSlot`` to rotate."""
        keypool = self.keypool
        assert keypool is not None
        thinking_retried = False
        same_slot_retried = False
        while True:
            try:
                return await self._invoke(call, cfg, slot.index), cfg
            except ApiError:
                raise
            except Exception as exc:  # noqa: BLE001 - D-05: both SDK hierarchies, timeouts
                code = status_of(exc)
                text = message_of(exc)
                if code == 429:
                    keypool.report(
                        slot, cfg.tier, outcome="429",
                        retry_after=parse_retry_after(exc), error_text=quota_text_of(exc),
                    )  # fmt: skip
                    raise _NextSlot("429") from None
                if code in (503, 504):
                    keypool.report(slot, cfg.tier, outcome="5xx", code=code)
                    if same_slot_retried:
                        raise _NextSlot("5xx") from None
                    same_slot_retried = True
                    await self._sleep(SAME_SLOT_RETRY_DELAY_S)
                    continue
                if code in (500, 502):
                    keypool.report(slot, cfg.tier, outcome="5xx", code=code)
                    raise _NextSlot("5xx") from None
                if code == 400:
                    if degraded and not thinking_retried and is_thinking_level_rejection(text):
                        thinking_retried = True
                        cfg = replace(cfg, thinking=ThinkingLevel.low)
                        continue
                    if call.task is Task.analyze_single and is_schema_rejection(text):
                        raise SchemaFallbackNeeded(
                            "upstream 400 rejected the response schema"
                        ) from None
                    keypool.report(slot, cfg.tier, outcome="400", code=400)
                    raise ApiError(
                        ErrorCode.invalid_request,
                        400,
                        "The AI service rejected the request.",
                        details={"upstream": 400},
                    ) from None
                if code in (401, 403):
                    keypool.report(slot, cfg.tier, outcome="4xx_fatal", code=code)
                    raise _NextSlot("4xx_fatal") from None
                keypool.report(
                    slot, cfg.tier, outcome="5xx", code=code if code is not None else 504
                )
                if code is None and not _is_timeout(exc):
                    log_event(
                        request_id=call.request_id, route=f"upstream.{call.task.value}",
                        error_code="upstream_exception", slot_index=slot.index,
                    )  # fmt: skip
                raise _NextSlot("5xx") from None

    async def _invoke(
        self, call: "_Call", cfg: RouteConfig, slot_index: int | None
    ) -> StructuredResult:
        """One provider call with the content-free upstream log line (ARCHITECTURE §2.1)."""
        t0 = time.monotonic()
        try:
            res = await self.provider.generate_structured(
                task=call.task,
                tier=cfg.tier,
                parts=call.parts,
                system=call.system,
                schema=call.schema,
                thinking=cfg.thinking,
                media_resolution=cfg.media_resolution,
                max_output_tokens=cfg.max_output_tokens,
                request_id=call.request_id,
                slot_index=slot_index,
                hints=call.hints,
            )
        except Exception as exc:
            code = status_of(exc) or getattr(exc, "status", None)
            log_event(
                request_id=call.request_id, route=f"upstream.{call.task.value}", tier=cfg.tier,
                model=cfg.model_id, slot_index=slot_index, provider=self.provider.name,
                latency_ms=int((time.monotonic() - t0) * 1000),
                status=code if isinstance(code, int) else None,
                error_code=f"upstream_{code}" if isinstance(code, int) else "upstream_exception",
            )  # fmt: skip
            raise
        log_event(
            request_id=call.request_id, route=f"upstream.{call.task.value}", tier=cfg.tier,
            model=cfg.model_id, slot_index=slot_index, provider=self.provider.name,
            latency_ms=int((time.monotonic() - t0) * 1000), status=200,
            input_tokens=res.usage.input_tokens, output_tokens=res.usage.output_tokens,
            thought_tokens=res.usage.thought_tokens,
        )  # fmt: skip
        return res

    # ------------------------------------------------------------------- results

    def _finish(
        self,
        task: Task,
        res: StructuredResult,
        cfg: RouteConfig,
        slot_index: int | None,
        attempts: int,
        quality: ModelQuality,
        warnings: list[WarningCode],
    ) -> GenerateOutcome:
        if res.blocked_reason:
            raise ApiError(
                ErrorCode.content_blocked,
                422,
                "The AI service blocked this content.",
                details={"block_reason": res.blocked_reason.lower()},
            )
        if res.incomplete or res.parsed is None:
            if task is Task.analyze_single:
                reason = "incomplete" if res.incomplete else "unparsed"
                raise SchemaFallbackNeeded(reason)
            raise ApiError(
                ErrorCode.model_output_invalid,
                502,
                "The AI service returned an unusable answer.",
                details={"incomplete": res.incomplete, "finish_reason": res.finish_reason or ""},
            )
        return GenerateOutcome(
            result=res,
            route=cfg,
            quality=quality,
            slot_index=slot_index,
            attempts=attempts,
            warnings=list(warnings),
        )

    def _exhausted_error(
        self, tier: ModelTier, failures: list[str], *, timed_out: bool = False
    ) -> ApiError:
        keypool = self.keypool
        assert keypool is not None
        if (failures or timed_out) and "429" not in failures and "4xx_fatal" not in failures:
            # Only transient upstream failures (or the request's deadline ran out) while the
            # slots are still healthy → 503, not a misleading "keys exhausted" 429.
            return ApiError(
                ErrorCode.upstream_unavailable,
                503,
                "The AI service is temporarily unavailable.",
                retry_after=UPSTREAM_UNAVAILABLE_RETRY_AFTER_S,
                details={"tier": tier.value, "attempts": len(failures)},
            )
        counts = keypool.counts(tier)
        retry_after = keypool.min_cooldown_seconds(tier) or DEFAULT_QUOTA_RETRY_AFTER_S
        return ApiError(
            ErrorCode.quota_exhausted,
            429,
            "Every AI key is cooling down or exhausted.",
            retry_after=retry_after,
            key_exhausted=True,
            details={
                "tier": tier.value,
                "slots_total": len(keypool.slots),
                "slots_cooling": counts["cooling"],
                "slots_rpd_exhausted": counts["rpd_exhausted"],
                "slots_disabled": counts["disabled"],
            },
        )


@dataclass(frozen=True)
class _Call:
    task: Task
    parts: Sequence[Part]
    system: str
    schema: type[BaseModel]
    request_id: str
    hints: Mapping[str, str] | None
