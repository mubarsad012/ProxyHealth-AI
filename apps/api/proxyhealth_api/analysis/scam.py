"""Scam scoring — code, not the model (D-13; DOCUMENT_TAXONOMY §6; AI_PROMPTS §11.6).

Signals = regex hits from ``data/safety/scam.yaml`` over the NFKC-normalised transcript (en, es,
ar, prs and ps patterns, every one run on every text) ∪ verified model ``red_flags`` of the scam
kinds (a model flag and a regex for the same signal id count once). A payment term inside a
negated or anti-fraud sentence ("USCIS will never ask you to pay with gift cards",
``negation_cues``) is not a hit, and a model payment flag quoting only such sentences is ignored.
A model flag is matched on its printed quote only — the model's own ``text`` ("It does not ask
for gift cards") is prose, not page evidence (D-13). A model payment flag whose quote names no
known method counts as ``model_payment_method`` (weight 2) unless its quote asks for no payment at
all: the SAMPLE footer of a demo paper, or an agency's own ``.gov`` payment portal ("Pay online at
irs.gov/payments") with no cash, money order, voucher, courier or agent named
(``payment_flag_has_evidence``, ``scam.yaml`` ``model_payment``; DOCUMENT_TAXONOMY §6.1). It takes
``payment_app``'s guards read on that quote, except when the quote names such an in-hand payment.
On a paper scored ``none`` it then neither shows nor counts as tag evidence
(``settle_payment_flags``). Dari/Pashto put the verb last, so their anti-fraud cue is a "never"
word before the payment term with a negated ask/accept/pay verb on either side of it, and a
positive verb between them ends its scope (``framed``, ``FramedCue.clause``); English and Spanish
also read a prohibitive "Never pay with gift cards" / "Nunca pague con tarjetas de regalo" there.
Guards (sender kind, document type, negative regex on the hit block, a ``.gov`` payment portal
printed in it) can lower a signal's weight to 0/1. ``score`` = Σ weights; ``likely`` when
``score ≥ 4`` or one of the ``likely_rules`` holds; ``possible`` when ``2 ≤ score < 4`` or a lone
payment-app request on a private sender; else ``none``. The model's ``scam_signals`` are hints
only and never score.

Outputs: ``scam_risk``, ``scam_reasons`` (the fixed ``scam.*`` keys, weight desc then table order,
≤ 6), ``is_likely_scam`` and code ``RedFlag``s for regex-only signals (text from the pack, quote =
the matched block). The same scorer serves troubleshoot (``screen_text`` lines as segments, and
``asks_for_credentials_or_payment`` feeding the data-request signal). Pure; nothing logged.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from proxyhealth_api.analysis.contacts_filter import find_contacts
from proxyhealth_api.analysis.i18n import Translator
from proxyhealth_api.analysis.transcript import Transcript
from proxyhealth_api.analysis.verify import (
    MULTIPLE_DOCUMENTS_SENTINEL,
    VerifiedRedFlags,
    normalize,
)
from proxyhealth_api.contracts.analysis import Demand, RedFlag
from proxyhealth_api.contracts.enums import (
    DemandKind,
    DocumentType,
    RedFlagKind,
    ScamRisk,
    SenderKind,
    Severity,
)
from proxyhealth_api.demo.fixtures import is_sample_banner
from proxyhealth_api.settings import DATA_DIR

SCAM_YAML = DATA_DIR / "safety" / "scam.yaml"
MAX_REASONS = 6
AGENCY_WINDOW = 120
MODEL_SCAM_KINDS = frozenset(
    {
        RedFlagKind.scam_payment_method, RedFlagKind.urgency_pressure, RedFlagKind.impersonation,
        RedFlagKind.notario, RedFlagKind.fee_for_free_form, RedFlagKind.guaranteed_result,
    }
)  # fmt: skip
# A verified model flag whose quote matches no regex maps to this signal id (§6.1 kinds).
_MODEL_KIND_SIGNAL: Mapping[RedFlagKind, str] = {
    RedFlagKind.urgency_pressure: "urgency_pressure",
    RedFlagKind.impersonation: "impersonation",
    RedFlagKind.notario: "notario",
    RedFlagKind.fee_for_free_form: "fee_for_free_form",
    RedFlagKind.guaranteed_result: "guaranteed",
    RedFlagKind.scam_payment_method: "model_payment_method",
}
_ACRONYM_RE = re.compile(r"^[A-Z.]{2,6}$")


@dataclass(frozen=True)
class Guard:
    """``scam.yaml`` guard: when every given condition matches, ``weight`` replaces the weight."""

    weight: int
    sender_kind: frozenset[str] = frozenset()
    document_type: frozenset[str] = frozenset()
    negative_regex: re.Pattern[str] | None = None
    requires_sender_name: bool = False
    unless_any_of: frozenset[str] = frozenset()
    gov_url_in_segment: bool = False
    """The hit block prints a ``.gov``/``.mil`` address and no phone, e-mail or other address
    (an agency's own payment portal: "pay online with PayPal at vacourts.gov"). For a model-only
    hit, its quote must also point a payment at that address (``is_gov_payment_portal``)."""
    unless_in_hand: bool = False
    """The guard does not apply when the hit's model quote names an in-hand payment (cash, a money
    order, a voucher, a courier or agent; ``scam.yaml`` ``model_payment.in_hand``)."""


@dataclass(frozen=True)
class Signal:
    """One row of the §6.1 table."""

    id: str
    reason_key: str | None
    red_flag_kind: RedFlagKind
    weight: int
    patterns: tuple[re.Pattern[str], ...]
    guards: tuple[Guard, ...] = ()
    weight_with_secrecy: int | None = None
    secrecy_patterns: tuple[re.Pattern[str], ...] = ()
    weight_with_threat: int | None = None
    negation: bool = False
    """Matches in a negated or anti-fraud sentence ("USCIS will never ask you to pay with gift
    cards") do not count (``ScamConfig.negation_cues``)."""


@dataclass(frozen=True)
class NegationCues:
    """``scam.yaml`` ``negation_cues``: when a payment term sits in a sentence that negates the
    request or describes fraud, it is agency anti-fraud boilerplate, not a demand."""

    before: tuple[re.Pattern[str], ...] = ()
    """Cue somewhere before the match in the same sentence ("will never ask you to pay by")."""
    after: tuple[re.Pattern[str], ...] = ()
    """Cue after the match in the same sentence ("… with gift cards is a scam")."""
    breaks: re.Pattern[str] | None = None
    """Words between a ``before`` cue and the match that end its scope ("… only gift cards")."""
    framed: tuple[FramedCue, ...] = ()
    """Paired cues (``FramedCue``): verb-last Dari/Pashto ("هرگز … کارت تحفه … نمی‌خواهند") and the
    en/es prohibitive ("Never pay with gift cards")."""


@dataclass(frozen=True)
class FramedCue:
    """One ``negation_cues.framed`` item: ``before`` must match in the sentence before the payment
    term and ``after`` after it (either may be absent, not both), with no ``breaks`` word and no
    ``clause`` word (a positive finite verb of the pair's language: "هرگز دیر نکنید، کارت تحفه
    تهیه کنید") between the cue and the term on either side. On the ``after`` side only the text
    before its ``verb`` group (the negated verb itself) is checked."""

    before: re.Pattern[str] | None = None
    after: re.Pattern[str] | None = None
    clause: re.Pattern[str] | None = None

    def unbroken(self, between: str, breaks: re.Pattern[str] | None) -> bool:
        return not any(p is not None and p.search(between) for p in (breaks, self.clause))

    def after_ok(self, after: str, breaks: re.Pattern[str] | None) -> bool:
        if self.after is None:
            return True
        found = self.after.search(after)
        if found is None:
            return False
        has_verb = "verb" in self.after.groupindex and found.group("verb") is not None
        return self.unbroken(after[: found.start("verb") if has_verb else found.end()], breaks)

    def before_ok(self, before: str, breaks: re.Pattern[str] | None) -> bool:
        if self.before is None:
            return True
        return any(self.unbroken(before[m.end() :], breaks) for m in self.before.finditer(before))


@dataclass(frozen=True)
class ScamConfig:
    """Parsed ``data/safety/scam.yaml`` (schema DOCUMENT_TAXONOMY §6.6)."""

    version: str
    possible: int
    likely: int
    gov_tlds: tuple[str, ...]
    agency_names: tuple[str, ...]
    agency_document_types: frozenset[DocumentType]
    agency_sender_kinds: frozenset[str]
    private_sender_kinds: frozenset[str]
    payment_signals: frozenset[str]
    threat_signals: frozenset[str]
    fee_signals: frozenset[str]
    request_signals: frozenset[str]
    likely_rules: tuple[str, ...]
    signals: tuple[Signal, ...]
    reviewed_by: Mapping[str, str | None]
    negation_cues: NegationCues = field(default_factory=NegationCues)
    portal_cues: tuple[re.Pattern[str], ...] = ()
    """``model_payment.portal``: a pay phrase ending right before a printed address ("Pay online
    at …"), every language's list."""
    in_hand_cues: tuple[re.Pattern[str], ...] = ()
    """``model_payment.in_hand``: cash, a money order, a voucher, a courier or agent."""

    def names_in_hand(self, quote: str | None) -> bool:
        """``quote`` asks for a payment handed over in cash, by money order or voucher, or to a
        courier or agent (never an agency's online portal)."""
        text = normalize(quote or "")
        return bool(text) and any(p.search(text) for p in self.in_hand_cues)

    def signal(self, signal_id: str) -> Signal | None:
        """The signal with id ``signal_id`` from the table, or ``None`` when it is not listed."""
        return next((s for s in self.signals if s.id == signal_id), None)

    @property
    def reason_keys(self) -> frozenset[str]:
        """Every ``scam.*`` chip key the table can emit."""
        return frozenset(s.reason_key for s in self.signals if s.reason_key)


def _patterns(raw: Any) -> tuple[re.Pattern[str], ...]:
    out: list[re.Pattern[str]] = []
    if isinstance(raw, Mapping):
        for items in raw.values():
            out += [re.compile(str(p), re.IGNORECASE) for p in (items or [])]
    return tuple(out)


def _guard(raw: Mapping[str, Any]) -> Guard:
    neg = raw.get("negative_regex")
    return Guard(
        weight=int(raw.get("weight", 0)),
        sender_kind=frozenset(str(x) for x in raw.get("sender_kind") or []),
        document_type=frozenset(str(x) for x in raw.get("document_type") or []),
        negative_regex=re.compile(str(neg), re.IGNORECASE) if neg else None,
        requires_sender_name=bool(raw.get("requires_sender_name", False)),
        unless_any_of=frozenset(str(x) for x in raw.get("unless_any_of") or []),
        gov_url_in_segment=bool(raw.get("gov_url_in_segment", False)),
    )


def _framed(raw: Any) -> tuple[FramedCue, ...]:
    """``negation_cues.framed`` → ``FramedCue``s, every language's list."""
    out: list[FramedCue] = []

    def opt(value: Any) -> re.Pattern[str] | None:
        return re.compile(str(value), re.IGNORECASE) if value else None

    if isinstance(raw, Mapping):
        for lang, items in raw.items():
            for pair in items or []:
                cue = FramedCue(opt(pair.get("before")), opt(pair.get("after")),
                                opt(pair.get("clause")))  # fmt: skip
                if cue.before is None and cue.after is None:
                    raise ValueError(f"scam.yaml negation_cues.framed.{lang}: before or after")
                out.append(cue)
    return tuple(out)


def _negation_cues(raw: Any) -> NegationCues:
    if not isinstance(raw, Mapping):
        return NegationCues()
    breaks = raw.get("breaks")
    return NegationCues(
        before=_patterns(raw.get("before")), after=_patterns(raw.get("after")),
        breaks=re.compile(str(breaks), re.IGNORECASE) if breaks else None,
        framed=_framed(raw.get("framed")),
    )  # fmt: skip


def _model_payment(raw: Any) -> tuple[tuple[re.Pattern[str], ...], tuple[re.Pattern[str], ...]]:
    """``model_payment`` → (``portal`` patterns, ``in_hand`` patterns), every language's list."""
    if not isinstance(raw, Mapping):
        return (), ()
    return _patterns(raw.get("portal")), _patterns(raw.get("in_hand"))


def parse_config(data: Mapping[str, Any]) -> ScamConfig:
    """Build a ``ScamConfig`` from the loaded YAML mapping (raises on a malformed table)."""
    signals: list[Signal] = []
    for raw in data["signals"]:
        signals.append(
            Signal(
                id=str(raw["id"]),
                reason_key=str(raw["reason_key"]) if raw.get("reason_key") else None,
                red_flag_kind=RedFlagKind(str(raw["red_flag_kind"])),
                weight=int(raw["weight"]),
                patterns=_patterns(raw.get("patterns")),
                guards=tuple(_guard(g) for g in raw.get("guards") or []),
                weight_with_secrecy=raw.get("weight_with_secrecy"),
                secrecy_patterns=_patterns(raw.get("secrecy_patterns")),
                weight_with_threat=raw.get("weight_with_threat"),
                negation=bool(raw.get("negation", False)),
            )
        )
    # A model scam_payment_method flag whose quote names no known method: payment_app's guards
    # (an agency's own .gov portal → 0; a named private sender → 1), §6.1 — never when the quote
    # names cash, a money order, a voucher, a courier or an agent.
    app = next((s for s in signals if s.id == "payment_app"), None)
    signals.append(
        Signal("model_payment_method", None, RedFlagKind.scam_payment_method, 2, (),
               guards=tuple(replace(g, unless_in_hand=True) for g in (app.guards if app else ())))
    )  # fmt: skip
    portal, in_hand = _model_payment(data.get("model_payment"))
    thresholds = data.get("thresholds") or {}

    def ids(key: str) -> frozenset[str]:
        return frozenset(str(x) for x in data.get(key) or [])

    return ScamConfig(
        version=str(data.get("version", "0")),
        possible=int(thresholds.get("possible", 2)),
        likely=int(thresholds.get("likely", 4)),
        gov_tlds=tuple(str(x).lower() for x in data.get("gov_tlds") or [".gov", ".mil"]),
        agency_names=tuple(str(x) for x in data.get("agency_names") or []),
        agency_document_types=frozenset(DocumentType(str(x)) for x in data.get(
            "agency_document_types") or []),
        agency_sender_kinds=ids("agency_sender_kinds"),
        private_sender_kinds=ids("private_sender_kinds"),
        payment_signals=ids("payment_signals") | {"model_payment_method"},
        threat_signals=ids("threat_signals"),
        fee_signals=ids("fee_signals"),
        request_signals=ids("request_signals") | {"model_payment_method"},
        likely_rules=tuple(str(x) for x in data.get("likely_rules") or []),
        signals=tuple(signals),
        reviewed_by=dict(data.get("reviewed_by") or {}),
        negation_cues=_negation_cues(data.get("negation_cues")),
        portal_cues=portal, in_hand_cues=in_hand,
    )  # fmt: skip


@lru_cache(maxsize=4)
def load_config(path: Path = SCAM_YAML) -> ScamConfig:
    """Load and cache ``scam.yaml``."""
    return parse_config(yaml.safe_load(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class Segment:
    """A piece of text the scorer scans: a transcript block or a troubleshoot screen line."""

    id: str
    page: int | None
    text: str


def segments_from_transcript(transcript: Transcript) -> list[Segment]:
    """Transcript blocks as scorer segments (ids and pages kept for red-flag crops)."""
    return [Segment(b.id, b.page, b.text) for b in transcript.blocks]


def segments_from_lines(lines: Iterable[str], prefix: str = "s") -> list[Segment]:
    """Plain lines (troubleshoot ``screen_text`` / ``user_goal``) as segments ``s1``, ``s2`` …"""
    return [Segment(f"{prefix}{i}", None, line) for i, line in enumerate(lines, 1) if line]


@dataclass
class SignalHit:
    """A fired signal: where the regex matched (if it did) and whether a model flag backs it."""

    signal: Signal
    segment: Segment | None = None
    from_regex: bool = False
    from_model: bool = False
    model_quote: str | None = None
    weight: int = 0


@dataclass
class ScamOutcome:
    """``score_scam`` result; the pipeline copies the first four fields into the result."""

    scam_risk: ScamRisk
    is_likely_scam: bool
    scam_reasons: list[str]
    red_flags: list[RedFlag]
    score: int
    hits: dict[str, SignalHit] = field(default_factory=dict)
    likely_rule: str | None = None
    hints: list[str] = field(default_factory=list)

    @property
    def fired(self) -> list[str]:
        """Signal ids with a positive weight after guards."""
        return [sid for sid, h in self.hits.items() if h.weight > 0]


_SENTENCE_END_RE = re.compile(r"[.!?;\n]")


def _ends_sentence(text: str, i: int) -> bool:
    """``text[i]`` (one of ``.!?;`` or a newline) ends a sentence; a decimal point ("1.5") or a
    dot inside a word or domain ("uscis.gov") does not."""
    if text[i] != ".":
        return True
    before = text[i - 1] if i > 0 else ""
    after = text[i + 1] if i + 1 < len(text) else ""
    return not ((before.isdigit() and after.isdigit()) or (before.isalnum() and after.isalnum()))


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    """(start, end) of the sentence around ``text[start:end]``."""
    head = 0
    for m in _SENTENCE_END_RE.finditer(text, 0, start):
        if _ends_sentence(text, m.start()):
            head = m.end()
    tail = len(text)
    for m in _SENTENCE_END_RE.finditer(text, end):
        if _ends_sentence(text, m.start()):
            tail = m.start()
            break
    return head, tail


def is_negated(text: str, start: int, end: int, cues: NegationCues) -> bool:
    """True when the match ``text[start:end]`` sits in a sentence that negates the request or
    describes fraud ("… will never ask you to pay with gift cards", "Nunca le pediremos pagos
    con tarjetas de regalo", "anyone who asks for gift cards is a scammer") — unless a scope
    break ("only", "instead", "but") stands between the negating cue and the match. ``framed``
    cues (``FramedCue``): verb-last Dari/Pashto, the "never" word before the match and the
    negated ask/accept/pay verb after it ("هرگز پول را از راه … کارت تحفه … نمی‌خواهند"), and the
    en/es prohibitive ("Never pay with gift cards"); no break or positive verb on either side."""
    head, tail = _sentence_bounds(text, start, end)
    before = text[head:start]
    breaks = cues.breaks
    for pattern in cues.before:
        for m in pattern.finditer(before):
            if breaks is None or not breaks.search(before[m.end() :]):
                return True
    after = text[end:tail]
    if any(p.search(after) for p in cues.after):
        return True
    return any(c.after_ok(after, breaks) and c.before_ok(before, breaks) for c in cues.framed)


def _signal_match(sig: Signal, text: str, cues: NegationCues) -> bool:
    """True when a pattern of ``sig`` matches ``text`` outside a negated sentence."""
    for p in sig.patterns:
        for m in p.finditer(text):
            if not (sig.negation and is_negated(text, m.start(), m.end(), cues)):
                return True
    return False


def is_anti_fraud_quote(quote: str | None, config: ScamConfig | None = None) -> bool:
    """True when ``quote`` names a payment method only inside negated / anti-fraud sentences
    ("USCIS will never ask you to pay by Western Union"): such a model red flag is boilerplate,
    not a demand, and neither scores nor shows."""
    if not quote:
        return False
    cfg = config or load_config()
    text = normalize(quote)
    seen = False
    for sig in cfg.signals:
        if not sig.negation:
            continue
        for p in sig.patterns:
            for m in p.finditer(text):
                seen = True
                if not is_negated(text, m.start(), m.end(), cfg.negation_cues):
                    return False
    return seen


def _agency_regex(names: Sequence[str]) -> re.Pattern[str]:
    parts: list[str] = []
    for name in names:
        esc = re.escape(name)
        if _ACRONYM_RE.match(name):
            parts.append(rf"(?-i:(?<![A-Za-z]){esc}(?![A-Za-z]))")
        else:
            parts.append(rf"\b{esc}\b")
    return re.compile("|".join(parts) or r"(?!x)x", re.IGNORECASE)


def host_of(url_or_email: str) -> str:
    """Lower-case host of a URL, bare domain or e-mail address (``www.`` dropped)."""
    s = url_or_email.strip().lower()
    if "@" in s and "/" not in s:
        s = s.rsplit("@", 1)[1]
    s = re.sub(r"^[a-z]+://", "", s)
    s = s.split("/", 1)[0].split(":", 1)[0].rstrip(".")
    return s[4:] if s.startswith("www.") else s


def is_gov_host(host: str, gov_tlds: Sequence[str]) -> bool:
    """True when the registrable domain ends in ``.gov``/``.mil`` (the configured TLDs)."""
    return any(host == tld.lstrip(".") or host.endswith(tld) for tld in gov_tlds)


def _allowed_host(host: str, allowed: Iterable[str]) -> bool:
    return any(host == a or host.endswith("." + a) for a in allowed if a)


def find_non_gov_domains(
    segments: Sequence[Segment],
    config: ScamConfig,
    *,
    resource_hosts: Iterable[str] = (),
) -> list[tuple[Segment, str]]:
    """(segment, host) for every non-.gov URL/e-mail/domain within ``AGENCY_WINDOW`` characters
    of an agency name (DB resource hosts excepted)."""
    agency = _agency_regex(config.agency_names)
    allowed = [host_of(h) for h in resource_hosts]
    texts = [normalize(s.text) for s in segments]
    full = "\n".join(texts)
    starts: list[int] = []
    pos = 0
    for text in texts:
        starts.append(pos)
        pos += len(text) + 1
    names = [m.start() for m in agency.finditer(full)] + [m.end() for m in agency.finditer(full)]
    out: list[tuple[Segment, str]] = []
    if not names:
        return out
    for c in find_contacts(full, include_orgs=False):
        if c.kind not in ("url", "email"):
            continue
        host = host_of(c.text)
        if not host or is_gov_host(host, config.gov_tlds) or _allowed_host(host, allowed):
            continue
        if not any(abs(n - c.start) <= AGENCY_WINDOW or abs(n - c.end) <= AGENCY_WINDOW
                   for n in names):  # fmt: skip
            continue
        index = max(i for i, st in enumerate(starts) if st <= c.start)
        out.append((segments[index], host))
    return out


def _guard_applies(
    guard: Guard,
    hit: SignalHit,
    *,
    document_type: DocumentType | None,
    sender_kind: SenderKind,
    sender_as_written: str | None,
    fired_before: set[str],
    config: ScamConfig,
) -> bool:
    if guard.sender_kind and sender_kind.value not in guard.sender_kind:
        return False
    if guard.unless_in_hand and config.names_in_hand(hit.model_quote):
        return False
    # The hit block; for a model-only hit, the flag's verified quote must send the payment to the
    # .gov address it prints ("Pay online at irs.gov/payments"), not merely print one.
    if guard.gov_url_in_segment and not (
        _gov_portal_only(hit.segment.text, config.gov_tlds) if hit.segment is not None
        else is_gov_payment_portal(hit.model_quote, config)
    ):  # fmt: skip
        return False
    if guard.document_type and (document_type is None or document_type.value not in
                                guard.document_type):  # fmt: skip
        return False
    if guard.requires_sender_name and not (sender_as_written or "").strip():
        return False
    if guard.negative_regex is not None:
        texts = [t for t in (hit.segment.text if hit.segment else None, hit.model_quote) if t]
        if not texts or not all(guard.negative_regex.search(normalize(t)) for t in texts):
            return False
    return not (guard.unless_any_of & fired_before)


def _gov_portal_only(text: str, gov_tlds: Sequence[str]) -> bool:
    """The block prints at least one ``.gov``/``.mil`` address and no other contact (no phone,
    e-mail or non-government address a payment could be sent to)."""
    contacts = find_contacts(normalize(text), include_orgs=False)
    urls = [c for c in contacts if c.kind == "url"]
    if not urls or len(urls) != len(contacts):
        return False
    return all(is_gov_host(host_of(c.text), gov_tlds) for c in urls)


def _match_signal(config: ScamConfig, kind: RedFlagKind, quote: str) -> str:
    """The signal a verified model flag of ``kind`` stands for: the table row whose pattern
    matches the printed ``quote`` outside a negated sentence, else the kind's own signal."""
    norm = normalize(quote)
    for sig in config.signals:
        if sig.red_flag_kind is kind and _signal_match(sig, norm, config.negation_cues):
            return sig.id
    return _MODEL_KIND_SIGNAL.get(kind, "model_payment_method")


_PAYMENT_METHODS = ("gift_card", "wire_transfer", "payment_app", "crypto")


def is_gov_payment_portal(quote: str | None, config: ScamConfig | None = None) -> bool:
    """``quote`` sends a payment to an agency's own ``.gov``/``.mil`` address it prints ("Pay
    online at irs.gov/payments or mail a check …"): a ``model_payment.portal`` phrase ends right
    before that address, the quote prints no phone, e-mail or other address, and it names no cash,
    money order, voucher, courier or agent. "Send the $500 penalty in cash to our office. See
    www.uscis.gov" is not one: the .gov link is decoration, not where the money goes."""
    cfg = config or load_config()
    text = normalize(quote or "")
    if not text or not _gov_portal_only(text, cfg.gov_tlds) or cfg.names_in_hand(text):
        return False
    urls = [c for c in find_contacts(text, include_orgs=False) if c.kind == "url"]
    return any(p.search(text[: c.start]) for c in urls for p in cfg.portal_cues)


def payment_flag_has_evidence(quote: str | None, config: ScamConfig | None = None) -> bool:
    """True when a verified model ``scam_payment_method`` flag quoting ``quote`` may show and score
    (DOCUMENT_TAXONOMY §6.1 model-only payment row).

    The flag stands unless its quote asks for no payment: anti-fraud boilerplate
    (``is_anti_fraud_quote``), the SAMPLE footer of a demo paper or a piece of it
    (``demo.fixtures.is_sample_banner``), or — when it names none of the four methods — an agency's
    own ``.gov`` payment portal (``is_gov_payment_portal``). Any other quote keeps the flag, in
    every language: a model that marks a payment demand is never second-guessed by a word list.
    """
    if not quote or not quote.strip():
        return False
    cfg = config or load_config()
    if is_anti_fraud_quote(quote, cfg) or is_sample_banner(quote):
        return False
    text = normalize(quote)
    return names_payment_method(text, cfg) or not is_gov_payment_portal(text, cfg)


def names_payment_method(quote: str | None, config: ScamConfig | None = None) -> bool:
    """``quote`` names a gift card, wire transfer, payment app or cryptocurrency outside a negated
    sentence (the four §6.1 payment-method rows)."""
    cfg = config or load_config()
    text = normalize(quote or "")
    for sid in _PAYMENT_METHODS:
        sig = cfg.signal(sid)
        if text and sig is not None and _signal_match(sig, text, cfg.negation_cues):
            return True
    return False


def screen_model_flags(
    checked: VerifiedRedFlags, config: ScamConfig | None = None
) -> VerifiedRedFlags:
    """The verified model flags that may show and score: a payment flag whose quote asks for no
    payment (``payment_flag_has_evidence``) is dropped and counted as a rejected fact
    (verification only gets stricter, D-09), and a repeated flag (same kind, same quote) shows
    once."""
    cfg = config or load_config()
    kept: list[RedFlag] = []
    seen: set[tuple[RedFlagKind, str, bool]] = set()
    rejected = checked.facts_rejected
    for f in checked.flags:
        if f.kind is RedFlagKind.scam_payment_method and not payment_flag_has_evidence(
            f.source_quote, cfg
        ):
            rejected += 1
            continue
        sentinel = f.text.strip() == MULTIPLE_DOCUMENTS_SENTINEL
        key = (f.kind, normalize(f.source_quote or "").casefold(), sentinel)
        if key not in seen:
            seen.add(key)
            kept.append(f)
    return VerifiedRedFlags(
        flags=kept, facts_checked=checked.facts_checked, facts_rejected=rejected
    )


def settle_payment_flags(
    checked: VerifiedRedFlags, outcome: ScamOutcome, config: ScamConfig | None = None
) -> VerifiedRedFlags:
    """After scoring: on a paper the scorer found no scam on (``scam_risk == none``), a model
    ``scam_payment_method`` flag whose quote names none of the four methods ("Pay at the leasing
    office or call …", read by a small model as "It does not ask for gift cards") neither shows
    nor counts as scam evidence for the tags; it is a rejected fact (§6.1 model-only row). On a
    possible or likely scam it stays — it is part of what the reader is warned about."""
    if outcome.scam_risk is not ScamRisk.none:
        return checked
    cfg = config or load_config()
    kept = [
        f for f in checked.flags
        if f.kind is not RedFlagKind.scam_payment_method
        or names_payment_method(f.source_quote, cfg)
    ]  # fmt: skip
    return VerifiedRedFlags(
        flags=kept, facts_checked=checked.facts_checked,
        facts_rejected=checked.facts_rejected + len(checked.flags) - len(kept),
    )  # fmt: skip


def score_scam(
    segments: Sequence[Segment],
    *,
    document_type: DocumentType | None,
    sender_kind: SenderKind = SenderKind.unknown,
    sender_as_written: str | None = None,
    model_flags: Iterable[RedFlag] = (),
    model_signals: Iterable[str] = (),
    demands: Iterable[Demand] = (),
    credential_request: bool = False,
    resource_hosts: Iterable[str] = (),
    t: Translator | None = None,
    config: ScamConfig | None = None,
) -> ScamOutcome:
    """Score one paper or screenshot (DOCUMENT_TAXONOMY §6.2) — see the module docstring.

    ``model_flags`` must be the *verified* model red flags (``verify_red_flags``). ``demands`` are
    the verified demands (used by ``no_sender``). ``credential_request`` is troubleshoot's
    ``asks_for_credentials_or_payment``. ``resource_hosts`` are DB URLs that are never counted as
    a fake agency domain. ``t`` renders code red-flag text (pack key used as text without it).
    """
    cfg = config or load_config()
    hits: dict[str, SignalHit] = {}
    norm = [(seg, normalize(seg.text)) for seg in segments]
    cues = cfg.negation_cues
    for sig in cfg.signals:
        for seg, text in norm:
            if sig.patterns and _signal_match(sig, text, cues):
                hits[sig.id] = SignalHit(sig, segment=seg, from_regex=True)
                break
    non_gov = cfg.signal("non_gov_domain")
    if non_gov is not None:
        found = find_non_gov_domains(segments, cfg, resource_hosts=resource_hosts)
        if found:
            hits["non_gov_domain"] = SignalHit(non_gov, segment=found[0][0], from_regex=True)
    for flag in model_flags:
        if not flag.verified or flag.kind not in MODEL_SCAM_KINDS:
            continue
        if flag.kind is RedFlagKind.scam_payment_method and not payment_flag_has_evidence(
            flag.source_quote, cfg
        ):
            continue  # anti-fraud boilerplate, the SAMPLE footer, an agency's own .gov portal
        # The printed quote only: the model's ``text`` is its own prose, not the page (D-13).
        sid = _match_signal(cfg, flag.kind, flag.source_quote or "")
        model_sig = cfg.signal(sid)
        if model_sig is None:
            continue
        hit = hits.setdefault(sid, SignalHit(model_sig))
        hit.from_model = True
        hit.model_quote = hit.model_quote or flag.source_quote
    data_req = cfg.signal("id_or_payment_data_request")
    if credential_request and data_req is not None:
        hits.setdefault(data_req.id, SignalHit(data_req)).from_model = True
    no_sender = cfg.signal("no_sender")
    money = any(d.kind is DemandKind.amount or d.role == "payment_due" for d in demands)
    if no_sender is not None and not (sender_as_written or "").strip():
        if money or data_req is not None and data_req.id in hits:
            hits.setdefault(no_sender.id, SignalHit(no_sender, from_regex=True))
    # weights: guards first (``unless_any_of`` sees every signal that fired before guards)
    fired_before = set(hits)
    for hit in hits.values():
        hit.weight = hit.signal.weight
        for guard in hit.signal.guards:
            if _guard_applies(
                guard, hit, document_type=document_type, sender_kind=sender_kind,
                sender_as_written=sender_as_written, fired_before=fired_before - {hit.signal.id},
                config=cfg,
            ):  # fmt: skip
                hit.weight = guard.weight
                break
    threat = any(hits[s].weight > 0 for s in cfg.threat_signals if s in hits)
    urgency = hits.get("urgency_pressure")
    if urgency is not None and urgency.weight > 0 and urgency.signal.weight_with_secrecy:
        if any(p.search(text) for _seg, text in norm for p in urgency.signal.secrecy_patterns):
            urgency.weight = int(urgency.signal.weight_with_secrecy)
    request = hits.get("id_or_payment_data_request")
    if request is not None and request.weight > 0:
        if credential_request:
            request.weight = max(request.weight, 2)
        if threat and request.signal.weight_with_threat:
            request.weight = max(request.weight, int(request.signal.weight_with_threat))
    return _decide(cfg, hits, sender_kind, list(model_signals), t)


def _positive(hits: Mapping[str, SignalHit], ids: Iterable[str], minimum: int = 1) -> bool:
    return any(hits[s].weight >= minimum for s in ids if s in hits)


def _decide(
    cfg: ScamConfig,
    hits: dict[str, SignalHit],
    sender_kind: SenderKind,
    hints: list[str],
    t: Translator | None,
) -> ScamOutcome:
    score = sum(h.weight for h in hits.values() if h.weight > 0)
    payment = _positive(hits, cfg.payment_signals)
    threat = _positive(hits, cfg.threat_signals)
    rules = {
        "payment_and_agency_sender": _positive(hits, cfg.payment_signals, 2)
        and sender_kind.value in cfg.agency_sender_kinds,
        "payment_and_threat": payment and threat,
        "nongov_and_request": _positive(hits, ["non_gov_domain"])
        and _positive(hits, cfg.request_signals - {"non_gov_domain"}),
        "guaranteed_and_fee": _positive(hits, ["guaranteed"]) and _positive(hits, cfg.fee_signals),
    }
    likely_rule = next((r for r in cfg.likely_rules if rules.get(r)), None)
    lone_app = (
        _positive(hits, ["payment_app"])
        and sender_kind.value in cfg.private_sender_kinds
        and not threat
    )
    if score >= cfg.likely or likely_rule is not None:
        risk = ScamRisk.likely
    elif score >= cfg.possible or lone_app:
        risk = ScamRisk.possible
    else:
        risk = ScamRisk.none
    order = {s.id: i for i, s in enumerate(cfg.signals)}
    fired = sorted(
        (h for h in hits.values() if h.weight > 0 and h.signal.reason_key),
        key=lambda h: (-h.weight, order.get(h.signal.id, 99)),
    )
    reasons = [h.signal.reason_key for h in fired if h.signal.reason_key][:MAX_REASONS]
    flags: list[RedFlag] = []
    if risk is not ScamRisk.none:
        severity = Severity.high if risk is ScamRisk.likely else Severity.medium
        for h in fired:
            if not h.from_regex or h.from_model or h.segment is None or not h.signal.reason_key:
                continue
            key = h.signal.reason_key
            flags.append(
                RedFlag(
                    kind=h.signal.red_flag_kind, text=t(key) if t else key,
                    source_quote=h.segment.text,
                    span_ids=[h.segment.id] if h.segment.page is not None else [],
                    page=h.segment.page, severity=severity, fixed_copy_key=None, verified=True,
                )  # fmt: skip
            )
    return ScamOutcome(
        scam_risk=risk, is_likely_scam=risk is ScamRisk.likely, scam_reasons=reasons,
        red_flags=flags, score=score, hits=hits, likely_rule=likely_rule if risk is
        ScamRisk.likely else None, hints=hints,
    )  # fmt: skip


def score_transcript(
    transcript: Transcript,
    *,
    document_type: DocumentType | None,
    sender_kind: SenderKind = SenderKind.unknown,
    sender_as_written: str | None = None,
    model_flags: Iterable[RedFlag] = (),
    model_signals: Iterable[str] = (),
    demands: Iterable[Demand] = (),
    credential_request: bool = False,
    resource_hosts: Iterable[str] = (),
    t: Translator | None = None,
    config: ScamConfig | None = None,
    skip_ids: Collection[str] = (),
) -> ScamOutcome:
    """``score_scam`` over every transcript block (same keyword arguments as ``score_scam``)
    except the blocks in ``skip_ids`` (a sample paper's SAMPLE footer, ``classify.py``)."""
    segments = [s for s in segments_from_transcript(transcript) if s.id not in skip_ids]
    return score_scam(
        segments, document_type=document_type,
        sender_kind=sender_kind, sender_as_written=sender_as_written, model_flags=model_flags,
        model_signals=model_signals, demands=demands, credential_request=credential_request,
        resource_hosts=resource_hosts, t=t, config=config,
    )  # fmt: skip


def retype_for_scam(
    document_type: DocumentType, scam_risk: ScamRisk, config: ScamConfig | None = None
) -> DocumentType:
    """§6.5: a ``likely`` scam on an agency paper type becomes ``other_notice``; court papers and
    everything else keep their type."""
    cfg = config or load_config()
    if scam_risk is ScamRisk.likely and document_type in cfg.agency_document_types:
        return DocumentType.other_notice
    return document_type


__all__ = [
    "MODEL_SCAM_KINDS",
    "SCAM_YAML",
    "FramedCue",
    "Guard",
    "ScamConfig",
    "ScamOutcome",
    "Segment",
    "Signal",
    "SignalHit",
    "NegationCues",
    "find_non_gov_domains",
    "host_of",
    "is_anti_fraud_quote",
    "is_gov_payment_portal",
    "is_gov_host",
    "is_negated",
    "load_config",
    "names_payment_method",
    "parse_config",
    "payment_flag_has_evidence",
    "retype_for_scam",
    "score_scam",
    "score_transcript",
    "screen_model_flags",
    "settle_payment_flags",
    "segments_from_lines",
    "segments_from_transcript",
]
