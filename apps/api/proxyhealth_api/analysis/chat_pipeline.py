"""``run_chat`` — one grounded follow-up answer (BUILD_PLAN §4.1; AI_PROMPTS §5.4, §11).

Stateless: the client re-sends the stored ``AnalysisContext`` and the last ≤ 8 turns; images
are never re-sent. Order: context compaction (≤ 60 000 chars, §5.4.3) → one ``chat`` call (fast,
``low``) → grounding check (every ``grounded_span_ids`` id must exist in ``original_text``; none
left → ``not_in_document``) → contact scrubber (only contacts printed on the paper survive) →
phrasing lint (a hedged answer carries the matching ``refusal_kind`` and a referral) →
injection guard (typed instructions + a failing answer → ``out_of_scope``) → a
``not_in_document`` answer that is not a refusal carries the pack's fixed ``chat.not_in_document``
sentence exactly once (``with_not_in_document``; the client never adds it) → emergency lexicon over
the question and the turns → tags → disclaimers and warnings. The model is never asked to
compute a date: the context shows the app's own labelled dates only. Nothing here writes to disk
or logs content (ARCHITECTURE §7).
"""

from __future__ import annotations

import difflib
import re
import time
import unicodedata
from collections.abc import Sequence

from proxyhealth_api.ai import prompt_loader as prompt
from proxyhealth_api.ai.provider import Part, Task
from proxyhealth_api.analysis import (
    contacts_filter,
    disclaimers,
    emergency,
    injection,
    phrasing,
    tagging,
)
from proxyhealth_api.analysis.pipeline import (
    PipelineDeps,
    RewriteBudget,
    analysis_today,
    demo_of,
    elapsed_ms,
    english,
    generate,
    hints_for,
    make_rewriter,
    model_meta,
    parsed_as,
    prompt_base_vars,
    translator,
)
from proxyhealth_api.contracts.analysis import Demand
from proxyhealth_api.contracts.chat import AnalysisContext, ChatAnswer, ChatRequest, Quote
from proxyhealth_api.contracts.common import PageText
from proxyhealth_api.contracts.enums import (
    DateKind,
    DocumentType,
    ModelQuality,
    Provider,
    ReferTo,
    RefusalKind,
    WarningCode,
)
from proxyhealth_api.contracts.model_out import ChatModelOut

MAX_CONTEXT_CHARS = 60_000
MAX_SUGGESTED = 3
NOT_IN_DOCUMENT_KEY = "chat.not_in_document"
# A model sentence this close to the fixed one (after normalisation) is the same sentence.
SAME_SENTENCE_RATIO = 0.8
REFER_REQUIRED = frozenset(
    {RefusalKind.eligibility, RefusalKind.filing_advice, RefusalKind.outcome,
     RefusalKind.medical_interpretation, RefusalKind.drafting}
)  # fmt: skip


def _q(text: str | None) -> str:
    """A context value on one line, quoted; never able to forge the END marker."""
    flat = " ".join((text or "").split()).replace("===", "= = =")
    return '"' + flat.replace('"', "'") + '"'


def _date_label(d: Demand) -> str:
    if d.date is None:
        return ""
    if d.date.kind is DateKind.stated:
        return f" date=stated {d.date.value_iso or 'unparsed'}"
    if d.date.kind is DateKind.estimated:
        return (
            f" date=estimated {d.date.value_iso} (rule {d.date.rule_id}; confirm with sender)"
        )
    return " date=unresolved"


def _demand_lines(demands: Sequence[Demand]) -> list[str]:
    if not demands:
        return ["  (none)"]
    return [
        f"  {d.id} {d.kind.value}" + (f" role={d.role}" if d.role else "")
        + f" value={_q(d.value_verbatim)}{_date_label(d)} spans={','.join(d.span_ids)}"
        + f" quote={_q(d.source_quote)}"
        for d in demands
    ]  # fmt: skip


