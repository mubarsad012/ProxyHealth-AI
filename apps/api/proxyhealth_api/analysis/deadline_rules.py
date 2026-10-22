"""Deadline rules — the only place dates are computed (D-11; AI_PROMPTS §11.4; TAXONOMY §5.3).

The model never computes a date: it records ``date_text`` as printed, or ``relative_rule_text`` +
``anchor_span_id``. This module turns verified demands into ``Demand.date``:

* ``stated`` — deterministic parse of the printed date (regex table: US numeric formats, ISO,
  month names in the 26 bundled languages, CJK/Vietnamese numeric forms; 2-digit year → 2000+;
  no ``dateutil`` guessing). Exactly one date → ``value_iso``; otherwise ``value_iso=None`` and
  ``confidence=low`` (a numeric ``03/04`` ambiguity also appends ``demand.ambiguous_date``).
* ``estimated`` — only when a seeded rule's ``pattern`` matches the printed relative phrase, the
  anchor (``anchor_span_id``) is a *verified stated* demand whose ``role == rule.anchor_role``, the
  document type is in ``applies_to_doc_types`` (an ``other_notice`` also needs the rule's
  category, ``OTHER_NOTICE_RULE_CATEGORY``) and ``valid_until`` has not passed. Business days
  skip weekends and the federal-holiday table below.
* ``unresolved`` — anything else; the client shows "Ask the sender which date this means."

A printed date on the same demand always wins. Eviction papers never receive an estimate. A
verified ``amount``/``document_requested``/``action`` demand with a date role gets a ``stated``
date only from a ``date_text`` printed inside its quote (``resolve_carried``), never an estimate.
``time_text`` is kept only when it sits in the verified quote.

``DateInfo.localized_line`` is the line the app *adds* under a date (D-26, never a substitute
for the printed value): for a ``stated`` date the ISO day in the pack's own digits (Persian,
Eastern Arabic …; ``None`` for Western-digit packs); for an ``estimated`` date — which is printed
nowhere — the estimate written the way the paper prints its anchor date, in Western digits and
English month names ("November 13, 2026", or "11/13/2026" when the anchor is printed
"10/14/2026"), for every language, so the client can show "About {date} (estimate)" on the demand
row (``estimate_text``). Pure functions with an injected ``today``; nothing logged.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from proxyhealth_api.analysis.i18n import Translator
from proxyhealth_api.analysis.transcript import Transcript
from proxyhealth_api.analysis.urgency import ANY_DRIVING
from proxyhealth_api.analysis.verify import ascii_digits, check_value, verify_span
from proxyhealth_api.contracts.analysis import DateInfo, Demand
from proxyhealth_api.contracts.enums import (
    Confidence,
    DateFormat,
    DateKind,
    DemandKind,
    DigitSystem,
    DocumentCategory,
    DocumentType,
)
from proxyhealth_api.contracts.model_out import DemandOut
from proxyhealth_api.contracts.rules import DeadlineRule

AMBIGUOUS_DATE_KEY = "demand.ambiguous_date"
DATED_KINDS = frozenset({DemandKind.deadline, DemandKind.relative_deadline, DemandKind.appointment})
# Kinds that may carry a printed date for a date role ("return the form by …", "prepay … by …").
DATE_CARRYING_KINDS = frozenset(
    {DemandKind.amount, DemandKind.document_requested, DemandKind.action}
)
NEVER_ESTIMATE_TYPES = frozenset({DocumentType.pay_or_quit, DocumentType.eviction_summons})
# DOCUMENT_TAXONOMY §5.3: on the catch-all ``other_notice`` (also the scam re-type target) these
# rules apply only to a paper of this category, so a debt collector's "within 30 days" never gets
# an estimate cited to the OSHA retaliation rule.
OTHER_NOTICE_RULE_CATEGORY: Mapping[str, DocumentCategory] = {
    "eeoc_180_300d": DocumentCategory.employment,
    "osha_retaliation_30d": DocumentCategory.employment,
}

# --- month names (Gregorian) in the 26 bundled languages -----------------------------------------
# Each entry: month number → names/abbreviations as printed. Matching is case-insensitive after
# NFKC. A token that means different months in different languages (Portuguese "out" = October,
# Haitian "out" = August) is only accepted when the caller names the language.
_MONTHS: dict[str, dict[int, tuple[str, ...]]] = {
    "en": {
        1: ("january", "jan"), 2: ("february", "feb"), 3: ("march", "mar"), 4: ("april", "apr"),
        5: ("may",), 6: ("june", "jun"), 7: ("july", "jul"), 8: ("august", "aug"),
        9: ("september", "sept", "sep"), 10: ("october", "oct"), 11: ("november", "nov"),
        12: ("december", "dec"),
    },
    "es": {
        1: ("enero", "ene"), 2: ("febrero",), 3: ("marzo",), 4: ("abril", "abr"), 5: ("mayo",),
        6: ("junio",), 7: ("julio",), 8: ("agosto", "ago"), 9: ("septiembre", "setiembre"),
        10: ("octubre",), 11: ("noviembre",), 12: ("diciembre", "dic"),
    },
    "fr": {
        1: ("janvier", "janv"), 2: ("février", "fevrier", "févr", "fevr"), 3: ("mars",),
        4: ("avril", "avr"), 5: ("mai",), 6: ("juin",), 7: ("juillet", "juil"),
        8: ("août", "aout"), 9: ("septembre",), 10: ("octobre",), 11: ("novembre",),
        12: ("décembre", "decembre", "déc"),
    },
    "pt-BR": {
        1: ("janeiro",), 2: ("fevereiro", "fev"), 3: ("março", "marco"), 4: ("abril",),
        5: ("maio",), 6: ("junho",), 7: ("julho",), 8: ("agosto",), 9: ("setembro", "set"),
        10: ("outubro", "out"), 11: ("novembro",), 12: ("dezembro", "dez"),
    },
    "tl": {
        1: ("enero",), 2: ("pebrero",), 3: ("marso",), 4: ("abril",), 5: ("mayo",),
        6: ("hunyo",), 7: ("hulyo",), 8: ("agosto",), 9: ("setyembre",), 10: ("oktubre",),
        11: ("nobyembre",), 12: ("disyembre",),
    },
    "ht": {
        1: ("janvye",), 2: ("fevriye",), 3: ("mas",), 4: ("avril",), 5: ("me",), 6: ("jen",),
        7: ("jiyè", "jiye"), 8: ("out",), 9: ("septanm",), 10: ("oktòb", "oktob"),
        11: ("novanm",), 12: ("desanm",),
    },
    "ru": {
        1: ("января", "январь"), 2: ("февраля", "февраль"), 3: ("марта", "март"),
        4: ("апреля", "апрель"), 5: ("мая", "май"), 6: ("июня", "июнь"), 7: ("июля", "июль"),
        8: ("августа", "август"), 9: ("сентября", "сентябрь"), 10: ("октября", "октябрь"),
        11: ("ноября", "ноябрь"), 12: ("декабря", "декабрь"),
    },
    "uk": {
        1: ("січня", "січень"), 2: ("лютого", "лютий"), 3: ("березня", "березень"),
        4: ("квітня", "квітень"), 5: ("травня", "травень"), 6: ("червня", "червень"),
        7: ("липня", "липень"), 8: ("серпня", "серпень"), 9: ("вересня", "вересень"),
        10: ("жовтня", "жовтень"), 11: ("листопада", "листопад"), 12: ("грудня", "грудень"),
    },
    "ar": {
        1: ("يناير", "كانون الثاني"), 2: ("فبراير", "شباط"), 3: ("مارس", "آذار"),
        4: ("أبريل", "ابريل", "إبريل", "نيسان"), 5: ("مايو", "أيار"), 6: ("يونيو", "حزيران"),
        7: ("يوليو", "تموز"), 8: ("أغسطس", "اغسطس", "آب"), 9: ("سبتمبر", "أيلول"),
        10: ("أكتوبر", "اكتوبر", "تشرين الأول"), 11: ("نوفمبر", "تشرين الثاني"),
        12: ("ديسمبر", "كانون الأول"),
    },
    "fa": {
        1: ("ژانویه",), 2: ("فوریه",), 3: ("مارس",), 4: ("آوریل",), 5: ("مه",),
        6: ("ژوئن",), 7: ("ژوئیه", "جولای"), 8: ("اوت", "آگوست"), 9: ("سپتامبر",),
        10: ("اکتبر",), 11: ("نوامبر",), 12: ("دسامبر",),
    },
    "prs": {
        1: ("جنوری",), 2: ("فبروری",), 3: ("مارچ",), 4: ("اپریل",), 5: ("می",), 6: ("جون",),
        7: ("جولای",), 8: ("اگست",), 9: ("سپتمبر",), 10: ("اکتوبر",), 11: ("نومبر",),
        12: ("دسمبر",),
    },
    "ps": {
        1: ("جنوري",), 2: ("فبروري",), 3: ("مارچ",), 4: ("اپریل",), 5: ("می",), 6: ("جون",),
        7: ("جولای",), 8: ("اګست", "اگست"), 9: ("سپتمبر",), 10: ("اکتوبر",), 11: ("نومبر",),
        12: ("دسمبر",),
    },
    "ur": {
        1: ("جنوری",), 2: ("فروری",), 3: ("مارچ",), 4: ("اپریل",), 5: ("مئی",), 6: ("جون",),
        7: ("جولائی",), 8: ("اگست",), 9: ("ستمبر",), 10: ("اکتوبر",), 11: ("نومبر",),
        12: ("دسمبر",),
    },
    "hi": {
        1: ("जनवरी",), 2: ("फ़रवरी", "फरवरी"), 3: ("मार्च",), 4: ("अप्रैल",), 5: ("मई",),
        6: ("जून",), 7: ("जुलाई",), 8: ("अगस्त",), 9: ("सितंबर", "सितम्बर"),
        10: ("अक्टूबर",), 11: ("नवंबर", "नवम्बर"), 12: ("दिसंबर", "दिसम्बर"),
    },
    "ne": {
        1: ("जनवरी",), 2: ("फेब्रुअरी",), 3: ("मार्च",), 4: ("अप्रिल",), 5: ("मे",), 6: ("जुन",),
        7: ("जुलाई",), 8: ("अगस्ट",), 9: ("सेप्टेम्बर",), 10: ("अक्टोबर",), 11: ("नोभेम्बर",),
        12: ("डिसेम्बर",),
    },
    "pa": {
        1: ("ਜਨਵਰੀ",), 2: ("ਫ਼ਰਵਰੀ", "ਫਰਵਰੀ"), 3: ("ਮਾਰਚ",), 4: ("ਅਪ੍ਰੈਲ",), 5: ("ਮਈ",),
        6: ("ਜੂਨ",), 7: ("ਜੁਲਾਈ",), 8: ("ਅਗਸਤ",), 9: ("ਸਤੰਬਰ",), 10: ("ਅਕਤੂਬਰ",),
        11: ("ਨਵੰਬਰ",), 12: ("ਦਸੰਬਰ",),
    },
    "bn": {
        1: ("জানুয়ারী", "জানুয়ারি"), 2: ("ফেব্রুয়ারী", "ফেব্রুয়ারি"), 3: ("মার্চ",),
        4: ("এপ্রিল",), 5: ("মে",), 6: ("জুন",), 7: ("জুলাই",), 8: ("আগস্ট",),
        9: ("সেপ্টেম্বর",), 10: ("অক্টোবর",), 11: ("নভেম্বর",), 12: ("ডিসেম্বর",),
    },
    "so": {
        1: ("janaayo",), 2: ("febraayo",), 3: ("maarso",), 4: ("abriil",), 5: ("maajo",),
        6: ("juun",), 7: ("luulyo",), 8: ("agoosto",), 9: ("sebtembar",), 10: ("oktoobar",),
        11: ("nofembar",), 12: ("desembar",),
    },
    "sw": {
        1: ("januari",), 2: ("februari",), 3: ("machi",), 4: ("aprili",), 5: ("mei",),
        6: ("juni",), 7: ("julai",), 8: ("agosti",), 9: ("septemba",), 10: ("oktoba",),
        11: ("novemba",), 12: ("desemba",),
    },
    "rw": {
        1: ("mutarama",), 2: ("gashyantare",), 3: ("werurwe",), 4: ("mata",), 5: ("gicurasi",),
        6: ("kamena",), 7: ("nyakanga",), 8: ("kanama",), 9: ("nzeri",), 10: ("ukwakira",),
        11: ("ugushyingo",), 12: ("ukuboza",),
    },
    "am": {
        1: ("ጃንዩወሪ", "ጃንዋሪ"), 2: ("ፌብሩወሪ", "ፌብሩዋሪ"), 3: ("ማርች",), 4: ("ኤፕሪል",),
        5: ("ሜይ",), 6: ("ጁን",), 7: ("ጁላይ",), 8: ("ኦገስት",), 9: ("ሴፕቴምበር",),
        10: ("ኦክቶበር",), 11: ("ኖቬምበር",), 12: ("ዲሴምበር",),
    },
    "my": {
        1: ("ဇန်နဝါရီ",), 2: ("ဖေဖော်ဝါရီ",), 3: ("မတ်",), 4: ("ဧပြီ",), 5: ("မေ",),
        6: ("ဇွန်",), 7: ("ဇူလိုင်",), 8: ("ဩဂုတ်", "သြဂုတ်"), 9: ("စက်တင်ဘာ",),
        10: ("အောက်တိုဘာ",), 11: ("နိုဝင်ဘာ",), 12: ("ဒီဇင်ဘာ",),
    },
}  # fmt: skip
# vi, zh-Hans, zh-Hant and ko print numeric months ("tháng 10", "10月", "10월") — see _CJK/_VI.
MONTH_LANGUAGES = frozenset({*_MONTHS, "vi", "zh-Hans", "zh-Hant", "ko"})


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _token_table() -> dict[str, dict[str, int]]:
    table: dict[str, dict[str, int]] = {}
    for lang, months in _MONTHS.items():
        for number, names in months.items():
            for name in names:
                table.setdefault(_fold(name), {})[lang] = number
    return table


_TOKEN_MONTHS = _token_table()
_MON_ALT = "|".join(re.escape(t) for t in sorted(_TOKEN_MONTHS, key=len, reverse=True))
_WB_BEFORE = r"(?<![^\W\d_])"
_WB_AFTER = r"(?![^\W\d_])"
_ORD = r"(?:st|nd|rd|th|er|e|º|°|\.)?"
_P_DMY_NAME = re.compile(
    rf"(?<!\d)(?P<d>\d{{1,2}}){_ORD}\s*(?:de\s+|of\s+|-)?{_WB_BEFORE}(?P<mon>{_MON_ALT})"
    rf"{_WB_AFTER}\.?,?\s*(?:de\s+|del\s+|-)?(?P<y>\d{{4}}|\d{{2}})(?!\d)"
)
_P_MDY_NAME = re.compile(
    rf"{_WB_BEFORE}(?P<mon>{_MON_ALT}){_WB_AFTER}\.?\s*(?P<d>\d{{1,2}})(?:st|nd|rd|th)?(?!\d)"
    rf",?\s*(?P<y>\d{{4}})(?!\d)"
)
_P_MONTH_DAY = re.compile(
    rf"{_WB_BEFORE}(?P<mon>{_MON_ALT}){_WB_AFTER}\.?\s*\d{{1,2}}(?!\d)"
    rf"|(?<!\d)\d{{1,2}}{_ORD}\s*(?:de\s+|of\s+|-)?{_WB_BEFORE}(?P<mon2>{_MON_ALT}){_WB_AFTER}"
)
_P_ISO = re.compile(r"(?<![\d/.-])(?P<y>\d{4})[-/.](?P<m>\d{1,2})[-/.](?P<d>\d{1,2})(?![\d])")
_P_NUM = re.compile(
    r"(?<![\d/.-])(?P<a>\d{1,2})(?P<sep>[/.-])(?P<b>\d{1,2})(?P=sep)(?P<y>\d{4}|\d{2})(?![\d])"
)
_P_CJK = re.compile(
    r"(?P<y>\d{4})\s*[年년]\s*(?P<m>\d{1,2})\s*[月월]\s*(?P<d>\d{1,2})\s*[日일号]?"
)
_P_VI = re.compile(
    r"(?:ngày\s*)?(?P<d>\d{1,2})\s*tháng\s*(?P<m>\d{1,2})\s*(?:năm|,)?\s*(?P<y>\d{4})"
)


@dataclass(frozen=True)
class DateParse:
    """Every distinct date a printed string can mean, plus the numeric-ambiguity flag."""

    dates: tuple[date, ...]
    ambiguous_numeric: bool
    extra_mentions: bool = False
    """A month + day printed without a year next to a full date ("October 14 or 21, 2026")."""

    @property
    def single(self) -> date | None:
        """The date when exactly one reading exists and nothing was ambiguous, else ``None``."""
        if len(self.dates) == 1 and not self.ambiguous_numeric and not self.extra_mentions:
            return self.dates[0]
        return None


def _year(raw: str) -> int:
    value = int(raw)
    return 2000 + value if len(raw) == 2 else value


def _make(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _month_of(token: str, language: str | None) -> int | None:
    meanings = _TOKEN_MONTHS.get(token.rstrip("."))
    if not meanings:
        return None
    if language is not None and language in meanings:
        return meanings[language]
    values = set(meanings.values())
    return values.pop() if len(values) == 1 else None


def numeric_order_cue(text: str) -> DateFormat | None:
    """``mdy``/``dmy`` when another numeric date on the paper settles the order, else ``None``.

    ``10/14/2026`` elsewhere on the page proves month-first; ``14/10/2026`` proves day-first;
    evidence both ways (or none) gives ``None``.
    """
    mdy = dmy = False
    for m in _P_NUM.finditer(ascii_digits(_fold(text))):
        a, b = int(m.group("a")), int(m.group("b"))
        if a > 12 >= b:
            dmy = True
        elif b > 12 >= a:
            mdy = True
    if mdy == dmy:
        return None
    return DateFormat.mdy if mdy else DateFormat.dmy


def parse_dates(
    text: str | None,
    *,
    default_order: DateFormat | None = None,
    language: str | None = None,
    order_cue: DateFormat | None = None,
) -> DateParse:
    """All Gregorian dates printed in ``text`` (deterministic regex table; D-11).

    A numeric date whose day and month could swap ("10/07/2026") is read in the paper's own
    order: ``order_cue`` (another numeric date on the page settles it, ``numeric_order_cue``),
    else ``default_order`` (``paper_default_order``: US-issued paper types print month first),
    else it stays ambiguous. The reader's ``Preferences.date_format`` is a display preference and
    is never used here. ``language`` resolves month tokens that differ between languages.
    Two-digit years mean 2000+.
    """
    if not text:
        return DateParse((), False)
    s = ascii_digits(_fold(text))
    found: list[date] = []
    ambiguous = False

    def add(value: date | None) -> None:
        if value is not None and value not in found:
            found.append(value)

    for pattern in (_P_DMY_NAME, _P_MDY_NAME):
        for m in pattern.finditer(s):
            month = _month_of(m.group("mon"), language)
            if month is not None:
                add(_make(_year(m.group("y")), month, int(m.group("d"))))
    for pattern in (_P_ISO, _P_CJK, _P_VI):
        for m in pattern.finditer(s):
            add(_make(int(m.group("y")), int(m.group("m")), int(m.group("d"))))
    named = sum(
        1
        for m in _P_MONTH_DAY.finditer(s)
        if _month_of(m.group("mon") or m.group("mon2") or "", language) is not None
    )
    named_full = 0
    for pattern in (_P_DMY_NAME, _P_MDY_NAME):
        named_full += sum(1 for m in pattern.finditer(s) if _month_of(m.group("mon"), language))
    extra = named > named_full
    order = order_cue or (default_order if default_order is not DateFormat.auto else None)
    for m in _P_NUM.finditer(s):
        a, b, y = int(m.group("a")), int(m.group("b")), _year(m.group("y"))
        if a > 12 or (order is DateFormat.dmy and b <= 12):
            add(_make(y, b, a))
        elif b > 12 or a == b or order is DateFormat.mdy:
            add(_make(y, a, b))
        else:
            ambiguous = True
    return DateParse(tuple(found), ambiguous, extra)


# --- federal holidays, business days, time zones -------------------------------------------------


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def federal_holidays(year: int) -> frozenset[date]:
    """U.S. federal holidays (5 U.S.C. 6103) observed in ``year`` (Sat → Fri, Sun → Mon)."""
    fixed = [date(year, 1, 1), date(year, 6, 19), date(year, 7, 4), date(year, 11, 11),
             date(year, 12, 25)]  # fmt: skip
    days = {_observed(d) for d in fixed}
    days |= {
        _nth_weekday(year, 1, 0, 3),  # Birthday of Martin Luther King, Jr.
        _nth_weekday(year, 2, 0, 3),  # Washington's Birthday
        _last_weekday(year, 5, 0),  # Memorial Day
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 10, 0, 2),  # Columbus Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving Day
    }
    # New Year's Day of the next year observed on Friday Dec 31 of this year.
    if _observed(date(year + 1, 1, 1)).year == year:
        days.add(_observed(date(year + 1, 1, 1)))
    return frozenset(d for d in days if d.year == year)


def is_business_day(day: date) -> bool:
    """Monday–Friday and not a federal holiday."""
    return day.weekday() < 5 and day not in federal_holidays(day.year)


def add_business_days(start: date, days: int) -> date:
    """Walk ``days`` business days forward from ``start`` (the start day itself never counts)."""
    current = start
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if is_business_day(current):
            remaining -= 1
    return current


STATE_TIME_ZONES: Mapping[str, str] = {
    "AL": "America/Chicago", "AK": "America/Anchorage", "AZ": "America/Phoenix",
    "AR": "America/Chicago", "CA": "America/Los_Angeles", "CO": "America/Denver",
    "CT": "America/New_York", "DE": "America/New_York", "DC": "America/New_York",
    "FL": "America/New_York", "GA": "America/New_York", "HI": "Pacific/Honolulu",
    "ID": "America/Boise", "IL": "America/Chicago", "IN": "America/Indiana/Indianapolis",
    "IA": "America/Chicago", "KS": "America/Chicago", "KY": "America/New_York",
    "LA": "America/Chicago", "ME": "America/New_York", "MD": "America/New_York",
    "MA": "America/New_York", "MI": "America/Detroit", "MN": "America/Chicago",
    "MS": "America/Chicago", "MO": "America/Chicago", "MT": "America/Denver",
    "NE": "America/Chicago", "NV": "America/Los_Angeles", "NH": "America/New_York",
    "NJ": "America/New_York", "NM": "America/Denver", "NY": "America/New_York",
    "NC": "America/New_York", "ND": "America/Chicago", "OH": "America/New_York",
    "OK": "America/Chicago", "OR": "America/Los_Angeles", "PA": "America/New_York",
    "RI": "America/New_York", "SC": "America/New_York", "SD": "America/Chicago",
    "TN": "America/Chicago", "TX": "America/Chicago", "UT": "America/Denver",
    "VT": "America/New_York", "VA": "America/New_York", "WA": "America/Los_Angeles",
    "WV": "America/New_York", "WI": "America/Chicago", "WY": "America/Denver",
    "PR": "America/Puerto_Rico", "GU": "Pacific/Guam", "VI": "America/St_Thomas",
    "AS": "Pacific/Pago_Pago", "MP": "Pacific/Saipan",
}  # fmt: skip
DEFAULT_TIME_ZONE = "America/New_York"


def local_today(now: datetime, state: str | None = None) -> date:
    """``now`` converted to the user's state's zone (default ``America/New_York``) as a date."""
    name = STATE_TIME_ZONES.get((state or "").upper(), DEFAULT_TIME_ZONE)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    try:
        return now.astimezone(ZoneInfo(name)).date()
    except ZoneInfoNotFoundError:  # no tz database: fall back to US Eastern standard time
        return (now.astimezone(UTC) - timedelta(hours=5)).date()


_DIGIT_BASES: Mapping[DigitSystem, int] = {
    DigitSystem.eastern_arabic: 0x0660, DigitSystem.persian: 0x06F0,
    DigitSystem.devanagari: 0x0966, DigitSystem.bengali: 0x09E6, DigitSystem.gurmukhi: 0x0A66,
    DigitSystem.myanmar: 0x1040,
}  # fmt: skip


def localize_digits(text: str, digit_system: DigitSystem) -> str:
    """ASCII digits → the target script's digits (western/ethiopic/other are left as ASCII)."""
    base = _DIGIT_BASES.get(digit_system)
    if base is None:
        return text
    return "".join(chr(base + int(ch)) if "0" <= ch <= "9" else ch for ch in text)


