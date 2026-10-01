"""Runtime settings (ARCHITECTURE §6.1; D-01; D-03; D-04). Read from the environment and ``.env``.

Field names are the lower-case form of the env variable names (pydantic-settings matches them
case-insensitively). Secrets never appear in ``repr`` or logs (``SecretStr``), and validation
errors never echo their input (``hide_input_in_errors``) — a malformed ``GEMINI_KEYS`` entry
must not print a key into the boot traceback.

``.env`` is read from the current directory and, as a fallback, from ``apps/api/.env`` (anchored
on this file), so repo-root commands (``uvicorn --app-dir apps/api``, ``scripts/gen_packs.py``)
see the same file; the current directory's ``.env`` wins on conflicts. An empty ``GEMINI_KEYS``
means no slots.

Boot-time rules (WP1):

* model ids: ``gemini-1.5*``, ``gemini-2.0*``, ``gemini-2.5*`` and ``*-latest`` are refused;
  ``gemini-3.1-pro-preview`` needs every slot billed (no free tier);
* ``GEMINI_KEYS`` projects must be distinct (rate limits are per project, D-01);
* ``ENV=production`` refuses unbilled slots unless ``ALLOW_UNPAID_KEYS=1`` and always refuses
  ``ALLOW_UNPAID_REAL_DOCUMENTS``;
* ``validate_runtime()`` (called in the lifespan) refuses ``AI_PROVIDER=gemini`` with zero slots
  outside ``ENV=development`` (tier ``none``).

The EEA/Switzerland/UK rule (D-03: every key ``billing:true``) is documentation only — the
server does not geolocate users; see ``.env.example``.
"""

import json
import re
import secrets
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from proxyhealth_api.contracts.config import FeatureFlags
from proxyhealth_api.contracts.enums import DataUseTier, ModelTier, Provider, ThinkingLevel

# apps/api/data — bundled packs, languages.yaml, fonts, resources, rules, fixtures.
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# apps/api/.env — read after (so overridden by) the current directory's ``.env``.
API_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

CONTRACT_VERSION = 1

# D-04: retired families and hot-swapping aliases are refused at boot.
FORBIDDEN_MODEL_RE = re.compile(r"gemini-(1\.5|2\.0|2\.5)|-latest$")

# D-04: no free tier → every slot must be billed.
PAID_ONLY_MODEL_SUBSTRINGS = ("gemini-3.1-pro-preview",)

_LOG_LEVELS = frozenset({"debug", "info", "warning", "error", "critical"})