def _transcript_lines(pages: Sequence[PageText]) -> list[str]:
    lines: list[str] = []
    for page in pages:
        lines.append(f"--- page {page.page} ---")
        for b in page.blocks:
            text = " ".join(b.text.split())
            if text.startswith(("===", "---")):
                text = " " + text
            lines.append(f"[{b.id}] {text}")
    return lines


def render_context(
    ctx: AnalysisContext,
    *,
    glossary: bool = True,
    plan: bool = True,
    unverified: bool = True,
    pages: int | None = None,
) -> str:
    """AI_PROMPTS §5.4.3 text (English labels; target-language text kept as stored)."""
    u = ctx.urgency
    kept_pages = ctx.original_text if pages is None else ctx.original_text[:pages]
    plan_text = " | ".join(
        f"{s.id} {s.kind.value}" + (f" ({s.demand_id})" if s.demand_id else "") + f" {_q(s.text)}"
        for s in ctx.plan_steps
    )  # fmt: skip
    flags = " | ".join(f"{f.kind.value} {_q(f.text)}" for f in ctx.red_flags)
    gloss = " | ".join(f"{_q(g.term_as_written)} — {_q(g.explanation)}" for g in ctx.glossary)
    lines = [
        "=== BEGIN PAPER CONTEXT ===",
        f"PAPER: type={ctx.document_type.value} category={ctx.category.value} "
        f"language={ctx.detected_language} sender={_q(ctx.sender_as_written or 'none')}",
        f"URGENCY: level={u.level.value} nearest_date={u.nearest_date_iso or 'none'} "
        f"days_until={u.days_until if u.days_until is not None else 'none'} "
        f"driving={u.driving_demand_id or 'none'}",
        f"SUMMARY (en): {_q(ctx.summary.body_en)}",
        f"SUMMARY (target): {_q(ctx.summary.body)}",
        "DEMANDS (verified):",
        *_demand_lines(ctx.demands),
    ]
    if unverified:
        lines += ["DEMANDS (not confirmed on the page):", *_demand_lines(ctx.unverified)]
    if plan:
        lines.append(f"PLAN: {plan_text or '(none)'}")
    lines.append(f"RED FLAGS: {flags or '(none)'}")
    if glossary:
        lines.append(f"GLOSSARY: {gloss or '(none)'}")
    lines += ["TRANSCRIPT:", *_transcript_lines(kept_pages), "=== END PAPER CONTEXT ==="]
    return "\n".join(lines)


def compact_context(ctx: AnalysisContext, limit: int = MAX_CONTEXT_CHARS) -> str:
    """Drop glossary, then plan, then unverified items, then transcript pages from the last page
    backwards until the text fits ``limit`` (the client already cut oldest pages)."""
    options: dict[str, bool] = {"glossary": True, "plan": True, "unverified": True}
    text = render_context(ctx, **options)
    for name in ("glossary", "plan", "unverified"):
        if len(text) <= limit:
            return text
        options[name] = False
        text = render_context(ctx, **options)
    pages = len(ctx.original_text)
    while len(text) > limit and pages > 0:
        pages -= 1
        text = render_context(ctx, pages=pages, **options)
    return text[:limit]


def render_history(req: ChatRequest, max_turns: int) -> str:
    turns = req.messages[-max_turns:] if max_turns else []
    if not turns:
        return prompt.NONE_TEXT
    return "\n".join(
        f"{'USER' if m.role == 'user' else 'ASSISTANT'}: {prompt.untrusted(m.text, 1000)}"
        for m in turns
    )


def grounded_quotes(ctx: AnalysisContext, span_ids: Sequence[str]) -> list[Quote]:
    """Quotes for the ids that exist in ``original_text`` (unknown ids dropped, order kept)."""
    blocks = {b.id: b for page in ctx.original_text for b in page.blocks}
    out: list[Quote] = []
    for sid in dict.fromkeys(span_ids):
        block = blocks.get(sid)
        if block is not None:
            out.append(Quote(span_id=sid, text=block.text, page=block.page))
    return out


