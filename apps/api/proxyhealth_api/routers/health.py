"""``GET /health`` (API_CONTRACT §3.1). No docstring on the route: it would enter openapi.json.

``keys_healthy`` counts slots healthy for the pro tier; ``status`` is ``degraded`` when the
provider is gemini and no slot is healthy for either tier (or no pool could be built).
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from proxyhealth_api import __version__
from proxyhealth_api.ai.keypool import KeyPool
from proxyhealth_api.contracts.config import HealthResponse
from proxyhealth_api.contracts.enums import ModelTier
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
    if keypool is None:
        keys_healthy, any_healthy = 0, False
    else:
        keys_healthy = keypool.counts(ModelTier.pro)["healthy"]
        any_healthy = any(keypool.counts(tier)["healthy"] > 0 for tier in ModelTier)
    degraded = settings.ai_provider != "mock" and not any_healthy
    return HealthResponse(
        status="degraded" if degraded else "ok",
        provider=settings.provider,
        version=__version__,
        contract_version=CONTRACT_VERSION,
        keys_configured=keys_configured,
        keys_healthy=keys_healthy,
        data_use_tier=settings.data_use_tier,
        resources_loaded=resources.count(),  # CL-018: YAML entry count
    )
