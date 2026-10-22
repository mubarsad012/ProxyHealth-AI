"""``ai/openai_compat.OpenAICompatProvider`` against a fake OpenAI-compatible server
(free-ai-providers §4.3–§4.9). No network: ``httpx.MockTransport`` answers every request, records
the JSON body, and the failover tests run the real ``AIService`` + one-slot ``KeyPool``."""

import asyncio
import base64
import io
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image
from pydantic import BaseModel
from reportlab.pdfgen import canvas

from proxyhealth_api.ai import openai_compat as oc
from proxyhealth_api.ai.failover import AIService, SchemaFallbackNeeded
from proxyhealth_api.ai.openai_compat import (
    OpenAICompatError,
    OpenAICompatProvider,
    build_openai_compat_stack,
    flatten_schema,
    strip_to_json,
)
from proxyhealth_api.ai.provider import Part, StructuredResult, Task
from proxyhealth_api.ai.routing import route
from proxyhealth_api.contracts.enums import DataUseTier, ErrorCode, ModelTier, ThinkingLevel
from proxyhealth_api.contracts.model_out import AnalysisModelOut, RewriteOut, TaggingModelOut
from proxyhealth_api.errors import ApiError
from proxyhealth_api.settings import Settings
from tests.conftest import FROZEN_NOW, make_settings

SENTENCE = "This letter may ask for a reply."
MARKER = "ZQX-MARKER-7731"  # must never reach a log line or an error message

Reply = httpx.Response | BaseException | Callable[[httpx.Request], httpx.Response]


def compat(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "ai_provider": "openai_compat",
        "openai_compat_data_tier": "local",
        "openai_compat_model_label": "Qwen",
        "openai_compat_model_pro": "qwen3.5:4b",
        "openai_compat_model_fast": "qwen3.5:2b",
    }
    values.update(overrides)
    return make_settings(tmp_path, **values)


def hosted(tmp_path: Path, host: str, **overrides: object) -> Settings:
    return compat(
        tmp_path, openai_compat_base_url=f"https://{host}/v1", openai_compat_data_tier="unpaid",
        openai_compat_vendor_name="Vendor", openai_compat_api_key="sk-test-key-0001", **overrides,
    )  # fmt: skip


def completion(
    content: str | None = None,
    *,
    finish: str | None = "stop",
    usage: dict[str, Any] | None = None,
    refusal: str | None = None,
) -> httpx.Response:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if refusal is not None:
        message["refusal"] = refusal
    body: dict[str, Any] = {
        "id": "chatcmpl-1",
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": usage or {"prompt_tokens": 11, "completion_tokens": 7},
    }
    return httpx.Response(200, json=body)


def ok(sentence: str = SENTENCE) -> httpx.Response:
    return completion(RewriteOut(sentence=sentence).model_dump_json())


def error(status: int, message: str = "upstream", **headers: str) -> httpx.Response:
    body = {"error": {"message": message, "code": "e"}, "echo": MARKER}
    return httpx.Response(status, json=body, headers=headers)


class FakeServer:
    """Scripted ``/chat/completions``: replies in order (the last one repeats)."""

    def __init__(self, *replies: Reply) -> None:
        self.replies = list(replies) or [ok()]
        self.requests: list[httpx.Request] = []
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.bodies.append(json.loads(request.content))
        index = min(len(self.requests) - 1, len(self.replies) - 1)
        reply = self.replies[index]
        if isinstance(reply, BaseException):
            raise reply
        if callable(reply) and not isinstance(reply, httpx.Response):
            return reply(request)
        return reply

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def provider(settings: Settings, server: FakeServer, **kwargs: Any) -> OpenAICompatProvider:
    return OpenAICompatProvider(settings, transport=server.transport, **kwargs)


async def call(
    p: OpenAICompatProvider,
    *,
    task: Task = Task.phrasing_rewrite,
    tier: ModelTier = ModelTier.fast,
    parts: list[Part] | None = None,
    schema: type[BaseModel] = RewriteOut,
    thinking: ThinkingLevel | None = None,
    max_output_tokens: int = 256,
) -> StructuredResult:
    return await p.generate_structured(
        task=task, tier=tier, parts=parts or [Part.of_text("Rewrite this.")], system="SYS",
        schema=schema, thinking=thinking, media_resolution=None,
        max_output_tokens=max_output_tokens, request_id="rid-1",
    )  # fmt: skip


def png(width: int = 32, height: int = 16) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, format="PNG")
    return buf.getvalue()


def jpeg(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, format="JPEG")
    return buf.getvalue()


