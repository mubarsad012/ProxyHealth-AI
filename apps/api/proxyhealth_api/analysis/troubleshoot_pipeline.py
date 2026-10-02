"""``run_troubleshoot`` — screenshot help and scam check (BUILD_PLAN §4.1; AI_PROMPTS §5.3, §11).

Order: upload validation + redaction (in the thread pool) → one ``troubleshoot`` call (pro,
``medium``) → quote checks against the model's own ``screen_text`` (``error_text_quoted``, each
step's ``ui_target_as_written``, red-flag quotes) → contact scrubber → scam scorer (regexes over
the screen, model hints, credential request) → emergency lexicon (``screen_text`` + ``user_goal``,
plus the model's ``crisis`` tag) → injection detection (flag + warning; a screenshot has no block
boxes to mask, so no re-run) → phrasing lint (steps, flags, summary, meaning, cautions) →
printed forms (a date or number the screen shows keeps its spelling; other digits Western,
``prose_dates.as_printed``, AI_PROMPTS §5.0 rule 7) → tags (``scam_report`` / ``crisis`` first) →
disclaimers and warnings. A sample screenshot never sends
the typed goal to the provider. The deadline, urgency and clerk/resource steps of AI_PROMPTS §11
do not apply to a screen. Nothing here writes to disk or logs content (ARCHITECTURE §7).
"""

from __future__ import annotations

import re
import time
from collections.abc import Sequence

from proxyhealth_api.ai import prompt_loader as prompt
from proxyhealth_api.ai.provider import Part, Task
from proxyhealth_api.analysis import (
    contacts_filter,
    disclaimers,
    emergency,
    injection,
    prose_dates,
    redaction,
    scam,
    tagging,
    uploads,
    verify,
)
from proxyhealth_api.analysis.deadline_rules import local_today
from proxyhealth_api.analysis.pipeline import (
    PhrasingStats,
    PipelineDeps,
    RewriteBudget,
    demo_of,
    elapsed_ms,
    fixture_for,
    generate,
    hints_for,
    make_rewriter,
    model_meta,
    offload,
    parsed_as,
    phrase,
    prompt_base_vars,
    resource_hosts,
    translator,
)
from proxyhealth_api.contracts.analysis import RedFlag
from proxyhealth_api.contracts.enums import (
    DisclaimerKind,
    DocumentType,
    ModelQuality,
    RedFlagKind,
    ResourceTag,
    Severity,
    WarningCode,
)
from proxyhealth_api.contracts.model_out import RedFlagOut, TroubleshootModelOut
from proxyhealth_api.contracts.troubleshoot import (
    TroubleshootRequest,
    TroubleshootResult,
    TroubleshootStep,
)

# AI_PROMPTS §11.11: a screen that asks for any of these is a credential/payment request.
CREDENTIAL_RE = re.compile(
    r"\bPIN\b|(?i:password|pass\s?code|one[- ]time (?:code|password)|verification code|"
    r"card number|credit card|debit card|\bCVV\b|\bCVC\b|security code|\bSSN\b|"
    r"social security|A[- ]?Number|alien (?:registration )?number|routing|account number)"
)
_HIGH_KINDS = frozenset(
    {
        RedFlagKind.scam_payment_method,
        RedFlagKind.impersonation,
        RedFlagKind.notario,
        RedFlagKind.guaranteed_result,
        RedFlagKind.fee_for_free_form,
    }
)
MAX_STEPS = 6
MAX_CAUTIONS = 4


def screen_media(req: TroubleshootRequest, deps: PipelineDeps) -> Part:
    """The one screenshot: the sample's PNG for a demo request (client bytes ignored), else the
    upload decoded, sniffed and redacted (EXIF, rotation, masks) in memory."""
    if req.demo_sample_id:
        fixture = fixture_for(deps, req.demo_sample_id, "screenshot")
        return Part.of_bytes(fixture.page_png(1), "image/png")
    page = uploads.decode_pages([req.screenshot], deps.settings).pages[0]
    red = redaction.redact_image(page.data, page.mime_type, page.masks, page.rotation)
    return Part.of_bytes(red.data, red.mime_type)


