"""Demand repair — deterministic citation fixes before span verification (AI_PROMPTS §11.2).

A small model often copies a fact faithfully but cites it badly: it writes the block id
(``"p1b3"``) in ``source_quote`` and the printed sentence in ``value_verbatim``, cites the block
next to the right one (or an id beyond its last block), or has its sentence cut at the
``value_verbatim`` cap. The rules below only re-arrange the model's own strings and printed block
text; they never create text. The result then goes through ``verify.verify_span`` **unchanged**
(D-09: exact or fuzzy quote with agreeing digits, value inside the quote and on the page), and a
repair is all-or-nothing: a demand that still fails is returned as the original object and is
rejected exactly as before.

* **R0** — a demand that already verifies is returned unchanged (the same object), so well-formed
  output (Gemini, the mock, the golden fixtures) is never touched.
* **R1** — ``source_quote`` holds only block ids (or nothing): the model's ``value_verbatim``
  becomes the quote ("verbatim means character-for-character as printed", §4.1) and the quoted
  ids join ``span_ids`` (at most 3).
* **R3** — (with R1) a value cut at its schema cap: the one printed sentence of the cited blocks
  that holds the value's whole-word prefix (≥ 40 characters, exact) becomes the quote.
* **R2** — (with R1) the value is narrowed to the first of the model's own typed fields that sits
  inside the quote (``date_text`` / ``amount_text`` / ``relative_rule_text`` by kind, the single
  ``documents`` item), else to the one printed date (dated kinds) or phone/URL/e-mail
  (``contact``) the quote holds; otherwise the whole printed sentence stays the value.
* **R4** — the quote is not in the cited blocks (``not found``, ``unknown block id``, ``numbers
  differ``): the shortest run of 1–3 consecutive blocks on the **same page** (never another page,
  so a ``[multiple_documents]`` page stays out) whose text holds the quote **exactly** and passes
  ``verify_span`` becomes the span; ties → nearest the first cited block, then the earliest.
* **R5** — when the repaired quote is only the value ("(703) 555-0190"), the one printed sentence
  (≤ 300 characters) of the anchored blocks holding it on token boundaries becomes the quote.

A repaired demand has ``confidence`` capped at ``medium`` and its ``verification_note`` ends in
``" (repaired: R1, R2)"`` (fixed codes, no content). Demands only: red flags are never repaired —
the dropped model flags of the sweep all quote the SAMPLE footer (§11.2). Pure functions; the SSN
and ID masks (§11.1) apply before any comparison; nothing is logged.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field

from proxyhealth_api.analysis import contacts_filter, phrasing, prose_dates, verify
from proxyhealth_api.analysis.transcript import Transcript
from proxyhealth_api.analysis.verify import VerifiedDemands
from proxyhealth_api.contracts.analysis import Demand
from proxyhealth_api.contracts.common import TextBlock
from proxyhealth_api.contracts.enums import Confidence, DemandKind
from proxyhealth_api.contracts.model_out import DemandOut

R1_ID_QUOTE = "R1"
R2_NARROWED = "R2"
R3_COMPLETED = "R3"
R4_REANCHORED = "R4"
R5_SENTENCE = "R5"

MIN_PREFIX_CHARS = 40  # R3: the shortest cut value that may pick a printed sentence
MAX_RUN = 3  # R4: ``DemandOut.span_ids`` holds at most three ids
_REANCHOR_NOTES = frozenset({verify.NOTE_NOT_FOUND, verify.NOTE_UNKNOWN_BLOCK,
                             verify.NOTE_DIGITS_DIFFER})  # fmt: skip
_DATED = frozenset({DemandKind.deadline, DemandKind.appointment})
_CONTACT_KINDS = frozenset({"phone", "url", "email"})

# One cited id as a model writes it in a quote: ``p1b3``, ``[p1b3]``, ``[p1b3|unclear]`` (the
# two-call transcript format, §5.2.3). Glue between ids: separators, whitespace, "and".
_ID_TAG_RE = re.compile(r"\[?\s*(p\d+b\d+)(?:\|[a-z,]*)?\s*\]?", re.IGNORECASE)
_ID_GLUE_RE = re.compile(r"(?:[\s,;/&]|\band\b)*", re.IGNORECASE)
_LAST_TOKEN_RE = re.compile(r"\s+\S*$")


def _max_length(name: str) -> int:
    """The schema cap of a ``DemandOut`` string field (WP0 owns it; never hard-coded here)."""
    for meta in DemandOut.model_fields[name].metadata:
        cap = getattr(meta, "max_length", None)
        if isinstance(cap, int):
            return cap
    raise RuntimeError(f"DemandOut.{name} has no max_length")


VALUE_CAP = _max_length("value_verbatim")
QUOTE_CAP = _max_length("source_quote")


@dataclass(frozen=True)
class Repair:
    """One demand after repair: ``demand`` is the input object itself when ``codes`` is empty."""

    demand: DemandOut
    codes: tuple[str, ...] = ()
    original_span_ids: list[str] = field(default_factory=list)


def quote_ids(quote: str) -> list[str] | None:
    """The block ids of a quote that holds nothing but ids (``[]`` when it is empty), else
    ``None`` — the quote then has words of its own."""
    rest = _ID_TAG_RE.sub(" ", quote)
    if _ID_GLUE_RE.fullmatch(rest) is None:
        return None
    return [m.lower() for m in _ID_TAG_RE.findall(quote)]


def _printed_sentences(blocks: Iterable[TextBlock]) -> Iterator[str]:
    """Every printed sentence (per line, ``phrasing.split_sentences``) of ``blocks`` that fits
    the ``source_quote`` cap — block text verbatim, already masked."""
    for b in blocks:
        for line in b.text.splitlines():
            for sentence in phrasing.split_sentences(line):
                s = sentence.strip()
                if s and len(s) <= QUOTE_CAP:
                    yield s


def whole_word_prefix(value: str) -> str:
    """``value`` without its last (possibly cut) token; ``""`` for a single token."""
    head = value.rstrip()
    m = _LAST_TOKEN_RE.search(head)
    return head[: m.start()] if m else ""


def _complete_cut_value(t: Transcript, ids: Sequence[str], cut: str) -> str | None:
    """R3: the one printed sentence of the cited blocks that holds the whole-word prefix."""
    if len(verify.normalize(cut)) < MIN_PREFIX_CHARS:
        return None
    key = verify.match_key(cut)
    hits = [s for s in _printed_sentences(t.blocks_for(ids)) if key in verify.match_key(s)]
    return hits[0] if len(hits) == 1 else None


def _narrow_value(d: DemandOut, t: Transcript, quote: str) -> str | None:
    """R2: the model's own typed field, else one printed date/contact span, inside the quote."""
    typed: list[str | None] = []
    if d.kind in _DATED:
        typed.append(d.date_text)
    elif d.kind is DemandKind.amount:
        typed.append(d.amount_text)
    elif d.kind is DemandKind.relative_deadline:
        typed.append(d.relative_rule_text)
    elif d.kind is DemandKind.document_requested and len(d.documents) == 1:
        typed.append(d.documents[0])
    for raw in typed:
        candidate = t.mask(raw).strip() if raw else ""
        if candidate and verify.check_value(candidate, quote) is None:
            return candidate
    spans: list[str] = []
    if d.kind in _DATED:
        spans = [quote[m.start : m.end] for m in prose_dates.find_mentions(quote) if m.dates]
    elif d.kind is DemandKind.contact:
        found = contacts_filter.find_contacts(quote, include_orgs=False)
        spans = [c.text for c in found if c.kind in _CONTACT_KINDS]
    if len(spans) == 1 and verify.check_value(spans[0], quote) is None:
        return spans[0]
    return None