def pdf(pages: int) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(612, 792))
    for n in range(pages):
        c.drawString(72, 700, f"Page {n + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def image_urls(body: dict[str, Any]) -> list[str]:
    content = body["messages"][1]["content"]
    return [p["image_url"]["url"] for p in content if p["type"] == "image_url"]


def decoded_size(url: str) -> tuple[int, int]:
    data = base64.b64decode(url.split(",", 1)[1])
    with Image.open(io.BytesIO(data)) as im:
        return im.size


def walk_keys(node: Any) -> set[str]:
    if isinstance(node, dict):
        keys = set(node)
        for value in node.values():
            keys |= walk_keys(value)
        return keys
    if isinstance(node, list):
        return set().union(*(walk_keys(v) for v in node)) if node else set()
    return set()


# --------------------------------------------------------------------------- request shape


async def test_request_shape_text_before_images_and_no_sampling_beyond_temperature(
    tmp_path: Path,
) -> None:
    server = FakeServer(ok())
    p = provider(compat(tmp_path), server)
    parts = [Part.of_bytes(png(), "image/png"), Part.of_text("first"), Part.of_text("second")]
    res = await call(p, tier=ModelTier.pro, parts=parts, max_output_tokens=16384)
    assert isinstance(res.parsed, RewriteOut) and res.model_id == "qwen3.5:4b"
    req, body = server.requests[0], server.bodies[0]
    assert req.method == "POST" and str(req.url) == "http://127.0.0.1:11434/v1/chat/completions"
    assert "authorization" not in req.headers  # no key configured → no header
    assert body["model"] == "qwen3.5:4b" and body["stream"] is False
    assert body["temperature"] == 0 and body["max_tokens"] == 4096  # loopback OPENAI_COMPAT cap
    assert body["reasoning_effort"] == "none"
    assert not {"top_p", "top_k", "n", "seed", "think", "num_ctx"} & set(body)
    system, user = body["messages"]
    assert system == {"role": "system", "content": "SYS"}  # json_schema mode: no schema text
    assert user["role"] == "user"
    assert user["content"][0] == {"type": "text", "text": "first\n\nsecond"}
    assert [p["type"] for p in user["content"]] == ["text", "image_url"]
    assert image_urls(body)[0].startswith("data:image/png;base64,")
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["name"] == "RewriteOut"


async def test_fast_tier_uses_model_fast_and_text_only_content_is_a_string(
    tmp_path: Path,
) -> None:
    server = FakeServer(ok())
    await call(provider(compat(tmp_path), server), tier=ModelTier.fast)
    body = server.bodies[0]
    assert body["model"] == "qwen3.5:2b" and body["max_tokens"] == 256
    assert body["messages"][1]["content"] == "Rewrite this."


async def test_api_key_goes_only_into_the_authorization_header(tmp_path: Path) -> None:
    server = FakeServer(ok())
    await call(provider(compat(tmp_path, openai_compat_api_key="sk-local-9"), server))
    assert server.requests[0].headers["authorization"] == "Bearer sk-local-9"
    assert "sk-local-9" not in server.requests[0].content.decode()


@pytest.mark.parametrize(
    ("mode", "thinking", "expected"),
    [
        ("none", ThinkingLevel.high, "none"),
        ("none", None, "none"),
        ("mapped", ThinkingLevel.high, "high"),
        ("mapped", ThinkingLevel.medium, "medium"),
        ("mapped", ThinkingLevel.low, "low"),
        ("mapped", ThinkingLevel.minimal, "none"),
        ("mapped", None, None),
        ("omit", ThinkingLevel.high, None),
    ],
)
async def test_thinking_flag(
    tmp_path: Path, mode: str, thinking: ThinkingLevel | None, expected: str | None
) -> None:
    server = FakeServer(ok())
    await call(provider(compat(tmp_path, openai_compat_reasoning=mode), server), thinking=thinking)
    assert server.bodies[0].get("reasoning_effort") == expected


@pytest.mark.parametrize(
    ("task", "expected"), [(Task.analyze_single, 4096), (Task.phrasing_rewrite, 256)]
)
async def test_analyze_max_tokens_capped_at_4096_on_loopback(
    tmp_path: Path, task: Task, expected: int
) -> None:
    settings = compat(tmp_path)
    cap = route(task, pages=1, is_pdf=False, degraded=False, settings=settings).max_output_tokens
    server = FakeServer(ok())
    await call(provider(settings, server), task=task, max_output_tokens=cap)
    assert server.bodies[0]["max_tokens"] == expected
    hosted_server = FakeServer(ok())
    await call(provider(hosted(tmp_path, "api.groq.com"), hosted_server),
               task=Task.analyze_single, max_output_tokens=16384)  # fmt: skip
    assert hosted_server.bodies[0]["max_tokens"] == 6144


def test_httpx_timeouts_follow_section_4_6(tmp_path: Path) -> None:
    p = provider(compat(tmp_path), FakeServer())
    t = p._client.timeout
    assert (t.connect, t.read, t.write, t.pool) == (5.0, 300.0, 30.0, 5.0)
    hosted_p = provider(hosted(tmp_path, "api.groq.com"), FakeServer())
    assert hosted_p._client.timeout.read == 90.0


# ----------------------------------------------------------------------- structured modes


def test_flatten_schema_inlines_refs_and_strict_lists_every_property() -> None:
    flat = flatten_schema(AnalysisModelOut, strict=True)
    keys = walk_keys(flat)
    assert not {"$ref", "$defs", "title", "description", "default"} & (keys - {"properties"})
    assert flat["additionalProperties"] is False
    assert flat["required"] == list(flat["properties"])
    nullable = flat["properties"]["sender_as_written"]["anyOf"]
    assert {"type": "null"} in nullable
    demand = flat["properties"]["demands"]["items"]
    assert demand["type"] == "object" and demand["additionalProperties"] is False
    assert set(demand["required"]) == set(demand["properties"])
    assert "enum" in flat["properties"]["document_type"]
    loose = flatten_schema(AnalysisModelOut, strict=False)
    assert "additionalProperties" not in loose


@pytest.mark.parametrize(
    ("host", "image_mode", "text_mode"),
    [
        ("dashscope-intl.aliyuncs.com", "json_object", "json_schema"),
        ("api.z.ai", "prompt", "json_object"),
        ("api.groq.com", "json_object", "json_schema"),
        ("api.cerebras.ai", "json_schema", "json_schema"),
        ("api.siliconflow.com", "json_object", "json_object"),
        ("openrouter.ai", "json_schema", "json_schema"),
        ("unknown.example.org", "json_schema", "json_schema"),
    ],
)
def test_host_capability_table(host: str, image_mode: str, text_mode: str) -> None:
    assert oc.host_json_mode(host, has_images=True) == image_mode
    assert oc.host_json_mode(host, has_images=False) == text_mode


async def test_json_object_mode_puts_the_schema_in_the_system_message(tmp_path: Path) -> None:
    server = FakeServer(ok())
    p = provider(hosted(tmp_path, "api.groq.com"), server)
    await call(p, parts=[Part.of_text("t"), Part.of_bytes(png(), "image/png")])
    body = server.bodies[0]
    assert body["response_format"] == {"type": "json_object"}
    system = body["messages"][0]["content"]
    assert system.startswith("SYS\n\n") and "JSON Schema" in system and '"sentence"' in system
    assert p.last_json_mode == "json_object"


async def test_prompt_mode_sends_no_response_format(tmp_path: Path) -> None:
    server = FakeServer(ok())
    p = provider(hosted(tmp_path, "api.z.ai"), server)
    await call(p, parts=[Part.of_text("t"), Part.of_bytes(png(), "image/png")])
    assert "response_format" not in server.bodies[0]
    assert "JSON Schema" in server.bodies[0]["messages"][0]["content"]


async def test_json_mode_setting_overrides_the_host_table(tmp_path: Path) -> None:
    server = FakeServer(ok())
    await call(provider(compat(tmp_path, openai_compat_json_mode="json_object"), server))
    assert server.bodies[0]["response_format"] == {"type": "json_object"}


async def test_openrouter_pins_providers_that_honour_every_parameter(tmp_path: Path) -> None:
    server = FakeServer(ok())
    await call(provider(hosted(tmp_path, "openrouter.ai"), server))
    assert server.bodies[0]["provider"] == {"require_parameters": True, "data_collection": "deny"}


@pytest.mark.parametrize(
    "raw",
    [
        f'<think>I should answer {MARKER}</think>{{"sentence": "{SENTENCE}"}}',
        f'```json\n{{"sentence": "{SENTENCE}"}}\n```',
        f'Here you go: {{"sentence": "{SENTENCE}"}} done',
        f'reasoning without an opening tag</think>\n{{"sentence": "{SENTENCE}"}}',
    ],
)
async def test_think_blocks_and_fences_are_stripped(tmp_path: Path, raw: str) -> None:
    assert strip_to_json(raw) == f'{{"sentence": "{SENTENCE}"}}'
    res = await call(provider(compat(tmp_path), FakeServer(completion(raw))))
    assert isinstance(res.parsed, RewriteOut) and res.parsed.sentence == SENTENCE


# --------------------------------------------------------------------- repair + finish reasons


async def test_one_repair_retry_carries_only_loc_and_type(tmp_path: Path) -> None:
    bad = json.dumps({"sentence": MARKER * 40})  # too long: string_too_long, value never echoed
    server = FakeServer(completion(bad), ok())
    p = provider(compat(tmp_path), server)
    res = await call(p)
    assert isinstance(res.parsed, RewriteOut) and p.last_repaired is True
    assert len(server.bodies) == 2
    second = server.bodies[1]["messages"]
    assert [m["role"] for m in second] == ["system", "user", "assistant", "user"]
    repair = second[3]["content"]
    assert repair.startswith("Your JSON did not match the schema. Problems: sentence: ")
    assert "string_too_long" in repair and repair.endswith("Return only the corrected JSON.")
    assert MARKER not in repair
    assert res.usage.input_tokens == 22 and res.usage.output_tokens == 14  # both calls counted


async def test_invalid_json_is_repaired_with_the_json_invalid_type(tmp_path: Path) -> None:
    server = FakeServer(completion("not json at all"), ok())
    res = await call(provider(compat(tmp_path), server))
    assert isinstance(res.parsed, RewriteOut)
    assert "(root): json_invalid" in server.bodies[1]["messages"][3]["content"]


async def test_failed_repair_is_incomplete_for_the_two_call_fallback(tmp_path: Path) -> None:
    server = FakeServer(completion("{}"), completion('{"nope": 1}'))
    res = await call(provider(compat(tmp_path), server))
    assert res.parsed is None and res.incomplete is True and res.raw_text is None
    assert len(server.bodies) == 2  # exactly one repair


async def test_finish_length_is_incomplete_without_a_repair(tmp_path: Path) -> None:
    server = FakeServer(completion('{"sentence": "cut', finish="length"))
    res = await call(provider(compat(tmp_path), server))
    assert res.incomplete is True and res.parsed is None and res.finish_reason == "length"
    assert len(server.bodies) == 1


async def test_finish_length_with_valid_json_is_still_incomplete(tmp_path: Path) -> None:
    res = await call(provider(compat(tmp_path), FakeServer(completion(
        RewriteOut(sentence=SENTENCE).model_dump_json(), finish="length"
    ))))  # fmt: skip
    assert res.incomplete is True


@pytest.mark.parametrize(
    "reply",
    [completion(None, finish="content_filter"), completion(None, refusal="I can't help")],
)
async def test_content_filter_and_refusal_are_blocked_other(
    tmp_path: Path, reply: httpx.Response
) -> None:
    res = await call(provider(compat(tmp_path), FakeServer(reply)))
    assert res.blocked_reason == "other" and res.parsed is None


async def test_no_choices_is_incomplete(tmp_path: Path) -> None:
    res = await call(provider(compat(tmp_path), FakeServer(httpx.Response(200, json={}))))
    assert res.parsed is None and res.incomplete is True


async def test_usage_maps_prompt_completion_and_reasoning_tokens(tmp_path: Path) -> None:
    usage = {"prompt_tokens": 100, "completion_tokens": 40,
             "completion_tokens_details": {"reasoning_tokens": 9}}  # fmt: skip
    res = await call(provider(compat(tmp_path), FakeServer(completion(
        RewriteOut(sentence=SENTENCE).model_dump_json(), usage=usage
    ))))  # fmt: skip
    assert (res.usage.input_tokens, res.usage.output_tokens, res.usage.thought_tokens) == (
        100, 40, 9,
    )  # fmt: skip


async def test_repair_is_skipped_when_the_call_budget_is_spent(tmp_path: Path) -> None:
    now = [0.0]

    def slow_invalid(_: httpx.Request) -> httpx.Response:
        now[0] += 298.0  # the first call used almost all of the 300 s budget
        return completion("{}")

    server = FakeServer(slow_invalid)
    p = provider(compat(tmp_path), server, clock=lambda: now[0])
    res = await call(p)
    assert res.incomplete is True and len(server.bodies) == 1


# ------------------------------------------------------------------ protocol fallbacks (§4.4)


async def test_schema_rejection_in_auto_mode_falls_back_to_prompt_and_remembers(
    tmp_path: Path,
) -> None:
    server = FakeServer(error(400, "JSON Mode couldn't be met"), ok(), ok())
    p = provider(compat(tmp_path), server)
    res = await call(p)
    assert isinstance(res.parsed, RewriteOut) and p.last_json_mode == "prompt"
    assert "response_format" in server.bodies[0] and "response_format" not in server.bodies[1]
    assert "JSON Schema" in server.bodies[1]["messages"][0]["content"]
    await call(p)
    assert "response_format" not in server.bodies[2]  # learned once per process


async def test_reasoning_rejection_retries_without_the_field(tmp_path: Path) -> None:
    server = FakeServer(error(400, "Unrecognized request argument: reasoning_effort"), ok())
    res = await call(provider(compat(tmp_path), server))
    assert isinstance(res.parsed, RewriteOut)
    assert "reasoning_effort" in server.bodies[0] and "reasoning_effort" not in server.bodies[1]


async def test_explicit_json_mode_never_falls_back(tmp_path: Path) -> None:
    server = FakeServer(error(400, "response_format json_schema is not supported"))
    p = provider(compat(tmp_path, openai_compat_json_mode="json_schema"), server)
    with pytest.raises(OpenAICompatError) as info:
        await call(p)
    assert info.value.status_code == 400 and len(server.bodies) == 1
    assert MARKER not in info.value.message and "json_schema" in info.value.message


# --------------------------------------------------------------------- errors (§4.7) direct


async def test_connection_refused_on_loopback_is_local_server_not_running(tmp_path: Path) -> None:
    server = FakeServer(httpx.ConnectError("refused"))
    with pytest.raises(ApiError) as info:
        await call(provider(compat(tmp_path), server))
    err = info.value
    assert (err.status, err.code, err.retry_after) == (503, ErrorCode.provider_not_configured, 30)
    assert err.message == "Local AI server is not running."


async def test_connection_error_on_a_hosted_endpoint_propagates(tmp_path: Path) -> None:
    server = FakeServer(httpx.ConnectError("refused"))
    with pytest.raises(httpx.ConnectError):
        await call(provider(hosted(tmp_path, "api.groq.com"), server))


async def test_model_not_found_is_provider_not_configured(tmp_path: Path) -> None:
    server = FakeServer(error(404, "model 'qwen3.5:4b' not found"))
    with pytest.raises(ApiError) as info:
        await call(provider(compat(tmp_path), server))
    assert info.value.status == 503 and info.value.code is ErrorCode.provider_not_configured


async def test_error_text_is_the_upstream_message_only_and_capped(tmp_path: Path) -> None:
    server = FakeServer(error(500, "x" * 1000))
    with pytest.raises(OpenAICompatError) as info:
        await call(provider(compat(tmp_path), server))
    assert len(info.value.message) <= 300 and MARKER not in info.value.message
    assert info.value.response is not None and info.value.response.content == b""


async def test_unprocessable_maps_to_400(tmp_path: Path) -> None:
    server = FakeServer(error(422, "bad value"))
    with pytest.raises(OpenAICompatError) as info:
        await call(provider(compat(tmp_path), server))
    assert info.value.status_code == 400


# ---------------------------------------------------------------- timeouts and a busy slot


async def test_read_timeout_is_content_free_503_ai_too_slow(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    server = FakeServer(httpx.ReadTimeout(f"read timed out {MARKER}"))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ApiError) as info:
            await call(provider(compat(tmp_path), server), task=Task.analyze_single,
                       parts=[Part.of_text(f"paper {MARKER}")])  # fmt: skip
    err = info.value
    assert (err.status, err.code, err.user_message_key) == (
        503, ErrorCode.upstream_unavailable, "err.ai_too_slow",
    )  # fmt: skip
    assert err.retry_after is None  # a retry at temperature 0 takes as long again
    assert err.details == {"reason": "ai_timeout", "timeout_s": 300}
    assert MARKER not in err.message and MARKER not in caplog.text


async def test_timeouts_on_other_tasks_keep_the_generic_copy(tmp_path: Path) -> None:
    server = FakeServer(httpx.ReadTimeout("slow"))
    with pytest.raises(ApiError) as info:
        await call(provider(compat(tmp_path), server), task=Task.chat)
    assert info.value.user_message_key == "err.upstream_unavailable"
    assert info.value.details is not None and info.value.details["reason"] == "ai_timeout"


async def test_semaphore_wait_timeout_is_ai_busy(tmp_path: Path) -> None:
    server = FakeServer(ok())
    p = provider(compat(tmp_path), server)
    p._timeout_s = 0.05  # the whole call budget, queue wait included
    await p._semaphore.acquire()  # another paper holds the one loopback slot
    try:
        with pytest.raises(ApiError) as info:
            await call(p, task=Task.analyze_single)
    finally:
        p._semaphore.release()
    err = info.value
    assert (err.status, err.user_message_key, err.retry_after) == (503, "err.ai_busy", 60)
    assert err.details is not None and err.details["reason"] == "ai_busy"
    assert not server.bodies


async def test_timeout_after_a_long_queue_wait_is_ai_busy(tmp_path: Path) -> None:
    now = [0.0]
    p = provider(compat(tmp_path), FakeServer(httpx.ReadTimeout("slow")), clock=lambda: now[0])
    await p._semaphore.acquire()
    pending = asyncio.ensure_future(call(p, task=Task.analyze_single))
    await asyncio.sleep(0)  # queued behind the other call
    now[0] = 200.0  # the other paper held the slot for 200 s of this call's 300 s
    p._semaphore.release()
    with pytest.raises(ApiError) as info:
        await pending
    assert info.value.user_message_key == "err.ai_busy"
    assert info.value.details == {"reason": "ai_busy", "waited_s": 200}


async def test_trickling_endpoint_cannot_outlast_the_call_budget(tmp_path: Path) -> None:
    async def trickle() -> Any:
        while True:
            await asyncio.sleep(0.2)
            yield b" "

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=trickle())

    p = provider(compat(tmp_path, openai_compat_timeout_s=1), FakeServer(handler))
    started = asyncio.get_running_loop().time()
    with pytest.raises(ApiError) as info:
        await call(p, task=Task.analyze_single)
    assert asyncio.get_running_loop().time() - started < 1.8
    assert info.value.user_message_key == "err.ai_too_slow"


