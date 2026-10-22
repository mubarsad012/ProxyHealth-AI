"""A client that goes away stops its request's model call (``routers/_cancel.py``; LOCAL_AI.md §5).

The app is driven as a raw ASGI callable so the test controls ``receive``: it delivers the
``/v1/analyze`` body, then ``http.disconnect`` once the fake OpenAI-compatible server (an
``httpx.MockTransport`` that never answers) has the call. No network and no model."""

import asyncio
import json
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

import httpx
import pytest

from proxyhealth_api.ai.openai_compat import OpenAICompatProvider
from proxyhealth_api.main import create_app
from proxyhealth_api.routers import _cancel
from proxyhealth_api.settings import Settings
from tests.conftest import make_settings
from tests.contract._fixtures_wp1 import demo_body, running


def compat(tmp_path: Path) -> Settings:
    return make_settings(
        tmp_path, ai_provider="openai_compat", openai_compat_data_tier="local",
        openai_compat_model_label="Qwen",
    )  # fmt: skip


def scope_for(path: str, body: bytes) -> dict[str, Any]:
    return {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
        "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
        "root_path": "", "client": ("127.0.0.1", 50000), "server": ("test", 80),
        "headers": [
            (b"host", b"test"), (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
    }  # fmt: skip


class StuckModel:
    """A model server that never answers; records when the call starts and is cancelled."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self._never = asyncio.Event()

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.started.set()
        try:
            await self._never.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        raise AssertionError("unreachable")


async def test_disconnect_cancels_the_model_call_and_frees_the_slot(tmp_path: Path) -> None:
    app = create_app(compat(tmp_path))
    async with app.router.lifespan_context(app):
        provider = app.state.provider
        assert isinstance(provider, OpenAICompatProvider)
        model = StuckModel()
        provider._client = httpx.AsyncClient(transport=httpx.MockTransport(model))
        body = json.dumps(demo_body()).encode()
        gone = asyncio.Event()
        delivered = False
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            await gone.wait()
            return {"type": "http.disconnect"}

        async def send(message: MutableMapping[str, Any]) -> None:
            sent.append(dict(message))

        app_task = asyncio.ensure_future(app(scope_for("/v1/analyze", body), receive, send))
        await asyncio.wait_for(model.started.wait(), 10)
        gone.set()  # the reader pressed Cancel
        await asyncio.wait_for(model.cancelled.wait(), 2)
        await asyncio.wait_for(app_task, 2)
        # The one loopback slot is free at once for the reader's retry.
        await asyncio.wait_for(provider._semaphore.acquire(), 0.5)
        provider._semaphore.release()
        starts = [m for m in sent if m["type"] == "http.response.start"]
        assert [m["status"] for m in starts] == [_cancel.CLIENT_GONE_STATUS]


async def test_other_providers_never_watch_the_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    watched: list[object] = []

    async def record(request: object) -> None:
        watched.append(request)

    monkeypatch.setattr(_cancel, "_client_gone", record)
    async with running(make_settings(tmp_path)) as (_app, client):
        r = await client.post("/v1/analyze", json=demo_body())
        assert r.status_code == 200
    assert watched == []


async def test_a_finished_request_answers_normally_on_openai_compat(tmp_path: Path) -> None:
    async def done() -> str:
        return "result"

    class Req:
        async def receive(self) -> dict[str, Any]:
            await asyncio.Event().wait()  # the client stays connected
            return {"type": "http.disconnect"}

    request: Any = Req()  # only ``receive`` is used
    out = await _cancel.run_until_disconnect(request, done(), compat(tmp_path), request_id="rid")
    assert out == "result"
