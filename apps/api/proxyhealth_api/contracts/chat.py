"""Stateless follow-up chat about an analysis: ``POST /v1/chat`` (API_CONTRACT §3.7)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from proxyhealth_api.contracts.analysis import (
    Demand,
    GlossaryTerm,
    PlanStep,
    RedFlag,
    Safety,
    SummaryCard,
    Urgency,
)
from proxyhealth_api.contracts.common import LanguageTag, ModelMeta, PageText
from proxyhealth_api.contracts.enums import (
    DisclaimerKind,
    DocumentCategory,
    DocumentType,
    ReferTo,
    RefusalKind,
    ResourceTag,
    WarningCode,
)

MAX_CHAT_HISTORY = 8
MAX_QUESTION_CHARS = 1000

# Phase 2C caps on the re-sent context: the same bounds ``chat_pipeline.bounded_context`` applies
# (≤ 60 pages × 400 blocks × 4 000 chars, ≤ 60 items per list; the longest accepted paper is a
# 60-page PDF). A real analysis is far inside them; a padded body now gets ``400`` before any work.
MAX_CONTEXT_PAGES = 60
MAX_BLOCKS_PER_PAGE = 400
MAX_BLOCK_CHARS = 4_000
MAX_CONTEXT_ITEMS = 60


class AnalysisContext(BaseModel):
    """API_CONTRACT §3.7 — subset of ``AnalysisResult`` the client re-sends with each question.

    Each ``original_text`` page holds at most ``MAX_BLOCKS_PER_PAGE`` blocks of at most
    ``MAX_BLOCK_CHARS`` characters (checked here, because ``PageText``/``TextBlock`` are shared
    with the analysis output and its model schema)."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: str
    category: DocumentCategory
    document_type: DocumentType
    detected_language: LanguageTag
    sender_as_written: str | None
    summary: SummaryCard
    demands: list[Demand] = Field(max_length=MAX_CONTEXT_ITEMS)
    unverified: list[Demand] = Field(max_length=MAX_CONTEXT_ITEMS)
    plan_steps: list[PlanStep] = Field(max_length=MAX_CONTEXT_ITEMS)
    red_flags: list[RedFlag] = Field(max_length=MAX_CONTEXT_ITEMS)
    glossary: list[GlossaryTerm] = Field(max_length=MAX_CONTEXT_ITEMS)
    original_text: list[PageText] = Field(max_length=MAX_CONTEXT_PAGES)
    urgency: Urgency

    @field_validator("original_text")
    @classmethod
    def _pages_bounded(cls, pages: list[PageText]) -> list[PageText]:
        for page in pages:
            if len(page.blocks) > MAX_BLOCKS_PER_PAGE:
                raise ValueError(f"a page may hold at most {MAX_BLOCKS_PER_PAGE} blocks")
            if any(len(block.text) > MAX_BLOCK_CHARS for block in page.blocks):
                raise ValueError(f"a block may hold at most {MAX_BLOCK_CHARS} characters")
        return pages


class ChatMessage(BaseModel):
    """API_CONTRACT §3.7 — one prior turn."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    text: Annotated[str, StringConstraints(max_length=MAX_QUESTION_CHARS)]


class ChatRequest(BaseModel):
    """API_CONTRACT §3.7 — analysis context, ≤ 8 prior turns and the new question."""

    model_config = ConfigDict(extra="forbid")

    analysis: AnalysisContext
    messages: list[ChatMessage] = Field(default_factory=list, max_length=MAX_CHAT_HISTORY)
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    target_language: LanguageTag
    demo_sample_id: str | None = None


class Quote(BaseModel):
    """API_CONTRACT §3.7 — a verified quote the answer rests on."""

    span_id: str
    text: str
    page: int


class ChatAnswer(BaseModel):
    """API_CONTRACT §3.7 — the ``POST /v1/chat`` response."""

    request_id: str
    answer: str
    grounded_span_ids: list[str]
    grounded_quotes: list[Quote]
    not_in_document: bool
    refusal_kind: RefusalKind
    refer_to_professional: ReferTo
    distress_acknowledged: bool
    suggested_questions: list[str]
    resource_tags: list[ResourceTag]
    safety: Safety
    disclaimer_kind: DisclaimerKind
    warnings: list[WarningCode]
    model_meta: ModelMeta
