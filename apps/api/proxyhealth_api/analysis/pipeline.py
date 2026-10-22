"""``run_analysis`` — the document pipeline (BUILD_PLAN §4.1/§5.3 step 6; AI_PROMPTS §9.4, §11).

Order (AI_PROMPTS §11 as built — §14 item 15 there): upload validation → redaction (EXIF,
rotation, masks) → model reading (``single``, or ``two_call`` on ``SchemaFallbackNeeded`` /
``ANALYSIS_MODE``) → transcript assembly + quality (unreadable → stop, one call only) → injection
detection and one masked re-run → span verification → contact scrubber → scam scorer (a likely
scam is re-typed before any date or floor is applied) → deadline rules → the one ``tag`` call
when tagging needs it → emergency lexicon → urgency → phrasing lint/rewrite → dates in prose
checked against the paper (``prose_dates``) → tags, resources, clerk card, fixed notices →
disclaimers and warnings → ``AnalysisResult``. Decoding, redaction and PDF rasterization run in
the thread pool (``offload``).

No step trusts a model field it can recompute: facts must quote the transcript (D-09), contacts
come only from the paper or the resource DB (D-10), dates only from ``deadline_rules`` (D-11),
urgency only from ``urgency`` (D-12). A sample paper (``demo_sample_id``, or a mock dHash match)
computes its dates and urgency as of ``demo.as_of.DEMO_AS_OF`` because its printed dates are
fixed; real papers use the real clock. Nothing here writes to disk or logs content; page bytes,
transcripts and model prose live only in this request's memory (ARCHITECTURE §7).

This module also holds the helpers ``troubleshoot_pipeline`` and ``chat_pipeline`` share
(translator, language info, prompt variables, the ``generate`` wrapper, the rewrite callable).
"""

from __future__ import annotations

import functools
import re
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from proxyhealth_api.ai import prompt_loader as prompt
from proxyhealth_api.ai.failover import AIService, GenerateOutcome, SchemaFallbackNeeded
from proxyhealth_api.ai.provider import Part, Task
from proxyhealth_api.analysis import (
    classify,
    clerk,
    contacts_filter,
    deadline_rules,
    disclaimers,
    emergency,
    fixed_notices,
    injection,
    pdf_pages,
    phrasing,
    prose_dates,
    redaction,
    scam,
    tagging,
    transcript,
    uploads,
    urgency,
    verify,
)
from proxyhealth_api.analysis.i18n import Translator, translator_from
from proxyhealth_api.contracts.analysis import (
    AnalysisResult,
    AnalyzeRequest,
    ClerkMessage,
    Demand,
    Entities,
    PageThumbnail,
    PlanStep,
    Quality,
    RedFlag,
    Safety,
    SummaryCard,
    Urgency,
    VerificationSummary,
)
from proxyhealth_api.contracts.common import LANGUAGE_TAG_PATTERN, GeoHints, ModelMeta, TextBlock
from proxyhealth_api.contracts.enums import (
    AnalysisMode,
    Confidence,
    DataUseTier,
    DigitSystem,
    DisclaimerKind,
    DocumentCategory,
    DocumentType,
    ErrorCode,
    Legibility,
    ModelQuality,
    PackTier,
    PlanStepKind,
    Provider,
    RedFlagKind,
    ResourceTag,
    ScamRisk,
    SenderKind,
    UrgencyLevel,
    WarningCode,
)
from proxyhealth_api.contracts.model_out import (
    AnalysisModelOut,
    ChatModelOut,
    ExplainOut,
    LanguagePackModelOut,
    LanguageResolveOut,
    PlanStepOut,
    RewriteOut,
    TaggingModelOut,
    TranscriptOut,
    TroubleshootModelOut,
)
from proxyhealth_api.contracts.resources import ResourceMatch, ResourceMatchRequest
from proxyhealth_api.demo.as_of import DEMO_AS_OF
from proxyhealth_api.demo.fixtures import Fixture, FixtureStore
from proxyhealth_api.errors import ApiError
from proxyhealth_api.logging_ import log_event
from proxyhealth_api.packs.base import LanguageEntry, LanguageTable
from proxyhealth_api.packs.cache import PackCache, t_server
from proxyhealth_api.resources import matcher
from proxyhealth_api.resources.loader import ResourceRepo
from proxyhealth_api.resources.rules_repo import RulesRepo
from proxyhealth_api.settings import DATA_DIR, Settings


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
    # Optional (defaults keep every BUILD_PLAN §4.1 caller working): the app's pack cache and
    # language table; ``None`` → a process-wide default reading the same files.
    packs: PackCache | None = None
    languages: LanguageTable | None = None


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
TASK_PROMPT: dict[Task, str] = dict(prompt.SYSTEM_PROMPT)

MAX_REWRITE_CALLS = 8
"""Phrasing rewrites per request; beyond this the fixed hedge is used directly (latency cap)."""
CLERK_CARD_KEY = "clerk_card"  # strings-block key only; not a pack key (AI_PROMPTS §5.5.4)
CLERK_CARD_CONTEXT = (
    "The English card the reader shows a receptionist; translate for the reader's own eyes; "
    "keep dates and names as written"
)
_LANG_RE = re.compile(LANGUAGE_TAG_PATTERN)
_STATE_RE = re.compile(r"^[A-Za-z]{2}$")
_ZIP3_RE = re.compile(r"^\d{3}")


# ----------------------------------------------------------------------------- shared helpers


@functools.cache
def _default_languages() -> LanguageTable:
    return LanguageTable.load(DATA_DIR / "languages.yaml", DATA_DIR / "langpacks")


@functools.cache
def _default_packs(var_dir: str) -> PackCache:
    return PackCache(Path(var_dir))


def packs_of(deps: PipelineDeps) -> PackCache:
    if deps.packs is not None:
        return deps.packs
    return _default_packs(str(deps.settings.var_dir / "langpacks"))


def languages_of(deps: PipelineDeps) -> LanguageTable:
    return deps.languages if deps.languages is not None else _default_languages()


def translator(deps: PipelineDeps, tag: str) -> Translator:
    """``t_server`` bound to ``tag`` (target-language pack, English fallback, never raising)."""
    packs = packs_of(deps)

    def _t(key: str, /, **vars: str) -> str:
        return t_server(tag, key, packs, packs.base, **vars)

    return translator_from(_t)


def english(deps: PipelineDeps) -> Translator:
    return translator(deps, "en")


def base_strings(deps: PipelineDeps) -> dict[str, str]:
    return packs_of(deps).base.strings


@dataclass(frozen=True)
class LanguageFacts:
    """What the prompts and validators need to know about the target language."""

    tag: str
    name_en: str
    direction: str
    script: str | None
    digit_system: DigitSystem
    tier: PackTier
    known: bool


def language_facts(deps: PipelineDeps, tag: str) -> LanguageFacts:
    entry: LanguageEntry | None = languages_of(deps).get(tag)
    if entry is not None:
        return LanguageFacts(
            tag, entry.name_en, entry.direction.value, entry.script, entry.digit_system,
            entry.tier, True,
        )  # fmt: skip
    pack = packs_of(deps).lookup(tag) if _LANG_RE.match(tag) else None
    if pack is not None:
        return LanguageFacts(
            tag, pack.language_name_en, pack.direction.value, pack.script, pack.digit_system,
            pack.tier, False,
        )  # fmt: skip
    slug = tag[2:] if tag.startswith("x-") else tag
    name = " ".join(slug.replace("-", " ").split()).title() or tag
    return LanguageFacts(tag, name, "ltr", None, DigitSystem.western, PackTier.tier_3, False)


