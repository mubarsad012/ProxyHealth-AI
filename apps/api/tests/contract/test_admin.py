"""``GET /v1/admin/keys`` (API_CONTRACT §3.14; CL-013: always mounted, 404 while unset)."""

from pathlib import Path

from proxyhealth_api.contracts.admin import AdminKeysResponse
from proxyhealth_api.contracts.errors import ErrorResponse
from tests.conftest import make_settings
from tests.contract._fixtures_wp1 import FAKE_KEYS, gemini, running


async def test_404_while_admin_token_unset(tmp_path: Path) -> None:
    async with running(make_settings(tmp_path)) as (_app, client):
        r = await client.get("/v1/admin/keys", headers={"X-Admin-Token": "anything"})
        assert r.status_code == 404
        assert ErrorResponse.model_validate(r.json()).error.code == "not_found"


async def test_401_without_or_with_wrong_token(tmp_path: Path) -> None:
    async with running(make_settings(tmp_path, admin_token="adm1n")) as (_app, client):
        for headers in ({}, {"X-Admin-Token": "wrong"}):
            r = await client.get("/v1/admin/keys", headers=headers)
            assert r.status_code == 401
            assert ErrorResponse.model_validate(r.json()).error.code == "unauthorized"


async def test_mock_mode_has_no_slots(tmp_path: Path) -> None:
    async with running(make_settings(tmp_path, admin_token="adm1n")) as (_app, client):
        r = await client.get("/v1/admin/keys", headers={"X-Admin-Token": "adm1n"})
        assert r.status_code == 200
        body = AdminKeysResponse.model_validate(r.json())
        assert body.data_use_tier == "demo" and body.slots == []


async def test_gemini_snapshot_is_content_free(tmp_path: Path) -> None:
    settings = gemini(tmp_path, True, False, admin_token="adm1n")
    async with running(settings) as (_app, client):
        r = await client.get("/v1/admin/keys", headers={"X-Admin-Token": "adm1n"})
        assert r.status_code == 200
        body = AdminKeysResponse.model_validate(r.json())
        assert body.data_use_tier == "mixed"
        assert [s.index for s in body.slots] == [0, 1]
        assert [s.billing for s in body.slots] == [True, False]
        assert body.slots[0].key_last4 == FAKE_KEYS[0][-4:]
        assert set(body.slots[0].tiers) == {"pro", "fast"}
        for key in FAKE_KEYS[:2]:
            assert key not in r.text  # never the key string itself
