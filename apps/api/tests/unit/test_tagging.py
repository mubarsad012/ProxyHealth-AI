"""WP2 — ``analysis/tagging.py`` (D-10/D-13/D-14; AI_PROMPTS §11.10; TAXONOMY §2)."""

from __future__ import annotations

import pytest

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
from proxyhealth_api.contracts.model_out import AnalysisModelOut, RedFlagOut
from proxyhealth_api.demo.fixtures import FixtureStore
from proxyhealth_api.settings import DATA_DIR

DT = DocumentType
RT = ResourceTag
STORE = FixtureStore.load(DATA_DIR / "fixtures")


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
    gated = tg.finalize_tags(
        ["scam_report"], document_type=DT.other_notice, category=DocumentCategory.immigration,
        red_flags=[flag], gate_sensitive=True,
    )  # fmt: skip
    assert gated.tags == out.tags  # a verified impersonation flag is scam evidence


# --- the type's tags always follow the model's; crisis and scam tags need code evidence ---------
# (D-13, D-14). A small model tagged a pharmacy label crisis/domestic_violence/trafficking with no
# emergency term printed, and gave a SNAP notice only scam_report although the scorer said none.


def test_unbacked_scam_report_falls_back_to_the_type() -> None:
    out = tg.finalize_tags(["scam_report"], document_type=DT.snap_notice, gate_sensitive=True)
    assert out.tags == [RT.snap, RT.food, RT.benefits_navigation] and out.source == "type"
    possible = tg.finalize_tags(
        ["scam_report"], document_type=DT.snap_notice, scam_risk=ScamRisk.possible,
        gate_sensitive=True,
    )  # fmt: skip
    assert possible.tags == [RT.scam_report, RT.snap, RT.food, RT.benefits_navigation]
    likely = tg.finalize_tags(["food"], document_type=DT.other_notice, scam_risk=ScamRisk.likely,
                              gate_sensitive=True)  # fmt: skip
    assert likely.tags[0] is RT.scam_report
    first_call = tg.finalize_tags(["scam_report"], document_type=DT.snap_notice)
    assert first_call.tags[0] is RT.scam_report, "only the final call is gated"


LABEL = "CVS Pharmacy\nTake 1 tablet by mouth twice daily\nRefills: 2"


def test_emergency_tags_need_an_emergency_on_a_sample_paper() -> None:
    """The sweep's junk tags came from sample papers: there crisis/poison need an emergency."""
    model = ["prescription_help", "crisis", "domestic_violence", "trafficking", "poison"]
    calm = tg.finalize_tags(model, document_type=DT.prescription_label, gate_sensitive=True,
                            printed_text=LABEL, language="en", sample=True)  # fmt: skip
    assert calm.tags == [RT.prescription_help, RT.language_access]
    urgent = tg.finalize_tags(model, document_type=DT.prescription_label, emergency=True,
                              gate_sensitive=True, printed_text=LABEL, language="en",
                              sample=True)  # fmt: skip
    assert urgent.tags[0] is RT.crisis and RT.domestic_violence in urgent.tags
    assert len(urgent.tags) == tg.MAX_TAGS
    tag_call = tg.finalize_tags([], document_type=DT.unknown, tag_call_tags=["crisis", "food"],
                                gate_sensitive=True, sample=True)  # fmt: skip
    assert tag_call.tags == [RT.food] and tag_call.source == "tag_call"


def test_a_real_upload_keeps_the_models_crisis_and_poison_tags() -> None:
    """Integration review, issue 13 (D-14): a drafted lexicon misses wording ("li vle touye tèt
    li"), so on a real upload the model's crisis/poison tag is never dropped — DV/trafficking
    still need an abuse context, as before."""
    model = ["prescription_help", "crisis", "domestic_violence", "trafficking", "poison"]
    real = tg.finalize_tags(model, document_type=DT.prescription_label, gate_sensitive=True,
                            printed_text=LABEL, language="en")  # fmt: skip
    assert real.tags == [RT.prescription_help, RT.crisis, RT.poison, RT.language_access]
    school = tg.finalize_tags(["crisis"], document_type=DT.other_notice,
                              category=DocumentCategory.school, gate_sensitive=True,
                              printed_text="Pitit ou a te di li vle touye tèt li.",
                              language="ht")  # fmt: skip
    assert school.tags == [RT.crisis, RT.school_enrollment]
    assert tg.model_crisis(["school_enrollment", "Crisis"], sample=False)
    assert not tg.model_crisis(["crisis"], sample=True), "a sample's junk tag is no emergency"
    assert not tg.model_crisis(["poison", "domestic_violence"], sample=False)