def language_tag(value: str) -> str:
    return value if _LANG_RE.match(value) else "und"


def base_of(tag: str | None) -> str:
    return (tag or "").split("-")[0].lower()


def hints_for(**values: str | None) -> dict[str, str]:
    return {k: v for k, v in values.items() if v}


def parsed_as[T: BaseModel](outcome: GenerateOutcome, schema: type[T]) -> T:
    parsed = outcome.result.parsed
    if not isinstance(parsed, schema):
        raise ApiError(
            ErrorCode.model_output_invalid, 502, f"Model output did not match {schema.__name__}."
        )
    return parsed


def prompt_base_vars(
    deps: PipelineDeps, *, target_language: str, today: date, direction: str | None = None
) -> dict[str, str]:
    """Placeholders every task shares: the closed lists plus target language and today."""
    lang = language_facts(deps, target_language)
    return {
        **prompt.catalog_vars(),
        "target_language": target_language,
        "target_language_name": lang.name_en,
        "direction": direction or lang.direction,
        "today": today.isoformat(),
    }


async def generate(
    deps: PipelineDeps,
    task: Task,
    media: Sequence[Part],
    vars: Mapping[str, str],
    *,
    pages: int = 1,
    is_pdf: bool = False,
    hints: Mapping[str, str] | None = None,
    deadline_at: datetime | None = None,
    lead: Sequence[Part] = (),
) -> GenerateOutcome:
    """One provider call through ``AIService``: rendered system prompt + user text before media.

    ``lead`` parts go before the user text (the mock reads the chat ``AnalysisContext`` from the
    first text part; Gemini never receives them — see ``chat_pipeline``)."""
    system = prompt.system(task, **vars)
    user_text = prompt.user(task, **vars)
    return await deps.ai.generate(
        task=task, parts=[*lead, Part.of_text(user_text), *media], system=system,
        schema=TASK_SCHEMA[task], pages=pages, is_pdf=is_pdf, request_id=deps.request_id,
        hints=hints, deadline_at=deadline_at,
    )  # fmt: skip


@dataclass
class RewriteBudget:
    """Shared across one request so a noisy answer cannot fan out into many fast calls."""

    remaining: int = MAX_REWRITE_CALLS
    calls: int = 0


def make_rewriter(
    deps: PipelineDeps,
    *,
    language: str,
    today: date,
    budget: RewriteBudget,
    deadline_at: datetime | None,
) -> phrasing.Rewriter:
    """``async rewrite(sentence, professional)`` via task ``phrasing_rewrite`` (fast tier).

    Any failure (quota, upstream, schema) returns ``None`` so the linter uses the fixed hedge —
    the fast tier being unavailable is never an error (AI_PROMPTS §11.9)."""

    async def rewrite(sentence: str, professional: str) -> str | None:
        if budget.remaining <= 0:
            return None
        budget.remaining -= 1
        budget.calls += 1
        vars = {
            **prompt_base_vars(deps, target_language=language, today=today),
            "professional": professional,
            "sentence": prompt.untrusted(sentence, 400),
        }
        try:
            outcome = await generate(
                deps, Task.phrasing_rewrite, [], vars, deadline_at=deadline_at,
                hints=hints_for(sentence=sentence, target_language=language),
            )  # fmt: skip
        except (ApiError, SchemaFallbackNeeded):
            return None
        parsed = outcome.result.parsed
        return parsed.sentence if isinstance(parsed, RewriteOut) else None

    return rewrite


def model_meta(
    outcome: GenerateOutcome,
    deps: PipelineDeps,
    *,
    demo: bool,
    latency_ms: int,
    mode: AnalysisMode = AnalysisMode.single,
) -> ModelMeta:
    provider = deps.ai.provider.name
    mock = provider is Provider.mock
    return ModelMeta(
        provider=provider,
        tier=outcome.route.tier,
        model_id=outcome.result.model_id,
        thinking_level=outcome.route.thinking,
        quality=outcome.quality,
        analysis_mode=AnalysisMode.mock if mock else mode,
        data_use_tier=DataUseTier.demo if mock else deps.data_use_tier,
        demo=demo or mock,
        latency_ms=latency_ms,
    )


def pack_machine_translated(deps: PipelineDeps, tag: str) -> bool:
    flag = packs_of(deps).machine_translated(tag)
    return flag if flag is not None else base_of(tag) != "en"


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


# ----------------------------------------------------------------------------- small mappers


def resource_tags(values: Sequence[str]) -> list[ResourceTag]:
    """Closed-list filter, order kept, duplicates dropped (unknown tags vanish silently)."""
    return tagging.validate_tags(values)


def demo_of(deps: PipelineDeps, demo_sample_id: str | None) -> bool:
    return bool(demo_sample_id) or deps.ai.provider.name is Provider.mock


def fixture_for(deps: PipelineDeps, demo_sample_id: str, kind: str) -> Fixture:
    """The sample paper behind ``demo_sample_id``; unknown id or wrong kind → ``400``.

    A demo request skips the consent gate, so its pages must always come from the fixture —
    never from the client (API_CONTRACT §3.5)."""
    fixture = deps.fixtures.get(demo_sample_id)
    if fixture is None or fixture.kind != kind:
        raise ApiError(
            ErrorCode.invalid_request, 400, "Unknown demo_sample_id.",
            details={"demo_sample_id": demo_sample_id[:64]},
        )  # fmt: skip
    return fixture


def is_sample_paper(deps: PipelineDeps, demo_sample_id: str | None, media: Sequence[Part]) -> bool:
    """A sample paper: ``demo_sample_id``, or (mock only) a first page the mock resolves to a
    document fixture by dHash — the same test ``MockProvider.resolve_fixture`` applies, so a
    photographed SAMPLE sheet counts. Real uploads with keys are never samples."""
    if demo_sample_id:
        return True
    if deps.ai.provider.name is not Provider.mock:
        return False
    first = next(
        (p.data for p in media
         if p.kind == "bytes" and p.data and (p.mime_type or "").startswith("image/")),
        None,
    )  # fmt: skip
    if first is None:
        return False
    limit = deps.settings.mock_phash_max_hamming
    return deps.fixtures.match_dhash(first, limit, kind="document") is not None


def analysis_today(now: datetime, state: str | None, *, sample: bool) -> date:
    """The day dates and urgency are computed from: ``DEMO_AS_OF`` for sample papers (their
    printed dates are fixed), the user's local day on the real clock (``now``) otherwise."""
    return DEMO_AS_OF if sample else deadline_rules.local_today(now, state)


# ----------------------------------------------------------------------------- upload

# Decoding, redaction, the mock dHash and PDF rasterization are CPU-bound (up to ~12 MP per page,
# 12 pages or a 60-page PDF): they run in the thread pool so one upload never stalls the event
# loop for every other request, and at most this many run at once to bound peak memory.
MAX_PARALLEL_IMAGE_WORK = 2
_IMAGE_SLOTS = threading.BoundedSemaphore(MAX_PARALLEL_IMAGE_WORK)


