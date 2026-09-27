"""Language packs: ``GET /v1/language-packs/{tag}`` (API_CONTRACT §3.3), ``POST`` (§3.4)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from proxyhealth_api.contracts.common import LanguageTag
from proxyhealth_api.contracts.enums import (
    Confidence,
    DigitSystem,
    Direction,
    PackSource,
    PackTier,
)


class LanguagePackRequest(BaseModel):
    """API_CONTRACT §3.4 — resolve a typed language and generate/fetch its pack."""

    model_config = ConfigDict(extra="forbid")

    language_query: str = Field(min_length=1, max_length=60)
    pack_version: str
    hint_tag: LanguageTag | None = None


class LanguagePack(BaseModel):
    """API_CONTRACT §3.3 — every UI string for one language plus pack provenance."""

    language_tag: LanguageTag
    language_name_native: str
    language_name_en: str
    direction: Direction
    script: str | None = None
    digit_system: DigitSystem
    font_hint: str | None = None
    tier: PackTier
    source: PackSource
    pack_version: str
    etag: str
    strings: dict[str, str]
    fallback_keys: list[str] = Field(default_factory=list)
    coverage: float = Field(ge=0.0, le=1.0)
    machine_translated: bool
    reviewed_by: str | None = None
    confidence: Confidence
    generated_at: datetime
    tts_tag: str | None = None
    tts_fallback_tag: str | None = None