PROTECTIVE_ORDER = (
    "JUVENILE AND DOMESTIC RELATIONS DISTRICT COURT\n"
    "PRELIMINARY PROTECTIVE ORDER (FAMILY ABUSE)\n"
    "The respondent shall have no contact with the petitioner."
)


def test_abuse_papers_keep_dv_and_trafficking_tags_without_an_emergency() -> None:
    """Review of package B: a protective order, a VAWA or U/T-visa paper prints no emergency
    term, yet the DV and trafficking hotlines are exactly its resources. Only crisis and poison
    (immediate danger) need the emergency lexicon."""
    model = ["court_notice", "domestic_violence", "crisis"]
    order = tg.finalize_tags(model, document_type=DT.other_notice, category=DocumentCategory.court,
                             gate_sensitive=True, printed_text=PROTECTIVE_ORDER,
                             language="en", sample=True)  # fmt: skip
    assert order.tags == [RT.court_notice, RT.domestic_violence]
    for text in ("Form I-918, Petition for U Nonimmigrant Status", "Form I-914 T visa",
                 "VAWA self-petition (Form I-360)", "Victims of human trafficking",
                 "Orden de protección por violencia doméstica"):  # fmt: skip
        assert tg.prints_abuse_context(text, "en") and tg.prints_abuse_context(text, "es-US"), text
    assert not tg.prints_abuse_context(LABEL, "en")
    # A language with no cue list (or none detected) keeps the model's DV/trafficking tags.
    assert tg.prints_abuse_context(LABEL, "vi") and tg.prints_abuse_context(LABEL, None)
    kept = tg.finalize_tags(["trafficking", "crisis"], document_type=DT.unknown,
                            gate_sensitive=True, printed_text=LABEL, language="vi",
                            sample=True)  # fmt: skip
    assert kept.tags == [RT.trafficking]


def test_primary_tags_follow_the_models_own() -> None:
    out = tg.finalize_tags(["housing_counseling"], document_type=DT.pay_or_quit)
    assert out.tags == [RT.housing_counseling, RT.eviction, RT.rent_assistance]
    assert out.source == "model"
    receipt = tg.finalize_tags(["uscis_receipt", "work_permit"], document_type=DT.uscis_receipt,
                               form_numbers=["I-797C", "I-765"])  # fmt: skip
    assert receipt.tags == [RT.work_permit, RT.immigration_legal_help]
    capped = tg.finalize_tags(
        ["food", "wic", "ssa_benefits", "section8", "school_meals", "eviction"],
        document_type=DT.snap_notice, gate_sensitive=True,
    )  # fmt: skip
    assert len(capped.tags) == tg.MAX_TAGS and capped.tags[0] is RT.food


@pytest.mark.parametrize(
    ("fid", "lang"),
    [(f.id, lang) for f in STORE.all() if f.kind == "document" for lang in f.languages],
)
def test_curated_fixture_tags_are_unchanged(fid: str, lang: str) -> None:
    out = STORE.get(fid).analysis_out(lang)  # type: ignore[union-attr]
    assert out is not None
    scam = ScamRisk.likely if fid == "scam_gift_card_letter" else ScamRisk.none
    got = tg.finalize_tags(
        out.resource_tags, document_type=out.document_type, category=out.category,
        form_numbers=out.form_numbers, scam_risk=scam, gate_sensitive=True,
    )  # fmt: skip
    model = tg.validate_tags(out.resource_tags)
    if scam is ScamRisk.likely:
        model = [RT.scam_report, *[t for t in model if t is not RT.scam_report]]
    assert got.tags == model


# --- integration review: the model's own scam verdict, and the gated first pass ----------------


