"""Model-output schemas Gemini returns through ``response_schema`` (API_CONTRACT §4; AI_PROMPTS §4).

Never exposed in OpenAPI responses. Every class obeys D-06 (depth ≤ 3, no dict/Any/recursion,
unions only ``X | None``, enums ≤ 64 values, ``bbox`` = ``list[float]`` len 4) and is checked by
``ai/schema_guard.assert_subset_safe`` at import. Shared value objects (``TextBlock``,
``TranslatedPage``, ``GlossaryTerm``, ``TroubleshootStep``) are the contract classes reused
unchanged. ``max_length`` caps follow AI_PROMPTS §4 (the pipeline also truncates defensively).
"""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from proxyhealth_api.ai.schema_guard import assert_subset_safe
from proxyhealth_api.contracts.analysis import GlossaryTerm
from proxyhealth_api.contracts.common import TextBlock, TranslatedPage
from proxyhealth_api.contracts.enums import (
    Confidence,
    DemandKind,
    DigitSystem,
    Direction,
    DocumentCategory,
    DocumentType,
    Legibility,
    PlanStepKind,
    RedFlagKind,
    ReferTo,
    RefusalKind,
    SenderKind,
)
from proxyhealth_api.contracts.troubleshoot import TroubleshootStep

Str12 = Annotated[str, StringConstraints(max_length=12)]
Str80 = Annotated[str, StringConstraints(max_length=80)]
Str120 = Annotated[str, StringConstraints(max_length=120)]
Str140 = Annotated[str, StringConstraints(max_length=140)]
Str160 = Annotated[str, StringConstraints(max_length=160)]
Str200 = Annotated[str, StringConstraints(max_length=200)]
Str220 = Annotated[str, StringConstraints(max_length=220)]
Str300 = Annotated[str, StringConstraints(max_length=300)]
Str400 = Annotated[str, StringConstraints(max_length=400)]
Str600 = Annotated[str, StringConstraints(max_length=600)]


class KeyValue(BaseModel):
    """API_CONTRACT §4 — one translated UI string (``key`` copied exactly from the input)."""

    key: str
    value: str


class DemandOut(BaseModel):
    """API_CONTRACT §4 / AI_PROMPTS §4.3 — one fact the paper asks for; nothing computed."""

    id: str
    kind: DemandKind
    text: Str200
    value_verbatim: Str120
    source_quote: Str300
    span_ids: list[str] = Field(max_length=3)
    page: int
    date_text: str | None
    time_text: str | None
    relative_rule_text: str | None
    anchor_span_id: str | None
    amount_text: str | None
    currency: str | None
    documents: list[str]
    role: str | None
    confidence: Confidence
    ambiguity_note: Str160 | None


class PlanStepOut(BaseModel):
    """API_CONTRACT §4 / AI_PROMPTS §4.3 — one ordered, gentle imperative step."""

    id: str
    text: Str220
    kind: PlanStepKind
    resource_tags: list[str]
    span_ids: list[str]
    demand_id: str | None


class RedFlagOut(BaseModel):
    """API_CONTRACT §4 / AI_PROMPTS §4.3 — model-found red flag with its quote."""

    kind: RedFlagKind
    text: Str220
    source_quote: str | None
    span_ids: list[str]
    page: int | None


class _ExplainFields(BaseModel):
    """AI_PROMPTS §4.2/§4.4 — explaining fields shared by the analysis schemas."""

    document_type: DocumentType
    category: DocumentCategory
    document_type_confidence: Confidence
    sender_as_written: Str200 | None
    sender_kind: SenderKind
    detected_language: Str12
    translated_pages: list[TranslatedPage]
    summary_title: Str80
    summary_body: Str400
    summary_body_en: Str400
    summary_span_ids: list[str] = Field(max_length=6)
    demands: list[DemandOut]
    plan_steps: list[PlanStepOut]
    glossary: list[GlossaryTerm] = Field(max_length=8)
    red_flags: list[RedFlagOut]
    questions_to_ask: list[Str140] = Field(max_length=5)
    clerk_need_en: Str200
    emergency_terms_found: list[str] = Field(max_length=10)
    is_likely_scam: bool
    scam_signals: list[str]
    resource_tags: list[str] = Field(max_length=6)
    institutions_as_written: list[str] = Field(max_length=10)
    form_numbers: list[str] = Field(max_length=10)
    geo_state: str | None
    geo_county: str | None
    geo_city: str | None
    geo_zip: str | None


