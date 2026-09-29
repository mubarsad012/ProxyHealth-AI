"""``ai/gemini.GeminiProvider`` with a fake client (AI_PROMPTS §9.5; BUILD_PLAN §5.2 step 3).
WP1 lane 1B. No network: ``FakeClient.aio.models.generate_content`` records its kwargs and
returns a canned ``types.GenerateContentResponse``; upstream errors are the SDK's own
``errors.ClientError`` so the failover integration test exercises the real hierarchy."""

import importlib.util
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
from google.genai import errors, types
from pydantic import BaseModel, SecretStr

from proxyhealth_api.ai import gemini
from proxyhealth_api.ai.failover import AIService
from proxyhealth_api.ai.gemini import (
    GeminiProvider,
    build_config,
    build_contents,
    contract_block_reason,
    to_result,
)
from proxyhealth_api.ai.keypool import KeyPool
from proxyhealth_api.ai.provider import Part, StructuredResult, Task, Usage
from proxyhealth_api.contracts.enums import Legibility, ModelTier, Provider, ThinkingLevel
from proxyhealth_api.contracts.model_out import RewriteOut, TranscriptOut
from proxyhealth_api.errors import ApiError
from proxyhealth_api.settings import KeySlotConfig, Settings

NOW = datetime(2026, 9, 24, 14, 0, 0, tzinfo=UTC)
PRO = "gemini-3.8-flash"
FAST = "gemini-3.5-flash-lite"
KEYS = ["AIzaSy-test-key-alpha-Qx7A", "AIzaSy-test-key-bravo-Zz9B"]
SENTENCE = "This letter may ask for a reply."

Script = list[types.GenerateContentResponse | BaseException]


# ------------------------------------------------------------------------------ fakes


def response(
    *,
    text: str | None = None,
    parsed: BaseModel | None = None,
    finish: types.FinishReason | None = types.FinishReason.STOP,
    block_reason: types.BlockedReason | None = None,
    candidates: bool = True,
    usage: tuple[int, int, int] | None = (11, 7, 3),
) -> types.GenerateContentResponse:
    um = (
        types.GenerateContentResponseUsageMetadata(
            prompt_token_count=usage[0], candidates_token_count=usage[1],
            thoughts_token_count=usage[2],
        )  # fmt: skip
        if usage
        else None
    )
    if block_reason is not None:
        feedback = types.GenerateContentResponsePromptFeedback(block_reason=block_reason)
        return types.GenerateContentResponse(prompt_feedback=feedback, usage_metadata=um)
    if not candidates:
        return types.GenerateContentResponse(candidates=[], usage_metadata=um)
    content = (
        types.Content(parts=[types.Part(text=text)], role="model") if text is not None else None
    )
    cand = types.Candidate(finish_reason=finish, content=content)
    return types.GenerateContentResponse(candidates=[cand], parsed=parsed, usage_metadata=um)


def ok_response(sentence: str = SENTENCE) -> types.GenerateContentResponse:
    obj = RewriteOut(sentence=sentence)
    return response(text=obj.model_dump_json(), parsed=obj)


def client_error(code: int, message: str = "upstream", *, retry_after: int | None = None) -> Any:
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else {}
    body = {"error": {"code": code, "message": message, "status": "ERROR"}}
    return errors.ClientError(code, body, httpx.Response(code, headers=headers))


class FakeAioModels:
    """AI_PROMPTS §9.5: records ``generate_content(**kw)`` and plays a script of responses."""

    def __init__(self, script: Script) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, **kw: Any) -> types.GenerateContentResponse:
        self.calls.append(kw)
        if not self.script:
            raise AssertionError("FakeAioModels script exhausted: unexpected extra call")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


@dataclass
class FakeClient:
    api_key: str
    http_options: types.HttpOptions
    models: FakeAioModels

    @property
    def aio(self) -> "FakeClient":
        return self


class Factory:
    """``client_factory``: records every (api_key, http_options) and scripts each slot."""

    def __init__(self, scripts: dict[int, Script] | None = None) -> None:
        self.clients: list[FakeClient] = []
        self.scripts = scripts or {}

    def __call__(self, api_key: str, http_options: types.HttpOptions) -> FakeClient:
        index = len(self.clients)
        client = FakeClient(api_key, http_options, FakeAioModels(self.scripts.get(index, [])))
        self.clients.append(client)
        return client


class FakeClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def slots(n: int = 2) -> list[KeySlotConfig]:
    return [KeySlotConfig(key=SecretStr(KEYS[i]), project=f"p{i}", billing=True) for i in range(n)]


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "ai_provider": "gemini", "gemini_keys": slots(), "var_dir": tmp_path / "var",
        "model_pro": PRO, "model_fast": FAST,
    }  # fmt: skip
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def build(
    tmp_path: Path, scripts: dict[int, Script] | None = None, **overrides: object
) -> tuple[GeminiProvider, Factory, Settings]:
    settings = _settings(tmp_path, **overrides)
    factory = Factory(scripts if scripts is not None else {0: [ok_response()], 1: [ok_response()]})
    provider = GeminiProvider(list(settings.gemini_keys), settings, client_factory=factory)
    return provider, factory, settings


async def generate(
    provider: GeminiProvider,
    *,
    task: Task = Task.chat,
    tier: ModelTier = ModelTier.fast,
    parts: list[Part] | None = None,
    thinking: ThinkingLevel | None = ThinkingLevel.low,
    media: Any = None,
    slot_index: int | None = 0,
    max_tokens: int = 2048,
) -> StructuredResult:
    return await provider.generate_structured(
        task=task,
        tier=tier,
        parts=parts if parts is not None else default_parts(),
        system="SYSTEM PROMPT",
        schema=RewriteOut,
        thinking=thinking,
        media_resolution=media,
        max_output_tokens=max_tokens,
        request_id="req-1",
        slot_index=slot_index,
    )


def default_parts() -> list[Part]:
    return [Part.of_text("hello"), Part.of_bytes(b"\x89PNG", "image/png")]


def config_of(factory: Factory, slot: int = 0, call: int = 0) -> types.GenerateContentConfig:
    cfg = factory.clients[slot].models.calls[call]["config"]
    assert isinstance(cfg, types.GenerateContentConfig)
    return cfg


# --------------------------------------------------------------------- client per slot


def test_one_client_per_slot_with_its_key_and_shared_http_options(tmp_path: Path) -> None:
    provider, factory, _ = build(tmp_path, upstream_timeout_s=45)
    assert provider.name is Provider.gemini
    assert [c.api_key for c in factory.clients] == KEYS
    for client in factory.clients:
        assert client.http_options is provider.http_options
    opts = provider.http_options
    assert opts.timeout == 45_000  # milliseconds (test_gemini_timeout_unit.py guards the unit)
    assert opts.retry_options is not None and opts.retry_options.attempts == 2
    assert opts.retry_options.http_status_codes == [408, 500, 502, 503, 504]


