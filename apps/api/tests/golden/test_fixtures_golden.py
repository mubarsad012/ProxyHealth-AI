"""Golden set (D-16; BUILD_PLAN §5.8 step 5 and Appendix D; PRODUCT_SPEC §12.3).

For every fixture × recorded language: the recorded output validates, every quote is verbatim on
the page (WP2's ``verify.py`` rejects nothing), no prose carries a contact that is not printed,
and ``run_analysis`` / ``run_troubleshoot`` through the mock return a valid result with the
expected readability, demand count and single model call. The Appendix D urgency / date-kind /
scam / fixed-notice / clerk expectations need WP2's §11 pipeline modules and are marked
``xfail(strict=False)`` until those modules exist on disk; the resource-order checks call WP3's
matcher directly.
"""

from pathlib import Path

import pytest

from proxyhealth_api.analysis.transcript import assemble_transcript
from proxyhealth_api.analysis.verify import normalize, verify_demands, verify_red_flags
from proxyhealth_api.contracts.enums import DemandKind, DocumentType, ResourceTag, ScamRisk
from proxyhealth_api.contracts.model_out import AnalysisModelOut, TroubleshootModelOut
from proxyhealth_api.contracts.resources import ResourceMatchRequest
from proxyhealth_api.resources.matcher import match
from tests.golden._fixtures_wp7 import (
    RESOURCES,
    RULES,
    WP2_PIPELINE,
    DepsUnavailable,
    analyze,
    cases,
    contacts_in,
    digits,
    document_cases,
    fixture,
    screenshot_cases,
    troubleshoot,
)

needs_wp2 = pytest.mark.xfail(
    not WP2_PIPELINE, reason="needs WP2 §11 pipeline modules (urgency, deadline_rules, scam, "
    "fixed_notices, clerk, contacts_filter)", strict=False,
)  # fmt: skip


def analysis_out(fid: str, lang: str) -> AnalysisModelOut:
    out = fixture(fid).analysis_out(lang)
    assert out is not None, (fid, lang)
    return out


@pytest.mark.parametrize(("fid", "lang"), cases())
def test_recorded_output_quotes_are_verbatim(fid: str, lang: str) -> None:
    fx = fixture(fid)
    corpus = normalize(fx.transcript)
    out = fx.out(lang)
    if isinstance(out, TroubleshootModelOut):
        assert all(normalize(s) in corpus for s in out.screen_text)
        assert all(s.ui_target_as_written in out.screen_text for s in out.steps
                   if s.ui_target_as_written)  # fmt: skip
        assert out.error_text_quoted is None or normalize(out.error_text_quoted) in corpus
        return
    assert isinstance(out, AnalysisModelOut)
    transcript = assemble_transcript(out.blocks, pages_received=fx.manifest.pages)
    checked = verify_demands(out.demands, transcript)
    assert checked.facts_rejected == 0, [d.verification_note for d in checked.unverified]
    assert all(normalize(d.source_quote) in corpus for d in out.demands)
    flags = verify_red_flags(out.red_flags, transcript)
    assert flags.facts_rejected == 0 and len(flags.flags) == len(out.red_flags)
    ids = {b.id for b in out.blocks}
    assert set(out.summary_span_ids) <= ids
    assert all(set(s.span_ids) <= ids for s in out.plan_steps)


@pytest.mark.parametrize(("fid", "lang"), cases())
def test_no_contact_in_prose_that_is_not_printed(fid: str, lang: str) -> None:
    fx = fixture(fid)
    printed = digits(fx.transcript)
    corpus = fx.transcript.casefold()
    out = fx.out(lang)
    if isinstance(out, AnalysisModelOut):
        prose = [out.summary_title, out.summary_body, out.summary_body_en, out.clerk_need_en]
        prose += [d.text for d in out.demands] + [s.text for s in out.plan_steps]
        prose += [g.explanation for g in out.glossary] + [r.text for r in out.red_flags]
        prose += list(out.questions_to_ask)
    else:
        assert isinstance(out, TroubleshootModelOut)
        prose = [out.screen_summary, out.error_meaning, *out.cautions, *(s.text for s in out.steps)]
    for text in prose:
        for hit in contacts_in(text):
            ok = digits(hit) in printed if digits(hit) else hit.casefold() in corpus
            assert ok, (fid, lang, hit)


def expecting(key: str) -> list[str]:
    return sorted({fid for fid, _ in document_cases() if key in fixture(fid).expected})


@pytest.mark.parametrize("fid", expecting("glossary_terms"))
def test_glossary_terms_are_explained_and_printed(fid: str) -> None:
    # Appendix D: W-2 glossary has EIN + "Federal income tax withheld"; the label has a glossary.
    fx = fixture(fid)
    out = analysis_out(fid, "en")
    terms = {g.term_as_written for g in out.glossary}
    corpus = normalize(fx.transcript)
    for term in fx.expected["glossary_terms"]:
        assert term in terms, (fid, term, terms)
        assert normalize(term) in corpus, (fid, term)
    assert all(g.explanation.strip() for g in out.glossary)


