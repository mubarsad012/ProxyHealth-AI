"""``GET /v1/config`` (API_CONTRACT §3.2)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from proxyhealth_api import __version__
from proxyhealth_api.ai.keypool import KeyPool
from proxyhealth_api.contracts.config import KeySlotSummary, Limits, ModelsInfo, ServerConfig
from proxyhealth_api.deps import (
    get_keypool,
    get_languages,
    get_packs,
    get_resources,
    get_rules,
    get_settings,
)
from proxyhealth_api.packs.base import BasePack, LanguageTable
from proxyhealth_api.resources.loader import ResourceRepo
from proxyhealth_api.resources.rules_repo import RulesRepo
from proxyhealth_api.settings import CONTRACT_VERSION, Settings

router = APIRouter(prefix="/v1", tags=["status"])

TAXONOMY_VERSION = "0"  # WP2 owns docs/DOCUMENT_TAXONOMY.md and bumps this


@router.get("/config", response_model=ServerConfig)
async def config(
    settings: Annotated[Settings, Depends(get_settings)],
    keypool: Annotated[KeyPool | None, Depends(get_keypool)],
    packs: Annotated[BasePack, Depends(get_packs)],
    languages: Annotated[LanguageTable, Depends(get_languages)],
    resources: Annotated[ResourceRepo, Depends(get_resources)],
    rules: Annotated[RulesRepo, Depends(get_rules)],
) -> ServerConfig:
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
            fast=settings.model_fast,
            pro=settings.model_pro,
            pro_degraded_thinking=settings.model_pro_degraded_thinking,
        ),
        features=settings.features,
        limits=Limits(
            max_pages=settings.max_pages,
            max_page_bytes=settings.max_page_bytes,
            max_pdf_bytes=settings.max_pdf_bytes,
            max_pdf_pages=settings.max_pdf_pages,
            max_request_bytes=settings.max_request_bytes,
            max_upstream_inline_bytes=settings.max_upstream_inline_bytes,
            max_chat_history=settings.max_chat_history,
            translate_full_max_pages=settings.translate_full_max_pages,
        ),
        consent_version=settings.consent_version,
        privacy_policy_url=settings.privacy_policy_url,
        base_pack_version=packs.version,
        languages=languages.infos(),
        taxonomy_version=TAXONOMY_VERSION,
        resource_db_version=resources.version,
        rules_version=rules.version,
        key_slots=slots,
        region_notice="us_only",
        server_time=datetime.now(UTC),
    )