async def offload[**P, R](fn: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs) -> R:
    """``fn(*args, **kwargs)`` in the thread pool, holding one of the image-work slots."""

    def run() -> R:
        with _IMAGE_SLOTS:
            return fn(*args, **kwargs)

    return await run_in_threadpool(run)


@dataclass
class PreparedUpload:
    """Pages after validation and redaction, in memory only (never written anywhere)."""

    media: list[Part]
    is_pdf: bool
    pages_received: int
    page_sizes: list[tuple[int, int] | None] = field(default_factory=list)
    pdf_bytes: bytes | None = None


def prepare_upload(req: AnalyzeRequest, deps: PipelineDeps) -> PreparedUpload:
    """Upload validation + redaction (EXIF, rotation, masks) — ARCHITECTURE §2 steps 1–2."""
    if req.demo_sample_id:
        fixture = fixture_for(deps, req.demo_sample_id, "document")
        pngs = [fixture.page_png(n) for n in range(1, fixture.manifest.pages + 1)]
        return PreparedUpload(
            media=[Part.of_bytes(png, "image/png") for png in pngs], is_pdf=False,
            pages_received=len(pngs), page_sizes=[redaction.image_size(png) for png in pngs],
        )  # fmt: skip
    decoded = uploads.decode_pages(req.pages, deps.settings)
    if decoded.is_pdf:
        page = decoded.pages[0]
        if page.masks:
            raise ApiError(
                ErrorCode.invalid_request, 400,
                "Parts to hide cannot be applied to a PDF; send photos of the pages instead.",
            )  # fmt: skip
        sizes: list[tuple[int, int] | None] = list(pdf_pages.page_sizes(page.data))
        return PreparedUpload(
            media=[Part.of_bytes(page.data, uploads.PDF_MIME)], is_pdf=True,
            pages_received=decoded.page_count, page_sizes=sizes, pdf_bytes=page.data,
        )  # fmt: skip
    media: list[Part] = []
    image_sizes: list[tuple[int, int] | None] = []
    for page in decoded.pages:
        red = redaction.redact_image(page.data, page.mime_type, page.masks, page.rotation)
        media.append(Part.of_bytes(red.data, red.mime_type))
        image_sizes.append((red.width, red.height) if red.width and red.height else None)
    return PreparedUpload(
        media=media, is_pdf=False, pages_received=decoded.page_count, page_sizes=image_sizes
    )


# ----------------------------------------------------------------------------- prompt vars


def analysis_vars(
    req: AnalyzeRequest, deps: PipelineDeps, *, page_count: int, today: date
) -> dict[str, str]:
    """AI_PROMPTS §2 placeholders for ``analyze_single`` / ``transcribe`` / ``explain``."""
    notes = "; ".join(n.strip() for n in req.preferences.calendar_notes if n.strip())
    full = page_count <= deps.settings.translate_full_max_pages
    return {
        **prompt_base_vars(
            deps, target_language=req.target_language, today=today,
            direction=req.ui_direction.value,
        ),  # fmt: skip
        "state_or_unknown": req.state.upper() if req.state else "unknown",
        "tone": req.preferences.tone.value,
        "calendar_notes": prompt.untrusted(notes, 240),
        "date_format": req.preferences.date_format.value,
        "page_count": str(page_count),
        "translate_full": "yes" if full else "no",
        "document_hint": req.document_hint.value if req.document_hint else prompt.NONE_TEXT,
    }


_MARKER_PREFIXES = ("===", "--- page")


def render_paper_text(
    blocks: Sequence[TextBlock],
    *,
    page_count: int,
    detected_language: str,
    masked_ids: Sequence[str] = (),
) -> str:
    """AI_PROMPTS §5.2.3 ``{transcript}``: one ``[id|flags] text`` line per block, page markers.

    A block whose own text starts like a marker gets a leading space so it cannot forge one;
    injection-masked blocks show the fixed mask text instead of their words."""
    masked = set(masked_ids)
    mask_text = injection.load_config().mask_text
    pages = max(page_count, max((b.page for b in blocks), default=1), 1)
    lines = [f"=== BEGIN PAPER TEXT ({pages} pages, language {detected_language}) ==="]
    for number in range(1, pages + 1):
        lines.append(f"--- page {number} ---")
        for b in (x for x in blocks if x.page == number):
            flags = ",".join(
                f for f, on in (("unclear", b.is_unclear), ("hand", b.is_handwriting)) if on
            )
            label = f"{b.id}|{flags}" if flags else b.id
            words = transcript.mask_ssn(" ".join(b.text.splitlines()))
            text = mask_text if b.id in masked else words
            if text.lstrip().startswith(_MARKER_PREFIXES):
                text = " " + text
            lines.append(f"[{label}] {text}")
    lines.append("=== END PAPER TEXT ===")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- model reading

_CALL1_FIELDS = frozenset({"blocks", "legibility", "readable_reason"})


def merge_two_call(first: TranscriptOut, second: ExplainOut) -> AnalysisModelOut:
    """Seeing fields from call 1 (``transcribe``), everything else from call 2 (``explain``)."""
    return AnalysisModelOut(
        **second.model_dump(exclude=set(_CALL1_FIELDS)),
        blocks=list(first.blocks), legibility=first.legibility,
        readable_reason=first.readable_reason,
    )  # fmt: skip


def transcript_only(first: TranscriptOut) -> AnalysisModelOut:
    """Unreadable two-call result: call 1 said ``poor``, so call 2 is never made."""
    return AnalysisModelOut(
        document_type=DocumentType.unknown, category=DocumentCategory.other,
        document_type_confidence=Confidence.low, sender_as_written=None,
        sender_kind=SenderKind.unknown, detected_language=first.detected_language[:12] or "und",
        translated_pages=[], summary_title="", summary_body="", summary_body_en="",
        summary_span_ids=[], demands=[], plan_steps=[], glossary=[], red_flags=[],
        questions_to_ask=[], clerk_need_en="", emergency_terms_found=[], is_likely_scam=False,
        scam_signals=[], resource_tags=[], institutions_as_written=[], form_numbers=[],
        geo_state=None, geo_county=None, geo_city=None, geo_zip=None,
        legibility=first.legibility, readable_reason=first.readable_reason,
        blocks=list(first.blocks),
    )  # fmt: skip


@dataclass
class ModelReading:
    """What the model(s) returned for one request, before any validator ran."""

    out: AnalysisModelOut
    outcome: GenerateOutcome
    mode: AnalysisMode
    calls: int


async def explain_call(
    deps: PipelineDeps,
    first: TranscriptOut,
    vars: Mapping[str, str],
    *,
    page_count: int,
    hints: Mapping[str, str],
    deadline_at: datetime,
    masked_ids: Sequence[str] = (),
) -> tuple[AnalysisModelOut, GenerateOutcome]:
    """Two-call mode, call 2: text only (the pages are never re-sent)."""
    detected = first.detected_language or "und"
    vars2 = {
        **vars,
        "detected_language": detected,
        "transcript": render_paper_text(
            first.blocks, page_count=page_count, detected_language=detected,
            masked_ids=masked_ids,
        ),  # fmt: skip
    }
    outcome = await generate(
        deps, Task.explain, [], vars2, pages=page_count, hints=hints, deadline_at=deadline_at
    )
    return merge_two_call(first, parsed_as(outcome, ExplainOut)), outcome


