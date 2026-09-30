"""Text-only quick-sheet PDF (API_CONTRACT §3.11; ARCHITECTURE §2.1 ``quicksheet/render.py``).

``render(req, repo) -> bytes`` builds the PDF in memory with reportlab and returns it; nothing is
written to disk or logged (ARCHITECTURE §7). Every Arabic-script line is shaped with
``arabic_reshaper.reshape()`` and reordered with python-bidi's ``get_display()`` (the Rust
``unicode-bidi`` implementation, which honours isolates) before drawing (DECISIONS §14,
2026-09-27); ``direction == rtl`` right-aligns every paragraph, and inside an RTL line every
Latin/digit run (dates, numbers, names, phones) is laid out in its own LRI…PDI isolate first, as the
app does (D-26): without it a date printed after Arabic letters reads "29-09-2026" (UAX #9 W2
makes its digits Arabic numbers, so the hyphens between them take the RTL direction). English
sub-headers appear under the localized ones for the clerk. Resources are re-validated against the
resource DB (RESOURCE_DB §7): a ``QuickSheetResource`` is kept only when its ``name``/``url``
match an entry and its ``phone`` is that entry's ``phone``/``tty`` (or null); anything else is
dropped silently and only the *count* is logged.

The "Who can help" heading is localized like the other sections (target-language heading, English
sub-heading for the clerk). Its text comes, in order, from a *heading carrier* the client sends —
a section whose ``heading_en`` is the English ``quicksheet.help`` and whose ``lines`` are empty
(the carrier itself is never drawn as a section) — else from the bundled pack for
``language_tag``, else English. US phone numbers are printed readably (``1-800-318-2596`` toll
free, ``(571) 472-5880`` otherwise; every national digit kept); the DB keeps E.164 for ``tel:``.
"""

from __future__ import annotations

import functools
import io
import json
import logging
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

import arabic_reshaper
from bidi import get_display
from reportlab.lib import pagesizes
from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from proxyhealth_api.contracts.enums import Direction
from proxyhealth_api.contracts.quicksheet import (
    QuickSheetRequest,
    QuickSheetResource,
    QuickSheetSection,
)
from proxyhealth_api.quicksheet.fonts import (
    FontPair,
    arabic_font,
    font_for,
    latin_font,
    missing_glyphs,
)
from proxyhealth_api.resources.loader import ResourceRepo
from proxyhealth_api.settings import DATA_DIR

logger = logging.getLogger("proxyhealth.quicksheet")

LETTER: tuple[float, float] = (float(pagesizes.letter[0]), float(pagesizes.letter[1]))
A4: tuple[float, float] = (float(pagesizes.A4[0]), float(pagesizes.A4[1]))
MARGIN = 54.0
# API_CONTRACT §3.11: "A4/Letter auto by language_tag region, default Letter".
LETTER_REGIONS: frozenset[str] = frozenset(
    {"US", "CA", "MX", "PR", "PH", "CL", "CO", "VE", "GT", "CR", "PA", "DO", "SV", "419"}
)
FOOTER_HEIGHT = 64.0
MAX_BYTES = 200 * 1024
MAX_LINE_CHARS = 400

SIZE_TITLE = 18
SIZE_HEADING = 13
SIZE_SUBHEADING = 9
SIZE_BODY = 11
SIZE_RESOURCE = 10
SIZE_FOOTER = 9
SIZE_META = 8

GREY = Color(0.35, 0.35, 0.35)
BLACK = Color(0, 0, 0)

