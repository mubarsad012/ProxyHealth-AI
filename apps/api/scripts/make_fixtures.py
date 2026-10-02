"""Render the synthetic sample papers (BUILD_PLAN §5.8 step 1; D-29; AI_PROMPTS §10.2).

One hand-authored ``data/fixtures/<id>/template.yaml`` per fixture is the single source. From it
this script generates, byte-deterministically:

* ``page-<n>.png`` — 1600 px wide, Noto fonts from ``data/fonts``, Arabic-script lines shaped
  with ``arabic_reshaper`` + ``bidi`` (Pillow here has no raqm), a diagonal SAMPLE watermark on
  every page; ``blurry_unreadable_page`` is Gaussian-blurred and low-contrast.
* ``transcript.txt`` — every text block in reading order (the verification corpus; quotes in the
  outputs are checked to be verbatim substrings of a block).
* ``manifest.yaml`` — the ``DemoFixture`` fields, the frozen ``today`` for goldens, the golden
  expectations and the 16×16 dHash of page 1 (``demo/phash.py``).
* ``out.<lang>.json`` — the hand-authored ``AnalysisModelOut`` (``TroubleshootModelOut`` for the
  screenshot) per recorded language, assembled from ``template.out.base`` plus per-language
  overrides, with ``blocks`` (ids + bboxes) taken from the rendered layout and a ``_meta`` object.
* ``clerk.<lang>.json`` — for a readable document in a recorded non-English language, the
  hand-recorded ``clerk_translate`` answer: the English clerk card the pipeline builds
  (``analysis/clerk.py``) and its translation from ``out.<lang>.clerk_cards`` (the mock serves it
  as ``clerk_message.translated``; a missing or stale translation fails the build).

Every output language keeps printed dates and times exactly as printed (AI_PROMPTS §5.0 rule 7,
PRODUCT_SPEC §7.1 "Numbers", D-26): ``October 7, 2026`` in Spanish, Arabic and Dari prose alike.

Block ids are ``p<page>b<n>`` in reading order (AI_PROMPTS §4.1). Template lines may carry a
``ref`` name; any ``"@name"`` string in a span-id field of the output resolves to that block id.

``--check`` regenerates everything in memory and exits 1 when any byte would change (CI gate);
``--only <id>`` limits the run while authoring; ``--distances`` prints the pairwise dHash matrix.
A write run never overwrites or deletes an ``out.<lang>.json`` whose ``_meta.recorded_by`` is
``recording_provider`` (``ai/recording.py``, AI_PROMPTS §10.4): it is kept for human review and
``--check`` keeps reporting it until it is folded into ``template.yaml`` or deleted by hand.
"""

from __future__ import annotations

import argparse
import copy
import functools
import io
import json
import math
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import arabic_reshaper
import yaml
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from pydantic import ValidationError

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from proxyhealth_api.ai import prompt_loader  # noqa: E402
from proxyhealth_api.analysis import clerk  # noqa: E402
from proxyhealth_api.contracts.enums import DocumentType, ResourceTag  # noqa: E402
from proxyhealth_api.contracts.model_out import (  # noqa: E402
    AnalysisModelOut,
    TroubleshootModelOut,
)
from proxyhealth_api.demo.phash import dhash, hamming, hash_to_hex  # noqa: E402

DATA = API_ROOT / "data"
FIXTURES_DIR = DATA / "fixtures"
FONTS_DIR = DATA / "fonts"
DEFAULT_PROMPTS_VERSION = "2026-09-27.1"  # AI_PROMPTS §10.2 until WP2 lands ai/prompts/VERSION
RECORDED_ON = "2026-09-27"

PAGE_W = 1600
DOC_H = 2070  # US letter aspect at 1600 px wide
SCREEN_H = 1100
MARGIN = 120
FOOTER_TEXT = "SAMPLE — synthetic document made for demonstration. Not a real letter."
SCREEN_FOOTER_TEXT = "SAMPLE — synthetic screen made for demonstration. Not a real website."

Align = Literal["left", "center", "right"]
Rgb = tuple[int, int, int]

INK: Rgb = (20, 20, 20)
GREY: Rgb = (96, 96, 96)
RED: Rgb = (178, 24, 24)
WHITE: Rgb = (255, 255, 255)
SCREEN_BG: Rgb = (240, 243, 247)
_VALID_TAGS = {t.value for t in ResourceTag}
_ROLES = {
    "response_due", "payment_due", "appointment", "hearing_date", "expiry", "move_date",
    "notice_date", "decision_date", "other",
}  # fmt: skip


# --------------------------------------------------------------------------- fonts and shaping


@functools.cache
def _font(family: str, size: int, bold: bool) -> ImageFont.FreeTypeFont:
    weight = "Bold" if bold else "Regular"
    path = FONTS_DIR / f"{family}-{weight}.ttf"
    return ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.BASIC)


def is_arabic_script(text: str) -> bool:
    for ch in text:
        code = ord(ch)
        if 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F or 0xFB50 <= code <= 0xFEFF:
            return True
    return False


def shape(text: str) -> str:
    """Contextual forms + visual (bidi) order for one line of Arabic-script text."""
    shaped: str = get_display(arabic_reshaper.reshape(text))
    return shaped


def font_for(text: str, size: int, bold: bool) -> ImageFont.FreeTypeFont:
    if is_arabic_script(text):
        return _font("NotoNaskhArabic", size, bold)
    return _font("NotoSans", size, bold)


def visual(text: str) -> str:
    return shape(text) if is_arabic_script(text) else text


def wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Greedy word wrap on the logical string (Arabic lines are shaped after wrapping)."""
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if current and font.getlength(visual(candidate)) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def normalize(text: str) -> str:
    """NFKC + collapsed whitespace — the same normaliser WP2's ``verify.py`` uses."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


# --------------------------------------------------------------------------- styles


@dataclass(frozen=True)
class Style:
    size: int = 32
    bold: bool = False
    color: Rgb = INK
    align: Align = "left"
    before: int = 14
    after: int = 14
    box: Literal["none", "stamp", "button", "error", "band", "field", "row", "note"] = "none"
    indent: int = 0
    rule: bool = False


