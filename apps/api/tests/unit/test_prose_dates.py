"""Phase 2B — ``analysis/prose_dates.py``: dates in model prose must be the paper's (D-11)."""

from __future__ import annotations

import threading
from datetime import date

import pytest

from proxyhealth_api.analysis import pipeline
from proxyhealth_api.analysis import prose_dates as pd
from proxyhealth_api.contracts.analysis import DateInfo, Demand
from proxyhealth_api.contracts.enums import Confidence, DateKind, DemandKind
from tests.unit._fixtures_wp2 import en_t

TODAY = date(2026, 10, 2)
PAPER = (
    "Date of notice: September 24, 2026\n"
    "YOU ARE ORDERED to appear before an immigration judge on October 7, 2026 at 8:30 AM."
)
SEE_PAPER = en_t()(pd.SEE_PAPER_KEY)  # the key itself until the en.json merge adds the copy


def hearing(text: str = "Go to the immigration court on October 7, 2026 at 8:30 AM.") -> Demand:
    info = DateInfo(
        value_iso="2026-10-07", time_text="8:30 AM", kind=DateKind.stated, formula=None,
        anchor_quote=None, anchor_demand_id=None, rule_id=None, rule_source_url=None,
        rule_verification=None, localized_line=None,
    )  # fmt: skip
    return Demand(
        id="d1", kind=DemandKind.deadline, text=text, value_verbatim="October 7, 2026",
        source_quote="appear before an immigration judge on October 7, 2026 at 8:30 AM.",
        span_ids=["p1b2"], page=1, confidence=Confidence.high, verified=True,
        verification_note="exact", date=info, amount=None, documents=[], role="hearing_date",
        reminder_eligible=True, ambiguity_note=None,
    )  # fmt: skip


def allowed() -> pd.AllowedDates:
    return pd.allowed_dates([hearing()], PAPER, today=TODAY, language="en")


def test_mentions_cover_named_numeric_iso_eastern_and_year_less_dates() -> None:
    found = pd.find_mentions("By 10/13/2026, ۱۴ اکتبر ۲۰۲۶, 2026-10-15 or October 16.", "prs")
    assert [sorted(m.dates) for m in found[:3]] == [
        [date(2026, 10, 13)], [date(2026, 10, 14)], [date(2026, 10, 15)],
    ]
    assert found[3].dates == frozenset() and found[3].month_days == {(10, 16)}
    assert pd.find_mentions("Call 1-800-222-1222. Case 12-34-5678. You may 2 times.", "en") == []


def test_printed_verified_and_today_dates_pass_unchanged() -> None:
    stats = pd.ProseDateStats()
    text = "Your notice is from September 24, 2026. Go on October 7, 2026. Today is October 2."
    assert pd.check_text(text, allowed(), t=en_t(), language="en", stats=stats) == text
    assert stats.checked == 3 and stats.rejected == 0


def test_invented_dates_drop_their_sentence_in_longer_prose() -> None:
    stats = pd.ProseDateStats()
    text = (
        "This paper starts a court case. You must appear before a judge on October 17, 2026. "
        "You then have until November 30, 2026 to file your application. Nothing is decided yet."
    )
    out = pd.check_text(text, allowed(), t=en_t(), language="en", stats=stats)
    assert out == "This paper starts a court case. Nothing is decided yet."
    assert stats.rejected == 2


def test_a_single_sentence_keeps_its_action_without_the_invented_date() -> None:
    stats = pd.ProseDateStats()
    step = "You have 30 days, until November 6, 2026, to send your answer."
    out = pd.check_text(step, allowed(), t=en_t(), language="en", stats=stats)
    assert "November 6" not in out and SEE_PAPER in out and stats.rejected == 1


def test_a_demand_sentence_gets_its_own_verified_date() -> None:
    stats = pd.ProseDateStats()
    shifted = hearing("Go to the immigration court on October 17, 2026 at 8:30 AM.")
    out = pd.check_demand_text(shifted, allowed(), t=en_t(), language="en", stats=stats)
    assert out == "Go to the immigration court on October 7, 2026 at 8:30 AM."
    assert stats.rejected == 1


