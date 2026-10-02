"""``AI_PROVIDER=openai_compat`` through the HTTP surface (free-ai-providers §4.6, §5.2):
``/v1/config`` and ``/health`` fields, ``X-Data-Use-Tier``, the tier gate per tier, and a full
``/v1/analyze`` against a fake OpenAI-compatible server (``httpx.MockTransport``, no network)."""

import base64
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from proxyhealth_api.contracts.analysis import AnalysisResult
from proxyhealth_api.contracts.config import HealthResponse, ServerConfig
from proxyhealth_api.contracts.model_out import RewriteOut, TaggingModelOut
from proxyhealth_api.demo.fixtures import FixtureStore
from proxyhealth_api.settings import DATA_DIR, Settings
from tests.conftest import make_settings
from tests.contract._fixtures_wp1 import demo_body, gemini, running

CONSENT = {"X-Consent-Version": "2026-10-01"}
SAMPLE = "medicaid_address_confirmation"


def compat(tmp_path: Path, tier: str = "local", **overrides: object) -> Settings:
    values: dict[str, object] = {
        "ai_provider": "openai_compat",
        "openai_compat_data_tier": tier,
        "openai_compat_model_label": "Qwen",
        "openai_compat_vendor_name": "Groq" if tier != "local" else "",
    }
    if tier == "attested":
        values |= {
            "openai_compat_base_url": "https://api.groq.com/openai/v1",
            "openai_compat_api_key": "sk-test-0001",
            "openai_compat_no_training_attested": True,
        }
    values.update(overrides)
    return make_settings(tmp_path, **values)


class FakeModel:
    """Answers each structured-output request by its ``json_schema`` name: the sample's recorded
    analysis for ``AnalysisModelOut``, minimal valid objects for the small tasks."""

    def __init__(self) -> None:
        fx = FixtureStore.load(DATA_DIR / "fixtures").get(SAMPLE)
        assert fx is not None
        out = fx.analysis_out("en")
        assert out is not None
        self.answers: dict[str, str] = {
            "AnalysisModelOut": out.model_dump_json(),
            "TaggingModelOut": TaggingModelOut(
                tags=[], geo_state=None, geo_county=None, geo_city=None, geo_zip=None,
                institutions_as_written=[], emergency=False,
            ).model_dump_json(),  # fmt: skip
            "RewriteOut": RewriteOut(sentence="The paper says to reply.").model_dump_json(),
        }
        self.schemas: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        name = body["response_format"]["json_schema"]["name"]
        self.schemas.append(name)
        if name not in self.answers:
            return httpx.Response(400, json={"error": {"message": f"no answer for {name}"}})
        message = {"role": "assistant", "content": self.answers[name]}
        return httpx.Response(200, json={
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1200, "completion_tokens": 300},
        })  # fmt: skip


@asynccontextmanager
async def serving(
    settings: Settings, model: FakeModel | None = None
) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient]]:
    async with running(settings) as (app, client):
        if model is not None:  # the provider's own client, pointed at the fake server
            app.state.provider._client = httpx.AsyncClient(transport=httpx.MockTransport(model))
        yield app, client


def page_body() -> dict[str, Any]:
    png = (DATA_DIR / "fixtures" / SAMPLE / "page-1.png").read_bytes()
    page = {"mime_type": "image/png", "data_base64": base64.b64encode(png).decode("ascii")}
    return {"pages": [page], "target_language": "en", "client_platform": "web"}


# ------------------------------------------------------------------------------- /v1/config


async def test_config_on_the_local_tier(tmp_path: Path) -> None:
    async with serving(compat(tmp_path, openai_compat_max_images=8)) as (_app, client):
        r = await client.get("/v1/config")
        cfg = ServerConfig.model_validate(r.json())
        assert r.headers["X-Data-Use-Tier"] == "local"
        assert cfg.provider == "openai_compat" and cfg.data_use_tier == "local"
        assert cfg.ai_model_label == "Qwen" and cfg.ai_vendor_name is None
        assert cfg.features.real_documents_allowed is True and cfg.features.chat is True
        assert cfg.features.degraded_fallback is False
        assert (cfg.models.pro, cfg.models.fast) == ("qwen3.5:4b", "qwen3.5:4b")
        assert (cfg.limits.max_pages, cfg.limits.max_pdf_pages) == (8, 8)
        t = cfg.client_timeouts
        assert (t.analyze_s, t.troubleshoot_s, t.language_pack_s, t.chat_s, t.default_s) == (
            625, 625, 625, 625, 30,
        )  # fmt: skip
        assert cfg.key_slots.total == 1 and cfg.key_slots.healthy == 1
        health = HealthResponse.model_validate((await client.get("/health")).json())
        assert health.provider == "openai_compat" and health.data_use_tier == "local"
        assert (health.keys_configured, health.keys_healthy, health.status) == (1, 1, "ok")


