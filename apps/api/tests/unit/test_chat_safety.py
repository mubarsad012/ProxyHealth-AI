"""Phase 2C — chat safety, server-rebuilt sample context, printed forms (D-14, D-01, D-26).

* ``ChatAnswer.safety`` comes from the deterministic emergency lexicon over what the reader typed
  (the question and their earlier turns, every bundled language) — never from the model alone.
* A chat about a sample paper (known ``demo_sample_id``) ignores the client's context: the server
  rebuilds it from the fixture's recorded output in the request language.
* Dates the paper prints keep their printed spelling in the answer; digits stay Western.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from proxyhealth_api.ai.failover import AIService
from proxyhealth_api.ai.provider import StructuredResult, Task, Usage
from proxyhealth_api.analysis import chat_pipeline as cp
from proxyhealth_api.analysis import phrasing
from proxyhealth_api.analysis.pipeline import PipelineDeps, run_analysis, translator
from proxyhealth_api.contracts.analysis import AnalyzeRequest, RedFlag
from proxyhealth_api.contracts.chat import AnalysisContext, ChatAnswer, ChatMessage, ChatRequest
from proxyhealth_api.contracts.common import PageText, TextBlock
from proxyhealth_api.contracts.enums import (
    DocumentCategory,
    Provider,
    RedFlagKind,
    ReferTo,
    RefusalKind,
    ResourceTag,
    ScamRisk,
    Severity,
)
from proxyhealth_api.contracts.model_out import ChatModelOut
from proxyhealth_api.errors import ApiError
from tests.golden._fixtures_wp7 import STORE, CountingMock, build_deps, fixture

MEDICAID = "medicaid_address_confirmation"
CONTEXT_FIELDS = tuple(AnalysisContext.model_fields)
Script = Callable[[dict[str, Any]], BaseModel | StructuredResult | None]


class ScriptedChat(CountingMock):
    """Reports as ``gemini``; ``chat`` returns what ``script`` builds (else the mock), and
    ``phrasing_rewrite`` what ``rewrite`` builds when one is given."""

    name = Provider.gemini

    def __init__(self, script: Script, deps: PipelineDeps, rewrite: Script | None = None) -> None:
        super().__init__(STORE, deps.settings)
        self.script = script
        self.rewrite_script = rewrite  # ``rewrite`` is the mock's own method
        self.seen: list[dict[str, Any]] = []

    async def generate_structured(self, **kwargs: Any) -> StructuredResult:
        self.seen.append(kwargs)
        scripted = {Task.chat: self.script, Task.phrasing_rewrite: self.rewrite_script}
        script = scripted.get(kwargs["task"])
        if script is not None:
            value = script(kwargs)
            if isinstance(value, StructuredResult):
                return value
            if value is not None:
                return StructuredResult(value, None, "fake", Usage(), finish_reason="STOP")
        return await super().generate_structured(**kwargs)


def plain_answer(answer: str = "The paper asks you to confirm your address.") -> ChatModelOut:
    """An ordinary grounded answer with no ``crisis`` tag: only the lexicon can set safety."""
    return ChatModelOut(
        answer=answer, grounded_span_ids=["p1b7"], not_in_document=False,
        refusal_kind=RefusalKind.none, refer_to_professional=ReferTo.none,
        distress_acknowledged=False, suggested_questions=[], resource_tags=[],
    )  # fmt: skip


def blocked(_: dict[str, Any]) -> StructuredResult:
    return StructuredResult(None, None, "fake", Usage(), finish_reason="SAFETY",
                            blocked_reason="SAFETY")  # fmt: skip


async def context(tmp_path: Path, lang: str = "en") -> tuple[PipelineDeps, AnalysisContext]:
    deps, _ = build_deps(fixture(MEDICAID), tmp_path)
    req = AnalyzeRequest(
        pages=[], target_language=lang, client_platform="web", demo_sample_id=MEDICAID
    )
    result = (await run_analysis(req, deps)).model_dump()
    return deps, AnalysisContext.model_validate({k: result[k] for k in CONTEXT_FIELDS})


async def ask(
    tmp_path: Path,
    question: str,
    *,
    lang: str = "en",
    script: Script = lambda kw: plain_answer(),
    analysis: AnalysisContext | None = None,
    rewrite: Script | None = None,
    **extra: Any,
) -> tuple[ChatAnswer, ScriptedChat]:
    deps, ctx = await context(tmp_path, lang)
    provider = ScriptedChat(script, deps, rewrite)
    deps.ai = AIService(provider, None, deps.settings)
    req = ChatRequest(analysis=analysis or ctx, question=question, target_language=lang, **extra)
    return await cp.run_chat(req, deps), provider


def prompt_text(provider: ScriptedChat) -> str:
    call = next(c for c in provider.seen if c["task"] is Task.chat)
    return "\n".join([call["system"], *(p.text or "" for p in call["parts"])])


# ---------------------------------------------------------------------------- safety (D-14)

DISTRESS = [
    ("en", "I have chest pain and cannot breathe", ["chest_pain", "breathing"]),
    ("en", "My son swallowed bleach, should I call poison control?", ["poison"]),
    ("en", "I want to kill myself", ["self_harm"]),
    ("es", "Me duele mucho el pecho y no puedo respirar", ["chest_pain", "breathing"]),
    ("es", "Me quiero suicidar", ["self_harm"]),
    ("es", "Mi esposo me pega", ["violence"]),
    ("ar", "أشعر بألم في صدري ولا أستطيع التنفس", ["chest_pain", "breathing"]),
    ("ar", "أريد أن أنتحر", ["self_harm"]),
    ("ar", "ابني شرب الكلور", ["poison"]),
    ("ar", "زوجي يضربني", ["violence"]),
    ("prs", "درد قفسه سینه دارم و نفس کشیده نمی‌توانم", ["chest_pain", "breathing"]),
    ("prs", "می‌خواهم خودم را بکشم", ["self_harm"]),
    ("prs", "شوهرم مرا لت و کوب می‌کند", ["violence"]),
]
ORDINARY = [
    ("en", "When do I have to send the form?"),
    ("es", "¿Cuándo tengo que mandar el papel?"),
    ("ar", "متى يجب أن أرسل الورقة؟"),
    ("ar", "كل الأوراق جاهزة، هل أرسلها بالبريد؟"),
    ("prs", "چه وقت باید کاغذ را بفرستم؟"),
    ("prs", "کدام مدارک را بیاورم؟"),
]


@pytest.mark.parametrize(("lang", "question", "kinds"), DISTRESS)
async def test_distress_question_sets_safety_with_the_right_kinds(
    lang: str, question: str, kinds: list[str], tmp_path: Path
) -> None:
    ans, _ = await ask(tmp_path, question, lang=lang)
    assert ans.safety.emergency is True, (lang, question)
    assert ans.safety.emergency_kinds == kinds, (lang, question)
    assert ans.resource_tags[:1] == [ResourceTag.crisis]


@pytest.mark.parametrize(("lang", "question"), ORDINARY)
async def test_ordinary_question_has_no_emergency(
    lang: str, question: str, tmp_path: Path
) -> None:
    ans, _ = await ask(tmp_path, question, lang=lang)
    assert ans.safety.emergency is False and ans.safety.emergency_kinds == []
    assert ResourceTag.crisis not in ans.resource_tags


async def test_distress_in_an_earlier_user_turn_still_counts(tmp_path: Path) -> None:
    history = [
        ChatMessage(role="user", text="أريد أن أنتحر"),
        ChatMessage(role="assistant", text="أنا آسف. الورقة تطلب تأكيد العنوان."),
    ]
    ans, _ = await ask(tmp_path, "متى يجب أن أرسل الورقة؟", lang="ar", messages=history)
    assert ans.safety.emergency is True and ans.safety.emergency_kinds == ["self_harm"]


async def test_assistant_turns_drop_printed_help_line_names(tmp_path: Path) -> None:
    """``exclude`` phrases are removed from quoted/printed text only, never from user words."""
    said = "The label says: if swallowed, call Poison Help."
    history = [ChatMessage(role="assistant", text=said)]
    ans, _ = await ask(tmp_path, "What does the label ask me to do?", messages=history)
    assert ans.safety.emergency is False


async def test_the_model_crisis_tag_is_a_backstop_without_kinds(tmp_path: Path) -> None:
    out = plain_answer().model_copy(update={"resource_tags": [ResourceTag.crisis]})
    ans, _ = await ask(tmp_path, "Everything is too much", script=lambda kw: out)
    assert ans.safety.emergency is True and ans.safety.emergency_kinds == []


@pytest.mark.parametrize(
    ("lang", "question", "keys"),
    [
        ("en", "I want to kill myself", ["emergency.911", "emergency.988"]),
        ("prs", "می‌خواهم خودم را بکشم", ["emergency.911", "emergency.988"]),
        ("es", "Mi hijo se tragó cloro", ["emergency.911", "emergency.poison"]),
    ],
)
async def test_a_blocked_model_call_still_answers_a_reader_in_distress(
    lang: str, question: str, keys: list[str], tmp_path: Path
) -> None:
    ans, _ = await ask(tmp_path, question, lang=lang, script=blocked)
    t = translator(build_deps(fixture(MEDICAID), tmp_path)[0], lang)
    assert ans.answer == " ".join(t(k) for k in keys)
    assert ans.safety.emergency is True and ans.resource_tags == [ResourceTag.crisis]
    assert ans.grounded_quotes == [] and ans.refusal_kind is RefusalKind.none


async def test_a_blocked_ordinary_question_is_still_an_error(tmp_path: Path) -> None:
    with pytest.raises(ApiError) as err:
        await ask(tmp_path, "When is it due?", script=blocked)
    assert err.value.status == 422


# ---------------------------------------------------------------------------- sample context


def tampered(ctx: AnalysisContext) -> AnalysisContext:
    """A client context that claims to be the sample but carries other words."""
    page = PageText(page=1, width=None, height=None, blocks=[
        TextBlock(id="p1b1", page=1, text="CLIENT-SIDE TEXT 4471 Real Street", bbox=None,
                  is_handwriting=False, is_unclear=False),
    ])  # fmt: skip
    summary = ctx.summary.model_copy(update={"body": "CLIENT SUMMARY", "body_en": "CLIENT SUMMARY"})
    return ctx.model_copy(
        update={"original_text": [page], "summary": summary, "sender_as_written": "Client Co"}
    )


async def test_sample_chat_ignores_the_client_context(tmp_path: Path) -> None:
    deps, ctx = await context(tmp_path)
    ans, provider = await ask(
        tmp_path, "When is it due?", analysis=tampered(ctx), demo_sample_id=MEDICAID
    )
    text = prompt_text(provider)
    assert "CLIENT" not in text and "4471 Real Street" not in text
    assert "by October 14, 2026" in text  # the fixture's own transcript
    assert [q.text for q in ans.grounded_quotes] == [
        "Please confirm or update your address by October 14, 2026."
    ]


async def test_without_a_sample_id_the_client_context_is_used(tmp_path: Path) -> None:
    deps, ctx = await context(tmp_path)
    _, provider = await ask(tmp_path, "When is it due?", analysis=tampered(ctx))
    assert "CLIENT-SIDE TEXT 4471 Real Street" in prompt_text(provider)


@pytest.mark.parametrize(("target", "rebuilt"), [("prs", "prs"), ("es-MX", "es"), ("vi", "en")])
async def test_sample_context_is_rebuilt_in_the_request_language(
    target: str, rebuilt: str, tmp_path: Path
) -> None:
    deps, _ = await context(tmp_path)
    ctx = await cp.sample_context(deps, MEDICAID, target)
    assert cp.sample_language(fixture(MEDICAID), target) == rebuilt
    recorded = fixture(MEDICAID).analysis_out(rebuilt)
    assert recorded is not None and ctx.summary.body_en == recorded.summary_body_en
    assert ctx.document_type is recorded.document_type and ctx.detected_language == "en"
    # Cached: the same object comes back for the same fixture, language and rules table.
    assert await cp.sample_context(deps, MEDICAID, target) is ctx


async def test_sample_context_never_calls_the_configured_model(tmp_path: Path) -> None:
    deps, _ = await context(tmp_path)
    provider = ScriptedChat(lambda kw: plain_answer(), deps)
    deps.ai = AIService(provider, None, deps.settings)
    cp._SAMPLE_CONTEXTS.clear()
    await cp.sample_context(deps, MEDICAID, "en")
    assert provider.seen == []


@pytest.mark.parametrize("bad", ["not-a-real-fixture", "portal_file_too_large"])
async def test_unknown_or_screenshot_sample_id_is_400(bad: str, tmp_path: Path) -> None:
    with pytest.raises(ApiError) as err:
        await ask(tmp_path, "When is it due?", demo_sample_id=bad)
    assert err.value.status == 400


# ---------------------------------------------------------------------------- printed forms


@pytest.mark.parametrize(
    ("lang", "model_answer", "expected"),
    [
        ("prs", "تا ۱۴ اکتبر ۲۰۲۶ آدرس خود را تأیید کنید.",
         "تا October 14, 2026 آدرس خود را تأیید کنید."),
        ("ar", "أكّد عنوانك قبل ١٤ أكتوبر ٢٠٢٦.", "أكّد عنوانك قبل October 14, 2026."),
    ],
)  # fmt: skip
async def test_chat_answer_keeps_the_printed_date(
    lang: str, model_answer: str, expected: str, tmp_path: Path
) -> None:
    ans, _ = await ask(
        tmp_path, "When is it due?", lang=lang, script=lambda kw: plain_answer(model_answer)
    )
    assert ans.answer == expected


# ---------------------------------------------------------------------------- scam (TAXONOMY §6.4)

SCAM = "scam_gift_card_letter"


async def analysed(tmp_path: Path, fid: str, lang: str = "en") -> tuple[PipelineDeps, Any]:
    deps, _ = build_deps(fixture(fid), tmp_path)
    req = AnalyzeRequest(pages=[], target_language=lang, client_platform="web", demo_sample_id=fid)
    return deps, await run_analysis(req, deps)


def as_context(result: Any) -> AnalysisContext:
    return AnalysisContext.model_validate({k: getattr(result, k) for k in CONTEXT_FIELDS})


async def scam_context(tmp_path: Path, category: DocumentCategory) -> AnalysisContext:
    """The likely-scam sample's context as the client re-sends it, filed under ``category`` (a
    tax, benefits or school impersonation; the sample itself is an immigration paper)."""
    _, result = await analysed(tmp_path, SCAM)
    assert result.scam_risk is ScamRisk.likely
    return as_context(result).model_copy(update={"category": category})


def answered(
    answer: str, refusal: RefusalKind = RefusalKind.none, refer: ReferTo = ReferTo.none
) -> Script:
    out = plain_answer(answer).model_copy(
        update={"refusal_kind": refusal, "refer_to_professional": refer,
                "grounded_span_ids": ["p1b6"]}
    )  # fmt: skip
    return lambda kw: out


@pytest.mark.parametrize("category", list(DocumentCategory))
def test_no_scam_referral_points_back_at_the_paper(category: DocumentCategory) -> None:
    # The phrasing.yaml maps chat relies on: on a scam no category refers to the sender.
    for risk in (ScamRisk.possible, ScamRisk.likely):
        assert phrasing.refer_to_for(category, scam_risk=risk) not in cp.PAPER_CONTACT_REFERRALS


@pytest.mark.parametrize(
    ("category", "script"),
    [
        # review/chat_scam.py: on a likely scam filed under tax, a hedged "pay today" answer, an
        # explicit refusal and the model's own sender referral all came back ``sender``.
        (DocumentCategory.tax, answered("You should pay the amount today.")),
        (DocumentCategory.tax, answered("I cannot tell you whether to pay.",
                                        RefusalKind.filing_advice)),
        (DocumentCategory.tax, answered("I cannot tell you whether to pay.",
                                        RefusalKind.filing_advice, ReferTo.sender)),
        (DocumentCategory.benefits, answered("I cannot tell you whether to pay.",
                                             RefusalKind.filing_advice)),
        (DocumentCategory.benefits, answered("The letter asks for $950.", refer=ReferTo.sender)),
        (DocumentCategory.school, answered("The letter asks for $950.",
                                           refer=ReferTo.benefits_office)),
    ],
)  # fmt: skip
async def test_chat_never_refers_a_scam_reader_to_the_sender(
    category: DocumentCategory, script: Script, tmp_path: Path
) -> None:
    ctx = await scam_context(tmp_path, category)
    ans, _ = await ask(
        tmp_path, "Should I pay this?", script=script, analysis=ctx, rewrite=blocked
    )  # the fast tier is unavailable: a flagged sentence gets the fixed hedge
    assert ans.refer_to_professional is ReferTo.lawyer_or_accredited_rep


async def test_a_hedged_scam_answer_is_refused(tmp_path: Path) -> None:
    ctx = await scam_context(tmp_path, DocumentCategory.tax)
    ans, _ = await ask(
        tmp_path, "Should I pay this?", script=answered("You should pay the amount today."),
        analysis=ctx, rewrite=blocked,
    )  # fmt: skip
    assert ans.refusal_kind is RefusalKind.filing_advice
    assert ans.refer_to_professional is ReferTo.lawyer_or_accredited_rep
    assert "pay the amount today" not in ans.answer


async def test_the_scam_rewrite_template_names_no_sender(tmp_path: Path) -> None:
    # A benefits paper's rewrite professional is "the office that sent this paper"; on a scam it
    # is the lawyer wording, as on the analysis card (phrasing.yaml scam_professional_by_category).
    ctx = await scam_context(tmp_path, DocumentCategory.benefits)
    _, provider = await ask(
        tmp_path, "Should I pay this?", script=answered("You should pay the amount today."),
        analysis=ctx,
    )  # fmt: skip
    rewrites = [c for c in provider.seen if c["task"] is Task.phrasing_rewrite]
    assert rewrites, "the flagged sentence went to the rewriter"
    for call in rewrites:
        text = "\n".join(p.text or "" for p in call["parts"])
        assert "Professional wording to use, exactly: a licensed lawyer\n" in text
        assert "the office that sent this paper" not in text


@pytest.mark.parametrize(
    ("script", "refer"),
    [
        (answered("I cannot tell you whether you qualify.", RefusalKind.eligibility),
         ReferTo.benefits_office),
        (answered("The paper asks you to confirm your address.", refer=ReferTo.sender),
         ReferTo.sender),
    ],
)  # fmt: skip
async def test_a_genuine_paper_keeps_its_sender_referral(
    script: Script, refer: ReferTo, tmp_path: Path
) -> None:
    # The Medicaid sample scores no scam: the office that sent it is the one to ask.
    ans, _ = await ask(tmp_path, "Do I qualify?", script=script)
    assert ans.refer_to_professional is refer


async def test_context_scam_risk_agrees_with_every_sample_analysis(tmp_path: Path) -> None:
    # Every sample paper in every recorded language: the scam letter is a scam in all four; the
    # Inova bill's "FINAL NOTICE" urgency flag (model words, medium) and the fixed cards (jury,
    # NTA, pay-or-quit, I-797C) are not.
    derived: dict[str, ScamRisk] = {}
    for fx in STORE.all():
        if fx.kind != "document":
            continue
        for lang in fx.languages:
            deps, result = await analysed(tmp_path, fx.id, lang)
            reasons = cp.scorer_reason_texts(translator(deps, lang), translator(deps, "en"))
            risk = cp.context_scam_risk(as_context(result), reasons)
            assert (risk is ScamRisk.none) is (result.scam_risk is ScamRisk.none), (fx.id, lang)
            derived[f"{fx.id}/{lang}"] = risk
    assert derived[f"{SCAM}/prs"] is ScamRisk.possible
    assert derived["inova_final_notice/en"] is ScamRisk.none


def red_flag(kind: RedFlagKind, text: str, severity: Severity, key: str | None = None) -> RedFlag:
    return RedFlag(kind=kind, text=text, source_quote="Pay today.", span_ids=["p1b2"], page=1,
                   severity=severity, fixed_copy_key=key, verified=True)  # fmt: skip


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ([], ScamRisk.none),
        # A model urgency flag in its own words weighs 1 in the scorer: below ``possible``.
        ([red_flag(RedFlagKind.urgency_pressure, "It rushes you.", Severity.medium)],
         ScamRisk.none),
        # A fixed card is never scam evidence.
        ([red_flag(RedFlagKind.not_a_court_order, "Not a court order.", Severity.high,
                   "fixed.not_a_court_order")], ScamRisk.none),
        # (a) the kinds the analysis itself takes as scam evidence, at any severity.
        ([red_flag(RedFlagKind.scam_payment_method, "Asks for a wire.", Severity.medium)],
         ScamRisk.possible),
        ([red_flag(RedFlagKind.notario, "A notario.", Severity.high)], ScamRisk.possible),
        # (b) a high scorer kind: only the scorer marks urgency or contact flags high (likely).
        ([red_flag(RedFlagKind.urgency_pressure, "It rushes you.", Severity.high)],
         ScamRisk.possible),
        ([red_flag(RedFlagKind.unusual_contact, "Asks for ID numbers.", Severity.high)],
         ScamRisk.possible),
        # (c) the scorer's own flag text: "Threatens arrest" alone scores ``possible`` (medium).
        ([red_flag(RedFlagKind.urgency_pressure, "Threatens  arrest", Severity.medium)],
         ScamRisk.possible),
    ],
)  # fmt: skip
async def test_context_scam_risk_reads_the_red_flags(
    flags: list[RedFlag], expected: ScamRisk, tmp_path: Path
) -> None:
    deps, ctx = await context(tmp_path)
    reasons = cp.scorer_reason_texts(translator(deps, "en"))
    risk = cp.context_scam_risk(ctx.model_copy(update={"red_flags": flags}), reasons)
    assert risk is expected


async def test_the_scorer_text_counts_in_the_reader_language(tmp_path: Path) -> None:
    deps, ctx = await context(tmp_path, "es")
    es = translator(deps, "es")
    flags = [red_flag(RedFlagKind.urgency_pressure, es("scam.arrest_threat"), Severity.medium)]
    assert es("scam.arrest_threat") != translator(deps, "en")("scam.arrest_threat")
    scam_ctx = ctx.model_copy(update={"red_flags": flags})
    assert cp.context_scam_risk(scam_ctx, cp.scorer_reason_texts(es)) is ScamRisk.possible
    assert cp.context_scam_risk(
        scam_ctx, cp.scorer_reason_texts(translator(deps, "en"))
    ) is ScamRisk.none
