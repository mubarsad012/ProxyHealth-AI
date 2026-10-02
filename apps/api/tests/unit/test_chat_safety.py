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
from proxyhealth_api.analysis.pipeline import PipelineDeps, run_analysis, translator
from proxyhealth_api.contracts.analysis import AnalyzeRequest
from proxyhealth_api.contracts.chat import AnalysisContext, ChatAnswer, ChatMessage, ChatRequest
from proxyhealth_api.contracts.common import PageText, TextBlock
from proxyhealth_api.contracts.enums import Provider, ReferTo, RefusalKind, ResourceTag
from proxyhealth_api.contracts.model_out import ChatModelOut
from proxyhealth_api.errors import ApiError
from tests.golden._fixtures_wp7 import STORE, CountingMock, build_deps, fixture

MEDICAID = "medicaid_address_confirmation"
CONTEXT_FIELDS = tuple(AnalysisContext.model_fields)
Script = Callable[[dict[str, Any]], BaseModel | StructuredResult | None]


class ScriptedChat(CountingMock):
    """Reports as ``gemini``; ``chat`` returns what ``script`` builds (else the mock)."""

    name = Provider.gemini

    def __init__(self, script: Script, deps: PipelineDeps) -> None:
        super().__init__(STORE, deps.settings)
        self.script = script
        self.seen: list[dict[str, Any]] = []

    async def generate_structured(self, **kwargs: Any) -> StructuredResult:
        self.seen.append(kwargs)
        if kwargs["task"] is Task.chat:
            value = self.script(kwargs)
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
    **extra: Any,
) -> tuple[ChatAnswer, ScriptedChat]:
    deps, ctx = await context(tmp_path, lang)
    provider = ScriptedChat(script, deps)
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
