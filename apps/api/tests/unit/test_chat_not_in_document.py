"""A ``not_in_document`` chat answer says "The paper does not say." exactly once (POLISH item 2).

The mock and the model both write the sentence; the client used to append ``chat.not_in_document``
again. ``chat_pipeline.with_not_in_document`` is now the one source of truth: the answer carries
the target pack's fixed sentence exactly once and the client renders it as is.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from proxyhealth_api.ai.failover import AIService
from proxyhealth_api.ai.provider import StructuredResult, Task, Usage
from proxyhealth_api.analysis.chat_pipeline import run_chat, with_not_in_document
from proxyhealth_api.analysis.pipeline import PipelineDeps, run_analysis, translator
from proxyhealth_api.contracts.analysis import AnalyzeRequest
from proxyhealth_api.contracts.chat import AnalysisContext, ChatAnswer, ChatRequest
from proxyhealth_api.contracts.enums import Provider, ReferTo, RefusalKind
from proxyhealth_api.contracts.model_out import ChatModelOut
from proxyhealth_api.demo.as_of import DEMO_AS_OF
from tests.golden._fixtures_wp7 import STORE, CountingMock, build_deps, fixture

EN = "The paper does not say."
PRS = "کاغذ این را نمی\u200cگوید."
PS = "کاغذ دا نه وايي."
MEDICAID = "medicaid_address_confirmation"
CONTEXT_FIELDS = tuple(AnalysisContext.model_fields)


class ScriptedChat(CountingMock):
    """Reports as ``gemini``; ``chat`` returns what ``script`` builds (else the mock)."""

    name = Provider.gemini

    def __init__(self, script: Callable[[dict[str, Any]], BaseModel | None], deps: Any) -> None:
        super().__init__(STORE, deps.settings)
        self.script = script
        self.seen: list[dict[str, Any]] = []

    async def generate_structured(self, **kwargs: Any) -> StructuredResult:
        self.seen.append(kwargs)
        if kwargs["task"] is Task.chat:
            value = self.script(kwargs)
            if value is not None:
                return StructuredResult(value, None, "fake", Usage(), finish_reason="STOP")
        return await super().generate_structured(**kwargs)


def model_answer(answer: str, **update: Any) -> ChatModelOut:
    base = ChatModelOut(
        answer=answer, grounded_span_ids=[], not_in_document=True,
        refusal_kind=RefusalKind.none, refer_to_professional=ReferTo.none,
        distress_acknowledged=False, suggested_questions=[], resource_tags=[],
    )  # fmt: skip
    return base.model_copy(update=update)


async def deps_and_context(tmp_path: Path, lang: str) -> tuple[PipelineDeps, AnalysisContext]:
    deps, _ = build_deps(fixture(MEDICAID), tmp_path)
    req = AnalyzeRequest(
        pages=[], target_language=lang, client_platform="web", demo_sample_id=MEDICAID,
        state="VA",
    )  # fmt: skip
    result = (await run_analysis(req, deps)).model_dump()
    return deps, AnalysisContext.model_validate({k: result[k] for k in CONTEXT_FIELDS})


async def ask(
    tmp_path: Path, lang: str, question: str = "Who is the caseworker?", **extra: Any
) -> tuple[ChatAnswer, PipelineDeps]:
    script = extra.pop("script", None)
    deps, ctx = await deps_and_context(tmp_path, lang)
    if script is not None:
        deps.ai = AIService(ScriptedChat(script, deps), None, deps.settings)
    req = ChatRequest(analysis=ctx, question=question, target_language=lang, **extra)
    return await run_chat(req, deps), deps


# ---------------------------------------------------------------------------- the normaliser


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("The paper does not say. It is about: X", "The paper does not say. It is about: X"),
        ("The paper does not say. The paper does not say.", EN),
        ("The paper doesn't say.", EN),
        ("the paper does NOT say", EN),
        ("", EN),
        ("Ask the office that sent it.", "The paper does not say. Ask the office that sent it."),
        # A warm first sentence keeps its place; the fixed one replaces the model's own.
        ("I know this is hard. The paper does not say. Ask the office.",
         "I know this is hard. The paper does not say. Ask the office."),
        # A sentence that starts with it already says it (no near-duplicate is added).
        ("The paper does not say who your caseworker is.",
         "The paper does not say who your caseworker is."),
        # Short specific sentences keep their information (no ratio match on a longer prefix).
        ("The paper does not say when.", "The paper does not say when."),
        ("The paper does not say the amount.", "The paper does not say the amount."),
        ("The paper does not say the amount. The paper does not say.",
         "The paper does not say the amount."),
    ],
)  # fmt: skip
def test_english_sentence_exactly_once(answer: str, expected: str) -> None:
    assert with_not_in_document(answer, EN) == expected


def test_target_sentence_replaces_other_spellings() -> None:
    # Without the ZWNJ, and the English sentence the mock uses for untranslated languages.
    assert with_not_in_document("کاغذ این را نمیگوید. درباره X است.", PRS, EN) == (
        f"{PRS} درباره X است."
    )
    assert with_not_in_document("The paper does not say. It is about: X", PS, EN) == (
        f"{PS} It is about: X"
    )
    # A short specific Dari sentence that starts with the fixed one is kept as written.
    when = "کاغذ این را نمی‌گوید که چه وقت."
    assert with_not_in_document(when, PRS, EN) == when
    cjk = with_not_in_document("该文件没有说明。它是关于X", "文件上没有写。", EN)
    assert cjk.startswith("文件上没有写。") and cjk.count("文件上没有写。") == 1


# ---------------------------------------------------------------------------- the pipeline


@pytest.mark.parametrize(("lang", "fixed"), [("en", EN), ("prs", PRS), ("ps", PS)])
async def test_mock_answer_carries_the_pack_sentence_once(
    lang: str, fixed: str, tmp_path: Path
) -> None:
    ans, deps = await ask(tmp_path, lang)
    assert ans.not_in_document is True and ans.refusal_kind is RefusalKind.none
    assert fixed == translator(deps, lang)("chat.not_in_document")
    assert ans.answer.startswith(fixed) and ans.answer.count(fixed) == 1
    if lang != "en":
        assert EN not in ans.answer


async def test_model_repeating_the_sentence_is_collapsed(tmp_path: Path) -> None:
    ans, _ = await ask(tmp_path, "en", script=lambda kw: model_answer(f"{EN} {EN}"))
    assert ans.answer == EN


async def test_model_omitting_the_sentence_gets_it_first(tmp_path: Path) -> None:
    ans, _ = await ask(
        tmp_path, "prs", script=lambda kw: model_answer("از دفتر فرستنده بپرسید.")
    )
    assert ans.answer == f"{PRS} از دفتر فرستنده بپرسید."


async def test_grounded_answer_is_left_alone(tmp_path: Path) -> None:
    ans, _ = await ask(tmp_path, "en", "When is it due?")
    assert ans.not_in_document is False and EN not in ans.answer


async def test_refusal_speaks_through_its_template_only(tmp_path: Path) -> None:
    ans, _ = await ask(
        tmp_path, "en",
        script=lambda kw: model_answer("", refusal_kind=RefusalKind.eligibility),
    )  # fmt: skip
    assert ans.refusal_kind is RefusalKind.eligibility and ans.answer == ""


async def test_sample_chat_prompt_uses_demo_as_of(tmp_path: Path) -> None:
    ans, deps = await ask(
        tmp_path, "en", "When is it due?", demo_sample_id=MEDICAID,
        script=lambda kw: None,
    )  # fmt: skip
    provider = deps.ai.provider
    assert isinstance(provider, ScriptedChat)
    chat_call = next(c for c in provider.seen if c["task"] is Task.chat)
    text = "\n".join(p.text or "" for p in chat_call["parts"])
    assert f"Today's date: {DEMO_AS_OF.isoformat()}" in text
    assert ans.model_meta.demo is True
