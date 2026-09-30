"""Content-free feedback counters: ``POST /v1/feedback`` (API_CONTRACT §3.12; D-31)."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from proxyhealth_api.contracts.common import LanguageTag
from proxyhealth_api.contracts.enums import (
    DocumentCategory,
    DocumentType,
    FeedbackKind,
    FeedbackSurface,
    Platform,
)

# API_CONTRACT §3.12 — stable card/step id (``d1``, ``s2``, ``summary``), never text.
CardId = Annotated[str, StringConstraints(max_length=32, pattern=r"^[a-z0-9_.-]+$")]

# API_CONTRACT §3.12; DECISIONS §14 CL-026. Coarse identifier filters so free text (names,
# addresses, case numbers) is refused with 400 before the route runs. They are not the privacy
# boundary: ``feedback/store.py`` still narrows each value to a vetted-DB resource id, a
# semver-like version and a configured/Gemini-shaped model id, and stores ``other`` for anything
# else (CL-052). ``[0-9]`` rather than ``\d`` because pydantic-core's regex ``\d`` also matches
# non-ASCII digits (``١.٠.٠``); JSON Schema clients read ``[0-9]`` the same way.
ResourceId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]{1,64}$")]
AppVersion = Annotated[
    str,
    StringConstraints(max_length=40, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.]{1,20})?$"),
]
ModelId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9.-]{1,64}$")]


class FeedbackRequest(BaseModel):
    """API_CONTRACT §3.12 — "Was this clear?" signal; only the counter key is stored."""

    model_config = ConfigDict(extra="forbid")

    kind: FeedbackKind
    surface: FeedbackSurface
    language_tag: LanguageTag
    document_category: DocumentCategory | None = None
    document_type: DocumentType | None = None
    card_id: CardId | None = None
    resource_id: ResourceId | None = None
    app_version: AppVersion
    platform: Platform
    model_id: ModelId | None = None


class FeedbackResponse(BaseModel):
    """API_CONTRACT §3.12 — acknowledgement with an opaque id."""

    received: bool
    id: str