def test_provider_needs_at_least_one_slot(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one"):
        GeminiProvider([], _settings(tmp_path), client_factory=Factory())


def test_model_ids_come_only_from_settings(tmp_path: Path) -> None:
    provider, _, _ = build(
        tmp_path, model_pro="gemini-3.7-flash", model_fast="gemini-3.1-flash-lite"
    )
    assert provider.model_for(ModelTier.pro) == "gemini-3.7-flash"
    assert provider.model_for(ModelTier.fast) == "gemini-3.1-flash-lite"


# -------------------------------------------------------------------- request shape


async def test_request_shape_matches_d05(tmp_path: Path) -> None:
    provider, factory, _ = build(tmp_path)
    res = await generate(provider)
    call = factory.clients[0].models.calls[0]
    assert call["model"] == FAST
    contents = call["contents"]
    assert [p.text for p in contents] == ["hello", None]  # text part precedes media (D-04)
    assert contents[1].inline_data.mime_type == "image/png"
    assert contents[1].inline_data.data == b"\x89PNG"
    cfg = config_of(factory)
    assert cfg.system_instruction == "SYSTEM PROMPT"
    assert cfg.response_mime_type == "application/json"
    assert cfg.response_schema is RewriteOut
    assert cfg.max_output_tokens == 2048
    assert cfg.media_resolution is None  # text-only task
    assert cfg.thinking_config is not None
    assert cfg.thinking_config.thinking_level is types.ThinkingLevel.LOW
    assert cfg.thinking_config.include_thoughts is False
    assert res.model_id == FAST and provider.last_latency_ms is not None


async def test_no_sampling_knobs_or_thinking_budget_are_ever_set(tmp_path: Path) -> None:
    provider, factory, _ = build(tmp_path)
    await generate(provider)
    cfg = config_of(factory)
    for knob in ("temperature", "top_p", "top_k", "candidate_count", "response_json_schema"):
        assert getattr(cfg, knob) is None
    assert cfg.thinking_config is not None and cfg.thinking_config.thinking_budget is None
    assert cfg.model_fields_set <= {
        "system_instruction", "response_mime_type", "response_schema", "thinking_config",
        "media_resolution", "max_output_tokens",
    }  # fmt: skip


def test_build_contents_reorders_text_before_media() -> None:
    parts = [
        Part.of_bytes(b"a", "image/jpeg"),
        Part.of_text("first"),
        Part.of_bytes(b"b", "application/pdf"),
        Part.of_text("second"),
    ]
    contents = build_contents(parts)
    assert [p.text for p in contents[:2]] == ["first", "second"]
    assert [p.inline_data.mime_type for p in contents[2:] if p.inline_data] == [
        "image/jpeg",
        "application/pdf",
    ]


async def test_pro_tier_uses_model_pro_high_media_and_high_thinking(tmp_path: Path) -> None:
    provider, factory, _ = build(tmp_path)
    await generate(
        provider, task=Task.analyze_single, tier=ModelTier.pro, thinking=ThinkingLevel.high,
        media="high", max_tokens=16384,
    )  # fmt: skip
    call = factory.clients[0].models.calls[0]
    cfg = config_of(factory)
    assert call["model"] == PRO
    assert cfg.media_resolution is types.MediaResolution.MEDIA_RESOLUTION_HIGH
    assert cfg.thinking_config is not None
    assert cfg.thinking_config.thinking_level is types.ThinkingLevel.HIGH
    assert cfg.max_output_tokens == 16384


async def test_pdf_media_resolution_is_medium(tmp_path: Path) -> None:
    provider, factory, _ = build(tmp_path)
    await generate(provider, tier=ModelTier.pro, thinking=ThinkingLevel.medium, media="medium")
    assert config_of(factory).media_resolution is types.MediaResolution.MEDIA_RESOLUTION_MEDIUM


async def test_minimal_is_downgraded_to_low_on_gemini_38(tmp_path: Path) -> None:
    provider, factory, _ = build(tmp_path, model_fast="gemini-3.8-flash")
    await generate(provider, task=Task.tag, thinking=ThinkingLevel.minimal)
    cfg = config_of(factory)
    assert cfg.thinking_config is not None
    assert cfg.thinking_config.thinking_level is types.ThinkingLevel.LOW


async def test_minimal_is_kept_on_flash_lite(tmp_path: Path) -> None:
    provider, factory, _ = build(tmp_path)
    await generate(provider, task=Task.tag, thinking=ThinkingLevel.minimal)
    cfg = config_of(factory)
    assert cfg.thinking_config is not None
    assert cfg.thinking_config.thinking_level is types.ThinkingLevel.MINIMAL


async def test_thinking_none_omits_the_thinking_config(tmp_path: Path) -> None:
    provider, factory, _ = build(tmp_path)
    await generate(provider, thinking=None)
    assert config_of(factory).thinking_config is None


def test_build_config_is_the_only_config_we_send() -> None:
    cfg = build_config(
        system="S", schema=RewriteOut, model_id=PRO, thinking=ThinkingLevel.minimal,
        media_resolution="high", max_output_tokens=512,
    )  # fmt: skip
    assert cfg.thinking_config is not None
    assert cfg.thinking_config.thinking_level is types.ThinkingLevel.LOW  # guarded for 3.8
    assert cfg.media_resolution is types.MediaResolution.MEDIA_RESOLUTION_HIGH
    assert cfg.temperature is None and cfg.top_p is None and cfg.top_k is None


# ------------------------------------------------------------------ slot selection


async def test_slot_index_picks_that_slots_client(tmp_path: Path) -> None:
    provider, factory, _ = build(tmp_path)
    await generate(provider, slot_index=1)
    assert factory.clients[0].models.calls == [] and len(factory.clients[1].models.calls) == 1
    await generate(provider, slot_index=None)  # None → slot 0
    assert len(factory.clients[0].models.calls) == 1


async def test_slot_index_out_of_range_is_a_value_error(tmp_path: Path) -> None:
    provider, _, _ = build(tmp_path)
    with pytest.raises(ValueError, match="out of range"):
        await generate(provider, slot_index=2)


async def test_upstream_exceptions_propagate_uncaught(tmp_path: Path) -> None:
    provider, factory, _ = build(tmp_path, {0: [client_error(429, "quota", retry_after=17)]})
    with pytest.raises(errors.ClientError) as info:
        await generate(provider)
    assert info.value.code == 429  # failover.status_of reads this (D-05)
    assert len(factory.clients[0].models.calls) == 1


async def test_hints_are_ignored_by_the_gemini_provider(tmp_path: Path) -> None:
    provider, factory, _ = build(tmp_path)
    await provider.generate_structured(
        task=Task.chat, tier=ModelTier.fast, parts=[Part.of_text("x")], system="s",
        schema=RewriteOut, thinking=None, media_resolution=None, max_output_tokens=10,
        request_id="r", slot_index=0, hints={"demo_sample_id": "medicaid_address_confirmation"},
    )  # fmt: skip
    assert len(factory.clients[0].models.calls) == 1


# ------------------------------------------------------ reading the response (§9.3)


def test_parsed_comes_from_resp_parsed() -> None:
    obj = RewriteOut(sentence=SENTENCE)
    res = to_result(response(text=obj.model_dump_json(), parsed=obj), FAST, RewriteOut)
    assert res.parsed is obj
    assert res.raw_text is None  # never kept once parsed (D-08)
    assert (res.blocked_reason, res.finish_reason, res.incomplete) == (None, "STOP", False)
    assert (res.usage.input_tokens, res.usage.output_tokens, res.usage.thought_tokens) == (11, 7, 3)
    assert res.model_id == FAST


def test_parsed_falls_back_to_validating_the_text_when_sdk_left_it_empty() -> None:
    text = RewriteOut(sentence=SENTENCE).model_dump_json()
    res = to_result(response(text=text), FAST, RewriteOut)
    assert isinstance(res.parsed, RewriteOut) and res.parsed.sentence == SENTENCE
    assert res.incomplete is False


def test_parsed_of_the_wrong_schema_is_ignored() -> None:
    class Other(BaseModel):
        x: int

    res = to_result(response(text="{}", parsed=Other(x=1)), FAST, RewriteOut)
    assert res.parsed is None and res.raw_text == "{}"


def test_max_tokens_is_incomplete_even_with_no_text() -> None:
    res = to_result(response(text=None, finish=types.FinishReason.MAX_TOKENS), PRO, RewriteOut)
    assert res.incomplete is True and res.parsed is None
    assert res.finish_reason == "MAX_TOKENS" and res.blocked_reason is None


def test_max_tokens_with_truncated_json_is_incomplete_and_keeps_raw_in_memory() -> None:
    truncated = '{"sentence": "This letter may'
    res = to_result(response(text=truncated, finish=types.FinishReason.MAX_TOKENS), PRO, RewriteOut)
    assert res.incomplete is True and res.parsed is None and res.raw_text == truncated


def test_stop_with_invalid_json_is_unparsed_but_not_incomplete() -> None:
    res = to_result(response(text="not json"), PRO, RewriteOut)
    assert res.parsed is None and res.incomplete is False and res.raw_text == "not json"


@pytest.mark.parametrize(
    ("finish", "reason"),
    [
        (types.FinishReason.SPII, "spii"),
        (types.FinishReason.SAFETY, "safety"),
        (types.FinishReason.RECITATION, "recitation"),
        (types.FinishReason.PROHIBITED_CONTENT, "prohibited_content"),
        (types.FinishReason.BLOCKLIST, "blocklist"),
        (types.FinishReason.IMAGE_SAFETY, "safety"),
        (types.FinishReason.IMAGE_PROHIBITED_CONTENT, "prohibited_content"),
    ],
)
def test_blocked_finish_reasons_map_to_the_contract_vocabulary(
    finish: types.FinishReason, reason: str
) -> None:
    res = to_result(response(text=None, finish=finish), PRO, RewriteOut)
    assert res.blocked_reason == reason
    assert res.finish_reason == finish.name
    assert res.parsed is None and res.raw_text is None and res.incomplete is False


@pytest.mark.parametrize(
    ("block", "reason"),
    [
        (types.BlockedReason.SAFETY, "safety"),
        (types.BlockedReason.PROHIBITED_CONTENT, "prohibited_content"),
        (types.BlockedReason.BLOCKLIST, "blocklist"),
        (types.BlockedReason.JAILBREAK, "other"),
        (types.BlockedReason.MODEL_ARMOR, "other"),
        (types.BlockedReason.OTHER, "other"),
    ],
)
def test_prompt_feedback_block_reason_is_blocked(block: types.BlockedReason, reason: str) -> None:
    res = to_result(response(block_reason=block), PRO, RewriteOut)
    assert res.blocked_reason == reason and res.parsed is None and res.finish_reason is None


def test_unspecified_prompt_block_reason_is_not_a_block() -> None:
    obj = RewriteOut(sentence=SENTENCE)
    resp = response(text=obj.model_dump_json(), parsed=obj)
    resp.prompt_feedback = types.GenerateContentResponsePromptFeedback(
        block_reason=types.BlockedReason.BLOCKED_REASON_UNSPECIFIED
    )
    res = to_result(resp, PRO, RewriteOut)
    assert res.blocked_reason is None and res.parsed is obj


def test_empty_candidates_is_blocked_other() -> None:
    res = to_result(response(candidates=False), PRO, RewriteOut)
    assert res.blocked_reason == "other" and res.parsed is None


def test_missing_usage_metadata_counts_zero() -> None:
    res = to_result(response(text="{}", usage=None), PRO, RewriteOut)
    assert (res.usage.input_tokens, res.usage.output_tokens, res.usage.thought_tokens) == (0, 0, 0)


def test_contract_block_reason_mapping() -> None:
    assert contract_block_reason("SPII") == "spii"
    assert contract_block_reason("IMAGE_SAFETY") == "safety"
    assert contract_block_reason("IMAGE_RECITATION") == "recitation"
    assert contract_block_reason("JAILBREAK") == "other"
    assert gemini.CONTRACT_REASONS == {"safety", "spii", "prohibited_content", "recitation",
                                       "blocklist"}  # fmt: skip


async def test_provider_returns_blocked_spii_from_a_live_shaped_response(tmp_path: Path) -> None:
    provider, _, _ = build(tmp_path, {0: [response(text=None, finish=types.FinishReason.SPII)]})
    res = await generate(provider)
    assert res.blocked_reason == "spii"


# ---------------------------------- through AIService + KeyPool (the real SDK errors)


def server_error(code: int) -> Any:
    body = {"error": {"code": code, "message": "unavailable", "status": "UNAVAILABLE"}}
    return errors.ServerError(code, body, httpx.Response(code))


@dataclass
class Stack:
    service: AIService
    keypool: KeyPool
    factory: Factory
    clock: FakeClock
    sleeps: list[float]


def stack(tmp_path: Path, scripts: dict[int, Script]) -> Stack:
    provider, factory, settings = build(tmp_path, scripts)
    clock = FakeClock()
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    keypool = KeyPool.from_settings(settings, clock)
    service = AIService(provider, keypool, settings, clock=clock, sleep=sleep)
    return Stack(service, keypool, factory, clock, sleeps)


async def run_chat(s: Stack) -> Any:
    return await s.service.generate(
        task=Task.chat, parts=[Part.of_text("q")], system="SYSTEM", schema=RewriteOut,
        request_id="req-9",
    )  # fmt: skip


async def test_sdk_429_with_retry_after_cools_that_slot_for_exactly_n_seconds(
    tmp_path: Path,
) -> None:
    s = stack(tmp_path, {0: [client_error(429, "rate", retry_after=17)], 1: [ok_response()]})
    out = await run_chat(s)
    assert out.slot_index == 1 and out.attempts == 2
    assert isinstance(out.result.parsed, RewriteOut)
    ts = s.keypool.tier_state(0, ModelTier.fast)
    assert ts.state == "cooling"
    assert ts.cooldown_until == NOW + timedelta(seconds=17)
    s.clock.now = NOW + timedelta(seconds=16)
    assert s.keypool.effective_state(0, ModelTier.fast) == "cooling"
    s.clock.now = NOW + timedelta(seconds=17)
    assert s.keypool.effective_state(0, ModelTier.fast) == "healthy"


async def test_sdk_503_retries_the_same_slot_once(tmp_path: Path) -> None:
    s = stack(tmp_path, {0: [server_error(503), ok_response()], 1: []})
    out = await run_chat(s)
    assert out.slot_index == 0
    assert len(s.factory.clients[0].models.calls) == 2 and s.sleeps == [1.5]
    assert s.factory.clients[1].models.calls == []


async def test_sdk_spii_block_is_422_and_never_tried_on_another_key(tmp_path: Path) -> None:
    s = stack(tmp_path, {0: [response(text=None, finish=types.FinishReason.SPII)], 1: []})
    with pytest.raises(ApiError) as info:
        await run_chat(s)
    assert info.value.status == 422
    assert s.factory.clients[1].models.calls == []


async def test_sdk_401_disables_the_slot_and_rotates(tmp_path: Path) -> None:
    s = stack(tmp_path, {0: [client_error(401, "API key not valid")], 1: [ok_response()]})
    out = await run_chat(s)
    assert out.slot_index == 1
    assert s.keypool.tier_state(0, ModelTier.fast).state == "disabled"
    assert KEYS[0] not in s.keypool.path.read_text(encoding="utf-8")


# ------------------------------------------- scripts/spike_schema.py (no network, stubbed)

SPIKE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "spike_schema.py"


def load_spike() -> ModuleType:
    spec = importlib.util.spec_from_file_location("spike_schema_under_test", SPIKE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StubProvider:
    """Returns an unvalidated instance of the requested schema; scripted failures per task."""

    name: Provider = Provider.gemini

    def __init__(self, failures: dict[Task, BaseException] | None = None) -> None:
        self.failures = failures or {}
        self.tasks: list[Task] = []

    async def generate_structured(self, **kw: Any) -> StructuredResult:
        task: Task = kw["task"]
        schema: type[BaseModel] = kw["schema"]
        self.tasks.append(task)
        if task in self.failures:
            raise self.failures[task]
        if schema is TranscriptOut:
            parsed: BaseModel = TranscriptOut.model_construct(
                blocks=[], detected_language="en", legibility=Legibility.good,
                readable_reason=None,
            )  # fmt: skip
        elif schema is RewriteOut:
            parsed = RewriteOut(sentence="SECRET-MODEL-SENTENCE")
        else:
            parsed = schema.model_construct()
        return StructuredResult(
            parsed=parsed, raw_text=None, model_id=FAST, usage=Usage(1, 2, 3), finish_reason="STOP"
        )


def spike_stack(tmp_path: Path, stub: StubProvider) -> tuple[Any, Any, Settings]:
    spike = load_spike()
    settings = _settings(tmp_path)
    recorder = spike.UpstreamRecorder(stub)
    keypool = KeyPool.from_settings(settings, FakeClock())
    return spike, (AIService(recorder, keypool, settings), recorder), settings


def test_spike_schema_exits_2_with_a_clear_message_without_keys(
    capsys: pytest.CaptureFixture[str],
) -> None:
    spike = load_spike()
    settings = Settings(_env_file=None, ai_provider="mock")
    assert spike.main([], settings=settings) == 2
    assert "GEMINI_KEYS is empty" in capsys.readouterr().err


async def test_spike_single_call_accepted_recommends_auto(tmp_path: Path) -> None:
    stub = StubProvider()
    spike, (service, recorder), settings = spike_stack(tmp_path, stub)
    fx = spike.SpikeFixture("fx_doc", "document", [b"\x89PNG"])
    report = await spike.run_spike(service, recorder, settings, [fx])
    assert [r.mode for r in report.fixtures] == ["single"]
    assert {p.status for p in report.tasks} == {"ok", "skipped"}  # no screenshot fixture
    line, passed = spike.recommendation(report)
    assert passed and line.endswith("ANALYSIS_MODE=auto")
    assert Task.analyze_single in stub.tasks and Task.transcribe not in stub.tasks


async def test_spike_schema_rejection_falls_back_to_two_call(tmp_path: Path) -> None:
    stub = StubProvider({Task.analyze_single: client_error(400, "Unsupported: too many states")})
    spike, (service, recorder), settings = spike_stack(tmp_path, stub)
    fx = spike.SpikeFixture("fx_doc", "document", [b"\x89PNG"])
    report = await spike.run_spike(service, recorder, settings, [fx], probe_tasks=False)
    run = report.fixtures[0]
    assert run.mode == "two_call"
    assert [p.status for p in run.probes] == ["schema_rejected", "ok", "ok"]
    assert stub.tasks == [Task.analyze_single, Task.transcribe, Task.explain]
    line, passed = spike.recommendation(report)
    assert passed and line.endswith("ANALYSIS_MODE=two_call")


async def test_spike_flags_a_schema_rejected_text_task(tmp_path: Path) -> None:
    stub = StubProvider({Task.tag: client_error(400, "response_schema nesting too deep")})
    spike, (service, recorder), settings = spike_stack(tmp_path, stub)
    report = await spike.run_spike(service, recorder, settings, [])
    tag = next(p for p in report.tasks if p.task == "tag")
    assert (tag.status, tag.http) == ("schema_rejected", 400)
    assert spike.recommendation(report)[1] is False


async def test_spike_report_is_content_free(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stub = StubProvider()
    spike, (service, recorder), settings = spike_stack(tmp_path, stub)
    report = await spike.run_spike(service, recorder, settings, [])
    for as_json in (False, True):
        spike.print_report(report, as_json=as_json)
        out = capsys.readouterr().out
        assert "SECRET-MODEL-SENTENCE" not in out and "phrasing_rewrite" in out
        assert all(key not in out for key in KEYS)


def test_spike_loads_the_on_disk_fixtures() -> None:
    spike = load_spike()
    fixtures = spike.load_fixtures()
    if not fixtures:
        pytest.skip("no data/fixtures on disk yet (WP7)")
    for fx in fixtures:
        assert fx.pages and all(page.startswith(b"\x89PNG") for page in fx.pages)


# ------------------------------------------------------------ lifespan builder (lane 1A)


def test_build_gemini_stack_with_keys_returns_provider_and_restored_pool(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    factory = Factory()
    clock = FakeClock()
    provider, keypool = gemini.build_gemini_stack(settings, clock=clock, client_factory=factory)
    assert isinstance(provider, GeminiProvider) and keypool is not None
    assert len(factory.clients) == 2 and keypool.clock is clock
    assert keypool.var_dir == settings.var_dir


@pytest.mark.parametrize(
    "overrides",
    [
        {"gemini_keys": []},
        {"ai_provider": "gemini_interactions"},
        {"ai_provider": "mock"},
    ],
)
async def test_build_gemini_stack_without_usable_keys_is_unconfigured(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    provider, keypool = gemini.build_gemini_stack(_settings(tmp_path, **overrides))
    assert keypool is None and provider.name is Provider.gemini
    with pytest.raises(ApiError) as info:
        await provider.generate_structured(
            task=Task.chat, tier=ModelTier.fast, parts=[Part.of_text("x")], system="s",
            schema=RewriteOut, thinking=None, media_resolution=None, max_output_tokens=10,
            request_id="r",
        )  # fmt: skip
    assert info.value.status == 503


# ------------------------------------- SDK-side schema conversion (the keyless half of D-06)


MODEL_OUT_SCHEMAS = [
    "AnalysisModelOut", "TranscriptOut", "ExplainOut", "TroubleshootModelOut", "ChatModelOut",
    "LanguagePackModelOut", "LanguageResolveOut", "RewriteOut", "TaggingModelOut",
]  # fmt: skip


@pytest.mark.parametrize("schema_name", MODEL_OUT_SCHEMAS)
def test_every_model_output_schema_converts_through_the_sdk(schema_name: str) -> None:
    # The SDK turns ``response_schema=<Pydantic class>`` into a Gemini Schema before sending;
    # a conversion error here would surface as a request-time crash. Server-side acceptance is
    # what ``scripts/spike_schema.py`` measures with keys.
    from google import genai
    from google.genai import _transformers

    from proxyhealth_api.contracts import model_out

    schema = getattr(model_out, schema_name)
    client = genai.Client(api_key="AIzaSy-offline-conversion-only")
    converted = _transformers.t_schema(client._api_client, schema)
    assert converted is not None and converted.properties
