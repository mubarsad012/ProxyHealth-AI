"""Font registry for the quick-sheet PDF (ARCHITECTURE §2.1 ``quicksheet/fonts.py``; D-26).

Maps a language pack's ``font_hint`` (``data/languages.yaml``) to the static Noto TTFs shipped in
``data/fonts/`` and registers each family with reportlab **once** per process. Unknown or missing
hints fall back to the tag's row in ``data/languages.yaml`` (so ``prs`` without a hint still gets
Noto Naskh Arabic), then Noto Sans; CJK tags (whose ``font_hint`` is ``null``) use reportlab's
built-in CID fonts so the viewer supplies the glyphs. Nothing here is user content.

reportlab draws through the font's cmap only (no OpenType GSUB/GPOS), so Arabic script reaches it
pre-shaped as Arabic Presentation Forms (U+FB50–FEFF, ``arabic_reshaper``). Noto Nastaliq Urdu
maps none of those code points (it shapes through GSUB), so every Urdu line would be invisible:
the PDF substitutes Noto Naskh Arabic for it (``PDF_SUBSTITUTES``); the app UI keeps Nastaliq.
"""

from __future__ import annotations

import logging
import threading
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont

from proxyhealth_api.settings import DATA_DIR

logger = logging.getLogger("proxyhealth.quicksheet")

FONT_DIR: Path = DATA_DIR / "fonts"
DEFAULT_FAMILY = "NotoSans"

# font_hint → (regular file, bold file). The nine families of DECISIONS §14 (2026-09-27).
FAMILIES: dict[str, tuple[str, str]] = {
    "NotoSans": ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf"),
    "NotoNaskhArabic": ("NotoNaskhArabic-Regular.ttf", "NotoNaskhArabic-Bold.ttf"),
    "NotoNastaliqUrdu": ("NotoNastaliqUrdu-Regular.ttf", "NotoNastaliqUrdu-Bold.ttf"),
    "NotoSansEthiopic": ("NotoSansEthiopic-Regular.ttf", "NotoSansEthiopic-Bold.ttf"),
    "NotoSansMyanmar": ("NotoSansMyanmar-Regular.ttf", "NotoSansMyanmar-Bold.ttf"),
    "NotoSansDevanagari": ("NotoSansDevanagari-Regular.ttf", "NotoSansDevanagari-Bold.ttf"),
    "NotoSansBengali": ("NotoSansBengali-Regular.ttf", "NotoSansBengali-Bold.ttf"),
    "NotoSansGurmukhi": ("NotoSansGurmukhi-Regular.ttf", "NotoSansGurmukhi-Bold.ttf"),
    "NotoSansHanifiRohingya": (
        "NotoSansHanifiRohingya-Regular.ttf",
        "NotoSansHanifiRohingya-Bold.ttf",
    ),
}

# Line-height multipliers (D-26: Nastaliq needs 2.0; the other scripts read well at 1.45).
LEADING: dict[str, float] = {
    "NotoNastaliqUrdu": 2.0,
    "NotoSansMyanmar": 1.7,
    "NotoSansBengali": 1.6,
}
DEFAULT_LEADING = 1.45

# Families whose PDF drawing needs a different face (see the module docstring).
PDF_SUBSTITUTES: dict[str, str] = {"NotoNastaliqUrdu": "NotoNaskhArabic"}
# The face that covers every Presentation Form ``arabic_reshaper`` emits (and all of ASCII).
ARABIC_FAMILY = "NotoNaskhArabic"
LANGUAGES_FILE: Path = DATA_DIR / "languages.yaml"

# CJK primary subtags → reportlab built-in CID fonts (no file needed; viewer supplies glyphs).
CID_FONTS: dict[str, str] = {"zh": "STSong-Light", "ja": "HeiseiMin-W3", "ko": "HYSMyeongJo-Medium"}

_lock = threading.Lock()
_registered: dict[str, FontPair] = {}


@dataclass(frozen=True)
class FontPair:
    """Registered reportlab face names for one family."""

    family: str
    regular: str
    bold: str
    leading: float = DEFAULT_LEADING

    @property
    def embedded(self) -> bool:
        """True when the faces are TTFs from ``data/fonts`` (CID and Helvetica are not)."""
        return self.family in FAMILIES


def _register_ttf(name: str, filename: str) -> bool:
    if name in pdfmetrics.getRegisteredFontNames():
        return True
    path = FONT_DIR / filename
    if not path.is_file():
        logger.warning("font file missing: %s", path)
        return False
    pdfmetrics.registerFont(TTFont(name, str(path)))
    return True


