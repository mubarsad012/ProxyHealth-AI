"""``/v1/language-packs`` contract (API_CONTRACT §3.3, §3.4; D-25; BUILD_PLAN §5.2 step 4).

GET: bundled/cached pack, ``ETag`` + ``304``, ``409`` on a stale base, ``404`` unknown, ``400``
invalid tag. POST: resolve → bundled/cached/generated (mock pseudo-localizes and is never
cached), single-flight, disk cache only for real packs with coverage >= 0.9, ``409``, ``422``.
Generator: 2 chunks in flight, one retry of failing keys, partial pack on mid-pack quota loss,
§7.6 direction table, §7.7 confidence cap.
"""

import asyncio
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from proxyhealth_api.ai.failover import AIService, GenerateOutcome
from proxyhealth_api.ai.provider import Part, StructuredResult, Task, Usage
from proxyhealth_api.ai.routing import RouteConfig
from proxyhealth_api.contracts.enums import (
    Confidence,
    DigitSystem,
    Direction,
    ErrorCode,
    ModelQuality,
    ModelTier,
)
from proxyhealth_api.contracts.errors import ErrorResponse
from proxyhealth_api.contracts.langpack import LanguagePack
from proxyhealth_api.contracts.model_out import KeyValue, LanguagePackModelOut, LanguageResolveOut
from proxyhealth_api.errors import ApiError
from proxyhealth_api.packs.base import BasePack, LanguageTable
from proxyhealth_api.packs.generator import Target, generate_pack
from proxyhealth_api.settings import DATA_DIR
from tests.conftest import make_settings
from tests.contract._fixtures_wp1 import gemini, running

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


async def test_mock_pack_is_served_but_never_cached(tmp_path: Path) -> None:
    """AI_PROMPTS §7.10: pseudo packs never reach var/, so a provider switch never serves one."""
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
        assert pack.tier == 3 and pack.confidence == "low"
        assert not list((settings.var_dir / "langpacks").glob("*.json"))
        got = await client.get("/v1/language-packs/x-hakha-chin")
        assert got.status_code == 404  # the client POSTs again and gets a fresh pseudo pack
        again = await client.post("/v1/language-packs", json=body)
        assert again.status_code == 200 and again.json()["source"] == "generated"
    # A real provider in the same VAR_DIR finds nothing to serve.
    async with running(gemini(tmp_path, True)) as (_app, client):
        assert (await client.get("/v1/language-packs/x-hakha-chin")).status_code == 404


async def test_real_pack_is_cached_and_served(tmp_path: Path) -> None:
    settings = gemini(tmp_path, True)
    async with running(settings) as (app, client):
        fake = _TranslatingAI()
        app.state.ai = fake
        version = await base_version(client)
        body = {"language_query": "Hakha Chin", "pack_version": version}
        r = await client.post("/v1/language-packs", json=body)
        assert r.status_code == 200, r.text
        pack = LanguagePack.model_validate(r.json())
        assert pack.language_tag == "x-hakha-chin" and pack.source == "generated"
        assert pack.coverage == 1.0 and pack.fallback_keys == []
        assert pack.strings["home.scan_cta"].startswith("T· ")
        assert pack.confidence == "medium"  # x- tag: never above medium (AI_PROMPTS §7.7)
        cached_file = settings.var_dir / "langpacks" / f"x-hakha-chin--{version}.json"
        assert cached_file.is_file()
        got = await client.get("/v1/language-packs/x-hakha-chin")
        assert got.status_code == 200 and got.json()["source"] == "cache"
        assert got.headers["ETag"] == pack.etag
        not_modified = await client.get(
            "/v1/language-packs/x-hakha-chin", headers={"If-None-Match": pack.etag}
        )
        assert not_modified.status_code == 304
        # A hint the server knows only from its cache is ignored (languages.yaml only, §7.2).
        hinted = await client.post(
            "/v1/language-packs",
            json={"language_query": "Kaqchikel", "pack_version": version,
                  "hint_tag": "x-hakha-chin"},
        )  # fmt: skip
        assert hinted.status_code == 200 and hinted.json()["language_tag"] == "x-kaqchikel"
    # A fresh process serves the pack from var/langpacks without regenerating it.
    async with running(settings) as (_app, client):
        again = await client.get("/v1/language-packs/x-hakha-chin")
        assert again.status_code == 200 and again.json()["etag"] == pack.etag