# ------------------------------------------------------- failover + one synthetic slot (§4.7)


class Clock:
    def __init__(self) -> None:
        self.now = FROZEN_NOW

    def __call__(self) -> datetime:
        return self.now


def service(
    settings: Settings, server: FakeServer
) -> tuple[AIService, Any, Clock, list[float]]:
    clock = Clock()
    p, keypool = build_openai_compat_stack(settings, clock=clock)
    p._client = httpx.AsyncClient(transport=server.transport)
    sleeps: list[float] = []

    async def sleep(s: float) -> None:
        sleeps.append(s)

    return AIService(p, keypool, settings, clock=clock, sleep=sleep), keypool, clock, sleeps


async def generate(svc: AIService, task: Task = Task.phrasing_rewrite) -> Any:
    schema: type[BaseModel] = AnalysisModelOut if task is Task.analyze_single else RewriteOut
    return await svc.generate(
        task=task, parts=[Part.of_text("x")], system="SYS", schema=schema, request_id="rid"
    )


async def test_429_with_retry_after_cools_the_slot_for_exactly_n_seconds(tmp_path: Path) -> None:
    server = FakeServer(error(429, "Rate limit reached", **{"Retry-After": "17"}))
    svc, keypool, clock, _ = service(compat(tmp_path), server)
    with pytest.raises(ApiError) as info:
        await generate(svc)
    assert info.value.status == 429 and info.value.code is ErrorCode.quota_exhausted
    assert info.value.retry_after == 17
    ts = keypool.tier_state(0, ModelTier.fast)
    assert ts.state == "cooling" and ts.cooldown_until == clock.now + timedelta(seconds=17)


