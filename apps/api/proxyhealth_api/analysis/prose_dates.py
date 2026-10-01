"""Dates in model prose must be the paper's dates (D-11; invariant #5; AI_PROMPTS §11.4).

Only ``source_quote`` / ``value_verbatim`` are span-verified (D-09), but the summary (read aloud
first), each demand's sentence and the plan steps are model prose and may name a date too. After
phrasing, every date-like span in that prose (the ``deadline_rules`` regex table: named months in
the bundled languages, numeric, ISO, CJK/Vietnamese forms, and a month + day without a year) must
be a date of a verified demand (``stated`` or ``estimated`` ``value_iso``), a date printed in the
transcript, or today. Anything else is an invented or shifted date:

* in a demand's own sentence it is replaced by that demand's verified ``value_verbatim`` (when the
  demand has a resolved date not already in the sentence), otherwise by the fixed phrase
  ``SEE_PAPER_KEY`` ("the date on the paper");
* in other prose the sentence carrying it is dropped; a text of one sentence keeps the sentence
  with the date replaced by ``SEE_PAPER_KEY``.

Each replaced or dropped span counts as a checked and rejected fact in ``verification``. Pure
functions; nothing logged.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

from proxyhealth_api.analysis import deadline_rules as dr
from proxyhealth_api.analysis.i18n import Translator
from proxyhealth_api.analysis.phrasing import split_sentences
from proxyhealth_api.analysis.verify import ascii_digits
from proxyhealth_api.contracts.analysis import Demand

SEE_PAPER_KEY = "verify.date_see_paper"


@dataclass(frozen=True)
class DateMention:
    """One date-like span of a string: every full date it can mean, or its month/day pairs when
    it carries no year."""

    start: int
    end: int
    dates: frozenset[date] = frozenset()
    month_days: frozenset[tuple[int, int]] = frozenset()


def _folded(text: str) -> tuple[str, list[int]]:
    """``text`` NFKC-normalised, case-folded, digits in ASCII — with, per output character, the
    index of the input character it came from (so spans map back onto ``text``)."""
    chars: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(text):
        out = ascii_digits(unicodedata.normalize("NFKC", ch).casefold())
        chars.append(out)
        index.extend([i] * len(out))
    return "".join(chars), index


def _valid(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def find_mentions(text: str, language: str | None = None) -> list[DateMention]:
    """Every date-like span of ``text`` (non-overlapping, longest first on overlap)."""
    if not text:
        return []
    s, index = _folded(text)
    raw: list[tuple[int, int, frozenset[date], frozenset[tuple[int, int]]]] = []

    def add(
        m_start: int,
        m_end: int,
        dates: Iterable[date | None],
        md: Iterable[tuple[int, int]] = (),
    ) -> None:
        ds = frozenset(d for d in dates if d is not None)
        mds = frozenset(md)
        if ds or mds:
            raw.append((m_start, m_end, ds, mds))

    for pattern in (dr._P_DMY_NAME, dr._P_MDY_NAME):
        for m in pattern.finditer(s):
            month = dr._month_of(m.group("mon"), language)
            if month is not None:
                add(m.start(), m.end(), [_valid(dr._year(m.group("y")), month, int(m.group("d")))])
    for pattern in (dr._P_ISO, dr._P_CJK, dr._P_VI):
        for m in pattern.finditer(s):
            y, mo, d = int(m.group("y")), int(m.group("m")), int(m.group("d"))
            add(m.start(), m.end(), [_valid(y, mo, d)])
    for m in dr._P_NUM.finditer(s):
        a, b, y = int(m.group("a")), int(m.group("b")), dr._year(m.group("y"))
        add(m.start(), m.end(), [_valid(y, a, b), _valid(y, b, a)])
    for m in dr._P_MONTH_DAY.finditer(s):
        token = m.group("mon") or m.group("mon2") or ""
        first = text[index[m.start("mon") if m.group("mon") else m.start("mon2")]]
        if token.rstrip(".") == "may" and first.islower():
            continue  # "you may 2 …" is the verb, not the month
        month = dr._month_of(token, language)
        digits = [int(x) for x in _digit_runs(m.group(0))]
        if month is not None and digits and 1 <= digits[0] <= 31:
            add(m.start(), m.end(), [], [(month, digits[0])])
    raw.sort(key=lambda r: (r[0], -(r[1] - r[0])))
    out: list[DateMention] = []
    last_end = -1
    for start, end, ds, mds in raw:
        if start < last_end:
            continue
        last_end = end
        out.append(DateMention(index[start], index[end - 1] + 1, ds, mds))
    return out


def _digit_runs(text: str) -> list[str]:
    runs: list[str] = []
    cur = ""
    for ch in text:
        if ch.isdigit():
            cur += ch
        elif cur:
            runs.append(cur)
            cur = ""
    if cur:
        runs.append(cur)
    return runs


@dataclass(frozen=True)
class AllowedDates:
    """Dates prose may name: verified demand dates, dates printed on the paper, today."""

    dates: frozenset[date]

    @property
    def month_days(self) -> frozenset[tuple[int, int]]:
        return frozenset((d.month, d.day) for d in self.dates)

    def allows(self, mention: DateMention) -> bool:
        if mention.dates:
            return bool(mention.dates & self.dates)
        return bool(mention.month_days & self.month_days)


def allowed_dates(
    demands: Iterable[Demand],
    transcript_text: str,
    *,
    today: date,
    language: str | None = None,
) -> AllowedDates:
    """The dates prose may name for one result (every reading of a printed numeric date)."""
    found: set[date] = {today}
    for d in demands:
        if d.verified and d.date is not None and d.date.value_iso:
            try:
                found.add(date.fromisoformat(d.date.value_iso))
            except ValueError:
                continue
    for m in find_mentions(transcript_text, language):
        found |= m.dates
    return AllowedDates(frozenset(found))


@dataclass
class ProseDateStats:
    """Bookkeeping for one result: spans checked and spans rejected (replaced or dropped)."""

    checked: int = 0
    rejected: int = 0
    dropped_sentences: list[str] = field(default_factory=list)


def _replace_spans(sentence: str, spans: Sequence[DateMention], replacement: str) -> str:
    out = sentence
    for m in sorted(spans, key=lambda x: x.start, reverse=True):
        out = out[: m.start] + replacement + out[m.end :]
    return out


def check_text(
    text: str,
    allowed: AllowedDates,
    *,
    t: Translator,
    language: str | None,
    stats: ProseDateStats,
) -> str:
    """``text`` without dates the paper does not print (module docstring: drop the sentence, or
    replace the date when the text is a single sentence)."""
    if not text or not text.strip():
        return text
    sentences = split_sentences(text)
    kept: list[str] = []
    for sentence in sentences:
        mentions = find_mentions(sentence, language)
        stats.checked += len(mentions)
        bad = [m for m in mentions if not allowed.allows(m)]
        if not bad:
            kept.append(sentence)
            continue
        stats.rejected += len(bad)
        if len(sentences) == 1:
            kept.append(_replace_spans(sentence, bad, t(SEE_PAPER_KEY)))
        else:
            stats.dropped_sentences.append(sentence)
    if len(kept) == len(sentences) and all(a == b for a, b in zip(kept, sentences, strict=True)):
        return text
    return " ".join(kept)


def check_demand_text(
    demand: Demand,
    allowed: AllowedDates,
    *,
    t: Translator,
    language: str | None,
    stats: ProseDateStats,
) -> str:
    """A demand's sentence: an unprinted date becomes the demand's own verified value (when it
    has a resolved date that the sentence does not already name), else ``SEE_PAPER_KEY``."""
    text = demand.text
    if not text or not text.strip():
        return text
    mentions = find_mentions(text, language)
    stats.checked += len(mentions)
    bad = [m for m in mentions if not allowed.allows(m)]
    if not bad:
        return text
    stats.rejected += len(bad)
    own: date | None = None
    if demand.verified and demand.date is not None and demand.date.value_iso:
        try:
            own = date.fromisoformat(demand.date.value_iso)
        except ValueError:
            own = None
    names_own = own is not None and any(own in m.dates for m in mentions)
    if own is not None and not names_own and len(bad) == 1 and demand.value_verbatim:
        return _replace_spans(text, bad, demand.value_verbatim)
    return _replace_spans(text, bad, t(SEE_PAPER_KEY))


__all__ = [
    "SEE_PAPER_KEY",
    "AllowedDates",
    "DateMention",
    "ProseDateStats",
    "allowed_dates",
    "check_demand_text",
    "check_text",
    "find_mentions",
]
