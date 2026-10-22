"""``analysis/compat_runtime`` — the ``openai_compat`` runtime adjustments of the pipeline
(LOCAL_AI.md §5; AI_PROMPTS §9.4, §11.9): the two-call fallback only when it can finish, a
same-language paper as its own translation, and one phrasing rewrite per sentence per request.
The fixture-backed mock plays the model (reporting as ``openai_compat`` or ``gemini``) and an
injected clock stands in for a slow local model. No network, no model."""

import json
import logging
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from proxyhealth_api.ai.failover import AIService
from proxyhealth_api.ai.mock import MockProvider
from proxyhealth_api.ai.provider import StructuredResult, Task, Usage
from proxyhealth_api.analysis import compat_runtime, phrasing, transcript
from proxyhealth_api.analysis.pipeline import (
    MAX_REWRITE_CALLS,
    PipelineDeps,
    RewriteBudget,
    make_rewriter,
    run_analysis,
)
from proxyhealth_api.contracts.analysis import AnalysisResult, AnalyzeRequest
from proxyhealth_api.contracts.common import TextBlock, TranslatedPage
from proxyhealth_api.contracts.enums import AnalysisMode, Provider, WarningCode
from proxyhealth_api.contracts.model_out import AnalysisModelOut, RewriteOut
from proxyhealth_api.demo.fixtures import FixtureStore
from proxyhealth_api.errors import ApiError
from proxyhealth_api.resources.loader import ResourceRepo
from proxyhealth_api.resources.rules_repo import RulesRepo
from proxyhealth_api.settings import DATA_DIR, Settings
from tests.conftest import FROZEN_NOW, make_settings

STORE = FixtureStore.load(DATA_DIR / "fixtures")
RESOURCES = ResourceRepo.load(DATA_DIR / "resources")
RULES = RulesRepo.load(DATA_DIR / "rules")
MEDICAID = "medicaid_address_confirmation"
BANNER = "SAMPLE — synthetic document. Not a real letter."
Override = Callable[[dict[str, Any]], BaseModel | StructuredResult | None]


class Clock:
    def __init__(self) -> None:
        self.now = FROZEN_NOW

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class Scripted(MockProvider):
    """The fixture mock under another provider name, with per-task overrides and a call log."""

    def __init__(self, settings: Settings, name: Provider, **overrides: Override) -> None:
        super().__init__(STORE, settings)
        self.name = name
        self.overrides = {Task(k): v for k, v in overrides.items()}
        self.tasks: list[Task] = []

    async def generate_structured(self, **kwargs: Any) -> StructuredResult:
        self.tasks.append(kwargs["task"])
        override = self.overrides.get(kwargs["task"])
        value = override(kwargs) if override is not None else None
        if isinstance(value, StructuredResult):
            return value
        if value is not None:
            return StructuredResult(value, None, "fake", Usage(), finish_reason="stop")
        return await super().generate_structured(**kwargs)


def local(tmp_path: Path) -> Settings:
    return make_settings(
        tmp_path, ai_provider="openai_compat", openai_compat_data_tier="local",
        openai_compat_model_label="Qwen",
    )  # fmt: skip


def hosted(tmp_path: Path) -> Settings:
    return make_settings(
        tmp_path, ai_provider="openai_compat", openai_compat_data_tier="unpaid",
        openai_compat_vendor_name="Groq", openai_compat_api_key="sk-test-0001",
        openai_compat_base_url="https://api.groq.com/openai/v1",
    )  # fmt: skip


def deps_for(settings: Settings, provider: Scripted, clock: Clock) -> PipelineDeps:
    return PipelineDeps(
        settings=settings, ai=AIService(provider, None, settings, clock=clock),
        resources=RESOURCES, rules=RULES, fixtures=STORE, request_id="rt-test",
        data_use_tier=settings.data_use_tier, clock=clock,
    )  # fmt: skip


def medicaid_out(**update: Any) -> AnalysisModelOut:
    out = STORE.get(MEDICAID).analysis_out("en")  # type: ignore[union-attr]
    assert out is not None
    return out.model_copy(update=update, deep=True)


def demo_request() -> AnalyzeRequest:
    return AnalyzeRequest(
        pages=[], target_language="en", client_platform="web", demo_sample_id=MEDICAID
    )


def incomplete_after(clock: Clock, seconds: float) -> Override:
    def reply(_: dict[str, Any]) -> StructuredResult:
        clock.advance(seconds)  # the local model wrote until max_tokens cut it off
        return StructuredResult(None, None, "fake", Usage(), finish_reason="length",
                                incomplete=True)  # fmt: skip

    return reply


# --------------------------------------------------------- two-call fallback budget (§9.4)