def test_a_real_upload_the_model_calls_a_scam_keeps_its_scam_report_tag() -> None:
    """Issue 14: with no code evidence left (a block-id quote, a language without scam regexes),
    the model's own verdict keeps its scam_report tag on a real upload — never on a sample, where
    the SAMPLE footer made a small model call every paper fake. On that verdict alone the tag goes
    behind the type's own (G1 review: a small model also calls genuine papers fake)."""

    def tags(*, model_scam: bool, sample: bool = False) -> tg.TagOutcome:
        return tg.finalize_tags(
            ["scam_report"], document_type=DT.other_notice,
            category=DocumentCategory.immigration, gate_sensitive=True, model_scam=model_scam,
            sample=sample,
        )  # fmt: skip

    assert tags(model_scam=True).tags == [RT.immigration_legal_help, RT.scam_report]
    sample = tags(model_scam=True, sample=True)
    assert sample.tags == [RT.immigration_legal_help] and sample.source == "type"
    assert RT.scam_report not in tags(model_scam=False).tags
    # No type tags to put first: the verdict's tag is the list (and is not cut by the cap).
    alone = tg.finalize_tags(["scam_report"], document_type=DT.other_notice,
                             category=DocumentCategory.other, gate_sensitive=True,
                             model_scam=True)  # fmt: skip
    assert alone.tags == [RT.scam_report]
    many = tg.finalize_tags(["scam_report", "food", "utility_shutoff", "benefits_navigation",
                             "rent_assistance", "tax_notice"], document_type=DT.other_notice,
                            category=DocumentCategory.other, gate_sensitive=True,
                            model_scam=True)  # fmt: skip
    assert many.tags[-1] is RT.scam_report and len(many.tags) == tg.MAX_TAGS
    # Code evidence keeps the model's order (and a likely scam fronts the tag).
    possible = tg.finalize_tags(["scam_report", "benefits_navigation"],
                                document_type=DT.other_notice, category=DocumentCategory.benefits,
                                gate_sensitive=True, scam_risk=ScamRisk.possible)  # fmt: skip
    assert possible.tags[0] is RT.scam_report


def _model_out(*, likely: bool, signals: list[str], kinds: list[RedFlagKind]) -> AnalysisModelOut:
    flags = [RedFlagOut(kind=k, text="Flag.", source_quote="p1b1", span_ids=["p1b1"], page=1)
             for k in kinds]  # fmt: skip
    fixture = STORE.get("scam_gift_card_letter")
    out = fixture.analysis_out("en") if fixture is not None else None
    assert out is not None
    return out.model_copy(update={"is_likely_scam": likely, "scam_signals": signals,
                                  "red_flags": flags})  # fmt: skip


def test_the_models_verdict_needs_one_of_its_own_scam_flags() -> None:
    """G1 review: a genuine Fairfax SNAP interview notice the small model called a scam
    (is_likely_scam, signals ['urgency_pressure'], no red flag, tags ['scam_report', …]) filled the
    whole preview with scam-report help. A bare verdict is no evidence (D-13)."""
    assert not tg.model_scam_verdict(
        _model_out(likely=True, signals=["urgency_pressure"], kinds=[])
    )
    assert not tg.model_scam_verdict(
        _model_out(likely=True, signals=[], kinds=[RedFlagKind.urgency_pressure])
    )
    assert not tg.model_scam_verdict(
        _model_out(likely=False, signals=[], kinds=[RedFlagKind.scam_payment_method])
    )
    for kind in (RedFlagKind.scam_payment_method, RedFlagKind.impersonation, RedFlagKind.notario):
        assert tg.model_scam_verdict(_model_out(likely=False, signals=["gift_card"], kinds=[kind]))
        assert tg.model_scam_verdict(_model_out(likely=True, signals=[], kinds=[kind]))


@pytest.mark.parametrize(
    "model", [["crisis"], ["scam_report"], ["domestic_violence"], ["trafficking", "poison"]]
)
def test_a_list_the_gates_empty_still_gets_the_tag_call(model: list[str]) -> None:
    """Issue 5: the pass that decides on the tag call is gated like the final one, so a model list
    made only of sensitive tags without evidence asks for the call instead of ending empty."""
    gated = tg.finalize_tags(model, document_type=DT.other_notice, category=DocumentCategory.other,
                             gate_sensitive=True, printed_text="Your account is past due.",
                             language="en", sample=True)  # fmt: skip
    assert gated.tags == [] and gated.needs_tag_call
    final = tg.finalize_tags(model, document_type=DT.other_notice, category=DocumentCategory.other,
                             gate_sensitive=True, printed_text="Your account is past due.",
                             language="en", sample=True,
                             tag_call_tags=["benefits_navigation"])  # fmt: skip
    assert final.tags == [RT.benefits_navigation] and final.source == "tag_call"
