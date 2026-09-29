"""Quick-sheet PDF renderer tests (API_CONTRACT §3.11; RESOURCE_DB §7, §10; BUILD_PLAN §5.4 step 5).

PDFs are inspected with pypdfium2 (text + glyph boxes) because reportlab compresses page streams.
"""

from __future__ import annotations

import re
import time
from typing import Any

import arabic_reshaper
import pypdfium2 as pdfium
import pytest
import yaml
from bidi.algorithm import get_display
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from proxyhealth_api.contracts.quicksheet import QuickSheetRequest, QuickSheetResource
from proxyhealth_api.quicksheet import fonts
from proxyhealth_api.quicksheet.render import (
    MARGIN,
    MAX_BYTES,
    clean,
    has_arabic,
    main_font,
    page_size_for,
    render,
    shape,
    validate_resources,
    wrap,
)
from proxyhealth_api.settings import DATA_DIR
from tests.unit._fixtures_wp3 import DARI_EXAMPLE, ENGLISH_EXAMPLE, real_repo

# Base Arabic-script letters (incl. Persian پ چ ژ ک گ ی) vs. any Arabic-script code point.
ARABIC_BASE_LETTERS = re.compile(
    "[" + "".join(f"{chr(a)}-{chr(b)}" for a, b in ((0x0621, 0x064A), (0x067E, 0x06CC))) + "]"
)
ARABIC_ANY = re.compile(
    "[" + "".join(f"{chr(a)}-{chr(b)}" for a, b in ((0x0600, 0x06FF), (0xFB50, 0xFEFC))) + "]"
)
ZWSP, ZWNJ = chr(0x200B), chr(0x200C)


def req(body: dict[str, Any], **overrides: Any) -> QuickSheetRequest:
    return QuickSheetRequest.model_validate({**body, **overrides})


def page_text(pdf: bytes) -> str:
    doc = pdfium.PdfDocument(pdf)
    return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


def base_fonts(pdf: bytes) -> set[str]:
    return {m.decode() for m in re.findall(rb"/BaseFont /([A-Za-z0-9+_-]+)", pdf)}


# ---- rendering ------------------------------------------------------------------------------


def test_ltr_request_renders_small_pdf_with_embedded_noto() -> None:
    pdf = render(req(ENGLISH_EXAMPLE), real_repo())
    assert pdf.startswith(b"%PDF")
    assert len(pdf) <= MAX_BYTES == 200 * 1024
    assert {"AAAAAA+NotoSans-Regular", "AAAAAA+NotoSans-Bold"} <= base_fonts(pdf)
    text = page_text(pdf)
    assert "What is this?" in text and "Who can help" in text
    assert "1/1" in text


def test_rtl_dari_example_renders_shaped_and_right_aligned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drawn: list[tuple[str, str]] = []
    original_right = Canvas.drawRightString
    original_left = Canvas.drawString

    def spy_right(self: Canvas, x: float, y: float, text: str, *a: Any, **k: Any) -> Any:
        drawn.append(("right", text))
        return original_right(self, x, y, text, *a, **k)

    def spy_left(self: Canvas, x: float, y: float, text: str, *a: Any, **k: Any) -> Any:
        drawn.append(("left", text))
        return original_left(self, x, y, text, *a, **k)

    monkeypatch.setattr(Canvas, "drawRightString", spy_right)
    monkeypatch.setattr(Canvas, "drawString", spy_left)
    pdf = render(req(DARI_EXAMPLE), real_repo())
    assert pdf.startswith(b"%PDF")
    assert len(pdf) <= MAX_BYTES
    assert any("NotoNaskhArabic" in name for name in base_fonts(pdf))
    arabic_lines = [(side, t) for side, t in drawn if ARABIC_ANY.search(t)]
    assert len(arabic_lines) >= 9  # title, 3 headings, 5 lines, footer
    for side, line in arabic_lines:
        assert side == "right", line  # RTL paragraphs are right-aligned
        # Joined glyphs: every Arabic letter was reshaped into a presentation form.
        assert not ARABIC_BASE_LETTERS.search(line), line
    title = get_display(arabic_reshaper.reshape(DARI_EXAMPLE["title"]), base_dir="R")
    assert ("right", title) in drawn
    text = page_text(pdf)
    # English sub-headers under the Dari ones.
    assert "What is this?" in text and "Your steps" in text
    doc = pdfium.PdfDocument(pdf)
    page = doc[0]
    width = page.get_width()
    textpage = page.get_textpage()
    rights = [textpage.get_charbox(i)[2] for i in range(textpage.count_chars())]
    assert max(rights) == pytest.approx(width - MARGIN, abs=3)
    # The title (first line, right-aligned) starts well right of the left margin.
    first_line = [
        textpage.get_charbox(i)
        for i in range(textpage.count_chars())
        if textpage.get_charbox(i)[3] > page.get_height() - MARGIN - 30
    ]
    assert min(box[0] for box in first_line) > MARGIN + 100