ARABIC_RE = re.compile("[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufefe]")
# C0/C1 controls, zero-width space, BOM, and the bidi embedding/isolate controls (U+202A–U+202E,
# U+2066–U+2069) a client may carry over from its UI: reportlab would draw them as boxes, and
# ``_visual`` adds its own isolates per line. LRM/RLM and ZWJ/ZWNJ are kept: they shape text.
CONTROL_RE = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b\u202a-\u202e\u2066-\u2069\ufeff]"
)
LRI, PDI = "\u2066", "\u2069"
# Removed from a line once it is shaped and reordered: isolates and the zero-width format marks
# (ZWNJ/ZWJ already did their work in ``arabic_reshaper``; reportlab would draw them as boxes).
DRAW_STRIP_RE = re.compile("[\u200b-\u200f\u202a-\u202e\u2066-\u2069]")
# A Latin/digit run (Western, Arabic-Indic or Persian digits) with the punctuation that belongs
# inside it; it starts on a letter/digit, optionally after "+", "(" and/or a currency sign (so
# "$1,240.00" keeps its "$" on the left in RTL lines), and ends on a letter/digit or ")".
_ALNUM = r"0-9A-Za-z\u0660-\u0669\u06f0-\u06f9"
_CURRENCY = "$€£¥"
LTR_RUN_RE = re.compile(
    rf"[+(]?[{_CURRENCY}]?[{_ALNUM}](?:[{_ALNUM}{_CURRENCY} .,:/()+\-–&#@']*[{_ALNUM})])?"
)
HELP_KEY = "quicksheet.help"
HELP_FALLBACK = "Who can help"
LANGPACKS_DIR = DATA_DIR / "langpacks"
_TAG_RE = re.compile(r"^[A-Za-z0-9]{1,8}(?:-[A-Za-z0-9]{1,8})*$")
# NANP numbers as the resource DB stores them (E.164 ``+1NXXNXXXXXX``; bare 10/11 digits too).
_NANP_RE = re.compile(r"(?:\+?1)?([2-9]\d{2})([2-9]\d{2})(\d{4})")
TOLL_FREE_AREA_CODES: frozenset[str] = frozenset({"800", "833", "844", "855", "866", "877", "888"})


def has_arabic(text: str) -> bool:
    return bool(ARABIC_RE.search(text))


def clean(text: str) -> str:
    """NFC, control characters removed, whitespace collapsed, bounded length."""
    s = unicodedata.normalize("NFC", text)
    s = CONTROL_RE.sub("", s)
    s = re.sub(r"[ \t\r\n]+", " ", s).strip()
    return s[:MAX_LINE_CHARS]


def _reshape(text: str) -> str:
    """Contextual forms + lam-alef ligatures for Arabic script; other text is returned as is.

    Default ``arabic_reshaper`` config: harakat are dropped because reportlab has no mark
    positioning (they would render as detached spacing glyphs).
    """
    return arabic_reshaper.reshape(text) if has_arabic(text) else text


def isolate_ltr_runs(text: str) -> str:
    """Wrap every Latin/digit run of a logical RTL line in LRI…PDI (the quick-sheet HTML's
    ``isolateLtrRuns`` rule), so dates, amounts, phones and names keep their own order."""
    return LTR_RUN_RE.sub(lambda m: f"{LRI}{m.group(0)}{PDI}", text)


def _visual(text: str, rtl: bool) -> str:
    """Bidi-reorder an already reshaped logical line into drawing order (``DRAW_STRIP_RE`` marks
    removed afterwards, as the pure-Python ``bidi.algorithm`` used to drop them)."""
    if text and (rtl or has_arabic(text)):
        logical = isolate_ltr_runs(text) if rtl else text
        shaped: str = get_display(logical, base_dir="R" if rtl else "L")
        return DRAW_STRIP_RE.sub("", shaped)
    return text


def shape(text: str, rtl: bool) -> str:
    """One logical line → visual string: reshape Arabic script, then bidi reorder."""
    if not text:
        return text
    return _visual(_reshape(text), rtl)


def format_phone(phone: str) -> str:
    """A DB phone as printed: US toll free ``1-800-318-2596``, other US ``(571) 472-5880``;
    N11 codes (``211``), extensions and non-US numbers unchanged. Every national digit is kept
    (only the ``+1`` of a non-toll-free number is left out, as US papers print it)."""
    p = phone.strip()
    m = _NANP_RE.fullmatch(p)
    if m is None:
        return p
    area, exchange, line = m.groups()
    if area in TOLL_FREE_AREA_CODES:
        return f"1-{area}-{exchange}-{line}"
    return f"({area}) {exchange}-{line}"


@functools.lru_cache(maxsize=64)
def bundled_string(language_tag: str, key: str) -> str | None:
    """``key`` from ``data/langpacks/<tag>.json`` (exact tag, then its base subtag); ``None``
    when no bundled pack has it. Packs are UI strings only (never user content)."""
    if not _TAG_RE.match(language_tag):
        return None
    for tag in dict.fromkeys((language_tag, language_tag.split("-")[0])):
        path = LANGPACKS_DIR / f"{tag}.json"
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        strings = data.get("strings", data) if isinstance(data, dict) else {}
        value = strings.get(key) if isinstance(strings, dict) else None
        if isinstance(value, str) and value.strip():
            return value
    return None