async def test_thin_pack_is_returned_but_not_cached(tmp_path: Path) -> None:
    settings = gemini(tmp_path, True)
    async with running(settings) as (app, client):
        app.state.ai = _TranslatingAI(omit_every=5)  # 20 % of keys never come back
        version = await base_version(client)
        body = {"language_query": "Hakha Chin", "pack_version": version}
        r = await client.post("/v1/language-packs", json=body)
        assert r.status_code == 200, r.text
        pack = LanguagePack.model_validate(r.json())
        assert pack.coverage < 0.9 and pack.confidence == "low"
        assert not list((settings.var_dir / "langpacks").glob("*.json"))
        assert (await client.get("/v1/language-packs/x-hakha-chin")).status_code == 404


async def test_unusable_resolve_answer_falls_back_to_private_tag(tmp_path: Path) -> None:
    async with running(gemini(tmp_path, True)) as (app, client):
        app.state.ai = _TranslatingAI(resolve_error=ErrorCode.model_output_invalid)
        version = await base_version(client)
        r = await client.post(
            "/v1/language-packs", json={"language_query": "Hakha Chin", "pack_version": version}
        )
        assert r.status_code == 200, r.text
        assert r.json()["language_tag"] == "x-hakha-chin"


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


async def test_single_flight_generates_once(tmp_path: Path) -> None:
    async with running(gemini(tmp_path, True)) as (app, client):
        fake = _TranslatingAI()
        app.state.ai = fake
        version = await base_version(client)
        body = {"language_query": "Kaqchikel", "pack_version": version}
        first, second = await asyncio.gather(
            client.post("/v1/language-packs", json=body),
            client.post("/v1/language-packs", json=body),
        )
        assert first.status_code == second.status_code == 200
        assert first.json()["etag"] == second.json()["etag"]
        n_chunks = len(app.state.packs.chunks(60))
        assert len(fake.chunk_calls) == n_chunks  # one generation, not two
        assert fake.max_in_flight == 2  # AI_PROMPTS §7.4: at most 2 chunks in flight


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


# ---------------------------------------------------------------- a gemini-like fake AI


def _outcome(parsed: BaseModel) -> GenerateOutcome:
    route = RouteConfig(
        tier=ModelTier.fast, model_id="gemini-3.5-flash-lite", thinking=None,
        media_resolution=None, max_output_tokens=8192,
    )  # fmt: skip
    result = StructuredResult(parsed=parsed, raw_text=None, model_id=route.model_id, usage=Usage())
    return GenerateOutcome(
        result=result, route=route, quality=ModelQuality.full, slot_index=0, attempts=1
    )


class _TranslatingAI:
    """Stands in for a real provider: "T· <English>" (QA-clean, no pseudo marker)."""

    def __init__(
        self, *, omit_every: int = 0, bad_first: frozenset[str] = frozenset(),
        quota_after: int | None = None, resolve_error: ErrorCode | None = None,
        script: str | None = "Latn", confidence: Confidence = Confidence.high,
    ) -> None:  # fmt: skip
        self.omit_every = omit_every
        self.bad_first = bad_first  # empty value the first time a key is asked for
        self.quota_after = quota_after  # chunk calls from this index on raise 429
        self.resolve_error = resolve_error
        self.script = script
        self.confidence = confidence
        self.chunk_calls: list[list[str]] = []
        self.seen: set[str] = set()
        self.in_flight = 0
        self.max_in_flight = 0

    async def generate(
        self, *, task: Task, parts: Sequence[Part], system: str, schema: Any,
        pages: int = 1, is_pdf: bool = False, request_id: str,
        hints: Mapping[str, str] | None = None,
    ) -> GenerateOutcome:  # fmt: skip
        hints = hints or {}
        if task is Task.resolve_language:
            if self.resolve_error is not None:
                raise ApiError(self.resolve_error, 502, "unusable")
            return _outcome(
                LanguageResolveOut(
                    language_tag=None, language_name_en=hints["language_query"],
                    language_name_native=None, script=None, direction=Direction.ltr,
                    digit_system=DigitSystem.western, confidence=Confidence.low,
                )  # fmt: skip
            )
        strings: dict[str, str] = json.loads(hints["strings_json"])
        index = len(self.chunk_calls)
        self.chunk_calls.append(list(strings))
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0.001)
            if self.quota_after is not None and index >= self.quota_after:
                raise ApiError(
                    ErrorCode.quota_exhausted, 429, "quota", retry_after=60, key_exhausted=True
                )
        finally:
            self.in_flight -= 1
        pairs = []
        for i, (key, english) in enumerate(strings.items()):
            if self.omit_every and i % self.omit_every == 0:
                continue
            bad = key in self.bad_first and key not in self.seen
            self.seen.add(key)
            pairs.append(KeyValue(key=key, value="" if bad else f"T· {english}"))
        return _outcome(
            LanguagePackModelOut(
                language_tag=hints["language_tag"], language_name_native="Native",
                language_name_en=hints["language_name_en"], direction=Direction.ltr,
                script=self.script, digit_system=DigitSystem.western, strings=pairs,
                fallback_keys=[], confidence=self.confidence, notes_for_reviewer=None,
            )  # fmt: skip
        )