async def test_cut_off_late_on_loopback_skips_the_fallback_with_ai_too_slow(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock = Clock()
    provider = Scripted(local(tmp_path), Provider.openai_compat,
                        analyze_single=incomplete_after(clock, 250))  # fmt: skip
    with caplog.at_level(logging.INFO, logger="proxyhealth"):
        with pytest.raises(ApiError) as info:
            await run_analysis(demo_request(), deps_for(local(tmp_path), provider, clock))
    err = info.value
    assert (err.status, err.code.value, err.user_message_key) == (
        502, "model_output_invalid", "err.ai_too_slow",
    )  # fmt: skip
    assert err.details == {"reason": "incomplete"}
    assert provider.tasks == [Task.analyze_single]  # no transcribe was started
    lines = [json.loads(r.getMessage()) for r in caplog.records if "fallback" in r.getMessage()]
    assert [(e["route"], e["error_code"]) for e in lines] == [
        ("analysis.mode_fallback_skipped", "fallback_budget")
    ]
    assert set(lines[0]) == {"ts", "request_id", "route", "error_code", "provider"}


async def test_cut_off_early_on_loopback_still_runs_the_two_call_fallback(tmp_path: Path) -> None:
    clock = Clock()
    provider = Scripted(local(tmp_path), Provider.openai_compat,
                        analyze_single=incomplete_after(clock, 100))  # fmt: skip
    res = await run_analysis(demo_request(), deps_for(local(tmp_path), provider, clock))
    assert provider.tasks[:3] == [Task.analyze_single, Task.transcribe, Task.explain]
    assert res.model_meta.analysis_mode is AnalysisMode.two_call


@pytest.mark.parametrize("which", ["gemini", "hosted_openai_compat"])
async def test_fast_providers_keep_the_fallback_however_late(tmp_path: Path, which: str) -> None:
    clock = Clock()
    if which == "gemini":
        settings, name = make_settings(tmp_path), Provider.gemini
    else:
        settings, name = hosted(tmp_path), Provider.openai_compat
    provider = Scripted(settings, name, analyze_single=incomplete_after(clock, 250))
    res = await run_analysis(demo_request(), deps_for(settings, provider, clock))
    assert provider.tasks[:3] == [Task.analyze_single, Task.transcribe, Task.explain]
    assert res.model_meta.analysis_mode is AnalysisMode.two_call


# ------------------------------------------------------- same-language translation (§11.11)


def page_text(res: AnalysisResult, page: int = 1) -> str:
    return "\n".join(b.text for b in res.original_text[page - 1].blocks)


async def run_with(settings: Settings, name: Provider, out: AnalysisModelOut) -> AnalysisResult:
    provider = Scripted(settings, name, analyze_single=lambda _: out)
    return await run_analysis(demo_request(), deps_for(settings, provider, Clock()))


async def test_same_language_stub_becomes_the_transcript_on_openai_compat(tmp_path: Path) -> None:
    # The sweep's stub: one line of the page (there, the sample banner the model transcribed).
    stub = medicaid_out().blocks[0].text.split("\n")[0]
    out = medicaid_out(translated_pages=[TranslatedPage(page=1, text=stub)])
    res = await run_with(local(tmp_path), Provider.openai_compat, out)
    assert [p.page for p in res.translated_text] == [1]
    assert res.translated_text[0].text == page_text(res)
    assert WarningCode.translation_partial not in res.warnings
    # Leaving translated_pages empty (what the prompt may ask for) gives the same copy.
    empty = await run_with(local(tmp_path), Provider.openai_compat,
                           medicaid_out(translated_pages=[]))  # fmt: skip
    assert empty.translated_text == res.translated_text
    assert WarningCode.translation_partial not in empty.warnings


async def test_a_real_rewrite_is_kept_and_still_scrubbed(tmp_path: Path) -> None:
    fx_out = medicaid_out()
    words = len(" ".join(p.text for p in fx_out.translated_pages).split())
    rewrite = " ".join(["Confirme su dirección pronto."] * max(words // 4, 1))
    rewrite += " Llame al 703-555-0142 hoy."  # a number the paper does not print
    out = medicaid_out(translated_pages=[TranslatedPage(page=1, text=rewrite)])
    res = await run_with(local(tmp_path), Provider.openai_compat, out)
    text = res.translated_text[0].text
    assert text.startswith("Confirme su dirección") and "703-555-0142" not in text


async def test_other_languages_and_other_providers_keep_the_model_text(tmp_path: Path) -> None:
    stub = [TranslatedPage(page=1, text=BANNER)]
    spanish = medicaid_out(detected_language="es", translated_pages=stub)
    res = await run_with(local(tmp_path), Provider.openai_compat, spanish)
    assert res.translated_text[0].text == BANNER
    gemini = await run_with(make_settings(tmp_path), Provider.gemini,
                            medicaid_out(translated_pages=stub))  # fmt: skip
    assert gemini.translated_text[0].text == BANNER


def test_same_language_pages_unit_rules(tmp_path: Path) -> None:
    out = medicaid_out()
    paper = transcript.assemble_transcript(out.blocks, pages_received=1)
    text = "\n".join(b.text for b in paper.pages[0].blocks)
    settings = local(tmp_path)

    def pages_for(model: list[TranslatedPage], detected: str = "en") -> list[TranslatedPage]:
        o = out.model_copy(update={"translated_pages": model})
        return compat_runtime.same_language_pages(
            settings, o, paper, detected=detected, target="en-US"
        ).translated_pages

    lines = text.split("\n")
    copy = [TranslatedPage(page=1, text=text)]
    assert pages_for([TranslatedPage(page=1, text=lines[0])]) == copy  # a stub: the first line
    assert pages_for([TranslatedPage(page=1, text=lines[-1][:30])]) == copy  # a cut-off line
    assert pages_for([TranslatedPage(page=1, text=text.upper() + " x")]) == copy  # a re-typed copy
    merged = " ".join(lines[:3]) + "\n" + "\n".join(lines[3:]).replace("2026", "2O26", 1)
    assert pages_for([TranslatedPage(page=1, text=merged)]) == copy  # lines joined, a digit slip
    assert pages_for([]) == copy  # nothing written
    # Words the page does not have are never discarded: a note is the model's own text.
    note = [TranslatedPage(page=1, text="This letter is already in English.")]
    assert pages_for(note) == note
    extra = TranslatedPage(page=7, text="a page the paper does not have")
    assert pages_for([extra]) == [*copy, extra]
    assert pages_for([TranslatedPage(page=1, text=BANNER)], detected="es") == [
        TranslatedPage(page=1, text=BANNER)
    ]
    mock = make_settings(tmp_path)
    o = out.model_copy(update={"translated_pages": []})
    assert compat_runtime.same_language_pages(mock, o, paper, detected="en", target="en") is o


LEASE_ES = [
    "CONTRATO DE ARRENDAMIENTO RESIDENCIAL",
    "Inquilino: Maria Lopez. Propietario: Casa Verde LLC.",
    "La renta mensual es de 1.200 dolares, pagadera el primer dia de cada mes.",
    "El inquilino debe mantener la vivienda limpia y en buen estado.",
]
NOTICE_EN = (
    "NOTICE: Your lease ends on November 30, 2026. You must move out or sign a renewal by "
    "November 15, 2026."
)
NOTICE_ES = (
    "AVISO: Su contrato termina el 30 de noviembre de 2026. Debe mudarse o firmar una renovacion "
    "antes del 15 de noviembre de 2026."
)
LETTER_EN = [
    "Fairfax County Department of Family Services",
    "Your SNAP interview is on November 4, 2026 at 10:00 AM.",
    "If you cannot come, call us before that day to change the time.",
    "Bring proof of income for the last 30 days.",
]


def bilingual(lines: list[str]) -> transcript.Transcript:
    blocks = [
        TextBlock(id=f"b{i}", page=1, text=t, bbox=None, is_handwriting=False, is_unclear=False)
        for i, t in enumerate(lines, 1)
    ]  # fmt: skip
    return transcript.assemble_transcript(blocks, pages_received=1)


@pytest.mark.parametrize(
    ("target", "page", "model", "translated", "foreign"),
    [
        # A Spanish lease with an English deadline notice, read in Spanish.
        ("es", [*LEASE_ES, NOTICE_EN], [*LEASE_ES, NOTICE_ES], NOTICE_ES, NOTICE_EN),
        # An English letter with a Spanish passage, read in English (the mirror case).
        ("en", [*LETTER_EN[:2], NOTICE_ES, *LETTER_EN[2:]],
         [*LETTER_EN[:2], NOTICE_EN, *LETTER_EN[2:]], NOTICE_EN, NOTICE_ES),
    ],
)  # fmt: skip
def test_bilingual_page_keeps_the_translated_passage(
    tmp_path: Path, target: str, page: list[str], model: list[str], translated: str, foreign: str
) -> None:
    paper = bilingual(page)
    out = medicaid_out(translated_pages=[TranslatedPage(page=1, text="\n".join(model))])
    res = compat_runtime.same_language_pages(
        local(tmp_path), out, paper, detected=target, target=target
    ).translated_pages
    assert len(res) == 1 and translated in res[0].text.split("\n")
    assert foreign not in res[0].text  # the passage is not shown untranslated
    assert res[0].text.split("\n") == model  # the copied lines are the transcript's own
    # Copied lines the model re-typed with a slip come back as the transcript's lines.
    slipped = [model[0].upper(), re.sub(r"(\w+)(\W*)$", r"\1s\2", model[1]), *model[2:]]
    assert slipped[1] != model[1]
    out = medicaid_out(translated_pages=[TranslatedPage(page=1, text="\n".join(slipped))])
    res = compat_runtime.same_language_pages(
        local(tmp_path), out, paper, detected=target, target=target
    ).translated_pages
    assert res[0].text.split("\n") == model


async def test_bilingual_page_through_the_pipeline_has_no_partial_warning(tmp_path: Path) -> None:
    fx = medicaid_out()
    blocks = [*fx.blocks, fx.blocks[-1].model_copy(update={"id": "b-es", "text": NOTICE_ES})]
    page = [ln for b in fx.blocks for ln in b.text.split("\n") if ln.strip()]
    model = "\n".join([*page, NOTICE_EN])
    out = medicaid_out(blocks=blocks, translated_pages=[TranslatedPage(page=1, text=model)])
    res = await run_with(local(tmp_path), Provider.openai_compat, out)
    text = res.translated_text[0].text
    assert NOTICE_EN in text and NOTICE_ES not in text
    assert WarningCode.translation_partial not in res.warnings


# ---------------------------------------------------------- one rewrite per sentence (§11.9)


def rewrite_deps(settings: Settings, name: Provider, results: list[str | None]) -> tuple[
    PipelineDeps, Scripted
]:  # fmt: skip
    def reply(_: dict[str, Any]) -> StructuredResult:
        value = results.pop(0)
        parsed = RewriteOut(sentence=value) if value is not None else None
        return StructuredResult(parsed, None, "fake", Usage(), finish_reason="stop",
                                incomplete=parsed is None)  # fmt: skip

    provider = Scripted(settings, name, phrasing_rewrite=reply)
    return deps_for(settings, provider, Clock()), provider


async def test_memo_asks_once_per_sentence_language_and_professional(tmp_path: Path) -> None:
    deps, provider = rewrite_deps(local(tmp_path), Provider.openai_compat,
                                  ["The paper says to reply.", None, "B.", "C."])  # fmt: skip
    budget = RewriteBudget()
    today = FROZEN_NOW.date()
    target = make_rewriter(deps, language="en-US", today=today, budget=budget, deadline_at=None)
    english = make_rewriter(deps, language="en", today=today, budget=budget, deadline_at=None)
    assert await target("You should reply.", "a lawyer") == "The paper says to reply."
    assert await english(" You should reply. ", "a lawyer") == "The paper says to reply."
    assert budget.calls == 1 and budget.remaining == MAX_REWRITE_CALLS - 1
    assert await target("You must pay.", "a lawyer") is None  # failed → hedge
    assert await english("You must pay.", "a lawyer") is None  # remembered, not retried
    assert await target("You should reply.", "a doctor") == "B."  # another professional
    spanish = make_rewriter(deps, language="es", today=today, budget=budget, deadline_at=None)
    assert await spanish("You should reply.", "a lawyer") == "C."  # another language
    assert provider.tasks.count(Task.phrasing_rewrite) == 4 and budget.calls == 4


async def test_no_memo_for_other_providers(tmp_path: Path) -> None:
    deps, provider = rewrite_deps(make_settings(tmp_path), Provider.gemini, ["A.", "A."])
    budget = RewriteBudget()
    rewrite = make_rewriter(deps, language="en", today=FROZEN_NOW.date(), budget=budget,
                            deadline_at=None)  # fmt: skip
    await rewrite("You should reply.", "a lawyer")
    await rewrite("You should reply.", "a lawyer")
    assert provider.tasks.count(Task.phrasing_rewrite) == 2 and budget.memo == {}


async def test_english_summary_and_body_en_share_their_rewrites(tmp_path: Path) -> None:
    body = "You should appeal within 180 days. You must pay the fee."
    category = medicaid_out().category
    assert len(phrasing.lint_text(body, category=category, language="en")) == 2
    out = medicaid_out(summary_body=body, summary_body_en=body)
    provider = Scripted(
        local(tmp_path), Provider.openai_compat, analyze_single=lambda _: out,
        phrasing_rewrite=lambda kw: RewriteOut(sentence="The paper asks for a reply."),
    )  # fmt: skip
    await run_analysis(demo_request(), deps_for(local(tmp_path), provider, Clock()))
    assert provider.tasks.count(Task.phrasing_rewrite) == 2  # not 4