def register_family(family: str) -> FontPair | None:
    """Register ``family`` (regular + bold) once; ``None`` when its files are not on disk."""
    with _lock:
        cached = _registered.get(family)
        if cached is not None:
            return cached
        files = FAMILIES.get(family)
        if files is None:
            return None
        regular_name = family
        bold_name = f"{family}-Bold"
        if not _register_ttf(regular_name, files[0]):
            return None
        bold_ok = _register_ttf(bold_name, files[1])
        pair = FontPair(
            family=family,
            regular=regular_name,
            bold=bold_name if bold_ok else regular_name,
            leading=LEADING.get(family, DEFAULT_LEADING),
        )
        _registered[family] = pair
        return pair


def _register_cid(primary: str) -> FontPair | None:
    name = CID_FONTS.get(primary)
    if name is None:
        return None
    with _lock:
        cached = _registered.get(name)
        if cached is not None:
            return cached
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont(name))
        pair = FontPair(family=name, regular=name, bold=name, leading=DEFAULT_LEADING)
        _registered[name] = pair
        return pair


@lru_cache(maxsize=1)
def _language_hints() -> dict[str, str | None]:
    """``data/languages.yaml`` tag (casefolded) → ``font_hint``; empty when the file is absent."""
    try:
        raw = yaml.safe_load(LANGUAGES_FILE.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        logger.warning("languages.yaml unreadable at %s; font_for uses hints only", LANGUAGES_FILE)
        return {}
    out: dict[str, str | None] = {}
    for tag, row in raw.items():
        hint = row.get("font_hint") if isinstance(row, dict) else None
        out[str(tag).casefold()] = str(hint) if hint else None
    return out


def hint_for_language(language_tag: str) -> str | None:
    """The ``font_hint`` of ``language_tag`` (exact tag first, then its primary subtag)."""
    hints = _language_hints()
    tag = language_tag.strip().casefold()
    if tag in hints:
        return hints[tag]
    return hints.get(tag.split("-")[0])


def _resolve(family: str | None) -> FontPair | None:
    if not family:
        return None
    family = family.strip()
    return register_family(PDF_SUBSTITUTES.get(family, family))


def font_for(font_hint: str | None, language_tag: str) -> FontPair:
    """Resolve the request's ``font_hint``/``language_tag`` to registered faces (never raises).

    Order: the hinted Noto family (Nastaliq → Naskh, see ``PDF_SUBSTITUTES``) → the tag's
    ``languages.yaml`` family → a CID font for CJK tags → Noto Sans → Helvetica (only if the font
    directory is missing entirely). ``render`` additionally switches to ``arabic_font()`` when
    the chosen face lacks glyphs for the request's Arabic-script text (``missing_glyphs``).
    """
    pair = _resolve(font_hint) or _resolve(hint_for_language(language_tag))
    if pair is not None:
        return pair
    primary = language_tag.split("-")[0].lower()
    cid = _register_cid(primary)
    if cid is not None:
        return cid
    fallback = register_family(DEFAULT_FAMILY)
    if fallback is not None:
        return fallback
    return FontPair(family="Helvetica", regular="Helvetica", bold="Helvetica-Bold")


def arabic_font() -> FontPair | None:
    """Noto Naskh Arabic (``None`` when its files are missing)."""
    return register_family(ARABIC_FAMILY)


def missing_glyphs(pair: FontPair, text: str) -> set[str]:
    """Characters of already-shaped ``text`` that ``pair``'s regular face cannot draw.

    Whitespace and format characters (ZWJ/ZWNJ, bidi marks) are ignored. CID and Helvetica faces
    are not embedded, so nothing can be checked for them and the result is empty.
    """
    if not pair.embedded:
        return set()
    face = pdfmetrics.getFont(pair.regular).face
    cmap: dict[int, int] = face.charToGlyph
    return {
        ch
        for ch in set(text)
        if ord(ch) not in cmap and not ch.isspace() and unicodedata.category(ch) != "Cf"
    }


def latin_font() -> FontPair:
    """Noto Sans for the English sub-headers and the footer meta line (Helvetica if missing)."""
    pair = register_family(DEFAULT_FAMILY)
    return pair or FontPair(family="Helvetica", regular="Helvetica", bold="Helvetica-Bold")


__all__ = [
    "ARABIC_FAMILY",
    "CID_FONTS",
    "DEFAULT_FAMILY",
    "FAMILIES",
    "FONT_DIR",
    "PDF_SUBSTITUTES",
    "FontPair",
    "arabic_font",
    "font_for",
    "hint_for_language",
    "latin_font",
    "missing_glyphs",
    "register_family",
]
