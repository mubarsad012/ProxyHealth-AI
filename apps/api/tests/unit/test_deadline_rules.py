"""WP2 — ``analysis/deadline_rules.py`` + ``data/rules/deadlines.yaml`` (D-11; §5.3)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from proxyhealth_api.analysis import deadline_rules as dr
from proxyhealth_api.analysis.demand_repair import R4_REANCHORED, repair_demands
from proxyhealth_api.analysis.transcript import Transcript, assemble_transcript
from proxyhealth_api.analysis.verify import VerifiedDemands, verify_demands
from proxyhealth_api.contracts.analysis import Demand
from proxyhealth_api.contracts.enums import (
    Confidence,
    DateFormat,
    DateKind,
    DemandKind,
    DigitSystem,
    DocumentCategory,
    DocumentType,
    RuleVerification,
)
from proxyhealth_api.contracts.model_out import DemandOut
from proxyhealth_api.contracts.rules import DeadlineRule
from proxyhealth_api.resources.rules_repo import load_deadlines
from proxyhealth_api.settings import DATA_DIR
from tests.unit._fixtures_wp2 import block, demand_out, en_t

RULES_PATH = DATA_DIR / "rules" / "deadlines.yaml"
D11_IDS = {
    "bia_appeal_30d", "ar11_10d", "eoir33_5bd", "aca_internal_appeal_180d",
    "aca_external_review_4mo", "medicare_advantage_65d", "medicaid_fair_hearing_90d_max",
    "asylum_annual_fee_30d", "in_absentia_rescission_180d", "eeoc_180_300d",
    "osha_retaliation_30d", "gfe_dispute_120d",
}  # fmt: skip
# API_CONTRACT §3.10 — the two entries BUILD_PLAN §5.3 requires verbatim.
CONTRACT_EXAMPLE = json.loads(
    '[{"id": "ar11_10d", "label_en": "Report a move to USCIS within 10 days", '
    '"applies_to_doc_types": ["uscis_receipt", "uscis_rfe", "uscis_biometrics", '
    '"uscis_interview", "uscis_approval", "ead_related", "green_card_related", "tps_related"], '
    '"pattern": "within (10|ten) days of (moving|your move|the move)", "days": 10, '
    '"count_basis": "calendar", "anchor_role": "move_date", "receipt_based": false, '
    '"mail_days": 0, "source_url": "https://www.uscis.gov/addresschange", '
    '"source_verified_on": "2026-09-23", "verification": "verified", "valid_until": null, '
    '"notes_en": "USPS forwarding does not update USCIS."}, '
    '{"id": "bia_appeal_30d", "label_en": "Appeal to the BIA within 30 calendar days (must be '
    'received)", "applies_to_doc_types": ["ij_decision"], "pattern": "(within|no later than) '
    '(30|thirty) (calendar )?days", "days": 30, "count_basis": "calendar", "anchor_role": '
    '"decision_date", "receipt_based": true, "mail_days": 0, "source_url": '
    '"https://www.justice.gov/eoir/policy-manual-eoir/part-III/bia/chapter-3-5", '
    '"source_verified_on": "2026-09-23", "verification": "likely", "valid_until": "2027-03-31", '
    '"notes_en": "Treat as likely until the page is re-fetched; the Board cannot extend this '
    'deadline."}]'
)
TODAY = date(2026, 9, 24)


@pytest.fixture(scope="module")
def rules() -> list[DeadlineRule]:
    loaded, version = load_deadlines(RULES_PATH)
    assert version != "0"
    return loaded


# --- the seeded table ----------------------------------------------------------------------------


def test_table_has_exactly_the_twelve_d11_rules(rules: list[DeadlineRule]) -> None:
    assert {r.id for r in rules} == D11_IDS
    assert len(rules) == 12
    assert dr.validate_rules(rules) == []
    for r in rules:
        assert r.source_url.startswith("https://")
        assert not any(t in dr.NEVER_ESTIMATE_TYPES for t in r.applies_to_doc_types), r.id
    assert all("evict" not in r.id and "quit" not in r.id for r in rules)


def test_contract_entries_are_verbatim(rules: list[DeadlineRule]) -> None:
    by_id = {r.id: r.model_dump(mode="json") for r in rules}
    for entry in CONTRACT_EXAMPLE:
        assert by_id[entry["id"]] == entry


def test_likely_rules_carry_valid_until(rules: list[DeadlineRule]) -> None:
    for r in rules:
        if r.verification is RuleVerification.likely:
            assert r.valid_until is not None, r.id


# --- deterministic parsing -----------------------------------------------------------------------

OCT14 = date(2026, 10, 14)


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("October 14, 2026", None), ("Oct. 14, 2026", None), ("Monday, October 14th, 2026", None),
        ("14 October 2026", None), ("10/14/2026", None), ("10-14-26", None), ("2026-10-14", None),
        ("14 de octubre de 2026", "es"), ("14 octobre 2026", "fr"),
        ("14 de outubro de 2026", "pt-BR"),
        ("Oktubre 14, 2026", "tl"), ("14 oktòb 2026", "ht"), ("14 октября 2026", "ru"),
        ("14 жовтня 2026", "uk"), ("١٤ أكتوبر ٢٠٢٦", "ar"), ("۱۴ اکتبر ۲۰۲۶", "fa"),
        ("۱۴ اکتوبر ۲۰۲۶", "prs"), ("14 اکتوبر 2026", "ps"), ("14 اکتوبر 2026", "ur"),
        ("14 अक्टूबर 2026", "hi"), ("14 अक्टोबर 2026", "ne"), ("14 ਅਕਤੂਬਰ 2026", "pa"),
        ("১৪ অক্টোবর ২০২৬", "bn"), ("14 Oktoobar 2026", "so"), ("14 Oktoba 2026", "sw"),
        ("14 Ukwakira 2026", "rw"), ("ኦክቶበር 14, 2026", "am"), ("၁၄ အောက်တိုဘာ ၂၀၂၆", "my"),
        ("ngày 14 tháng 10 năm 2026", "vi"), ("2026年10月14日", "zh-Hans"),
        ("2026年10月14日", "zh-Hant"), ("2026년 10월 14일", "ko"),
    ],
)  # fmt: skip
def test_every_bundled_language_parses(text: str, language: str | None) -> None:
    assert dr.parse_dates(text, language=language).single == OCT14


def test_every_bundled_language_has_a_month_table() -> None:
    bundled = {
        "en", "es", "zh-Hans", "zh-Hant", "vi", "tl", "ar", "ht", "pt-BR", "ru", "uk", "ko", "fr",
        "prs", "ps", "fa", "ur", "hi", "pa", "bn", "so", "sw", "am", "my", "ne", "rw",
    }  # fmt: skip
    assert bundled <= dr.MONTH_LANGUAGES


def test_cross_language_token_needs_the_language() -> None:
    assert dr.parse_dates("14 out 2026").single is None  # pt "out" = Oct, ht "out" = Aug
    assert dr.parse_dates("14 out 2026", language="pt-BR").single == OCT14
    assert dr.parse_dates("14 out 2026", language="ht").single == date(2026, 8, 14)


def test_ambiguous_numeric_and_how_it_resolves() -> None:
    p = dr.parse_dates("03/04/2026")
    assert p.single is None and p.ambiguous_numeric
    assert dr.parse_dates("03/04/2026", default_order=DateFormat.mdy).single == date(2026, 3, 4)
    assert dr.parse_dates("03/04/2026", default_order=DateFormat.dmy).single == date(2026, 4, 3)
    assert dr.parse_dates("05/05/2026").single == date(2026, 5, 5)
    cue = dr.numeric_order_cue("Printed 10/14/2026. Pay by 03/04/2027.")
    assert cue is DateFormat.mdy
    assert dr.parse_dates("03/04/2027", order_cue=cue).single == date(2027, 3, 4)
    assert dr.numeric_order_cue("no dates here") is None


def test_more_than_one_date_is_not_a_single_date() -> None:
    assert dr.parse_dates("October 14 or October 21, 2026").single is None
    assert dr.parse_dates("From 10/01/2026 to 10/14/2026").single is None
    assert dr.parse_dates("February 30, 2026").single is None
    assert dr.parse_dates("within 30 days").dates == ()
    assert dr.parse_dates(None).dates == ()


# --- holidays, business days, zones, digits ------------------------------------------------------


def test_federal_holidays_2026() -> None:
    assert sorted(dr.federal_holidays(2026)) == [
        date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 5, 25),
        date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 10, 12),
        date(2026, 11, 11), date(2026, 11, 26), date(2026, 12, 25),
    ]  # fmt: skip
    assert date(2027, 12, 31) in dr.federal_holidays(2027)  # New Year 2028 is a Saturday


def test_business_days_skip_weekends_and_holidays() -> None:
    assert dr.add_business_days(date(2026, 11, 24), 5) == date(2026, 12, 2)  # Thanksgiving
    assert dr.add_business_days(date(2026, 10, 9), 1) == date(2026, 10, 13)  # Columbus Day
    assert not dr.is_business_day(date(2026, 10, 10))


def test_local_today_uses_the_state_zone() -> None:
    now = datetime(2026, 9, 25, 3, 30, tzinfo=UTC)
    assert dr.local_today(now, "CA") == date(2026, 9, 24)
    assert dr.local_today(now, "VA") == date(2026, 9, 24)
    assert dr.local_today(now, None) == date(2026, 9, 24)
    assert dr.local_today(datetime(2026, 9, 25, 12, 0, tzinfo=UTC), "HI") == date(2026, 9, 25)


def test_localize_digits() -> None:
    assert dr.localize_digits("2026-10-14", DigitSystem.persian) == "۲۰۲۶-۱۰-۱۴"
    assert dr.localize_digits("2026-10-14", DigitSystem.eastern_arabic) == "٢٠٢٦-١٠-١٤"
    assert dr.localize_digits("2026", DigitSystem.western) == "2026"


# --- applying the rules to verified demands ------------------------------------------------------


def _denial_paper() -> Transcript:
    return assemble_transcript(
        [
            block("p1b1", "Date of notice: September 1, 2026"),
            block("p1b2", "You may ask for an internal appeal within 180 days of this notice."),
            block("p1b3", "Please call us by 10/14/2026 at 2:00 PM."),
        ],
        pages_received=1,
    )


def _denial_demands(t: Transcript, *, anchor_role: str = "notice_date") -> VerifiedDemands:
    notice = demand_out(
        "d1", kind=DemandKind.deadline, value_verbatim="September 1, 2026",
        source_quote="Date of notice: September 1, 2026", span_ids=["p1b1"],
        date_text="September 1, 2026", role=anchor_role,
    )  # fmt: skip
    appeal = demand_out(
        "d2", kind=DemandKind.relative_deadline, value_verbatim="within 180 days",
        source_quote="internal appeal within 180 days of this notice", span_ids=["p1b2"],
        relative_rule_text="within 180 days of this notice", anchor_span_id="p1b1",
        role="response_due",
    )  # fmt: skip
    call = demand_out(
        "d3", kind=DemandKind.appointment, value_verbatim="10/14/2026",
        source_quote="Please call us by 10/14/2026 at 2:00 PM.", span_ids=["p1b3"],
        date_text="10/14/2026", time_text="2:00 PM", role="response_due",
    )  # fmt: skip
    return verify_demands([notice, appeal, call], t)


def _ctx(rules: list[DeadlineRule], doc: DocumentType, today: date = TODAY) -> dr.DeadlineContext:
    return dr.DeadlineContext(document_type=doc, rules=rules, today=today, t=en_t())


def _apply(
    v: VerifiedDemands,
    rules: list[DeadlineRule],
    doc: DocumentType,
    t: Transcript,
    *,
    only: list[Demand] | None = None,
) -> list[Demand]:
    demands = v.verified if only is None else only
    return dr.apply_deadline_rules(demands, v.sources, _ctx(rules, doc), t)


def test_stated_and_estimated_dates(rules: list[DeadlineRule]) -> None:
    t = _denial_paper()
    v = _denial_demands(t)
    out = _apply(v, rules, DocumentType.insurance_denial, t)
    notice, appeal, call = out
    assert notice.date is not None and notice.date.kind is DateKind.stated
    assert notice.date.value_iso == "2026-09-01" and notice.reminder_eligible
    assert call.date is not None and call.date.value_iso == "2026-10-14"
    assert call.date.time_text == "2:00 PM" and call.reminder_eligible
    assert appeal.date is not None and appeal.date.kind is DateKind.estimated
    assert appeal.date.value_iso == "2027-02-28"
    assert appeal.date.rule_id == "aca_internal_appeal_180d"
    assert appeal.date.rule_verification is RuleVerification.verified
    assert appeal.date.rule_source_url and appeal.date.rule_source_url.startswith("https://")
    assert appeal.date.anchor_demand_id == "d1"
    assert appeal.date.anchor_quote == "Date of notice: September 1, 2026"
    assert appeal.date.formula == "September 1, 2026 + 180 calendar days"
    assert appeal.reminder_eligible is False


def test_anchor_must_have_the_rule_role(rules: list[DeadlineRule]) -> None:
    t = _denial_paper()
    v = _denial_demands(t, anchor_role="other")
    out = _apply(v, rules, DocumentType.insurance_denial, t)
    assert out[1].date is not None and out[1].date.kind is DateKind.unresolved
    assert out[1].date.value_iso is None


def test_unverified_anchor_cannot_stand_in(rules: list[DeadlineRule]) -> None:
    t = _denial_paper()
    v = _denial_demands(t)
    only_appeal = [d for d in v.verified if d.id != "d1"]
    out = _apply(v, rules, DocumentType.insurance_denial, t, only=only_appeal)
    assert out[0].date is not None and out[0].date.kind is DateKind.unresolved


def test_rule_must_apply_to_the_document_type(rules: list[DeadlineRule]) -> None:
    t = _denial_paper()
    v = _denial_demands(t)
    out = _apply(v, rules, DocumentType.lab_result, t)
    assert out[1].date is not None and out[1].date.kind is DateKind.unresolved
    assert out[0].date is not None and out[0].date.kind is DateKind.stated  # printed still wins


def test_expired_rule_is_not_used(rules: list[DeadlineRule]) -> None:
    t = assemble_transcript(
        [block("p1b1", "Decision date: March 1, 2027"),
         block("p1b2", "An appeal must be received within 30 calendar days.")],
        pages_received=1,
    )  # fmt: skip
    decision = demand_out(
        "d1", value_verbatim="March 1, 2027", source_quote="Decision date: March 1, 2027",
        span_ids=["p1b1"], date_text="March 1, 2027", role="decision_date",
    )  # fmt: skip
    appeal = demand_out(
        "d2", kind=DemandKind.relative_deadline, value_verbatim="within 30 calendar days",
        source_quote="received within 30 calendar days", span_ids=["p1b2"],
        relative_rule_text="within 30 calendar days", anchor_span_id="p1b1", role="response_due",
    )  # fmt: skip
    v = verify_demands([decision, appeal], t)
    live = dr.apply_deadline_rules(
        v.verified, v.sources, _ctx(rules, DocumentType.ij_decision, date(2027, 3, 2)), t
    )
    assert live[1].date is not None and live[1].date.kind is DateKind.estimated
    assert live[1].date.rule_id == "bia_appeal_30d"
    assert live[1].date.rule_verification is RuleVerification.likely
    assert live[1].date.formula is not None and "must be received" in live[1].date.formula
    expired = dr.apply_deadline_rules(
        v.verified, v.sources, _ctx(rules, DocumentType.ij_decision, date(2027, 4, 1)), t
    )
    assert expired[1].date is not None and expired[1].date.kind is DateKind.unresolved


def test_printed_date_beats_a_rule(rules: list[DeadlineRule]) -> None:
    t = _denial_paper()
    both = demand_out(
        "d9", kind=DemandKind.relative_deadline, value_verbatim="10/14/2026",
        source_quote="Please call us by 10/14/2026", span_ids=["p1b3"], date_text="10/14/2026",
        relative_rule_text="within 180 days", anchor_span_id="p1b1",
    )  # fmt: skip
    v = verify_demands([both], t)
    out = _apply(v, rules, DocumentType.insurance_denial, t)
    assert out[0].date is not None and out[0].date.kind is DateKind.stated
    assert out[0].date.value_iso == "2026-10-14"


def test_eviction_papers_never_get_an_estimate() -> None:
    fake = DeadlineRule(
        id="fake_evict", label_en="x", applies_to_doc_types=[DocumentType.eviction_summons],
        pattern="within (14|fourteen) days", days=14, count_basis="calendar",
        anchor_role="notice_date", receipt_based=False, mail_days=0,
        source_url="https://example.invalid", source_verified_on=date(2026, 9, 1),
        verification=RuleVerification.verified, valid_until=None, notes_en=None,
    )  # fmt: skip
    assert not dr.rule_applies(fake, DocumentType.eviction_summons, TODAY)
    assert dr.find_rule("within 14 days", DocumentType.eviction_summons, [fake], TODAY) is None


def test_ambiguous_printed_date_is_low_confidence_with_note(rules: list[DeadlineRule]) -> None:
    t = assemble_transcript([block("p1b1", "Return this by 03/04/2027.")], pages_received=1)
    d = demand_out(
        "d1", value_verbatim="03/04/2027", source_quote="Return this by 03/04/2027.",
        span_ids=["p1b1"], date_text="03/04/2027", role="response_due",
    )  # fmt: skip
    v = verify_demands([d], t)
    out = _apply(v, rules, DocumentType.other_notice, t)
    assert out[0].date is not None and out[0].date.kind is DateKind.stated
    assert out[0].date.value_iso is None and out[0].confidence is Confidence.low
    assert out[0].ambiguity_note and "03/04" in out[0].ambiguity_note
    assert out[0].reminder_eligible is False
    mdy = dr.DeadlineContext(
        document_type=DocumentType.other_notice, rules=rules, today=TODAY,
        default_order=DateFormat.mdy,
    )  # fmt: skip
    resolved = dr.apply_deadline_rules(v.verified, v.sources, mdy, t)[0]
    assert resolved.date is not None and resolved.date.value_iso == "2027-03-04"


def test_year_less_printed_date_is_stated_null_and_low(rules: list[DeadlineRule]) -> None:
    t = assemble_transcript([block("p1b1", "Come in on Monday, October 14.")], pages_received=1)
    d = demand_out(
        "d1", kind=DemandKind.appointment, value_verbatim="Monday, October 14",
        source_quote="Come in on Monday, October 14.", span_ids=["p1b1"],
        date_text="Monday, October 14", role="appointment", confidence=Confidence.high,
    )  # fmt: skip
    v = verify_demands([d], t)
    out = _apply(v, rules, DocumentType.other_notice, t)
    assert out[0].date is not None and out[0].date.kind is DateKind.stated
    assert out[0].date.value_iso is None and out[0].confidence is Confidence.low
    assert out[0].reminder_eligible is False


def test_model_date_text_not_in_the_quote_falls_back_to_the_value(
    rules: list[DeadlineRule],
) -> None:
    t = assemble_transcript(
        [block("p1b1", "Please respond by October 14, 2026.")], pages_received=1
    )
    d = demand_out(
        "d1", value_verbatim="October 14, 2026", source_quote="respond by October 14, 2026",
        span_ids=["p1b1"], date_text="2026-10-15", role="response_due",
    )  # fmt: skip
    v = verify_demands([d], t)
    out = _apply(v, rules, DocumentType.other_notice, t)
    assert out[0].date is not None and out[0].date.value_iso == "2026-10-14"


def test_non_date_kinds_are_untouched(rules: list[DeadlineRule]) -> None:
    t = assemble_transcript([block("p1b1", "Amount due: $45.10")], pages_received=1)
    d = demand_out(
        "d1", kind=DemandKind.amount, value_verbatim="$45.10", source_quote="Amount due: $45.10",
        span_ids=["p1b1"], amount_text="$45.10",
    )  # fmt: skip
    v = verify_demands([d], t)
    out = _apply(v, rules, DocumentType.medical_bill, t)
    assert out[0].date is None and out[0].reminder_eligible is False


def test_business_day_rule_and_localized_line(rules: list[DeadlineRule]) -> None:
    rule = next(r for r in rules if r.id == "eoir33_5bd")
    assert dr.compute_estimate(date(2026, 11, 24), rule) == date(2026, 12, 2)
    assert dr.rule_formula(rule, "November 24, 2026") == "November 24, 2026 + 5 business days"
    ctx = dr.context_for(
        document_type=DocumentType.nta, rules=rules, now=datetime(2026, 9, 24, 14, tzinfo=UTC),
        state="VA", transcript_text="Printed 10/14/2026", digit_system=DigitSystem.persian,
    )  # fmt: skip
    assert ctx.today == TODAY and ctx.order_cue is DateFormat.mdy
    t = assemble_transcript([block("p1b1", "Hearing on October 14, 2026")], pages_received=1)
    d = demand_out(
        "d1", value_verbatim="October 14, 2026", source_quote="Hearing on October 14, 2026",
        span_ids=["p1b1"], date_text="October 14, 2026", role="hearing_date",
    )  # fmt: skip
    v = verify_demands([d], t)
    out = dr.apply_deadline_rules(v.verified, v.sources, ctx, t)
    assert out[0].date is not None and out[0].date.localized_line == "۲۰۲۶-۱۰-۱۴"


def test_eeoc_rule_never_estimates_a_printed_300_day_window(rules: list[DeadlineRule]) -> None:
    doc, emp = DocumentType.other_notice, DocumentCategory.employment
    assert [r.id for r in dr.matching_rules("within 180 days", doc, rules, TODAY, emp)] == [
        "eeoc_180_300d"
    ]
    assert dr.matching_rules("within 300 days", doc, rules, TODAY, emp) == []


# --- Phase 2B: the display preference never reads a printed date; employment rules on letters ---


NTA_TEXT = "Date of notice: 09/24/2026. You must appear on 10/07/2026 at 8:30 AM."


def test_paper_order_beats_any_default_and_the_preference_is_not_a_parser_input() -> None:
    """``Preferences.date_format`` is display only: a Dari reader who picks day-month-year must
    never have a US court date 10/07/2026 read as 10 July (84 days in the past, high confidence)."""
    cue = dr.numeric_order_cue(NTA_TEXT)
    assert cue is DateFormat.mdy
    got = dr.parse_dates("10/07/2026", default_order=DateFormat.dmy, order_cue=cue)
    assert got.single == date(2026, 10, 7), "the page's own cue wins over any default"
    assert "date_format" not in dr.context_for.__code__.co_varnames
    assert "date_format" not in dr.parse_dates.__code__.co_varnames


def test_us_paper_types_default_to_month_first_foreign_ones_stay_ambiguous() -> None:
    assert dr.paper_default_order(DocumentType.nta) is DateFormat.mdy
    assert dr.paper_default_order(DocumentType.uscis_rfe) is DateFormat.mdy
    for doc in (DocumentType.vaccine_record, DocumentType.other_notice, DocumentType.unknown):
        assert dr.paper_default_order(doc) is None
    now = datetime(2026, 10, 2, 14, tzinfo=UTC)
    ctx = dr.context_for(
        document_type=DocumentType.nta, rules=[], now=now, transcript_text="Hearing 10/07/2026"
    )
    assert ctx.default_order is DateFormat.mdy and ctx.order_cue is None
    t = assemble_transcript([block("p1b1", "Hearing on 10/07/2026 at 8:30 AM.")], pages_received=1)
    d = demand_out(
        "d1", value_verbatim="10/07/2026", source_quote="Hearing on 10/07/2026 at 8:30 AM.",
        span_ids=["p1b1"], date_text="10/07/2026", role="hearing_date",
    )  # fmt: skip
    v = verify_demands([d], t)
    out = dr.apply_deadline_rules(v.verified, v.sources, ctx, t)[0]
    assert out.date is not None and out.date.value_iso == "2026-10-07"
    foreign = dr.context_for(
        document_type=DocumentType.vaccine_record, rules=[], now=now, transcript_text=""
    )
    vax = dr.apply_deadline_rules(v.verified, v.sources, foreign, t)[0]
    assert vax.date is not None and vax.date.value_iso is None, "no cue, no default → ambiguous"


def test_employment_rules_never_estimate_a_debt_collectors_window(
    rules: list[DeadlineRule],
) -> None:
    """TAXONOMY §5.3: on an ``other_notice`` the OSHA/EEOC rules need category ``employment``."""
    t = assemble_transcript(
        [
            block("p1b1", "Letter date: September 25, 2026"),
            block("p1b2", "You may dispute this debt within 30 days of receiving this letter."),
        ],
        pages_received=1,
    )
    anchor = demand_out(
        "d1", value_verbatim="September 25, 2026", source_quote="Letter date: September 25, 2026",
        span_ids=["p1b1"], date_text="September 25, 2026", role="other",
    )  # fmt: skip
    window = demand_out(
        "d2", kind=DemandKind.relative_deadline, value_verbatim="within 30 days",
        source_quote="You may dispute this debt within 30 days of receiving this letter.",
        span_ids=["p1b2"], relative_rule_text="within 30 days of receiving this letter",
        anchor_span_id="p1b1", role="response_due",
    )  # fmt: skip
    v = verify_demands([anchor, window], t)
    for category in (None, DocumentCategory.other, DocumentCategory.benefits):
        ctx = dr.DeadlineContext(
            document_type=DocumentType.other_notice, rules=rules, today=TODAY, category=category
        )
        d2 = dr.apply_deadline_rules(v.verified, v.sources, ctx, t)[1]
        assert d2.date is not None and d2.date.kind is DateKind.unresolved, category
        assert d2.date.rule_id is None
    emp = dr.DeadlineContext(
        document_type=DocumentType.other_notice, rules=rules, today=TODAY,
        category=DocumentCategory.employment,
    )  # fmt: skip
    d2 = dr.apply_deadline_rules(v.verified, v.sources, emp, t)[1]
    assert d2.date is not None and d2.date.rule_id == "osha_retaliation_30d"


# --- Phase 2C: an estimate carries a readable line for "About {date} (estimate)" ---------------


def test_estimated_date_carries_a_readable_line_in_every_language(
    rules: list[DeadlineRule],
) -> None:
    """The estimate is printed nowhere: ``localized_line`` holds it written like the printed
    anchor (Western digits, English month), also for Persian-digit packs (D-26, rule 7)."""
    t = _denial_paper()
    v = _denial_demands(t)
    for digits in (DigitSystem.western, DigitSystem.persian, DigitSystem.eastern_arabic):
        ctx = dr.DeadlineContext(
            document_type=DocumentType.insurance_denial, rules=rules, today=TODAY, t=en_t(),
            digit_system=digits,
        )  # fmt: skip
        notice, appeal, _ = dr.apply_deadline_rules(v.verified, v.sources, ctx, t)
        assert appeal.date is not None and appeal.date.kind is DateKind.estimated
        assert appeal.date.localized_line == "February 28, 2027", digits
        # A stated date keeps its digit-localized line (or none for Western digits).
        assert notice.date is not None
        expected = None if digits is DigitSystem.western else dr.localize_digits(
            "2026-09-01", digits
        )
        assert notice.date.localized_line == expected


@pytest.mark.parametrize(
    ("anchor", "anchor_iso", "expected"),
    [
        ("October 14, 2026", "2026-10-14", "November 13, 2026"),
        ("Oct. 14, 2026", "2026-10-14", "November 13, 2026"),
        ("14 October 2026", "2026-10-14", "13 November 2026"),
        ("14 de octubre de 2026", "2026-10-14", "13 November 2026"),
        ("10/14/2026", "2026-10-14", "11/13/2026"),
        ("14/10/2026", "2026-10-14", "13/11/2026"),
        ("3/4/26", "2026-03-04", "11/13/26"),
        ("05-06-2026", "2026-05-06", "11-13-2026"),
        ("۱۰/۱۴/۲۰۲۶", "2026-10-14", "11/13/2026"),
        ("2026-10-14", "2026-10-14", "November 13, 2026"),
        (None, None, "November 13, 2026"),
    ],
)
def test_estimate_text_follows_the_printed_anchor(
    anchor: str | None, anchor_iso: str | None, expected: str
) -> None:
    assert dr.estimate_text(date(2026, 11, 13), anchor, anchor_iso) == expected


# --- a printed date carried by another kind (resolve_carried; AI_PROMPTS §11.4) -----------------

PREPAY = "You may prepay $156.00 by October 9, 2026 instead of coming to court."
QUESTIONNAIRE = "Juror Qualification Questionnaire"
RETURN_FORM = f"Please complete the {QUESTIONNAIRE} and return it by October 23, 2026."


def _carried_paper() -> Transcript:
    return assemble_transcript(
        [
            block("p1b1", "You must appear in court on October 13, 2026 at 9:00 AM, Courtroom 2B."),
            block("p1b2", f"This is a prepayable offense. {PREPAY}"),
            block("p1b3", RETURN_FORM),
            block("p1b4", "Amount due: $312.45 Pay by: October 26, 2026"),
        ],
        pages_received=1,
    )


def _prepay(demand_id: str = "d2", role: str | None = "payment_due") -> DemandOut:
    return demand_out(
        demand_id, kind=DemandKind.amount, value_verbatim="$156.00", source_quote=PREPAY,
        span_ids=["p1b2"], date_text="October 9, 2026", amount_text="$156.00", role=role,
    )  # fmt: skip


def test_dated_role_on_amount_gets_stated_date(rules: list[DeadlineRule]) -> None:
    """traffic_court_notice d2: "prepay $156.00 by October 9, 2026" as an ``amount``."""
    t = _carried_paper()
    v = verify_demands([_prepay()], t)
    out = _apply(v, rules, DocumentType.traffic_court, t)[0]
    assert out.kind is DemandKind.amount and out.source_quote == PREPAY
    assert out.date is not None and out.date.kind is DateKind.stated
    assert out.date.value_iso == "2026-10-09" and out.reminder_eligible
    # The banner, reminder and quick sheet show ``value_verbatim`` as the date: the printed one.
    assert out.value_verbatim == "October 9, 2026"
    assert out.amount is not None and out.amount.amount_minor == 15600


def test_dated_role_on_document_request_gets_stated_date(rules: list[DeadlineRule]) -> None:
    """jury_summons d1: "return it by October 23, 2026" as ``document_requested``."""
    t = _carried_paper()
    d = demand_out(
        "d1", kind=DemandKind.document_requested, value_verbatim=QUESTIONNAIRE,
        source_quote=RETURN_FORM, span_ids=["p1b3"], date_text="October 23, 2026",
        documents=[QUESTIONNAIRE], role="response_due",
    )  # fmt: skip
    v = verify_demands([d], t)
    out = _apply(v, rules, DocumentType.jury_summons, t)[0]
    assert out.kind is DemandKind.document_requested
    assert out.date is not None and out.date.value_iso == "2026-10-23" and out.reminder_eligible
    assert out.documents == [QUESTIONNAIRE]
    assert out.value_verbatim == "October 23, 2026"


def test_date_text_outside_quote_is_ignored(rules: list[DeadlineRule]) -> None:
    """irs_cp_notice d1: the quote is "Amount due: $312.45"; the date beside it is not quoted."""
    t = _carried_paper()
    d = demand_out(
        "d1", kind=DemandKind.amount, value_verbatim="$312.45", source_quote="Amount due: $312.45",
        span_ids=["p1b4"], date_text="October 26, 2026", amount_text="$312.45",
        role="payment_due",
    )  # fmt: skip
    v = verify_demands([d], t)
    out = _apply(v, rules, DocumentType.irs_notice, t)[0]
    assert out.date is None and out.value_verbatim == "$312.45" and not out.reminder_eligible


@pytest.mark.parametrize("role", ["other", "notice_date", "decision_date", None])
def test_role_other_or_notice_date_not_dated(rules: list[DeadlineRule], role: str | None) -> None:
    t = _carried_paper()
    v = verify_demands([_prepay(role=role)], t)
    out = _apply(v, rules, DocumentType.traffic_court, t)[0]
    assert out.date is None and out.value_verbatim == "$156.00"


def test_duplicate_date_not_added_twice(rules: list[DeadlineRule]) -> None:
    t = _carried_paper()
    deadline = demand_out(
        "d1", value_verbatim="October 9, 2026", source_quote=PREPAY, span_ids=["p1b2"],
        date_text="October 9, 2026", role="payment_due",
    )  # fmt: skip
    v = verify_demands([deadline, _prepay("d2"), _prepay("d3")], t)
    out = _apply(v, rules, DocumentType.traffic_court, t)
    assert out[0].date is not None and out[0].date.value_iso == "2026-10-09"
    assert [d.date for d in out[1:]] == [None, None]
    # Without the deadline the first carrier gets the date and the second stays as written.
    v2 = verify_demands([_prepay("d2"), _prepay("d3")], t)
    out2 = _apply(v2, rules, DocumentType.traffic_court, t)
    assert out2[0].date is not None and out2[1].date is None


def test_no_estimate_for_non_dated_kinds(rules: list[DeadlineRule]) -> None:
    t = _denial_paper()
    v = _denial_demands(t)
    action = demand_out(
        "d4", kind=DemandKind.action, value_verbatim="internal appeal",
        source_quote="You may ask for an internal appeal within 180 days of this notice.",
        span_ids=["p1b2"], relative_rule_text="within 180 days of this notice",
        anchor_span_id="p1b1", role="response_due",
    )  # fmt: skip
    both = verify_demands([*v.sources.values(), action], t)
    out = _apply(both, rules, DocumentType.insurance_denial, t)
    assert out[1].date is not None and out[1].date.kind is DateKind.estimated
    assert out[3].kind is DemandKind.action and out[3].date is None


def test_carried_date_needs_one_printed_day(rules: list[DeadlineRule]) -> None:
    t = assemble_transcript(
        [block("p1b1", "Bring your lease by Monday, October 14."),
         block("p1b2", "Please return the form by Octobr 23, 2026.")],
        pages_received=1,
    )  # fmt: skip
    yearless = demand_out(
        "d1", kind=DemandKind.document_requested, value_verbatim="your lease",
        source_quote="Bring your lease by Monday, October 14.", span_ids=["p1b1"],
        date_text="Monday, October 14", documents=["your lease"], role="response_due",
    )  # fmt: skip
    # A fuzzy quote (the page misspells the month): the model's date is not what is printed.
    misprint = demand_out(
        "d2", kind=DemandKind.document_requested, value_verbatim="the form",
        source_quote="Please return the form by October 23, 2026.", span_ids=["p1b2"],
        date_text="October 23, 2026", documents=["the form"], role="response_due",
    )  # fmt: skip
    v = verify_demands([yearless, misprint], t)
    assert len(v.verified) == 2
    out = _apply(v, rules, DocumentType.other_notice, t)
    for d, before in zip(out, v.verified, strict=True):
        assert d == before, "no date, no low-confidence side effect, value unchanged"


HEDGE = "I cannot tell you what to file or send. I can explain what the paper asks for."


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        (HEDGE, f"$156.00 — {HEDGE}"),  # the lint hedged the sentence that held the amount
        ("Pay early to skip court.", "$156.00 — Pay early to skip court."),  # never written
        ("", "$156.00"),
        ("You may prepay $156.00 instead.", "You may prepay $156.00 instead."),  # still shown
    ],
)
def test_a_carried_payment_keeps_its_printed_amount_in_view(
    rules: list[DeadlineRule], text: str, shown: str
) -> None:
    """The value became the printed date (banner, reminders, quick sheet); the amount — printed in
    the verified quote — stays in the text, so the row and "Hear it" still say what to pay."""
    t = _carried_paper()
    v = verify_demands([_prepay()], t)
    carried = _apply(v, rules, DocumentType.traffic_court, t)[0].model_copy(update={"text": text})
    out = dr.keep_carried_amount(carried, v.sources["d2"])
    assert out.text == shown
    assert out.value_verbatim == "October 9, 2026" and out.date == carried.date


def test_only_a_carried_amount_with_a_printed_amount_is_touched(rules: list[DeadlineRule]) -> None:
    t = _carried_paper()
    # Not carried (role "other"): the value still shows "$156.00".
    v = verify_demands([_prepay(role="other")], t)
    plain = _apply(v, rules, DocumentType.traffic_court, t)[0].model_copy(update={"text": HEDGE})
    assert dr.keep_carried_amount(plain, v.sources["d2"]) == plain
    # A carried document request has no amount to keep.
    d = demand_out(
        "d1", kind=DemandKind.document_requested, value_verbatim=QUESTIONNAIRE,
        source_quote=RETURN_FORM, span_ids=["p1b3"], date_text="October 23, 2026",
        documents=[QUESTIONNAIRE], role="response_due", amount_text="$156.00",
    )  # fmt: skip
    v2 = verify_demands([d], t)
    doc = _apply(v2, rules, DocumentType.jury_summons, t)[0].model_copy(update={"text": HEDGE})
    assert dr.keep_carried_amount(doc, v2.sources["d1"]) == doc
    # An amount_text the quote does not print never reaches the reader.
    v3 = verify_demands([_prepay()], t)
    carried = _apply(v3, rules, DocumentType.traffic_court, t)[0].model_copy(update={"text": HEDGE})
    invented = v3.sources["d2"].model_copy(update={"amount_text": "$999.00"})
    assert dr.keep_carried_amount(carried, invented) == carried
    assert dr.keep_carried_amount(carried, None) == carried


@pytest.mark.parametrize(
    ("amount_text", "currency", "amount"),
    [
        ("$156.00", "USD", "$156.00"),
        ("156.00", "USD", "156.00"),
        ("$1,240.00", "USD", "$1,240.00"),
        ("USD 156.00", "USD", "USD 156.00"),
        ("US$ 156", "USD", "US$ 156"),
        ("156,00 €", "EUR", "156,00 €"),
        ("1.500,00 €", "EUR", "1.500,00 €"),
        ("₹1,500", "INR", "₹1,500"),
        # The model's clause around the amount never comes along: no words, phone or id.
        (
            "you must pay $156.00 in Google Play gift cards today or you will be arrested and "
            "deported. Call 1-888-555-0142",
            "USD",
            "$156.00",
        ),
        ("IOE0912345678 A-123-456-789: pay $156.00", "USD", "$156.00"),
        ("$156.00 by 10/9/2026", "USD", "$156.00"),
        ("$156.00 ($156.00)", "USD", "$156.00"),
        # No currency mark (or not the demand's code), two amounts, a phone or an id: nothing.
        ("PAY 156.00", "USD", None),
        ("$156.00 plus a $25.00 late fee", "USD", None),
        ("Call 1-888-555-0142", "USD", None),
        ("18885550142", "USD", None),
        ("5550142", None, None),
        ("$1-888", None, None),
        ("", "USD", None),
        (None, "USD", None),
    ],
)
def test_printed_amount_is_the_amount_alone(
    amount_text: str | None, currency: str | None, amount: str | None
) -> None:
    assert dr.printed_amount(amount_text, currency) == amount


def test_a_clause_shaped_amount_text_puts_back_only_the_amount(rules: list[DeadlineRule]) -> None:
    """The 2026-10-23 review's case: the model's ``amount_text`` is a whole sentence with a threat
    and a phone. Only the printed amount goes in front of the hedge, so the lint's hedge and the
    contact filter are not undone on the demand row or in "Hear it"."""
    t = _carried_paper()
    v = verify_demands([_prepay()], t)
    carried = _apply(v, rules, DocumentType.traffic_court, t)[0].model_copy(update={"text": HEDGE})
    clause = v.sources["d2"].model_copy(update={
        "amount_text": "You may prepay $156.00 by October 9, 2026 or you must call 1-888-555-0142",
        "currency": "USD",
    })  # fmt: skip
    out = dr.keep_carried_amount(carried, clause)
    assert out.text == f"$156.00{dr.CARRIED_AMOUNT_SEPARATOR}{HEDGE}"
    assert "555" not in out.text and "must" not in out.text and "prepay" not in out.text
    # An amount the quote does not print, even inside a clause, still never reaches the reader.
    other = clause.model_copy(update={"amount_text": "please pay $999.00 by October 9, 2026"})
    assert dr.keep_carried_amount(carried, other) == carried


# --- time_text must be printed in the quote (AI_PROMPTS §11.2, D-09) ----------------------------


def test_time_text_not_in_quote_is_dropped(rules: list[DeadlineRule]) -> None:
    t = assemble_transcript(
        [block("p1b1", "Please respond by October 14, 2026.")], pages_received=1
    )
    d = demand_out(
        "d1", value_verbatim="October 14, 2026", source_quote="respond by October 14, 2026",
        span_ids=["p1b1"], date_text="October 14, 2026", time_text="7:00 AM",
        role="response_due",
    )  # fmt: skip
    rel = demand_out(
        "d2", kind=DemandKind.relative_deadline, value_verbatim="by October 14, 2026",
        source_quote="respond by October 14, 2026", span_ids=["p1b1"],
        relative_rule_text="within 3 days", time_text="5:00 PM", role="response_due",
    )  # fmt: skip
    v = verify_demands([d, rel], t)
    stated, relative = _apply(v, rules, DocumentType.other_notice, t)
    assert stated.date is not None and stated.date.value_iso == "2026-10-14"
    assert stated.date.time_text is None
    assert relative.date is not None and relative.date.time_text is None


def test_printed_time_kept(rules: list[DeadlineRule]) -> None:
    line = (
        "YOU ARE ORDERED to appear before an immigration judge at 100 Sample Plaza, Suite 200, "
        "Fairfax, VA 22030 on October 7, 2026 at 8:30 AM."
    )
    t = assemble_transcript([block("p1b1", line)], pages_received=1)
    d = demand_out(
        "d1", kind=DemandKind.appointment, value_verbatim="October 7, 2026", source_quote=line,
        span_ids=["p1b1"], date_text="October 7, 2026", time_text="8:30 AM", role="hearing_date",
    )  # fmt: skip
    v = verify_demands([d], t)
    out = _apply(v, rules, DocumentType.nta, t)[0]
    assert out.date is not None and out.date.time_text == "8:30 AM"
    assert out.date.value_iso == "2026-10-07"


# --- an anchor re-anchored by demand_repair (R4) still answers to its cited id ------------------


def test_anchor_resolves_after_reanchor(rules: list[DeadlineRule]) -> None:
    window ="within 180 days of the date of this notice"
    appeal_line = f"You must ask for an internal appeal {window}."
    t = assemble_transcript(
        [
            block("p1b1", "Blue Ridge Sample Health Plan"),
            block("p1b2", "Date of this notice: April 20, 2026"),
            block("p1b3", appeal_line),
        ],
        pages_received=1,
    )
    notice = demand_out(
        "d1", value_verbatim="April 20, 2026", source_quote="Date of this notice: April 20, 2026",
        span_ids=["p1b1"], date_text="April 20, 2026", role="notice_date",
    )  # fmt: skip
    appeal = demand_out(
        "d2", kind=DemandKind.relative_deadline, value_verbatim=window, source_quote=appeal_line,
        span_ids=["p1b3"], relative_rule_text=window, anchor_span_id="p1b1", role="response_due",
    )  # fmt: skip
    repaired = repair_demands([notice, appeal], t)
    assert repaired.repairs[0].codes == (R4_REANCHORED,)
    checked = repaired.verify(t)
    assert [d.span_ids for d in checked.verified] == [["p1b2"], ["p1b3"]]
    ctx = _ctx(rules, DocumentType.insurance_denial, date(2026, 5, 1))
    plain = dr.apply_deadline_rules(checked.verified, checked.sources, ctx, t)
    assert plain[1].date is not None and plain[1].date.kind is DateKind.unresolved
    aliases = repaired.span_aliases(checked)
    assert aliases == {"d1": ["p1b1"]}
    out = dr.apply_deadline_rules(checked.verified, checked.sources, ctx, t, span_aliases=aliases)
    assert out[1].date is not None and out[1].date.kind is DateKind.estimated
    assert out[1].date.anchor_demand_id == "d1" and out[1].date.value_iso == "2026-10-17"


def _appeal_paper(*extra: tuple[str, str]) -> Transcript:
    return assemble_transcript(
        [
            block("p1b1", "Blue Ridge Sample Health Plan"),
            block("p1b2", "Date of this notice: April 20, 2026"),
            block("p1b3", "You must ask for an internal appeal within 180 days of the date of "
                          "this notice."),
            *(block(i, text) for i, text in extra),
        ],
        pages_received=1,
    )  # fmt: skip


def _appeal_demands(*anchors: DemandOut, anchor_span_id: str = "p1b2") -> list[DemandOut]:
    window = "within 180 days of the date of this notice"
    appeal = demand_out(
        "d3", kind=DemandKind.relative_deadline, value_verbatim=window,
        source_quote=f"You must ask for an internal appeal {window}.", span_ids=["p1b3"],
        relative_rule_text=window, anchor_span_id=anchor_span_id, role="response_due",
    )  # fmt: skip
    return [*anchors, appeal]


def _mailed(span: str = "p1b2") -> DemandOut:
    """"Date mailed" quoted exactly but cited to ``span`` (R4 moves it to p1b4)."""
    return demand_out(
        "d1", value_verbatim="April 27, 2026", source_quote="Date mailed: April 27, 2026",
        span_ids=[span], date_text="April 27, 2026", role="notice_date",
    )  # fmt: skip


def _estimate_with_aliases(
    rules: list[DeadlineRule], t: Transcript, demands: list[DemandOut]
) -> Demand:
    repaired = repair_demands(demands, t)
    checked = repaired.verify(t)
    ctx = _ctx(rules, DocumentType.insurance_denial, date(2026, 5, 1))
    out = dr.apply_deadline_rules(
        checked.verified, checked.sources, ctx, t, span_aliases=repaired.span_aliases(checked)
    )
    return out[-1]


def test_direct_anchor_wins_over_reanchored_alias(rules: list[DeadlineRule]) -> None:
    """D-11 (b): the demand whose own span holds ``anchor_span_id`` is the anchor, whatever the
    list order; a demand R4 moved *away* from that block (listed first here) never stands in, so
    the estimate never counts from the later "Date mailed"."""
    t = _appeal_paper(("p1b4", "Date mailed: April 27, 2026"))
    notice = demand_out(
        "d2", value_verbatim="April 20, 2026", source_quote="Date of this notice: April 20, 2026",
        span_ids=["p1b2"], date_text="April 20, 2026", role="notice_date",
    )  # fmt: skip
    appeal = _estimate_with_aliases(rules, t, _appeal_demands(_mailed(), notice))
    assert appeal.date is not None and appeal.date.kind is DateKind.estimated
    assert appeal.date.anchor_demand_id == "d2" and appeal.date.value_iso == "2026-10-17"


def test_alias_refused_when_named_block_prints_another_date(rules: list[DeadlineRule]) -> None:
    """No demand quotes p1b2's own date (April 20): the re-anchored "Date mailed" (April 27) may
    not stand in for it, so the appeal stays unresolved rather than a week too late."""
    t = _appeal_paper(("p1b4", "Date mailed: April 27, 2026"))
    appeal = _estimate_with_aliases(rules, t, _appeal_demands(_mailed()))
    assert appeal.date is not None and appeal.date.kind is DateKind.unresolved


def test_alias_kept_when_named_block_prints_the_same_date(rules: list[DeadlineRule]) -> None:
    t = assemble_transcript(
        [
            block("p1b1", "Issued April 27, 2026"),
            block("p1b2", "Blue Ridge Sample Health Plan"),
            block("p1b3", "You must ask for an internal appeal within 180 days of the date of "
                          "this notice."),
            block("p1b4", "Date mailed: April 27, 2026"),
        ],
        pages_received=1,
    )  # fmt: skip
    demands = _appeal_demands(_mailed("p1b1"), anchor_span_id="p1b1")
    appeal = _estimate_with_aliases(rules, t, demands)
    assert appeal.date is not None and appeal.date.kind is DateKind.estimated
    assert appeal.date.anchor_demand_id == "d1" and appeal.date.value_iso == "2026-10-24"
