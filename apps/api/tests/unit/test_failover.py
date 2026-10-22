"""``ai/failover.AIService`` — D-07 budgets, rotation, degraded path and error mapping with a
scripted fake provider, an injected clock and a recorded ``sleep`` (AI_PROMPTS §8.4). WP1 lane 1B.
No network; the SDK's real ``errors.ClientError``/``ServerError`` are raised by the fake."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import httpx
import pytest
from google.genai import errors
from pydantic import BaseModel, SecretStr

from proxyhealth_api.ai.failover import (
    MAX_SLOT_ATTEMPTS,
    SAME_SLOT_RETRY_DELAY_S,
    AIService,
    GenerateOutcome,
    SchemaFallbackNeeded,
    UnconfiguredGeminiProvider,
    is_schema_rejection,
    is_thinking_level_rejection,
    message_of,
    parse_retry_after,
    status_of,
)
from proxyhealth_api.ai.keypool import KeyPool
from proxyhealth_api.ai.openai_compat import synthetic_slot
from proxyhealth_api.ai.provider import Part, StructuredResult, Task, Usage
from proxyhealth_api.ai.slow_errors import too_slow_error
from proxyhealth_api.contracts.enums import (
    ErrorCode,
    ModelQuality,
    ModelTier,
    Provider,
    ThinkingLevel,
    WarningCode,
)
from proxyhealth_api.contracts.model_out import RewriteOut
from proxyhealth_api.errors import ApiError
from proxyhealth_api.settings import KeySlotConfig, Settings

NOW = datetime(2026, 9, 24, 14, 0, 0, tzinfo=UTC)
PRO = "gemini-3.8-flash"
FAST = "gemini-3.5-flash-lite"
_STATUS = {400: "INVALID_ARGUMENT", 401: "UNAUTHENTICATED", 403: "PERMISSION_DENIED",
           429: "RESOURCE_EXHAUSTED", 500: "INTERNAL", 502: "BAD_GATEWAY",
           503: "UNAVAILABLE", 504: "DEADLINE_EXCEEDED"}  # fmt: skip

Script = list[StructuredResult | BaseException]


class FakeClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


class FakeProvider:
    """Plays a script of results/exceptions in order and records every call's arguments."""

    name: Provider = Provider.gemini

    def __init__(self, script: Script, *, on_call: Callable[[], None] | None = None) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []
        self._on_call = on_call

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
        self.calls.append(
            {
                "task": task, "tier": tier, "parts": parts, "system": system, "schema": schema,
                "thinking": thinking, "media_resolution": media_resolution,
                "max_output_tokens": max_output_tokens, "request_id": request_id,
                "slot_index": slot_index, "hints": hints,
            }
        )  # fmt: skip
        if self._on_call is not None:
            self._on_call()
        if not self.script:
            raise AssertionError("FakeProvider script exhausted: unexpected extra call")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def ok(model_id: str = FAST) -> StructuredResult:
    return StructuredResult(
        parsed=RewriteOut(sentence="This letter may ask for a reply."),
        raw_text=None,
        model_id=model_id,
        usage=Usage(input_tokens=10, output_tokens=5, thought_tokens=2),
        finish_reason="STOP",
    )


def blocked(reason: str = "spii") -> StructuredResult:
    return StructuredResult(None, None, PRO, Usage(), blocked_reason=reason, finish_reason=reason)


def incomplete() -> StructuredResult:
    return StructuredResult(None, "{\"sentence\": \"trunc", PRO, Usage(), None, "MAX_TOKENS", True)


def unparsed() -> StructuredResult:
    return StructuredResult(None, "not json", PRO, Usage(), None, "STOP", False)


def client_error(code: int, message: str = "upstream", *, retry_after: int | None = None) -> Any:
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else {}
    body = {"error": {"code": code, "message": message, "status": _STATUS.get(code, "ERROR")}}
    return errors.ClientError(code, body, httpx.Response(code, headers=headers))


def server_error(code: int, message: str = "unavailable") -> Any:
    body = {"error": {"code": code, "message": message, "status": _STATUS.get(code, "ERROR")}}
    return errors.ServerError(code, body, httpx.Response(code))


@dataclass
class Harness:
    service: AIService
    provider: FakeProvider
    keypool: KeyPool
    clock: FakeClock
    settings: Settings
    sleeps: list[float] = field(default_factory=list)


