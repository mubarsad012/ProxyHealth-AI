"""Phase 2B — ``analysis/prose_dates.py``: dates in model prose must be the paper's (D-11)."""

from __future__ import annotations

import threading
from datetime import date

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