def clean_screen_text(lines: Sequence[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        text = " ".join(line.split())
        if text and text not in out:
            out.append(text)
    return out


def on_screen(text: str | None, corpus: str) -> bool:
    """True when ``text`` is (NFKC/dash/quote-normalised, or ≥ 0.92 fuzzily) in ``corpus``."""
    return bool(text and text.strip()) and verify.find_quote(text or "", corpus).found


def screen_flags(flags: Sequence[RedFlagOut], corpus: str) -> tuple[list[RedFlag], int]:
    """Model red flags whose quote is on the screen (others dropped, D-09); (kept, dropped)."""
    kept: list[RedFlag] = []
    dropped = 0
    for f in flags:
        if not on_screen(f.source_quote, corpus):
            dropped += 1
            continue
        if f.kind is RedFlagKind.scam_payment_method and scam.is_anti_fraud_quote(f.source_quote):
            dropped += 1  # "SSA will never ask you to pay with gift cards" is not a demand
            continue
        kept.append(
            RedFlag(
                kind=f.kind, text=f.text, source_quote=f.source_quote, span_ids=[], page=None,
                severity=Severity.high if f.kind in _HIGH_KINDS else Severity.medium,
                fixed_copy_key=None, verified=True,
            )  # fmt: skip
        )
    return kept, dropped


async def run_troubleshoot(req: TroubleshootRequest, deps: PipelineDeps) -> TroubleshootResult:
    started = time.perf_counter()
    deadline_at = deps.ai.request_deadline()
    media = await offload(screen_media, req, deps)  # decode + redaction off the event loop
    uploads.check_inline_budget([media], deps.settings)
    target = req.target_language
    t = translator(deps, target)
    today = local_today(deps.clock())
    vars = {
        **prompt_base_vars(deps, target_language=target, today=today),
        "mode": req.mode.value,
        "portal_hint": req.portal_hint.value if req.portal_hint else prompt.NONE_TEXT,
        # A sample screenshot skips the consent gate, so nothing the reader typed may reach the
        # provider with it: the typed goal stays on the server (emergency lexicon only).
        "user_goal": prompt.untrusted(None if req.demo_sample_id else req.user_goal, 300),
    }
    hints = hints_for(
        demo_sample_id=req.demo_sample_id, target_language=target, mode=req.mode.value
    )
    outcome = await generate(
        deps, Task.troubleshoot, [media], vars, hints=hints, deadline_at=deadline_at
    )
    out = parsed_as(outcome, TroubleshootModelOut)
    warnings: list[WarningCode] = []

    # Quote checks against the model's own screen transcript.
    screen_text = clean_screen_text(out.screen_text)
    corpus = "\n".join(screen_text)
    error_quoted = out.error_text_quoted if on_screen(out.error_text_quoted, corpus) else None
    model_flags, _ = screen_flags(out.red_flags, corpus)
    asks = out.asks_for_credentials_or_payment or bool(CREDENTIAL_RE.search(corpus))

    # Contact scrubber: only contacts printed on the screen may survive.
    scrubber = contacts_filter.make_scrubber("", deps.resources.names(), t, extra_texts=screen_text)

    # Scam scorer over what the screen shows (the typed goal is the reader's words, not the
    # screen's, so it never scores as a signal).
    scam_out = scam.score_scam(
        scam.segments_from_lines(screen_text), document_type=None, model_flags=model_flags,
        model_signals=out.scam_signals, credential_request=asks,
        resource_hosts=resource_hosts(deps), t=t,
    )  # fmt: skip

    # Emergency lexicon over the screen and the reader's goal.
    emerg = emergency.detect_emergency(
        screen_text, detected_language=None, target_language=target,
        user_texts=[req.user_goal] if req.user_goal else [],
        model_flag=ResourceTag.crisis.value in out.resource_tags,
        credential_or_payment_request=asks,
    )  # fmt: skip
    warnings.extend(emerg.warnings)

    # Injection: text on the screen addressed to computers → flag + warning (no boxes to mask).
    code_flags: list[RedFlag] = list(scam_out.red_flags)
    if injection.text_has_injection(screen_text):
        code_flags.append(
            RedFlag(
                kind=RedFlagKind.injection_suspected, text=t(injection.WARNING_KEY),
                source_quote=None, span_ids=[], page=None, severity=Severity.medium,
                fixed_copy_key=None, verified=True,
            )  # fmt: skip
        )
        warnings.append(injection.INJECTION_WARNING)

    # Phrasing lint (one fast rewrite per flagged sentence, else the fixed hedge).
    stats = PhrasingStats()
    rewrite = make_rewriter(
        deps, language=target, today=today, budget=RewriteBudget(), deadline_at=deadline_at
    )

    # Rule 7 / D-26: a date the screen prints keeps its printed spelling; digits stay Western.
    printed = prose_dates.printed_forms(corpus)

    async def clean(text: str) -> str:
        text = await phrase(
            scrubber.scrub(text), t=t, language=target, category=None, rewrite=rewrite,
            stats=stats,
        )  # fmt: skip
        return prose_dates.as_printed(text, printed, target)

    steps: list[TroubleshootStep] = []
    for step in sorted(out.steps, key=lambda s: s.order)[:MAX_STEPS]:
        target_text = step.ui_target_as_written
        steps.append(
            TroubleshootStep(
                order=len(steps) + 1, text=await clean(step.text),
                ui_target_as_written=target_text if on_screen(target_text, corpus) else None,
            )  # fmt: skip
        )
    flags = [f.model_copy(update={"text": await clean(f.text)}) for f in model_flags]
    summary = await clean(out.screen_summary)
    meaning = await clean(out.error_meaning)
    # Cautions are model prose like the steps: contact filter and phrasing lint (TAXONOMY §8).
    cautions = [c for c in [await clean(c) for c in out.cautions[:MAX_CAUTIONS]] if c.strip()]
    tags = tagging.finalize_tags(
        out.resource_tags, document_type=DocumentType.unknown, readable=True,
        scam_risk=scam_out.scam_risk, emergency=emerg.safety.emergency, red_flags=flags,
    ).tags  # fmt: skip

    warnings += [*outcome.warnings, *scrubber.warnings(), *stats.warnings]
    demo = demo_of(deps, req.demo_sample_id)
    meta = model_meta(outcome, deps, demo=demo, latency_ms=elapsed_ms(started))
    final = disclaimers.final_warnings(
        warnings, degraded=meta.quality is ModelQuality.degraded,
        data_use_tier=meta.data_use_tier, demo=meta.demo,
    )  # fmt: skip
    return TroubleshootResult(
        request_id=deps.request_id,
        screen_summary=summary,
        error_text_quoted=error_quoted,
        error_meaning=meaning,
        steps=steps,
        cautions=cautions,
        asks_for_credentials_or_payment=asks,
        is_likely_scam=scam_out.is_likely_scam,
        scam_risk=scam_out.scam_risk,
        scam_reasons=list(scam_out.scam_reasons),
        needs_human_help=out.needs_human_help or scam_out.is_likely_scam,
        red_flags=sorted([*code_flags, *flags], key=lambda f: f.severity is not Severity.high),
        resource_tags=tags,
        screen_text=screen_text,
        confidence=out.confidence,
        safety=emerg.safety,
        disclaimer_kind=DisclaimerKind.general_information,
        warnings=final,
        model_meta=meta,
    )
