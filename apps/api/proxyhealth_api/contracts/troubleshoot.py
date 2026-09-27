"""Screenshot troubleshooting / scam check: ``POST /v1/troubleshoot`` (API_CONTRACT §3.6)."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from proxyhealth_api.contracts.analysis import RedFlag, Safety
from proxyhealth_api.contracts.common import LanguageTag, ModelMeta, PageInput
from proxyhealth_api.contracts.enums import (
    Confidence,
    DisclaimerKind,
    Platform,
    PortalHint,
    ResourceTag,
    ScamRisk,
    TroubleshootMode,
    WarningCode,
)


class TroubleshootRequest(BaseModel):
    """API_CONTRACT §3.6 — exactly one screenshot image (never a PDF) plus the user's goal."""

    model_config = ConfigDict(extra="forbid")

    screenshot: PageInput
    user_goal: str | None = Field(default=None, max_length=300)
    mode: TroubleshootMode = TroubleshootMode.portal
    portal_hint: PortalHint | None = None
    target_language: LanguageTag
    demo_sample_id: str | None = None
    client_platform: Platform

    @field_validator("screenshot")
    @classmethod
    def _image_only(cls, value: PageInput) -> PageInput:
        if value.mime_type == "application/pdf":
            raise ValueError("screenshot must be an image, not a PDF")
        return value


class TroubleshootStep(BaseModel):
    """API_CONTRACT §3.6 — one tap naming the button exactly as written (also a model-output item).
    """

    order: int
    text: str
    ui_target_as_written: str | None


class TroubleshootResult(BaseModel):
    """API_CONTRACT §3.6 — the ``POST /v1/troubleshoot`` response."""

    request_id: str
    screen_summary: str
    error_text_quoted: str | None
    error_meaning: str
    steps: list[TroubleshootStep]
    cautions: list[str]
    asks_for_credentials_or_payment: bool
    is_likely_scam: bool
    scam_risk: ScamRisk
    scam_reasons: list[str]
    needs_human_help: bool
    red_flags: list[RedFlag]
    resource_tags: list[ResourceTag]
    screen_text: list[str]
    confidence: Confidence
    safety: Safety
    disclaimer_kind: DisclaimerKind
    warnings: list[WarningCode]
    model_meta: ModelMeta
