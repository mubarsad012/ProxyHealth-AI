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

``AI_PROVIDER=openai_compat`` (free-ai-providers §4.2, §5.2) adds its own boot rules: ``ENV=
production`` refuses it; ``OPENAI_COMPAT_DATA_TIER=local`` needs a loopback base URL (127.0.0.0/8,
``::1`` or ``localhost``), ``OPENAI_COMPAT_MODEL_LABEL`` and no Ollama ``:cloud``/``-cloud`` model;
``attested`` boots only in ``ENV=development`` with ``OPENAI_COMPAT_VENDOR_NAME``,
``OPENAI_COMPAT_NO_TRAINING_ATTESTED=1`` and a host off ``ATTESTED_HOST_DENYLIST``; ``unpaid``
(the default) needs ``OPENAI_COMPAT_VENDOR_NAME`` and behaves like Gemini ``unpaid`` (samples only).
``FAILOVER_DEADLINE_S`` must be at least ``OPENAI_COMPAT_TIMEOUT_S + 10``; left unset, it is raised
to that value. The Gemini model-id rules never apply to ``OPENAI_COMPAT_MODEL_*``.

The EEA/Switzerland/UK rule (D-03: every key ``billing:true``) is documentation only — the
server does not geolocate users; see ``.env.example``.
"""

import ipaddress
import json
import re
import secrets
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from proxyhealth_api.contracts.config import ClientTimeouts, FeatureFlags
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

# free-ai-providers §4.2 rule 2: hosts refused for ``OPENAI_COMPAT_DATA_TIER=attested`` — they store
# data in mainland China, train on API content by default, or ban personal data (§1.5). ``*.x``
# also matches ``x`` itself; ``*.x.*`` matches any host with the label ``x``. The Gemini free tier
# must go through ``AI_PROVIDER=gemini`` with ``billing:false``.
ATTESTED_HOST_DENYLIST: tuple[str, ...] = (
    "*.cn", "*.deepseek.com", "open.bigmodel.cn", "*.moonshot.*", "*.kimi.ai",
    "*.minimax.io", "*.minimaxi.com", "*.minimax.chat", "*.stepfun.ai", "*.stepfun.com",
    "*.z.ai", "*.siliconflow.com", "*.baidubce.com",
    "integrate.api.nvidia.com", "generativelanguage.googleapis.com",
)  # fmt: skip
# D-32 verdicts enforced: Z.ai (terms forbid medical/legal-substitute use and HIPAA data),
# SiliconFlow (no commercial use) and Baidu Qianfan (PRC ID) are synthetic-samples-only.

# §1.5 "two more traps": Ollama ``:cloud`` / ``-cloud`` tags run on Ollama's servers, so the
# ``local`` sentence "runs on our server" would be false.
OLLAMA_CLOUD_TAG_RE = re.compile(r"[:-]cloud$", re.I)

# §4.2 rule 5: the failover deadline must outlast one provider call by this margin.
DEADLINE_MARGIN_S = 10
# §4.6: what the app adds on top of the server's own worst case before it gives up.
CLIENT_TIMEOUT_MARGIN_S = 15
OPENAI_COMPAT_LOOPBACK_TIMEOUT_S = 300
OPENAI_COMPAT_HOSTED_TIMEOUT_S = 90
OPENAI_COMPAT_LOOPBACK_CONCURRENCY = 1
OPENAI_COMPAT_HOSTED_CONCURRENCY = 4

OpenAICompatTier = Literal["local", "attested", "unpaid"]
OpenAICompatJsonMode = Literal["auto", "json_schema", "json_object", "prompt"]


def url_host(url: str) -> str:
    """Lower-case host of ``url`` without brackets or a trailing dot; ``""`` when unparsable."""
    try:
        host = urlsplit(url.strip()).hostname or ""
    except ValueError:
        return ""
    return host.rstrip(".").lower()


def is_loopback_host(host: str) -> bool:
    """``localhost``, ``127.0.0.0/8`` or ``::1`` (also as an IPv4-mapped address)."""
    if host == "localhost":
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return addr.ipv4_mapped.is_loopback
    return addr.is_loopback


def host_is_denylisted(host: str, patterns: tuple[str, ...] = ATTESTED_HOST_DENYLIST) -> bool:
    """True when ``host`` matches one ``ATTESTED_HOST_DENYLIST`` pattern (see its comment)."""
    host = host.rstrip(".").lower()
    labels = host.split(".")
    for pattern in patterns:
        if pattern.startswith("*.") and pattern.endswith(".*"):
            if pattern[2:-2] in labels:
                return True
        elif pattern.startswith("*."):
            apex = pattern[2:]
            if host == apex or host.endswith("." + apex):
                return True
        elif host == pattern:
            return True
    return False


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
    ai_provider: Literal["mock", "gemini", "gemini_interactions", "openai_compat"] = "mock"
    # NoDecode: parsed by _parse_gemini_keys so "" means [] and JSON errors never echo keys.
    gemini_keys: Annotated[list[KeySlotConfig], NoDecode] = Field(default_factory=list)
    allow_unpaid_keys: bool = False
    allow_unpaid_real_documents: bool = False
    model_pro: str = "gemini-3.8-flash"
    model_fast: str = "gemini-3.5-flash-lite"
    model_pro_degraded_thinking: ThinkingLevel = ThinkingLevel.medium
    allow_degraded: bool = True
    analysis_mode: Literal["auto", "single", "two_call"] = "auto"
    # AI_PROVIDER=openai_compat (free-ai-providers §4.2). Model ids come only from these two.
    openai_compat_base_url: str = "http://127.0.0.1:11434/v1"
    openai_compat_api_key: SecretStr = SecretStr("")
    openai_compat_model_pro: str = "qwen3.5:4b"
    openai_compat_model_fast: str = "qwen3.5:4b"
    openai_compat_data_tier: OpenAICompatTier = "unpaid"
    openai_compat_model_label: str = Field(default="", max_length=60)
    openai_compat_vendor_name: str = Field(default="", max_length=60)
    # §5.2: the operator's own statement that the vendor's API terms say "no training on API
    # content" (a human claim, like ``billing`` in GEMINI_KEYS). Required for ``attested``.
    openai_compat_no_training_attested: bool = False
    openai_compat_json_mode: OpenAICompatJsonMode = "auto"
    # none: every call sends reasoning_effort "none" (§4.5); mapped: ThinkingLevel → effort;
    # omit: never send the field (endpoints that reject it).
    openai_compat_reasoning: Literal["none", "mapped", "omit"] = "none"
    openai_compat_timeout_s: int | None = Field(default=None, ge=1)  # 300 loopback / 90 hosted
    openai_compat_max_output_tokens: int = Field(default=6144, ge=256)
    openai_compat_max_images: int = Field(default=12, ge=1)
    openai_compat_concurrency: int | None = Field(default=None, ge=1)  # 1 loopback / 4 hosted
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
    consent_version: str = "2026-10-04"
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

    @field_validator("openai_compat_model_pro", "openai_compat_model_fast")
    @classmethod
    def _compat_model_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("OPENAI_COMPAT_MODEL_PRO/_FAST must not be empty")
        return value

    @field_validator("openai_compat_timeout_s", "openai_compat_concurrency", mode="before")
    @classmethod
    def _blank_is_default(cls, value: object) -> object:
        """``OPENAI_COMPAT_TIMEOUT_S=`` (blank) means "use the loopback/hosted default"."""
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("openai_compat_base_url")
    @classmethod
    def _compat_base_url(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @field_validator("openai_compat_model_label", "openai_compat_vendor_name")
    @classmethod
    def _compat_label(cls, value: str) -> str:
        return " ".join(value.split())

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
        if self.ai_provider == "openai_compat":
            self._openai_compat_rules()
        return self

    def _openai_compat_rules(self) -> None:
        """free-ai-providers §4.2 boot rules 1–5 and §5.2. Messages name the host, never the URL
        (it could carry credentials) and never the key."""
        if self.env == "production":
            raise ValueError(
                "ENV=production refuses AI_PROVIDER=openai_compat until a DECISIONS entry approves "
                "a named deployment (free-ai-providers §4.2 rule 4)"
            )
        parts = urlsplit(self.openai_compat_base_url)
        host = url_host(self.openai_compat_base_url)
        if parts.scheme not in ("http", "https") or not host:
            raise ValueError("OPENAI_COMPAT_BASE_URL must be an http(s) URL with a host")
        if parts.username is not None or parts.password is not None:
            raise ValueError(
                "OPENAI_COMPAT_BASE_URL must not carry credentials; use OPENAI_COMPAT_API_KEY"
            )
        if not is_loopback_host(host) and not self.openai_compat_api_key.get_secret_value():
            raise ValueError(f"OPENAI_COMPAT_API_KEY is required for the hosted endpoint {host!r}")
        tier = self.openai_compat_data_tier
        if tier == "local":
            if not is_loopback_host(host):
                raise ValueError(
                    f"OPENAI_COMPAT_DATA_TIER=local needs a loopback OPENAI_COMPAT_BASE_URL "
                    f"(127.0.0.0/8, ::1 or localhost); host {host!r} is not (rule 1)"
                )
            if not self.openai_compat_model_label:
                raise ValueError("OPENAI_COMPAT_DATA_TIER=local needs OPENAI_COMPAT_MODEL_LABEL")
            for model in (self.openai_compat_model_pro, self.openai_compat_model_fast):
                if OLLAMA_CLOUD_TAG_RE.search(model):
                    raise ValueError(
                        f"OPENAI_COMPAT_DATA_TIER=local refuses the Ollama cloud model {model!r}: "
                        "it runs on Ollama's servers, not on this machine"
                    )
        elif tier == "attested":
            if self.env != "development":
                raise ValueError("OPENAI_COMPAT_DATA_TIER=attested only boots in ENV=development")
            if not self.openai_compat_vendor_name:
                raise ValueError(
                    "OPENAI_COMPAT_DATA_TIER=attested needs OPENAI_COMPAT_VENDOR_NAME"
                )
            if not self.openai_compat_no_training_attested:
                raise ValueError(
                    "OPENAI_COMPAT_DATA_TIER=attested needs OPENAI_COMPAT_NO_TRAINING_ATTESTED=1: "
                    "your statement that the vendor's API terms say no training on API content"
                )
            if host_is_denylisted(host):
                raise ValueError(
                    f"OPENAI_COMPAT_DATA_TIER=attested refuses host {host!r} "
                    "(ATTESTED_HOST_DENYLIST, free-ai-providers §4.2 rule 2)"
                )
        elif not self.openai_compat_vendor_name:
            raise ValueError(
                "OPENAI_COMPAT_DATA_TIER=unpaid needs OPENAI_COMPAT_VENDOR_NAME (shown in the "
                "consent copy)"
            )
        needed = self.openai_compat_timeout + DEADLINE_MARGIN_S
        if self.failover_deadline_s < needed:
            if "failover_deadline_s" in self.model_fields_set:
                raise ValueError(
                    f"FAILOVER_DEADLINE_S={self.failover_deadline_s} must be at least "
                    f"OPENAI_COMPAT_TIMEOUT_S + {DEADLINE_MARGIN_S} = {needed} (rule 5)"
                )
            self.failover_deadline_s = needed

    def validate_runtime(self) -> None:
        """Boot-time checks that need the whole environment (ARCHITECTURE §2.1 startup)."""
        gemini = self.ai_provider in ("gemini", "gemini_interactions")
        if gemini and not self.gemini_keys and self.env != "development":
            raise ValueError(
                "AI_PROVIDER=gemini with zero GEMINI_KEYS slots (tier 'none') only boots in "
                "ENV=development (D-01)"
            )
        if self.ai_provider == "gemini_interactions":
            raise ValueError("AI_PROVIDER=gemini_interactions is LATER (D-05); use gemini or mock")

    @property
    def provider(self) -> Provider:
        if self.ai_provider == "mock":
            return Provider.mock
        if self.ai_provider == "openai_compat":
            return Provider.openai_compat
        return Provider.gemini

    @property
    def data_use_tier(self) -> DataUseTier:
        """D-01: demo for mock; paid/unpaid/mixed from slot billing flags; none without slots.
        ``openai_compat``: the configured ``OPENAI_COMPAT_DATA_TIER`` (§4.2 rule 7)."""
        if self.ai_provider == "mock":
            return DataUseTier.demo
        if self.ai_provider == "openai_compat":
            return DataUseTier(self.openai_compat_data_tier)
        if not self.gemini_keys:
            return DataUseTier.none
        billed = [s.billing for s in self.gemini_keys]
        if all(billed):
            return DataUseTier.paid
        if not any(billed):
            return DataUseTier.unpaid
        return DataUseTier.mixed

    @property
    def samples_only(self) -> bool:
        """The tier gate's predicate (D-01; §5.2): real papers and typed text are refused unless
        ``ALLOW_UNPAID_REAL_DOCUMENTS``. ``attested`` is samples-only outside development (it
        cannot boot there; this keeps the gate closed even so)."""
        tier = self.data_use_tier
        if tier is DataUseTier.attested:
            return self.env != "development"
        return tier in (DataUseTier.unpaid, DataUseTier.mixed)

    @property
    def real_documents_allowed(self) -> bool:
        """D-01 gate: mock, paid, local, attested in development, or the dev-only bypass."""
        tier = self.data_use_tier
        return (
            self.ai_provider == "mock"
            or tier in (DataUseTier.paid, DataUseTier.local)
            or (tier is DataUseTier.attested and self.env == "development")
            or self.allow_unpaid_real_documents
        )

    # ---------------------------------------------------------------- openai_compat helpers

    @property
    def openai_compat_host(self) -> str:
        return url_host(self.openai_compat_base_url)

    @property
    def openai_compat_is_loopback(self) -> bool:
        return is_loopback_host(self.openai_compat_host)

    @property
    def openai_compat_timeout(self) -> int:
        """``OPENAI_COMPAT_TIMEOUT_S``, else 300 s on a loopback host and 90 s otherwise."""
        if self.openai_compat_timeout_s is not None:
            return self.openai_compat_timeout_s
        if self.openai_compat_is_loopback:
            return OPENAI_COMPAT_LOOPBACK_TIMEOUT_S
        return OPENAI_COMPAT_HOSTED_TIMEOUT_S

    @property
    def openai_compat_concurrency_limit(self) -> int:
        """``OPENAI_COMPAT_CONCURRENCY``, else 1 on a loopback host (16 GB RAM) and 4 otherwise."""
        if self.openai_compat_concurrency is not None:
            return self.openai_compat_concurrency
        if self.openai_compat_is_loopback:
            return OPENAI_COMPAT_LOOPBACK_CONCURRENCY
        return OPENAI_COMPAT_HOSTED_CONCURRENCY

    @property
    def active_model_pro(self) -> str:
        """The pro model of the active provider (§4.2 rule 6; ``route()`` and the logs use it)."""
        if self.ai_provider == "openai_compat":
            return self.openai_compat_model_pro
        return self.model_pro

    @property
    def active_model_fast(self) -> str:
        if self.ai_provider == "openai_compat":
            return self.openai_compat_model_fast
        return self.model_fast

    @property
    def degraded_enabled(self) -> bool:
        """D-07 degraded path. Off for ``openai_compat`` (§4.5): locally PRO equals FAST, and a
        hosted FAST model may be text-only."""
        return self.allow_degraded and self.ai_provider != "openai_compat"

    @property
    def ai_model_label(self) -> str | None:
        """``{model}`` in the tier's consent copy (§5.3); ``None`` for the mock."""
        if self.ai_provider == "openai_compat":
            return self.openai_compat_model_label or None
        if self.ai_provider == "mock":
            return None
        return "Gemini"

    @property
    def ai_vendor_name(self) -> str | None:
        """``{vendor}`` in the tier's consent copy (§5.3); ``None`` for the mock."""
        if self.ai_provider == "openai_compat":
            return self.openai_compat_vendor_name or None
        if self.ai_provider == "mock":
            return None
        return "Google"

    @property
    def client_timeouts(self) -> ClientTimeouts:
        """§4.6: the app's waits. The fixed defaults, except on ``openai_compat``, where every
        model-calling request may take ``FAILOVER_DEADLINE_S`` (the last call starts just before
        it) + ``OPENAI_COMPAT_TIMEOUT_S`` (that call) + a margin."""
        base = ClientTimeouts()
        if self.ai_provider != "openai_compat":
            return base
        budget = self.failover_deadline_s + self.openai_compat_timeout + CLIENT_TIMEOUT_MARGIN_S
        return ClientTimeouts(
            analyze_s=max(base.analyze_s, budget),
            troubleshoot_s=max(base.troubleshoot_s, budget),
            language_pack_s=max(base.language_pack_s, budget),
            chat_s=max(base.chat_s, budget),
            default_s=base.default_s,
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
            degraded_fallback=self.degraded_enabled,
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