# Sentence ends kept with the sentence (Latin, Arabic/Urdu, Devanagari and CJK full stops).
_ENDS = ".!?؟۔।。！？"
_SENTENCE_RE = re.compile(rf"[^{_ENDS}]*(?:[{_ENDS}]+[\"'”’»)\]]*|$)")
# Case, spacing, joiners, bidi marks and punctuation do not make a sentence different.
_NOISE_RE = re.compile(rf"[\s\u200c\u200d\u200e\u200f\u2066-\u2069{_ENDS},،;:\"'“”‘’«»()\[\]…\-]+")


def _sentence_key(text: str) -> str:
    return _NOISE_RE.sub("", unicodedata.normalize("NFKC", text).casefold())


def _same_sentence(key: str, fixed_keys: Sequence[str]) -> bool:
    if key in fixed_keys:
        return True
    # A longer sentence that starts with it ("… does not say when.") says more and is kept as
    # written; a prefix of it is a different, shorter sentence. Only other spellings ("doesn't")
    # are matched by ratio, so short specific sentences never lose their information.
    if any(key.startswith(fixed) or fixed.startswith(key) for fixed in fixed_keys):
        return False
    return any(
        len(key) <= 2 * len(fixed)
        and difflib.SequenceMatcher(None, key, fixed).ratio() >= SAME_SENTENCE_RATIO
        for fixed in fixed_keys
    )


def with_not_in_document(answer: str, fixed: str, *variants: str) -> str:
    """``answer`` carrying the fixed "The paper does not say." sentence exactly once.

    The fixed sentence is the target pack's ``chat.not_in_document``; ``variants`` (the English
    sentence) are other spellings the model or the mock may have used. A sentence of the answer
    that is the same sentence (exact after normalising case, spacing, joiners and punctuation, or
    a near spelling such as "doesn't") is replaced in place by ``fixed``; further copies are
    dropped; a sentence that merely starts with it ("The paper does not say who …") counts as
    saying it and is kept as written. When no sentence says it, ``fixed`` is put first. The client
    renders ``answer`` as is and no longer appends the key itself (one source of truth)."""
    fixed = " ".join(fixed.split())
    keys = [k for k in dict.fromkeys(_sentence_key(s) for s in (fixed, *variants)) if k]
    out: list[str] = []
    said = False
    for match in _SENTENCE_RE.finditer(answer):
        chunk = match.group(0)
        if not chunk:
            continue
        key = _sentence_key(chunk)
        if key and _same_sentence(key, keys):
            if not said:
                out.append(chunk[: len(chunk) - len(chunk.lstrip())] + fixed)
                said = True
            continue
        if key and any(key.startswith(k) for k in keys):
            said = True
        out.append(chunk)
    text = "".join(out).strip()
    if not said:
        text = f"{fixed} {text}".strip()
    return re.sub(r"[ \t]{2,}", " ", text)


