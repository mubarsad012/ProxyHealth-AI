"""Runtime settings (ARCHITECTURE §6.1; D-01; D-04). Read from the environment and ``.env``.

Field names are the lower-case form of the env variable names (pydantic-settings matches them
case-insensitively). Secrets never appear in ``repr`` or logs (``SecretStr``).
"""

import re
import secrets
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from proxyhealth_api.contracts.config import FeatureFlags
from proxyhealth_api.contracts.enums import DataUseTier, Provider, ThinkingLevel

# apps/api/data — bundled packs, languages.yaml, fonts, resources, rules, fixtures.
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

CONTRACT_VERSION = 1

# D-04: retired families and hot-swapping aliases are refused at boot.
FORBIDDEN_MODEL_RE = re.compile(r"gemini-(1\.5|2\.0|2\.5)|-latest$")


class KeySlotConfig(BaseModel):
    """One ``GEMINI_KEYS`` entry; ``billing`` is an operator attestation (D-01)."""

    key: SecretStr
    project: str = Field(min_length=1)
    billing: bool


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="forbid", case_sensitive=False)

    env: Literal["development", "staging", "production"] = "development"
    ai_provider: Literal["mock", "gemini", "gemini_interactions"] = "mock"
    gemini_keys: list[KeySlotConfig] = Field(default_factory=list)
    allow_unpaid_keys: bool = False
    allow_unpaid_real_documents: bool = False
    model_pro: str = "gemini-3.8-flash"
    model_fast: str = "gemini-3.5-flash-lite"
    model_pro_degraded_thinking: ThinkingLevel = ThinkingLevel.medium
    allow_degraded: bool = True
    analysis_mode: Literal["auto", "single", "two_call"] = "auto"
    translate_full_max_pages: int = 4
    rpd_soft_cap_pro: int = 0
    rpd_soft_cap_fast: int = 0
    upstream_timeout_s: int = 90
    failover_deadline_s: int = 100
    max_pages: int = 12
    max_page_bytes: int = 4_194_304
    max_pdf_bytes: int = 12_582_912
    max_pdf_pages: int = 60
    max_request_bytes: int = 20_971_520
    max_upstream_inline_bytes: int = 18_874_368
    max_chat_history: int = 8
    cors_origins: str = "http://localhost:8081"
    app_token: SecretStr = SecretStr("")
    admin_token: SecretStr = SecretStr("")
    install_hash_secret: SecretStr = Field(
        default_factory=lambda: SecretStr(secrets.token_hex(16))
    )
    rate_limit_analyze_per_hour: int = 20
    rate_limit_analyze_per_day: int = 100
    rate_limit_ip_per_minute: int = 60
    consent_version: str = "2026-09-24"
    privacy_policy_url: str = "https://proxyhealth.expo.app/privacy"
    var_dir: Path = Path("./var")
    langpack_cache_ttl_days: int = 180
    mock_latency_min_ms: int = 300
    mock_latency_max_ms: int = 900
    mock_phash_max_hamming: int = 10
    log_level: str = "info"
    run_live: bool = False

    @field_validator("model_pro", "model_fast")
    @classmethod
    def _model_id_allowed(cls, value: str) -> str:
        if FORBIDDEN_MODEL_RE.search(value):
            raise ValueError(
                f"model id {value!r} is not allowed: gemini-1.5/2.0/2.5 and -latest are refused"
            )
        return value

    @model_validator(mode="after")
    def _runtime_rules(self) -> Self:
        if self.env == "production" and self.allow_unpaid_real_documents:
            raise ValueError("ALLOW_UNPAID_REAL_DOCUMENTS is refused when ENV=production (D-01)")
        if self.gemini_keys and any(not s.billing for s in self.gemini_keys):
            for model in (self.model_pro, self.model_fast):
                if "gemini-3.1-pro-preview" in model:
                    raise ValueError(f"{model!r} needs every key billed (D-04)")
        return self

    @property
    def provider(self) -> Provider:
        return Provider.mock if self.ai_provider == "mock" else Provider.gemini

    @property
    def data_use_tier(self) -> DataUseTier:
        """D-01: demo for mock; paid/unpaid/mixed from slot billing flags; none without slots."""
        if self.ai_provider == "mock":
            return DataUseTier.demo
        if not self.gemini_keys:
            return DataUseTier.none
        billed = [s.billing for s in self.gemini_keys]
        if all(billed):
            return DataUseTier.paid
        if not any(billed):
            return DataUseTier.unpaid
        return DataUseTier.mixed

    @property
    def features(self) -> FeatureFlags:
        return FeatureFlags(
            real_documents_allowed=(
                self.ai_provider == "mock"
                or self.data_use_tier is DataUseTier.paid
                or self.allow_unpaid_real_documents
            ),
            demo_samples=True,
            dynamic_language_packs=True,
            troubleshoot=True,
            chat=True,
            quicksheet_pdf=True,
            degraded_fallback=self.allow_degraded,
            hide_parts_server_masking=True,
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
