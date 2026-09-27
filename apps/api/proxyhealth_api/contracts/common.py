"""Shared models of the public API contract (API_CONTRACT §2) and the ``LanguageTag`` type (§1).

Models that appear in both request and response bodies carry no defaults, so FastAPI emits a
single schema per model (no ``-Input``/``-Output`` twins) and every wire key is required.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from proxyhealth_api.contracts.enums import (
    AnalysisMode,
    DataUseTier,
    DateFormat,
    ModelQuality,
    ModelTier,
    Provider,
    ThinkingLevel,
    Tone,
)

LANGUAGE_TAG_PATTERN = r"^(x-[a-z0-9-]{1,32}|[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*)$"

# API_CONTRACT §1 — BCP-47 tag (``en``, ``zh-Hans``, ``prs``) or private-use ``x-<slug>``.
LanguageTag = Annotated[str, StringConstraints(pattern=LANGUAGE_TAG_PATTERN, max_length=40)]

# API_CONTRACT §2 — ``[x0, y0, x1, y1]`` normalized 0–1; exactly four numbers.
BBox = Annotated[list[float], Field(min_length=4, max_length=4)]

# API_CONTRACT §2 — MIME allow-list for uploaded pages (415 ``unsupported_media_type`` otherwise).
PageMimeType = Literal[
    "image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "application/pdf"
]

# API_CONTRACT §2 — rotation applied server-side, in memory.
Rotation = Literal[0, 90, 180, 270]

# API_CONTRACT §2 — normalized 0–1 coordinate.
Unit = Annotated[float, Field(ge=0.0, le=1.0)]

# API_CONTRACT §3.5 — two-letter US state code as the user set it (never inferred).
StateCode = Annotated[str, StringConstraints(min_length=2, max_length=2)]

# API_CONTRACT §3.5 — first three digits of a US ZIP code.
Zip3 = Annotated[str, StringConstraints(pattern=r"^[0-9]{3}$")]


class MaskRect(BaseModel):
    """API_CONTRACT §2 — normalized 0–1 rectangle blacked out before inference (D-19)."""

    model_config = ConfigDict(extra="forbid")

    x0: Unit
    y0: Unit
    x1: Unit
    y1: Unit

    @model_validator(mode="after")
    def _corners_ordered(self) -> Self:
        if not (self.x0 < self.x1 and self.y0 < self.y1):
            raise ValueError("MaskRect requires x0 < x1 and y0 < y1")
        return self


class PageInput(BaseModel):
    """API_CONTRACT §2 — one uploaded page (image or the single PDF)."""

    model_config = ConfigDict(extra="forbid")

    mime_type: PageMimeType
    data_base64: str = Field(min_length=1, description="Standard base64, no data-URI prefix.")
    masks: list[MaskRect] = Field(default_factory=list)
    rotation: Rotation = 0


class Preferences(BaseModel):
    """API_CONTRACT §2 — cultural/tone settings passed to prompts (never to logs)."""

    model_config = ConfigDict(extra="forbid")

    tone: Tone = Tone.plain
    calendar_notes: list[Annotated[str, StringConstraints(max_length=40)]] = Field(
        default_factory=list, max_length=5
    )
    date_format: DateFormat = DateFormat.auto


class TextBlock(BaseModel):
    """API_CONTRACT §2 — one transcribed block of the original page (also a model-output item)."""

    id: str
    page: int
    text: str
    bbox: BBox | None
    is_handwriting: bool
    is_unclear: bool


class PageText(BaseModel):
    """API_CONTRACT §2 — ``original_text`` element; width/height are the pixel size bboxes use."""

    page: int
    width: int | None
    height: int | None
    blocks: list[TextBlock]


class TranslatedPage(BaseModel):
    """API_CONTRACT §2 — ``translated_text`` element (also a model-output item)."""

    page: int
    text: str


class ModelMeta(BaseModel):
    """API_CONTRACT §2 — which model served the request and how."""

    provider: Provider
    tier: ModelTier
    model_id: str
    thinking_level: ThinkingLevel | None
    quality: ModelQuality
    analysis_mode: AnalysisMode
    data_use_tier: DataUseTier
    demo: bool
    latency_ms: int


class GeoHints(BaseModel):
    """API_CONTRACT §2 — location printed on the paper only; zip truncated to 3 digits by code."""

    state: str | None
    county: str | None
    city: str | None
    zip3: str | None