async def test_429_naming_a_daily_quota_benches_the_slot_for_the_day(tmp_path: Path) -> None:
    server = FakeServer(error(429, "Rate limit reached on tokens per day (TPD)"))
    svc, keypool, _, _ = service(compat(tmp_path), server)
    with pytest.raises(ApiError):
        await generate(svc)
    assert keypool.tier_state(0, ModelTier.fast).state == "rpd_exhausted"


async def test_alibaba_free_tier_only_is_a_daily_429(tmp_path: Path) -> None:
    server = FakeServer(error(403, "AllocationQuota.FreeTierOnly"))
    svc, keypool, _, _ = service(compat(tmp_path), server)
    with pytest.raises(ApiError) as info:
        await generate(svc)
    assert info.value.status == 429
    assert keypool.tier_state(0, ModelTier.fast).state == "rpd_exhausted"


@pytest.mark.parametrize("status", [401, 402, 403])
async def test_auth_and_payment_errors_disable_the_slot(tmp_path: Path, status: int) -> None:
    server = FakeServer(error(status, "denied"))
    svc, keypool, _, _ = service(compat(tmp_path), server)
    with pytest.raises(ApiError):
        await generate(svc)
    assert keypool.tier_state(0, ModelTier.fast).state == "disabled"


async def test_503_retries_the_same_slot_once_then_answers(tmp_path: Path) -> None:
    server = FakeServer(error(503, "busy"), ok())
    svc, _, _, sleeps = service(compat(tmp_path), server)
    out = await generate(svc)
    assert isinstance(out.result.parsed, RewriteOut) and len(server.bodies) == 2
    assert sleeps == [1.5]


