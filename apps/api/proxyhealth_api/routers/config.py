"""``GET /v1/config`` (API_CONTRACT §3.2; D-01 tier matrix; D-25 pack flags).

The route function has no docstring on purpose (it would become the frozen OpenAPI description).
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from proxyhealth_api import __version__
from proxyhealth_api.ai.keypool import KeyPool
from proxyhealth_api.contracts.config import KeySlotSummary, Limits, ModelsInfo, ServerConfig
from proxyhealth_api.deps import (
    get_keypool,
    get_languages,
    get_pack_cache,
    get_packs,
    get_resources,
    get_rules,
    get_settings,
)
from proxyhealth_api.packs.base import BasePack, LanguageTable
from proxyhealth_api.packs.cache import PackCache
from proxyhealth_api.resources.loader import ResourceRepo
from proxyhealth_api.resources.rules_repo import RulesRepo
from proxyhealth_api.settings import CONTRACT_VERSION, Settings

router = APIRouter(prefix="/v1", tags=["status"])

# docs/DOCUMENT_TAXONOMY.md header (WP2 owns the doc; bump together with it).
TAXONOMY_VERSION = "2026-09-27"


@router.get("/config", response_model=ServerConfig)
async def config(
    settings: Annotated[Settings, Depends(get_settings)],
    keypool: Annotated[KeyPool | None, Depends(get_keypool)],
    packs: Annotated[BasePack, Depends(get_packs)],
    languages: Annotated[LanguageTable, Depends(get_languages)],
    cache: Annotated[PackCache, Depends(get_pack_cache)],
    resources: Annotated[ResourceRepo, Depends(get_resources)],
    rules: Annotated[RulesRepo, Depends(get_rules)],
) -> ServerConfig:
    # openai_compat sends at most OPENAI_COMPAT_MAX_IMAGES pages per call (free-ai-providers §4.8).
    image_cap = (
        settings.openai_compat_max_images
        if settings.ai_provider == "openai_compat"
        else max(settings.max_pages, settings.max_pdf_pages)
    )
    slots = (
        keypool.summary()
        if keypool is not None
        else KeySlotSummary(
            total=len(settings.gemini_keys), healthy=0, cooling=0, rpd_exhausted=0, disabled=0
        )
    )
    return ServerConfig(
        api_version=__version__,
        contract_version=CONTRACT_VERSION,
        provider=settings.provider,
        data_use_tier=settings.data_use_tier,
        models=ModelsInfo(
            fast=settings.active_model_fast,
            pro=settings.active_model_pro,
            pro_degraded_thinking=settings.model_pro_degraded_thinking,
        ),
        features=settings.features,
        limits=Limits(
            max_pages=min(settings.max_pages, image_cap),
            max_page_bytes=settings.max_page_bytes,
            max_pdf_bytes=settings.max_pdf_bytes,
            max_pdf_pages=min(settings.max_pdf_pages, image_cap),
            max_request_bytes=settings.max_request_bytes,
            max_upstream_inline_bytes=settings.max_upstream_inline_bytes,
            max_chat_history=settings.max_chat_history,
            translate_full_max_pages=settings.translate_full_max_pages,
        ),
        consent_version=settings.consent_version,
        privacy_policy_url=settings.privacy_policy_url,
        base_pack_version=packs.version,
        languages=languages.infos(cache.machine_translated),
        taxonomy_version=TAXONOMY_VERSION,
        resource_db_version=resources.version,
        rules_version=rules.version,
        key_slots=slots,
        region_notice="us_only",
        server_time=datetime.now(UTC),
        ai_model_label=settings.ai_model_label,
        ai_vendor_name=settings.ai_vendor_name,
        client_timeouts=settings.client_timeouts,
    )