# --- rule application ----------------------------------------------------------------------------


def compile_rule_pattern(rule: DeadlineRule) -> re.Pattern[str]:
    """``rule.pattern`` compiled case-insensitively (validated at load by ``validate_rules``)."""
    return re.compile(rule.pattern, re.IGNORECASE)


def validate_rules(rules: Iterable[DeadlineRule]) -> list[str]:
    """Problems with a rules table (bad regex, non-positive days); ``[]`` when it is sound."""
    problems: list[str] = []
    for rule in rules:
        try:
            compile_rule_pattern(rule)
        except re.error as exc:
            problems.append(f"{rule.id}: pattern does not compile: {exc}")
        if rule.days <= 0:
            problems.append(f"{rule.id}: days must be positive")
        if rule.mail_days < 0:
            problems.append(f"{rule.id}: mail_days must not be negative")
    return problems


def rule_applies(
    rule: DeadlineRule,
    document_type: DocumentType,
    today: date,
    category: DocumentCategory | None = None,
) -> bool:
    """D-11 conditions (c) and (d): the type is listed (an ``other_notice`` also of the rule's
    category, TAXONOMY §5.3) and ``valid_until`` has not passed."""
    if document_type in NEVER_ESTIMATE_TYPES:
        return False
    if document_type not in rule.applies_to_doc_types:
        return False
    needed = OTHER_NOTICE_RULE_CATEGORY.get(rule.id)
    if document_type is DocumentType.other_notice and needed is not None and category != needed:
        return False
    return rule.valid_until is None or rule.valid_until >= today


