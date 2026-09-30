"""Quick-sheet "Who can help" heading and phone format (POLISH item 3; API_CONTRACT §3.11).

The resources heading is localized like every other section (target-language heading, English
sub-heading for the clerk) and US phones print readably while every national digit is kept.
"""

from __future__ import annotations

import re
from typing import Any

import arabic_reshaper
import pypdfium2 as pdfium
import pytest
from bidi.algorithm import get_display
from reportlab.pdfgen.canvas import Canvas

from proxyhealth_api.contracts.quicksheet import QuickSheetRequest, QuickSheetSection
from proxyhealth_api.quicksheet.render import (
    bundled_string,
    clean,
    format_phone,
    help_heading,
    is_help_carrier,
    isolate_ltr_runs,
    render,
    shape,
)
from proxyhealth_api.settings import DATA_DIR
from tests.unit._fixtures_wp3 import DARI_EXAMPLE, ENGLISH_EXAMPLE, real_repo

HELP_PRS = "چه کسی کمک کرده می\u200cتواند"
TWO_PHONES = [
    {"name": "HealthCare.gov (Health Insurance Marketplace)", "phone": "+18003182596",
     "url": "https://www.healthcare.gov/"},
    {"name": "Inova Financial Assistance", "phone": "+15714725880", "url": None},
]  # fmt: skip
CARRIER = {"heading": HELP_PRS, "heading_en": "Who can help", "lines": []}


def dari(**overrides: Any) -> QuickSheetRequest:
    return QuickSheetRequest.model_validate({**DARI_EXAMPLE, "resources": TWO_PHONES, **overrides})


def page_text(pdf: bytes) -> str:
    doc = pdfium.PdfDocument(pdf)
    return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


def digits(text: str) -> str:
    return re.sub(r"\D", "", text)


@pytest.fixture
def drawn(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []
    right, left = Canvas.drawRightString, Canvas.drawString

    def spy_right(self: Canvas, x: float, y: float, text: str, *a: Any, **k: Any) -> Any:
        seen.append(("right", text))
        return right(self, x, y, text, *a, **k)

    def spy_left(self: Canvas, x: float, y: float, text: str, *a: Any, **k: Any) -> Any:
        seen.append(("left", text))
        return left(self, x, y, text, *a, **k)

    monkeypatch.setattr(Canvas, "drawRightString", spy_right)
    monkeypatch.setattr(Canvas, "drawString", spy_left)
    return seen


# ---- phones ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stored", "printed"),
    [
        ("+18003182596", "1-800-318-2596"),
        ("+18558894325", "1-855-889-4325"),
        ("+15714725880", "(571) 472-5880"),
        ("+12026449807", "(202) 644-9807"),
        ("211", "211"),
        ("988", "988"),
        ("+442071234567", "+442071234567"),
        ("+1800318259", "+1800318259"),  # malformed: printed as stored, never guessed
    ],
)
def test_format_phone(stored: str, printed: str) -> None:
    assert format_phone(stored) == printed


def test_every_db_phone_keeps_its_national_digits() -> None:
    for entry in real_repo().all():
        for phone in (entry.phone, entry.tty):
            if not phone:
                continue
            printed = format_phone(phone)
            national = digits(phone)[-10:] if len(digits(phone)) >= 10 else digits(phone)
            assert digits(printed).endswith(national), (entry.id, phone, printed)
            if printed.startswith("1-"):
                assert digits(printed) == digits(phone)  # toll free keeps the leading 1 too


# ---- heading --------------------------------------------------------------------------------


def test_heading_comes_from_the_carrier_then_the_bundled_pack_then_english() -> None:
    with_carrier = dari(sections=[*DARI_EXAMPLE["sections"], CARRIER])
    assert help_heading(with_carrier, {}) == (HELP_PRS, "Who can help")
    assert help_heading(dari(), {}) == (bundled_string("prs", "quicksheet.help"), "Who can help")
    assert bundled_string("prs", "quicksheet.help") == HELP_PRS
    assert bundled_string("es-US", "quicksheet.help") == "Quién puede ayudar"  # base subtag
    unknown = dari(language_tag="x-unknown-lang")
    assert help_heading(unknown, {"quicksheet.help": "Who can help"}) == (
        "Who can help", "Who can help",
    )  # fmt: skip
    assert bundled_string("../en", "quicksheet.help") is None


def test_a_section_with_lines_is_never_a_carrier() -> None:
    full = QuickSheetSection(heading=HELP_PRS, heading_en="Who can help", lines=["211"])
    assert not is_help_carrier(full, "Who can help")
    assert is_help_carrier(QuickSheetSection(**CARRIER), "who can help ")