def build(
    tmp_path: Path,
    script: Script,
    *,
    slots: int = 2,
    billing: bool = True,
    allow_degraded: bool = True,
    deadline_s: int = 100,
    degraded_thinking: str = "medium",
    on_call: Callable[[], None] | None = None,
) -> Harness:
    keys = [
        KeySlotConfig(
            key=SecretStr(f"AIzaSy-test-key-{i}-Q{i}A{i}"), project=f"p{i}", billing=billing
        )
        for i in range(slots)
    ]
    settings = Settings(
        _env_file=None,
        ai_provider="gemini",
        gemini_keys=keys,
        var_dir=tmp_path / "var",
        allow_degraded=allow_degraded,
        failover_deadline_s=deadline_s,
        model_pro=PRO,
        model_fast=FAST,
        model_pro_degraded_thinking=ThinkingLevel(degraded_thinking),
    )
    clock = FakeClock()
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    keypool = KeyPool.from_settings(settings, clock)
    provider = FakeProvider(script, on_call=on_call)
    service = AIService(provider, keypool, settings, clock=clock, sleep=sleep)
    return Harness(service, provider, keypool, clock, settings, sleeps)


async def call(h: Harness, task: Task = Task.chat, **kw: Any) -> GenerateOutcome:
    return await h.service.generate(
        task=task,
        parts=[Part.of_text("user text"), Part.of_bytes(b"\x89PNG", "image/png")],
        system="SYSTEM PROMPT",
        schema=RewriteOut,
        request_id="req-1",
        **kw,
    )


def cool_all(h: Harness, tier: ModelTier, seconds: int = 17) -> None:
    for i in range(len(h.keypool.slots)):
        h.keypool.report(
            h.keypool.slot(i), tier, outcome="429", retry_after=seconds, error_text="rate"
        )


def slot_indexes(h: Harness) -> list[int | None]:
    return [c["slot_index"] for c in h.provider.calls]


# ----------------------------------------------------------------------- happy paths


async def test_success_on_first_slot_reports_ok_and_returns_full_quality(tmp_path: Path) -> None:
    h = build(tmp_path, [ok()])
    out = await call(h)
    assert out.quality is ModelQuality.full and out.warnings == [] and out.attempts == 1
    assert out.slot_index in (0, 1) and out.route.tier is ModelTier.fast
    assert out.route.model_id == FAST and out.result.parsed is not None
    ts = h.keypool.tier_state(out.slot_index or 0, ModelTier.fast)
    assert ts.rpd_count == 1 and ts.last_error_code is None
    c = h.provider.calls[0]
    assert (c["tier"], c["thinking"], c["max_output_tokens"]) == (ModelTier.fast, "low", 2048)
    assert c["system"] == "SYSTEM PROMPT" and c["schema"] is RewriteOut
    assert c["request_id"] == "req-1"


async def test_mock_provider_is_one_passthrough_call_without_a_slot(tmp_path: Path) -> None:
    provider = FakeProvider([ok()])
    provider.name = Provider.mock
    settings = Settings(_env_file=None, ai_provider="mock", var_dir=tmp_path / "var")
    service = AIService(provider, None, settings)
    out = await service.generate(
        task=Task.analyze_single, parts=[Part.of_text("x")], system="s", schema=RewriteOut,
        request_id="r", hints={"demo_sample_id": "medicaid_address_confirmation"},
    )  # fmt: skip
    assert out.slot_index is None and out.attempts == 1 and out.quality is ModelQuality.full
    assert provider.calls[0]["slot_index"] is None
    assert provider.calls[0]["hints"] == {"demo_sample_id": "medicaid_address_confirmation"}


async def test_gemini_without_keypool_uses_slot_zero(tmp_path: Path) -> None:
    provider = FakeProvider([ok()])
    settings = Settings(_env_file=None, ai_provider="gemini", var_dir=tmp_path / "var")
    out = await AIService(provider, None, settings).generate(
        task=Task.chat, parts=[Part.of_text("x")], system="s", schema=RewriteOut, request_id="r"
    )
    assert out.slot_index == 0 and provider.calls[0]["slot_index"] == 0