def matching_rules(
    relative_rule_text: str | None,
    document_type: DocumentType,
    rules: Sequence[DeadlineRule],
    today: date,
    category: DocumentCategory | None = None,
) -> list[DeadlineRule]:
    """Seeded rules (table order) whose pattern matches the printed phrase and that apply today."""
    if not relative_rule_text:
        return []
    phrase = unicodedata.normalize("NFKC", relative_rule_text)
    return [
        rule
        for rule in rules
        if rule_applies(rule, document_type, today, category)
        and compile_rule_pattern(rule).search(phrase)
    ]


def find_rule(
    relative_rule_text: str | None,
    document_type: DocumentType,
    rules: Sequence[DeadlineRule],
    today: date,
    category: DocumentCategory | None = None,
) -> DeadlineRule | None:
    """First rule from ``matching_rules`` (``None`` when no seeded rule fits)."""
    found = matching_rules(relative_rule_text, document_type, rules, today, category)
    return found[0] if found else None


def compute_estimate(anchor: date, rule: DeadlineRule) -> date:
    """``anchor`` + ``rule.days`` (calendar, or business days skipping federal holidays), then
    ``+ rule.mail_days`` calendar days."""
    if rule.count_basis == "business":
        end = add_business_days(anchor, rule.days)
    else:
        end = anchor + timedelta(days=rule.days)
    return end + timedelta(days=rule.mail_days)


