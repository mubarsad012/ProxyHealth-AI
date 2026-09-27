"""``run_analysis`` (BUILD_PLAN §4.1/§5.0). WP0: one ``AIService.generate`` call and a neutral
``AnalysisModelOut → AnalysisResult`` mapping (urgency ``info``, ``verified=true`` copied, empty
``red_flags``, ``disclaimer_kind`` by category). No validators yet — WP2 adds the §11 pipeline.
"""

import base64
import binascii
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

from proxyhealth_api.ai.failover import AIService, GenerateOutcome
from proxyhealth_api.ai.provider import Part, Task
from proxyhealth_api.contracts.analysis import (
    AmountInfo,
    AnalysisResult,
    AnalyzeRequest,
    ClerkMessage,
    DateInfo,
    Demand,
    Entities,
    PlanStep,
    Quality,
    RedFlag,
    Safety,
    SummaryCard,
    Urgency,
    VerificationSummary,
)
from proxyhealth_api.contracts.common import (
    LANGUAGE_TAG_PATTERN,
    GeoHints,
    ModelMeta,
    PageInput,
    PageText,
    TextBlock,
)
from proxyhealth_api.contracts.enums import (
    AnalysisMode,
    Confidence,
    DataUseTier,
    DateKind,
    DisclaimerKind,
    DocumentCategory,
    ErrorCode,
    Legibility,
    Provider,
    ResourceTag,
    ScamRisk,
    Severity,
    UrgencyLevel,
    WarningCode,
)
from proxyhealth_api.contracts.model_out import (
    AnalysisModelOut,
    ChatModelOut,
    DemandOut,
    ExplainOut,
    LanguagePackModelOut,
    LanguageResolveOut,
    PlanStepOut,
    RedFlagOut,
    RewriteOut,
    TaggingModelOut,
    TranscriptOut,
    TroubleshootModelOut,
)
from proxyhealth_api.demo.fixtures import FixtureStore
from proxyhealth_api.errors import ApiError
from proxyhealth_api.resources.loader import ResourceRepo
from proxyhealth_api.resources.rules_repo import RulesRepo
from proxyhealth_api.settings import Settings


@dataclass
class PipelineDeps:
    settings: Settings
    ai: AIService
    resources: ResourceRepo
    rules: RulesRepo
    fixtures: FixtureStore
    request_id: str
    data_use_tier: DataUseTier
    clock: Callable[[], datetime]


# AI_PROMPTS §3 — looked up by the pipeline from the Task, not returned by route().
TASK_SCHEMA: dict[Task, type[BaseModel]] = {
    Task.analyze_single: AnalysisModelOut,
    Task.transcribe: TranscriptOut,
    Task.explain: ExplainOut,
    Task.troubleshoot: TroubleshootModelOut,
    Task.chat: ChatModelOut,
    Task.langpack_chunk: LanguagePackModelOut,
    Task.clerk_translate: LanguagePackModelOut,
    Task.tag: TaggingModelOut,
    Task.resolve_language: LanguageResolveOut,
    Task.phrasing_rewrite: RewriteOut,
}
TASK_PROMPT: dict[Task, str] = {
    Task.analyze_single: "analyze.md",
    Task.transcribe: "transcribe.md",
    Task.explain: "explain.md",
    Task.troubleshoot: "troubleshoot.md",
    Task.chat: "chat.md",
    Task.langpack_chunk: "langpack.md",
    Task.clerk_translate: "langpack.md",
    Task.tag: "tag.md",
    Task.resolve_language: "langpack.md",
    Task.phrasing_rewrite: "phrasing_rewrite.md",
}

_LANG_RE = re.compile(LANGUAGE_TAG_PATTERN)
_VALID_TAGS = {t.value for t in ResourceTag}
_AMOUNT_RE = re.compile(r"(\d[\d,]*)(?:\.(\d{1,2}))?")
_DISCLAIMER_BY_CATEGORY: dict[DocumentCategory, DisclaimerKind] = {
    DocumentCategory.immigration: DisclaimerKind.legal_information_only,
    DocumentCategory.court: DisclaimerKind.legal_information_only,
    DocumentCategory.medical: DisclaimerKind.medical_information_only,
    DocumentCategory.benefits: DisclaimerKind.benefits_information_only,
    DocumentCategory.housing: DisclaimerKind.housing_information_only,
}


