"""WP2 — ``analysis/tagging.py`` (D-10/D-13/D-14; AI_PROMPTS §11.10; TAXONOMY §2)."""

from __future__ import annotations

from proxyhealth_api.analysis import tagging as tg
from proxyhealth_api.contracts.analysis import RedFlag
from proxyhealth_api.contracts.enums import (
    DocumentCategory,
    DocumentType,
    RedFlagKind,
    ResourceTag,
    ScamRisk,
    Severity,
)

DT = DocumentType
RT = ResourceTag


def test_only_enum_tags_survive_deduplicated_and_capped() -> None:
    raw = ["snap", "SNAP", "free food!!", "Food", "benefits navigation", "wic", "crisis",
           "poison", "eviction", "asylum"]  # fmt: skip
    assert tg.validate_tags(raw) == [
        RT.snap, RT.food, RT.benefits_navigation, RT.wic, RT.crisis, RT.poison,
    ]  # fmt: skip
    assert tg.validate_tags(["dhs_oig", "https://evil.example"]) == []


def test_every_document_type_has_a_primary_tag_row() -> None:
    assert set(tg.PRIMARY_TAGS) == set(DocumentType)
    assert tg.primary_tags(DT.nta) == [RT.removal_proceedings, RT.court_notice,
                                       RT.change_of_address]  # fmt: skip
    assert tg.primary_tags(DT.uscis_receipt, form_numbers=["I-797C", "I-765"]) == [
        RT.immigration_legal_help, RT.work_permit,
    ]  # fmt: skip
    assert tg.primary_tags(DT.other_notice, DocumentCategory.tax) == [RT.tax_notice]
    assert tg.primary_tags(DT.unknown) == []


def test_empty_model_tags_fall_back_to_the_type() -> None:
    out = tg.finalize_tags([], document_type=DT.medicaid_renewal)
    assert out.tags == [RT.medicaid_renewal, RT.benefits_navigation] and out.source == "type"
    assert out.needs_tag_call is False


def test_tag_call_only_when_still_empty_and_readable() -> None:
    first = tg.finalize_tags([], document_type=DT.unknown, readable=True)
    assert first.tags == [] and first.needs_tag_call and first.source == "none"
    second = tg.finalize_tags([], document_type=DT.unknown, tag_call_tags=["food", "nope"])
    assert second.tags == [RT.food] and second.source == "tag_call"
    assert not second.needs_tag_call
    blurry = tg.finalize_tags([], document_type=DT.unknown, readable=False)
    assert blurry.tags == [] and not blurry.needs_tag_call


def test_scam_and_crisis_forcing() -> None:
    scam = tg.finalize_tags(
        ["immigration_legal_help", "scam_report"], document_type=DT.other_notice,
        scam_risk=ScamRisk.likely,
    )  # fmt: skip
    assert scam.tags[0] is RT.scam_report and scam.tags.count(RT.scam_report) == 1
    both = tg.finalize_tags(
        ["food"], document_type=DT.other_notice, scam_risk=ScamRisk.likely, emergency=True
    )
    assert both.tags[:2] == [RT.crisis, RT.scam_report]
    possible = tg.finalize_tags(
        ["food"], document_type=DT.other_notice, scam_risk=ScamRisk.possible
    )
    assert possible.tags == [RT.food]
    many = tg.finalize_tags(
        ["snap", "food", "wic", "benefits_navigation", "ssa_benefits", "medicaid_renewal"],
        document_type=DT.snap_notice, emergency=True,
    )  # fmt: skip
    assert len(many.tags) == tg.MAX_TAGS and many.tags[0] is RT.crisis


def test_scam_flags_add_the_category_tag() -> None:
    flag = RedFlag(
        kind=RedFlagKind.impersonation, text="x", source_quote="q", span_ids=["p1b1"], page=1,
        severity=Severity.high, fixed_copy_key=None, verified=True,
    )  # fmt: skip
    out = tg.finalize_tags(
        ["scam_report"], document_type=DT.other_notice, category=DocumentCategory.immigration,
        red_flags=[flag],
    )  # fmt: skip
    assert out.tags == [RT.scam_report, RT.immigration_legal_help]