async def test_unconfigured_gemini_provider_is_503_provider_not_configured(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, ai_provider="gemini", var_dir=tmp_path / "var")
    service = AIService(UnconfiguredGeminiProvider(), None, settings)
    with pytest.raises(ApiError) as info:
        await service.generate(
            task=Task.chat, parts=[Part.of_text("x")], system="s", schema=RewriteOut, request_id="r"
        )
    assert info.value.status == 503 and info.value.code is ErrorCode.provider_not_configured


# ------------------------------------------------------------------ 429 → rotate + cool


async def test_429_rotates_to_the_next_slot_and_cools_the_first(tmp_path: Path) -> None:
    h = build(tmp_path, [client_error(429, "Resource exhausted", retry_after=17), ok()])
    out = await call(h)
    first, second = slot_indexes(h)
    assert first is not None and second is not None and first != second
    assert out.slot_index == second and out.attempts == 2 and out.quality is ModelQuality.full
    ts = h.keypool.tier_state(first, ModelTier.fast)
    assert ts.state == "cooling" and ts.cooldown_until == NOW + timedelta(seconds=17)
    assert ts.consecutive_429 == 1 and h.sleeps == []


async def test_429_retry_after_header_cools_for_exactly_n_seconds(tmp_path: Path) -> None:
    h = build(tmp_path, [client_error(429, "rate", retry_after=17), ok()], slots=2)
    await call(h)
    first = slot_indexes(h)[0]
    assert first is not None
    h.clock.advance(16)
    assert h.keypool.effective_state(first, ModelTier.fast) == "cooling"
    h.clock.advance(1)
    assert h.keypool.effective_state(first, ModelTier.fast) == "healthy"


async def test_429_without_retry_after_uses_the_backoff_table(tmp_path: Path) -> None:
    h = build(tmp_path, [client_error(429, "rate"), ok()])
    await call(h)
    first = slot_indexes(h)[0]
    assert first is not None
    assert h.keypool.tier_state(first, ModelTier.fast).cooldown_until == NOW + timedelta(seconds=30)


async def test_429_naming_the_daily_quota_marks_rpd_exhausted(tmp_path: Path) -> None:
    text = "Quota exceeded for quota metric 'GenerateRequestsPerDay' and limit 'requests per day'"
    h = build(tmp_path, [client_error(429, text, retry_after=41), ok()])
    await call(h)
    first = slot_indexes(h)[0]
    assert first is not None
    ts = h.keypool.tier_state(first, ModelTier.fast)
    assert ts.state == "rpd_exhausted" and ts.cooldown_until is None
    assert ts.rpd_reset_at == datetime(2026, 9, 25, 7, 0, tzinfo=UTC)


async def test_daily_quota_id_only_in_error_details_still_marks_rpd_exhausted(
    tmp_path: Path,
) -> None:
    # Gemini's generic message ("You exceeded your current quota") names the quota id only in
    # ``details`` (QuotaFailure violations), so the daily regex must see message + details.
    body = {
        "error": {
            "code": 429, "message": "You exceeded your current quota.",
            "status": "RESOURCE_EXHAUSTED",
            "details": [{"violations": [
                {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}
            ]}],
        }
    }  # fmt: skip
    exc = errors.ClientError(429, body, httpx.Response(429))
    h = build(tmp_path, [exc, ok()])
    await call(h)
    first = slot_indexes(h)[0]
    assert first is not None
    assert h.keypool.tier_state(first, ModelTier.fast).state == "rpd_exhausted"


# --------------------------------------------------------------- 5xx → retry / rotate


async def test_503_retries_the_same_slot_once_after_1_5s(tmp_path: Path) -> None:
    h = build(tmp_path, [server_error(503), ok()])
    out = await call(h)
    idx = slot_indexes(h)
    assert idx[0] == idx[1] and out.slot_index == idx[0] and out.attempts == 1
    assert h.sleeps == [SAME_SLOT_RETRY_DELAY_S] == [1.5]
    assert h.keypool.effective_state(idx[0] or 0, ModelTier.fast) == "healthy"


@pytest.mark.parametrize("code", [503, 504])
async def test_second_5xx_on_same_slot_moves_to_next_slot(tmp_path: Path, code: int) -> None:
    h = build(tmp_path, [server_error(code), server_error(code), ok()])
    out = await call(h)
    idx = slot_indexes(h)
    assert idx[0] == idx[1] and idx[2] != idx[0] and out.slot_index == idx[2]
    assert out.attempts == 2 and h.sleeps == [1.5]
    assert h.keypool.summary().healthy == 2  # 5xx never changes slot state
    assert h.keypool.tier_state(idx[0] or 0, ModelTier.fast).last_error_code == code