async def read_paper(
    deps: PipelineDeps,
    media: Sequence[Part],
    vars: Mapping[str, str],
    *,
    page_count: int,
    is_pdf: bool,
    hints: Mapping[str, str],
    deadline_at: datetime,
) -> ModelReading:
    """AI_PROMPTS §9.4: ``single`` first; ``SchemaFallbackNeeded`` → ``two_call`` (``auto``)."""
    mode = deps.settings.analysis_mode
    calls = 0
    if mode in ("auto", "single"):
        try:
            calls += 1
            outcome = await generate(
                deps, Task.analyze_single, media, vars, pages=page_count, is_pdf=is_pdf,
                hints=hints, deadline_at=deadline_at,
            )  # fmt: skip
            out = parsed_as(outcome, AnalysisModelOut)
            return ModelReading(out, outcome, AnalysisMode.single, calls)
        except SchemaFallbackNeeded as exc:
            if mode == "single":
                raise ApiError(
                    ErrorCode.model_output_invalid, 502,
                    "The AI service could not read this paper in one step.",
                    details={"reason": str(exc)[:40]},
                ) from exc  # fmt: skip
            log_event(
                request_id=deps.request_id, route="analysis.mode_fallback",
                analysis_mode=AnalysisMode.two_call.value, error_code="schema_fallback",
            )  # fmt: skip
    try:
        calls += 1
        t_outcome = await generate(
            deps, Task.transcribe, media, vars, pages=page_count, is_pdf=is_pdf, hints=hints,
            deadline_at=deadline_at,
        )  # fmt: skip
        first = parsed_as(t_outcome, TranscriptOut)
        if first.legibility is Legibility.poor:
            return ModelReading(transcript_only(first), t_outcome, AnalysisMode.two_call, calls)
        calls += 1
        out, e_outcome = await explain_call(
            deps, first, vars, page_count=page_count, hints=hints, deadline_at=deadline_at
        )
    except SchemaFallbackNeeded as exc:  # pragma: no cover - raised only for analyze_single
        raise ApiError(
            ErrorCode.model_output_invalid, 502, "The AI service returned an unusable answer."
        ) from exc
    return ModelReading(out, e_outcome, AnalysisMode.two_call, calls)


async def masked_rerun(
    deps: PipelineDeps,
    reading: ModelReading,
    upload: PreparedUpload,
    paper: transcript.Transcript,
    hit_ids: Sequence[str],
    vars: Mapping[str, str],
    *,
    hints: Mapping[str, str],
    deadline_at: datetime,
) -> tuple[AnalysisModelOut, GenerateOutcome]:
    """D-15 / AI_PROMPTS §11.8: one re-run with the offending blocks masked.

    Single mode on photos with a box for every hit block → ``analyze_single`` again on the
    pages with black boxes burned over those blocks; otherwise (two-call mode, a PDF, a block
    without a box) → ``explain`` again with those blocks rendered as the fixed mask text. The
    re-run's explaining fields replace the first answer's; the blocks stay the original
    transcript so the reader still sees what was printed."""
    first = TranscriptOut(
        blocks=paper.blocks, detected_language=reading.out.detected_language,
        legibility=reading.out.legibility, readable_reason=reading.out.readable_reason,
    )  # fmt: skip
    plan = injection.mask_boxes(paper, hit_ids)
    if reading.mode is AnalysisMode.single and not upload.is_pdf and not plan.needs_two_call:
        media: list[Part] = []
        for number, part in enumerate(upload.media, 1):
            boxes = plan.boxes_by_page.get(number)
            if boxes and part.data is not None:
                burned = redaction.mask_regions(part.data, part.mime_type or "image/png", boxes)
                media.append(Part.of_bytes(burned.data, burned.mime_type))
            else:
                media.append(part)
        try:
            outcome = await generate(
                deps, Task.analyze_single, media, vars, pages=upload.pages_received,
                hints=hints, deadline_at=deadline_at,
            )  # fmt: skip
        except SchemaFallbackNeeded:
            pass  # fall through to the text-masked explain call
        else:
            rerun = parsed_as(outcome, AnalysisModelOut)
            if rerun.legibility is not Legibility.poor:
                explained = ExplainOut.model_validate(rerun.model_dump(exclude=set(_CALL1_FIELDS)))
                return merge_two_call(first, explained), outcome
    return await explain_call(
        deps, first, vars, page_count=upload.pages_received, hints=hints,
        deadline_at=deadline_at, masked_ids=hit_ids,
    )  # fmt: skip


def neutral_urgency() -> Urgency:
    return Urgency(
        level=UrgencyLevel.info, headline_key=urgency.KEY_INFO_NO_DATE, headline_params={},
        driving_demand_id=None, nearest_date_iso=None, days_until=None, past_date=False,
        floor_applied=False, verify_resource_id=None,
    )  # fmt: skip


def no_safety(*, credential_or_payment_request: bool = False) -> Safety:
    return Safety(
        emergency=False, emergency_kinds=[],
        credential_or_payment_request=credential_or_payment_request,
    )  # fmt: skip


def geo_hints(out: AnalysisModelOut | TaggingModelOut) -> GeoHints:
    """Location printed on the paper only; state = 2 letters, zip cut to 3 digits (D-10)."""
    state = (out.geo_state or "").strip()
    zip_digits = re.sub(r"\D", "", out.geo_zip or "")
    return GeoHints(
        state=state.upper() if _STATE_RE.match(state) else None,
        county=(out.geo_county or "").strip()[:80] or None,
        city=(out.geo_city or "").strip()[:80] or None,
        zip3=zip_digits[:3] if len(zip_digits) >= 3 else None,
    )


def translation_confidence(detected: str, target: str, lang: LanguageFacts) -> Confidence:
    if base_of(detected) == base_of(target):
        return Confidence.high
    if lang.tier is PackTier.tier_3:
        return Confidence.low
    return Confidence.medium


def page_thumbnails(req: AnalyzeRequest, upload: PreparedUpload) -> list[PageThumbnail] | None:
    """PDF pages rasterized in memory for the crops (API_CONTRACT §3.5); images → ``None``."""
    if not (upload.is_pdf and req.include_page_thumbnails and upload.pdf_bytes):
        return None
    return pdf_pages.rasterize(upload.pdf_bytes, max_pages=upload.pages_received)


# ----------------------------------------------------------------------------- §11 helpers


@dataclass
class PhrasingStats:
    """Phrasing-lint bookkeeping shared across one result (AI_PROMPTS §11.9)."""

    rewrites: int = 0
    warnings: list[WarningCode] = field(default_factory=list)


async def phrase(
    text: str,
    *,
    t: Translator,
    language: str,
    category: DocumentCategory | None,
    rewrite: phrasing.Rewriter | None,
    stats: PhrasingStats,
    document_type: DocumentType | None = None,
) -> str:
    """Lint one model-authored string; rewrite once, else hedge (fixed copy never comes here)."""
    if not text or not text.strip():
        return text
    res = await phrasing.enforce(
        text, t=t, category=category, language=language, rewrite=rewrite,
        document_type=document_type,
    )  # fmt: skip
    stats.rewrites += res.replacements
    for w in res.warnings:
        if w not in stats.warnings:
            stats.warnings.append(w)
    return res.text


