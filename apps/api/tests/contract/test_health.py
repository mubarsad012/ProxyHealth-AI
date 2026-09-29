"""``GET /health`` (API_CONTRACT §3.1) in mock and gemini modes."""

from pathlib import Path

import httpx

from proxyhealth_api import __version__
from proxyhealth_api.contracts.config import HealthResponse
from proxyhealth_api.contracts.enums import ModelTier
from tests.conftest import make_settings
from tests.contract._fixtures_wp1 import gemini, running


async def test_mock_health(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    body = HealthResponse.model_validate(r.json())
    assert body.status == "ok" and body.provider == "mock"
    assert body.version == __version__ and body.contract_version == 1
    assert body.keys_configured == 0 and body.keys_healthy == 0
    assert body.data_use_tier == "demo"
    assert body.resources_loaded >= 0
    assert r.headers["X-Data-Use-Tier"] == "demo"


async def test_gemini_health_counts_slots(tmp_path: Path) -> None:
    async with running(gemini(tmp_path, True, True)) as (_app, client):
        body = HealthResponse.model_validate((await client.get("/health")).json())
        assert body.provider == "gemini" and body.status == "ok"
        assert body.keys_configured == 2 and body.keys_healthy == 2
        assert body.data_use_tier == "paid"


async def test_gemini_health_degraded_when_no_slot_is_healthy(tmp_path: Path) -> None:
    async with running(gemini(tmp_path, True)) as (app, client):
        pool = app.state.keypool
        slot = pool.slot(0)
        for tier in ModelTier:
            pool.report(slot, tier, outcome="4xx_fatal", retry_after=None, error_text=None)
        body = HealthResponse.model_validate((await client.get("/health")).json())
        assert body.status == "degraded" and body.keys_healthy == 0


async def test_gemini_without_slots_in_development_is_degraded_tier_none(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, ai_provider="gemini", env="development")
    async with running(settings) as (_app, client):
        r = await client.get("/health")
        body = HealthResponse.model_validate(r.json())
        assert body.status == "degraded" and body.data_use_tier == "none"
        assert r.headers["X-Data-Use-Tier"] == "none"
