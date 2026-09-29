"""``run_analysis`` — the document pipeline (BUILD_PLAN §4.1/§5.3 step 6; AI_PROMPTS §9.4, §11).

Order (AI_PROMPTS §11; ARCHITECTURE §2): upload validation → redaction (EXIF, rotation, masks) →
model reading (``single``, or ``two_call`` on ``SchemaFallbackNeeded`` / ``ANALYSIS_MODE``) →
transcript assembly + quality (unreadable → stop, one call only) → injection detection and one
masked re-run → span verification → contact scrubber → deadline rules → emergency lexicon →
urgency → scam scorer → phrasing lint/rewrite → tags, resources, clerk card, fixed notices →
disclaimers and warnings → ``AnalysisResult``.

No step trusts a model field it can recompute: facts must quote the transcript (D-09), contacts
come only from the paper or the resource DB (D-10), dates only from ``deadline_rules`` (D-11),
urgency only from ``urgency`` (D-12). Nothing here writes to disk or logs content; page bytes,
transcripts and model prose live only in this request's memory (ARCHITECTURE §7).

This module also holds the helpers ``troubleshoot_pipeline`` and ``chat_pipeline`` share
(translator, language info, prompt variables, the ``generate`` wrapper, the rewrite callable).
"""

from __future__ import annotations

import functools
import re
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel

from proxyhealth_api.ai import prompt_loader as prompt
from proxyhealth_api.ai.failover import AIService, GenerateOutcome, SchemaFallbackNeeded
from proxyhealth_api.ai.provider import Part, Task
from proxyhealth_api.analysis import (
    clerk,
    contacts_filter,
    deadline_rules,
    disclaimers,
    emergency,
    fixed_notices,
    injection,
    pdf_pages,
    phrasing,
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
    ErrorCode,
    Legibility,
    ModelQuality,
    PackTier,
    PlanStepKind,
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
    ExplainOut,
    LanguagePackModelOut,
    LanguageResolveOut,
    RewriteOut,
    TaggingModelOut,
    TranscriptOut,
    TroubleshootModelOut,
)
from proxyhealth_api.contracts.resources import ResourceMatch, ResourceMatchRequest
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
CLERK_CARD_KEY = "clerk.card"
CLERK_CARD_CONTEXT = (
    "The English card the reader shows a receptionist; translate for the reader's own eyes; "
    "keep dates and names as written"
)
_LANG_RE = re.compile(LANGUAGE_TAG_PATTERN)
_STATE_RE = re.compile(r"^[A-Za-z]{2}$")
_ZIP3_RE = re.compile(r"^\d{3}")
_ALNUM_RE = re.compile(r"[^0-9a-z]")


# ----------------------------------------------------------------------------- shared helpers


@functools.cache
def _default_languages() -> LanguageTable:
    return LanguageTable.load(DATA_DIR / "languages.yaml", DATA_DIR / "langpacks")


@functools.cache
def _default_packs(var_dir: str) -> PackCache:
    return PackCache(Path(var_dir))


def packs_of(deps: PipelineDeps) -> PackCache:
    return deps.packs if deps.packs is not None else _default_packs(str(deps.settings.var_dir))


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