def is_help_carrier(section: QuickSheetSection, help_en: str) -> bool:
    """A section with no lines whose English heading is "Who can help": it only names the
    resources heading in the sheet's language (never drawn as a section of its own)."""
    same = clean(section.heading_en).casefold() == clean(help_en).casefold()
    return same and not any(clean(line) for line in section.lines)


def help_heading(req: QuickSheetRequest, en_strings: Mapping[str, str]) -> tuple[str, str]:
    """``(heading, heading_en)`` for the resources block (module docstring for the order)."""
    help_en = en_strings.get(HELP_KEY) or HELP_FALLBACK
    for section in req.sections:
        if is_help_carrier(section, help_en) and clean(section.heading):
            return section.heading, help_en
    return bundled_string(req.language_tag, HELP_KEY) or help_en, help_en


def page_size_for(language_tag: str) -> tuple[float, float]:
    """Letter unless the tag carries a region outside ``LETTER_REGIONS`` (``fr-FR`` → A4)."""
    for part in language_tag.split("-")[1:]:
        if (len(part) == 2 and part.isalpha()) or (len(part) == 3 and part.isdigit()):
            return LETTER if part.upper() in LETTER_REGIONS else A4
    return LETTER


@dataclass(frozen=True)
class ValidatedResource:
    """A resource line that survived re-validation (values are the DB entry's own)."""

    id: str
    name: str
    phone: str | None
    url: str | None


def _norm_url(url: str) -> str:
    return url.strip().rstrip("/").casefold()


def validate_resources(
    items: list[QuickSheetResource], repo: ResourceRepo | None
) -> tuple[list[ValidatedResource], int]:
    """RESOURCE_DB §7 re-validation. Returns ``(kept, dropped_count)``; no repo → all dropped."""
    if repo is None:
        return [], len(items)
    by_url: dict[str, str] = {}
    by_name: dict[str, str] = {}
    for res in repo.all():
        by_url.setdefault(_norm_url(res.url), res.id)
        for alt in res.alt_urls:
            by_url.setdefault(_norm_url(alt), res.id)
        by_name.setdefault(res.name.casefold().strip(), res.id)
    kept: list[ValidatedResource] = []
    seen: set[str] = set()
    dropped = 0
    for item in items:
        rid = by_url.get(_norm_url(item.url)) if item.url else None
        if rid is None:
            rid = by_name.get(item.name.casefold().strip())
        entry = repo.get(rid) if rid else None
        if entry is None:
            dropped += 1
            continue
        entry_urls = {_norm_url(entry.url), *(_norm_url(a) for a in entry.alt_urls)}
        if item.url and _norm_url(item.url) not in entry_urls:
            dropped += 1
            continue
        if item.phone is not None and item.phone.strip() not in {entry.phone, entry.tty}:
            dropped += 1
            continue
        if entry.id in seen:
            continue
        seen.add(entry.id)
        kept.append(
            ValidatedResource(
                id=entry.id,
                name=entry.name,
                phone=item.phone.strip() if item.phone else None,
                url=entry.url if item.url else None,
            )
        )
    return kept, dropped


def _hard_break(word: str, font: str, size: float, width: float) -> list[str]:
    """Split one over-wide (already reshaped) word by character, measuring incrementally."""
    parts: list[str] = []
    cur = ""
    cur_width = 0.0
    for ch in word:
        ch_width = pdfmetrics.stringWidth(ch, font, size)
        if cur and cur_width + ch_width > width:
            parts.append(cur)
            cur, cur_width = ch, ch_width
        else:
            cur += ch
            cur_width += ch_width
    if cur:
        parts.append(cur)
    return parts


def wrap(text: str, font: str, size: float, width: float, rtl: bool) -> list[str]:
    """Greedy word wrap on the logical text; each returned line is already shaped for drawing.

    Linear in the line length: the paragraph is reshaped once (Arabic joining never crosses a
    space, so its space-separated pieces are exactly the forms each word takes on any line), a
    line's width is the sum of its words and spaces (reportlab applies no kerning), and bidi
    reordering only permutes characters, so only finished lines are reordered.
    """
    space = pdfmetrics.stringWidth(" ", font, size)
    logical: list[str] = []
    cur: list[str] = []
    cur_width = 0.0
    for form in _reshape(text).split(" "):
        word_width = pdfmetrics.stringWidth(form, font, size)
        if word_width > width:
            if cur:
                logical.append(" ".join(cur))
                cur, cur_width = [], 0.0
            logical.extend(_hard_break(form, font, size, width))
            continue
        if cur and cur_width + space + word_width > width:
            logical.append(" ".join(cur))
            cur, cur_width = [form], word_width
        else:
            cur_width += (space if cur else 0.0) + word_width
            cur.append(form)
    if cur:
        logical.append(" ".join(cur))
    return [_visual(line, rtl) for line in logical] or [""]


