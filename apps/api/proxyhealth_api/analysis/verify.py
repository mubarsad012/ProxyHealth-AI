"""Span verification — every fact is a quotation (D-09; AI_PROMPTS §11.2).

For each model ``DemandOut`` / quoted ``RedFlagOut`` the ``source_quote`` must be an exact or
OCR-normalised substring of the referenced transcript blocks, and ``value_verbatim`` (with all of
its digit runs) must sit inside the quote *and* on the page. The fuzzy fallback tolerates letter
noise only: a quote whose digits differ from the page (a changed day, year or amount) or that cuts
a printed number in half fails with ``"numbers differ from page"``. Failures are shown, not
hidden: a demand moves to ``unverified[]`` with ``verified=False``, ``confidence=low`` and a
short ``verification_note``; a model red flag whose quote fails is dropped. Confidence is forced
``low`` when a referenced block is unclear/handwriting or touches a 3 % page edge (possible crop).
``amount_text`` becomes ``Demand.amount`` only when it sits in the quote. Pure functions; nothing
logged.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from proxyhealth_api.analysis.transcript import Transcript
from proxyhealth_api.contracts.analysis import AmountInfo, Demand, RedFlag
from proxyhealth_api.contracts.common import TextBlock
from proxyhealth_api.contracts.enums import Confidence, DemandKind, RedFlagKind, Severity
from proxyhealth_api.contracts.model_out import DemandOut, RedFlagOut

VERIFIER_VERSION = "2026-09-27"
FUZZY_THRESHOLD = 0.92
EDGE_MARGIN = 0.03
MULTIPLE_DOCUMENTS_SENTINEL = "[multiple_documents]"

NOTE_EXACT = "exact"
NOTE_NOT_FOUND = "not found on page"
NOTE_VALUE_NOT_IN_QUOTE = "value not in quote"
NOTE_UNKNOWN_BLOCK = "unknown block id"
NOTE_EMPTY_QUOTE = "empty quote"
NOTE_DIGITS_DIFFER = "numbers differ from page"
NOTE_VALUE_NOT_ON_PAGE = "value not on page"

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_DQUOTES = dict.fromkeys(map(ord, "“”„«»"), '"')
_SQUOTES = dict.fromkeys(map(ord, "‘’‚‹›´`"), "'")
_UNIFY = {**_DASHES, **_DQUOTES, **_SQUOTES}
# OCR confusion map — applied to the *matching copy only* (D-09), after case folding, so both
# cases of each confusable letter map the same way (O/o→0, I/i/l→1, S/s→5, B/b→8).
_OCR = str.maketrans({"o": "0", "l": "1", "i": "1", "s": "5", "b": "8"})
_WS_RE = re.compile(r"\s+")
_DIGITS_RE = re.compile(r"\d+")
# Thousands-separated groups need at least one separator; otherwise the whole digit run is taken
# (an unseparated "1234.50" must not stop after its first three digits).
_AMOUNT_RE = re.compile(r"(\d{1,3}(?:[,.]\d{3})+(?!\d)|\d+)(?:[.,](\d{1,2}))?")
# Scripts written without spaces between words: a letter from these never forms a token boundary.
_UNSPACED_RANGES = (
    (0x0E00, 0x0EFF),  # Thai, Lao
    (0x1000, 0x109F),  # Myanmar
    (0x1780, 0x17FF),  # Khmer
    (0x2E80, 0x9FFF),  # CJK radicals, kana, ideographs
    (0xF900, 0xFAFF),  # CJK compatibility ideographs
    (0xFF66, 0xFF9F),  # half-width katakana
)


def normalize(text: str) -> str:
    """NFKC → unify dashes/quotes → collapse whitespace → strip (the D-09 normaliser)."""
    out = unicodedata.normalize("NFKC", text).translate(_UNIFY)
    return _WS_RE.sub(" ", out).strip()


def match_key(text: str) -> str:
    """``normalize``, then case folding, then the OCR confusion map; used for matching only."""
    return normalize(text).casefold().translate(_OCR)


def _keyed(text: str) -> tuple[str, list[bool]]:
    """``match_key(text)`` plus, per key character, whether it came from a printed decimal digit.

    ``str.casefold`` works character by character, so folding each character alone gives the
    same key as ``match_key`` while keeping the positions aligned with the flags.
    """
    chars: list[str] = []
    real: list[bool] = []
    for ch in normalize(text):
        folded = ch.casefold()
        chars.append(folded)
        real.extend([ch.isdecimal()] * len(folded))
    return "".join(chars).translate(_OCR), real


def ascii_digits(text: str) -> str:
    """Replace every Unicode decimal digit (Eastern Arabic, Persian, Devanagari …) with ASCII."""
    return "".join(str(unicodedata.decimal(ch)) if ch.isdecimal() else ch for ch in text)


def digit_runs(text: str) -> list[str]:
    """Every run of digits in ``text`` after NFKC, with non-ASCII decimal digits folded to ASCII."""
    return _DIGITS_RE.findall(ascii_digits(unicodedata.normalize("NFKC", text)))


_REFINE_MARGIN = 0.1  # coarse windows this close to the threshold (or to the best) are re-scanned


def _best_window(needle: str, haystack: str) -> tuple[float, int]:
    """Best ``SequenceMatcher`` ratio over a sliding window, and the window's start index.

    A coarse pass (step ``n // 8``) finds the promising regions; every coarse start whose ratio is
    within ``_REFINE_MARGIN`` of the threshold or of the coarse best is then re-scanned with step
    1 over ``start ± step``, so an off-grid window is never skipped (shifting a window by ``d``
    characters moves its ratio by about ``d / n`` ≤ 1/16).
    """
    if not needle or not haystack:
        return 0.0, 0
    n = len(needle)
    if len(haystack) <= n:
        return SequenceMatcher(None, needle, haystack, autojunk=False).ratio(), 0
    last = len(haystack) - n

    def score(start: int) -> float:
        window = haystack[start : start + n]
        return SequenceMatcher(None, needle, window, autojunk=False).ratio()

    step = max(1, n // 8)
    coarse = [(score(start), start) for start in range(0, last + 1, step)]
    best, best_start = max(coarse, key=lambda item: (item[0], -item[1]))
    if best >= 0.999 or step == 1:
        return best, best_start
    floor = min(FUZZY_THRESHOLD, best) - _REFINE_MARGIN
    seen = {start for _, start in coarse}
    for ratio, centre in coarse:
        if ratio < floor:
            continue
        for start in range(max(0, centre - step + 1), min(last, centre + step - 1) + 1):
            if start in seen:
                continue
            seen.add(start)
            refined = score(start)
            if refined > best or (refined == best and start < best_start):
                best, best_start = refined, start
    return best, best_start


def fuzzy_ratio(needle: str, haystack: str) -> float:
    """Best ``SequenceMatcher`` ratio of ``needle`` against a sliding window over ``haystack``."""
    return _best_window(needle, haystack)[0]


@dataclass(frozen=True)
class QuoteCheck:
    """Outcome of matching one quote against one corpus."""

    found: bool
    note: str | None
    ratio: float | None


_FUZZY_PAD = 12  # extra corpus characters on each side of the best window, for the alignment


def _splits_number(key: str, real: Sequence[bool], index: int) -> bool:
    """True when the boundary before ``key[index]`` falls inside a printed number."""
    if index <= 0 or index >= len(key):
        return False
    left, right = key[index - 1], key[index]
    return left.isdecimal() and right.isdecimal() and (real[index - 1] or real[index])


def _fuzzy_digits_agree(
    q: str, q_real: Sequence[bool], c: str, c_real: Sequence[bool], start: int
) -> bool:
    """True when the fuzzy alignment of ``q`` near ``c[start:]`` differs only in non-digits.

    Every insert/delete/replace between quote and page is checked: if it touches a printed digit
    on either side (a changed day, year or amount), the quote is not the page. The aligned stretch
    must not start or end inside a printed number either (``$95`` against ``$950``). Region-only
    characters before the first and after the last aligned character are context, not a change.
    """
    pad = max(_FUZZY_PAD, len(q) // 4)
    lo = max(0, start - pad)
    region = c[lo : start + len(q) + pad]
    ops = SequenceMatcher(None, q, region, autojunk=False).get_opcodes()
    while ops and ops[0][0] == "insert":
        ops.pop(0)
    while ops and ops[-1][0] == "insert":
        ops.pop()
    if not ops:
        return False
    tag, i1, i2, j1, j2 = ops[0]
    if tag == "replace" and j2 - j1 > i2 - i1:
        ops[0] = (tag, i1, i2, j2 - (i2 - i1), j2)  # the rest of the replace is context
    tag, i1, i2, j1, j2 = ops[-1]
    if tag == "replace" and j2 - j1 > i2 - i1:
        ops[-1] = (tag, i1, i2, j1, j1 + (i2 - i1))
    for tag, i1, i2, j1, j2 in ops:
        if tag != "equal" and (any(q_real[i1:i2]) or any(c_real[lo + j1 : lo + j2])):
            return False
    begin, end = lo + ops[0][3], lo + ops[-1][4]
    return not (_splits_number(c, c_real, begin) or _splits_number(c, c_real, end))


def find_quote(quote: str, corpus: str) -> QuoteCheck:
    """Exact-after-normalisation substring, else fuzzy (ratio ≥ ``FUZZY_THRESHOLD``).

    Either way the printed numbers must agree: an exact occurrence may not cut a number in half,
    and a fuzzy match may differ from the page only in letters (``NOTE_DIGITS_DIFFER`` otherwise).
    """
    q, q_real = _keyed(quote)
    c, c_real = _keyed(corpus)
    if not q:
        return QuoteCheck(False, NOTE_EMPTY_QUOTE, None)
    start = c.find(q)
    if start != -1:
        while start != -1:
            end = start + len(q)
            if not (_splits_number(c, c_real, start) or _splits_number(c, c_real, end)):
                return QuoteCheck(True, NOTE_EXACT, 1.0)
            start = c.find(q, start + 1)
        return QuoteCheck(False, NOTE_DIGITS_DIFFER, 1.0)
    ratio, start = _best_window(q, c)
    if ratio < FUZZY_THRESHOLD:
        return QuoteCheck(False, NOTE_NOT_FOUND, ratio)
    if not _fuzzy_digits_agree(q, q_real, c, c_real, start):
        return QuoteCheck(False, NOTE_DIGITS_DIFFER, ratio)
    return QuoteCheck(True, f"fuzzy match {ratio:.2f}", ratio)


_OCR_TARGETS = frozenset("0158")  # the right-hand side of the ``_OCR`` confusion map
_NO_CLASS: frozenset[str] = frozenset()


def _char_class(ch: str) -> frozenset[str]:
    """Token class of one ``match_key`` character: digit ``d``, letter ``a``, or none.

    The OCR targets ``0 1 5 8`` count as both, since the confusion map turns letters into them.
    Letters of scripts written without spaces never form a token (class none).
    """
    if ch in _OCR_TARGETS:
        return frozenset("da")
    if ch.isdecimal():
        return frozenset("d")
    if ch.isalpha():
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in _UNSPACED_RANGES):
            return _NO_CLASS
        return frozenset("a")
    return _NO_CLASS


def contains_token(needle: str, haystack: str) -> bool:
    """True when ``needle`` occurs in ``haystack`` without splitting a word or a number.

    An occurrence is rejected when the character just outside it shares a class (digit next to
    digit, letter next to letter) with the needle's edge character, so ``"$95"`` is not inside
    ``"$950"`` and ``"october 1"`` is not inside ``"october 15"``. Both sides are expected to be
    ``match_key`` output.
    """
    if not needle:
        return True
    head, tail = _char_class(needle[0]), _char_class(needle[-1])
    start = haystack.find(needle)
    while start != -1:
        end = start + len(needle)
        before = _char_class(haystack[start - 1]) if start > 0 else _NO_CLASS
        after = _char_class(haystack[end]) if end < len(haystack) else _NO_CLASS
        if not (head & before) and not (tail & after):
            return True
        start = haystack.find(needle, start + 1)
    return False


def check_value(value_verbatim: str, quote: str) -> str | None:
    """``None`` when ``value_verbatim`` sits inside ``quote`` (AI_PROMPTS §11.2), else a note.

    Strict: the normalised value must be a substring of the normalised quote on token boundaries
    (no fuzzy fallback), and every whole digit run of the value must be a digit run of the quote.
    """
    v = match_key(value_verbatim)
    if not v:
        return None
    if not contains_token(v, match_key(quote)):
        return NOTE_VALUE_NOT_IN_QUOTE
    quote_runs = set(digit_runs(quote))
    for run in digit_runs(value_verbatim):
        if run not in quote_runs:
            return NOTE_VALUE_NOT_IN_QUOTE
    return None


def is_edge_block(block: TextBlock, margin: float = EDGE_MARGIN) -> bool:
    """True when the block's bbox lies within ``margin`` of any page edge (possible crop)."""
    if block.bbox is None or len(block.bbox) != 4:
        return False
    x0, y0, x1, y1 = block.bbox
    return x0 <= margin or y0 <= margin or x1 >= 1.0 - margin or y1 >= 1.0 - margin


@dataclass(frozen=True)
class SpanVerification:
    """Result of ``verify_span`` for one fact."""

    verified: bool
    note: str | None
    confidence: Confidence
    span_ids: list[str]
    page: int | None
    edge_crop: bool
    ratio: float | None = None


def _downgrade(confidence: Confidence, blocks: Sequence[TextBlock]) -> tuple[Confidence, bool]:
    edge = any(is_edge_block(b) for b in blocks)
    unclear = any(b.is_unclear or b.is_handwriting for b in blocks)
    if edge or unclear:
        return Confidence.low, edge
    return confidence, edge


def verify_span(
    transcript: Transcript,
    span_ids: Sequence[str],
    source_quote: str,
    *,
    value_verbatim: str | None = None,
    model_confidence: Confidence = Confidence.medium,
) -> SpanVerification:
    """Check one quote (and optional value) against the blocks named by ``span_ids``.

    Unknown ids are dropped; when none remain the fact fails with ``"unknown block id"``.
    ``value_verbatim`` must sit in the quote (``check_value``) and, on token boundaries after
    OCR normalisation, in the referenced blocks themselves (never fuzzily).
    """
    ids = transcript.existing(span_ids)
    blocks = transcript.blocks_for(ids)
    page = blocks[0].page if blocks else None
    if not blocks:
        return SpanVerification(False, NOTE_UNKNOWN_BLOCK, Confidence.low, [], None, False)
    corpus = transcript.text_of(ids)
    quote = find_quote(source_quote, corpus)
    if not quote.found:
        return SpanVerification(False, quote.note, Confidence.low, ids, page, False, quote.ratio)
    if value_verbatim is not None:
        value_note = check_value(value_verbatim, source_quote)
        if value_note is None and not contains_token(match_key(value_verbatim), match_key(corpus)):
            value_note = NOTE_VALUE_NOT_ON_PAGE  # D-09: the value itself must be on the page
        if value_note is not None:
            return SpanVerification(
                False, value_note, Confidence.low, ids, page, False, quote.ratio
            )
    confidence, edge = _downgrade(model_confidence, blocks)
    return SpanVerification(True, quote.note, confidence, ids, page, edge, quote.ratio)


def parse_amount(amount_text: str | None, currency: str | None) -> AmountInfo | None:
    """``"$1,234.50"`` → ``AmountInfo(123450, "USD")``; ``None`` when no number is printed."""
    if not amount_text:
        return None
    m = _AMOUNT_RE.search(unicodedata.normalize("NFKC", amount_text))
    if not m:
        return None
    whole = int(re.sub(r"[,.]", "", m.group(1)))
    cents = int((m.group(2) or "0").ljust(2, "0"))
    code = (currency or "USD").strip().upper()[:3] or "USD"
    return AmountInfo(amount_minor=whole * 100 + cents, currency=code)


def demand_from_out(
    d: DemandOut, transcript: Transcript, *, check: SpanVerification | None = None
) -> Demand:
    """Convert a model ``DemandOut`` into a contract ``Demand`` with D-09 verification applied.

    ``date`` is left ``None`` (``deadline_rules.py`` fills it), ``reminder_eligible`` is False
    until a stated date is resolved, ``amount`` is parsed from ``amount_text`` (``_amount_of``).
    ``source_quote`` and ``value_verbatim`` get the transcript's SSN/ID masks first (§11.1), so
    they match the masked blocks and never carry the full number. ``check`` is a ``verify_span``
    result the caller already holds for exactly this call (``d.span_ids``, the masked quote and
    value, ``d.confidence``) — ``demand_repair``'s R0 check — so the page is not searched twice.
    """
    quote, value = transcript.mask(d.source_quote), transcript.mask(d.value_verbatim)
    if check is None:
        check = verify_span(
            transcript, d.span_ids, quote, value_verbatim=value, model_confidence=d.confidence
        )
    page = check.page if check.page is not None else d.page
    return Demand(
        id=d.id, kind=d.kind, text=d.text, value_verbatim=value,
        source_quote=quote, span_ids=check.span_ids or list(d.span_ids), page=page,
        confidence=check.confidence, verified=check.verified, verification_note=check.note,
        date=None, amount=_amount_of(d, transcript, quote, value), documents=list(d.documents),
        role=d.role, reminder_eligible=False, ambiguity_note=d.ambiguity_note,
    )  # fmt: skip


def _amount_of(d: DemandOut, transcript: Transcript, quote: str, value: str) -> AmountInfo | None:
    """``amount_text`` parsed only when it sits in the quote (D-09: a figure the paper does not
    print never becomes ``Demand.amount``); else, for an ``amount`` demand whose value holds one
    number, the value itself (it was checked against the quote); else ``None``."""
    if d.amount_text and check_value(transcript.mask(d.amount_text), quote) is None:
        return parse_amount(d.amount_text, d.currency)
    numbers = _AMOUNT_RE.findall(unicodedata.normalize("NFKC", value))
    if d.kind is DemandKind.amount and len(numbers) == 1:
        return parse_amount(value, d.currency)
    return None


@dataclass
class VerifiedDemands:
    """Split of the model's demands into ``demands`` (verified) and ``unverified``."""

    verified: list[Demand] = field(default_factory=list)
    unverified: list[Demand] = field(default_factory=list)
    facts_checked: int = 0
    facts_rejected: int = 0
    page_edge_crop: bool = False
    sources: dict[str, DemandOut] = field(default_factory=dict)
    """Final demand id (after duplicate renaming) → the model's ``DemandOut`` (raw date fields
    for ``deadline_rules.apply_deadline_rules``)."""


def verify_demands(
    demands: Iterable[DemandOut],
    transcript: Transcript,
    *,
    checks: Sequence[SpanVerification | None] = (),
) -> VerifiedDemands:
    """Verify every demand; duplicates of an ``id`` are renamed ``<id>_2``, ``<id>_3`` …

    ``checks[i]``, when given, is the caller's ``verify_span`` result for ``demands[i]`` exactly
    as ``demand_from_out`` would compute it (``demand_from_out``'s ``check``)."""
    out = VerifiedDemands()
    seen: set[str] = set()
    for i, d in enumerate(demands):
        demand = demand_from_out(d, transcript, check=checks[i] if i < len(checks) else None)
        if demand.id in seen:
            n = 2
            while f"{demand.id}_{n}" in seen:
                n += 1
            demand = demand.model_copy(update={"id": f"{demand.id}_{n}"})
        seen.add(demand.id)
        out.sources[demand.id] = d
        out.facts_checked += 1
        blocks = transcript.blocks_for(demand.span_ids)
        if demand.verified and any(is_edge_block(b) for b in blocks):
            out.page_edge_crop = True
        if demand.verified:
            out.verified.append(demand)
        else:
            out.facts_rejected += 1
            out.unverified.append(demand)
    return out


@dataclass
class VerifiedRedFlags:
    """Model red flags that passed (``flags``) and the count that were dropped."""

    flags: list[RedFlag] = field(default_factory=list)
    facts_checked: int = 0
    facts_rejected: int = 0


def verify_red_flags(flags: Iterable[RedFlagOut], transcript: Transcript) -> VerifiedRedFlags:
    """Keep model flags whose quote verifies; drop the rest (fixed-copy flags come from code).

    The ``[multiple_documents]`` sentinel (DOCUMENT_TAXONOMY §3.13) is kept even without a quote
    so ``fixed_notices.py`` can swap in ``fixed.multiple_documents``.
    """
    out = VerifiedRedFlags()
    for f in flags:
        if f.text.strip() == MULTIPLE_DOCUMENTS_SENTINEL:
            ids = transcript.existing(f.span_ids)
            out.flags.append(
                RedFlag(
                    kind=RedFlagKind.other, text=MULTIPLE_DOCUMENTS_SENTINEL,
                    source_quote=f.source_quote, span_ids=ids,
                    page=transcript.page_of(ids) or f.page, severity=Severity.medium,
                    fixed_copy_key=None, verified=True,
                )  # fmt: skip
            )
            continue
        out.facts_checked += 1
        if not f.source_quote:
            out.facts_rejected += 1
            continue
        quote = transcript.mask(f.source_quote)
        check = verify_span(transcript, f.span_ids, quote)
        if not check.verified:
            out.facts_rejected += 1
            continue
        severity = Severity.high if f.kind in _HIGH_KINDS else Severity.medium
        out.flags.append(
            RedFlag(
                kind=f.kind, text=f.text, source_quote=quote, span_ids=check.span_ids,
                page=check.page if check.page is not None else f.page, severity=severity,
                fixed_copy_key=None, verified=True,
            )  # fmt: skip
        )
    return out


_HIGH_KINDS = frozenset(
    {
        RedFlagKind.scam_payment_method,
        RedFlagKind.impersonation,
        RedFlagKind.notario,
        RedFlagKind.guaranteed_result,
        RedFlagKind.fee_for_free_form,
    }
)


def verify_summary_span_ids(span_ids: Iterable[str], transcript: Transcript) -> list[str]:
    """Summary ``span_ids`` that exist in the transcript (unknown ids are dropped silently)."""
    return transcript.existing(span_ids)


__all__ = [
    "EDGE_MARGIN",
    "FUZZY_THRESHOLD",
    "MULTIPLE_DOCUMENTS_SENTINEL",
    "VERIFIER_VERSION",
    "QuoteCheck",
    "SpanVerification",
    "VerifiedDemands",
    "VerifiedRedFlags",
    "NOTE_DIGITS_DIFFER",
    "NOTE_EXACT",
    "NOTE_VALUE_NOT_ON_PAGE",
    "ascii_digits",
    "check_value",
    "contains_token",
    "demand_from_out",
    "digit_runs",
    "find_quote",
    "fuzzy_ratio",
    "is_edge_block",
    "match_key",
    "normalize",
    "parse_amount",
    "verify_demands",
    "verify_red_flags",
    "verify_span",
    "verify_summary_span_ids",
]