async def test_offload_runs_image_work_off_the_event_loop() -> None:
    loop_thread = threading.get_ident()
    worker = await pipeline.offload(threading.get_ident)
    assert worker != loop_thread


# --- Phase 2C: printed forms (D-26; AI_PROMPTS §5.0 rule 7) ------------------------------------

BILL = PAPER + "\nAmount due: $1,240.00. Form I-130. Call by 10/14/2026."


def forms() -> pd.PrintedForms:
    return pd.printed_forms(BILL, "en", [hearing()])


@pytest.mark.parametrize(
    ("lang", "prose", "expected"),
    [
        # Persian digits and a translated month → the printed date (Dari).
        ("prs", "تا ۷ اکتبر ۲۰۲۶ ساعت ۸:۳۰ به محکمه بروید.",
         "تا October 7, 2026 ساعت 8:30 به محکمه بروید."),
        # Month first with the Arabic comma before the year (the year is absorbed, not doubled).
        ("prs", "تاریخ اکتبر ۷، ۲۰۲۶ است.", "تاریخ October 7, 2026 است."),
        # Eastern Arabic digits, separators and a translated month (Arabic).
        ("ar", "اذهب إلى المحكمة في ٧ أكتوبر ٢٠٢٦ وادفع ١٬٢٤٠٫٠٠ دولار.",
         "اذهب إلى المحكمة في October 7, 2026 وادفع 1,240.00 دولار."),
        # Western digits, translated (Levantine) month name.
        ("ar", "الجلسة في 7 تشرين الأول 2026.", "الجلسة في October 7, 2026."),
        # A numeric printed date keeps its numeric spelling; form numbers get Western digits.
        ("ar", "اتصل قبل ١٤/١٠/٢٠٢٦ بخصوص النموذج I-١٣٠.",
         "اتصل قبل 10/14/2026 بخصوص النموذج I-130."),
        # Spanish month name on an English paper → as printed.
        ("es", "Vaya a la corte el 7 de octubre de 2026.", "Vaya a la corte el October 7, 2026."),
    ],
)  # fmt: skip
def test_localized_dates_and_digits_go_back_to_the_printed_form(
    lang: str, prose: str, expected: str
) -> None:
    assert pd.as_printed(prose, forms(), lang) == expected


def test_printed_forms_and_english_prose_are_left_alone() -> None:
    f = forms()
    for prose in (
        "Go to court on October 7, 2026 at 8:30 AM.",
        "Go to court on October 7.",  # an English month is never a translation
        "Pay $1,240.00 by 10/14/2026.",
        "تا October 7, 2026 به محکمه بروید.",
    ):
        assert pd.as_printed(prose, f, "prs") == prose


def test_unprinted_dates_keep_their_words_and_get_western_digits() -> None:
    # Today (allowed by check_text, printed nowhere): no spelling to restore, digits only.
    assert pd.as_printed("امروز ۲ اکتبر ۲۰۲۶ است.", forms(), "prs") == "امروز 2 اکتبر 2026 است."


def test_a_paper_that_prints_its_own_digits_keeps_them() -> None:
    paper = "موعد الجلسة: ٧ أكتوبر ٢٠٢٦. المبلغ ١٢٠ دولار."
    f = pd.printed_forms(paper, "ar")
    prose = "الجلسة في ٧ أكتوبر ٢٠٢٦ والمبلغ ١٢٠ دولار."
    assert pd.as_printed(prose, f, "ar") == prose
    # A run the paper does not print still becomes Western.
    assert pd.as_printed("ادفع ٣٠ دولار.", f, "ar") == "ادفع 30 دولار."


def test_western_digits_keeps_listed_runs() -> None:
    assert pd.western_digits("۱۲۳ و ٤٥٦") == "123 و 456"
    assert pd.western_digits("۱۲۳ و ٤٥٦", frozenset({"٤٥٦"})) == "123 و ٤٥٦"
    assert pd.western_digits("plain 123") == "plain 123"