@pytest.mark.parametrize(("tier", "allowed"), [("attested", True), ("unpaid", False)])
async def test_config_on_the_hosted_tiers(tmp_path: Path, tier: str, allowed: bool) -> None:
    async with serving(compat(tmp_path, tier)) as (_app, client):
        r = await client.get("/v1/config")
        cfg = ServerConfig.model_validate(r.json())
        assert cfg.data_use_tier == tier and r.headers["X-Data-Use-Tier"] == tier
        assert cfg.ai_vendor_name == "Groq"
        assert cfg.features.real_documents_allowed is allowed and cfg.features.chat is allowed


async def test_config_defaults_for_mock_and_gemini(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    cfg = ServerConfig.model_validate((await client.get("/v1/config")).json())
    assert cfg.ai_model_label is None and cfg.ai_vendor_name is None
    t = cfg.client_timeouts
    assert (t.analyze_s, t.troubleshoot_s, t.language_pack_s, t.chat_s, t.default_s) == (
        120, 60, 60, 30, 30,
    )  # fmt: skip
    assert (cfg.limits.max_pages, cfg.limits.max_pdf_pages) == (12, 60)
    async with running(gemini(tmp_path, True)) as (_app, gclient):
        gcfg = ServerConfig.model_validate((await gclient.get("/v1/config")).json())
        assert (gcfg.ai_model_label, gcfg.ai_vendor_name) == ("Gemini", "Google")


async def test_admin_keys_report_the_configured_tier(tmp_path: Path) -> None:
    async with serving(compat(tmp_path, admin_token="adm")) as (_app, client):
        r = await client.get("/v1/admin/keys", headers={"X-Admin-Token": "adm"})
        assert r.status_code == 200 and r.json()["data_use_tier"] == "local"
        assert r.json()["slots"][0]["project"] == "openai_compat:127.0.0.1"


# ------------------------------------------------------------------------------- tier gate


async def test_unpaid_refuses_real_pages_and_chat_but_serves_samples(tmp_path: Path) -> None:
    model = FakeModel()
    async with serving(compat(tmp_path, "unpaid"), model) as (_app, client):
        real = await client.post("/v1/analyze", json=page_body(), headers=CONSENT)
        assert real.status_code == 403 and real.headers["X-Data-Use-Tier"] == "unpaid"
        assert real.json()["error"]["code"] == "unpaid_tier_real_documents_disabled"
        sample = await client.post("/v1/analyze", json=demo_body(SAMPLE))
        assert sample.status_code == 200, sample.text[:300]
        assert AnalysisResult.model_validate(sample.json()).model_meta.data_use_tier == "unpaid"


async def test_local_analyze_end_to_end_with_verified_demands(tmp_path: Path) -> None:
    model = FakeModel()
    async with serving(compat(tmp_path), model) as (_app, client):
        missing = await client.post("/v1/analyze", json=page_body())
        assert missing.status_code == 428  # consent still required
        r = await client.post("/v1/analyze", json=page_body(), headers=CONSENT)
        assert r.status_code == 200, r.text[:300]
        assert r.headers["X-Data-Use-Tier"] == "local"
        result = AnalysisResult.model_validate(r.json())
        assert result.demands, "the fake model's facts verify against its own transcript"
        meta = result.model_meta
        assert (meta.provider, meta.model_id, meta.data_use_tier) == (
            "openai_compat", "qwen3.5:4b", "local",
        )  # fmt: skip
        assert meta.thinking_level is None and meta.demo is False
    assert model.schemas[0] == "AnalysisModelOut"


async def test_local_tier_when_ollama_is_down_is_a_content_free_503(tmp_path: Path) -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async with running(compat(tmp_path)) as (app, client):
        app.state.provider._client = httpx.AsyncClient(transport=httpx.MockTransport(refused))
        r = await client.post("/v1/analyze", json=page_body(), headers=CONSENT)
        assert r.status_code == 503 and r.headers["Retry-After"] == "30"
        assert r.json()["error"]["code"] == "provider_not_configured"
        assert r.json()["error"]["message"] == "Local AI server is not running."
