"""``/v1/language-packs`` contract (API_CONTRACT §3.3, §3.4; D-25; BUILD_PLAN §5.2 step 4).

GET: bundled/cached pack, ``ETag`` + ``304``, ``409`` on a stale base, ``404`` unknown, ``400``
invalid tag. POST: resolve → bundled/cached/generated (mock pseudo-localizes), single-flight,
disk cache, ``409``, ``422``.
"""

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from proxyhealth_api.ai.failover import AIService, GenerateOutcome
from proxyhealth_api.ai.provider import Part, Task
from proxyhealth_api.contracts.enums import ErrorCode
from proxyhealth_api.contracts.errors import ErrorResponse
from proxyhealth_api.contracts.langpack import LanguagePack
from proxyhealth_api.errors import ApiError
from proxyhealth_api.settings import DATA_DIR
from tests.conftest import make_settings
from tests.contract._fixtures_wp1 import running

BUNDLED = sorted(
    p.stem for p in (DATA_DIR / "langpacks").glob("*.json") if not p.name.startswith("_")
)


async def base_version(client: httpx.AsyncClient) -> str:
    version: str = (await client.get("/v1/config")).json()["base_pack_version"]
    return version


def code_of(r: httpx.Response) -> str:
    return ErrorResponse.model_validate(r.json()).error.code.value


@pytest.mark.parametrize("tag", BUNDLED)
async def test_get_every_bundled_pack(client: httpx.AsyncClient, tag: str) -> None:
    r = await client.get(f"/v1/language-packs/{tag}")
    assert r.status_code == 200, r.text
    pack = LanguagePack.model_validate(r.json())
    assert pack.language_tag == tag and pack.source == "bundled"
    assert r.headers["ETag"] == pack.etag and len(pack.etag) == 64
    assert pack.pack_version == await base_version(client)
    assert set(pack.strings) == set((await client.get("/v1/language-packs/en")).json()["strings"])
    assert pack.machine_translated is (tag != "en")
    assert 0.0 <= pack.coverage <= 1.0