@pytest.mark.parametrize("code", [500, 502])
async def test_500_502_move_to_the_next_slot_without_a_same_slot_retry(
    tmp_path: Path, code: int
) -> None:
    h = build(tmp_path, [server_error(code), ok()])
    out = await call(h)
    idx = slot_indexes(h)
    assert idx[0] != idx[1] and out.attempts == 2 and h.sleeps == []


async def test_timeout_moves_to_the_next_slot(tmp_path: Path) -> None:
    h = build(tmp_path, [httpx.ReadTimeout("read timed out"), ok()])
    out = await call(h)
    idx = slot_indexes(h)
    assert idx[0] != idx[1] and out.attempts == 2
    assert h.keypool.summary().healthy == 2


async def test_unknown_exception_moves_to_the_next_slot(tmp_path: Path) -> None:
    h = build(tmp_path, [RuntimeError("connection reset"), ok()])
    out = await call(h)
    assert out.attempts == 2 and len({*slot_indexes(h)}) == 2


# ------------------------------------------------------------------------ 400 → abort


async def test_400_aborts_without_rotation(tmp_path: Path) -> None:
    h = build(tmp_path, [client_error(400, "Invalid argument: contents must not be empty")])
    with pytest.raises(ApiError) as info:
        await call(h)
    err = info.value
    assert err.status == 400 and err.code is ErrorCode.invalid_request
    assert err.details == {"upstream": 400} and err.user_message_key == "err.invalid_request"
    assert len(h.provider.calls) == 1  # no second slot was tried
    first = slot_indexes(h)[0]
    assert first is not None
    ts = h.keypool.tier_state(first, ModelTier.fast)
    assert ts.state == "healthy" and ts.last_error_code == 400


async def test_400_schema_rejection_on_analyze_single_raises_schema_fallback(
    tmp_path: Path,
) -> None:
    h = build(tmp_path, [client_error(400, "response_schema: too many states for serving")])
    with pytest.raises(SchemaFallbackNeeded):
        await call(h, Task.analyze_single, pages=3)
    assert len(h.provider.calls) == 1
    assert h.keypool.summary().healthy == 2


async def test_400_schema_rejection_on_another_task_is_a_plain_400(tmp_path: Path) -> None:
    h = build(tmp_path, [client_error(400, "Unsupported schema nesting")])
    with pytest.raises(ApiError) as info:
        await call(h, Task.troubleshoot)
    assert info.value.status == 400 and len(h.provider.calls) == 1


# ------------------------------------------------------------------ 401/403 → disable


@pytest.mark.parametrize("code", [401, 403])
async def test_401_403_disable_the_slot_and_rotate(tmp_path: Path, code: int) -> None:
    h = build(tmp_path, [client_error(code, "API key not valid"), ok()])
    out = await call(h)
    first, second = slot_indexes(h)
    assert first is not None and first != second and out.slot_index == second
    ts = h.keypool.tier_state(first, ModelTier.fast)
    assert ts.state == "disabled" and ts.last_error_code == code
    assert h.keypool.acquire(ModelTier.fast, exclude={second or 0}) is None


# ------------------------------------------------------------------- result checks


async def test_blocked_result_is_422_and_never_retried_on_another_key(tmp_path: Path) -> None:
    h = build(tmp_path, [blocked("spii")])
    with pytest.raises(ApiError) as info:
        await call(h, Task.troubleshoot)
    err = info.value
    assert err.status == 422 and err.code is ErrorCode.content_blocked
    assert err.details == {"block_reason": "spii"}
    assert len(h.provider.calls) == 1
    first = slot_indexes(h)[0]
    assert first is not None
    assert h.keypool.tier_state(first, ModelTier.pro).rpd_count == 1  # the call still counted


async def test_incomplete_analyze_single_raises_schema_fallback(tmp_path: Path) -> None:
    h = build(tmp_path, [incomplete()])
    with pytest.raises(SchemaFallbackNeeded, match="incomplete"):
        await call(h, Task.analyze_single)
    assert len(h.provider.calls) == 1