def test_ltr_text_is_left_aligned() -> None:
    pdf = render(req(ENGLISH_EXAMPLE), real_repo())
    page = pdfium.PdfDocument(pdf)[0]
    textpage = page.get_textpage()
    lefts = [textpage.get_charbox(i)[0] for i in range(textpage.count_chars())]
    assert min(lefts) == pytest.approx(MARGIN, abs=3)


def test_long_request_paginates_and_stays_under_limit() -> None:
    lines = [f"Line {i}: bring the letter and your ID to the office." for i in range(40)]
    sections = [
        {"heading": f"Part {n}", "heading_en": f"Part {n}", "lines": lines} for n in range(8)
    ]
    pdf = render(req(ENGLISH_EXAMPLE, sections=sections), real_repo())
    doc = pdfium.PdfDocument(pdf)
    assert len(doc) > 1
    assert f"1/{len(doc)}" in doc[0].get_textpage().get_text_range()
    assert len(pdf) <= MAX_BYTES


def test_cjk_request_renders_with_cid_font() -> None:
    body = {**ENGLISH_EXAMPLE, "title": "医疗账单", "language_tag": "zh-Hans", "font_hint": None}
    pdf = render(req(body), real_repo())
    assert pdf.startswith(b"%PDF")
    assert "STSong-Light" in pdf.decode("latin-1")


def test_rtl_paper_size_follows_region() -> None:
    assert page_size_for("prs") == page_size_for("en-US") == page_size_for("es-419")
    assert page_size_for("fr-FR")[0] < page_size_for("en")[0]  # A4 is narrower than Letter


# ---- shaping ----------------------------------------------------------------------------------


def test_shape_reshapes_then_reorders_arabic_script() -> None:
    logical = "سلام دنیا"
    expected = get_display(arabic_reshaper.reshape(logical), base_dir="R")
    assert shape(logical, rtl=True) == expected
    assert shape(logical, rtl=True) != logical
    assert shape("Hello", rtl=False) == "Hello"
    assert has_arabic("نامه") and not has_arabic("Hello")


def test_clean_keeps_spaces_and_zwnj_but_drops_controls() -> None:
    assert clean("A  b\tc\x00" + ZWSP + "d") == "A b cd"
    word = "می" + ZWNJ + "خواهد"
    assert clean(word) == word


# ---- resource re-validation (RESOURCE_DB §7) --------------------------------------------------


def test_unknown_resource_phone_is_dropped() -> None:
    items = [QuickSheetResource.model_validate(r) for r in ENGLISH_EXAMPLE["resources"]]
    kept, dropped = validate_resources(items, real_repo())
    assert [(k.id, k.phone) for k in kept] == [("211", "211")]
    assert dropped == 2
    text = page_text(render(req(ENGLISH_EXAMPLE), real_repo()))
    assert "555" not in text and "Totally Real" not in text