def test_dari_sheet_draws_a_localized_heading_and_readable_phones(
    drawn: list[tuple[str, str]],
) -> None:
    pdf = render(dari(sections=[*DARI_EXAMPLE["sections"], CARRIER]), real_repo())
    heading = get_display(arabic_reshaper.reshape(HELP_PRS), base_dir="R")
    title = get_display(arabic_reshaper.reshape(DARI_EXAMPLE["title"]), base_dir="R")
    passes = drawn.count(("right", title))  # render lays the sheet out twice (page count)
    assert passes == 2
    assert drawn.count(("right", heading)) == passes  # the carrier is not drawn on its own
    text = page_text(pdf)
    assert "Who can help" in text  # the English sub-heading for the clerk
    assert "1-800-318-2596" in text and "(571) 472-5880" in text
    assert "+18003182596" not in text and "+15714725880" not in text
    names = [t for _, t in drawn if t.startswith(("HealthCare.gov", "Inova"))]
    assert len(names) == 2 * passes


def test_english_sheet_has_one_heading_and_no_duplicate_sub_heading(
    drawn: list[tuple[str, str]],
) -> None:
    render(QuickSheetRequest.model_validate(ENGLISH_EXAMPLE), real_repo())
    texts = [t for _, t in drawn]
    assert texts.count("Who can help") == texts.count(ENGLISH_EXAMPLE["title"]) == 2  # 2 passes


def test_carrier_without_surviving_resources_draws_nothing(drawn: list[tuple[str, str]]) -> None:
    fake = [{"name": "Totally Real Legal Help", "phone": "+15555550199", "url": None}]
    render(dari(resources=fake, sections=[*DARI_EXAMPLE["sections"], CARRIER]), real_repo())
    heading = get_display(arabic_reshaper.reshape(HELP_PRS), base_dir="R")
    assert ("right", heading) not in drawn


def test_clean_drops_bidi_isolates_a_client_may_send() -> None:
    assert clean("\u2068Call 211\u2069 \u202bnow\u202c") == "Call 211 now"
    assert clean("a\u200cb\u200fc") == "a\u200cb\u200fc"  # ZWNJ and RLM shape text: kept


@pytest.mark.parametrize(
    ("line", "kept"),
    [
        ("ساخته شده در 2026-09-29.", "2026-09-29"),
        ("به 1-800-318-2596 زنگ بزنید", "1-800-318-2596"),
        ("تا ۲۰۲۶-۱۰-۱۴ جواب بدهید", "۲۰۲۶-۱۰-۱۴"),
        ("October 14, 2026 — آدرس خود را تأیید کنید", "October 14, 2026"),
        ("از (571) 472-5880 بپرسید", "(571) 472-5880"),
        ("مبلغ: $125.00", "$125.00"),
        ("مبلغ €50 یا £20", "€50"),
    ],
)
def test_rtl_lines_keep_dates_and_numbers_in_order(line: str, kept: str) -> None:
    # Without isolation UAX #9 turns digits after Arabic letters into Arabic numbers and the
    # hyphens between them run right-to-left: "2026-09-29" would print as "29-09-2026" (D-26).
    drawn_line = shape(line, True)
    assert kept in drawn_line
    assert not re.search("[\u200b-\u200f\u2066-\u2069]", drawn_line)


def test_pdf_footer_date_reads_left_to_right() -> None:
    footer = "ساخته شده در 2026-09-29."
    text = page_text(render(dari(footer=footer), real_repo()))
    assert "2026-09-29" in text and "29-09-2026" not in text


# The real Dari demand sentence of the Inova sample (mobile assets/fixtures
# inova_final_notice.result.prs.json): the "$" must stay on the left of the amount.
INOVA_PRS = "می\u200cگوید مبلغ قابل پرداخت $1,240.00 تا ۲۸ اکتبر ۲۰۲۶ است."
MOBILE_FIXTURES = DATA_DIR.parents[1] / "mobile" / "assets" / "fixtures"


def test_inova_dari_amount_keeps_its_currency_sign_on_the_left() -> None:
    assert INOVA_PRS in (MOBILE_FIXTURES / "inova_final_notice.result.prs.json").read_text("utf-8")
    assert isolate_ltr_runs(INOVA_PRS).count("\u2066$1,240.00\u2069") == 1
    drawn_line = shape(INOVA_PRS, True)
    assert "$1,240.00" in drawn_line and "1,240.00$" not in drawn_line


def test_pdf_amount_keeps_its_currency_sign_on_the_left() -> None:
    text = page_text(render(dari(footer="مبلغ: $125.00"), real_repo()))
    assert "$125.00" in text and "125.00$" not in text