def _reanchor(
    t: Transcript, d: DemandOut, ids: Sequence[str], quote: str, value: str
) -> list[str] | None:
    """R4: the shortest run of consecutive blocks on the same page holding the quote exactly."""
    page = t.page_of(ids)
    if page is None:
        if not 1 <= d.page <= len(t.pages):
            return None
        page = d.page
    order = [b.id for p in t.pages if p.page == page for b in p.blocks]
    cited = [order.index(i) for i in t.existing(ids) if i in order]
    centre = cited[0] if cited else 0
    key = verify.match_key(quote)
    for size in range(1, MAX_RUN + 1):
        runs: list[tuple[int, int, list[str]]] = []
        for start in range(len(order) - size + 1):
            run = order[start : start + size]
            text = t.text_of(run)
            if key not in verify.match_key(text):  # cheap pre-filter; never a fuzzy search
                continue
            if verify.find_quote(quote, text).note != verify.NOTE_EXACT:
                continue
            if verify.verify_span(t, run, quote, value_verbatim=value).verified:
                runs.append((abs(start - centre), start, run))
        if runs:
            return min(runs)[2]
    return None


def _sentence_for_value(t: Transcript, ids: Sequence[str], quote: str, value: str) -> str | None:
    """R5: the one printed sentence of the anchored blocks that holds a quote-only value."""
    vkey = verify.match_key(value)
    if verify.match_key(quote) != vkey:
        return None
    hits = {
        s for s in _printed_sentences(t.blocks_for(ids))
        if verify.contains_token(vkey, verify.match_key(s))
    }  # fmt: skip
    if len(hits) != 1:
        return None
    sentence = hits.pop()
    return sentence if verify.match_key(sentence) != vkey else None


