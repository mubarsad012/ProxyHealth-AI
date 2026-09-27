"""Document analysis: ``POST /v1/analyze`` request and result (API_CONTRACT §3.5)."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from proxyhealth_api.contracts.common import (
    GeoHints,
    LanguageTag,
    ModelMeta,
    PageInput,
    PageText,
    Preferences,
    StateCode,
    TranslatedPage,
    Zip3,
)
from proxyhealth_api.contracts.enums import (
    Confidence,
    DateKind,
    DemandKind,
    Direction,
    DisclaimerKind,
    DocumentCategory,
    DocumentType,
    Legibility,
    PlanStepKind,
    Platform,
    RedFlagKind,
    ResourceTag,
    RuleVerification,
    ScamRisk,
    SenderKind,
    Severity,
    UrgencyLevel,
    WarningCode,
)
from proxyhealth_api.contracts.resources import ResourceMatch

MAX_PAGES = 12


class AnalyzeRequest(BaseModel):
    """API_CONTRACT §3.5 — 1–12 images or one PDF; ``pages`` may be ``[]`` only for a demo."""

    model_config = ConfigDict(extra="forbid")

    pages: list[PageInput] = Field(default_factory=list, max_length=MAX_PAGES)
    target_language: LanguageTag
    ui_direction: Direction = Direction.ltr
    state: StateCode | None = None
    zip3: Zip3 | None = None
    document_hint: DocumentType | None = None
    preferences: Preferences = Field(default_factory=Preferences)
    demo_sample_id: str | None = None
    include_page_thumbnails: bool = False
    masks_applied_client_side: bool = False
    hide_id_numbers: bool = False
    client_platform: Platform
    analysis_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _pages_or_demo(self) -> Self:
        if not self.pages and not self.demo_sample_id:
            raise ValueError("pages may be empty only when demo_sample_id is set")
        return self


class Quality(BaseModel):
    """API_CONTRACT §3.5 — capture quality; ``readable=false`` is a 200, not an error."""

    readable: bool
    legibility: Legibility
    reason: str | None
    pages_received: int
    pages_unreadable: list[int]


class Urgency(BaseModel):
    """API_CONTRACT §3.5 — code-computed urgency (D-12)."""

    level: UrgencyLevel
    headline_key: str
    headline_params: dict[str, str]
    driving_demand_id: str | None
    nearest_date_iso: str | None
    days_until: int | None
    past_date: bool
    floor_applied: bool
    verify_resource_id: str | None


class SummaryCard(BaseModel):
    """API_CONTRACT §3.5 — Card 1; ``body`` ≤ 3 sentences at 4th-grade level."""

    title: str
    body: str
    body_en: str
    span_ids: list[str]


class DateInfo(BaseModel):
    """API_CONTRACT §3.5 — resolved date of a demand (``value_iso`` is ``YYYY-MM-DD``)."""

    value_iso: str | None
    time_text: str | None
    kind: DateKind
    formula: str | None
    anchor_quote: str | None
    anchor_demand_id: str | None
    rule_id: str | None
    rule_source_url: str | None
    rule_verification: RuleVerification | None
    localized_line: str | None


class AmountInfo(BaseModel):
    """API_CONTRACT §3.5 — money amount in minor units with ISO 4217 currency."""

    amount_minor: int
    currency: str


class Demand(BaseModel):
    """API_CONTRACT §3.5 — Card 2 item; ``verified`` is true in ``demands``, false otherwise."""

    id: str
    kind: DemandKind
    text: str
    value_verbatim: str
    source_quote: str
    span_ids: list[str]
    page: int
    confidence: Confidence
    verified: bool
    verification_note: str | None
    date: DateInfo | None
    amount: AmountInfo | None
    documents: list[str]
    role: str | None
    reminder_eligible: bool
    ambiguity_note: str | None


class PlanStep(BaseModel):
    """API_CONTRACT §3.5 — Card 3 step."""

    id: str
    text: str
    kind: PlanStepKind
    resource_tags: list[ResourceTag]
    span_ids: list[str]
    demand_id: str | None


class RedFlag(BaseModel):
    """API_CONTRACT §3.5 — model flag (verified) or code flag (``fixed_copy_key``)."""

    kind: RedFlagKind
    text: str
    source_quote: str | None
    span_ids: list[str]
    page: int | None
    severity: Severity
    fixed_copy_key: str | None
    verified: bool


class GlossaryTerm(BaseModel):
    """API_CONTRACT §3.5 — one explained term (also a model-output item)."""

    term_as_written: str
    explanation: str


class Entities(BaseModel):
    """API_CONTRACT §3.5 — names exactly as printed; no invented organizations."""

    institutions_as_written: list[str]
    form_numbers: list[str]
    geo: GeoHints
    has_case_number: bool
    has_receipt_number: bool


class ClerkMessage(BaseModel):
    """API_CONTRACT §3.5 — full-screen clerk card text (D-18)."""

    english: str
    translated: str
    need_line_source: Literal["ai", "template"]
    appended_line_keys: list[str]


class VerificationSummary(BaseModel):
    """API_CONTRACT §3.5 — counts from the output safety pipeline."""

    facts_checked: int
    facts_rejected: int
    contacts_stripped: int
    phrasing_rewrites: int
    injection_masked: bool
    verifier_version: str


class Safety(BaseModel):
    """API_CONTRACT §3.5 — emergency lexicon and credential-guard results (shared by §3.6, §3.7)."""

    emergency: bool
    emergency_kinds: list[str]
    credential_or_payment_request: bool


class PageThumbnail(BaseModel):
    """API_CONTRACT §3.5 — PDF page rasterized in memory (≤ 1200 px longest edge)."""

    page: int
    mime_type: str
    data_base64: str
    width: int
    height: int


class AnalysisResult(BaseModel):
    """API_CONTRACT §3.5 — the full ``POST /v1/analyze`` response (``schema_version`` 1)."""

    schema_version: int = 1
    request_id: str
    analysis_id: str
    created_at: datetime
    quality: Quality
    category: DocumentCategory
    document_type: DocumentType
    document_type_confidence: Confidence
    sender_as_written: str | None
    sender_kind: SenderKind
    detected_language: LanguageTag
    target_language: LanguageTag
    translation_confidence: Confidence
    is_likely_scam: bool
    scam_risk: ScamRisk
    scam_reasons: list[str]
    urgency: Urgency
    summary: SummaryCard
    demands: list[Demand]
    unverified: list[Demand]
    plan_steps: list[PlanStep]
    red_flags: list[RedFlag]
    glossary: list[GlossaryTerm]
    entities: Entities
    clerk_message: ClerkMessage
    resource_tags: list[ResourceTag]
    resource_preview: list[ResourceMatch]
    original_text: list[PageText]
    translated_text: list[TranslatedPage]
    questions_to_ask: list[str]
    verification: VerificationSummary
    safety: Safety
    disclaimer_kind: DisclaimerKind
    disclaimers: list[DisclaimerKind]
    warnings: list[WarningCode]
    model_meta: ModelMeta
    page_thumbnails: list[PageThumbnail] | None