async def test_unparsed_analyze_single_raises_schema_fallback(tmp_path: Path) -> None:
    h = build(tmp_path, [unparsed()])
    with pytest.raises(SchemaFallbackNeeded, match="unparsed"):
        await call(h, Task.analyze_single)


@pytest.mark.parametrize("task", [Task.transcribe, Task.explain, Task.troubleshoot, Task.chat])
async def test_incomplete_on_other_tasks_is_502_model_output_invalid(
    tmp_path: Path, task: Task
) -> None:
    h = build(tmp_path, [incomplete()])
    with pytest.raises(ApiError) as info:
        await call(h, task)
    assert info.value.status == 502 and info.value.code is ErrorCode.model_output_invalid
    assert len(h.provider.calls) == 1


async def test_fast_task_unparsed_is_502_for_callers_to_fall_back(tmp_path: Path) -> None:
    h = build(tmp_path, [unparsed()])
    with pytest.raises(ApiError) as info:
        await call(h, Task.phrasing_rewrite)
    assert info.value.code is ErrorCode.model_output_invalid


# ------------------------------------------------------------------ degraded path (D-07)


async def test_all_pro_slots_cooling_runs_degraded_on_the_fast_model(tmp_path: Path) -> None:
    h = build(tmp_path, [ok()])
    cool_all(h, ModelTier.pro, seconds=300)
    out = await call(h, Task.analyze_single, pages=2, is_pdf=True)
    assert out.quality is ModelQuality.degraded
    assert out.warnings == [WarningCode.degraded_model]
    assert out.route.tier is ModelTier.fast and out.route.model_id == FAST
    assert out.route.thinking is ThinkingLevel.medium  # MODEL_PRO_DEGRADED_THINKING
    assert out.route.media_resolution == "medium" and out.route.max_output_tokens == 16384
    assert out.attempts == 1 and len(h.provider.calls) == 1
    c = h.provider.calls[0]
    assert c["tier"] is ModelTier.fast and c["thinking"] is ThinkingLevel.medium
    assert out.slot_index is not None
    assert h.keypool.tier_state(out.slot_index, ModelTier.fast).rpd_count == 1


async def test_degraded_after_three_failed_pro_attempts(tmp_path: Path) -> None:
    script: Script = [client_error(429, "rate") for _ in range(3)]
    h = build(tmp_path, [*script, ok()], slots=3)
    out = await call(h, Task.troubleshoot)
    assert out.quality is ModelQuality.degraded and out.attempts == 4
    assert out.warnings == [WarningCode.degraded_model]
    assert [c["tier"] for c in h.provider.calls] == [ModelTier.pro] * 3 + [ModelTier.fast]
    assert h.keypool.counts(ModelTier.pro)["cooling"] == 3
    assert h.keypool.counts(ModelTier.fast)["healthy"] == 3


async def test_degraded_thinking_rejection_retries_once_with_low(tmp_path: Path) -> None:
    rejection = client_error(
        400, "Invalid value at 'generation_config.thinking_config.thinking_level'"
    )
    h = build(tmp_path, [rejection, ok()])
    cool_all(h, ModelTier.pro)
    out = await call(h, Task.analyze_single)
    assert out.quality is ModelQuality.degraded and out.route.thinking is ThinkingLevel.low
    assert [c["thinking"] for c in h.provider.calls] == [ThinkingLevel.medium, ThinkingLevel.low]
    idx = slot_indexes(h)
    assert idx[0] == idx[1] and h.sleeps == []  # same slot, no delay
    assert out.attempts == 1


async def test_degraded_second_thinking_rejection_is_a_400(tmp_path: Path) -> None:
    h = build(tmp_path, [client_error(400, "thinking_level"), client_error(400, "thinking_level")])
    cool_all(h, ModelTier.pro)
    with pytest.raises(ApiError) as info:
        await call(h, Task.analyze_single)
    assert info.value.status == 400 and len(h.provider.calls) == 2


async def test_thinking_rejection_on_a_full_quality_call_is_a_plain_400(tmp_path: Path) -> None:
    h = build(tmp_path, [client_error(400, "thinking_level is not supported")])
    with pytest.raises(ApiError) as info:
        await call(h, Task.chat)
    assert info.value.status == 400 and len(h.provider.calls) == 1