WrapKey = tuple[str, str, float, bool]  # (cleaned text, face, size, rtl)


class _Sheet:
    """Cursor-based page layout over a reportlab canvas (manual pagination, two passes)."""

    def __init__(
        self,
        req: QuickSheetRequest,
        main: FontPair,
        latin: FontPair,
        wraps: dict[WrapKey, list[str]] | None = None,
    ) -> None:
        self.req = req
        # Per-render memo shared by both passes (lives only for this ``render`` call).
        self.wraps: dict[WrapKey, list[str]] = {} if wraps is None else wraps
        self.main = main
        self.latin = latin
        self.rtl = req.direction == Direction.rtl
        self.buf = io.BytesIO()
        self.width, self.height = page_size_for(req.language_tag)
        self.text_width = self.width - 2 * MARGIN
        self.pdf = canvas.Canvas(self.buf, pagesize=(self.width, self.height))
        self.pdf.setTitle(clean(req.title))
        self.pdf.setAuthor("ProxyHealth AI")
        self.pdf.setCreator("ProxyHealth AI quick sheet")
        self.page = 1
        self.total_pages = 1
        self.y = self.height - MARGIN

    # -- primitives ---------------------------------------------------------------------------

    def _draw(self, text: str, font: str, size: float, color: Color, align_right: bool) -> None:
        self.pdf.setFont(font, size)
        self.pdf.setFillColor(color)
        if align_right:
            self.pdf.drawRightString(self.width - MARGIN, self.y, text)
        else:
            self.pdf.drawString(MARGIN, self.y, text)

    def _wrap(self, text: str, font: str, size: float, rtl: bool) -> list[str]:
        key = (text, font, size, rtl)
        lines = self.wraps.get(key)
        if lines is None:
            lines = self.wraps[key] = wrap(text, font, size, self.text_width, rtl)
        return lines

    def _ensure(self, height: float) -> None:
        if self.y - height < MARGIN + FOOTER_HEIGHT:
            self._footer()
            self.pdf.showPage()
            self.page += 1
            self.y = self.height - MARGIN

    def paragraph(
        self,
        text: str,
        *,
        font: FontPair,
        bold: bool = False,
        size: float = SIZE_BODY,
        color: Color = BLACK,
        rtl: bool | None = None,
        align_right: bool | None = None,
        gap_after: float = 4.0,
    ) -> None:
        text = clean(text)
        is_rtl = self.rtl if rtl is None else rtl
        right = self.rtl if align_right is None else align_right
        face = font.bold if bold else font.regular
        leading = size * font.leading
        for line in self._wrap(text, face, size, is_rtl):
            self._ensure(leading)
            self.y -= leading
            self._draw(line, face, size, color, right)
        self.y -= gap_after

    def space(self, points: float) -> None:
        self.y -= points

    def rule(self) -> None:
        self._ensure(10)
        self.pdf.setStrokeColor(GREY)
        self.pdf.setLineWidth(0.5)
        self.pdf.line(MARGIN, self.y - 4, self.width - MARGIN, self.y - 4)
        self.y -= 12

    # -- footer -------------------------------------------------------------------------------

    def _footer(self) -> None:
        saved_y = self.y
        self.y = MARGIN + FOOTER_HEIGHT - 8
        footer = clean(self.req.footer)
        face = self.main.regular
        for line in self._wrap(footer, face, SIZE_FOOTER, self.rtl)[:3]:
            self.y -= SIZE_FOOTER * self.main.leading
            self._draw(line, face, SIZE_FOOTER, GREY, self.rtl)
        meta = f"{self.req.generated_on.isoformat()}  ·  {self.page}/{self.total_pages}"
        self.pdf.setFont(self.latin.regular, SIZE_META)
        self.pdf.setFillColor(GREY)
        if self.rtl:
            self.pdf.drawString(MARGIN, MARGIN - 6, meta)
        else:
            self.pdf.drawRightString(self.width - MARGIN, MARGIN - 6, meta)
        self.y = saved_y

    def finish(self) -> bytes:
        self._footer()
        self.pdf.showPage()
        self.pdf.save()
        return self.buf.getvalue()


