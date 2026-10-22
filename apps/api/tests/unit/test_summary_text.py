"""``analysis/summary_text.py`` — summary card repairs before the lint (AI_PROMPTS §11.9).

The cut titles and English bodies are the ones a small local model (qwen3.5:4b, strict JSON-schema
decoding) wrote for the synthetic samples; every curated fixture output must pass unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from proxyhealth_api.analysis import summary_text as st
from proxyhealth_api.analysis.prose_dates import find_mentions
from proxyhealth_api.contracts.model_out import AnalysisModelOut
from proxyhealth_api.settings import DATA_DIR

INOVA = "This is a bill from Inova Health System asking you to pay $1,240.00 by October 2"
MEDICAID = "This letter asks you to confirm your address so they can send your Medicaid and "
JURY = "This is a summons from the Circuit Court of Sample County, Virginia, asking you"
JURY_BODY = (
    "to appear for jury service on November 16, 2026, and to return a questionnaire by "
    "October 23, 2026."
)


def test_title_cap_is_the_schema_cap() -> None:
    field = AnalysisModelOut.model_fields["summary_title"]
    caps = [m.max_length for m in field.metadata if getattr(m, "max_length", None)]
    assert caps == [st.TITLE_CAP]


@pytest.mark.parametrize(
    ("raw", "fixed"),
    [
        (INOVA, "This is a bill from Inova Health System asking you to pay…"),
        (MEDICAID, "This letter asks you to confirm your address so they can send your Medicaid…"),
        (JURY, "This is a summons from the Circuit Court of Sample County, Virginia…"),
        (
            "This is an immunization notice from Maple Grove Elementary School about missing,",
            "This is an immunization notice from Maple Grove Elementary School about missing…",
        ),
    ],
)
def test_a_title_cut_at_the_cap_ends_on_a_whole_word(raw: str, fixed: str) -> None:
    assert len(raw) >= st.TITLE_CAP - 2 and st.is_cut(raw)
    assert st.repair_title(raw) == fixed
    assert not any(ch.isdigit() for ch in fixed)


def test_a_word_the_cap_split_is_dropped() -> None:
    kept = "This notice from the county asks you to bring your papers to the office"
    raw = f"{kept} by Octob"
    assert len(raw) == st.TITLE_CAP
    assert st.repair_title(raw) == f"{kept}…"


def test_no_partial_date_or_amount_stays_in_a_cut_title() -> None:
    """"by October 2" (printed: October 28) matched the demo's own day; it never reaches the
    title card now."""
    fixed = st.repair_title(INOVA)
    assert find_mentions(fixed, "en") == [] and "1,240" not in fixed and "October" not in fixed


@pytest.mark.parametrize(
    "title",
    [
        "This is a denial notice from Blue Ridge Sample Health Plan about an MRI request now.",
        "Hospital bill from Inova marked final notice",
        "This is a fake paper that says it is not real.",
    ],
)
def test_whole_or_short_titles_are_unchanged(title: str) -> None:
    assert st.repair_title(title) == title


@pytest.mark.parametrize(
    ("raw", "language", "fixed"),
    [
        ("إشعار من مالك الشقة عن إيجار غير مدفوع لشهر سبتمبر وطلب الدفع قبل يوم 8 أكتوبر 2026",
         "ar", "إشعار من مالك الشقة عن إيجار غير مدفوع لشهر سبتمبر وطلب الدفع قبل يوم…"),
        ("اطلاعیه صاحب‌خانه درباره کرایه پرداخت‌نشده ماه سپتمبر و درخواست پرداخت تا ۸ اکتبر ۲۰۲۶ در",
         "prs", "اطلاعیه صاحب‌خانه درباره کرایه پرداخت‌نشده ماه سپتمبر و درخواست پرداخت…"),
    ],
)  # fmt: skip
def test_arabic_script_titles_lose_a_trailing_number(raw: str, language: str, fixed: str) -> None:
    raw = raw.ljust(st.TITLE_CAP - 1)[: st.TITLE_CAP]
    assert st.is_cut(raw)
    out = st.repair_title(raw, language=language)
    assert out == fixed
    assert not any(ch.isdigit() for ch in out)


def test_a_body_that_continues_the_title_gets_it_back() -> None:
    joined = st.join_continuation(JURY, JURY_BODY)
    assert joined == f"{JURY} {JURY_BODY}"
    fields = st.tidy(JURY, JURY_BODY, joined, target_language="en")
    assert fields.title == "This is a summons from the Circuit Court of Sample County, Virginia…"
    assert fields.body == fields.body_en == joined
    # a capitalised body, a whole title or a short label are never glued on
    assert st.join_continuation(JURY, "The court sent this.") == "The court sent this."
    assert st.join_continuation("Jury summons.", "you must answer.") == "you must answer."
    assert st.join_continuation("Jury summons", "you must answer.") == "you must answer."
    assert st.continues("Notice asking you", "to appear in court.")


TITLE = "This is a court notice telling you to go to an immigration hearing."
BODY = "The Immigration Court says you must appear on October 7, 2026 at 8:30 AM in Fairfax."


def test_english_body_en_that_only_repeats_the_title_takes_the_body() -> None:
    fields = st.tidy(TITLE, BODY, TITLE, target_language="en")
    assert fields.body == fields.body_en == BODY and fields.title == TITLE


def test_english_body_en_opening_with_the_title_loses_it() -> None:
    fields = st.tidy(TITLE, BODY, f"{TITLE} {BODY}", target_language="en-US")
    assert fields.body == fields.body_en == BODY


def test_a_body_in_the_papers_language_gives_way_to_the_english_one() -> None:
    spanish = (
        "Propiedades Los Robles LLC envió este contrato de alquiler que cubre el periodo del 1 de "
        "diciembre de 2026 al 30 de noviembre de 2027."
    )
    english = (
        "Propiedades Los Robles LLC sent this lease for an apartment in Arlington, Virginia, "
        "from December 1, 2026 to November 30, 2027."
    )
    fields = st.tidy("Contrato de alquiler", spanish, english, target_language="en")
    assert fields.body == fields.body_en == english


def test_two_english_bodies_become_the_readers_body() -> None:
    fields = st.tidy(TITLE, "This letter is from the court. You qualify for help.", BODY,
                     target_language="en")  # fmt: skip
    assert fields.body == fields.body_en == "This letter is from the court. You qualify for help."


def test_a_non_english_reader_keeps_both_bodies() -> None:
    body = "La corte de inmigración le pide ir a una audiencia."
    fields = st.tidy("Aviso de Comparecencia", body, TITLE, target_language="es")
    assert (fields.body, fields.body_en) == (body, TITLE)


FIXTURE_OUTPUTS = sorted((DATA_DIR / "fixtures").glob("*/out.*.json"))


@pytest.mark.parametrize("path", FIXTURE_OUTPUTS, ids=lambda p: f"{p.parent.name}-{p.name}")
def test_every_fixture_summary_is_unchanged(path: Path) -> None:
    out = json.loads(path.read_text(encoding="utf-8"))
    if not out.get("summary_title"):
        pytest.skip("no summary in this fixture")
    lang = path.name.split(".")[1]
    fields = st.tidy(out["summary_title"], out["summary_body"], out["summary_body_en"],
                     target_language=lang)  # fmt: skip
    assert (fields.title, fields.body, fields.body_en) == (
        out["summary_title"], out["summary_body"], out["summary_body_en"]
    )