def resource_hosts(deps: PipelineDeps) -> set[str]:
    """Hosts of every DB URL (never counted as a fake agency domain by the scam scorer)."""
    hosts: set[str] = set()
    for res in deps.resources.all():
        for url in (res.url, *res.alt_urls):
            if url:
                hosts.add(scam.host_of(url))
    return {h for h in hosts if h}


def printed_forms(form_numbers: Sequence[str], full_text: str) -> list[str]:
    """Form numbers the model listed that are really printed (``I-765`` ≈ ``I 765``), as the
    printed number only ("Form W-2 Wage and Tax Statement 2025" → ``W-2``; ``classify.py``)."""
    return classify.printed_form_numbers(form_numbers, full_text)


def printed_institutions(
    names: Sequence[str], scrubber: contacts_filter.ContactScrubber
) -> list[str]:
    """Institution names on the paper (or in the DB); invented organisations are dropped."""
    out: list[str] = []
    for name in names:
        clean = " ".join(name.split())[:120]
        if clean and clean not in out and scrubber.allow.allows_org(clean):
            out.append(clean)
    return out


def plan_steps_from(
    steps: Sequence[PlanStepOut],
    paper: transcript.Transcript,
    demand_ids: set[str],
    *,
    drop_paper_contact_steps: bool,
) -> list[PlanStep]:
    """Model plan steps → contract steps (tags validated, span/demand ids checked, ids unique).

    With a likely scam, ``call``/``submit_online`` steps aimed at the paper's own contact (no
    DB tag to route them to a checked resource) are dropped (DOCUMENT_TAXONOMY §6.4)."""
    out: list[PlanStep] = []
    seen: set[str] = set()
    for step in steps:
        tags = resource_tags(step.resource_tags)
        if (
            drop_paper_contact_steps
            and step.kind in (PlanStepKind.call, PlanStepKind.submit_online)
            and not tags
        ):
            continue
        sid = step.id if step.id and step.id not in seen else f"s{len(out) + 1}"
        while sid in seen:
            sid += "_"
        seen.add(sid)
        out.append(
            PlanStep(
                id=sid, text=step.text, kind=step.kind, resource_tags=tags,
                span_ids=paper.existing(step.span_ids),
                demand_id=step.demand_id if step.demand_id in demand_ids else None,
            )  # fmt: skip
        )
    return out


def tag_summary_text(
    out: AnalysisModelOut,
    document_type: DocumentType,
    demands: Sequence[Demand],
    flags: Sequence[RedFlag],
    geo: GeoHints,
) -> str:
    """AI_PROMPTS §5.6 ``{summary_text}`` (≤ 2 000 chars; quoted values only, no transcript)."""
    asks = "; ".join(f"{d.kind.value} {d.role or 'other'} {d.value_verbatim}" for d in demands)
    places = ", ".join(v for v in (geo.city, geo.county, geo.state, geo.zip3) if v)
    lines = [
        f"type={document_type.value} category={out.category.value} "
        f"sender={out.sender_as_written or 'none'}",
        f"summary: {out.summary_body_en}",
        f"asks for: {asks or 'none'}",
        f"institutions: {', '.join(out.institutions_as_written) or 'none'}",
        f"places: {places or 'none'}",
        f"forms: {', '.join(out.form_numbers) or 'none'}",
        f"flags: {', '.join(f.kind.value for f in flags) or 'none'}",
    ]
    return prompt.untrusted("\n".join(lines), 2000)


async def run_tag_call(
    deps: PipelineDeps,
    summary_text: str,
    *,
    document_type: DocumentType,
    demo_sample_id: str | None,
    deadline_at: datetime,
) -> TaggingModelOut | None:
    """Task ``tag`` (fast, text only) — at most once; any failure means "no extra tags"."""
    vars = {**prompt.catalog_vars(), "summary_text": summary_text}
    try:
        outcome = await generate(
            deps, Task.tag, [], vars, deadline_at=deadline_at,
            hints=hints_for(demo_sample_id=demo_sample_id, document_type=document_type.value),
        )  # fmt: skip
    except ApiError:
        return None
    parsed = outcome.result.parsed
    return parsed if isinstance(parsed, TaggingModelOut) else None


def make_clerk_translator(
    deps: PipelineDeps, lang: LanguageFacts, *, deadline_at: datetime
) -> clerk.ClerkTranslate:
    """AI_PROMPTS §5.5.4: the English card as a one-line ``clerk_translate`` chunk."""

    async def translate(english: str) -> str | None:
        line = f"{CLERK_CARD_KEY} ⟶ {' '.join(english.split())} ⟶ {CLERK_CARD_CONTEXT}"
        vars = {
            "chunk_index": "1", "chunk_count": "1", "language_name_en": lang.name_en,
            "language_tag": lang.tag, "script_hint": lang.script or "unknown",
            "direction_hint": lang.direction if lang.known else "unknown",
            "digit_hint": lang.digit_system.value if lang.known else "unknown",
            "strings_block": line,
        }  # fmt: skip
        outcome = await generate(
            deps, Task.clerk_translate, [], vars, deadline_at=deadline_at,
            hints=hints_for(
                language_tag=lang.tag, language_name_en=lang.name_en, key=CLERK_CARD_KEY,
                english=english,
            ),
        )  # fmt: skip
        parsed = outcome.result.parsed
        if not isinstance(parsed, LanguagePackModelOut) or not parsed.strings:
            return None
        for kv in parsed.strings:
            if kv.key == CLERK_CARD_KEY:
                return kv.value
        return parsed.strings[0].value

    return translate


# ----------------------------------------------------------------------------- results


@dataclass
class RequestContext:
    """Per-request values every result builder needs."""

    req: AnalyzeRequest
    deps: PipelineDeps
    upload: PreparedUpload
    lang: LanguageFacts
    t: Translator
    started: float
    demo: bool
    thumbnails: list[PageThumbnail] | None = None
    """PDF page thumbnails, rasterized off the event loop (``page_thumbnails``)."""


def finish_meta(
    rc: RequestContext,
    outcome: GenerateOutcome,
    mode: AnalysisMode,
    *,
    detected: str,
    warnings: Sequence[WarningCode],
    translation_partial: bool,
) -> tuple[ModelMeta, list[DisclaimerKind], list[WarningCode]]:
    """§11.11: ``model_meta``, secondary ``disclaimers[]`` and the final ``warnings[]``."""
    meta = model_meta(
        outcome, rc.deps, demo=rc.demo, latency_ms=elapsed_ms(rc.started), mode=mode
    )
    secondary = disclaimers.secondary_disclaimers(
        detected_language=detected, target_language=rc.req.target_language,
        pack_machine_translated=pack_machine_translated(rc.deps, rc.req.target_language),
        model_meta=meta,
    )  # fmt: skip
    final = disclaimers.final_warnings(
        warnings, translation_partial=translation_partial, detected_language=detected,
        target_language=rc.req.target_language, degraded=meta.quality is ModelQuality.degraded,
        data_use_tier=meta.data_use_tier, demo=meta.demo,
    )  # fmt: skip
    return meta, secondary, final


