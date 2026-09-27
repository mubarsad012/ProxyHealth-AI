"""``GET /health`` (API_CONTRACT §3.1)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from proxyhealth_api import __version__
from proxyhealth_api.ai.keypool import KeyPool
from proxyhealth_api.contracts.config import HealthResponse
from proxyhealth_api.deps import get_keypool, get_resources, get_settings
from proxyhealth_api.resources.loader import ResourceRepo
from proxyhealth_api.settings import CONTRACT_VERSION, Settings

router = APIRouter(tags=["status"])


@router.get("/health", response_model=HealthResponse)
async def health(
    settings: Annotated[Settings, Depends(get_settings)],
    keypool: Annotated[KeyPool | None, Depends(get_keypool)],
    resources: Annotated[ResourceRepo, Depends(get_resources)],
) -> HealthResponse:
    keys_configured = len(settings.gemini_keys)
    keys_healthy = 0 if keypool is None else keypool.summary().healthy
    degraded = settings.ai_provider != "mock" and keys_healthy == 0
    return HealthResponse(
        status="degraded" if degraded else "ok",
        provider=settings.provider,
        version=__version__,
        contract_version=CONTRACT_VERSION,
        keys_configured=keys_configured,
        keys_healthy=keys_healthy,
        data_use_tier=settings.data_use_tier,
        resources_loaded=len(resources.all()),
    )