class KeySlotConfig(BaseModel):
    """One ``GEMINI_KEYS`` entry; ``billing`` is an operator attestation (D-01)."""

    model_config = ConfigDict(hide_input_in_errors=True)

    key: SecretStr
    project: str = Field(min_length=1)
    billing: bool


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(API_ENV_FILE, ".env"),  # later files win: cwd .env overrides apps/api/.env
        extra="forbid",
        case_sensitive=False,
        hide_input_in_errors=True,  # never echo GEMINI_KEYS (or any secret) in errors
    )

    env: Literal["development", "staging", "production"] = "development"
    ai_provider: Literal["mock", "gemini", "gemini_interactions"] = "mock"
    # NoDecode: parsed by _parse_gemini_keys so "" means [] and JSON errors never echo keys.
    gemini_keys: Annotated[list[KeySlotConfig], NoDecode] = Field(default_factory=list)
    allow_unpaid_keys: bool = False
    allow_unpaid_real_documents: bool = False
    model_pro: str = "gemini-3.8-flash"
    model_fast: str = "gemini-3.5-flash-lite"
    model_pro_degraded_thinking: ThinkingLevel = ThinkingLevel.medium
    allow_degraded: bool = True
    analysis_mode: Literal["auto", "single", "two_call"] = "auto"
    translate_full_max_pages: int = Field(default=4, ge=0)
    rpd_soft_cap_pro: int = Field(default=0, ge=0)
    rpd_soft_cap_fast: int = Field(default=0, ge=0)
    upstream_timeout_s: int = Field(default=90, ge=1)
    failover_deadline_s: int = Field(default=100, ge=1)
    max_pages: int = Field(default=12, ge=1)
    max_page_bytes: int = Field(default=4_194_304, ge=1)
    max_pdf_bytes: int = Field(default=12_582_912, ge=1)
    max_pdf_pages: int = Field(default=60, ge=1)
    max_request_bytes: int = Field(default=20_971_520, ge=1)
    max_upstream_inline_bytes: int = Field(default=18_874_368, ge=1)
    max_chat_history: int = Field(default=8, ge=0)
    cors_origins: str = "http://localhost:8081"
    app_token: SecretStr = SecretStr("")
    admin_token: SecretStr = SecretStr("")
    install_hash_secret: SecretStr = Field(
        default_factory=lambda: SecretStr(secrets.token_hex(16))
    )
    rate_limit_analyze_per_hour: int = Field(default=20, ge=1)
    rate_limit_analyze_per_day: int = Field(default=100, ge=1)
    rate_limit_ip_per_minute: int = Field(default=60, ge=1)
    # D-08 "also": both IP-class buckets apply to every model-calling request, install id or not.
    rate_limit_ip_per_day: int = Field(default=1000, ge=1)
    # Proxies in front that each append to X-Forwarded-For (Cloud Run: 1; + external HTTPS load
    # balancer: 2). 0 = rate-limit the socket peer (uvicorn reachable directly, local dev).
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)
    consent_version: str = "2026-10-01"
    privacy_policy_url: str = "https://proxyhealth.expo.app/privacy"
    var_dir: Path = Path("./var")
    langpack_cache_ttl_days: int = Field(default=180, ge=1)
    mock_latency_min_ms: int = Field(default=300, ge=0)
    mock_latency_max_ms: int = Field(default=900, ge=0)
    mock_phash_max_hamming: int = Field(default=10, ge=0)
    # WP7's recording provider (CL-010): capture live model output into fixtures. Dev only.
    record_fixtures: bool = False
    log_level: str = "info"
    run_live: bool = False

    @field_validator("model_pro", "model_fast")
    @classmethod
    def _model_id_allowed(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("model id must not be empty")
        if FORBIDDEN_MODEL_RE.search(value):
            raise ValueError(
                f"model id {value!r} is not allowed: gemini-1.5/2.0/2.5 and -latest are refused"
            )
        return value

    @field_validator("log_level")
    @classmethod
    def _log_level_known(cls, value: str) -> str:
        level = value.strip().lower()
        if level not in _LOG_LEVELS:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(_LOG_LEVELS)}, got {value!r}")
        return level

    @field_validator("gemini_keys", mode="before")
    @classmethod
    def _parse_gemini_keys(cls, value: object) -> object:
        """``GEMINI_KEYS`` from the environment is a JSON list; empty/blank means no slots."""
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if not isinstance(value, str):
            return value
        if not value.strip():
            return []
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:  # message carries only the position, never the text
            raise ValueError(
                f"GEMINI_KEYS must be a JSON list of {{key, project, billing}} objects "
                f"({exc.msg}, char {exc.pos})"
            ) from None

    @field_validator("gemini_keys")
    @classmethod
    def _projects_distinct(cls, slots: list[KeySlotConfig]) -> list[KeySlotConfig]:
        projects = [s.project for s in slots]
        dupes = sorted({p for p in projects if projects.count(p) > 1})
        if dupes:
            raise ValueError(
                "GEMINI_KEYS projects must be distinct (rate limits are per project, D-01); "
                f"duplicated: {dupes}"
            )
        empty = [i for i, s in enumerate(slots) if not s.key.get_secret_value().strip()]
        if empty:
            raise ValueError(f"GEMINI_KEYS slots {empty} have an empty key")
        return slots

    @model_validator(mode="after")
    def _runtime_rules(self) -> Self:
        if self.env == "production":
            if self.allow_unpaid_real_documents:
                raise ValueError(
                    "ALLOW_UNPAID_REAL_DOCUMENTS is refused when ENV=production (D-01)"
                )
            unbilled = [s.project for s in self.gemini_keys if not s.billing]
            if unbilled and not self.allow_unpaid_keys:
                raise ValueError(
                    "ENV=production refuses billing:false key slots "
                    f"({', '.join(unbilled)}) unless ALLOW_UNPAID_KEYS=1 (D-01)"
                )
        if self.gemini_keys and any(not s.billing for s in self.gemini_keys):
            for model in (self.model_pro, self.model_fast):
                if any(sub in model for sub in PAID_ONLY_MODEL_SUBSTRINGS):
                    raise ValueError(f"{model!r} needs every key billed (D-04)")
        if self.mock_latency_min_ms > self.mock_latency_max_ms:
            raise ValueError("MOCK_LATENCY_MIN_MS must be <= MOCK_LATENCY_MAX_MS")
        return self

    def validate_runtime(self) -> None:
        """Boot-time checks that need the whole environment (ARCHITECTURE §2.1 startup)."""
        if self.ai_provider != "mock" and not self.gemini_keys and self.env != "development":
            raise ValueError(
                "AI_PROVIDER=gemini with zero GEMINI_KEYS slots (tier 'none') only boots in "
                "ENV=development (D-01)"
            )
        if self.ai_provider == "gemini_interactions":
            raise ValueError("AI_PROVIDER=gemini_interactions is LATER (D-05); use gemini or mock")

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
    def real_documents_allowed(self) -> bool:
        """D-01 gate: mock, paid, or the dev-only bypass."""
        return (
            self.ai_provider == "mock"
            or self.data_use_tier is DataUseTier.paid
            or self.allow_unpaid_real_documents
        )

    @property
    def features(self) -> FeatureFlags:
        return FeatureFlags(
            real_documents_allowed=self.real_documents_allowed,
            demo_samples=True,
            dynamic_language_packs=True,
            troubleshoot=True,
            # Every chat turn is client text (question, history, context), so the D-01 gate blocks
            # it on unpaid/mixed even for a sample paper; the flag says so up front.
            chat=self.real_documents_allowed,
            quicksheet_pdf=True,
            degraded_fallback=self.allow_degraded,
            hide_parts_server_masking=True,
        )

    @property
    def soft_caps(self) -> dict[ModelTier, int]:
        """Per-slot daily soft caps for the key pool (0 = disabled)."""
        return {ModelTier.pro: self.rpd_soft_cap_pro, ModelTier.fast: self.rpd_soft_cap_fast}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def unbilled_slot_indexes(self) -> list[int]:
        return [i for i, s in enumerate(self.gemini_keys) if not s.billing]