async def test_degraded_disabled_by_settings_is_429_quota_exhausted(tmp_path: Path) -> None:
    h = build(tmp_path, [], allow_degraded=False)
    cool_all(h, ModelTier.pro, seconds=120)
    with pytest.raises(ApiError) as info:
        await call(h, Task.analyze_single)
    err = info.value
    assert err.status == 429 and err.code is ErrorCode.quota_exhausted and err.key_exhausted
    assert err.retry_after == 120 and h.provider.calls == []
    assert err.user_message_key == "err.quota_exhausted"
    assert err.details == {
        "tier": "pro", "slots_total": 2, "slots_cooling": 2, "slots_rpd_exhausted": 0,
        "slots_disabled": 0,
    }  # fmt: skip


@pytest.mark.parametrize("task", [Task.chat, Task.tag, Task.langpack_chunk])
async def test_fast_tasks_never_escalate_to_pro(tmp_path: Path, task: Task) -> None:
    h = build(tmp_path, [])
    cool_all(h, ModelTier.fast, seconds=45)
    with pytest.raises(ApiError) as info:
        await call(h, task)
    assert info.value.status == 429 and info.value.retry_after == 45 and h.provider.calls == []
    assert h.keypool.counts(ModelTier.pro)["healthy"] == 2  # pro slots were never touched


async def test_degraded_with_fast_slots_also_unavailable_is_429(tmp_path: Path) -> None:
    h = build(tmp_path, [])
    cool_all(h, ModelTier.pro, seconds=100)
    cool_all(h, ModelTier.fast, seconds=200)
    with pytest.raises(ApiError) as info:
        await call(h, Task.analyze_single)
    assert info.value.status == 429 and info.value.retry_after == 100  # the pro tier's cooldown
    assert h.provider.calls == []


async def test_rpd_exhausted_pool_reports_time_to_pacific_midnight(tmp_path: Path) -> None:
    h = build(tmp_path, [], allow_degraded=False)
    for i in range(2):
        h.keypool.report(
            h.keypool.slot(i), ModelTier.pro, outcome="429", retry_after=None,
            error_text="quota metric GenerateRequestsPerDay",
        )  # fmt: skip
    with pytest.raises(ApiError) as info:
        await call(h, Task.explain)
    midnight = datetime(2026, 9, 25, 7, 0, tzinfo=UTC)
    assert info.value.retry_after == int((midnight - NOW).total_seconds())
    assert info.value.details is not None and info.value.details["slots_rpd_exhausted"] == 2


# ------------------------------------------------------------ per-request budget (D-07)


async def test_at_most_three_slot_attempts_per_request(tmp_path: Path) -> None:
    script: Script = [client_error(429, "rate") for _ in range(3)]
    h = build(tmp_path, [*script, ok()], slots=5)
    with pytest.raises(ApiError) as info:
        await call(h, Task.chat)  # fast tier: no degraded path, so the budget ends the request
    assert MAX_SLOT_ATTEMPTS == 3 and len(h.provider.calls) == 3
    assert len(set(slot_indexes(h))) == 3
    assert info.value.status == 429 and info.value.code is ErrorCode.quota_exhausted
    assert info.value.retry_after == 30  # first backoff step of the cooling slots
    counts = h.keypool.counts(ModelTier.fast)
    assert (counts["healthy"], counts["cooling"]) == (2, 3)


async def test_failover_deadline_stops_further_attempts(tmp_path: Path) -> None:
    clocks: list[FakeClock] = []

    def slow_call() -> None:
        clocks[0].advance(11)  # every upstream call outlives the whole deadline

    h = build(tmp_path, [server_error(500), ok()], slots=3, deadline_s=10, on_call=slow_call)
    clocks.append(h.clock)
    with pytest.raises(ApiError) as info:
        await call(h, Task.chat)
    assert len(h.provider.calls) == 1  # a second slot was never tried
    assert info.value.status == 503 and info.value.code is ErrorCode.upstream_unavailable


async def test_deadline_also_skips_the_degraded_attempt(tmp_path: Path) -> None:
    clocks: list[FakeClock] = []

    def slow_call() -> None:
        clocks[0].advance(40)

    script: Script = [client_error(429, "rate") for _ in range(3)]
    h = build(tmp_path, [*script, ok()], slots=3, deadline_s=100, on_call=slow_call)
    clocks.append(h.clock)
    with pytest.raises(ApiError) as info:
        await call(h, Task.analyze_single)
    assert len(h.provider.calls) == 3  # 3 × 40 s > 100 s: no fourth (degraded) call
    assert info.value.status == 429 and info.value.key_exhausted