def test_resource_values_come_from_the_db() -> None:
    dhs = real_repo().get("dhs_oig")
    assert dhs is not None and dhs.phone is not None
    item = QuickSheetResource(name="  dhs oig  ", phone=dhs.phone, url=dhs.url + "/")
    kept, dropped = validate_resources([item, item], real_repo())
    assert dropped == 0
    assert [(k.name, k.phone, k.url) for k in kept] == [(dhs.name, dhs.phone, dhs.url)]


def test_wrong_url_for_named_entry_and_no_repo_are_dropped() -> None:
    item = QuickSheetResource(name="211", phone="211", url="https://evil.example/")
    assert validate_resources([item], real_repo()) == ([], 1)
    assert validate_resources([item], None) == ([], 1)


# ---- fonts ------------------------------------------------------------------------------------


def test_every_font_hint_resolves_to_an_embedded_noto_family() -> None:
    table = yaml.safe_load((DATA_DIR / "languages.yaml").read_text(encoding="utf-8"))
    rows = table.get("languages", table) if isinstance(table, dict) else {}
    hints = {row.get("font_hint") for row in rows.values() if isinstance(row, dict)}
    for hint in sorted(h for h in hints if h):
        pair = fonts.font_for(hint, "en")
        assert pair.family == fonts.PDF_SUBSTITUTES.get(hint, hint) and pair.embedded, hint


def test_font_registration_is_idempotent_and_falls_back() -> None:
    first = fonts.register_family("NotoNaskhArabic")
    assert first is not None and first is fonts.register_family("NotoNaskhArabic")
    assert fonts.font_for("NoSuchFont", "es").family == fonts.DEFAULT_FAMILY
    assert fonts.font_for(None, "ja").family == "HeiseiMin-W3"
    # reportlab cannot run Nastaliq's GSUB shaping: the PDF draws Urdu with Noto Naskh Arabic.
    assert fonts.font_for("NotoNastaliqUrdu", "ur").family == "NotoNaskhArabic"


# ---- Arabic-script coverage after shaping (reportlab draws Presentation Forms by cmap) ---------

# One sentence per Arabic-script language of data/languages.yaml, covering its extra letters
# (Urdu ٹ ڈ ڑ ں ہ ھ ے, Pashto ښ ږ ځ څ ډ ړ ګ ڼ ې ۍ, Persian پ چ ژ گ, Arabic ة ى and lam-alef).
ARABIC_SCRIPT_SAMPLES: dict[str, str] = {
    "ar": "هذه الرسالة من برنامج ميديكيد في فيرجينيا. لم يتم إلغاء تأمينك. لا، إلى، ة، ى، ٠١٢٣",
    "prs": (
        "این نامه از مدیکید ویرجینیا است. بیمه شما قطع نشده است. "
        "تا October 14, 2026 جواب بدهید."
    ),
    "fa": "این نامه از مدیکید ویرجینیا است. پژوهش، گچ، چای، ۱۲۳",
    "ps": "دا لیک د ویرجینیا مېډیکېډ څخه دی. ستاسو بیمه نه ده ختمه شوې. ښځه، ږ، ځ، ړ، ګ، ڼ، ۍ",
    "ur": (
        "یہ خط ورجینیا میڈیکیڈ سے ہے۔ آپ کا بیمہ ختم نہیں ہوا۔ "
        "بجلی کا بل بھیجیں۔ ٹھیک، ڈاک، پڑھیں"
    ),
}


def arabic_script_languages() -> dict[str, str | None]:
    table = yaml.safe_load((DATA_DIR / "languages.yaml").read_text(encoding="utf-8"))
    return {str(tag): row.get("font_hint") for tag, row in table.items() if row["script"] == "Arab"}


def test_every_arabic_script_language_has_a_coverage_sample() -> None:
    assert set(arabic_script_languages()) == set(ARABIC_SCRIPT_SAMPLES)


