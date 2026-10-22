"""``POST /v1/analyze`` (API_CONTRACT §3.5). Gated by consent + tier (D-01); body by WP2."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from proxyhealth_api.ai.failover import AIService
from proxyhealth_api.analysis.pipeline import PipelineDeps, run_analysis
from proxyhealth_api.contracts.analysis import AnalysisResult, AnalyzeRequest
from proxyhealth_api.demo.fixtures import FixtureStore
from proxyhealth_api.deps import (
    get_ai,
    get_fixtures,
    get_languages,
    get_pack_cache,
    get_request_id,
    get_resources,
    get_rules,
    get_settings,
)
from proxyhealth_api.errors import error_responses
from proxyhealth_api.middleware import consent_and_tier_gate
from proxyhealth_api.packs.base import LanguageTable
from proxyhealth_api.packs.cache import PackCache
from proxyhealth_api.ratelimit import rate_limit_dependency
from proxyhealth_api.resources.loader import ResourceRepo
from proxyhealth_api.resources.rules_repo import RulesRepo
from proxyhealth_api.routers._cancel import run_until_disconnect
from proxyhealth_api.settings import Settings

router = APIRouter(
    prefix="/v1",
    tags=["analysis"],
    dependencies=[Depends(consent_and_tier_gate), Depends(rate_limit_dependency())],
)


def build_deps(
    settings: Annotated[Settings, Depends(get_settings)],
    ai: Annotated[AIService, Depends(get_ai)],
    resources: Annotated[ResourceRepo, Depends(get_resources)],
    rules: Annotated[RulesRepo, Depends(get_rules)],
    fixtures: Annotated[FixtureStore, Depends(get_fixtures)],
    request_id: Annotated[str, Depends(get_request_id)],
    packs: Annotated[PackCache, Depends(get_pack_cache)],
    languages: Annotated[LanguageTable, Depends(get_languages)],
) -> PipelineDeps:
    """One request's ``PipelineDeps`` from ``app.state`` (shared by the three gated routers)."""
    return PipelineDeps(
        settings=settings,
        ai=ai,
        resources=resources,
        rules=rules,
        fixtures=fixtures,
        request_id=request_id,
        data_use_tier=settings.data_use_tier,
        clock=lambda: datetime.now(UTC),
        packs=packs,
        languages=languages,
    )


@router.post(
    "/analyze",
    response_model=AnalysisResult,
    responses=error_responses(400, 403, 413, 415, 422, 428, 429, 502, 503),
)
async def analyze(
    req: AnalyzeRequest, request: Request, deps: Annotated[PipelineDeps, Depends(build_deps)]
) -> AnalysisResult | Response:
    return await run_until_disconnect(
        request, run_analysis(req, deps), deps.settings, request_id=deps.request_id
    )
