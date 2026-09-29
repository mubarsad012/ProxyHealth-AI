"""WP2 — ``analysis/fixed_notices.py`` + ``data/rules/fixed_notices.yaml`` (D-20; TAXONOMY §7)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from proxyhealth_api.analysis import fixed_notices as fn
from proxyhealth_api.analysis.verify import MULTIPLE_DOCUMENTS_SENTINEL
from proxyhealth_api.contracts.analysis import DateInfo, Demand, RedFlag
from proxyhealth_api.contracts.enums import (
    Confidence,
    DateKind,
    DemandKind,
    DocumentType,
    RedFlagKind,
    ScamRisk,
    Severity,
)
from proxyhealth_api.resources.rules_repo import RulesRepo
from proxyhealth_api.settings import DATA_DIR
from tests.unit._fixtures_wp2 import en_t

DT = DocumentType


@pytest.fixture(scope="module")
def rules() -> RulesRepo:
    return RulesRepo.load(DATA_DIR / "rules")


def stated(role: str, iso: str, *, verified: bool = True) -> Demand:
    info = DateInfo(
        value_iso=iso, time_text=None, kind=DateKind.stated, formula=None, anchor_quote=None,
        anchor_demand_id=None, rule_id=None, rule_source_url=None, rule_verification=None,
        localized_line=None,
    )  # fmt: skip
    return Demand(
        id=f"d_{role}", kind=DemandKind.deadline, text="x", value_verbatim=iso, source_quote=iso,
        span_ids=["p1b1"], page=1, confidence=Confidence.high, verified=verified,
        verification_note=None, date=info, amount=None, documents=[], role=role,
        reminder_eligible=verified, ambiguity_note=None,
    )  # fmt: skip


def flag(kind: RedFlagKind, text: str = "t", severity: Severity = Severity.medium) -> RedFlag:
    return RedFlag(
        kind=kind, text=text, source_quote="q", span_ids=["p1b1"], page=1, severity=severity,
        fixed_copy_key=None, verified=True,
    )  # fmt: skip


def keys(rules: RulesRepo, facts: fn.NoticeFacts) -> list[str]:
    return [f.fixed_copy_key or "" for f in fn.evaluate_notices(rules, facts, en_t())]


def test_yaml_loads_with_the_seeded_and_enabled_notices(rules: RulesRepo) -> None:
    ids = {n.id for n in rules.all_fixed_notices()}
    assert {
        "jury_citizenship", "ead_receipt", "not_a_court_order", "court_date_deadline_eviction",
        "no_fee_waiver", "address_multi_agency",
    } <= ids  # fmt: skip
    for n in rules.all_fixed_notices():
        assert n.fixed_copy_key.startswith("fixed.")
        assert fn.condition_holds(n.when, fn.NoticeFacts(DT.unknown)) in (True, False)


@pytest.mark.parametrize(
    ("doc", "key", "kind"),
    [
        (DT.jury_summons, "fixed.jury_summons", RedFlagKind.jury_citizenship_warning),
        (DT.pay_or_quit, "fixed.pay_or_quit", RedFlagKind.not_a_court_order),
        (DT.eviction_summons, "fixed.eviction_summons", RedFlagKind.court_date_is_the_deadline),
        (DT.asylum_fee_notice, "fixed.asylum_fee_notice", RedFlagKind.no_fee_waiver),
        (DT.nta, "fixed.address_change_multi_agency", RedFlagKind.address_change_multi_agency),
        (DT.hearing_notice, "fixed.address_change_multi_agency",
         RedFlagKind.address_change_multi_agency),
        (DT.eob, "fixed.eob_not_a_bill", RedFlagKind.other),
        (DT.traffic_court, "fixed.traffic_court_immigration", RedFlagKind.other),
    ],
)  # fmt: skip
def test_always_notices(rules: RulesRepo, doc: DocumentType, key: str, kind: RedFlagKind) -> None:
    [card, *_] = [f for f in fn.evaluate_notices(rules, fn.NoticeFacts(doc), en_t())
                  if f.fixed_copy_key == key]  # fmt: skip
    assert card.kind is kind and card.verified and card.source_quote is None
    assert card.span_ids == [] and card.page is None
    assert card.text == en_t()(key) and card.text != key


def test_ead_receipt_conditions(rules: RulesRepo) -> None:
    text = "I-797C Notice of Action. Receipt Notice. Form I-765 Application for Employment."
    base = fn.NoticeFacts(DT.uscis_receipt, transcript_text=text, form_numbers=["I-765"])
    assert keys(rules, base) == ["fixed.uscis_receipt_i765"]
    # the form number printed only in the transcript (hyphen-insensitive) also counts
    loose = fn.NoticeFacts(DT.uscis_receipt, transcript_text=text.replace("I-765", "I765"))
    assert keys(rules, loose)
    # received before 2025-10-30 → hidden; on/after → shown; none printed → shown (fail-open)
    old = replace(base, demands=[stated("notice_date", "2025-10-01")])
    new = replace(base, demands=[stated("notice_date", "2025-11-03")])
    assert keys(rules, old) == [] and keys(rules, new) == ["fixed.uscis_receipt_i765"]
    tps = fn.NoticeFacts(DT.uscis_receipt, transcript_text=text + " Category (a)(12) A12",
                         form_numbers=["I-765"])  # fmt: skip
    assert keys(rules, tps) == []
    assert keys(rules, fn.NoticeFacts(DT.uscis_receipt, transcript_text="Receipt Notice I-130",
                                      form_numbers=["I-130"])) == []  # fmt: skip


def test_low_type_confidence_hides_type_cards(rules: RulesRepo) -> None:
    low = fn.NoticeFacts(DT.jury_summons, document_type_confidence=Confidence.low)
    assert keys(rules, low) == []
    medium = fn.NoticeFacts(DT.jury_summons, document_type_confidence=Confidence.medium)
    assert keys(rules, medium) == ["fixed.jury_summons"]


def test_role_red_flag_and_text_conditions(rules: RulesRepo) -> None:
    hearing = fn.NoticeFacts(DT.nta, demands=[stated("hearing_date", "2026-10-01")])
    assert "fixed.court_date_is_the_deadline" in keys(rules, hearing)
    unverified = fn.NoticeFacts(DT.nta, demands=[stated("hearing_date", "2026-10-01",
                                                        verified=False)])  # fmt: skip
    assert "fixed.court_date_is_the_deadline" not in keys(rules, unverified)
    notario = fn.NoticeFacts(DT.other_notice, red_flags=[flag(RedFlagKind.notario)])
    assert keys(rules, notario) == ["fixed.notario_not_a_lawyer"]
    low_notario = fn.NoticeFacts(DT.other_notice, document_type_confidence=Confidence.low,
                                 red_flags=[flag(RedFlagKind.notario)])  # fmt: skip
    assert keys(rules, low_notario) == ["fixed.notario_not_a_lawyer"]  # 'any' is not type-specific
    card = fn.NoticeFacts(DT.green_card_related, transcript_text="Conditional resident CR1")
    assert keys(rules, card) == ["fixed.conditional_card"]
    assert keys(rules, fn.NoticeFacts(DT.green_card_related, transcript_text="10-year card")) == []


def test_condition_grammar_edges() -> None:
    facts = fn.NoticeFacts(DT.other_notice, scam_risk=ScamRisk.likely)
    assert fn.condition_holds("always", facts)
    assert fn.condition_holds({"scam_risk": "likely"}, facts)
    assert not fn.condition_holds({"scam_risk": "possible"}, facts)
    assert not fn.condition_holds({"made_up_condition": True}, facts)  # fails closed
    assert not fn.condition_holds(42, facts)
    assert not fn.condition_holds(
        {"date_on_or_after": {"role": "notice_date", "iso": "2025-10-30", "when_missing": "hide"}},
        facts,
    )


def test_multiple_documents_sentinel_and_merge() -> None:
    t = en_t()
    sentinel = flag(RedFlagKind.other, MULTIPLE_DOCUMENTS_SENTINEL)
    model = flag(RedFlagKind.urgency_pressure, "Pushes you to hurry.")
    swapped = fn.replace_multiple_documents_sentinel([model, sentinel, sentinel], t)
    assert [f.fixed_copy_key for f in swapped] == [None, "fixed.multiple_documents"]
    high_fixed = fn.fixed_red_flag(RedFlagKind.jury_citizenship_warning, Severity.high,
                                   "fixed.jury_summons", t)  # fmt: skip
    high_model = flag(RedFlagKind.scam_payment_method, "x", Severity.high)
    merged = fn.merge_red_flags([high_model, *swapped], [high_fixed, high_fixed])
    assert merged[0] is high_fixed and merged[1] is high_model
    assert [f.fixed_copy_key for f in merged].count("fixed.jury_summons") == 1
    assert merged[2].fixed_copy_key == "fixed.multiple_documents"