def unreadable_result(
    rc: RequestContext,
    reading: ModelReading,
    paper: transcript.Transcript,
    quality: Quality,
    warnings: Sequence[WarningCode],
) -> AnalysisResult:
    """§11.1: ``legibility == poor`` → a ``200`` that says "try again"; §11.2–§11.10 skipped."""
    out = classify.unreadable_reading(reading.out)  # TAXONOMY §3.11: unknown / other
    detected = language_tag(out.detected_language)
    scrubber = contacts_filter.make_scrubber(paper.full_text, rc.deps.resources.names(), rc.t)
    en = english(rc.deps)
    need = en(clerk.GENERIC_NEED_KEY)
    card = clerk.generic_card(rc.lang.name_en, need)
    meta, secondary, final = finish_meta(
        rc, reading.outcome, reading.mode, detected=detected, warnings=warnings,
        translation_partial=False,
    )  # fmt: skip
    return AnalysisResult(
        schema_version=1, request_id=rc.deps.request_id,
        analysis_id=rc.req.analysis_id or str(uuid.uuid4()), created_at=rc.deps.clock(),
        quality=quality, category=out.category, document_type=out.document_type,
        document_type_confidence=Confidence.low, sender_as_written=None,
        sender_kind=out.sender_kind, detected_language=detected,
        target_language=rc.req.target_language, translation_confidence=Confidence.low,
        is_likely_scam=False, scam_risk=ScamRisk.none, scam_reasons=[],
        urgency=neutral_urgency(),
        summary=SummaryCard(
            title=scrubber.scrub(out.summary_title), body=scrubber.scrub(out.summary_body),
            body_en=scrubber.scrub(out.summary_body_en), span_ids=[],
        ),
        demands=[], unverified=[], plan_steps=[], red_flags=[], glossary=[],
        entities=Entities(
            institutions_as_written=[], form_numbers=[],
            geo=GeoHints(state=None, county=None, city=None, zip3=None),
            has_case_number=paper.has_case_number, has_receipt_number=paper.has_receipt_number,
        ),
        clerk_message=ClerkMessage(
            english=card, translated=card, need_line_source="template", appended_line_keys=[]
        ),
        resource_tags=[], resource_preview=[], original_text=paper.pages, translated_text=[],
        questions_to_ask=[],
        verification=VerificationSummary(
            facts_checked=0, facts_rejected=0, contacts_stripped=scrubber.total,
            phrasing_rewrites=0, injection_masked=False, verifier_version=verify.VERIFIER_VERSION,
        ),
        safety=no_safety(), disclaimer_kind=disclaimers.disclaimer_kind(out.category),
        disclaimers=secondary, warnings=final, model_meta=meta,
        page_thumbnails=rc.thumbnails,
    )  # fmt: skip


async def run_analysis(req: AnalyzeRequest, deps: PipelineDeps) -> AnalysisResult:
    """The document pipeline (module docstring; AI_PROMPTS §11)."""
    started = time.perf_counter()
    deadline_at = deps.ai.request_deadline()
    upload = await offload(prepare_upload, req, deps)
    uploads.check_inline_budget(upload.media, deps.settings)
    now = deps.clock()
    # Sample papers print fixed dates: their dates and urgency run as of DEMO_AS_OF (demo/as_of).
    sample = await offload(is_sample_paper, deps, req.demo_sample_id, upload.media)
    today = analysis_today(now, req.state, sample=sample)
    lang = language_facts(deps, req.target_language)
    t = translator(deps, req.target_language)
    rc = RequestContext(
        req, deps, upload, lang, t, started, demo_of(deps, req.demo_sample_id),
        thumbnails=await offload(page_thumbnails, req, upload),
    )  # fmt: skip
    hints = hints_for(demo_sample_id=req.demo_sample_id, target_language=req.target_language)
    vars = analysis_vars(req, deps, page_count=upload.pages_received, today=today)

    # Model reading, then transcript assembly + quality (§11.1).
    reading = await read_paper(
        deps, upload.media, vars, page_count=upload.pages_received, is_pdf=upload.is_pdf,
        hints=hints, deadline_at=deadline_at,
    )  # fmt: skip
    paper = transcript.assemble_transcript(
        reading.out.blocks, pages_received=upload.pages_received, page_sizes=upload.page_sizes,
        hide_id_numbers=req.hide_id_numbers,
    )  # fmt: skip
    quality, warnings = transcript.compute_quality(
        reading.out.legibility, reading.out.readable_reason, paper,
        pages_received=upload.pages_received,
    )  # fmt: skip
    if not quality.readable:
        return unreadable_result(rc, reading, paper, quality, warnings)

    # §11.8 detection first (no FAST call is spent on output that would be discarded).
    out, outcome = reading.out, reading.outcome
    code_flags: list[RedFlag] = []
    scan = injection.detect_injection(paper)
    if scan.found:
        out, outcome = await masked_rerun(
            deps, reading, upload, paper, scan.hit_ids, vars, hints=hints,
            deadline_at=deadline_at,
        )  # fmt: skip
        code_flags.append(injection.injection_red_flag(paper, scan.hit_ids, t))
        warnings.append(injection.INJECTION_WARNING)
        log_event(request_id=deps.request_id, route="analysis.injection", injection_suspected=1)
    detected = language_tag(out.detected_language)
    # TAXONOMY §3 rule 16 / §2: a printed form label or heading checks the model's type, and the
    # type fixes the category (classify.py) — before verification and scam scoring use them.
    type_check = classify.check_document_type(out, paper)
    out = classify.apply_type_check(out, type_check)
    if type_check.rule is not None:
        log_event(request_id=deps.request_id, route=f"analysis.type_check.{type_check.rule}",
                  document_type=type_check.document_type.value)  # fmt: skip

    # §11.2 span verification.
    checked = verify.verify_demands(out.demands, paper)
    flags_checked = verify.verify_red_flags(out.red_flags, paper)
    # An agency's anti-fraud line ("USCIS will never ask you to pay with gift cards") quoted as a
    # payment red flag is boilerplate, not a demand: it neither scores nor shows.
    flags_checked.flags = [
        f for f in flags_checked.flags
        if f.kind is not RedFlagKind.scam_payment_method
        or not scam.is_anti_fraud_quote(f.source_quote)
    ]  # fmt: skip
    # A payment flag must quote a payment request (TAXONOMY §6.1); a sample paper's SAMPLE footer
    # is no part of it — no flag, step or scam signal rests on it (classify.py, §6.3).
    flags_checked = scam.screen_model_flags(flags_checked, language=detected)
    banner = classify.sample_banner_ids(paper) if sample else frozenset[str]()
    if sample:
        flags_checked.flags = classify.drop_banner_flags(flags_checked.flags, banner)
        out = out.model_copy(
            update={"plan_steps": classify.drop_banner_steps(out.plan_steps, paper, banner)}
        )
    if checked.page_edge_crop:
        warnings.append(WarningCode.page_edge_crop)
    summary_ids = verify.verify_summary_span_ids(out.summary_span_ids, paper)

    # §11.3 contact scrubber (target-language marker; English marker for ``body_en``).
    names = deps.resources.names()
    scrubber = contacts_filter.make_scrubber(paper.full_text, names, t)
    scrub_en = contacts_filter.make_scrubber(paper.full_text, names, english(deps))

    # §11.6 scam (before dates/urgency so a re-typed scam paper never gets agency rules).
    scam_out = scam.score_transcript(
        paper, document_type=out.document_type, sender_kind=out.sender_kind,
        sender_as_written=out.sender_as_written, model_flags=flags_checked.flags,
        model_signals=out.scam_signals, demands=checked.verified,
        resource_hosts=resource_hosts(deps), t=t,
        language=detected, skip_ids=banner,
    )  # fmt: skip
    document_type = scam.retype_for_scam(out.document_type, scam_out.scam_risk)
    # A code-corrected type never survives a likely scam; a re-typed paper is low confidence.
    out, document_type = classify.after_scam(out, type_check, document_type, scam_out.scam_risk)
    code_flags.extend(scam_out.red_flags)

    # §11.4 deadline rules.
    # ``Preferences.date_format`` is a display preference only: printed dates are read in the
    # paper's own order (page cue, then the type's default), never the reader's.
    ctx = deadline_rules.context_for(
        document_type=document_type, rules=deps.rules.deadline_rules(), now=now,
        state=req.state, language=detected, transcript_text=paper.full_text,
        digit_system=lang.digit_system, t=t, category=out.category,
    )  # fmt: skip
    if ctx.today != today:  # a sample paper: pinned day (the state's zone never moves it)
        ctx = replace(ctx, today=today)
    demands = deadline_rules.apply_deadline_rules(checked.verified, checked.sources, ctx, paper)

    # §11.10 (part) tags; the one ``tag`` call runs now so its emergency hint reaches §11.7.
    geo = geo_hints(out)
    forms = printed_forms(out.form_numbers, paper.full_text)
    tag_call_tags: list[str] | None = None
    first_tags = tagging.finalize_tags(
        out.resource_tags, document_type=document_type, category=out.category,
        form_numbers=forms, readable=True,
    )  # fmt: skip
    tag_out: TaggingModelOut | None = None
    if first_tags.needs_tag_call:
        tag_out = await run_tag_call(
            deps, tag_summary_text(out, document_type, demands, flags_checked.flags, geo),
            document_type=document_type, demo_sample_id=req.demo_sample_id,
            deadline_at=deadline_at,
        )  # fmt: skip
        tag_call_tags = list(tag_out.tags) if tag_out is not None else []

    # Emergency lexicon (§11.7), then urgency (it reads the emergency flag).
    emerg = emergency.detect_emergency(
        [b.text for b in paper.blocks], detected_language=detected,
        target_language=req.target_language, model_terms=out.emergency_terms_found,
        model_flag=bool(tag_out and tag_out.emergency),
    )  # fmt: skip
    warnings.extend(emerg.warnings)
    urg = urgency.compute_urgency(
        document_type, out.category, demands, emergency=emerg.safety.emergency,
        today=ctx.today, t=t, unverified=checked.unverified,
    )  # fmt: skip
    code_flags.extend(urg.red_flags)

    return await finish_analysis(
        rc, out, outcome, reading.mode, paper=paper, quality=quality, warnings=warnings,
        detected=detected, checked=checked, model_flags=flags_checked, summary_ids=summary_ids,
        scrubber=scrubber, scrub_en=scrub_en, scam_out=scam_out, document_type=document_type,
        demands=demands, geo=geo, forms=forms, tag_call_tags=tag_call_tags, safety=emerg.safety,
        urgency_value=urg.urgency, code_flags=code_flags, injection_masked=scan.found,
        today=ctx.today, resources_today=deadline_rules.local_today(now, req.state),
        deadline_at=deadline_at,
    )  # fmt: skip


