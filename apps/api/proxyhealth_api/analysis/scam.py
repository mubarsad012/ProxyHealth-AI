"""Scam scoring — code, not the model (D-13; DOCUMENT_TAXONOMY §6; AI_PROMPTS §11.6).

Signals = regex hits from ``data/safety/scam.yaml`` over the NFKC-normalised transcript (en + es)
∪ verified model ``red_flags`` of the scam kinds (a model flag and a regex for the same signal id
count once). Guards (sender kind, document type, negative regex on the hit block) can lower a
signal's weight to 0/1. ``score`` = Σ weights; ``likely`` when ``score ≥ 4`` or one of the
``likely_rules`` holds; ``possible`` when ``2 ≤ score < 4`` or a lone payment-app request on a
private sender; else ``none``. The model's ``scam_signals`` are hints only and never score.

Outputs: ``scam_risk``, ``scam_reasons`` (the fixed ``scam.*`` keys, weight desc then table order,
≤ 6), ``is_likely_scam`` and code ``RedFlag``s for regex-only signals (text from the pack, quote =
the matched block). The same scorer serves troubleshoot (``screen_text`` lines as segments, and
``asks_for_credentials_or_payment`` feeding the data-request signal). Pure; nothing logged.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from proxyhealth_api.analysis.contacts_filter import find_contacts
from proxyhealth_api.analysis.i18n import Translator
from proxyhealth_api.analysis.transcript import Transcript
from proxyhealth_api.analysis.verify import normalize
from proxyhealth_api.contracts.analysis import Demand, RedFlag
from proxyhealth_api.contracts.enums import (
    DemandKind,
    DocumentType,
    RedFlagKind,
    ScamRisk,
    SenderKind,
    Severity,
)
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
    )


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
            )
        )
    signals.append(  # model scam_payment_method flag whose quote names no known method
        Signal("model_payment_method", None, RedFlagKind.scam_payment_method, 2, ())
    )
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
) -> bool:
    if guard.sender_kind and sender_kind.value not in guard.sender_kind:
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


def _match_signal(config: ScamConfig, kind: RedFlagKind, text: str) -> str:
    norm = normalize(text)
    for sig in config.signals:
        if sig.red_flag_kind is kind and any(p.search(norm) for p in sig.patterns):
            return sig.id
    return _MODEL_KIND_SIGNAL.get(kind, "model_payment_method")


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
    for sig in cfg.signals:
        for seg, text in norm:
            if sig.patterns and any(p.search(text) for p in sig.patterns):
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
        sid = _match_signal(cfg, flag.kind, f"{flag.source_quote or ''} {flag.text}")
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
) -> ScamOutcome:
    """``score_scam`` over every transcript block (same keyword arguments as ``score_scam``)."""
    return score_scam(
        segments_from_transcript(transcript), document_type=document_type,
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
    "Guard",
    "ScamConfig",
    "ScamOutcome",
    "Segment",
    "Signal",
    "SignalHit",
    "find_non_gov_domains",
    "host_of",
    "is_gov_host",
    "load_config",
    "parse_config",
    "retype_for_scam",
    "score_scam",
    "score_transcript",
    "segments_from_lines",
    "segments_from_transcript",
]