def repair_demand(d: DemandOut, t: Transcript) -> Repair:
    """R0–R5 for one model demand (module docstring); all-or-nothing."""
    quote, value = t.mask(d.source_quote), t.mask(d.value_verbatim)
    original = Repair(d, (), list(d.span_ids))
    if verify.verify_span(t, d.span_ids, quote, value_verbatim=value).verified:
        return original  # R0
    codes: list[str] = []
    ids = list(d.span_ids)
    cited = quote_ids(quote)
    if cited is not None:
        if not value.strip() or quote_ids(value) is not None:
            return original
        ids = t.existing([*d.span_ids, *cited])[:MAX_RUN]
        quote = value
        codes.append(R1_ID_QUOTE)
        capped = len(d.value_verbatim) >= VALUE_CAP
        if capped and not verify.find_quote(quote, t.text_of(ids)).found:
            cut = whole_word_prefix(value)
            sentence = _complete_cut_value(t, ids, cut)
            if sentence is not None:
                quote, value = sentence, cut
                codes.append(R3_COMPLETED)
        narrowed = _narrow_value(d, t, quote)
        if narrowed is not None and narrowed != value:
            value = narrowed
            codes.append(R2_NARROWED)
    check = verify.verify_span(t, ids, quote, value_verbatim=value)
    if not check.verified and check.note in _REANCHOR_NOTES:
        run = _reanchor(t, d, ids, quote, value)
        if run is not None:
            ids = run
            codes.append(R4_REANCHORED)
            check = verify.verify_span(t, ids, quote, value_verbatim=value)
    if not check.verified:
        return original
    sentence = _sentence_for_value(t, check.span_ids, quote, value)
    if sentence is not None:
        widened = verify.verify_span(t, check.span_ids, sentence, value_verbatim=value)
        if widened.verified:
            quote, check = sentence, widened
            codes.append(R5_SENTENCE)
    confidence = Confidence.medium if d.confidence is Confidence.high else d.confidence
    repaired = d.model_copy(
        update={
            "source_quote": quote, "value_verbatim": value, "span_ids": list(check.span_ids),
            "page": check.page if check.page is not None else d.page, "confidence": confidence,
        }
    )  # fmt: skip
    return Repair(repaired, tuple(sorted(codes)), list(d.span_ids))


@dataclass
class RepairedDemands:
    """``repair_demand`` over the model's demand list, in order."""

    repairs: list[Repair] = field(default_factory=list)

    @property
    def demands(self) -> list[DemandOut]:
        """The demands to verify: repaired ones, and every other one as the model wrote it."""
        return [r.demand for r in self.repairs]

    def _by_final_id(self, checked: VerifiedDemands) -> dict[str, Repair]:
        # ``verify_demands`` records one ``sources`` entry per input demand, in input order, under
        # its final (de-duplicated) id.
        return dict(zip(checked.sources, self.repairs, strict=True))

    def verify(self, transcript: Transcript) -> VerifiedDemands:
        """``verify.verify_demands`` over ``demands``; each verified repaired demand's note then
        ends in ``" (repaired: …)"``."""
        checked = verify.verify_demands(self.demands, transcript)
        by_id = self._by_final_id(checked)
        checked.verified = [annotate(d, by_id[d.id].codes) for d in checked.verified]
        return checked

    def span_aliases(self, checked: VerifiedDemands) -> dict[str, list[str]]:
        """Final demand id → the model's own ``span_ids`` for every re-anchored (R4) demand, so a
        relative deadline whose ``anchor_span_id`` names the old block still finds its anchor
        (``deadline_rules._anchor_for``)."""
        return {
            demand_id: list(r.original_span_ids)
            for demand_id, r in self._by_final_id(checked).items()
            if R4_REANCHORED in r.codes
        }


def annotate(demand: Demand, codes: Sequence[str]) -> Demand:
    """``verification_note`` + ``" (repaired: R1, R2)"`` (fixed codes) after any repair."""
    if not codes:
        return demand
    note = f"{demand.verification_note or ''} (repaired: {', '.join(codes)})".strip()
    return demand.model_copy(update={"verification_note": note})


def repair_demands(demands: Iterable[DemandOut], transcript: Transcript) -> RepairedDemands:
    """R0–R5 over every model demand (never red flags); see the module docstring."""
    return RepairedDemands([repair_demand(d, transcript) for d in demands])


__all__ = [
    "MIN_PREFIX_CHARS",
    "QUOTE_CAP",
    "R1_ID_QUOTE",
    "R2_NARROWED",
    "R3_COMPLETED",
    "R4_REANCHORED",
    "R5_SENTENCE",
    "VALUE_CAP",
    "Repair",
    "RepairedDemands",
    "annotate",
    "quote_ids",
    "repair_demand",
    "repair_demands",
    "whole_word_prefix",
]