async def run_chat(req: ChatRequest, deps: PipelineDeps) -> ChatAnswer:
    started = time.perf_counter()
    deadline_at = deps.ai.request_deadline()
    ctx = req.analysis
    target = req.target_language
    t = translator(deps, target)
    # A sample paper's context carries dates computed as of DEMO_AS_OF; the prompt's "today" must
    # agree with them (demo/as_of.py).
    today = analysis_today(deps.clock(), None, sample=bool(req.demo_sample_id))
    vars = {
        **prompt_base_vars(deps, target_language=target, today=today),
        "analysis_context": compact_context(ctx),
        "history": render_history(req, deps.settings.max_chat_history),
        "question": prompt.untrusted(req.question, 1000),
    }
    # The mock answers from the structured context (AI_PROMPTS §10.1); Gemini gets the text only.
    lead = [Part.of_text(ctx.model_dump_json())] if deps.ai.provider.name is Provider.mock else []
    outcome = await generate(
        deps, Task.chat, [], vars, deadline_at=deadline_at, lead=lead,
        hints=hints_for(
            demo_sample_id=req.demo_sample_id, target_language=target, question=req.question
        ),
    )  # fmt: skip
    out = parsed_as(outcome, ChatModelOut)
    warnings: list[WarningCode] = list(outcome.warnings)

    # Grounding check (replaces span verification for chat).
    quotes = grounded_quotes(ctx, out.grounded_span_ids)

    # Contact scrubber: contacts printed on the paper may be quoted; nothing else.
    paper_text = "\n".join(b.text for page in ctx.original_text for b in page.blocks)
    scrubber = contacts_filter.make_scrubber(paper_text, deps.resources.names(), t)
    answer = scrubber.scrub(out.answer)
    suggested = [q for q in scrubber.scrub_all(out.suggested_questions[:MAX_SUGGESTED]) if q]

    # Phrasing lint: the answer is information, never advice.
    refusal, refer = out.refusal_kind, out.refer_to_professional
    rewrite = make_rewriter(
        deps, language=target, today=today, budget=RewriteBudget(), deadline_at=deadline_at
    )
    linted = await phrasing.enforce(
        answer, t=t, category=ctx.category, language=target, rewrite=rewrite
    )
    answer = linted.text
    warnings.extend(linted.warnings)
    if linted.hedged and refusal is RefusalKind.none:
        refusal = phrasing.refusal_kind_for(linted.families)

    # Typed instructions to the model + an answer that failed lint → the fixed refusal.
    typed = [req.question, *(m.text for m in req.messages if m.role == "user")]
    if injection.text_has_injection(typed) and linted.replacements:
        refusal = RefusalKind.out_of_scope
        answer = t("chat.refusal.out_of_scope")
        quotes = []
    # An answer that rests on no block of the paper is "not in the document" (a refusal may
    # legitimately cite nothing); ids that do not exist were dropped above.
    dropped_all = bool(out.grounded_span_ids) and not quotes
    not_in_document = (
        out.not_in_document or dropped_all or (not quotes and refusal is RefusalKind.none)
    )
    # The fixed sentence exactly once, for the mock and for Gemini alike; a refusal speaks through
    # its own fixed template instead (rendered by the client from ``refusal_kind``).
    if not_in_document and refusal is RefusalKind.none:
        answer = with_not_in_document(
            answer, t(NOT_IN_DOCUMENT_KEY), english(deps)(NOT_IN_DOCUMENT_KEY)
        )
    if refusal is RefusalKind.medical_interpretation:
        refer = ReferTo.clinician
    elif refusal in REFER_REQUIRED and refer is ReferTo.none:
        refer = phrasing.refer_to_for(ctx.category)

    # Emergency lexicon: the reader's words and the earlier assistant turns.
    emerg = emergency.detect_emergency(
        [m.text for m in req.messages if m.role == "assistant"],
        detected_language=ctx.detected_language, target_language=target,
        user_texts=typed,
    )  # fmt: skip
    warnings += [*emerg.warnings, *scrubber.warnings()]
    tags = tagging.finalize_tags(
        out.resource_tags, document_type=DocumentType.unknown, readable=True,
        emergency=emerg.safety.emergency,
    ).tags  # fmt: skip

    demo = demo_of(deps, req.demo_sample_id)
    meta = model_meta(outcome, deps, demo=demo, latency_ms=elapsed_ms(started))
    final = disclaimers.final_warnings(
        warnings, degraded=meta.quality is ModelQuality.degraded,
        data_use_tier=meta.data_use_tier, demo=meta.demo,
    )  # fmt: skip
    return ChatAnswer(
        request_id=deps.request_id,
        answer=answer,
        grounded_span_ids=[q.span_id for q in quotes],
        grounded_quotes=quotes,
        not_in_document=not_in_document,
        refusal_kind=refusal,
        refer_to_professional=refer,
        distress_acknowledged=out.distress_acknowledged,
        suggested_questions=suggested,
        resource_tags=tags,
        safety=emerg.safety,
        disclaimer_kind=disclaimers.disclaimer_kind(ctx.category),
        warnings=final,
        model_meta=meta,
    )
