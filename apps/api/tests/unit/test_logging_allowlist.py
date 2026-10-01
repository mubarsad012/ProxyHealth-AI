"""Content-free logging (ARCHITECTURE §2.1 "Logging", §7; D-08).

Any key outside the allow-list raises under pytest, and a full request cycle (analyze, chat,
language pack, errors) emits only allow-listed keys and never the request's text.
"""

import io
import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import BaseModel

from proxyhealth_api import logging_
from proxyhealth_api.logging_ import (
    ALLOWED_FIELDS,
    BOOT_MESSAGE_LEN,
    MAX_STRING_LEN,
    LogFieldError,
    check_fields,
    configure_logging,
    log_event,
    serving,
    set_strict,
)
from tests.conftest import make_settings
from tests.contract._fixtures_wp1 import demo_body, page_body, running

EXPECTED_FIELDS = {
    "ts", "request_id", "route", "status", "error_code", "provider", "model", "tier",
    "slot_index", "quality", "analysis_mode", "latency_ms", "input_tokens", "output_tokens",
    "thought_tokens", "page_count", "total_bytes", "document_type", "category", "urgency_level",
    "scam_risk", "contacts_stripped", "phrasing_rewrites", "facts_total", "facts_unverified",
    "injection_suspected", "target_language", "detected_language", "install_id_hash",
    "client_platform", "data_use_tier",
}  # fmt: skip


@pytest.fixture
def captured() -> Iterator[io.StringIO]:
    configure_logging("info")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("proxyhealth")
    logger.addHandler(handler)
    try:
        yield stream
    finally:
        logger.removeHandler(handler)


def lines(stream: io.StringIO) -> list[dict[str, object]]:
    out = []
    for line in stream.getvalue().splitlines():
        if line.startswith("{"):
            out.append(json.loads(line))
    return out


def test_allow_list_is_exactly_the_architecture_set() -> None:
    assert set(ALLOWED_FIELDS) == EXPECTED_FIELDS


def test_unknown_key_raises_under_pytest() -> None:
    with pytest.raises(LogFieldError):
        log_event(route="x", quote="the paper says...")
    with pytest.raises(LogFieldError):
        check_fields({"filename": "scan.jpg"})
    check_fields({"route": "x", "status": 200})


def test_non_strict_mode_drops_unknown_keys(captured: io.StringIO) -> None:
    set_strict(False)
    try:
        log_event(route="x", transcript="secret words", status=200)
    finally:
        set_strict(None)
    (entry,) = lines(captured)
    assert entry["route"] == "x" and entry["status"] == 200 and "transcript" not in entry
    assert "secret" not in captured.getvalue() and "ts" in entry


def test_values_are_scalars_and_truncated(captured: io.StringIO) -> None:
    log_event(route="r" * 500, slot_index=2, quality=None, contacts_stripped=True)
    (entry,) = lines(captured)
    assert isinstance(entry["route"], str) and len(entry["route"]) == MAX_STRING_LEN
    assert entry["slot_index"] == 2 and entry["quality"] is None
    assert entry["contacts_stripped"] is True


def test_uvicorn_access_log_is_disabled() -> None:
    configure_logging("info")
    assert logging.getLogger("uvicorn.access").disabled is True
    assert logging_.is_strict() is True


async def test_request_cycle_logs_only_allowed_keys(
    tmp_path: Path, captured: io.StringIO, tiny_png_base64: str
) -> None:
    secret = "SECRET-QUESTION-TEXT"
    async with running(make_settings(tmp_path)) as (_app, client):
        consent = {"X-Consent-Version": "2026-10-01", "X-Install-Id": "install-123"}
        await client.post("/v1/analyze", json=page_body(tiny_png_base64), headers=consent)
        await client.post("/v1/analyze", json=demo_body())
        await client.post("/v1/analyze", json=page_body(tiny_png_base64))  # 428
        await client.post("/v1/chat", json={"question": secret}, headers=consent)
        version = (await client.get("/v1/config")).json()["base_pack_version"]
        await client.post(
            "/v1/language-packs", json={"language_query": "Hakha Chin", "pack_version": version}
        )
        await client.get("/v1/nope")
    entries = lines(captured)
    assert entries, "the access log must emit one line per request"
    for entry in entries:
        assert set(entry) <= ALLOWED_FIELDS, set(entry) - ALLOWED_FIELDS
    text = captured.getvalue()
    assert secret not in text and tiny_png_base64[:40] not in text
    assert "install-123" not in text  # only the HMAC hash may appear
    routes = {e.get("route") for e in entries}
    assert {"/v1/analyze", "/v1/language-packs", "/v1/chat", "unmatched"} <= routes


async def test_access_log_records_the_body_client_platform(
    tmp_path: Path, captured: io.StringIO, tiny_png_base64: str
) -> None:
    """Regression: client_platform came from an X-Client-Platform header nobody sends, so it was
    always null. The contract carries it in the body (AnalyzeRequest/TroubleshootRequest)."""
    shot = {"mime_type": "image/png", "data_base64": tiny_png_base64}
    screen = {"screenshot": shot, "target_language": "en", "client_platform": "android",
              "demo_sample_id": "portal_file_too_large"}  # fmt: skip
    async with running(make_settings(tmp_path)) as (_app, client):
        assert (await client.post("/v1/analyze", json=demo_body())).status_code == 200
        assert (await client.post("/v1/troubleshoot", json=screen)).status_code == 200
        ios = {**demo_body(), "client_platform": "ios"}
        r = await client.post("/v1/analyze", json=ios, headers={"X-Client-Platform": "android"})
        assert r.status_code == 200
        bad = {**demo_body(), "client_platform": "desktop"}  # not a Platform: 400, logged null
        assert (await client.post("/v1/analyze", json=bad)).status_code == 400
        await client.post("/v1/analyze", json=page_body(tiny_png_base64))  # 428 still has it
    access = [e for e in lines(captured) if "client_platform" in e and "latency_ms" in e]
    got = [(e["route"], e["status"], e["client_platform"]) for e in access]
    assert got == [
        ("/v1/analyze", 200, "web"), ("/v1/troubleshoot", 200, "android"),
        ("/v1/analyze", 200, "ios"), ("/v1/analyze", 400, None), ("/v1/analyze", 428, "web"),
    ]  # fmt: skip