def rule_formula(rule: DeadlineRule, anchor_text: str) -> str:
    """Human-readable formula, e.g. ``"September 1, 2026 + 30 calendar days (+3 mail days)"``."""
    text = f"{anchor_text} + {rule.days} {rule.count_basis} days"
    if rule.mail_days:
        text += f" (+{rule.mail_days} mail days)"
    if rule.receipt_based:
        text += " (must be received by then)"
    return text


def _unresolved(time_text: str | None) -> DateInfo:
    return DateInfo(
        value_iso=None, time_text=time_text, kind=DateKind.unresolved, formula=None,
        anchor_quote=None, anchor_demand_id=None, rule_id=None, rule_source_url=None,
        rule_verification=None, localized_line=None,
    )  # fmt: skip


def _localized(value: date | None, digit_system: DigitSystem) -> str | None:
    if value is None or digit_system is DigitSystem.western:
        return None
    line = localize_digits(value.isoformat(), digit_system)
    return line if line != value.isoformat() else None


EN_MONTHS = (
    "January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December",
)  # fmt: skip
_P_NUMERIC_LIKE = re.compile(r"(?<!\d)(\d{1,2})([/.-])(\d{1,2})\2(\d{4}|\d{2})(?!\d)")


def estimate_text(
    value: date, anchor_text: str | None = None, anchor_iso: str | None = None
) -> str:
    """``value`` written like the printed anchor date: the anchor's numeric order, separator,
    zero padding and year width when it is printed in numbers ("10/14/2026" → "11/13/2026",
    "14.10.26" → "13.11.26"); "13 November 2026" when it prints the day before a month name;
    otherwise "November 13, 2026". Western digits and English month names only (rule 7: dates
    stay in Latin letters and Western digits in every language)."""
    like = _fold(ascii_digits(anchor_text or ""))
    month_name = EN_MONTHS[value.month - 1]
    if _P_DMY_NAME.search(like):
        return f"{value.day} {month_name} {value.year}"
    numeric = None if _P_MDY_NAME.search(like) else _P_NUMERIC_LIKE.search(like)
    if numeric is None:
        return f"{month_name} {value.day}, {value.year}"
    a, sep, b, y = numeric.groups()
    anchor = _iso_or_none(anchor_iso)
    day_first = anchor is not None and anchor.day != anchor.month and (
        (int(a), int(b)) == (anchor.day, anchor.month)
    )
    first, second = (value.day, value.month) if day_first else (value.month, value.day)
    pad = a.startswith("0") or b.startswith("0") or (len(a) == 2 and len(b) == 2)
    year = f"{value.year % 100:02d}" if len(y) == 2 else str(value.year)
    if pad:
        return f"{first:02d}{sep}{second:02d}{sep}{year}"
    return f"{first}{sep}{second}{sep}{year}"