async def test_shared_request_deadline_spans_several_generate_calls(tmp_path: Path) -> None:
    # AI_PROMPTS §8.4/§9.4: the two-call fallback and the injection re-run share one budget.
    h = build(tmp_path, [ok(), ok()], deadline_s=100)
    deadline = h.service.request_deadline()
    assert deadline == NOW + timedelta(seconds=100)
    first = await call(h, Task.chat, deadline_at=deadline)
    assert first.attempts == 1
    h.clock.advance(100)  # the first call (or a slow upstream) used the whole budget
    with pytest.raises(ApiError) as info:
        await call(h, Task.chat, deadline_at=deadline)
    assert len(h.provider.calls) == 1  # nothing sent once the shared deadline passed
    assert info.value.status == 503 and info.value.code is ErrorCode.upstream_unavailable
    assert info.value.retry_after == 30 and not info.value.key_exhausted


async def test_without_deadline_at_each_call_gets_a_fresh_budget(tmp_path: Path) -> None:
    h = build(tmp_path, [ok(), ok()], deadline_s=100)
    await call(h, Task.chat)
    h.clock.advance(150)
    assert (await call(h, Task.chat)).attempts == 1


async def test_only_transient_5xx_failures_end_as_503_upstream_unavailable(tmp_path: Path) -> None:
    h = build(tmp_path, [server_error(500), server_error(502)], slots=2)
    with pytest.raises(ApiError) as info:
        await call(h, Task.chat)
    err = info.value
    assert err.status == 503 and err.code is ErrorCode.upstream_unavailable
    assert err.retry_after == 30 and err.key_exhausted is False
    assert err.details == {"tier": "fast", "attempts": 2}
    assert h.keypool.summary().healthy == 2  # nothing was benched


async def test_mixed_5xx_and_429_failures_end_as_429_key_exhausted(tmp_path: Path) -> None:
    h = build(tmp_path, [server_error(500), client_error(429, "rate", retry_after=25)], slots=2)
    with pytest.raises(ApiError) as info:
        await call(h, Task.chat)
    err = info.value
    assert err.status == 429 and err.key_exhausted and err.retry_after == 25
    assert err.details is not None and err.details["slots_cooling"] == 1


async def test_every_slot_disabled_is_429_with_the_default_retry_after(tmp_path: Path) -> None:
    h = build(tmp_path, [client_error(403, "denied"), client_error(401, "denied")], slots=2)
    with pytest.raises(ApiError) as info:
        await call(h, Task.chat)
    err = info.value
    assert err.status == 429 and err.retry_after == 60  # nothing is cooling: default 60 s
    assert err.details is not None and err.details["slots_disabled"] == 2
    assert h.keypool.summary().disabled == 2


async def test_no_slots_configured_is_429_key_exhausted(tmp_path: Path) -> None:
    provider = FakeProvider([ok()])
    settings = Settings(_env_file=None, ai_provider="gemini", var_dir=tmp_path / "var")
    service = AIService(provider, KeyPool([], tmp_path / "var", FakeClock()), settings)
    with pytest.raises(ApiError) as info:
        await service.generate(
            task=Task.chat, parts=[Part.of_text("x")], system="s", schema=RewriteOut, request_id="r"
        )
    assert info.value.status == 429 and info.value.key_exhausted and provider.calls == []


# ------------------------------------------- openai_compat: "too slow", not "try again later"


def compat_harness(tmp_path: Path, script: Script) -> Harness:
    settings = Settings(
        _env_file=None, ai_provider="openai_compat", openai_compat_data_tier="local",
        openai_compat_model_label="Qwen", var_dir=tmp_path / "var",
    )  # fmt: skip
    clock = FakeClock()
    keypool = KeyPool(
        [synthetic_slot(settings)], settings.var_dir, clock, data_use_tier=settings.data_use_tier
    )
    provider = FakeProvider(script)
    provider.name = Provider.openai_compat
    service = AIService(provider, keypool, settings, clock=clock)
    return Harness(service, provider, keypool, clock, settings)