STYLES: dict[str, Style] = {
    "letterhead": Style(size=40, bold=True, before=0, after=4),
    "letterhead_sub": Style(size=27, color=GREY, before=0, after=4),
    "title": Style(size=50, bold=True, align="center", before=40, after=24),
    "heading": Style(size=38, bold=True, before=30, after=10),
    "subheading": Style(size=33, bold=True, before=22, after=8),
    "body": Style(size=31, before=12, after=12),
    "bold": Style(size=31, bold=True, before=12, after=12),
    "small": Style(size=25, color=GREY, before=8, after=8),
    "right": Style(size=29, align="right", before=6, after=6),
    "center": Style(size=31, align="center", before=10, after=10),
    "stamp": Style(size=46, bold=True, color=RED, align="center", before=30, after=30, box="stamp"),
    "field": Style(size=30, before=6, after=6, box="field"),
    "row": Style(size=29, before=6, after=6, box="row"),
    "indent": Style(size=31, before=8, after=8, indent=60),
    "bullet": Style(size=31, before=6, after=6, indent=60),
    "button": Style(size=34, bold=True, color=WHITE, before=18, after=18, box="button"),
    "error": Style(size=31, bold=True, color=RED, before=18, after=18, box="error"),
    "note": Style(size=29, before=14, after=14, box="note"),
    "band": Style(size=40, bold=True, color=WHITE, before=0, after=0, box="band"),
    "rule": Style(size=1, before=10, after=10, rule=True),
    "gap": Style(size=1, before=0, after=0),
    "footer": Style(size=22, color=GREY, align="center", before=0, after=0),
}


@dataclass
class RenderProfile:
    kind: Literal["document", "screenshot"] = "document"
    accent: Rgb = (31, 71, 136)
    band_height: int = 0  # coloured top band (0 = none)
    logo: Literal["none", "left", "right", "seal"] = "none"
    blur: float = 0.0
    contrast: float = 1.0
    brightness: float = 1.0
    watermark_angle: int = 32
    font_scale: float = 1.0
    paper: Rgb = WHITE

    @classmethod
    def from_yaml(cls, raw: dict[str, Any] | None, kind: str) -> RenderProfile:
        raw = raw or {}
        accent = tuple(int(v) for v in raw.get("accent", (31, 71, 136)))
        default_paper = SCREEN_BG if kind == "screenshot" else WHITE
        paper = tuple(int(v) for v in raw.get("paper", default_paper))
        assert len(accent) == 3 and len(paper) == 3
        return cls(
            kind="screenshot" if kind == "screenshot" else "document",
            accent=(accent[0], accent[1], accent[2]),
            band_height=int(raw.get("band_height", 0)),
            logo=raw.get("logo", "none"),
            blur=float(raw.get("blur", 0.0)),
            contrast=float(raw.get("contrast", 1.0)),
            brightness=float(raw.get("brightness", 1.0)),
            watermark_angle=int(raw.get("watermark_angle", 32)),
            font_scale=float(raw.get("font_scale", 1.0)),
            paper=(paper[0], paper[1], paper[2]),
        )


@dataclass
class Line:
    text: str
    style: str
    ref: str | None = None
    unclear: bool = False
    handwriting: bool = False
    gap: int = 40


@dataclass
class PlacedBlock:
    id: str
    page: int
    text: str
    bbox: tuple[float, float, float, float]
    ref: str | None = None
    unclear: bool = False
    handwriting: bool = False


@dataclass
class RenderedPage:
    png: bytes
    blocks: list[PlacedBlock] = field(default_factory=list)


# --------------------------------------------------------------------------- rendering


def _scaled(style: Style, profile: RenderProfile) -> int:
    return max(12, int(round(style.size * profile.font_scale)))


def _draw_logo(draw: ImageDraw.ImageDraw, profile: RenderProfile) -> None:
    accent = profile.accent
    if profile.logo == "seal":
        cx, cy, r = MARGIN + 52, MARGIN + 52, 52
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=accent, width=6)
        draw.ellipse([cx - r + 14, cy - r + 14, cx + r - 14, cy + r - 14], outline=accent, width=3)
        points: list[tuple[float, float]] = []
        for i in range(10):  # five-pointed star drawn as a polygon (Noto Sans has no U+2605)
            radius = 22 if i % 2 == 0 else 9
            angle = math.pi / 2 + i * math.pi / 5
            points.append((cx + radius * math.cos(angle), cy - radius * math.sin(angle)))
        draw.polygon(points, fill=accent)
    elif profile.logo == "left":
        draw.rectangle([MARGIN, MARGIN, MARGIN + 104, MARGIN + 104], fill=accent)
        draw.rectangle([MARGIN + 22, MARGIN + 22, MARGIN + 82, MARGIN + 82], fill=WHITE)
    elif profile.logo == "right":
        x1 = PAGE_W - MARGIN
        draw.rectangle([x1 - 220, MARGIN, x1, MARGIN + 70], outline=accent, width=4)
        draw.text((x1 - 110, MARGIN + 35), "LOGO", fill=accent, font=_font("NotoSans", 30, True),
                  anchor="mm")  # fmt: skip


