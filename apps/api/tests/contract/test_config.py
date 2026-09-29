"""``GET /v1/config`` (API_CONTRACT §3.2): the D-01 tier matrix and D-25 language flags."""

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from proxyhealth_api import __version__
from proxyhealth_api.contracts.config import ServerConfig
from proxyhealth_api.settings import DATA_DIR
from tests.conftest import make_settings
from tests.contract._fixtures_wp1 import gemini, running


async def test_mock_is_demo_and_allows_samples_and_real_pages(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/config")
    cfg = ServerConfig.model_validate(r.json())
    assert cfg.provider == "mock" and cfg.data_use_tier == "demo"
    assert cfg.features.real_documents_allowed is True and cfg.features.demo_samples is True
    assert r.headers["X-Data-Use-Tier"] == "demo"
    assert cfg.key_slots.total == 0


@pytest.mark.parametrize(
    ("billing", "tier", "allowed"),
    [
        ((True,), "paid", True),
        ((True, True, True), "paid", True),
        ((True, False), "mixed", False),
        ((False, True, True), "mixed", False),
        ((False,), "unpaid", False),
        ((False, False), "unpaid", False),
    ],
)
async def test_tier_matrix(
    tmp_path: Path, billing: tuple[bool, ...], tier: str, allowed: bool
) -> None:
    async with running(gemini(tmp_path, *billing)) as (_app, client):
        r = await client.get("/v1/config")
        cfg = ServerConfig.model_validate(r.json())
        assert cfg.provider == "gemini"
        assert cfg.data_use_tier == tier and r.headers["X-Data-Use-Tier"] == tier
        assert cfg.features.real_documents_allowed is allowed
        assert cfg.key_slots.total == len(billing) and cfg.key_slots.healthy == len(billing)


async def test_dev_bypass_turns_real_documents_on(tmp_path: Path) -> None:
    settings = gemini(tmp_path, False, allow_unpaid_real_documents=True)
    async with running(settings) as (_app, client):
        cfg = ServerConfig.model_validate((await client.get("/v1/config")).json())
        assert cfg.data_use_tier == "unpaid" and cfg.features.real_documents_allowed is True


async def test_gemini_without_slots_is_tier_none(tmp_path: Path) -> None:
    async with running(make_settings(tmp_path, ai_provider="gemini")) as (_app, client):
        cfg = ServerConfig.model_validate((await client.get("/v1/config")).json())
        assert cfg.data_use_tier == "none" and cfg.features.real_documents_allowed is False


async def test_models_limits_versions(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, max_pages=7, allow_degraded=False)
    async with running(settings) as (_app, client):
        cfg = ServerConfig.model_validate((await client.get("/v1/config")).json())
    assert cfg.api_version == __version__ and cfg.contract_version == 1
    assert cfg.models.pro == "gemini-3.8-flash" and cfg.models.fast == "gemini-3.5-flash-lite"
    assert cfg.models.pro_degraded_thinking == "medium"
    assert cfg.features.degraded_fallback is False
    assert cfg.limits.max_pages == 7 and cfg.limits.max_request_bytes == 20_971_520
    assert cfg.limits.max_question_chars == 1000 and cfg.limits.max_user_goal_chars == 300
    en_bytes = (DATA_DIR / "langpacks" / "en.json").read_bytes()
    assert cfg.base_pack_version == hashlib.sha256(en_bytes).hexdigest()
    assert cfg.consent_version == "2026-09-24" and cfg.region_notice == "us_only"
    assert cfg.privacy_policy_url.startswith("https://")
    assert cfg.taxonomy_version and cfg.resource_db_version and cfg.rules_version
    assert cfg.server_time.tzinfo is not None


async def test_languages_bundled_and_machine_translated_come_from_pack_files(
    client: httpx.AsyncClient,
) -> None:
    cfg = ServerConfig.model_validate((await client.get("/v1/config")).json())
    by_tag = {lang.tag: lang for lang in cfg.languages}
    langpacks = DATA_DIR / "langpacks"
    for tag, info in by_tag.items():
        path = langpacks / f"{tag}.json"
        assert info.bundled is path.is_file(), tag
        if tag == "en":
            assert info.machine_translated is False
        elif path.is_file():
            declared = json.loads(path.read_text(encoding="utf-8"))["machine_translated"]
            assert info.machine_translated is declared, tag
        else:
            assert info.machine_translated is True, tag
    assert by_tag["prs"].direction == "rtl" and by_tag["prs"].digit_system == "persian"
    assert by_tag["en"].tier == 1 and by_tag["prs"].tier == 2
