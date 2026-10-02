"""Status models: ``GET /health`` (API_CONTRACT §3.1) and ``GET /v1/config`` (§3.2)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from proxyhealth_api.contracts.common import LanguageTag
from proxyhealth_api.contracts.enums import (
    DataUseTier,
    DigitSystem,
    Direction,
    PackTier,
    Provider,
    ThinkingLevel,
)


class HealthResponse(BaseModel):
    """API_CONTRACT §3.1 — liveness plus a content-free provider summary."""

    status: Literal["ok", "degraded"]
    provider: Provider
    version: str
    contract_version: int
    keys_configured: int
    keys_healthy: int
    data_use_tier: DataUseTier
    resources_loaded: int


class ModelsInfo(BaseModel):
    """API_CONTRACT §3.2 — env-resolved model IDs (``MODEL_FAST`` / ``MODEL_PRO``)."""

    fast: str
    pro: str
    pro_degraded_thinking: ThinkingLevel


class FeatureFlags(BaseModel):
    """API_CONTRACT §3.2 — capabilities the client uses for honest banners."""

    real_documents_allowed: bool
    demo_samples: bool
    dynamic_language_packs: bool
    troubleshoot: bool
    chat: bool
    quicksheet_pdf: bool
    degraded_fallback: bool
    hide_parts_server_masking: bool


class Limits(BaseModel):
    """API_CONTRACT §3.2 — request limits; defaults are the contract's documented values."""

    max_pages: int = 12
    max_page_bytes: int = 4_194_304
    max_pdf_bytes: int = 12_582_912
    max_pdf_pages: int = 60
    max_request_bytes: int = 20_971_520
    max_upstream_inline_bytes: int = 18_874_368
    max_chat_history: int = 8
    max_question_chars: int = 1000
    max_user_goal_chars: int = 300
    translate_full_max_pages: int = 4


class ClientTimeouts(BaseModel):
    """How long the app waits for each kind of request before it gives up, in seconds.

    The defaults are the app's fixed limits from before ``AI_PROVIDER=openai_compat``; a local
    model is slower, so the server then sends limits that cover its own budget
    (``FAILOVER_DEADLINE_S`` + ``OPENAI_COMPAT_TIMEOUT_S`` + a margin; free-ai-providers §4.6).
    """

    analyze_s: int = Field(default=120, ge=1)
    troubleshoot_s: int = Field(default=60, ge=1)
    language_pack_s: int = Field(default=60, ge=1)
    chat_s: int = Field(default=30, ge=1)
    default_s: int = Field(default=30, ge=1)


class KeySlotSummary(BaseModel):
    """API_CONTRACT §3.2 — key-pool counts only (no key material)."""

    total: int
    healthy: int
    cooling: int
    rpd_exhausted: int
    disabled: int


class LanguageInfo(BaseModel):
    """API_CONTRACT §3.2 — one bundled/known language from ``data/languages.yaml``."""

    tag: LanguageTag
    name_native: str
    name_en: str
    direction: Direction
    script: str | None = None
    digit_system: DigitSystem
    font_hint: str | None = None
    tier: PackTier
    bundled: bool
    machine_translated: bool
    tts_tag: str | None = None
    tts_fallback_tag: str | None = None


class ServerConfig(BaseModel):
    """API_CONTRACT §3.2 — capabilities and status the client reads at boot."""

    api_version: str
    contract_version: int
    provider: Provider
    data_use_tier: DataUseTier
    models: ModelsInfo
    features: FeatureFlags
    limits: Limits
    consent_version: str
    privacy_policy_url: str
    base_pack_version: str
    languages: list[LanguageInfo] = Field(default_factory=list)
    taxonomy_version: str
    resource_db_version: str
    rules_version: str
    key_slots: KeySlotSummary
    region_notice: Literal["us_only"] = "us_only"
    server_time: datetime
    # free-ai-providers §5.2/§5.3: ``{model}`` / ``{vendor}`` in the tier's consent copy.
    ai_model_label: str | None = Field(default=None, max_length=60)
    ai_vendor_name: str | None = Field(default=None, max_length=60)
    client_timeouts: ClientTimeouts = Field(default_factory=ClientTimeouts)