def _watermark(img: Image.Image, angle: int) -> Image.Image:
    w, h = img.size
    layer = Image.new("RGBA", (w * 2, h * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font = _font("NotoSans", 250, True)
    for yy in range(0, h * 2, 620):
        for xx in range(-w, w * 2, 1250):
            d.text((xx, yy), "SAMPLE", font=font, fill=(120, 120, 120, 78))
    layer = layer.rotate(angle, resample=Image.Resampling.BICUBIC, center=(w, h))
    crop = layer.crop((w // 2, h // 2, w // 2 + w, h // 2 + h))
    return Image.alpha_composite(img.convert("RGBA"), crop).convert("RGB")


def _footer(draw: ImageDraw.ImageDraw, height: int, page_no: int, total: int, text: str) -> None:
    font = _font("NotoSans", 22, False)
    draw.text((PAGE_W // 2, height - 48), text, fill=GREY, font=font, anchor="mm")
    if total > 1:
        draw.text((PAGE_W - MARGIN, height - 48), f"Page {page_no} of {total}", fill=GREY,
                  font=font, anchor="rm")  # fmt: skip


def _box_bounds(style: Style, x0: int, y0: int, text_w: int, text_h: int, content_w: int,
                profile: RenderProfile) -> tuple[int, int, int, int]:  # fmt: skip
    pad = 22
    if style.box == "button":
        return (x0, y0, x0 + text_w + 2 * pad + 20, y0 + text_h + 2 * pad - 6)
    if style.box == "stamp":
        cx = MARGIN + content_w // 2
        half = text_w // 2 + pad + 10
        return (cx - half, y0, cx + half, y0 + text_h + 2 * pad - 8)
    return (x0, y0, MARGIN + content_w, y0 + text_h + 2 * pad - 6)


def _draw_box(draw: ImageDraw.ImageDraw, style: Style, bounds: tuple[int, int, int, int],
              profile: RenderProfile) -> None:  # fmt: skip
    accent = profile.accent
    if style.box == "button":
        draw.rounded_rectangle(bounds, radius=14, fill=accent)
    elif style.box == "stamp":
        draw.rectangle(bounds, outline=RED, width=6)
    elif style.box == "error":
        draw.rounded_rectangle(bounds, radius=10, fill=(253, 236, 236), outline=RED, width=3)
    elif style.box == "field":
        draw.rounded_rectangle(bounds, radius=8, fill=(250, 250, 250), outline=(170, 170, 170),
                               width=3)  # fmt: skip
    elif style.box == "note":
        draw.rectangle(bounds, fill=(245, 245, 235), outline=(200, 200, 180), width=2)
    elif style.box == "row":
        draw.rectangle(bounds, outline=(150, 150, 150), width=2)


def render_page(
    lines: list[Line], profile: RenderProfile, page_no: int, total: int
) -> RenderedPage:
    height = DOC_H if profile.kind == "document" else SCREEN_H
    img = Image.new("RGB", (PAGE_W, height), profile.paper)
    draw = ImageDraw.Draw(img)
    content_w = PAGE_W - 2 * MARGIN
    blocks: list[PlacedBlock] = []
    y = MARGIN
    if profile.band_height:
        draw.rectangle([0, 0, PAGE_W, profile.band_height], fill=profile.accent)
        y = profile.band_height + 40
    if profile.logo != "none" and not profile.band_height:
        _draw_logo(draw, profile)
    logo_offset = 130 if profile.logo in ("left", "seal") else 0
    band_cursor = 30
    n = 0
    for line in lines:
        style = STYLES[line.style]
        if line.style == "gap":
            y += line.gap
            continue
        if style.rule:
            y += style.before
            draw.line([MARGIN, y, PAGE_W - MARGIN, y], fill=(120, 120, 120), width=3)
            y += style.after
            continue
        size = _scaled(style, profile)
        font = font_for(line.text, size, style.bold)
        line_h = int(size * 1.35)
        indent = style.indent + (logo_offset if line.style.startswith("letterhead") else 0)
        x0 = MARGIN + indent
        if style.box == "band":
            top = band_cursor
            draw.text((MARGIN, top), visual(line.text), fill=WHITE, font=font)
            text_w = int(font.getlength(visual(line.text)))
            band_cursor += line_h
            bbox = (MARGIN, top, MARGIN + text_w, top + line_h)
        elif style.box == "row":
            cells = [c.strip() for c in line.text.split("|")]
            y += style.before
            top = y
            cell_w = content_w // max(1, len(cells))
            pad = 22
            bounds = (MARGIN, top, MARGIN + content_w, top + line_h + 2 * pad - 6)
            _draw_box(draw, style, bounds, profile)
            for i, cell in enumerate(cells):
                cx = MARGIN + i * cell_w + 16
                if i:
                    draw.line([MARGIN + i * cell_w, top, MARGIN + i * cell_w, bounds[3]],
                              fill=(150, 150, 150), width=2)  # fmt: skip
                draw.text((cx, top + pad - 4), visual(cell), fill=style.color, font=font)
            y = bounds[3]
            bbox = bounds
        else:
            max_w = content_w - indent - (44 if style.box != "none" else 0)
            wrapped = wrap(line.text, font, max_w)
            y += style.before
            pad = 22 if style.box != "none" else 0
            text_h = line_h * len(wrapped)
            text_w = max(int(font.getlength(visual(w))) for w in wrapped)
            top = y
            bounds = (x0, top, x0 + text_w, top + text_h)
            if style.box != "none":
                bounds = _box_bounds(style, x0, top, text_w, text_h, content_w, profile)
                _draw_box(draw, style, bounds, profile)
            ty = top + pad - (4 if style.box != "none" else 0)
            rtl = is_arabic_script(line.text)
            for w_line in wrapped:
                shown = visual(w_line)
                width = int(font.getlength(shown))
                if style.box in ("button", "stamp"):
                    tx = (bounds[0] + bounds[2]) // 2 - width // 2
                elif style.align == "center":
                    tx = MARGIN + content_w // 2 - width // 2
                elif style.align == "right" or rtl:
                    tx = PAGE_W - MARGIN - width - (pad + 10 if style.box != "none" else 0)
                else:
                    tx = x0 + pad + (10 if style.box != "none" else 0)
                draw.text((tx, ty), shown, fill=style.color, font=font)
                ty += line_h
            y = bounds[3] if style.box != "none" else top + text_h
            if style.align in ("left",) and not rtl and style.box == "none":
                bbox = (x0, top, x0 + text_w, top + text_h)
            else:
                bbox = bounds
        y += style.after
        n += 1
        blocks.append(
            PlacedBlock(
                id=f"p{page_no}b{n}", page=page_no, text=normalize(line.text),
                bbox=(round(bbox[0] / PAGE_W, 4), round(bbox[1] / height, 4),
                      round(min(bbox[2], PAGE_W) / PAGE_W, 4), round(bbox[3] / height, 4)),
                ref=line.ref, unclear=line.unclear, handwriting=line.handwriting,
            )  # fmt: skip
        )
    if profile.blur > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=profile.blur))
    if profile.contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(profile.contrast)
    if profile.brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(profile.brightness)
    img = _watermark(img, profile.watermark_angle)
    footer = SCREEN_FOOTER_TEXT if profile.kind == "screenshot" else FOOTER_TEXT
    _footer(ImageDraw.Draw(img), height, page_no, total, footer)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return RenderedPage(png=buf.getvalue(), blocks=blocks)


# --------------------------------------------------------------------------- templates → outputs

PROSE_ANALYSIS = ("summary_title", "summary_body", "summary_body_en", "clerk_need_en")
# Same shapes as WP2's contacts filter (AI_PROMPTS §11.3): URLs and bare domains, NANP phones.
_URL_RE = re.compile(r"(https?://\S+|www\.\S+|\b[\w-]+\.(gov|org|com|net|us|edu|info)\b)", re.I)
_PHONE_RE = re.compile(r"(\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}|\b\d{7,}\b)")
# AI_PROMPTS §5.0 rule 7 and §5.1.1 step 4, PRODUCT_SPEC §7.1 "Numbers": dates, times, amounts and
# numbers stay exactly as printed, in Latin letters and Western digits, even in a right-to-left
# language. The app may *add* a localized line (``DateInfo.localized_line``); prose never swaps
# one in. ``\d`` is every Unicode decimal digit, so this matches Eastern Arabic (U+0660–0669),
# Persian (U+06F0–06F9), Devanagari, Bengali, … runs.
_NON_WESTERN_DIGITS_RE = re.compile(r"(?:(?![0-9])\d)+")
_VERBATIM_DATE_KEYS = ("date_text", "time_text")


class TemplateError(Exception):
    pass


def _lines(raw_page: list[Any]) -> list[Line]:
    out: list[Line] = []
    for item in raw_page:
        if isinstance(item, str):
            out.append(Line(text=item, style="body"))
            continue
        style = str(item.get("style", "body"))
        if style not in STYLES:
            raise TemplateError(f"unknown style {style!r}")
        out.append(
            Line(
                text=str(item.get("text", "")), style=style, ref=item.get("ref"),
                unclear=bool(item.get("unclear", False)),
                handwriting=bool(item.get("handwriting", False)), gap=int(item.get("gap", 40)),
            )  # fmt: skip
        )
    return out


def _resolve(value: Any, refs: dict[str, str]) -> Any:
    """Replace every ``"@name"`` string (in lists or scalars) with the block id it names."""
    if isinstance(value, str) and value.startswith("@"):
        name = value[1:]
        if name not in refs:
            raise TemplateError(f"unknown block ref {value!r}")
        return refs[name]
    if isinstance(value, list):
        return [_resolve(v, refs) for v in value]
    return value


def _block_dicts(blocks: list[PlacedBlock]) -> list[dict[str, Any]]:
    return [
        {
            "id": b.id, "page": b.page, "text": b.text, "bbox": list(b.bbox),
            "is_handwriting": b.handwriting, "is_unclear": b.unclear,
        }  # fmt: skip
        for b in blocks
    ]


def _demand(raw: dict[str, Any], refs: dict[str, str], pages: dict[str, int]) -> dict[str, Any]:
    span_ids = _resolve(raw.get("span_ids", []), refs)
    d: dict[str, Any] = {
        "id": raw["id"], "kind": raw["kind"], "text": raw["text"],
        "value_verbatim": raw["value_verbatim"], "source_quote": raw["source_quote"],
        "span_ids": span_ids, "page": raw.get("page", pages.get(span_ids[0], 1) if span_ids else 1),
        "date_text": raw.get("date_text"), "time_text": raw.get("time_text"),
        "relative_rule_text": raw.get("relative_rule_text"),
        "anchor_span_id": _resolve(raw.get("anchor_span_id"), refs),
        "amount_text": raw.get("amount_text"), "currency": raw.get("currency"),
        "documents": list(raw.get("documents", [])), "role": raw.get("role"),
        "confidence": raw.get("confidence", "high"), "ambiguity_note": raw.get("ambiguity_note"),
    }  # fmt: skip
    if d["kind"] == "amount" and d["amount_text"] and not d["currency"]:
        d["currency"] = "USD"
    return d


def _plan_step(raw: dict[str, Any], refs: dict[str, str]) -> dict[str, Any]:
    return {
        "id": raw["id"], "text": raw["text"], "kind": raw["kind"],
        "resource_tags": list(raw.get("resource_tags", [])),
        "span_ids": _resolve(raw.get("span_ids", []), refs), "demand_id": raw.get("demand_id"),
    }  # fmt: skip


def _red_flag(raw: dict[str, Any], refs: dict[str, str], pages: dict[str, int]) -> dict[str, Any]:
    span_ids = _resolve(raw.get("span_ids", []), refs)
    return {
        "kind": raw["kind"], "text": raw["text"], "source_quote": raw.get("source_quote"),
        "span_ids": span_ids, "page": raw.get("page", pages.get(span_ids[0]) if span_ids else None),
    }  # fmt: skip


def analysis_out(tpl: dict[str, Any], lang: str, blocks: list[PlacedBlock],
                 page_texts: list[str]) -> dict[str, Any]:  # fmt: skip
    refs = {b.ref: b.id for b in blocks if b.ref}
    pages = {b.id: b.page for b in blocks}
    base = copy.deepcopy(tpl["out"]["base"])
    over = copy.deepcopy(tpl["out"].get(lang) or {}) if lang != "en" else {}
    doc_lang = tpl["language_of_document"]
    demands = [_demand(d, refs, pages) for d in base.get("demands", [])]
    for d in demands:
        for k, v in (over.get("demands") or {}).get(d["id"], {}).items():
            d[k] = v
    steps = [_plan_step(s, refs) for s in base.get("plan_steps", [])]
    for s in steps:
        for k, v in (over.get("plan_steps") or {}).get(s["id"], {}).items():
            s[k] = v
    glossary = [dict(g) for g in base.get("glossary", [])]
    for g in glossary:
        if g["term_as_written"] in (over.get("glossary") or {}):
            g["explanation"] = over["glossary"][g["term_as_written"]]
    flags = [_red_flag(r, refs, pages) for r in base.get("red_flags", [])]
    for i, text in enumerate(over.get("red_flags") or []):
        flags[i]["text"] = text
    if not base.get("blocks", True):  # unreadable page: nothing was read, nothing to translate
        translated = [{"page": i + 1, "text": ""} for i in range(len(page_texts))]
    elif lang == doc_lang or (lang == "en" and "translated_pages" not in base):
        translated = [{"page": i + 1, "text": t} for i, t in enumerate(page_texts)]
    else:
        source = over.get("translated_pages") if lang != "en" else base.get("translated_pages")
        if not source or len(source) != len(page_texts):
            raise TemplateError(f"{tpl['id']}: translated_pages for {lang} must cover every page")
        translated = [{"page": i + 1, "text": t} for i, t in enumerate(source)]
    out: dict[str, Any] = {
        "document_type": tpl["document_type"], "category": tpl["category"],
        "document_type_confidence": base.get("document_type_confidence", "high"),
        "sender_as_written": base.get("sender_as_written"),
        "sender_kind": base.get("sender_kind", "unknown"),
        "detected_language": base.get("detected_language", doc_lang),
        "translated_pages": translated,
        "summary_title": over.get("summary_title", base["summary_title"]),
        "summary_body": over.get("summary_body", base["summary_body"]),
        "summary_body_en": base.get("summary_body_en", base["summary_body"]),
        "summary_span_ids": _resolve(base.get("summary_span_ids", []), refs),
        "demands": demands, "plan_steps": steps, "glossary": glossary, "red_flags": flags,
        "questions_to_ask": over.get("questions_to_ask", base.get("questions_to_ask", [])),
        "clerk_need_en": base["clerk_need_en"],
        "emergency_terms_found": base.get("emergency_terms_found", []),
        "is_likely_scam": base.get("is_likely_scam", False),
        "scam_signals": base.get("scam_signals", []),
        "resource_tags": base.get("resource_tags", []),
        "institutions_as_written": base.get("institutions_as_written", []),
        "form_numbers": base.get("form_numbers", []),
        "geo_state": base.get("geo_state"), "geo_county": base.get("geo_county"),
        "geo_city": base.get("geo_city"), "geo_zip": base.get("geo_zip"),
        "legibility": base.get("legibility", "good"),
        "readable_reason": base.get("readable_reason"),
        "blocks": _block_dicts(blocks) if base.get("blocks", True) else [],
    }  # fmt: skip
    return out


def troubleshoot_out(tpl: dict[str, Any], lang: str) -> dict[str, Any]:
    base = copy.deepcopy(tpl["out"]["base"])
    over = copy.deepcopy(tpl["out"].get(lang) or {}) if lang != "en" else {}
    steps = [
        {
            "order": s["order"], "text": s["text"],
            "ui_target_as_written": s.get("ui_target_as_written"),
        }  # fmt: skip
        for s in base["steps"]
    ]
    for s in steps:
        if s["order"] in (over.get("steps") or {}):
            s["text"] = over["steps"][s["order"]]
    return {
        "screen_summary": over.get("screen_summary", base["screen_summary"]),
        "screen_text": base["screen_text"],
        "error_text_quoted": base.get("error_text_quoted"),
        "error_meaning": over.get("error_meaning", base["error_meaning"]),
        "steps": steps, "cautions": over.get("cautions", base.get("cautions", [])),
        "asks_for_credentials_or_payment": base.get("asks_for_credentials_or_payment", False),
        "is_likely_scam": base.get("is_likely_scam", False),
        "scam_signals": base.get("scam_signals", []),
        "needs_human_help": base.get("needs_human_help", False),
        "red_flags": base.get("red_flags", []), "resource_tags": base.get("resource_tags", []),
        "confidence": base.get("confidence", "high"),
    }  # fmt: skip


# --------------------------------------------------------------------------- validation


def _contains(haystack: str, needle: str) -> bool:
    return normalize(needle) in normalize(haystack)


def _span_text(blocks: dict[str, PlacedBlock], span_ids: list[str]) -> str:
    return " ".join(blocks[s].text for s in span_ids if s in blocks)


def _prose_contacts(text: str, transcript: str) -> str | None:
    """A phone number or URL in prose must also be printed on the paper (D-10)."""
    for pattern in (_URL_RE, _PHONE_RE):
        for m in pattern.finditer(text):
            if not _contains(transcript, m.group(0)):
                return m.group(0)
    return None


def _unprinted_digits(text: str, transcript: str) -> str | None:
    """A non-Western digit run in prose is allowed only when the paper prints it that way."""
    for m in _NON_WESTERN_DIGITS_RE.finditer(text):
        if m.group(0) not in transcript:
            return m.group(0)
    return None


@functools.cache
def _language_rows() -> dict[str, dict[str, Any]]:
    """``data/languages.yaml`` rows (script, ``name_en``, …) per language tag."""
    with (DATA / "languages.yaml").open(encoding="utf-8") as fh:
        table: dict[str, dict[str, Any]] = yaml.safe_load(fh)
    return {str(tag): dict(row) for tag, row in table.items()}


def _printed_values(demands: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """``(key, value)`` for every printed ``date_text`` / ``time_text`` of the English demands."""
    found: list[tuple[str, str]] = []
    for d in demands:
        for key in _VERBATIM_DATE_KEYS:
            value = d.get(key)
            if value and (key, value) not in found:
                found.append((key, str(value)))
    return found


def _repeats_printed(
    where: str, label: str, english: str, translated: str, printed: list[tuple[str, str]]
) -> list[str]:
    return [
        f"{where} {label}: text does not repeat the printed {key} {value!r} verbatim"
        for key, value in printed
        if _contains(english, value) and not _contains(translated, value)
    ]


def check_printed_dates(
    fid: str, lang: str, out: dict[str, Any], base: dict[str, Any] | None
) -> list[str]:
    """Rule 7 "exactly as printed, in Latin letters and Western digits" in EVERY output language
    (Spanish too, not only a right-to-left one; PRODUCT_SPEC §7.1 "Numbers", D-26): wherever the
    English sentence repeats a printed ``date_text`` / ``time_text``, the translated sentence
    repeats it verbatim (``October 7, 2026``, never ``7 de octubre de 2026`` or ``٧ أكتوبر ٢٠٢٦``).
    Checked over the summary, demands, plan steps, questions and translated pages."""
    if base is None or lang == "en":
        return []
    where = f"{fid}/out.{lang}.json"
    printed = _printed_values(base["demands"])
    pairs: list[tuple[str, str, str]] = [
        ("summary_title", base["summary_title"], out["summary_title"]),
        ("summary_body", base["summary_body"], out["summary_body"]),
    ]
    en_demands = {d["id"]: d["text"] for d in base["demands"]}
    pairs += [(f"demand {d['id']}", en_demands.get(d["id"], ""), d["text"]) for d in out["demands"]]
    en_steps = {s["id"]: s["text"] for s in base["plan_steps"]}
    pairs += [(f"step {s['id']}", en_steps.get(s["id"], ""), s["text"]) for s in out["plan_steps"]]
    en_questions, questions = base["questions_to_ask"], out["questions_to_ask"]
    if len(en_questions) == len(questions):
        asked = zip(en_questions, questions, strict=True)
        pairs += [(f"question {i + 1}", q_en, q) for i, (q_en, q) in enumerate(asked)]
    en_pages = {p["page"]: p["text"] for p in base["translated_pages"]}
    pairs += [
        (f"translated page {p['page']}", en_pages.get(p["page"], ""), p["text"])
        for p in out["translated_pages"]
    ]
    errors: list[str] = []
    for label, english, translated in pairs:
        errors += _repeats_printed(where, label, english, translated, printed)
    return errors


# --------------------------------------------------------------------------- clerk card recordings


def clerk_card_english(tpl: dict[str, Any], lang: str) -> tuple[str, str]:
    """(English clerk card, need-line source) exactly as ``analysis/clerk.build_clerk_message``
    composes it for this fixture read in ``lang`` (D-18): the fixed template around the paper's
    sender and the AI need line ``clerk_need_en``."""
    base = tpl["out"]["base"]
    need, source = clerk.choose_need_line(base.get("clerk_need_en"), "")
    name = str((_language_rows().get(lang) or {}).get("name_en") or lang)
    sender = clerk.checked_sender(base.get("sender_as_written"), None)
    document = clerk.document_phrase(DocumentType(tpl["document_type"]), sender)
    return clerk.TEMPLATE.format(language=name, document=document, need=need), source


def clerk_out(
    tpl: dict[str, Any], lang: str, transcript: str, meta: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[str]]:
    """``clerk.<lang>.json``: the recorded ``clerk_translate`` answer for a readable document in a
    recorded non-English language (AI_PROMPTS §5.5.4). ``out.<lang>.clerk_cards`` in the template
    lists ``{english, translated}`` pairs; the entry whose ``english`` is the card the pipeline
    builds today is written. A missing or stale entry is an error, so the zero-key demo never
    falls back to the ``⟦tag⟧`` pseudo card for a recorded language and never shows a
    translation of a different English card."""
    fid = str(tpl["id"])
    base = tpl["out"]["base"]
    if lang == "en" or tpl.get("kind", "document") != "document" or not base.get("blocks", True):
        return None, []
    where = f"{fid}/clerk.{lang}.json"
    english, source = clerk_card_english(tpl, lang)
    if source != "ai":
        return None, [
            f"{where}: clerk_need_en fails the D-18 checks (contact filter, phrasing lint, 200 "
            "characters); the pipeline would print the fixed need line instead"
        ]
    cards = (tpl["out"].get(lang) or {}).get("clerk_cards") or []
    wanted = " ".join(english.split())
    found = [c for c in cards if " ".join(str(c.get("english") or "").split()) == wanted]
    if not found:
        return None, [
            f"{where}: no out.{lang}.clerk_cards entry translates the current English card "
            f"{english!r}; add its translation (built from sender_as_written and clerk_need_en)"
        ]
    translated = str(found[0].get("translated") or "").strip()
    errors: list[str] = []
    if not translated or "⟦" in translated or " ".join(translated.split()) == wanted:
        errors.append(f"{where}: the translated card is empty, English or pseudo text")
    hit = _prose_contacts(translated, transcript)
    if hit:
        errors.append(f"{where}: contact {hit!r} in the translated card is not printed")
    localized = _unprinted_digits(translated, transcript)
    if localized:
        errors.append(f"{where}: localized digits {localized!r}; keep Western digits")
    printed = _printed_values(base.get("demands") or [])
    errors += _repeats_printed(where, "translated card", english, translated, printed)
    body = {
        "_meta": meta, "task": "clerk_translate", "language_tag": lang, "english": english,
        "translated": translated,
    }  # fmt: skip
    return body, errors


def check_analysis(
    fid: str,
    lang: str,
    out: dict[str, Any],
    blocks: list[PlacedBlock],
    transcript: str,
    base: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    where = f"{fid}/out.{lang}.json"
    try:
        AnalysisModelOut.model_validate({k: v for k, v in out.items() if k != "_meta"})
    except ValidationError as exc:
        errors.append(f"{where}: {exc.error_count()} schema error(s): {exc.errors()[0]}")
        return errors
    by_id = {b.id: b for b in blocks}
    demand_ids = {d["id"] for d in out["demands"]}
    for d in out["demands"]:
        did = f"{where} demand {d['id']}"
        unknown = [s for s in d["span_ids"] if s not in by_id]
        if unknown or not d["span_ids"]:
            errors.append(f"{did}: span_ids {d['span_ids']} unknown or empty")
            continue
        span = _span_text(by_id, d["span_ids"])
        if not _contains(span, d["source_quote"]):
            errors.append(f"{did}: source_quote is not verbatim in its span: {d['source_quote']!r}")
        for key in ("value_verbatim", "date_text", "time_text", "relative_rule_text",
                    "amount_text"):  # fmt: skip
            if d.get(key) and not _contains(d["source_quote"], d[key]):
                errors.append(f"{did}: {key}={d[key]!r} is not inside source_quote")
        if d.get("anchor_span_id") and d["anchor_span_id"] not in by_id:
            errors.append(f"{did}: anchor_span_id {d['anchor_span_id']!r} unknown")
        if d.get("role") and d["role"] not in _ROLES:
            errors.append(f"{did}: role {d['role']!r} is not a Demand role")
        if d["page"] != by_id[d["span_ids"][0]].page:
            errors.append(f"{did}: page {d['page']} does not match its first span")
        for doc in d["documents"]:
            if not _contains(transcript, doc):
                errors.append(f"{did}: documents item {doc!r} is not printed on the paper")
    for rf in out["red_flags"]:
        rid = f"{where} red_flag {rf['kind']}"
        if any(s not in by_id for s in rf["span_ids"]):
            errors.append(f"{rid}: unknown span id in {rf['span_ids']}")
        elif rf.get("source_quote") and not _contains(
            _span_text(by_id, rf["span_ids"]), rf["source_quote"]
        ):
            errors.append(f"{rid}: source_quote not verbatim: {rf['source_quote']!r}")
    if any(s not in by_id for s in out["summary_span_ids"]):
        errors.append(f"{where}: summary_span_ids {out['summary_span_ids']} has unknown ids")
    for step in out["plan_steps"]:
        sid = f"{where} step {step['id']}"
        if any(s not in by_id for s in step["span_ids"]):
            errors.append(f"{sid}: unknown span id in {step['span_ids']}")
        if step.get("demand_id") and step["demand_id"] not in demand_ids:
            errors.append(f"{sid}: demand_id {step['demand_id']!r} unknown")
        bad = [t for t in step["resource_tags"] if t not in _VALID_TAGS]
        if bad:
            errors.append(f"{sid}: resource_tags {bad} are not ResourceTag values")
    bad_tags = [t for t in out["resource_tags"] if t not in _VALID_TAGS]
    if bad_tags:
        errors.append(f"{where}: resource_tags {bad_tags} are not ResourceTag values")
    for field_name in ("sender_as_written",):
        value = out.get(field_name)
        if value and not _contains(transcript, value):
            errors.append(f"{where}: {field_name} {value!r} is not printed on the paper")
    for inst in out["institutions_as_written"]:
        if not _contains(transcript, inst):
            errors.append(f"{where}: institution {inst!r} is not printed on the paper")
    for form in out["form_numbers"]:
        if form.replace("-", "").lower() not in normalize(transcript).replace("-", "").lower():
            errors.append(f"{where}: form number {form!r} is not printed on the paper")
    for g in out["glossary"]:
        if normalize(g["term_as_written"]).lower() not in normalize(transcript).lower():
            errors.append(f"{where}: glossary term {g['term_as_written']!r} not on the paper")
    prose = [out[k] for k in PROSE_ANALYSIS if out.get(k)]
    prose += [d["text"] for d in out["demands"]] + [s["text"] for s in out["plan_steps"]]
    prose += [g["explanation"] for g in out["glossary"]] + list(out["questions_to_ask"])
    prose += [rf["text"] for rf in out["red_flags"]]
    for text in prose:
        hit = _prose_contacts(text, transcript)
        if hit:
            errors.append(f"{where}: contact {hit!r} in prose is not printed on the paper")
    for text in prose + [p["text"] for p in out["translated_pages"]]:
        localized = _unprinted_digits(text, transcript)
        if localized:
            errors.append(f"{where}: localized digits {localized!r} in prose; keep Western digits")
    errors += check_printed_dates(fid, lang, out, base)
    return errors


def check_troubleshoot(fid: str, lang: str, out: dict[str, Any], transcript: str) -> list[str]:
    errors: list[str] = []
    where = f"{fid}/out.{lang}.json"
    try:
        TroubleshootModelOut.model_validate({k: v for k, v in out.items() if k != "_meta"})
    except ValidationError as exc:
        errors.append(f"{where}: {exc.error_count()} schema error(s): {exc.errors()[0]}")
        return errors
    for line in out["screen_text"]:
        if not _contains(transcript, line):
            errors.append(f"{where}: screen_text {line!r} is not on the screenshot")
    for step in out["steps"]:
        target = step.get("ui_target_as_written")
        if target and target not in out["screen_text"]:
            errors.append(f"{where}: step {step['order']} target {target!r} not in screen_text")
    quoted = out.get("error_text_quoted")
    if quoted and not _contains(transcript, quoted):
        errors.append(f"{where}: error_text_quoted {quoted!r} is not on the screenshot")
    bad_tags = [t for t in out["resource_tags"] if t not in _VALID_TAGS]
    if bad_tags:
        errors.append(f"{where}: resource_tags {bad_tags} are not ResourceTag values")
    prose = [out["screen_summary"], out["error_meaning"], *out["cautions"]]
    for text in prose + [s["text"] for s in out["steps"]]:
        localized = _unprinted_digits(text, transcript)
        if localized:
            errors.append(f"{where}: localized digits {localized!r} in prose; keep Western digits")
    return errors


# --------------------------------------------------------------------------- build


@dataclass
class Built:
    id: str
    kind: str
    files: dict[str, bytes]
    dhash: int


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def prompts_version() -> str:
    """``prompt_loader.prompts_version()`` — the one ``ai/prompts/VERSION`` parser."""
    if not prompt_loader.VERSION_FILE.is_file():
        return DEFAULT_PROMPTS_VERSION
    try:
        return prompt_loader.prompts_version()
    except prompt_loader.PromptError as exc:
        raise TemplateError(str(exc)) from exc


def is_recording(path: Path) -> bool:
    """True for an ``out.<lang>.json`` written by ``ai/recording.py`` (kept for human review)."""
    if not (path.name.startswith("out.") and path.name.endswith(".json")):
        return False
    try:
        meta = json.loads(path.read_text("utf-8")).get("_meta")
    except (OSError, ValueError, AttributeError):
        return False
    return isinstance(meta, dict) and meta.get("recorded_by") == "recording_provider"


def build_fixture(tpl_dir: Path) -> Built:
    with (tpl_dir / "template.yaml").open(encoding="utf-8") as fh:
        tpl: dict[str, Any] = yaml.safe_load(fh)
    fid = str(tpl["id"])
    if fid != tpl_dir.name:
        raise TemplateError(f"{tpl_dir.name}: template id {fid!r} does not match the folder")
    kind = str(tpl.get("kind", "document"))
    profile = RenderProfile.from_yaml(tpl.get("render"), kind)
    raw_pages: list[list[Any]] = tpl["pages"]
    total = len(raw_pages)
    rendered = [
        render_page(_lines(page), profile, i + 1, total) for i, page in enumerate(raw_pages)
    ]
    blocks = [b for r in rendered for b in r.blocks]
    page_texts = ["\n".join(b.text for b in r.blocks) for r in rendered]
    transcript = "\n\n".join(page_texts) + "\n"
    langs: list[str] = list(tpl.get("languages", ["en"]))
    if langs[0] != "en":
        raise TemplateError(f"{fid}: languages must start with en")
    files: dict[str, bytes] = {}
    for i, r in enumerate(rendered):
        files[f"page-{i + 1}.png"] = r.png
    files["transcript.txt"] = transcript.encode("utf-8")
    meta = {
        "prompts_version": prompts_version(), "recorded_by": "hand",
        "recorded_on": RECORDED_ON, "model_id": "hand",
    }  # fmt: skip
    errors: list[str] = []
    en_body: dict[str, Any] | None = None  # langs[0] is en: the reference for printed dates
    for lang in langs:
        if kind == "screenshot":
            body = troubleshoot_out(tpl, lang)
            errors += check_troubleshoot(fid, lang, body, transcript)
        else:
            body = analysis_out(tpl, lang, blocks, page_texts)
            errors += check_analysis(fid, lang, body, blocks, transcript, base=en_body)
        if lang == "en":
            en_body = body
        files[f"out.{lang}.json"] = _json_bytes({"_meta": meta, **body})
        card, card_errors = clerk_out(tpl, lang, transcript, meta)
        errors += card_errors
        if card is not None:
            files[f"clerk.{lang}.json"] = _json_bytes(card)
    if errors:
        raise TemplateError("\n".join(errors))
    page_hashes = [dhash(r.png) for r in rendered]
    manifest: dict[str, Any] = {
        "id": fid,
        "title_key": f"fixture.{fid}",
        "title_en": tpl["title_en"],
        "document_type": tpl["document_type"],
        "category": tpl["category"],
        "language_of_document": tpl["language_of_document"],
        "pages": len(rendered),
        "kind": kind,
        "available_target_languages": langs,
        "thumbnail_url": f"/v1/demo/fixtures/{fid}/pages/1",
        "dhash": hash_to_hex(page_hashes[0]),
        "page_dhashes": [hash_to_hex(h) for h in page_hashes],
        "today": str(tpl["today"]),
        "recorded_on": RECORDED_ON,
        "expected": tpl.get("expected") or {},
    }
    files["manifest.yaml"] = yaml.safe_dump(
        manifest, sort_keys=False, allow_unicode=True, width=100
    ).encode("utf-8")
    return Built(id=fid, kind=kind, files=files, dhash=page_hashes[0])


def check_distances(built: list[Built], max_hamming: int) -> list[str]:
    """Same-kind fixtures must be far apart, or the mock could confuse two sample papers."""
    problems: list[str] = []
    for i, a in enumerate(built):
        for b in built[i + 1 :]:
            if a.kind != b.kind:
                continue
            d = hamming(a.dhash, b.dhash)
            if d <= max_hamming:
                problems.append(f"{a.id} vs {b.id}: dHash distance {d} <= {max_hamming}")
    return problems


def print_distances(built: list[Built]) -> None:
    width = max(len(b.id) for b in built)
    for a in built:
        row = " ".join(f"{hamming(a.dhash, b.dhash):3d}" for b in built)
        print(f"{a.id:<{width}} {row}")
    pairs = [
        (hamming(a.dhash, b.dhash), a.id, b.id)
        for i, a in enumerate(built)
        for b in built[i + 1 :]
    ]
    if pairs:
        d, x, y = min(pairs)
        print(f"min pairwise distance: {d} ({x} vs {y})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when any byte would change")
    parser.add_argument("--only", action="append", default=[], help="fixture id (repeatable)")
    parser.add_argument("--distances", action="store_true", help="print the pairwise dHash matrix")
    parser.add_argument("--max-hamming", type=int, default=10)
    args = parser.parse_args(argv)
    dirs = sorted(p.parent for p in FIXTURES_DIR.glob("*/template.yaml"))
    if args.only:
        dirs = [d for d in dirs if d.name in args.only]
    if not dirs:
        print("no templates found", file=sys.stderr)
        return 1
    built: list[Built] = []
    failures = 0
    for d in dirs:
        try:
            built.append(build_fixture(d))
        except TemplateError as exc:
            failures += 1
            print(f"TEMPLATE ERROR in {d.name}:\n{exc}", file=sys.stderr)
    if failures:
        return 1
    if not args.only:
        for problem in check_distances(built, args.max_hamming):
            failures += 1
            print(f"dHash collision: {problem}", file=sys.stderr)
    if args.distances:
        print_distances(built)
    if failures:
        return 1
    drift: list[str] = []
    kept: list[str] = []
    changed = 0
    for b in built:
        target = FIXTURES_DIR / b.id
        for name, content in b.files.items():
            path = target / name
            if path.is_file() and path.read_bytes() == content:
                continue
            if args.check:
                drift.append(f"{'differs' if path.is_file() else 'missing'}: {path.name} in {b.id}")
            elif is_recording(path):
                kept.append(f"{b.id}/{path.name}")
            else:
                path.write_bytes(content)
                changed += 1
        for path in sorted(target.iterdir()):
            if path.name in b.files or path.name == "template.yaml" or path.name == ".DS_Store":
                continue
            if args.check:
                drift.append(f"stray: {path.name} in {b.id}")
            elif is_recording(path):
                kept.append(f"{b.id}/{path.name}")
            else:
                path.unlink()
                changed += 1
    for name in kept:
        # A RecordingProvider capture awaits human review (AI_PROMPTS §10.4): never overwrite or
        # delete it here; the reviewer folds it into template.yaml or deletes it by hand.
        print(f"kept recording for review: {name}", file=sys.stderr)
    if args.check:
        for line in drift:
            print(line, file=sys.stderr)
        if drift:
            print(f"{len(drift)} fixture file(s) out of date; rerun the script", file=sys.stderr)
            return 1
        print(f"fixtures in sync ({len(built)} fixtures)")
        return 0
    print(f"{changed} file(s) written for {len(built)} fixture(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
