"""Error envelope, consent + tier gate, body limit, rate limit (BUILD_PLAN §5.2 steps 2 and 8).

API_CONTRACT §0.1: every non-2xx answer is ``{"error": ErrorBody}``; ``Retry-After`` on every
429/503; D-01 gate: 428 without consent, 403 on unpaid/mixed unless a known ``demo_sample_id``.
"""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from proxyhealth_api.ai.mock import MockProvider
from proxyhealth_api.contracts.enums import ErrorCode
from proxyhealth_api.contracts.errors import ErrorResponse
from proxyhealth_api.errors import ApiError
from proxyhealth_api.middleware import consent_is_current
from tests.conftest import make_settings
from tests.contract._fixtures_wp1 import demo_body, gemini, page_body, running

CONSENT = {"X-Consent-Version": "2026-09-24"}


def envelope(r: httpx.Response, status: int, code: str) -> ErrorResponse:
    assert r.status_code == status, r.text
    body = ErrorResponse.model_validate(r.json())
    assert body.error.code == code
    assert body.error.user_message_key == f"err.{code}"
    assert body.error.request_id == r.headers["X-Request-Id"]
    assert r.headers["X-Contract-Version"] == "1"
    assert r.headers["X-Data-Use-Tier"]
    assert set(r.json()["error"]) == {
        "code", "message", "user_message_key", "retry_after_seconds", "key_exhausted",
        "request_id", "details",
    }  # fmt: skip
    return body


def _add_raising_routes(app: FastAPI) -> None:
    async def quota() -> None:
        raise ApiError(
            ErrorCode.quota_exhausted, 429, "All slots cooling.", retry_after=240,
            key_exhausted=True, details={"tier": "pro", "slots_total": 3},
        )  # fmt: skip

    async def upstream() -> None:
        raise ApiError(ErrorCode.upstream_unavailable, 503, "Upstream 5xx.")

    async def unsupported() -> None:
        raise ApiError(ErrorCode.unsupported_media_type, 415, "MIME not allowed.")

    async def boom() -> None:
        raise RuntimeError("secret document text must never reach the envelope")

    app.add_api_route("/_test/429", quota)
    app.add_api_route("/_test/503", upstream)
    app.add_api_route("/_test/415", unsupported)
    app.add_api_route("/_test/500", boom)


