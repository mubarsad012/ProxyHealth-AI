"""``GET/POST /v1/language-packs`` (API_CONTRACT §3.3, §3.4; D-25).

Route functions carry no docstrings on purpose: FastAPI turns them into OpenAPI descriptions,
and ``openapi.json`` is a frozen snapshot.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from proxyhealth_api.ai.failover import AIService
from proxyhealth_api.contracts.common import LanguageTag
from proxyhealth_api.contracts.enums import ErrorCode, Provider
from proxyhealth_api.contracts.langpack import LanguagePack, LanguagePackRequest
from proxyhealth_api.deps import (
    get_ai,
    get_languages,
    get_pack_cache,
    get_packs,
    get_request_id,
    get_settings,
)
from proxyhealth_api.errors import ApiError, error_responses
from proxyhealth_api.logging_ import log_event
from proxyhealth_api.packs.base import BasePack, LanguageTable
from proxyhealth_api.packs.cache import MIN_CACHE_COVERAGE, PackCache, is_pseudo
from proxyhealth_api.packs.generator import Target, generate_pack
from proxyhealth_api.packs.resolve import Resolution, resolve_language
from proxyhealth_api.ratelimit import rate_limit_dependency
from proxyhealth_api.settings import Settings

router = APIRouter(prefix="/v1/language-packs", tags=["language-packs"])


def _pack_response(pack: LanguagePack) -> JSONResponse:
    return JSONResponse(content=pack.model_dump(mode="json"), headers={"ETag": pack.etag})


def etag_matches(if_none_match: str | None, etag: str) -> bool:
    """RFC 9110 weak comparison over a list; accepts quoted or bare tags and ``*``."""
    if not if_none_match:
        return False
    for raw in if_none_match.split(","):
        candidate = raw.strip()
        if candidate == "*":
            return True
        if candidate.startswith("W/"):
            candidate = candidate[2:]
        if candidate.strip('"') == etag:
            return True
    return False


def _check_version(given: str | None, base: BasePack) -> None:
    if given is not None and given != base.version:
        raise ApiError(
            ErrorCode.pack_version_mismatch,
            409,
            "Client base pack hash differs from the server's.",
            details={"server_pack_version": base.version},
        )


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
    _check_version(pack_version, base)
    pack = cache.lookup(tag)
    if pack is None:
        raise ApiError(ErrorCode.not_found, 404, "No bundled or cached pack for this tag.")
    if etag_matches(request.headers.get("if-none-match"), pack.etag):
        return Response(status_code=304, headers={"ETag": pack.etag})
    return _pack_response(pack)


def _hinted(req: LanguagePackRequest, languages: LanguageTable) -> str | None:
    """The client's ``hint_tag`` counts only when it is in ``languages.yaml`` (AI_PROMPTS §7.2)."""
    hint = req.hint_tag
    if hint and languages.get(hint) is not None:
        return hint
    return None


def _cacheable(pack: LanguagePack, settings: Settings) -> bool:
    """Only real packs with coverage >= 0.9 reach ``var/langpacks`` (AI_PROMPTS §7.8, §7.10).

    Mock pseudo-localized packs are never written, so switching ``AI_PROVIDER`` never serves one;
    a thinner pack is returned to this client and regenerated on the next request.
    """
    return (
        settings.provider is not Provider.mock
        and pack.coverage >= MIN_CACHE_COVERAGE
        and not is_pseudo(pack)
    )


def _target(resolution: Resolution, languages: LanguageTable) -> Target:
    return Target(
        tag=resolution.tag,
        name_en=resolution.name_en,
        name_native=resolution.name_native,
        entry=languages.get(resolution.tag),
        direction=resolution.direction,
        script=resolution.script,
        digit_system=resolution.digit_system,
    )


@router.post(
    "",
    response_model=LanguagePack,
    responses=error_responses(400, 409, 422, 429, 503),
    dependencies=[Depends(rate_limit_dependency())],  # generation spends fast-tier quota (D-08)
)
async def create_language_pack(
    req: LanguagePackRequest,
    rid: Annotated[str, Depends(get_request_id)],
    ai: Annotated[AIService, Depends(get_ai)],
    cache: Annotated[PackCache, Depends(get_pack_cache)],
    base: Annotated[BasePack, Depends(get_packs)],
    languages: Annotated[LanguageTable, Depends(get_languages)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    _check_version(req.pack_version, base)
    hinted = _hinted(req, languages)
    if hinted is not None:
        entry = languages.get(hinted)
        resolution = Resolution(
            tag=hinted,
            source="table",
            name_en=entry.name_en if entry else req.language_query,
            name_native=entry.name_native if entry else req.language_query,
        )
    else:
        resolution = await resolve_language(req.language_query, languages, ai, request_id=rid)
    existing = cache.lookup(resolution.tag)
    if existing is not None:
        return _pack_response(existing)
    async with cache.single_flight(resolution.tag):
        cached = cache.get(resolution.tag, base.version)
        if cached is not None:
            return _pack_response(cached)
        generated = await generate_pack(_target(resolution, languages), base, ai, request_id=rid)
        if _cacheable(generated.pack, settings):
            cache.put(generated.pack)
        log_event(request_id=rid, route="langpack.generated", target_language=resolution.tag)
        return _pack_response(generated.pack)
