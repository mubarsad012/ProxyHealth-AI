"""``POST /v1/chat`` (API_CONTRACT §3.7). Gated by consent + tier (D-01); body by WP2."""

from typing import Annotated

from fastapi import APIRouter, Depends

from proxyhealth_api.analysis.chat_pipeline import run_chat
from proxyhealth_api.analysis.pipeline import PipelineDeps
from proxyhealth_api.contracts.chat import ChatAnswer, ChatRequest
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
    "/chat",
    response_model=ChatAnswer,
    responses=error_responses(400, 403, 422, 428, 429, 502, 503),
)
async def chat(req: ChatRequest, deps: Annotated[PipelineDeps, Depends(build_deps)]) -> ChatAnswer:
    return await run_chat(req, deps)