async def test_etag_304_bare_quoted_weak_and_list(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/language-packs/en")
    etag = r.headers["ETag"]
    for value in (etag, f'"{etag}"', f'W/"{etag}"', f'"nope", "{etag}"', "*"):
        again = await client.get("/v1/language-packs/en", headers={"If-None-Match": value})
        assert again.status_code == 304, value
        assert again.headers["ETag"] == etag and again.content == b""
    miss = await client.get("/v1/language-packs/en", headers={"If-None-Match": '"other"'})
    assert miss.status_code == 200


async def test_get_409_on_stale_base(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/language-packs/en", params={"pack_version": "0" * 64})
    assert r.status_code == 409 and code_of(r) == "pack_version_mismatch"
    assert r.json()["error"]["details"]["server_pack_version"] == await base_version(client)
    ok = await client.get(
        "/v1/language-packs/en", params={"pack_version": await base_version(client)}
    )
    assert ok.status_code == 200


async def test_get_404_and_400(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/language-packs/rhg")  # known language, not bundled, not cached
    assert r.status_code == 404 and code_of(r) == "not_found"
    bad = await client.get("/v1/language-packs/not_a..tag")
    assert bad.status_code == 400 and code_of(bad) == "invalid_request"


async def test_post_409_and_422(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/v1/language-packs", json={"language_query": "Dari", "pack_version": "x"}
    )
    assert r.status_code == 409 and code_of(r) == "pack_version_mismatch"
    version = await base_version(client)
    garbage = await client.post(
        "/v1/language-packs", json={"language_query": "!!! ???", "pack_version": version}
    )
    assert garbage.status_code == 422 and code_of(garbage) == "language_unresolved"
    empty = await client.post(
        "/v1/language-packs", json={"language_query": "", "pack_version": version}
    )
    assert empty.status_code == 400


async def test_post_resolves_to_bundled_pack(client: httpx.AsyncClient) -> None:
    version = await base_version(client)
    r = await client.post(
        "/v1/language-packs", json={"language_query": "English", "pack_version": version}
    )
    assert r.status_code == 200
    assert r.json()["language_tag"] == "en" and r.json()["source"] == "bundled"


async def test_post_generates_caches_and_serves(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    async with running(settings) as (_app, client):
        version = await base_version(client)
        body = {"language_query": "Hakha Chin", "pack_version": version, "hint_tag": None}
        r = await client.post("/v1/language-packs", json=body)
        assert r.status_code == 200, r.text
        pack = LanguagePack.model_validate(r.json())
        assert pack.language_tag == "x-hakha-chin" and pack.source == "generated"
        assert pack.machine_translated is True and pack.reviewed_by is None
        assert pack.pack_version == version and r.headers["ETag"] == pack.etag
        assert pack.strings["home.scan_cta"].startswith("⟦x-hakha-chin⟧")  # mock pseudo-loc
        assert pack.coverage == pytest.approx(1 - len(pack.fallback_keys) / len(pack.strings))
        assert pack.tier == 3
        cached_file = settings.var_dir / "langpacks" / f"x-hakha-chin--{version}.json"
        assert cached_file.is_file()
        got = await client.get("/v1/language-packs/x-hakha-chin")
        assert got.status_code == 200 and got.json()["source"] == "cache"
        assert got.headers["ETag"] == pack.etag
        not_modified = await client.get(
            "/v1/language-packs/x-hakha-chin", headers={"If-None-Match": pack.etag}
        )
        assert not_modified.status_code == 304
    # A fresh process serves the pack from var/langpacks without regenerating it.
    async with running(settings) as (_app, client):
        again = await client.get("/v1/language-packs/x-hakha-chin")
        assert again.status_code == 200 and again.json()["etag"] == pack.etag


async def test_post_known_unbundled_language_uses_languages_yaml(client: httpx.AsyncClient) -> None:
    version = await base_version(client)
    r = await client.post(
        "/v1/language-packs", json={"language_query": "Rohingya", "pack_version": version}
    )
    assert r.status_code == 200, r.text
    pack = LanguagePack.model_validate(r.json())
    assert pack.language_tag == "rhg" and pack.direction == "rtl" and pack.tier == 3
    assert pack.font_hint == "NotoSansHanifiRohingya"


class _CountingAI:
    """Wraps the app's ``AIService`` and counts ``langpack_chunk`` calls."""

    def __init__(self, inner: AIService, *, invalid_chunks: bool = False) -> None:
        self.inner = inner
        self.chunks = 0
        self.calls = 0
        self.invalid_chunks = invalid_chunks

    async def generate(
        self, *, task: Task, parts: Sequence[Part], system: str, schema: Any,
        pages: int = 1, is_pdf: bool = False, request_id: str,
        hints: Mapping[str, str] | None = None,
    ) -> GenerateOutcome:  # fmt: skip
        self.calls += 1
        if task is Task.langpack_chunk:
            self.chunks += 1
            await asyncio.sleep(0)
            if self.invalid_chunks:
                raise ApiError(ErrorCode.model_output_invalid, 502, "schema failed")
        return await self.inner.generate(
            task=task, parts=parts, system=system, schema=schema, pages=pages,
            is_pdf=is_pdf, request_id=request_id, hints=hints,
        )  # fmt: skip


async def test_single_flight_generates_once(app: FastAPI, client: httpx.AsyncClient) -> None:
    counting = _CountingAI(app.state.ai)
    app.state.ai = counting
    version = await base_version(client)
    body = {"language_query": "Kaqchikel", "pack_version": version}
    first, second = await asyncio.gather(
        client.post("/v1/language-packs", json=body), client.post("/v1/language-packs", json=body)
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["etag"] == second.json()["etag"]
    n_chunks = len(app.state.packs.chunks(60))
    assert counting.chunks == n_chunks  # one generation, not two


async def test_hint_tag_is_used_only_when_known(client: httpx.AsyncClient) -> None:
    version = await base_version(client)
    r = await client.post(
        "/v1/language-packs",
        json={"language_query": "whatever", "pack_version": version, "hint_tag": "en"},
    )
    assert r.json()["language_tag"] == "en"
    unknown_hint = await client.post(
        "/v1/language-packs",
        json={"language_query": "Hakha Chin", "pack_version": version, "hint_tag": "zz-Fake"},
    )
    assert unknown_hint.json()["language_tag"] == "x-hakha-chin"


@pytest.mark.parametrize("query", ["123", "!!! 123 ???", "٣٤٥", "x-123"])
async def test_post_query_without_letters_is_422_before_any_model_call(
    app: FastAPI, client: httpx.AsyncClient, query: str
) -> None:
    counting = _CountingAI(app.state.ai)
    app.state.ai = counting
    version = await base_version(client)
    r = await client.post(
        "/v1/language-packs", json={"language_query": query, "pack_version": version}
    )
    assert r.status_code == 422 and code_of(r) == "language_unresolved", r.text
    assert counting.calls == 0


async def test_post_typed_private_tag_keeps_its_tag(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    counting = _CountingAI(app.state.ai)
    app.state.ai = counting
    version = await base_version(client)
    r = await client.post(
        "/v1/language-packs", json={"language_query": "x-foo", "pack_version": version}
    )
    assert r.status_code == 200, r.text
    assert r.json()["language_tag"] == "x-foo"  # never "x-x-foo"
    assert counting.calls == counting.chunks  # no resolve call, only the chunk calls


async def test_post_every_chunk_invalid_is_a_declared_503(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    app.state.ai = _CountingAI(app.state.ai, invalid_chunks=True)
    version = await base_version(client)
    r = await client.post(
        "/v1/language-packs", json={"language_query": "Kaqchikel", "pack_version": version}
    )
    assert r.status_code == 503 and code_of(r) == "upstream_unavailable", r.text
    assert int(r.headers["Retry-After"]) > 0
    assert r.json()["error"]["retry_after_seconds"] == int(r.headers["Retry-After"])
    route = app.openapi()["paths"]["/v1/language-packs"]["post"]["responses"]
    assert "503" in route and "502" not in route