async def finish_analysis(
    rc: RequestContext,
    out: AnalysisModelOut,
    outcome: GenerateOutcome,
    mode: AnalysisMode,
    *,
    paper: transcript.Transcript,
    quality: Quality,
    warnings: list[WarningCode],
    detected: str,
    checked: verify.VerifiedDemands,
    model_flags: verify.VerifiedRedFlags,
    summary_ids: list[str],
    scrubber: contacts_filter.ContactScrubber,
    scrub_en: contacts_filter.ContactScrubber,
    scam_out: scam.ScamOutcome,
    document_type: DocumentType,
    demands: list[Demand],
    geo: GeoHints,
    forms: list[str],
    tag_call_tags: list[str] | None,
    safety: Safety,
    urgency_value: Urgency,
    code_flags: list[RedFlag],
    injection_masked: bool,
    today: date,
    deadline_at: datetime,
    resources_today: date | None = None,
) -> AnalysisResult:
    """§11.9 phrasing, §11.10 clerk / fixed notices / tags / resources, §11.11 → result.

    ``today`` is the analysis day (``DEMO_AS_OF`` for a sample paper); ``resources_today`` is
    the real local day, used for resource-entry freshness (defaults to ``today``)."""
    req, deps, t = rc.req, rc.deps, rc.t
    target, category = req.target_language, out.category
    en = english(deps)
    budget = RewriteBudget()
    rewrite = make_rewriter(deps, language=target, today=today, budget=budget,
                            deadline_at=deadline_at)  # fmt: skip
    rewrite_en = make_rewriter(deps, language="en", today=today, budget=budget,
                               deadline_at=deadline_at)  # fmt: skip
    stats = PhrasingStats()

    # §11.4 in prose: a date the model wrote must be a verified demand's date, printed on the
    # paper, or today (``prose_dates``); others are replaced or their sentence dropped.
    allowed = prose_dates.allowed_dates(demands, paper.full_text, today=today, language=detected)
    date_stats = prose_dates.ProseDateStats()
    # D-26 / rule 7: a printed date keeps its printed spelling and digits stay Western in prose
    # ("۱۴ اکتبر ۲۰۲۶" for the printed "October 14, 2026" is put back as printed).
    printed = prose_dates.printed_forms(paper.full_text, detected, demands)

    def as_printed(text: str, language: str = target) -> str:
        return prose_dates.as_printed(text, printed, language)

    async def clean(text: str) -> str:
        text = await phrase(scrubber.scrub(text), t=t, language=target, category=category,
                            rewrite=rewrite, stats=stats, document_type=document_type)  # fmt: skip
        return as_printed(
            prose_dates.check_text(text, allowed, t=t, language=target, stats=date_stats)
        )

    async def clean_demand(d: Demand) -> Demand:
        text = await phrase(scrubber.scrub(d.text), t=t, language=target, category=category,
                            rewrite=rewrite, stats=stats, document_type=document_type)  # fmt: skip
        d = d.model_copy(update={"text": text})
        return d.model_copy(update={
            "text": as_printed(prose_dates.check_demand_text(
                d, allowed, t=t, language=target, stats=date_stats
            )),
            # D-10: every model-authored field shown to the reader passes the contact filter.
            "documents": [as_printed(x) for x in scrubber.scrub_all(d.documents) if x.strip()],
            "ambiguity_note": await clean(d.ambiguity_note) if d.ambiguity_note else None,
        })  # fmt: skip

    body_en = await phrase(scrub_en.scrub(out.summary_body_en), t=en, language="en",
                           category=category, rewrite=rewrite_en, stats=stats,
                           document_type=document_type)  # fmt: skip
    summary = SummaryCard(
        title=await clean(out.summary_title), body=await clean(out.summary_body),
        body_en=as_printed(
            prose_dates.check_text(body_en, allowed, t=en, language="en", stats=date_stats), "en"
        ),
        span_ids=summary_ids,
    )  # fmt: skip
    final_demands = [await clean_demand(d) for d in demands]
    unverified = [await clean_demand(d) for d in checked.unverified]
    flags: list[RedFlag] = []
    for f in model_flags.flags:
        if f.text.strip() == verify.MULTIPLE_DOCUMENTS_SENTINEL:
            flags.append(f)
        else:
            flags.append(f.model_copy(update={"text": await clean(f.text)}))
    demand_ids = {d.id for d in final_demands} | {d.id for d in unverified}
    steps: list[PlanStep] = []
    for step in plan_steps_from(out.plan_steps, paper, demand_ids,
                                drop_paper_contact_steps=scam_out.is_likely_scam):  # fmt: skip
        text = await clean(step.text)
        if step.kind is PlanStepKind.professional:
            text = phrasing.ensure_professional(text, category, t)
        steps.append(step.model_copy(update={"text": text}))
    glossary = [
        g.model_copy(update={"explanation": await clean(g.explanation)})
        for g in out.glossary
        # A term the paper does not print (an invented URL, phone or name) is no glossary entry.
        if scrubber.scrub(g.term_as_written) == g.term_as_written
    ]  # fmt: skip
    questions = [q for q in [await clean(q) for q in out.questions_to_ask] if q.strip()]
    # The sender line and the translation are model output too (D-10): an invented name or
    # contact in the sender drops the line (as the clerk card does); the translation keeps
    # translated organisation names but loses any phone, web or e-mail address the paper does not
    # print (a digit slip in a translated phone number never reaches the reader).
    sender = out.sender_as_written
    if sender and scrubber.scrub(sender) != sender:
        sender = None
    translated = [
        p.model_copy(update={
            "text": as_printed(scrubber.scrub_kinds(p.text, contacts_filter.CONTACT_KINDS))
        })
        for p in out.translated_pages
    ]  # fmt: skip

    # §11.10 tags, resources, clerk card, fixed notices.
    tags = tagging.finalize_tags(
        out.resource_tags, document_type=document_type, category=category, form_numbers=forms,
        readable=True, scam_risk=scam_out.scam_risk, emergency=safety.emergency,
        red_flags=flags, tag_call_tags=tag_call_tags, gate_sensitive=True,
    ).tags  # fmt: skip
    institutions = printed_institutions(out.institutions_as_written, scrubber)
    preview: list[ResourceMatch] = []
    if req.state and tags:
        preview = matcher.match(
            ResourceMatchRequest(
                tags=tags, document_type=document_type, category=category, state=req.state,
                county=geo.county, zip3=req.zip3, language=target,
                institutions_as_written=institutions, scam_risk=scam_out.scam_risk,
                emergency=safety.emergency, limit=3,
            ),
            deps.resources, en_strings=base_strings(deps), today=resources_today or today,
        ).results[:3]  # fmt: skip
    clerk_out = await clerk.build_clerk_message(
        language_name_en=rc.lang.name_en, document_type=document_type,
        sender_as_written=out.sender_as_written, sender_kind=out.sender_kind,
        clerk_need_en=out.clerk_need_en,
        template_line=clerk.template_need_line(deps.rules, document_type, en),
        target_language=target, scrubber=scrubber,
        first_resource_hhs_funded=bool(preview)
        and deps.resources.is_hhs_funded(preview[0].resource.id),
        translate=make_clerk_translator(deps, rc.lang, deadline_at=deadline_at),
        t=t,  # a failed translation → the pack's clerk.generic_card (CL-055(c), AI_PROMPTS §5.5.4)
    )  # fmt: skip
    # Code flags (the scam scorer's notario regex, injection, expired date) count as much as the
    # model's for the fixed cards: a notario flyer gets "A notario is not a lawyer" either way.
    facts = fixed_notices.NoticeFacts(
        document_type=document_type, document_type_confidence=out.document_type_confidence,
        transcript_text=paper.full_text, form_numbers=forms, demands=final_demands,
        red_flags=[*flags, *code_flags], scam_risk=scam_out.scam_risk,
    )  # fmt: skip
    notices = fixed_notices.evaluate_notices(deps.rules, facts, t)
    red_flags = fixed_notices.merge_red_flags(
        fixed_notices.replace_multiple_documents_sentinel(flags, t), [*notices, *code_flags]
    )

    # §11.11 disclaimers and warnings.
    warnings = [
        *warnings, *outcome.warnings, *scrubber.warnings(), *scrub_en.warnings(),
        *stats.warnings, *clerk_out.warnings,
    ]  # fmt: skip
    translated_pages = {p.page for p in out.translated_pages if p.text.strip()}
    partial = upload_partial(rc, paper, translated_pages)
    meta, secondary, final = finish_meta(
        rc, outcome, mode, detected=detected, warnings=warnings, translation_partial=partial
    )
    return AnalysisResult(
        schema_version=1, request_id=deps.request_id,
        analysis_id=req.analysis_id or str(uuid.uuid4()), created_at=deps.clock(),
        quality=quality, category=category, document_type=document_type,
        document_type_confidence=out.document_type_confidence,
        sender_as_written=sender, sender_kind=out.sender_kind,
        detected_language=detected, target_language=target,
        translation_confidence=translation_confidence(detected, target, rc.lang),
        is_likely_scam=scam_out.is_likely_scam, scam_risk=scam_out.scam_risk,
        scam_reasons=list(scam_out.scam_reasons), urgency=urgency_value, summary=summary,
        demands=final_demands, unverified=unverified, plan_steps=steps, red_flags=red_flags,
        glossary=glossary,
        entities=Entities(
            institutions_as_written=institutions, form_numbers=forms, geo=geo,
            has_case_number=paper.has_case_number, has_receipt_number=paper.has_receipt_number,
        ),
        clerk_message=clerk_out.message, resource_tags=tags, resource_preview=preview,
        original_text=paper.pages, translated_text=translated,
        questions_to_ask=questions,
        verification=VerificationSummary(
            # An unprinted date in prose is a rejected fact (checked and rejected once).
            facts_checked=checked.facts_checked + model_flags.facts_checked + date_stats.rejected,
            facts_rejected=checked.facts_rejected + model_flags.facts_rejected
            + date_stats.rejected,
            contacts_stripped=scrubber.total + scrub_en.total,
            phrasing_rewrites=stats.rewrites, injection_masked=injection_masked,
            verifier_version=verify.VERIFIER_VERSION,
        ),
        safety=safety, disclaimer_kind=disclaimers.disclaimer_kind(category),
        disclaimers=secondary, warnings=final, model_meta=meta,
        page_thumbnails=rc.thumbnails,
    )  # fmt: skip


def upload_partial(rc: RequestContext, paper: transcript.Transcript, translated: set[int]) -> bool:
    """``translation_partial``: long papers are translated in part by design; otherwise a page
    with text but no translation means the model skipped it."""
    if rc.upload.pages_received > rc.deps.settings.translate_full_max_pages:
        return True
    return any(p.blocks and p.page not in translated for p in paper.pages)
