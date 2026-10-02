"""Phase 2C — printed forms end to end (D-26; AI_PROMPTS §5.0 rule 7, §11.4).

A live model may write the printed "October 14, 2026" as "۱۴ اکتبر ۲۰۲۶" (Dari) or "١٤ أكتوبر ٢٠٢٦"
(Arabic): the right day, but no longer the spelling the reader can match against the paper or
show a clerk. The pipeline puts the printed spelling back in the summary, the demand text, the
plan steps and the questions (and the troubleshoot prose), and writes stray non-Western digit
runs in Western digits. Chosen over a warning: the fact is already verified; only its spelling is
restored.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from proxyhealth_api.ai.failover import AIService
from proxyhealth_api.ai.provider import StructuredResult
from proxyhealth_api.analysis.pipeline import run_analysis
from proxyhealth_api.contracts.analysis import AnalysisResult, AnalyzeRequest
from proxyhealth_api.contracts.model_out import AnalysisModelOut, ExplainOut
from proxyhealth_api.contracts.troubleshoot import TroubleshootResult
from proxyhealth_api.settings import Settings
from tests.contract.test_analyze import install
from tests.golden._fixtures_wp7 import STORE, CountingMock, build_deps, fixture

MEDICAID = "medicaid_address_confirmation"
SCREEN = "portal_file_too_large"
PRINTED = "October 14, 2026"
NON_WESTERN = {
    "prs": ("۱۴ اکتبر ۲۰۲۶", "۳۰"),
    "ar": ("١٤ أكتوبر ٢٠٢٦", "٣٠"),
}


def _localize(value: Any, date_text: str) -> Any:
    """Every printed date in a recorded model value written the way a live model might."""
    if isinstance(value, str):
        return value.replace(PRINTED, date_text)
    if isinstance(value, list):
        return [_localize(v, date_text) for v in value]
    if isinstance(value, dict):
        return {k: _localize(v, date_text) for k, v in value.items()}
    return value


class LocalizingMock(CountingMock):
    """The fixture mock, with the prose fields of the analysis output localized (digits and
    month name); quotes, ``date_text`` and ``value_verbatim`` stay as recorded."""

    PROSE = ("summary_title", "summary_body", "demands", "plan_steps", "questions_to_ask")
    KEEP_IN_DEMANDS = ("source_quote", "date_text", "time_text", "value_verbatim")

    def __init__(self, lang: str, settings: Any) -> None:
        super().__init__(STORE, settings)
        self.date_text, self.extra_digits = NON_WESTERN[lang]

    def _rewrite(self, out: BaseModel) -> BaseModel:
        data = out.model_dump()
        for name in self.PROSE:
            if name not in data:
                continue
            if name == "demands":
                data[name] = [
                    {k: (v if k in self.KEEP_IN_DEMANDS else _localize(v, self.date_text))
                     for k, v in d.items()}
                    for d in data[name]
                ]  # fmt: skip
            else:
                data[name] = _localize(data[name], self.date_text)
        # A stray localized digit run that the paper does not print (an amount of days).
        data["summary_body"] = f"{data['summary_body']} ({self.extra_digits})"
        return type(out).model_validate(data)

    async def generate_structured(self, **kwargs: Any) -> StructuredResult:
        res = await super().generate_structured(**kwargs)
        if isinstance(res.parsed, AnalysisModelOut | ExplainOut):
            res = StructuredResult(
                self._rewrite(res.parsed), res.raw_text, res.model_id, res.usage,
                res.blocked_reason, res.finish_reason, res.incomplete,
            )  # fmt: skip
        return res


async def analyze_localized(lang: str, tmp_path: Path) -> tuple[AnalysisResult, LocalizingMock]:
    deps, _ = build_deps(fixture(MEDICAID), tmp_path)
    provider = LocalizingMock(lang, deps.settings)
    deps.ai = AIService(provider, None, deps.settings)
    req = AnalyzeRequest(
        pages=[], target_language=lang, client_platform="web", demo_sample_id=MEDICAID
    )
    result = await run_analysis(req, deps)
    return AnalysisResult.model_validate(result.model_dump()), provider


def _has_non_western_digit(text: str) -> bool:
    return any(ch.isdecimal() and not ch.isascii() for ch in text)


@pytest.mark.parametrize("lang", sorted(NON_WESTERN))
async def test_localized_printed_date_goes_back_to_the_printed_form(
    lang: str, tmp_path: Path
) -> None:
    result, provider = await analyze_localized(lang, tmp_path)
    assert provider.calls >= 1
    date_text, extra = NON_WESTERN[lang]
    prose = {
        "summary.title": result.summary.title,
        "summary.body": result.summary.body,
        **{f"demand {d.id}": d.text for d in result.demands},
        **{f"step {s.id}": s.text for s in result.plan_steps},
        **{f"question {i}": q for i, q in enumerate(result.questions_to_ask)},
    }
    for where, text in prose.items():
        assert date_text not in text, (lang, where, text)
        assert not _has_non_western_digit(text), (lang, where, text)
    # The date the paper prints is back in its printed spelling where the model wrote it.
    assert PRINTED in result.summary.body
    assert any(PRINTED in d.text for d in result.demands)
    assert any(PRINTED in s.text for s in result.plan_steps)
    # A stray run the paper does not print becomes Western digits, never dropped.
    assert result.summary.body.endswith("(30)") and extra not in result.summary.body
    # Nothing was counted as rejected: the facts verified; only their spelling changed.
    assert all(d.verified for d in result.demands)


# ---------------------------------------------------------------------------- troubleshoot


async def test_troubleshoot_prose_keeps_the_numbers_the_screen_shows(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """The screen prints "5 MB" and "8.4 MB": a Dari step that writes "۵ MB" / "۸٫۴ MB" gets
    Western digits back (rule 7 applies to every prompt)."""
    recorded = STORE.get(SCREEN).troubleshoot_out("prs")  # type: ignore[union-attr]
    assert recorded is not None
    out = recorded.model_copy(deep=True)
    out.steps[0].text = "عکس شما ۸٫۴ MB است. آن را زیر ۵ MB کنید."
    out.screen_summary = "این صفحه می‌گوید فایل بزرگتر از ۵ MB است."
    install(app, settings, troubleshoot=lambda kw: out)
    shot = base64.b64encode(STORE.get(SCREEN).page_png(1)).decode()  # type: ignore[union-attr]
    r = await client.post("/v1/troubleshoot", json={
        "screenshot": {"mime_type": "image/png", "data_base64": shot},
        "target_language": "prs", "client_platform": "android", "demo_sample_id": SCREEN,
    })  # fmt: skip
    assert r.status_code == 200, r.text
    res = TroubleshootResult.model_validate(r.json())
    assert res.steps[0].text == "عکس شما 8.4 MB است. آن را زیر 5 MB کنید."
    assert res.screen_summary == "این صفحه می‌گوید فایل بزرگتر از 5 MB است."
