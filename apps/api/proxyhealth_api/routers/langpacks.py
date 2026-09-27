"""``GET/POST /v1/language-packs`` (API_CONTRACT §3.3, §3.4). WP1 adds chunking, QA, disk cache."""

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from proxyhealth_api.ai.failover import AIService
from proxyhealth_api.ai.provider import Part, Task
from proxyhealth_api.analysis.pipeline import parsed_as
from proxyhealth_api.contracts.common import LanguageTag
from proxyhealth_api.contracts.enums import DigitSystem, Direction, ErrorCode, PackSource, PackTier
from proxyhealth_api.contracts.langpack import LanguagePack, LanguagePackRequest
from proxyhealth_api.contracts.model_out import LanguagePackModelOut, LanguageResolveOut
from proxyhealth_api.deps import get_ai, get_languages, get_pack_cache, get_packs, get_request_id
from proxyhealth_api.errors import ApiError, error_responses
from proxyhealth_api.packs.base import BasePack, LanguageTable
from proxyhealth_api.packs.cache import PackCache

router = APIRouter(prefix="/v1/language-packs", tags=["language-packs"])

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _pack_response(pack: LanguagePack) -> JSONResponse:
    return JSONResponse(content=pack.model_dump(mode="json"), headers={"ETag": pack.etag})


@router.get(
    "/{tag}",
    response_model=LanguagePack,
    responses={
        304: {"description": "Not Modified (ETag matched)"},
        **error_responses(400, 404, 409),
    },
)
async def get_language_pack(
    tag: LanguageTag,
    request: Request,
    cache: Annotated[PackCache, Depends(get_pack_cache)],
    base: Annotated[BasePack, Depends(get_packs)],
    pack_version: str | None = None,
) -> Response:
    if pack_version is not None and pack_version != base.version:
        raise ApiError(
            ErrorCode.pack_version_mismatch,
            409,
            "Client base pack hash differs from the server's.",
            details={"server_pack_version": base.version},
        )
    pack = cache.bundled(tag) or cache.get(tag, base.version)
    if pack is None:
        raise ApiError(ErrorCode.not_found, 404, f"No language pack for tag {tag!r}.")
    if request.headers.get("if-none-match") == pack.etag:
        return Response(status_code=304, headers={"ETag": pack.etag})
    return _pack_response(pack)


async def _resolve_tag(
    req: LanguagePackRequest, languages: LanguageTable, ai: AIService, rid: str
) -> str:
    if req.hint_tag:
        return req.hint_tag
    known = languages.resolve(req.language_query)
    if known:
        return known
    outcome = await ai.generate(
        task=Task.resolve_language, parts=[Part.of_text(req.language_query)], system="",
        schema=LanguageResolveOut, request_id=rid, hints={"language_query": req.language_query},
    )  # fmt: skip
    resolved = parsed_as(outcome, LanguageResolveOut)
    if resolved.language_tag:
        return resolved.language_tag
    slug = _SLUG_RE.sub("-", req.language_query.lower()).strip("-")[:32]
    if not slug:
        raise ApiError(
            ErrorCode.language_unresolved, 422, "The typed language could not be resolved."
        )
    return f"x-{slug}"


@router.post("", response_model=LanguagePack, responses=error_responses(400, 409, 422, 429, 503))
async def create_language_pack(
    req: LanguagePackRequest,
    rid: Annotated[str, Depends(get_request_id)],
    ai: Annotated[AIService, Depends(get_ai)],
    cache: Annotated[PackCache, Depends(get_pack_cache)],
    base: Annotated[BasePack, Depends(get_packs)],
    languages: Annotated[LanguageTable, Depends(get_languages)],
) -> Response:
    if req.pack_version != base.version:
        raise ApiError(
            ErrorCode.pack_version_mismatch,
            409,
            "Client base pack hash differs from the server's.",
            details={"server_pack_version": base.version},
        )
    tag = await _resolve_tag(req, languages, ai, rid)
    existing = cache.bundled(tag) or cache.get(tag, base.version)
    if existing is not None:
        return _pack_response(existing)
    async with cache.single_flight(tag):
        cached = cache.get(tag, base.version)
        if cached is not None:
            return _pack_response(cached)
        entry = languages.get(tag)
        strings_json = json.dumps(base.strings, ensure_ascii=False, sort_keys=True)
        outcome = await ai.generate(
            task=Task.langpack_chunk, parts=[Part.of_text(strings_json)], system="",
            schema=LanguagePackModelOut, request_id=rid,
            hints={
                "language_tag": tag, "strings_json": strings_json,
                "language_name_en": entry.name_en if entry else req.language_query,
                "language_name_native": entry.name_native if entry else req.language_query,
            },
        )  # fmt: skip
        out = parsed_as(outcome, LanguagePackModelOut)
        strings = dict(base.strings)
        translated = {kv.key: kv.value for kv in out.strings if kv.key in strings and kv.value}
        strings.update(translated)
        fallback = sorted(k for k in strings if k not in translated)
        pack = LanguagePack(
            language_tag=tag,
            language_name_native=entry.name_native if entry else out.language_name_native,
            language_name_en=entry.name_en if entry else out.language_name_en,
            direction=entry.direction if entry else Direction(out.direction),
            script=entry.script if entry else out.script,
            digit_system=entry.digit_system if entry else DigitSystem(out.digit_system),
            font_hint=entry.font_hint if entry else None,
            tier=entry.tier if entry else PackTier.tier_3,
            source=PackSource.generated,
            pack_version=base.version,
            etag=hashlib.sha256(json.dumps(strings, sort_keys=True).encode()).hexdigest(),
            strings=strings,
            fallback_keys=fallback,
            coverage=1 - len(fallback) / max(len(strings), 1),
            machine_translated=True,
            reviewed_by=None,
            confidence=out.confidence,
            generated_at=datetime.now(UTC),
            tts_tag=entry.tts_tag if entry else None,
            tts_fallback_tag=entry.tts_fallback_tag if entry else None,
        )
        cache.put(pack)
        return _pack_response(pack)
