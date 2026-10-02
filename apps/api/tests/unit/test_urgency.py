"""WP2 — ``analysis/urgency.py`` (D-12; DOCUMENT_TAXONOMY §5.1–§5.2)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
import yaml

from proxyhealth_api.analysis import urgency as u
from proxyhealth_api.contracts.analysis import DateInfo, Demand
from proxyhealth_api.contracts.enums import (
    Confidence,
    DateKind,
    DemandKind,
    DocumentCategory,
    DocumentType,
    RedFlagKind,
    UrgencyLevel,
)
from proxyhealth_api.settings import DATA_DIR
from tests.unit._fixtures_wp2 import en_t

TODAY = date(2026, 9, 24)
DT = DocumentType
CAT = DocumentCategory


def dated(
    days: int | None,
    role: str,
    *,
    kind: DateKind = DateKind.stated,
    demand_id: str = "d1",
    verified: bool = True,
    value: str = "the printed date",
) -> Demand:
    iso = (TODAY + timedelta(days=days)).isoformat() if days is not None else None
    info = DateInfo(
        value_iso=iso, time_text=None, kind=kind, formula=None, anchor_quote=None,
        anchor_demand_id=None, rule_id=None, rule_source_url=None, rule_verification=None,
        localized_line=None,
    )  # fmt: skip
    return Demand(
        id=demand_id, kind=DemandKind.deadline, text="x", value_verbatim=value,
        source_quote=f"by {value}", span_ids=["p1b1"], page=1, confidence=Confidence.high,
        verified=verified, verification_note=None, date=info, amount=None, documents=[],
        role=role, reminder_eligible=verified, ambiguity_note=None,
    )  # fmt: skip


def run(doc: DocumentType, cat: DocumentCategory, *demands: Demand, emergency: bool = False
        ) -> u.UrgencyOutcome:  # fmt: skip
    return u.compute_urgency(doc, cat, list(demands), emergency=emergency, today=TODAY, t=en_t())


def test_emergency_wins_over_everything() -> None:
    out = run(DT.nta, CAT.court, dated(1, "hearing_date"), emergency=True)
    assert out.urgency.level is UrgencyLevel.emergency
    assert out.urgency.headline_key == "urgency.emergency.headline"
    assert out.urgency.nearest_date_iso is None and out.urgency.verify_resource_id is None


@pytest.mark.parametrize(
    ("days", "level", "headline"),
    [
        (0, UrgencyLevel.critical, "urgency.critical.date_today"),
        (7, UrgencyLevel.critical, "urgency.critical.date_soon"),
        (8, UrgencyLevel.high, "urgency.high.date_soon"),
        (14, UrgencyLevel.high, "urgency.high.date_soon"),
    ],
)
def test_critical_set_thresholds_on_a_hearing(
    days: int, level: UrgencyLevel, headline: str
) -> None:
    out = run(DT.nta, CAT.court, dated(days, "hearing_date", value="October 1, 2026"))
    assert out.urgency.level is level and out.urgency.headline_key == headline
    assert out.urgency.headline_params["date"] == "October 1, 2026"
    assert out.urgency.days_until == days and out.urgency.verify_resource_id == "eoir_hotline"
    assert out.urgency.driving_demand_id == "d1" and out.urgency.past_date is False


@pytest.mark.parametrize(
    ("days", "level"),
    [(3, UrgencyLevel.high), (14, UrgencyLevel.high), (15, UrgencyLevel.medium),
     (30, UrgencyLevel.medium), (31, UrgencyLevel.info)],
)  # fmt: skip
def test_non_critical_roles_never_reach_critical(days: int, level: UrgencyLevel) -> None:
    out = run(DT.medicaid_renewal, CAT.benefits, dated(days, "response_due"))
    assert out.urgency.level is level
    assert out.urgency.verify_resource_id is None


def test_medicaid_fixture_expectation() -> None:
    """``medicaid_address_confirmation``: stated 2026-10-14, frozen today 2026-10-02 → high."""
    d = dated(20, "response_due")  # 2026-10-14 relative to TODAY
    out = u.compute_urgency(
        DT.medicaid_renewal, CAT.benefits, [d], emergency=False, today=date(2026, 10, 2)
    )
    assert out.urgency.level is UrgencyLevel.high and out.urgency.nearest_date_iso == "2026-10-14"


def test_asylum_fee_payment_is_in_the_critical_set() -> None:
    out = run(DT.asylum_fee_notice, CAT.immigration, dated(5, "payment_due"))
    assert out.urgency.level is UrgencyLevel.critical
    assert out.urgency.verify_resource_id == "uscis_contact"


def test_anchor_roles_never_drive() -> None:
    out = run(DT.insurance_denial, CAT.medical, dated(2, "notice_date"), dated(3, "other"))
    assert out.urgency.level is UrgencyLevel.info
    assert out.urgency.headline_key == "urgency.info.no_date"
    assert out.urgency.driving_demand_id is None


def test_most_severe_candidate_wins() -> None:
    out = run(
        DT.uscis_interview, CAT.immigration,
        dated(3, "response_due", demand_id="evidence"), dated(6, "appointment", demand_id="appt"),
    )  # fmt: skip
    assert out.urgency.level is UrgencyLevel.critical and out.urgency.driving_demand_id == "appt"


def test_unverified_facts_never_raise_urgency() -> None:
    out = run(DT.medical_bill, CAT.medical, dated(2, "payment_due", verified=False))
    assert out.urgency.level is UrgencyLevel.info


def test_past_date_on_court_paper_is_critical_with_red_flag() -> None:
    out = run(DT.hearing_notice, CAT.court, dated(-5, "hearing_date", value="September 19, 2026"))
    assert out.urgency.level is UrgencyLevel.critical and out.urgency.past_date is True
    assert out.urgency.headline_key == "urgency.critical.date_passed"
    assert out.urgency.days_until == -5
    [flag] = out.red_flags
    assert flag.kind is RedFlagKind.expired_date and flag.verified and flag.fixed_copy_key is None
    assert "September 19, 2026" in flag.text


def test_past_eviction_court_date_is_critical_although_category_is_housing() -> None:
    out = run(DT.eviction_summons, CAT.housing, dated(-4, "hearing_date"))
    assert out.urgency.level is UrgencyLevel.critical and out.urgency.past_date is True
    assert u.past_level("hearing_date", CAT.housing, DT.eviction_summons) is UrgencyLevel.critical
    assert u.past_level("response_due", CAT.housing, DT.pay_or_quit) is UrgencyLevel.high


@pytest.mark.parametrize(
    ("role", "level"),
    [("payment_due", UrgencyLevel.high), ("appointment", UrgencyLevel.high),
     ("expiry", UrgencyLevel.medium)],
)  # fmt: skip
def test_past_date_elsewhere_by_role(role: str, level: UrgencyLevel) -> None:
    doc = DT.medical_bill if role == "payment_due" else DT.prior_auth
    if role == "appointment":
        doc = DT.appointment_reminder
    out = run(doc, CAT.medical, dated(-10, role))
    assert out.urgency.level is level and out.urgency.past_date


def test_dates_more_than_60_days_past_are_ignored() -> None:
    out = run(DT.medical_bill, CAT.medical, dated(-61, "payment_due"))
    assert out.urgency.level is UrgencyLevel.info and out.red_flags == []


def test_future_beats_past() -> None:
    out = run(
        DT.medical_bill, CAT.medical, dated(-3, "payment_due", demand_id="old"),
        dated(40, "payment_due", demand_id="new"),
    )  # fmt: skip
    assert out.urgency.driving_demand_id == "new" and out.urgency.past_date is False


def test_estimated_dates_are_capped_at_medium() -> None:
    out = run(DT.insurance_denial, CAT.medical, dated(3, "response_due", kind=DateKind.estimated))
    assert out.urgency.level is UrgencyLevel.medium
    assert out.urgency.headline_key == "urgency.medium.estimated"
    # ``date == date_iso`` (ISO) marks the estimate; the client writes it out in the reader's
    # language (features/analysis/estimatedDate.ts ``localizeUrgencyDate``).
    iso = (TODAY + timedelta(days=3)).isoformat()
    assert out.urgency.headline_params == {"date": iso, "date_iso": iso}


def test_estimated_headline_keeps_iso_even_with_a_readable_estimate_line() -> None:
    d = dated(20, "response_due", kind=DateKind.estimated)
    assert d.date is not None
    d = d.model_copy(update={"date": d.date.model_copy(update={"localized_line": "10/14/2026"})})
    out = run(DT.insurance_denial, CAT.medical, d)
    assert out.urgency.headline_params == {"date": "2026-10-14", "date_iso": "2026-10-14"}


@pytest.mark.parametrize("doc", sorted(u.FLOORS))
def test_floors_without_dates(doc: DocumentType) -> None:
    out = run(doc, CAT.court)
    assert out.urgency.level is UrgencyLevel.high and out.urgency.floor_applied
    assert out.urgency.headline_key == "urgency.high.floor"
    assert out.urgency.verify_resource_id is None


def test_pay_or_quit_is_high_even_with_a_far_date() -> None:
    out = run(DT.pay_or_quit, CAT.housing, dated(40, "response_due"))
    assert out.urgency.level is UrgencyLevel.high and out.urgency.floor_applied
    assert out.urgency.headline_key == "urgency.info.date_later"  # the date headline stays


def test_nothing_found() -> None:
    assert run(DT.w2_1099, CAT.employment).urgency.headline_key == "urgency.info.no_action"
    no_date = dated(None, "response_due")
    assert run(DT.w2_1099, CAT.employment, no_date).urgency.headline_key == "urgency.info.no_date"


def test_floors_mirror_resource_db_urgent_doc_boost() -> None:
    """TAXONOMY §5.2: ``_meta.yaml.urgent_doc_boost`` = floors + asylum fee + ICE check-in."""
    meta = yaml.safe_load((DATA_DIR / "resources" / "_meta.yaml").read_text(encoding="utf-8"))
    boosted = {DocumentType(k) for k in meta["urgent_doc_boost"]}
    assert boosted == set(u.FLOORS) | {DT.asylum_fee_notice, DT.ice_checkin}


def test_every_document_type_has_driving_roles() -> None:
    assert set(u.DRIVING_ROLES) == set(DocumentType)
    for roles in u.DRIVING_ROLES.values():
        assert not roles & u.NEVER_DRIVING


# --- Phase 2B: unverified dated facts (D-12 "up to medium") ------------------------------------


def _unverified(days: int | None, role: str = "response_due") -> Demand:
    d = dated(days, role, verified=False, demand_id="u1")
    return d.model_copy(update={"date": None, "reminder_eligible": False})


def test_unverified_date_lifts_a_dateless_result_to_medium_never_no_action() -> None:
    """Every quote failed on a skewed photo: the banner must not say "Nothing to do right now"."""
    out = u.compute_urgency(
        DT.uscis_rfe, CAT.immigration, [], emergency=False, today=TODAY, t=en_t(),
        unverified=[_unverified(None)],
    )  # fmt: skip
    urg = out.urgency
    assert urg.level is UrgencyLevel.medium and urg.headline_key == u.KEY_UNVERIFIED_DATE
    assert urg.headline_key != u.KEY_INFO_NO_ACTION and urg.driving_demand_id is None
    assert urg.verify_resource_id == u.VERIFY_USCIS, "the verify CTA still helps"


def test_unverified_date_keeps_its_headline_under_a_floor() -> None:
    out = u.compute_urgency(
        DT.nta, CAT.court, [], emergency=False, today=TODAY,
        unverified=[_unverified(None, "hearing_date")],
    )  # fmt: skip
    assert out.urgency.level is UrgencyLevel.high and out.urgency.floor_applied
    assert out.urgency.headline_key == u.KEY_UNVERIFIED_DATE


def test_unverified_never_beats_a_verified_date_and_anchor_roles_do_not_count() -> None:
    out = u.compute_urgency(
        DT.medical_bill, CAT.medical, [dated(45, "payment_due")], emergency=False, today=TODAY,
        unverified=[_unverified(None, "payment_due")],
    )  # fmt: skip
    assert out.urgency.level is UrgencyLevel.info and out.urgency.headline_key == u.KEY_INFO_LATER
    notice_only = u.compute_urgency(
        DT.medical_bill, CAT.medical, [], emergency=False, today=TODAY,
        unverified=[_unverified(None, "notice_date")],
    )  # fmt: skip
    assert notice_only.urgency.headline_key == u.KEY_INFO_NO_DATE, "something was on the page"