@pytest.mark.parametrize("fid", expecting("bring_list"))
def test_bring_list_is_a_document_requested_demand(fid: str) -> None:
    # Appendix D: snap_interview_notice has a "documents" bring list in every recorded language.
    fx = fixture(fid)
    corpus = normalize(fx.transcript)
    for lang in fx.languages:
        by_id = {d.id: d for d in analysis_out(fid, lang).demands}
        for demand_id, minimum in fx.expected["bring_list"].items():
            demand = by_id[demand_id]
            assert demand.kind == DemandKind.document_requested, (lang, demand.kind)
            assert len(demand.documents) >= minimum, (lang, demand.documents)
            assert all(normalize(doc) in corpus for doc in demand.documents), lang


@pytest.mark.parametrize("fid", expecting("fixed_severity"))
def test_fixed_red_flags_have_expected_severity(fid: str) -> None:
    # Appendix D: fixed.uscis_receipt_i765 and fixed.jury_summons are `high` fixed red flags.
    exp = fixture(fid).expected
    notices = {n.fixed_copy_key: n for n in RULES.all_fixed_notices()}
    for key in exp["fixed_keys"]:
        assert key in notices, key
        assert notices[key].severity == exp["fixed_severity"], (key, notices[key].severity)
        assert fixture(fid).manifest.document_type in notices[key].document_types or (
            not notices[key].document_types
        ), (key, notices[key].document_types)


@pytest.mark.parametrize(("fid", "lang"), document_cases())
async def test_pipeline_result_shape(fid: str, lang: str, tmp_path: Path) -> None:
    fx = fixture(fid)
    try:
        result, calls = await analyze(fx, lang, tmp_path)
    except DepsUnavailable as exc:
        pytest.xfail(f"PipelineDeps needs {exc} (WP2 in progress)")
    exp = fx.expected
    assert result.document_type == fx.manifest.document_type
    assert result.quality.readable is exp.get("readable", True)
    assert result.model_meta.demo is True and result.model_meta.provider == "mock"
    assert result.verification.facts_rejected == 0
    assert len(result.demands) == exp.get("demands_count", len(result.demands))
    assert result.unverified == []
    if "model_calls" in exp:
        assert calls == exp["model_calls"]


@needs_wp2
@pytest.mark.parametrize(("fid", "lang"), document_cases())
async def test_appendix_d_expectations(fid: str, lang: str, tmp_path: Path) -> None:
    fx = fixture(fid)
    try:
        result, _ = await analyze(fx, lang, tmp_path)
    except DepsUnavailable as exc:
        pytest.xfail(f"PipelineDeps needs {exc} (WP2 in progress)")
    exp = fx.expected
    assert result.urgency.level in exp["urgency_level"]
    if "nearest_date_iso" in exp:
        assert result.urgency.nearest_date_iso == exp["nearest_date_iso"]
    by_id = {d.id: d for d in result.demands}
    for demand_id, kind in (exp.get("date_kinds") or {}).items():
        info = by_id[demand_id].date
        assert info is not None and info.kind == kind, (demand_id, info)
    for demand_id, rule_id in (exp.get("rule_ids") or {}).items():
        info = by_id[demand_id].date
        assert info is not None and info.rule_id == rule_id and info.formula
        assert info.rule_source_url
    assert result.scam_risk == exp.get("scam_risk", "none")
    fixed = {r.fixed_copy_key for r in result.red_flags if r.fixed_copy_key}
    assert set(exp.get("fixed_keys", [])) <= fixed
    if "fixed_severity" in exp:
        wanted = set(exp.get("fixed_keys", []))
        severities = {r.severity for r in result.red_flags if r.fixed_copy_key in wanted}
        assert severities == {exp["fixed_severity"]}, severities
    kinds = {r.kind for r in result.red_flags}
    assert set(exp.get("red_flag_kinds", [])) <= kinds
    for demand_id, minimum in (exp.get("bring_list") or {}).items():
        assert by_id[demand_id].kind == DemandKind.document_requested
        assert len(by_id[demand_id].documents) >= minimum
    terms = {g.term_as_written for g in result.glossary}
    if lang == "en":
        assert set(exp.get("glossary_terms", [])) <= terms
    if "disclaimer_kind" in exp:
        assert result.disclaimer_kind == exp["disclaimer_kind"]
    assert set(exp.get("clerk_appended_keys", [])) <= set(result.clerk_message.appended_line_keys)
    if "verify_resource_id" in exp:
        assert result.urgency.verify_resource_id == exp["verify_resource_id"]
    assert set(exp.get("warnings_include", [])) <= set(result.warnings)
    if "detected_language" in exp:
        assert result.detected_language == exp["detected_language"]
    if "resource_tags_first" in exp:
        assert result.resource_tags and result.resource_tags[0] == exp["resource_tags_first"]
    assert set(exp.get("resource_tags_include", [])) <= set(result.resource_tags)
    assert result.verification.contacts_stripped == 0