# ------------------------------------------------------------ generator (AI_PROMPTS §7)

_BASE = BasePack.load(DATA_DIR / "langpacks" / "en.json")
_X = Target(tag="x-hakha-chin", name_en="Hakha Chin", name_native="Hakha Chin")


async def test_chunk_with_many_failures_is_retried_once_with_only_failing_keys() -> None:
    chunks = _BASE.chunks(60)
    many = frozenset(chunks[0][:30])  # 50 % of chunk 1 fails QA → retried
    few = frozenset(chunks[1][:5])  # < 20 % of chunk 2 fails → no retry, English fallback
    fake = _TranslatingAI(bad_first=many | few)
    result = await generate_pack(_X, _BASE, fake, request_id="r")  # type: ignore[arg-type]
    retries = fake.chunk_calls[len(chunks):]
    assert retries == [chunks[0][:30]]  # one retry, only the failing keys
    assert result.pack.fallback_keys == sorted(few)
    assert all(result.pack.strings[k].startswith("T· ") for k in many)
    assert all(result.pack.strings[k] == _BASE.strings[k] for k in few)


async def test_quota_mid_pack_returns_a_partial_pack() -> None:
    fake = _TranslatingAI(quota_after=2)
    result = await generate_pack(_X, _BASE, fake, request_id="r")  # type: ignore[arg-type]
    n_chunks = len(_BASE.chunks(60))
    assert len(fake.chunk_calls) <= 4 < n_chunks  # later chunks never start
    pack = result.pack
    assert 0 < pack.coverage < 0.9 and pack.confidence == "low"
    assert set(pack.fallback_keys) == {k for c in _BASE.chunks(60)[2:] for k in c}
    assert result.failed_chunks == n_chunks - 2


async def test_quota_before_any_work_is_a_429() -> None:
    fake = _TranslatingAI(quota_after=0)
    with pytest.raises(ApiError) as exc:
        await generate_pack(_X, _BASE, fake, request_id="r")  # type: ignore[arg-type]
    assert exc.value.status == 429 and exc.value.code == "quota_exhausted"
    assert len(fake.chunk_calls) <= 2  # the first failure stops everything not yet started


@pytest.mark.parametrize(
    ("script", "want"),
    [("Arab", ("Arab", "rtl")), ("Rohg", ("Rohg", "rtl")), ("Latn", ("Latn", "ltr")),
     ("Arabic", (None, "ltr")), (None, (None, "ltr"))],
)  # fmt: skip
async def test_direction_sanity_table_for_unknown_tags(
    script: str | None, want: tuple[str | None, str]
) -> None:
    fake = _TranslatingAI(script=script)
    pack = (await generate_pack(_X, _BASE, fake, request_id="r")).pack  # type: ignore[arg-type]
    assert (pack.script, pack.direction) == want
    assert pack.tier == 3 and pack.confidence == "medium"  # Tier 3 / x-: capped at medium


async def test_languages_yaml_row_overrides_the_model() -> None:
    table = LanguageTable.load(DATA_DIR / "languages.yaml", DATA_DIR / "langpacks")
    entry = table.get("rhg")
    assert entry is not None
    target = Target(tag="rhg", name_en=entry.name_en, name_native=entry.name_native, entry=entry)
    fake = _TranslatingAI(script="Latn")
    pack = (await generate_pack(target, _BASE, fake, request_id="r")).pack  # type: ignore[arg-type]
    assert pack.direction == "rtl" and pack.script == entry.script