def decode_pages(pages: list[PageInput], settings: Settings) -> tuple[list[Part], bool]:
    """Base64 → bytes with the cheap checks; WP2's ``uploads.py`` adds sniffing and PDF counts."""
    is_pdf = any(p.mime_type == "application/pdf" for p in pages)
    if is_pdf and len(pages) > 1:
        raise ApiError(ErrorCode.too_many_pages, 400, "A PDF must be the only page.")
    parts: list[Part] = []
    for index, page in enumerate(pages, 1):
        try:
            data = base64.b64decode(page.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ApiError(
                ErrorCode.invalid_request, 400, f"pages[{index - 1}].data_base64 is not base64."
            ) from exc
        cap = settings.max_pdf_bytes if is_pdf else settings.max_page_bytes
        if len(data) > cap:
            raise ApiError(
                ErrorCode.payload_too_large, 413, f"Page {index} exceeds the size limit.",
                details={"max_bytes": cap, "page": index},
            )  # fmt: skip
        parts.append(Part.of_bytes(data, page.mime_type))
    return parts, is_pdf


def language_tag(value: str) -> str:
    return value if _LANG_RE.match(value) else "und"


def resource_tags(values: list[str]) -> list[ResourceTag]:
    return [ResourceTag(v) for v in dict.fromkeys(values) if v in _VALID_TAGS]


def disclaimer_for(category: DocumentCategory) -> DisclaimerKind:
    return _DISCLAIMER_BY_CATEGORY.get(category, DisclaimerKind.general_information)


def hints_for(**values: str | None) -> dict[str, str]:
    return {k: v for k, v in values.items() if v}


def parsed_as[T: BaseModel](outcome: GenerateOutcome, schema: type[T]) -> T:
    parsed = outcome.result.parsed
    if not isinstance(parsed, schema):
        raise ApiError(
            ErrorCode.model_output_invalid, 502, f"Model output did not match {schema.__name__}."
        )
    return parsed


def model_meta(
    outcome: GenerateOutcome, deps: PipelineDeps, *, demo: bool, latency_ms: int
) -> ModelMeta:
    provider = deps.ai.provider.name
    return ModelMeta(
        provider=provider,
        tier=outcome.route.tier,
        model_id=outcome.result.model_id,
        thinking_level=outcome.route.thinking,
        quality=outcome.quality,
        analysis_mode=AnalysisMode.mock if provider is Provider.mock else AnalysisMode.single,
        data_use_tier=deps.data_use_tier,
        demo=demo,
        latency_ms=latency_ms,
    )  # fmt: skip


def red_flag(rf: RedFlagOut) -> RedFlag:
    return RedFlag(
        kind=rf.kind, text=rf.text, source_quote=rf.source_quote, span_ids=list(rf.span_ids),
        page=rf.page, severity=Severity.medium, fixed_copy_key=None, verified=True,
    )  # fmt: skip


def _amount(text: str | None, currency: str | None) -> AmountInfo | None:
    m = _AMOUNT_RE.search(text or "")
    if not m:
        return None
    whole = int(m.group(1).replace(",", ""))
    cents = int((m.group(2) or "0").ljust(2, "0"))
    return AmountInfo(amount_minor=whole * 100 + cents, currency=(currency or "USD")[:3].upper())


def _demand(d: DemandOut) -> Demand:
    date: DateInfo | None = None
    if d.date_text or d.relative_rule_text:
        date = DateInfo(
            value_iso=None, time_text=d.time_text, kind=DateKind.unresolved, formula=None,
            anchor_quote=None, anchor_demand_id=None, rule_id=None, rule_source_url=None,
            rule_verification=None, localized_line=d.date_text or d.relative_rule_text,
        )  # fmt: skip
    return Demand(
        id=d.id, kind=d.kind, text=d.text, value_verbatim=d.value_verbatim,
        source_quote=d.source_quote, span_ids=list(d.span_ids), page=d.page,
        confidence=d.confidence, verified=True, verification_note=None, date=date,
        amount=_amount(d.amount_text, d.currency), documents=list(d.documents), role=d.role,
        reminder_eligible=False, ambiguity_note=d.ambiguity_note,
    )  # fmt: skip


def _plan_step(p: PlanStepOut) -> PlanStep:
    return PlanStep(
        id=p.id, text=p.text, kind=p.kind, resource_tags=resource_tags(p.resource_tags),
        span_ids=list(p.span_ids), demand_id=p.demand_id,
    )  # fmt: skip


def _page_texts(blocks: list[TextBlock], pages: int) -> list[PageText]:
    count = max(pages, max((b.page for b in blocks), default=1))
    return [
        PageText(page=n, width=None, height=None, blocks=[b for b in blocks if b.page == n])
        for n in range(1, count + 1)
    ]


def map_analysis(
    out: AnalysisModelOut, req: AnalyzeRequest, outcome: GenerateOutcome, deps: PipelineDeps,
    *, pages_received: int, latency_ms: int,
) -> AnalysisResult:  # fmt: skip
    demo = bool(req.demo_sample_id) or deps.ai.provider.name is Provider.mock
    detected = language_tag(out.detected_language)
    kind = disclaimer_for(out.category)
    disclaimers = [kind, DisclaimerKind.ai_generated]
    if detected.split("-")[0] != req.target_language.split("-")[0]:
        disclaimers.append(DisclaimerKind.machine_translation)
    if demo:
        disclaimers.append(DisclaimerKind.demo_sample)
    warnings: list[WarningCode] = list(outcome.warnings)
    if demo:
        warnings.append(WarningCode.demo_sample)
    readable = out.legibility is not Legibility.poor
    return AnalysisResult(
        schema_version=1,
        request_id=deps.request_id,
        analysis_id=req.analysis_id or str(uuid.uuid4()),
        created_at=deps.clock(),
        quality=Quality(
            readable=readable, legibility=out.legibility, reason=out.readable_reason,
            pages_received=pages_received,
            pages_unreadable=[] if readable else list(range(1, pages_received + 1)),
        ),  # fmt: skip
        category=out.category,
        document_type=out.document_type,
        document_type_confidence=out.document_type_confidence,
        sender_as_written=out.sender_as_written,
        sender_kind=out.sender_kind,
        detected_language=detected,
        target_language=req.target_language,
        translation_confidence=(
            Confidence.high if detected == req.target_language else Confidence.medium
        ),
        is_likely_scam=out.is_likely_scam,
        scam_risk=ScamRisk.likely if out.is_likely_scam else ScamRisk.none,
        scam_reasons=list(out.scam_signals),
        urgency=Urgency(
            level=UrgencyLevel.info, headline_key="urgency.info.no_date", headline_params={},
            driving_demand_id=None, nearest_date_iso=None, days_until=None, past_date=False,
            floor_applied=False, verify_resource_id=None,
        ),  # fmt: skip
        summary=SummaryCard(
            title=out.summary_title, body=out.summary_body, body_en=out.summary_body_en,
            span_ids=list(out.summary_span_ids),
        ),  # fmt: skip
        demands=[_demand(d) for d in out.demands],
        unverified=[],
        plan_steps=[_plan_step(p) for p in out.plan_steps],
        red_flags=[],
        glossary=list(out.glossary),
        entities=Entities(
            institutions_as_written=list(out.institutions_as_written),
            form_numbers=list(out.form_numbers),
            geo=GeoHints(
                state=(out.geo_state or None) and out.geo_state[:2].upper(),
                county=out.geo_county, city=out.geo_city,
                zip3=(out.geo_zip or None) and out.geo_zip[:3],
            ),
            has_case_number=False,
            has_receipt_number=False,
        ),  # fmt: skip
        clerk_message=ClerkMessage(
            english=out.clerk_need_en,
            translated=out.clerk_need_en if detected == req.target_language
            else f"⟦{req.target_language}⟧ {out.clerk_need_en}",
            need_line_source="ai",
            appended_line_keys=[],
        ),  # fmt: skip
        resource_tags=resource_tags(out.resource_tags),
        resource_preview=[],
        original_text=_page_texts(out.blocks, pages_received),
        translated_text=list(out.translated_pages),
        questions_to_ask=list(out.questions_to_ask),
        verification=VerificationSummary(
            facts_checked=len(out.demands), facts_rejected=0, contacts_stripped=0,
            phrasing_rewrites=0, injection_masked=False, verifier_version="0",
        ),  # fmt: skip
        safety=Safety(
            emergency=bool(out.emergency_terms_found), emergency_kinds=[],
            credential_or_payment_request=False,
        ),  # fmt: skip
        disclaimer_kind=kind,
        disclaimers=disclaimers,
        warnings=warnings,
        model_meta=model_meta(outcome, deps, demo=demo, latency_ms=latency_ms),
        page_thumbnails=None,
    )


async def run_analysis(req: AnalyzeRequest, deps: PipelineDeps) -> AnalysisResult:
    media, is_pdf = decode_pages(req.pages, deps.settings)
    pages_received = len(req.pages)
    if not pages_received and req.demo_sample_id:
        fixture = deps.fixtures.get(req.demo_sample_id)
        pages_received = fixture.manifest.pages if fixture else 1
    parts = [Part.of_text(f"target_language={req.target_language}"), *media]
    started = time.perf_counter()
    outcome = await deps.ai.generate(
        task=Task.analyze_single, parts=parts, system="", schema=AnalysisModelOut,
        pages=max(pages_received, 1), is_pdf=is_pdf, request_id=deps.request_id,
        hints=hints_for(demo_sample_id=req.demo_sample_id, target_language=req.target_language),
    )  # fmt: skip
    latency_ms = int((time.perf_counter() - started) * 1000)
    out = parsed_as(outcome, AnalysisModelOut)
    return map_analysis(
        out, req, outcome, deps, pages_received=pages_received, latency_ms=latency_ms
    )