def _iso_or_none(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _printed_date_text(demand: Demand, source: DemandOut | None) -> str | None:
    """``date_text`` when its digits sit in the verified quote, else the verified value."""
    if source is not None and source.date_text:
        if check_value(source.date_text, demand.source_quote) is None:
            return source.date_text
    if source is not None and source.date_text is None:
        return None
    return demand.value_verbatim or None


def _printed_time_text(demand: Demand, source: DemandOut | None) -> str | None:
    """``time_text`` only when it sits in the verified quote (D-09): the client shows it next to
    the date, so a time the paper does not print never reaches the reader (AI_PROMPTS §11.2)."""
    if source is None or not source.time_text:
        return None
    return source.time_text if check_value(source.time_text, demand.source_quote) is None else None


def _append_note(existing: str | None, note: str) -> str:
    if not existing:
        return note
    return existing if note in existing else f"{existing} {note}"


# Paper types that only US senders issue print numeric dates month first (MM/DD/YYYY). A paper
# that may come from abroad (vaccine records, lab results, medicine labels, report cards) or of
# unknown origin (``other_notice``, ``unknown``) has no default: without a cue on the page an
# ambiguous "03/04/2026" stays ambiguous.
NO_DEFAULT_ORDER_TYPES = frozenset(
    {
        DocumentType.vaccine_record, DocumentType.lab_result, DocumentType.prescription_label,
        DocumentType.report_card, DocumentType.other_notice, DocumentType.unknown,
    }
)  # fmt: skip


def paper_default_order(document_type: DocumentType) -> DateFormat | None:
    """The numeric date order a paper of this type prints when the page itself gives no cue."""
    return None if document_type in NO_DEFAULT_ORDER_TYPES else DateFormat.mdy


@dataclass(frozen=True)
class DeadlineContext:
    """Everything ``apply_deadline_rules`` needs besides the demands themselves.

    ``default_order`` is the paper's own default numeric order (``paper_default_order``), never
    the reader's display preference."""

    document_type: DocumentType
    rules: Sequence[DeadlineRule]
    today: date
    default_order: DateFormat | None = None
    language: str | None = None
    order_cue: DateFormat | None = None
    digit_system: DigitSystem = DigitSystem.western
    t: Translator | None = None
    category: DocumentCategory | None = None


def resolve_stated(demand: Demand, source: DemandOut | None, ctx: DeadlineContext) -> Demand:
    """Pass 1 for one verified demand: ``stated`` when a printed date exists, else leave it."""
    time_text = _printed_time_text(demand, source)
    printed = _printed_date_text(demand, source)
    if printed is None:
        return demand
    parsed = parse_dates(
        printed, default_order=ctx.default_order, language=ctx.language, order_cue=ctx.order_cue
    )
    if not parsed.dates and not parsed.ambiguous_numeric and not parsed.extra_mentions:
        return demand  # no date in the text at all → maybe relative, else unresolved in pass 2
    # From here a date is printed; unless it parses to exactly one date (a year-less "Monday,
    # October 14" does not) it stays ``stated`` with ``value_iso=null`` and ``confidence=low``.
    value = parsed.single
    info = DateInfo(
        value_iso=value.isoformat() if value else None, time_text=time_text,
        kind=DateKind.stated, formula=None, anchor_quote=None, anchor_demand_id=None,
        rule_id=None, rule_source_url=None, rule_verification=None,
        localized_line=_localized(value, ctx.digit_system),
    )  # fmt: skip
    update: dict[str, object] = {"date": info, "reminder_eligible": bool(value and demand.verified)}
    if value is None:
        update["confidence"] = Confidence.low
        if parsed.ambiguous_numeric and ctx.t is not None:
            note = ctx.t(AMBIGUOUS_DATE_KEY)
            update["ambiguity_note"] = _append_note(demand.ambiguity_note, note)
    return demand.model_copy(update=update)


def resolve_carried(
    demand: Demand,
    source: DemandOut | None,
    ctx: DeadlineContext,
    transcript: Transcript | None = None,
) -> Demand:
    """Pass 1 for a printed date carried by another kind ("return the form by October 23, 2026"
    as ``document_requested``, "prepay $156.00 by October 9, 2026" as ``amount``).

    Only a verified ``amount``/``document_requested``/``action`` demand with a date role
    (``urgency.ANY_DRIVING``) whose ``date_text`` sits inside its verified quote — and, given the
    transcript, passes ``verify_span`` as a value of that quote — and parses to exactly one day.
    The printed ``date_text`` then becomes ``value_verbatim``, so every ``{date}`` the reader sees
    (banner, reminder, quick sheet) is the printed date; the kind, quote, ``amount`` and
    ``documents`` stay. Never an estimate. Otherwise the demand is returned unchanged.
    """
    if not demand.verified or demand.kind not in DATE_CARRYING_KINDS:
        return demand
    if demand.role not in ANY_DRIVING or source is None or not source.date_text:
        return demand
    printed = source.date_text.strip()
    if check_value(printed, demand.source_quote) is not None:
        return demand
    if transcript is not None and not verify_span(
        transcript, demand.span_ids, demand.source_quote, value_verbatim=printed
    ).verified:
        return demand
    dated = resolve_stated(demand.model_copy(update={"value_verbatim": printed}), source, ctx)
    if dated.date is None or not dated.date.value_iso:
        return demand
    return dated


def _anchor_for(
    source: DemandOut | None,
    rule: DeadlineRule,
    stated: Sequence[Demand],
    transcript: Transcript | None,
    span_aliases: Mapping[str, Sequence[str]] | None = None,
) -> Demand | None:
    """D-11 (b): the verified *stated* demand whose span holds ``anchor_span_id`` and whose role
    is the rule's ``anchor_role``. No other demand may stand in. ``span_aliases`` (final demand
    id → the model's own ``span_ids``) lets a demand re-anchored by ``demand_repair`` (R4) still
    answer to the id the model cited for it."""
    if source is None or not source.anchor_span_id:
        return None
    resolve = transcript.resolve if transcript else (lambda span_id: span_id)
    anchor_id = resolve(source.anchor_span_id)
    aliases = span_aliases or {}
    for cand in stated:
        cited = [*cand.span_ids, *(resolve(a) for a in aliases.get(cand.id, ()))]
        if (
            cand.verified
            and cand.date is not None
            and cand.date.kind is DateKind.stated
            and cand.date.value_iso
            and cand.role == rule.anchor_role
            and anchor_id in cited
        ):
            return cand
    return None


def resolve_relative(
    demand: Demand,
    source: DemandOut | None,
    stated: Sequence[Demand],
    ctx: DeadlineContext,
    transcript: Transcript | None = None,
    span_aliases: Mapping[str, Sequence[str]] | None = None,
) -> Demand:
    """Pass 2 for one verified demand without a stated date: ``estimated`` or ``unresolved``."""
    time_text = _printed_time_text(demand, source)
    rule: DeadlineRule | None = None
    anchor: Demand | None = None
    if demand.kind is DemandKind.relative_deadline and source is not None:
        phrase = source.relative_rule_text
        for cand in matching_rules(phrase, ctx.document_type, ctx.rules, ctx.today, ctx.category):
            anchor = _anchor_for(source, cand, stated, transcript, span_aliases)
            if anchor is not None:
                rule = cand
                break
    if rule is None or anchor is None or anchor.date is None or not anchor.date.value_iso:
        unresolved = _unresolved(time_text)
        return demand.model_copy(update={"date": unresolved, "reminder_eligible": False})
    value = compute_estimate(date.fromisoformat(anchor.date.value_iso), rule)
    info = DateInfo(
        value_iso=value.isoformat(), time_text=time_text, kind=DateKind.estimated,
        formula=rule_formula(rule, anchor.value_verbatim), anchor_quote=anchor.source_quote,
        anchor_demand_id=anchor.id, rule_id=rule.id, rule_source_url=rule.source_url,
        rule_verification=rule.verification,
        # Printed nowhere: the readable estimate for "About {date} (estimate)" (module docstring).
        localized_line=estimate_text(value, anchor.value_verbatim, anchor.date.value_iso),
    )  # fmt: skip
    return demand.model_copy(update={"date": info, "reminder_eligible": False})


def apply_deadline_rules(
    demands: Sequence[Demand],
    sources: Mapping[str, DemandOut],
    ctx: DeadlineContext,
    transcript: Transcript | None = None,
    *,
    span_aliases: Mapping[str, Sequence[str]] | None = None,
) -> list[Demand]:
    """Fill ``Demand.date`` + ``reminder_eligible`` for verified demands (AI_PROMPTS §11.4).

    ``demands`` are the *verified* demands (``VerifiedDemands.verified``), ``sources`` the
    ``VerifiedDemands.sources`` map. Kinds ``deadline``/``relative_deadline``/``appointment`` get
    a ``DateInfo``; an ``amount``/``document_requested``/``action`` demand gets a ``stated`` one
    only for a printed date it carries (``resolve_carried``), unless another verified demand
    already states that day for the same role; other demands are returned unchanged. A printed
    date always wins over a computed one; ``reminder_eligible = verified and stated and
    value_iso``. ``span_aliases`` comes from ``demand_repair`` (``_anchor_for``).
    """
    first: list[Demand] = []
    for d in demands:
        if d.kind in DATED_KINDS and d.verified:
            first.append(resolve_stated(d, sources.get(d.id), ctx))
        else:
            first.append(d)
    taken: set[tuple[str | None, str | None]] = {
        (d.date.value_iso, d.role) for d in first
        if d.date is not None and d.date.kind is DateKind.stated and d.date.value_iso
    }  # fmt: skip
    for i, d in enumerate(first):
        carried = resolve_carried(d, sources.get(d.id), ctx, transcript)
        if carried is d or carried.date is None:
            continue
        if (carried.date.value_iso, carried.role) not in taken:
            taken.add((carried.date.value_iso, carried.role))
            first[i] = carried
    stated = [d for d in first if d.date is not None and d.date.kind is DateKind.stated]
    out: list[Demand] = []
    for d in first:
        if d.kind in DATED_KINDS and d.verified and d.date is None:
            out.append(
                resolve_relative(d, sources.get(d.id), stated, ctx, transcript, span_aliases)
            )
        else:
            out.append(d)
    return out


def context_for(
    *,
    document_type: DocumentType,
    rules: Sequence[DeadlineRule],
    now: datetime,
    state: str | None = None,
    language: str | None = None,
    transcript_text: str = "",
    digit_system: DigitSystem = DigitSystem.western,
    t: Translator | None = None,
    category: DocumentCategory | None = None,
) -> DeadlineContext:
    """Convenience builder: ``today`` in the state's zone, the paper-wide numeric order cue and
    the type's default order. There is no ``date_format`` argument on purpose: the reader's
    display preference never decides how a printed date is read."""
    return DeadlineContext(
        document_type=document_type, rules=rules, today=local_today(now, state),
        default_order=paper_default_order(document_type), language=language, category=category,
        order_cue=numeric_order_cue(transcript_text) if transcript_text else None,
        digit_system=digit_system, t=t,
    )  # fmt: skip


__all__ = [
    "AMBIGUOUS_DATE_KEY",
    "DATED_KINDS",
    "DATE_CARRYING_KINDS",
    "DEFAULT_TIME_ZONE",
    "EN_MONTHS",
    "MONTH_LANGUAGES",
    "NEVER_ESTIMATE_TYPES",
    "NO_DEFAULT_ORDER_TYPES",
    "OTHER_NOTICE_RULE_CATEGORY",
    "STATE_TIME_ZONES",
    "DateParse",
    "DeadlineContext",
    "add_business_days",
    "apply_deadline_rules",
    "compile_rule_pattern",
    "compute_estimate",
    "context_for",
    "estimate_text",
    "federal_holidays",
    "find_rule",
    "is_business_day",
    "local_today",
    "localize_digits",
    "matching_rules",
    "numeric_order_cue",
    "paper_default_order",
    "parse_dates",
    "resolve_carried",
    "resolve_relative",
    "resolve_stated",
    "rule_applies",
    "rule_formula",
    "validate_rules",
]
