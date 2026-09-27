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


class FeedbackRequest(BaseModel):
    """API_CONTRACT §3.12 — "Was this clear?" signal; only the counter key is stored."""

    model_config = ConfigDict(extra="forbid")

    kind: FeedbackKind
    surface: FeedbackSurface
    language_tag: LanguageTag
    document_category: DocumentCategory | None = None
    document_type: DocumentType | None = None
    card_id: CardId | None = None
    resource_id: str | None = None
    app_version: str
    platform: Platform
    model_id: str | None = None


class FeedbackResponse(BaseModel):
    """API_CONTRACT §3.12 — acknowledgement with an opaque id."""

    received: bool
    id: str