class AnalysisModelOut(_ExplainFields):
    """API_CONTRACT §4 — task ``analyze_single``: seeing + explaining in one call."""

    legibility: Legibility
    readable_reason: Str120 | None
    blocks: list[TextBlock]


class TranscriptOut(BaseModel):
    """API_CONTRACT §4 — two-call mode, call 1 (task ``transcribe``): the four seeing fields."""

    blocks: list[TextBlock]
    detected_language: Str12
    legibility: Legibility
    readable_reason: Str120 | None


class ExplainOut(_ExplainFields):
    """API_CONTRACT §4 — two-call mode, call 2 (task ``explain``); no seeing fields."""


class TroubleshootModelOut(BaseModel):
    """API_CONTRACT §4 / AI_PROMPTS §4.5 — task ``troubleshoot``."""

    screen_summary: Str300
    screen_text: list[Str160] = Field(max_length=40)
    error_text_quoted: str | None
    error_meaning: Str300
    steps: list[TroubleshootStep] = Field(max_length=6)
    cautions: list[str] = Field(max_length=4)
    asks_for_credentials_or_payment: bool
    is_likely_scam: bool
    scam_signals: list[str]
    needs_human_help: bool
    red_flags: list[RedFlagOut]
    resource_tags: list[str]
    confidence: Confidence


class ChatModelOut(BaseModel):
    """API_CONTRACT §4 / AI_PROMPTS §4.6 — task ``chat``."""

    answer: Str600
    grounded_span_ids: list[str]
    not_in_document: bool
    refusal_kind: RefusalKind
    refer_to_professional: ReferTo
    distress_acknowledged: bool
    suggested_questions: list[Str120] = Field(max_length=3)
    resource_tags: list[str]


class LanguagePackModelOut(BaseModel):
    """API_CONTRACT §4 / AI_PROMPTS §4.7 — language-pack chunk as a list of pairs."""

    language_tag: str
    language_name_native: str
    language_name_en: str
    direction: Direction
    script: str | None
    digit_system: DigitSystem
    strings: list[KeyValue]
    fallback_keys: list[str]
    confidence: Confidence
    notes_for_reviewer: Str400 | None


class LanguageResolveOut(BaseModel):
    """API_CONTRACT §4 / AI_PROMPTS §4.8 — task ``resolve_language`` (unknown typed names only)."""

    language_tag: str | None
    language_name_en: str
    language_name_native: str | None
    script: str | None
    direction: Direction
    digit_system: DigitSystem
    confidence: Confidence


class RewriteOut(BaseModel):
    """API_CONTRACT §4 / AI_PROMPTS §4.9 — task ``phrasing_rewrite``: one hedged sentence."""

    sentence: Str400


class TaggingModelOut(BaseModel):
    """API_CONTRACT §4 / AI_PROMPTS §4.9 — task ``tag``."""

    tags: list[str]
    geo_state: str | None
    geo_county: str | None
    geo_city: str | None
    geo_zip: str | None
    institutions_as_written: list[str]
    emergency: bool


# Top-level schemas passed to ``response_schema``; nested items are checked transitively.
MODEL_OUT_CLASSES: tuple[type[BaseModel], ...] = (
    AnalysisModelOut,
    TranscriptOut,
    ExplainOut,
    TroubleshootModelOut,
    ChatModelOut,
    LanguagePackModelOut,
    LanguageResolveOut,
    RewriteOut,
    TaggingModelOut,
)

for _cls in MODEL_OUT_CLASSES:
    assert_subset_safe(_cls)

__all__ = [
    "MODEL_OUT_CLASSES",
    "AnalysisModelOut",
    "ChatModelOut",
    "DemandOut",
    "ExplainOut",
    "KeyValue",
    "LanguagePackModelOut",
    "LanguageResolveOut",
    "PlanStepOut",
    "RedFlagOut",
    "RewriteOut",
    "TaggingModelOut",
    "TranscriptOut",
    "TroubleshootModelOut",
]