def main_font(req: QuickSheetRequest) -> FontPair:
    """``font_for`` plus a coverage guard: Arabic-script text the chosen face cannot draw (a
    missing or wrong ``font_hint``) switches the sheet to Noto Naskh Arabic instead of rendering
    blank lines."""
    main = font_for(req.font_hint, req.language_tag)
    texts = [req.title, req.footer]
    for section in req.sections:
        texts.append(section.heading)
        texts.extend(section.lines)
    if not any(has_arabic(t) for t in texts):
        return main
    sample = _reshape(" ".join(clean(t) for t in texts))
    missing = missing_glyphs(main, sample)
    if not missing:
        return main
    arabic = arabic_font()
    if arabic is not None and len(missing_glyphs(arabic, sample)) < len(missing):
        return arabic
    return main


def _heading(
    sheet: _Sheet, heading: str, heading_en: str, *, main: FontPair, latin: FontPair
) -> None:
    """A localized section heading with the English one under it for the clerk (when different)."""
    sheet.paragraph(heading, font=main, bold=True, size=SIZE_HEADING, gap_after=0)
    if clean(heading_en) and clean(heading_en) != clean(heading):
        sheet.paragraph(
            heading_en, font=latin, size=SIZE_SUBHEADING, color=GREY, rtl=False, gap_after=4
        )


def _compose(
    req: QuickSheetRequest,
    resources: list[ValidatedResource],
    en_strings: Mapping[str, str],
    *,
    main: FontPair,
    total_pages: int,
    wraps: dict[WrapKey, list[str]],
) -> _Sheet:
    latin = latin_font()
    sheet = _Sheet(req, main, latin, wraps)
    sheet.total_pages = total_pages
    sheet.paragraph(req.title, font=main, bold=True, size=SIZE_TITLE, gap_after=2)
    sheet.paragraph(
        f"{req.generated_on.isoformat()}  ·  {req.language_tag}",
        font=latin, size=SIZE_META, color=GREY, rtl=False, gap_after=6,
    )  # fmt: skip
    sheet.rule()
    help_en = en_strings.get(HELP_KEY) or HELP_FALLBACK
    for section in req.sections:
        if is_help_carrier(section, help_en):
            continue
        sheet.space(4)
        _heading(sheet, section.heading, section.heading_en, main=main, latin=latin)
        for line in section.lines:
            if not clean(line):
                sheet.space(4)
                continue
            sheet.paragraph(line, font=main, size=SIZE_BODY, gap_after=2)
        sheet.space(6)
    if resources:
        sheet.rule()
        heading, heading_en = help_heading(req, en_strings)
        _heading(sheet, heading, heading_en, main=main, latin=latin)
        sheet.space(2)
        for res in resources:
            sheet.paragraph(res.name, font=latin, bold=True, size=SIZE_BODY, rtl=False, gap_after=0)
            phone = format_phone(res.phone) if res.phone else None
            details = "  ·  ".join(part for part in (phone, res.url) if part)
            if details:
                sheet.paragraph(
                    details, font=latin, size=SIZE_RESOURCE, color=GREY, rtl=False, gap_after=4
                )
            else:
                sheet.space(4)
    return sheet


def render(
    req: QuickSheetRequest,
    repo: ResourceRepo | None = None,
    *,
    en_strings: Mapping[str, str] | None = None,
) -> bytes:
    """Build the PDF bytes in memory (two passes so the footer can show ``page/total``)."""
    strings: Mapping[str, str] = en_strings or {}
    resources, dropped = validate_resources(req.resources, repo)
    if dropped:
        logger.info("quicksheet_resources_dropped=%d", dropped)
    main = main_font(req)
    wraps: dict[WrapKey, list[str]] = {}
    first = _compose(req, resources, strings, main=main, total_pages=1, wraps=wraps)
    first.finish()
    total = first.page
    final = _compose(req, resources, strings, main=main, total_pages=total, wraps=wraps)
    pdf = final.finish()
    if len(pdf) > MAX_BYTES:
        logger.warning("quicksheet_pdf_bytes=%d exceeds %d", len(pdf), MAX_BYTES)
    return pdf


__all__ = [
    "HELP_KEY",
    "LTR_RUN_RE",
    "MAX_BYTES",
    "TOLL_FREE_AREA_CODES",
    "ValidatedResource",
    "bundled_string",
    "clean",
    "format_phone",
    "has_arabic",
    "help_heading",
    "is_help_carrier",
    "isolate_ltr_runs",
    "main_font",
    "page_size_for",
    "render",
    "shape",
    "validate_resources",
    "wrap",
]