SECRET = "MODEL-PROSE-SECRET your caseworker Jane Doe"


class _Strict(BaseModel):
    n: int


@pytest.fixture
def formatted() -> Iterator[io.StringIO]:
    """The ``proxyhealth`` logger's output through the production JSON formatter."""
    configure_logging("info")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging_._JsonFormatter())
    logger = logging.getLogger("proxyhealth")
    logger.addHandler(handler)
    try:
        yield stream
    finally:
        logger.removeHandler(handler)


def test_stdlib_records_keep_only_their_template_while_serving(formatted: io.StringIO) -> None:
    log = logging.getLogger("proxyhealth.some_module")
    with serving():
        log.warning("resource DB: %s", SECRET)
        log.warning("quicksheet_resources_dropped=%d of %d", 3, 7)
        log.warning('{"quote": "%s"}', SECRET)  # a leading "{" is not a free pass
        log.warning("y" * 500)
        try:
            raise ValueError(SECRET)
        except ValueError:
            log.exception("chunk failed")
    text = formatted.getvalue()
    entries = [json.loads(line) for line in text.splitlines()]
    assert len(entries) == 5
    for entry in entries:
        assert set(entry) == {"ts", "route"} and len(str(entry["route"])) <= MAX_STRING_LEN
    assert entries[0]["route"] == "resource DB: %s"
    assert entries[1]["route"] == "quicksheet_resources_dropped=3 of 7"
    assert SECRET not in text and "Jane" not in text and "Traceback" not in text


def test_stdlib_boot_records_keep_their_detail(
    formatted: io.StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(logging_, "_serving", 0)  # no request can be in flight at boot
    path = "data/resources/national_immigration.yaml:177"
    logging.getLogger("proxyhealth.resources").warning("resource DB: %s", path)
    logging.getLogger("proxyhealth.resources").warning("z" * 5000)
    first, second = (json.loads(line) for line in formatted.getvalue().splitlines())
    assert first["route"] == f"resource DB: {path}"
    assert len(second["route"]) == BOOT_MESSAGE_LEN


def test_log_event_lines_pass_through_the_formatter(formatted: io.StringIO) -> None:
    log_event(route="/v1/config", status=200)
    (entry,) = (json.loads(line) for line in formatted.getvalue().splitlines())
    assert entry["route"] == "/v1/config" and entry["status"] == 200


def test_uvicorn_error_log_never_prints_a_traceback() -> None:
    configure_logging("info")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)  # default formatter appends exc_info when present
    uv_error = logging.getLogger("uvicorn.error")
    uv_error.addHandler(handler)
    try:
        try:
            _Strict(n=SECRET)
        except Exception as exc:  # noqa: BLE001
            uv_error.error("Exception in ASGI application\n", exc_info=exc)
        logging.getLogger("uvicorn").error("boom", stack_info=True)
    finally:
        uv_error.removeHandler(handler)
    text = stream.getvalue()
    assert "Exception in ASGI application" in text
    assert SECRET not in text and "input_value" not in text and "Traceback" not in text
    assert "Stack (most recent call last)" not in text


def test_uvicorn_access_log_stays_off_even_when_reenabled() -> None:
    configure_logging("info")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    access = logging.getLogger("uvicorn.access")
    access.addHandler(handler)
    access.disabled = False  # what uvicorn's own dictConfig does when uvicorn.run(app) starts
    try:
        access.warning('%s - "GET /v1/resources/%s HTTP/1.1" %d', "10.0.0.1", "some-id", 200)
    finally:
        access.removeHandler(handler)
        configure_logging("info")
    assert stream.getvalue() == ""


async def test_unhandled_exception_text_never_reaches_the_logs(
    tmp_path: Path, formatted: io.StringIO, capsys: pytest.CaptureFixture[str]
) -> None:
    async def pydantic_boom() -> None:
        _Strict(n=SECRET)

    async def value_boom() -> None:
        raise ValueError(SECRET)

    # raise_app_exceptions=True: a re-raised exception would fail the request below.
    async with running(make_settings(tmp_path)) as (app, client):
        app.add_api_route("/_boom", pydantic_boom)
        app.add_api_route("/_boom2", value_boom)
        origin = {"Origin": "http://localhost:8081"}
        responses = [await client.get(path, headers=origin) for path in ("/_boom", "/_boom2")]
    for r in responses:
        assert r.status_code == 500 and r.json()["error"]["code"] == "internal"
        assert r.headers["access-control-allow-origin"] == "http://localhost:8081"
        assert SECRET not in r.text
    entries = [json.loads(line) for line in formatted.getvalue().splitlines()]
    access = [e for e in entries if e.get("route") in ("/_boom", "/_boom2") and "latency_ms" in e]
    assert [e["status"] for e in access] == [500, 500]  # the real status, not 0
    out, err = capsys.readouterr()
    everything = formatted.getvalue() + out + err
    assert SECRET not in everything and "Jane" not in everything and "input_value" not in everything