async def test_openai_compat_deadline_refusal_is_ai_too_slow(tmp_path: Path) -> None:
    # Two-call mode: transcribe used the request's budget, so explain is never sent.
    h = compat_harness(tmp_path, [ok()])
    deadline = h.service.request_deadline()
    assert h.service.remaining_s(deadline) == 310.0
    h.clock.advance(311)
    assert h.service.remaining_s(deadline) == -1.0
    with pytest.raises(ApiError) as info:
        await call(h, Task.explain, deadline_at=deadline)
    err = info.value
    assert (err.status, err.code, err.user_message_key) == (
        503, ErrorCode.upstream_unavailable, "err.ai_too_slow",
    )  # fmt: skip
    assert err.retry_after is None and not err.key_exhausted
    assert err.details == {"reason": "deadline", "timeout_s": 310}
    assert h.provider.calls == []
    with pytest.raises(ApiError) as chat_info:
        await call(h, Task.chat, deadline_at=deadline)
    assert chat_info.value.user_message_key == "err.upstream_unavailable"  # not a paper


async def test_openai_compat_timeout_error_passes_through_unchanged(tmp_path: Path) -> None:
    slow = too_slow_error(Task.analyze_single, 300, reason="ai_timeout")
    h = compat_harness(tmp_path, [slow])
    with pytest.raises(ApiError) as info:
        await call(h, Task.analyze_single)
    assert info.value is slow and len(h.provider.calls) == 1
    assert h.keypool.summary().healthy == 1  # the slot is not benched


async def test_gemini_timeout_still_upstream_unavailable_default_key(tmp_path: Path) -> None:
    h = build(tmp_path, [TimeoutError(), TimeoutError()], slots=2)
    with pytest.raises(ApiError) as info:
        await call(h, Task.analyze_single)
    err = info.value
    assert (err.status, err.code, err.retry_after) == (503, ErrorCode.upstream_unavailable, 30)
    assert err.user_message_key == "err.upstream_unavailable"
    h2 = build(tmp_path / "b", [ok()], deadline_s=100)
    deadline = h2.service.request_deadline()
    h2.clock.advance(100)
    with pytest.raises(ApiError) as late:
        await call(h2, Task.explain, deadline_at=deadline)
    assert late.value.user_message_key == "err.upstream_unavailable"


# ------------------------------------------------------------------- helper functions


def test_status_of_reads_code_or_status_code() -> None:
    assert status_of(client_error(429)) == 429
    assert status_of(server_error(503)) == 503

    class InteractionsStyle(Exception):
        status_code = 502

    class StringCode(Exception):
        code = "429"

    assert status_of(InteractionsStyle()) == 502  # D-05: the other SDK hierarchy
    assert status_of(StringCode()) is None
    assert status_of(httpx.ReadTimeout("read timed out")) is None
    assert status_of(RuntimeError("x")) is None


def test_message_of_prefers_the_sdk_message() -> None:
    assert message_of(client_error(400, "Invalid argument")) == "Invalid argument"
    assert message_of(RuntimeError("boom")) == "boom"


def test_parse_retry_after_header_then_retry_delay_detail() -> None:
    assert parse_retry_after(client_error(429, retry_after=17)) == 17
    assert parse_retry_after(client_error(429)) is None
    assert parse_retry_after(RuntimeError("x")) is None
    detail = {
        "error": {
            "code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED",
            "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo",
                         "retryDelay": "17.5s"}],
        }
    }  # fmt: skip
    assert parse_retry_after(errors.ClientError(429, detail, httpx.Response(429))) == 18
    http_date = httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
    body = {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}}
    assert parse_retry_after(errors.ClientError(429, body, http_date)) is None  # HTTP-date form


def test_schema_and_thinking_rejection_patterns() -> None:
    for text in (
        "response_schema too complex",
        "Unsupported field type",
        "too many states for serving",
        "schema nesting depth exceeded",
    ):
        assert is_schema_rejection(text)
    assert not is_schema_rejection("contents must not be empty")
    for text in (
        "thinking_level",
        "thinking level not supported",
        "thinkingLevel MINIMAL",
        "generation_config.thinking_config",
    ):
        assert is_thinking_level_rejection(text)
    assert not is_thinking_level_rejection("response_schema")