@pytest.mark.parametrize("tag", sorted(ARABIC_SCRIPT_SAMPLES))
@pytest.mark.parametrize("with_hint", [True, False], ids=["hint", "no_hint"])
def test_arabic_script_face_covers_every_shaped_glyph(tag: str, with_hint: bool) -> None:
    """The face the PDF draws with maps every Presentation Form the reshaper emits (the Urdu
    sheet rendered blank when it drew with Noto Nastaliq Urdu, which maps none of them)."""
    hint = arabic_script_languages()[tag] if with_hint else None
    pair = fonts.font_for(hint, tag)
    shaped = shape(ARABIC_SCRIPT_SAMPLES[tag], True)
    assert any(0xFB50 <= ord(ch) <= 0xFEFC for ch in shaped)
    assert fonts.missing_glyphs(pair, shaped) == set(), (tag, hint, pair.family)


def test_arabic_text_with_a_latin_hint_switches_to_naskh() -> None:
    body = {
        **DARI_EXAMPLE,
        "font_hint": "NotoSans",
        "sections": [
            {"heading": "این چیست؟", "heading_en": "What is this?", "lines": ["یک بل برق"]}
        ],
    }
    assert main_font(req(body)).family == "NotoNaskhArabic"
    assert main_font(req(ENGLISH_EXAMPLE)).family == "NotoSans"


def ink(pdf: bytes) -> int:
    """Dark pixels on page 1 (a blank-glyph regression leaves only the English lines)."""
    bitmap = pdfium.PdfDocument(pdf)[0].render(scale=1).to_pil().convert("L")
    return sum(bitmap.histogram()[:128])


def test_urdu_sheet_draws_its_urdu_lines() -> None:
    line = ARABIC_SCRIPT_SAMPLES["ur"]
    body = {
        **DARI_EXAMPLE,
        "title": "ورجینیا میڈیکیڈ کا خط",
        "language_tag": "ur",
        "font_hint": "NotoNastaliqUrdu",
        "footer": "یہ غلط ہو سکتا ہے۔",
    }
    with_urdu = {**body, "sections": [{"heading": "یہ کیا ہے؟", "heading_en": "What is this?",
                                        "lines": [line] * 12}]}  # fmt: skip
    without = {**body, "sections": [{"heading": "", "heading_en": "What is this?", "lines": []}]}
    pdf = render(req(with_urdu), real_repo())
    assert any("NotoNaskhArabic" in name for name in base_fonts(pdf))
    assert not any("Nastaliq" in name for name in base_fonts(pdf))
    assert ink(pdf) > ink(render(req(without), real_repo())) + 2000


# ---- wrap: linear and within the text width -------------------------------------------------


def test_wrap_lines_fit_and_keep_every_word() -> None:
    pair = fonts.font_for("NotoNaskhArabic", "prs")
    text = clean(" ".join([ARABIC_SCRIPT_SAMPLES["prs"]] * 5))
    lines = wrap(text, pair.regular, 11, 300, True)
    assert len(lines) > 1
    for line in lines:
        assert pdfmetrics.stringWidth(line, pair.regular, 11) <= 300 + 1e-6
    # Bidi only permutes characters, so the lines hold exactly the one-line shaping's glyphs.
    drawn = sorted("".join(lines).replace(" ", ""))
    assert drawn == sorted(shape(text, True).replace(" ", ""))


def test_maximum_arabic_script_request_renders_quickly() -> None:
    """8 sections × 40 distinct 400-character lines used to take ~16 s (quadratic wrap)."""
    words = ARABIC_SCRIPT_SAMPLES["ur"].split(" ")

    def line(n: int) -> str:
        out = f"{n} "
        while len(out) < 400:
            out += words[(len(out) + n) % len(words)] + " "
        return out[:400]

    sections = [
        {"heading": line(s), "heading_en": "Part", "lines": [line(s * 40 + i) for i in range(40)]}
        for s in range(8)
    ]
    body = {**DARI_EXAMPLE, "language_tag": "ur", "font_hint": "NotoNastaliqUrdu",
            "sections": sections, "footer": line(999)}  # fmt: skip
    started = time.perf_counter()
    pdf = render(req(body), real_repo())
    assert time.perf_counter() - started < 8.0
    assert pdf.startswith(b"%PDF") and len(pdf) <= MAX_BYTES