async def test_500_is_upstream_unavailable_with_no_degraded_retry(tmp_path: Path) -> None:
    server = FakeServer(error(500, "boom"))
    svc, _, _, _ = service(compat(tmp_path), server)
    with pytest.raises(ApiError) as info:
        await generate(svc, Task.analyze_single)
    assert info.value.status == 503 and info.value.code is ErrorCode.upstream_unavailable
    assert len(server.bodies) == 1  # §4.5: no degraded path on openai_compat


async def test_schema_400_on_analyze_single_triggers_the_two_call_fallback(
    tmp_path: Path,
) -> None:
    server = FakeServer(error(400, "Unsupported response_format schema"))
    settings = compat(tmp_path, openai_compat_json_mode="json_schema")
    svc, _, _, _ = service(settings, server)
    with pytest.raises(SchemaFallbackNeeded):
        await generate(svc, Task.analyze_single)


async def test_invalid_output_after_repair_triggers_the_two_call_fallback(tmp_path: Path) -> None:
    svc, _, _, _ = service(compat(tmp_path), FakeServer(completion("{}")))
    with pytest.raises(SchemaFallbackNeeded):
        await generate(svc, Task.analyze_single)


async def test_upstream_log_line_names_the_provider_and_real_model(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    svc, _, _, _ = service(compat(tmp_path), FakeServer(ok()))
    with caplog.at_level(logging.INFO, logger="proxyhealth"):
        out = await generate(svc)
    assert out.route.model_id == "qwen3.5:2b" and out.result.model_id == "qwen3.5:2b"
    lines = [json.loads(r.getMessage()) for r in caplog.records if "upstream." in r.getMessage()]
    assert lines and lines[-1]["provider"] == "openai_compat" and lines[-1]["model"] == "qwen3.5:2b"


async def test_nothing_from_requests_or_responses_reaches_the_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    replies: list[Reply] = [
        error(429, f"quota {MARKER}"), completion(f'{{"sentence": "{MARKER}"}}'),
    ]  # fmt: skip
    for reply in replies:
        svc, _, _, _ = service(compat(tmp_path), FakeServer(reply))
        with caplog.at_level(logging.DEBUG):
            try:
                await svc.generate(
                    task=Task.phrasing_rewrite, parts=[Part.of_text(f"paper {MARKER}")],
                    system=f"sys {MARKER}", schema=RewriteOut, request_id="rid",
                )  # fmt: skip
            except ApiError as exc:
                assert MARKER not in exc.message
    out = capsys.readouterr()
    assert MARKER not in caplog.text and MARKER not in out.out and MARKER not in out.err


# ----------------------------------------------------------------------- PDFs + images (§4.8)


async def test_pdf_is_rasterised_to_png_pages_in_order_and_never_sent_as_pdf(
    tmp_path: Path,
) -> None:
    server = FakeServer(ok())
    parts = [Part.of_text("read"), Part.of_bytes(pdf(3), "application/pdf")]
    await call(provider(compat(tmp_path, openai_compat_max_images=3), server), parts=parts)
    urls = image_urls(server.bodies[0])
    assert len(urls) == 3 and all(u.startswith("data:image/png;base64,") for u in urls)
    assert max(decoded_size(urls[0])) == 1600
    assert "application/pdf" not in server.requests[0].content.decode()


async def test_pdf_over_the_image_cap_is_the_page_limit_error_before_any_call(
    tmp_path: Path,
) -> None:
    server = FakeServer(ok())
    p = provider(compat(tmp_path, openai_compat_max_images=2), server)
    with pytest.raises(ApiError) as info:
        await call(p, parts=[Part.of_bytes(pdf(3), "application/pdf")])
    assert (info.value.status, info.value.code) == (400, ErrorCode.pdf_too_long)
    assert info.value.details == {"max_pdf_pages": 2, "pages": 3}
    assert not server.bodies


async def test_images_over_the_cap_are_too_many_pages(tmp_path: Path) -> None:
    server = FakeServer(ok())
    p = provider(compat(tmp_path, openai_compat_max_images=2), server)
    with pytest.raises(ApiError) as info:
        await call(p, parts=[Part.of_bytes(png(), "image/png") for _ in range(3)])
    assert (info.value.status, info.value.code) == (400, ErrorCode.too_many_pages)
    assert not server.bodies


async def test_a_third_page_on_loopback_is_too_many_pages_by_default(tmp_path: Path) -> None:
    server = FakeServer(ok())
    with pytest.raises(ApiError) as info:
        await call(provider(compat(tmp_path), server),
                   parts=[Part.of_bytes(png(), "image/png") for _ in range(3)])  # fmt: skip
    assert (info.value.status, info.value.code) == (400, ErrorCode.too_many_pages)
    assert info.value.details == {"max_pages": 2, "pages": 3}
    assert not server.bodies
    hosted_server = FakeServer(ok())
    await call(provider(hosted(tmp_path, "openrouter.ai"), hosted_server),
               parts=[Part.of_bytes(png(), "image/png") for _ in range(3)])  # fmt: skip
    assert len(image_urls(hosted_server.bodies[0])) == 3


async def test_small_pages_pass_through_and_large_ones_are_downscaled(tmp_path: Path) -> None:
    server = FakeServer(ok())
    small = png(40, 20)
    parts = [Part.of_bytes(small, "image/png"), Part.of_bytes(jpeg(3200, 1000), "image/jpeg")]
    await call(provider(compat(tmp_path), server), parts=parts)
    first, second = image_urls(server.bodies[0])
    assert first == "data:image/png;base64," + base64.b64encode(small).decode()
    assert second.startswith("data:image/jpeg;base64,") and decoded_size(second) == (1600, 500)


async def test_webp_is_re_encoded_and_unreadable_pages_are_415(tmp_path: Path) -> None:
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(buf, format="WEBP")
    server = FakeServer(ok())
    await call(provider(compat(tmp_path), server),
               parts=[Part.of_bytes(buf.getvalue(), "image/webp")])  # fmt: skip
    assert image_urls(server.bodies[0])[0].startswith("data:image/jpeg;base64,")
    heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64  # no HEIC codec in this Pillow
    with pytest.raises(ApiError) as info:
        await call(provider(compat(tmp_path), FakeServer(ok())),
                   parts=[Part.of_bytes(heic, "image/heic")])  # fmt: skip
    assert info.value.status == 415


# ------------------------------------------------------------- concurrency + stack + slots


async def test_concurrency_limit_serialises_local_calls(tmp_path: Path) -> None:
    in_flight = 0
    peak = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return ok()

    p = OpenAICompatProvider(compat(tmp_path), transport=httpx.MockTransport(handler))
    await asyncio.gather(*(call(p) for _ in range(4)))
    assert peak == 1
    p4 = OpenAICompatProvider(compat(tmp_path, openai_compat_concurrency=4),
                              transport=httpx.MockTransport(handler))  # fmt: skip
    peak = 0
    await asyncio.gather(*(call(p4) for _ in range(4)))
    assert peak == 4


@pytest.mark.parametrize(
    ("tier", "billing", "data_tier"),
    [("local", True, DataUseTier.local), ("unpaid", False, DataUseTier.unpaid)],
)
def test_stack_has_one_synthetic_slot_with_the_configured_tier(
    tmp_path: Path, tier: str, billing: bool, data_tier: DataUseTier
) -> None:
    settings = compat(tmp_path, openai_compat_data_tier=tier, openai_compat_vendor_name="Me")
    p, keypool = build_openai_compat_stack(settings, clock=lambda: datetime.now(UTC))
    assert isinstance(p, OpenAICompatProvider) and len(keypool.slots) == 1
    slot = keypool.slots[0]
    assert slot.project == "openai_compat:127.0.0.1" and slot.billing is billing
    assert slot.key.get_secret_value() == "local"
    assert keypool.data_use_tier() is data_tier and keypool.snapshot().data_use_tier is data_tier
    keypool.persist()
    saved = (settings.var_dir / "keypool.json").read_text()
    assert "openai_compat:127.0.0.1" in saved and "11434" not in saved


async def test_slot_index_other_than_zero_is_refused(tmp_path: Path) -> None:
    p = provider(compat(tmp_path), FakeServer(ok()))
    with pytest.raises(ValueError):
        await p.generate_structured(
            task=Task.tag, tier=ModelTier.fast, parts=[Part.of_text("x")], system="s",
            schema=TaggingModelOut, thinking=None, media_resolution=None, max_output_tokens=64,
            request_id="r", slot_index=1,
        )  # fmt: skip


async def test_aclose_closes_the_http_client(tmp_path: Path) -> None:
    p = provider(compat(tmp_path), FakeServer(ok()))
    await p.aclose()
    assert p._client.is_closed