@pytest.fixture
async def raising(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    async with running(make_settings(tmp_path), raise_app_exceptions=False) as (app, client):
        _add_raising_routes(app)
        yield client


async def test_400_validation(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/analyze", json={"target_language": "en"}, headers=CONSENT)
    body = envelope(r, 400, "invalid_request")
    assert body.error.retry_after_seconds is None and body.error.key_exhausted is False


async def test_400_unknown_field_is_rejected(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/v1/language-packs",
        json={"language_query": "Dari", "pack_version": "x", "packVersion": "typo"},
    )
    envelope(r, 400, "invalid_request")


async def test_400_message_never_echoes_client_keys(client: httpx.AsyncClient) -> None:
    secret = "Jane Doe DOB 1950-01-01"
    r = await client.post(
        "/v1/language-packs", json={"language_query": "Dari", "pack_version": "x", secret: 1}
    )
    body = envelope(r, 400, "invalid_request")
    assert secret not in r.text and "Jane" not in body.error.message
    assert body.error.message == "Request validation failed at: body.<extra>"
    bad = await client.post(
        "/v1/analyze",
        json={"pages": [{"mime_type": "image/png"}], "target_language": "en"},
        headers=CONSENT,
    )
    assert "body.pages.0.data_base64" in envelope(bad, 400, "invalid_request").error.message


async def test_415_declared_mime_outside_the_allow_list(
    client: httpx.AsyncClient, tiny_png_base64: str
) -> None:
    body = page_body(tiny_png_base64)
    body["pages"] = [{"mime_type": "image/gif", "data_base64": tiny_png_base64}]
    r = await client.post("/v1/analyze", json=body, headers=CONSENT)
    assert "body.pages.0.mime_type" in envelope(r, 415, "unsupported_media_type").error.message


async def test_404_unknown_path_and_resource(client: httpx.AsyncClient) -> None:
    envelope(await client.get("/v1/does-not-exist"), 404, "not_found")
    envelope(await client.get("/v1/language-packs/xx"), 404, "not_found")


async def test_405_is_an_envelope(client: httpx.AsyncClient) -> None:
    r = await client.delete("/v1/config")
    assert r.status_code == 405
    ErrorResponse.model_validate(r.json())


async def test_413_declared_length_before_parsing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, max_request_bytes=1000)
    async with running(settings) as (_app, client):
        # No consent header: the body limit answers before the gate or the JSON parser run.
        r = await client.post(
            "/v1/analyze", content=b"{" + b" " * 2000, headers={"Content-Type": "application/json"}
        )
        body = envelope(r, 413, "payload_too_large")
        assert body.error.details == {"max_request_bytes": 1000}


async def test_413_streamed_body_without_content_length(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, max_request_bytes=1000)

    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(10):
            yield b"x" * 300

    async with running(settings) as (_app, client):
        r = await client.post(
            "/v1/analyze", content=chunks(), headers={"Content-Type": "application/json"}
        )
        assert "content-length" not in {k.lower() for k in r.request.headers}
        envelope(r, 413, "payload_too_large")


async def test_streamed_body_within_limit_is_replayed(tmp_path: Path) -> None:
    raw = json.dumps(demo_body()).encode()

    async def chunks() -> AsyncIterator[bytes]:
        yield raw[:10]
        yield raw[10:]

    async with running(make_settings(tmp_path)) as (_app, client):
        r = await client.post(
            "/v1/analyze", content=chunks(), headers={"Content-Type": "application/json"}
        )
        assert r.status_code == 200, r.text


async def test_415_envelope(raising: httpx.AsyncClient) -> None:
    envelope(await raising.get("/_test/415"), 415, "unsupported_media_type")


async def test_429_quota_has_retry_after(raising: httpx.AsyncClient) -> None:
    r = await raising.get("/_test/429")
    body = envelope(r, 429, "quota_exhausted")
    assert r.headers["Retry-After"] == "240"
    assert body.error.retry_after_seconds == 240 and body.error.key_exhausted is True
    assert body.error.details == {"tier": "pro", "slots_total": 3}


async def test_503_always_has_retry_after(raising: httpx.AsyncClient) -> None:
    r = await raising.get("/_test/503")
    body = envelope(r, 503, "upstream_unavailable")
    assert int(r.headers["Retry-After"]) > 0
    # Raised without retry_after: the body still mirrors the header (API_CONTRACT §0.1).
    assert body.error.retry_after_seconds == int(r.headers["Retry-After"])


async def test_500_is_content_free(raising: httpx.AsyncClient) -> None:
    r = await raising.get("/_test/500")
    body = envelope(r, 500, "internal")
    assert "secret" not in r.text and body.error.message == "Unexpected server error."


async def test_428_without_consent(client: httpx.AsyncClient, tiny_png_base64: str) -> None:
    r = await client.post("/v1/analyze", json=page_body(tiny_png_base64))
    body = envelope(r, 428, "consent_required")
    assert body.error.details == {"consent_version": "2026-09-24"}


@pytest.mark.parametrize("given", ["2026-01-01", "not-a-date", "zzzz", ""])
async def test_428_stale_or_malformed_consent(
    client: httpx.AsyncClient, tiny_png_base64: str, given: str
) -> None:
    r = await client.post("/v1/chat", json={"question": "x"}, headers={"X-Consent-Version": given})
    envelope(r, 428, "consent_required")


def test_consent_version_rules() -> None:
    assert consent_is_current("2026-09-24", "2026-09-24")
    assert consent_is_current(" 2026-10-01 ", "2026-09-24")
    assert not consent_is_current("2026-09-23", "2026-09-24")
    assert not consent_is_current("zzzz", "2026-09-24") and not consent_is_current(None, "x")
    assert consent_is_current("v2", "v2") and not consent_is_current("v3", "v2")


async def test_newer_consent_is_accepted(client: httpx.AsyncClient, tiny_png_base64: str) -> None:
    r = await client.post(
        "/v1/analyze", json=page_body(tiny_png_base64), headers={"X-Consent-Version": "2027-01-01"}
    )
    assert r.status_code == 200, r.text


async def test_demo_sample_without_consent_header_is_200(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/analyze", json=demo_body())
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("billing", [(False,), (True, False)], ids=["unpaid", "mixed"])
async def test_403_unpaid_or_mixed_tier_blocks_real_pages(
    tmp_path: Path, tiny_png_base64: str, billing: tuple[bool, ...]
) -> None:
    async with running(gemini(tmp_path, *billing)) as (_app, client):
        r = await client.post("/v1/analyze", json=page_body(tiny_png_base64), headers=CONSENT)
        body = envelope(r, 403, "unpaid_tier_real_documents_disabled")
        tier = "unpaid" if billing == (False,) else "mixed"
        assert r.headers["X-Data-Use-Tier"] == tier
        assert body.error.details == {"data_use_tier": tier}
        for path in ("/v1/troubleshoot", "/v1/chat"):
            r2 = await client.post(path, json={"question": "x"}, headers=CONSENT)
            envelope(r2, 403, "unpaid_tier_real_documents_disabled")


async def test_unknown_demo_sample_id_is_not_exempt_from_the_403_gate(
    tmp_path: Path, tiny_png_base64: str
) -> None:
    body = {**page_body(tiny_png_base64), "demo_sample_id": "not-a-real-fixture"}
    async with running(gemini(tmp_path, False)) as (_app, client):
        r = await client.post("/v1/analyze", json=body, headers=CONSENT)
        envelope(r, 403, "unpaid_tier_real_documents_disabled")


async def test_unknown_demo_sample_id_without_consent_is_428(
    client: httpx.AsyncClient, tiny_png_base64: str
) -> None:
    body = {**page_body(tiny_png_base64), "demo_sample_id": "not-a-real-fixture"}
    envelope(await client.post("/v1/analyze", json=body), 428, "consent_required")
    chat = {"question": "x", "demo_sample_id": "not-a-real-fixture"}
    envelope(await client.post("/v1/chat", json=chat), 428, "consent_required")


def _offline(app: FastAPI) -> None:
    """Keep the gemini-mode key pool but answer from fixtures: tests never touch the network."""
    app.state.ai.provider = MockProvider(app.state.fixtures, app.state.settings)


async def test_unpaid_tier_demo_sample_passes_the_gate(tmp_path: Path) -> None:
    async with running(gemini(tmp_path, False)) as (app, client):
        _offline(app)
        r = await client.post("/v1/analyze", json=demo_body())
        assert r.status_code == 200, r.text
        assert r.headers["X-Data-Use-Tier"] == "unpaid"


async def test_unpaid_dev_bypass_flag(tmp_path: Path, tiny_png_base64: str) -> None:
    settings = gemini(tmp_path, False, allow_unpaid_real_documents=True)
    async with running(settings) as (app, client):
        _offline(app)
        r = await client.post("/v1/analyze", json=page_body(tiny_png_base64), headers=CONSENT)
        assert r.status_code == 200, r.text


async def test_401_app_token_when_enforced(tmp_path: Path) -> None:
    async with running(make_settings(tmp_path, app_token="s3cret")) as (_app, client):
        envelope(await client.get("/v1/config"), 401, "unauthorized")
        wrong = await client.get("/v1/config", headers={"X-App-Token": "nope"})
        envelope(wrong, 401, "unauthorized")
        ok = await client.get("/v1/config", headers={"X-App-Token": "s3cret"})
        assert ok.status_code == 200


async def test_429_rate_limited_per_install(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, rate_limit_analyze_per_hour=2)
    headers = {"X-Install-Id": "4f7c2c1e-0000-4000-8000-000000000001"}
    async with running(settings) as (_app, client):
        for _ in range(2):
            ok = await client.post("/v1/analyze", json=demo_body(), headers=headers)
            assert ok.status_code == 200, ok.text
        r = await client.post("/v1/analyze", json=demo_body(), headers=headers)
        body = envelope(r, 429, "rate_limited")
        assert body.error.key_exhausted is False
        assert int(r.headers["Retry-After"]) == body.error.retry_after_seconds
        other = {"X-Install-Id": "4f7c2c1e-0000-4000-8000-000000000002"}
        again = await client.post("/v1/analyze", json=demo_body(), headers=other)
        assert again.status_code == 200


async def test_request_id_is_echoed(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/language-packs/xx", headers={"X-Request-Id": "abc-123"})
    assert r.headers["X-Request-Id"] == "abc-123"
    assert r.json()["error"]["request_id"] == "abc-123"
    bad = await client.get("/health", headers={"X-Request-Id": "has spaces in it"})
    assert bad.headers["X-Request-Id"] != "has spaces in it"


async def test_cors_headers_on_error_responses(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, max_request_bytes=10)
    async with running(settings) as (_app, client):
        r = await client.post(
            "/v1/analyze", content=b"x" * 50, headers={"Origin": "http://localhost:8081"}
        )
        assert r.status_code == 413
        assert r.headers["access-control-allow-origin"] == "http://localhost:8081"
        pre = await client.options(
            "/v1/analyze",
            headers={
                "Origin": "http://localhost:8081",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-Consent-Version",
            },
        )
        assert pre.status_code == 200
