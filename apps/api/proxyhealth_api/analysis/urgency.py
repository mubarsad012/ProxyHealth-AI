"""Urgency — computed in code from verified facts and the document type (D-12; TAXONOMY §5).

The model never sets a level. ``compute_urgency`` implements DOCUMENT_TAXONOMY §5.1:

1. the emergency lexicon fired → ``emergency``;
2. candidates = verified demands with a ``stated`` ``value_iso`` whose ``role`` is a driving role
   of the type (§5.2); ``notice_date`` / ``decision_date`` / ``other`` never drive;
3. a future date → ``critical`` ≤ 7 days only for the type's critical set, else ``high`` ≤ 14,
   ``medium`` ≤ 30, ``info`` beyond (the most severe candidate wins; ties → nearest);
4. only past dates (≤ 60 days) → ``date_passed`` headline, ``critical`` on immigration/court
   papers, else ``high`` for response/payment/appointment/hearing and ``medium`` for expiry/move,
   plus an ``expired_date`` red flag;
5. only ``estimated`` dates → the same thresholds capped at ``medium``; the headline's ``{date}``
   and ``date_iso`` are both the ISO day (``date == date_iso`` marks the estimate: the client
   writes it out in the reader's language, as on the demand row, whose readable server line is
   ``DateInfo.localized_line`` — ``deadline_rules.estimate_text``);
6. floors: ``nta``, ``hearing_notice``, ``eviction_summons``, ``uscis_noid``, ``utility_shutoff``,
   ``pay_or_quit`` never below ``high``;
7. no verified date drives it but ``unverified[]`` holds a dated demand (a quote that did not
   verify on a skewed photo) → ``medium`` "I saw a date but could not confirm it" (D-12: unverified
   facts raise urgency up to ``medium``, never above; the type floor still applies);
8. nothing found → ``info`` (``no_action`` only when neither list holds anything, else
   ``no_date``);
9. ``verify_resource_id`` = ``uscis_contact`` (USCIS types) / ``eoir_hotline`` (EOIR types) when a
   date drives the banner (a verified one, or the unverified one of step 7).

Copy keys are PRODUCT_SPEC §5.5 ``urgency.*``. Pure function with an injected ``today``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from proxyhealth_api.analysis.i18n import Translator
from proxyhealth_api.contracts.analysis import Demand, RedFlag, Urgency
from proxyhealth_api.contracts.enums import (
    DateKind,
    DemandKind,
    DocumentCategory,
    DocumentType,
    RedFlagKind,
    Severity,
    UrgencyLevel,
)

DT = DocumentType
KEY_EMERGENCY = "urgency.emergency.headline"
KEY_CRITICAL_TODAY = "urgency.critical.date_today"
KEY_CRITICAL_SOON = "urgency.critical.date_soon"
KEY_DATE_PASSED = "urgency.critical.date_passed"
KEY_HIGH_SOON = "urgency.high.date_soon"
KEY_HIGH_FLOOR = "urgency.high.floor"
KEY_MEDIUM_SOON = "urgency.medium.date_soon"
KEY_MEDIUM_ESTIMATED = "urgency.medium.estimated"
KEY_INFO_LATER = "urgency.info.date_later"
KEY_INFO_NO_ACTION = "urgency.info.no_action"
KEY_INFO_NO_DATE = "urgency.info.no_date"
KEY_UNVERIFIED_DATE = "urgency.medium.unverified_date"
DATED_KINDS = frozenset({DemandKind.deadline, DemandKind.relative_deadline, DemandKind.appointment})

VERIFY_USCIS = "uscis_contact"  # _meta.yaml well_known_ids.verify_uscis_date
VERIFY_EOIR = "eoir_hotline"  # _meta.yaml well_known_ids.verify_court_date

ANY_DRIVING = frozenset(
    {"hearing_date", "appointment", "payment_due", "response_due", "expiry", "move_date"}
)
NEVER_DRIVING = frozenset({"notice_date", "decision_date", "other"})
USCIS_TYPES = frozenset(
    {
        DT.uscis_receipt, DT.uscis_rfe, DT.uscis_noid, DT.uscis_biometrics, DT.uscis_interview,
        DT.uscis_approval, DT.uscis_denial, DT.ead_related, DT.green_card_related,
        DT.tps_related, DT.asylum_fee_notice, DT.parole_related,
    }
)  # fmt: skip
EOIR_TYPES = frozenset({DT.nta, DT.hearing_notice, DT.ij_decision, DT.bia_notice})
FLOORS = frozenset(
    {DT.nta, DT.hearing_notice, DT.eviction_summons, DT.uscis_noid, DT.utility_shutoff,
     DT.pay_or_quit}
)  # fmt: skip
PAST_CRITICAL_CATEGORIES = frozenset({DocumentCategory.immigration, DocumentCategory.court})
# Court papers filed under another category (§5.2 row ``eviction_summons``: "critical (court)").
PAST_CRITICAL_TYPES = frozenset({DT.eviction_summons})
PAST_WINDOW_DAYS = 60

_R = frozenset[str]
DRIVING_ROLES: Mapping[DocumentType, _R] = {
    DT.uscis_receipt: _R({"expiry", "response_due"}),
    DT.uscis_rfe: _R({"response_due"}),
    DT.uscis_noid: _R({"response_due"}),
    DT.uscis_biometrics: _R({"appointment"}),
    DT.uscis_interview: _R({"appointment", "response_due"}),
    DT.uscis_approval: _R({"expiry", "response_due"}),
    DT.uscis_denial: _R({"response_due"}),
    DT.ead_related: _R({"expiry", "response_due"}),
    DT.green_card_related: _R({"expiry", "response_due"}),
    DT.tps_related: _R({"response_due", "expiry"}),
    DT.asylum_fee_notice: _R({"payment_due"}),
    DT.parole_related: _R({"expiry", "response_due"}),
    DT.ice_checkin: _R({"appointment"}),
    DT.nta: _R({"hearing_date"}),
    DT.hearing_notice: _R({"hearing_date"}),
    DT.ij_decision: _R({"response_due"}),
    DT.bia_notice: _R({"response_due"}),
    DT.traffic_court: _R({"hearing_date", "payment_due"}),
    DT.medical_bill: _R({"payment_due"}),
    DT.eob: _R({"response_due"}),
    DT.insurance_denial: _R({"response_due"}),
    DT.prior_auth: _R({"expiry", "response_due"}),
    DT.lab_result: _R({"appointment"}),
    DT.prescription_label: _R({"expiry"}),
    DT.discharge_instructions: _R({"appointment"}),
    DT.vaccine_record: _R({"response_due"}),
    DT.appointment_reminder: _R({"appointment"}),
    DT.medicaid_renewal: _R({"response_due", "appointment"}),
    DT.snap_notice: _R({"appointment", "response_due"}),
    DT.wic_notice: _R({"appointment", "response_due"}),
    DT.ssa_letter: _R({"response_due", "appointment"}),
    DT.pay_or_quit: _R({"response_due", "payment_due"}),
    DT.eviction_summons: _R({"hearing_date"}),
    DT.lease: _R({"move_date", "payment_due", "expiry"}),
    DT.rent_increase: _R({"move_date"}),
    DT.section8_recert: _R({"response_due", "appointment"}),
    DT.utility_shutoff: _R({"payment_due", "response_due"}),
    DT.school_enrollment: _R({"response_due", "appointment"}),
    DT.immunization_notice: _R({"response_due"}),
    DT.iep_504_notice: _R({"appointment", "response_due"}),
    DT.school_meals: _R({"response_due"}),
    DT.report_card: _R(),
    DT.w2_1099: _R(),
    DT.i9: _R({"response_due", "expiry"}),
    DT.offer_letter: _R({"response_due"}),
    DT.pay_stub: _R(),
    DT.irs_notice: _R({"response_due", "payment_due"}),
    DT.itin: _R({"response_due", "expiry"}),
    DT.jury_summons: _R({"response_due", "appointment"}),
    DT.other_notice: ANY_DRIVING,
    DT.unknown: _R(),
}
CRITICAL_SET: Mapping[DocumentType, _R] = {
    DT.uscis_biometrics: _R({"appointment"}),
    DT.uscis_interview: _R({"appointment"}),
    DT.asylum_fee_notice: _R({"payment_due"}),
    DT.ice_checkin: _R({"appointment"}),
    DT.nta: _R({"hearing_date"}),
    DT.hearing_notice: _R({"hearing_date"}),
    DT.traffic_court: _R({"hearing_date"}),
    DT.eviction_summons: _R({"hearing_date"}),
}
PAST_HIGH_ROLES = frozenset({"response_due", "payment_due", "appointment", "hearing_date"})

_ORDER = {
    UrgencyLevel.info: 0, UrgencyLevel.medium: 1, UrgencyLevel.high: 2,
    UrgencyLevel.critical: 3, UrgencyLevel.emergency: 4,
}  # fmt: skip


def level_rank(level: UrgencyLevel) -> int:
    """Severity order: info < medium < high < critical < emergency."""
    return _ORDER[level]


def verify_resource_for(document_type: DocumentType) -> str | None:
    """§5.2 verify CTA family: USCIS Contact Center, EOIR hotline, or ``None`` (printed phone)."""
    if document_type in USCIS_TYPES:
        return VERIFY_USCIS
    if document_type in EOIR_TYPES:
        return VERIFY_EOIR
    return None


def threshold_level(days_until: int, *, critical_allowed: bool) -> UrgencyLevel:
    """Future-date thresholds: ≤ 7 critical (critical set only) · ≤ 14 high · ≤ 30 medium."""
    if days_until <= 7 and critical_allowed:
        return UrgencyLevel.critical
    if days_until <= 14:
        return UrgencyLevel.high
    if days_until <= 30:
        return UrgencyLevel.medium
    return UrgencyLevel.info


def _future_headline(level: UrgencyLevel, days_until: int) -> str:
    if level is UrgencyLevel.critical:
        return KEY_CRITICAL_TODAY if days_until == 0 else KEY_CRITICAL_SOON
    return {
        UrgencyLevel.high: KEY_HIGH_SOON,
        UrgencyLevel.medium: KEY_MEDIUM_SOON,
    }.get(level, KEY_INFO_LATER)


def past_level(
    role: str | None, category: DocumentCategory, document_type: DocumentType | None = None
) -> UrgencyLevel:
    """§5.1 step 4: critical on immigration/court papers (category ``immigration``/``court``,
    or a court paper of another category such as ``eviction_summons``); else by the role."""
    if category in PAST_CRITICAL_CATEGORIES or document_type in PAST_CRITICAL_TYPES:
        return UrgencyLevel.critical
    return UrgencyLevel.high if role in PAST_HIGH_ROLES else UrgencyLevel.medium


@dataclass(frozen=True)
class _Candidate:
    demand: Demand
    when: date
    days_until: int


@dataclass
class UrgencyOutcome:
    """``compute_urgency`` result: the contract ``Urgency`` plus code-added red flags."""

    urgency: Urgency
    red_flags: list[RedFlag] = field(default_factory=list)


def _candidates(demands: Iterable[Demand], roles: frozenset[str], kind: DateKind, today: date
                ) -> list[_Candidate]:  # fmt: skip
    out: list[_Candidate] = []
    for d in demands:
        if not d.verified or d.date is None or d.date.kind is not kind or not d.date.value_iso:
            continue
        if d.role not in roles or d.role in NEVER_DRIVING:
            continue
        try:
            when = date.fromisoformat(d.date.value_iso)
        except ValueError:
            continue
        out.append(_Candidate(d, when, (when - today).days))
    return out


def _urgency(
    level: UrgencyLevel,
    headline_key: str,
    *,
    cand: _Candidate | None = None,
    params: dict[str, str] | None = None,
    past: bool = False,
    floor: bool = False,
    verify: str | None = None,
) -> Urgency:
    return Urgency(
        level=level, headline_key=headline_key, headline_params=params or {},
        driving_demand_id=cand.demand.id if cand else None,
        nearest_date_iso=cand.when.isoformat() if cand else None,
        days_until=cand.days_until if cand else None, past_date=past, floor_applied=floor,
        verify_resource_id=verify if cand else None,
    )  # fmt: skip


def _pick(cands: Sequence[_Candidate], level_of: dict[int, UrgencyLevel]) -> _Candidate:
    """Most severe level wins; ties go to the nearest date, then table order."""
    return max(
        cands,
        key=lambda c: (level_rank(level_of[id(c)]), -abs(c.days_until), -cands.index(c)),
    )


def compute_urgency(
    document_type: DocumentType,
    category: DocumentCategory,
    demands: Sequence[Demand],
    *,
    emergency: bool,
    today: date,
    t: Translator | None = None,
    unverified: Sequence[Demand] = (),
) -> UrgencyOutcome:
    """DOCUMENT_TAXONOMY §5.1 over the **verified** ``demands`` (any ``verified=False`` item there
    is ignored). ``unverified`` is ``AnalysisResult.unverified``: a dated item there never drives
    a date, but lifts a dateless result to ``medium`` with its own headline (step 7) and keeps the
    banner from saying "Nothing to do right now". ``t`` renders the ``expired_date`` red flag
    text; without it the key is used as text."""
    if emergency:
        return UrgencyOutcome(_urgency(UrgencyLevel.emergency, KEY_EMERGENCY))
    roles = DRIVING_ROLES.get(document_type, ANY_DRIVING)
    critical_roles = CRITICAL_SET.get(document_type, frozenset())
    verify = verify_resource_for(document_type)
    stated = _candidates(demands, roles, DateKind.stated, today)
    future = [c for c in stated if c.days_until >= 0]
    past = [c for c in stated if -PAST_WINDOW_DAYS <= c.days_until < 0]
    flags: list[RedFlag] = []
    result: Urgency | None = None
    if future:
        levels = {
            id(c): threshold_level(c.days_until, critical_allowed=c.demand.role in critical_roles)
            for c in future
        }
        cand = _pick(future, levels)
        level = levels[id(cand)]
        params = {"date": cand.demand.value_verbatim, "date_iso": cand.when.isoformat()}
        headline = _future_headline(level, cand.days_until)
        result = _urgency(level, headline, cand=cand, params=params, verify=verify)
    elif past:
        levels = {id(c): past_level(c.demand.role, category, document_type) for c in past}
        cand = _pick(past, levels)
        params = {"date": cand.demand.value_verbatim, "date_iso": cand.when.isoformat()}
        result = _urgency(
            levels[id(cand)], KEY_DATE_PASSED, cand=cand, params=params, past=True, verify=verify
        )
        text = t(KEY_DATE_PASSED, date=cand.demand.value_verbatim) if t else KEY_DATE_PASSED
        flags.append(
            RedFlag(
                kind=RedFlagKind.expired_date, text=text, source_quote=cand.demand.source_quote,
                span_ids=list(cand.demand.span_ids), page=cand.demand.page,
                severity=Severity.medium, fixed_copy_key=None, verified=True,
            )  # fmt: skip
        )
    else:
        estimated = [
            c for c in _candidates(demands, roles, DateKind.estimated, today) if c.days_until >= 0
        ]
        if estimated:
            levels = {
                id(c): min(
                    threshold_level(c.days_until, critical_allowed=False),
                    UrgencyLevel.medium,
                    key=level_rank,
                )
                for c in estimated
            }
            cand = _pick(estimated, levels)
            iso = cand.when.isoformat()
            # ``date == date_iso`` (both ISO) is the client's signal that the banner date is an
            # estimate it writes out in the reader's language (features/analysis/estimatedDate.ts).
            result = _urgency(
                levels[id(cand)], KEY_MEDIUM_ESTIMATED, cand=cand,
                params={"date": iso, "date_iso": iso}, verify=verify,
            )  # fmt: skip
    if result is None and any(
        d.kind in DATED_KINDS and d.role not in NEVER_DRIVING for d in unverified
    ):
        result = _urgency(UrgencyLevel.medium, KEY_UNVERIFIED_DATE).model_copy(
            update={"verify_resource_id": verify}
        )
    if result is None:
        headline = KEY_INFO_NO_ACTION if not demands and not unverified else KEY_INFO_NO_DATE
        result = _urgency(UrgencyLevel.info, headline)
    if document_type in FLOORS and level_rank(result.level) < level_rank(UrgencyLevel.high):
        update: dict[str, object] = {"level": UrgencyLevel.high, "floor_applied": True}
        if result.driving_demand_id is None and result.headline_key != KEY_UNVERIFIED_DATE:
            update["headline_key"] = KEY_HIGH_FLOOR
            update["headline_params"] = {}
        result = result.model_copy(update=update)
    return UrgencyOutcome(result, flags)


__all__ = [
    "ANY_DRIVING",
    "CRITICAL_SET",
    "DATED_KINDS",
    "DRIVING_ROLES",
    "EOIR_TYPES",
    "FLOORS",
    "KEY_UNVERIFIED_DATE",
    "NEVER_DRIVING",
    "PAST_CRITICAL_TYPES",
    "PAST_WINDOW_DAYS",
    "USCIS_TYPES",
    "VERIFY_EOIR",
    "VERIFY_USCIS",
    "UrgencyOutcome",
    "compute_urgency",
    "level_rank",
    "past_level",
    "threshold_level",
    "verify_resource_for",
]