@pytest.mark.parametrize(("fid", "lang"), screenshot_cases())
async def test_troubleshoot_golden(fid: str, lang: str, tmp_path: Path) -> None:
    fx = fixture(fid)
    try:
        result = await troubleshoot(fx, lang, tmp_path)
    except DepsUnavailable as exc:
        pytest.xfail(f"PipelineDeps needs {exc} (WP2 in progress)")
    exp = fx.expected
    targets = [s.ui_target_as_written for s in result.steps if s.ui_target_as_written]
    assert targets == exp["steps_targets"]
    assert any(exp["caution_mentions"] in c for c in result.cautions)
    assert result.safety.emergency is exp["emergency"]
    assert result.scam_risk == exp["scam_risk"]


# --- resource expectations, checked against WP3's matcher and rules directly -----------------


def match_for(fid: str, scam_risk: ScamRisk = ScamRisk.none) -> list[str]:
    fx = fixture(fid)
    out = analysis_out(fid, "en")
    req = ResourceMatchRequest(
        tags=[ResourceTag(t) for t in out.resource_tags], document_type=out.document_type,
        category=out.category, state=fx.expected.get("state"), language="en",
        institutions_as_written=list(out.institutions_as_written), scam_risk=scam_risk,
    )  # fmt: skip
    response = match(req, RESOURCES)
    return [m.resource.id for m in response.results]


def test_inova_financial_assistance_first_in_virginia() -> None:
    assert match_for("inova_final_notice")[0] == "inova_fa"


def test_scam_letter_reporting_resources_first() -> None:
    # Appendix D "DHS OIG + FTC first": both lead the list; WP3's category bonus may slot the
    # USCIS scam page between them (RESOURCE_DB §12.2), which the demo script allows.
    ids = match_for("scam_gift_card_letter", ScamRisk.likely)
    assert ids[0] == "dhs_oig" and "ftc_reportfraud" in ids[:3], ids[:4]


def test_rfe_prepare_items() -> None:
    items = RULES.prepare_items(DocumentType.uscis_rfe)
    assert {"bring_notice", "bring_receipt_number"} <= set(items)


@pytest.mark.parametrize(
    ("fid", "resource_id"),
    [("school_immunization_notice", "cdc_iis"), ("irs_cp_notice", "irs_notice_lookup"),
     ("w2_form", "irs_itin")],
)  # fmt: skip
def test_expected_resource_in_preview(fid: str, resource_id: str) -> None:
    assert resource_id in match_for(fid)


# --- Appendix D urgency / date kinds / scam through WP2's validators, composed directly --------


@pytest.mark.parametrize("fid", sorted({fid for fid, _ in document_cases()}))
def test_validators_compose_to_appendix_d(fid: str) -> None:
    """Runs verify → deadline_rules → urgency → scam on the English output without the pipeline,
    so the fixture data is checked against WP2's real validators before the pipeline is wired.
    An import/signature mismatch (WP2 still moving) xfails; a wrong level or kind fails."""
    fx = fixture(fid)
    out = analysis_out(fid, "en")
    try:
        from datetime import UTC, datetime, time

        from proxyhealth_api.analysis.deadline_rules import apply_deadline_rules, context_for
        from proxyhealth_api.analysis.scam import score_transcript
        from proxyhealth_api.analysis.urgency import compute_urgency

        transcript = assemble_transcript(out.blocks, pages_received=fx.manifest.pages)
        checked = verify_demands(out.demands, transcript)
        now = datetime.combine(fx.today, time(14, 0), tzinfo=UTC)
        ctx = context_for(
            document_type=out.document_type, rules=RULES.deadline_rules(), now=now,
            state=fx.expected.get("state"), language=out.detected_language,
            transcript_text=transcript.full_text,
        )  # fmt: skip
        demands = apply_deadline_rules(checked.verified, checked.sources, ctx, transcript)
        urgency = compute_urgency(
            out.document_type, out.category, demands, emergency=False, today=ctx.today
        ).urgency
        flags = verify_red_flags(out.red_flags, transcript).flags
        scam = score_transcript(
            transcript, document_type=out.document_type, sender_kind=out.sender_kind,
            sender_as_written=out.sender_as_written, model_flags=flags,
            model_signals=out.scam_signals, demands=demands,
        )  # fmt: skip
    except (ImportError, TypeError, AttributeError) as exc:
        pytest.xfail(f"WP2 validator API not settled: {exc!r}")
    exp = fx.expected
    assert urgency.level in exp["urgency_level"], urgency
    if "nearest_date_iso" in exp:
        assert urgency.nearest_date_iso == exp["nearest_date_iso"]
    if "verify_resource_id" in exp:
        assert urgency.verify_resource_id == exp["verify_resource_id"]
    kinds = {d.id: d.date.kind for d in demands if d.date is not None}
    for demand_id, kind in (exp.get("date_kinds") or {}).items():
        assert kinds.get(demand_id) == kind, (demand_id, kinds)
    assert scam.scam_risk == exp.get("scam_risk", "none"), scam.scam_reasons
