"""``POST /v1/troubleshoot`` (API_CONTRACT §3.6). Gated by consent + tier (D-01); body by WP2."""

from typing import Annotated

from fastapi import APIRouter, Depends

from proxyhealth_api.analysis.pipeline import PipelineDeps
from proxyhealth_api.analysis.troubleshoot_pipeline import run_troubleshoot
from proxyhealth_api.contracts.troubleshoot import TroubleshootRequest, TroubleshootResult
from proxyhealth_api.errors import error_responses
from proxyhealth_api.middleware import consent_and_tier_gate
from proxyhealth_api.ratelimit import rate_limit_dependency
from proxyhealth_api.routers.analyze import build_deps

router = APIRouter(
    prefix="/v1",
    tags=["analysis"],
    dependencies=[Depends(consent_and_tier_gate), Depends(rate_limit_dependency())],
)


@router.post(
    "/troubleshoot",
    response_model=TroubleshootResult,
    responses=error_responses(400, 403, 413, 415, 422, 428, 429, 502, 503),
)
async def troubleshoot(
    req: TroubleshootRequest, deps: Annotated[PipelineDeps, Depends(build_deps)]
) -> TroubleshootResult:
    return await run_troubleshoot(req, deps)
