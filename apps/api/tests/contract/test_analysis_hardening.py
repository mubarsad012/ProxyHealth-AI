"""Phase 2B — ``POST /v1/analyze`` hardening through the real pipeline (ScriptedProvider).

Each test pins one audited finding: prose dates checked against the paper, unverified dates in
the banner, the display date preference, agency anti-fraud boilerplate, every model-authored
field through the contact filter, code-only notario flags, and the translated clerk card.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import FastAPI

from proxyhealth_api.ai.provider import Task
from proxyhealth_api.analysis import prose_dates
from proxyhealth_api.contracts.analysis import GlossaryTerm
from proxyhealth_api.contracts.enums import (
    Confidence,
    DocumentCategory,
    DocumentType,
    PlanStepKind,
    RedFlagKind,
    SenderKind,
)
from proxyhealth_api.contracts.model_out import AnalysisModelOut, PlanStepOut, RedFlagOut
from proxyhealth_api.demo.fixtures import SAMPLE_FOOTER
from proxyhealth_api.settings import Settings
from tests.contract.test_analyze import (
    STORE,
    analyze,
    body,
    demo_body,
    install,
    medicaid_out,
    page_b64,
    result_of,
)

NTA = "nta_hearing_date"
RFE = "uscis_rfe_87d"


def out_of(fid: str, lang: str = "en") -> AnalysisModelOut:
    out = STORE.get(fid).analysis_out(lang)  # type: ignore[union-attr]
    assert out is not None
    return out.model_copy(deep=True)


async def test_invented_dates_in_prose_never_reach_the_reader(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """D-11 / invariant #5: the summary, the demand sentence and the steps may only name the
    paper's dates (the verified value, a printed date, or today)."""
    out = out_of(NTA)
    out.demands[0].text = "Go to the immigration court on October 17, 2026 at 8:30 AM."
    out.summary_body = out.summary_body_en = (
        "This paper starts a case in immigration court. You must appear before a judge on "
        "October 17, 2026. You then have until November 30, 2026 to file your application."
    )
    out.plan_steps.append(
        PlanStepOut(
            id="s9", text="You have 30 days, until November 6, 2026, to send your answer.",
            kind=PlanStepKind.mail, resource_tags=[], span_ids=[], demand_id=None,
        )  # fmt: skip
    )
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body(NTA))
    shown = " ".join(
        [res.summary.body, res.summary.body_en, *(d.text for d in res.demands),
         *(s.text for s in res.plan_steps)]
    )  # fmt: skip
    for invented in ("October 17", "November 30", "November 6"):
        assert invented not in shown, invented
    assert res.demands[0].text == "Go to the immigration court on October 7, 2026 at 8:30 AM."
    assert res.demands[0].value_verbatim == "October 7, 2026" and res.demands[0].verified
    assert res.summary.body.startswith("This paper starts a case in immigration court.")
    assert res.verification.facts_rejected >= 4
    assert res.verification.facts_rejected <= res.verification.facts_checked
    step = next(s for s in res.plan_steps if s.id == "s9")
    assert prose_dates.SEE_PAPER_KEY in step.text or "date on the paper" in step.text


async def test_every_quote_failing_never_says_nothing_to_do(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """D-12: unverified dates may raise urgency up to medium; the RFE banner must not read
    "Nothing to do right now" while the summary states a deadline."""
    out = out_of(RFE)
    for d in out.demands:
        d.source_quote = "Response due 10/13/2026"  # not on the page (a skewed photo)
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body(RFE))
    assert res.demands == [] and len(res.unverified) == len(out.demands)
    assert res.urgency.headline_key == "urgency.medium.unverified_date"
    assert res.urgency.level == "medium" and res.urgency.verify_resource_id == "uscis_contact"


async def test_date_preference_never_moves_a_printed_court_date(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """A Dari reader who picks day-month-year still gets 10/07/2026 = October 7 on an NTA."""
    out = out_of(NTA)
    for b in out.blocks:
        b.text = b.text.replace("October 7, 2026", "10/07/2026")
    for d in out.demands:
        d.source_quote = d.source_quote.replace("October 7, 2026", "10/07/2026")
    out.demands[0].value_verbatim = out.demands[0].date_text = "10/07/2026"
    install(app, settings, analyze_single=lambda kw: out)
    prefs: dict[str, Any] = {"tone": "plain", "calendar_notes": [], "date_format": "dmy"}
    res = await analyze(client, demo_body(NTA, preferences=prefs))
    d1 = next(d for d in res.demands if d.id == "d1")
    assert d1.date is not None and d1.date.value_iso == "2026-10-07"
    assert res.urgency.nearest_date_iso == "2026-10-07"


async def test_agency_anti_fraud_line_keeps_a_real_rfe_an_rfe(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    out = out_of(RFE)
    last = out.blocks[-1]
    line = "Avoid scams: USCIS will never ask you to pay by Western Union, MoneyGram, PayPal, or gift cards."  # noqa: E501
    out.blocks.append(last.model_copy(update={"id": "p1b16", "text": line}))
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body(RFE))
    assert res.document_type == DocumentType.uscis_rfe and res.scam_risk == "none"
    assert res.urgency.verify_resource_id == "uscis_contact"
    assert not any(f.kind.value.startswith("scam") for f in res.red_flags)


async def test_every_model_authored_field_passes_the_contact_filter(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """D-10 / invariant #4: translation, sender line, documents, notes and glossary terms too."""
    out = medicaid_out()
    out.translated_pages[0].text += (
        " For help call 1-866-555-0123 or go to www.medicaid-renew-now.com."
    )
    out.demands[0].documents = [
        "Proof of address: call 1-888-555-0199 or visit www.fast-medicaid-help.com"
    ]
    out.demands[0].ambiguity_note = "Call (202) 555-0147 to confirm."
    out.sender_as_written = "Virginia Medicaid Helpline 1-877-555-0100 www.va-medicaid-fast.com"
    out.glossary.append(GlossaryTerm(term_as_written="www.renewhelp.net", explanation="A site."))
    out.questions_to_ask = ["You qualify for this, right?"]
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body())
    dump = res.model_dump_json()
    for invented in ("555-0123", "medicaid-renew-now", "555-0199", "fast-medicaid-help",
                     "555-0147", "555-0100", "va-medicaid-fast", "renewhelp"):  # fmt: skip
        assert invented not in dump, invented
    assert res.sender_as_written is None and "Medicaid" in res.clerk_message.english
    assert res.demands[0].documents and "Proof of address" in res.demands[0].documents[0]
    assert all("You qualify" not in q for q in res.questions_to_ask)
    assert res.verification.contacts_stripped >= 5


async def test_code_only_notario_gets_the_fixed_card(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """D-20: the scam scorer's notario regex alone brings "A notario is not a lawyer"."""
    out = out_of("scam_gift_card_letter")
    texts = [
        "Maria Lopez, Notario Publico",
        "We prepare your immigration papers quickly.",
        "Call our office for an appointment.",
    ]
    out.blocks = [b.model_copy(update={"text": x}) for b, x in zip(out.blocks, texts, strict=False)]
    out.red_flags, out.demands, out.glossary = [], [], []
    out.sender_as_written, out.sender_kind = "Maria Lopez", SenderKind.unknown
    out.document_type, out.category = DocumentType.other_notice, DocumentCategory.immigration
    out.translated_pages[0].text = "\n".join(texts)
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body("scam_gift_card_letter"))
    assert "scam.notario" in res.scam_reasons
    keys = {f.fixed_copy_key for f in res.red_flags}
    assert "fixed.notario_not_a_lawyer" in keys


async def test_failed_clerk_translation_uses_the_dari_generic_card(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """CL-055(c): a prs reader gets the pack's Dari card around the English need line."""
    provider = install(app, settings, clerk_translate=lambda kw: result_of(None))
    res = await analyze(client, demo_body(target_language="prs"))
    assert Task.clerk_translate in provider.tasks()
    assert res.clerk_message.translated.startswith("سلام. من به")
    assert res.clerk_message.english.startswith("Hello. I speak")
    assert "translation_partial" in res.warnings


# --- small-model sweep findings: scam scoring, the SAMPLE footer, type/category, tags ----------
# The outputs below rebuild, on the curated fixtures, what qwen3.5:4b returned for the synthetic
# samples (the same quotes, flag texts and steps) — no live output is committed.

TRAFFIC = "traffic_court_notice"
IRS = "irs_cp_notice"
SNAP = "snap_interview_notice"


def with_footer(out: AnalysisModelOut) -> AnalysisModelOut:
    """The fixture output plus the SAMPLE footer block every rendered sample page prints."""
    last = out.blocks[-1]
    footer = last.model_copy(update={
        "id": f"p1b{len(out.blocks) + 1}", "text": SAMPLE_FOOTER, "bbox": [0.25, 0.97, 0.75, 0.99],
    })  # fmt: skip
    out.blocks.append(footer)
    return out


def footer_flags(block_id: str) -> list[RedFlagOut]:
    return [
        RedFlagOut(kind=RedFlagKind.impersonation, source_quote=SAMPLE_FOOTER, span_ids=[block_id],
                   text="The paper uses the name of a court but says it is fake.", page=1),
        RedFlagOut(kind=RedFlagKind.scam_payment_method, source_quote=SAMPLE_FOOTER,
                   span_ids=[block_id], text="This paper says it is a sample.", page=1),
    ]  # fmt: skip


def footer_traffic() -> AnalysisModelOut:
    out = with_footer(out_of(TRAFFIC))
    footer_id = out.blocks[-1].id
    out.red_flags = footer_flags(footer_id)
    out.plan_steps.append(PlanStepOut(
        id="s9", text="If the paper says it is a sample, do not pay or go to court.",
        kind=PlanStepKind.wait, resource_tags=[], span_ids=[footer_id], demand_id=None,
    ))  # fmt: skip
    out.resource_tags = ["scam_report", "court_notice", "traffic_court"]
    return out


async def test_the_sample_footer_is_no_part_of_a_demo_paper(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """F2/CQ-9: no flag, step, scam signal or scam tag rests on "Not a real letter"."""
    install(app, settings, analyze_single=lambda kw: footer_traffic())
    res = await analyze(client, demo_body(TRAFFIC))
    assert res.document_type == DocumentType.traffic_court and res.scam_risk == "none"
    assert not any(f.kind in ("impersonation", "scam_payment_method") for f in res.red_flags)
    assert all("sample" not in s.text for s in res.plan_steps) and len(res.plan_steps) == 3
    assert "scam_report" not in res.resource_tags


async def test_a_real_upload_keeps_every_flag_that_has_evidence(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings, consent_headers: dict[str, str]
) -> None:
    """Real uploads are never samples: the footer filter is off (an impersonation flag still
    counts), while a payment flag that quotes no payment request is rejected everywhere."""
    install(app, settings, analyze_single=lambda kw: footer_traffic())
    page = {"mime_type": "image/png", "data_base64": page_b64(TRAFFIC)}
    res = await analyze(client, body(pages=[page]), headers=consent_headers)
    kinds = [f.kind for f in res.red_flags]
    assert "impersonation" in kinds and "scam_payment_method" not in kinds
    assert res.scam_risk == "possible" and res.verification.facts_rejected >= 1
    assert any("sample" in s.text for s in res.plan_steps)


async def test_an_irs_payment_line_keeps_a_real_cp14_an_irs_notice(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """F1/CQ-1: the model's own "It does not ask for gift cards" is no gift-card demand, and a
    payment flag on the agency's .gov payment line neither scores nor shows."""
    out = out_of(IRS)
    install(app, settings, analyze_single=lambda kw: out)
    base = await analyze(client, demo_body(IRS))
    out = out_of(IRS)
    out.red_flags = [RedFlagOut(
        kind=RedFlagKind.scam_payment_method, span_ids=["p1b11"], page=1,
        source_quote="Pay online at irs.gov/payments or mail a check with the payment stub below.",
        text="This paper says to pay online or by mail. It does not ask for gift cards, wire "
             "transfers, or crypto.",
    )]  # fmt: skip
    out.plan_steps.append(PlanStepOut(
        id="s4", text="If you did not pay, go to the IRS website or mail a check.",
        kind=PlanStepKind.submit_online, resource_tags=[], span_ids=["p1b11"], demand_id=None,
    ))  # fmt: skip
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body(IRS))
    assert res.document_type == DocumentType.irs_notice and res.document_type_confidence == "high"
    assert res.scam_risk == "none" and res.scam_reasons == []
    assert {"call", "submit_online"} <= {s.kind for s in res.plan_steps}
    assert not any(f.kind == "scam_payment_method" for f in res.red_flags)
    assert res.verification.facts_rejected == base.verification.facts_rejected + 1
    assert "scam_report" not in res.resource_tags


async def test_a_retyped_scam_paper_is_low_confidence(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """§6.5: a likely scam on an agency type becomes other_notice with confidence low."""
    out = out_of("scam_gift_card_letter")
    out.document_type, out.document_type_confidence = DocumentType.uscis_receipt, Confidence.high
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body("scam_gift_card_letter"))
    assert res.scam_risk == "likely" and res.document_type == DocumentType.other_notice
    assert res.document_type_confidence == "low" and res.category == DocumentCategory.immigration


async def test_a_snap_heading_upgrades_other_notice(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """F3/F6: "Notice of Interview" + SNAP → snap_notice; an unbacked scam_report tag goes."""
    out = out_of(SNAP)
    out.document_type, out.document_type_confidence = DocumentType.other_notice, Confidence.low
    out.category, out.resource_tags = DocumentCategory.other, ["scam_report"]
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body(SNAP))
    assert res.document_type == DocumentType.snap_notice
    assert res.document_type_confidence == "medium" and res.category == DocumentCategory.benefits
    assert res.disclaimer_kind == "benefits_information_only"
    assert res.resource_tags == ["snap", "food", "benefits_navigation"]


async def test_a_snap_themed_gift_card_scam_is_not_upgraded(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """A type the code chose never survives a likely scam (§3.11)."""
    out = out_of(SNAP)
    out.document_type, out.document_type_confidence = DocumentType.other_notice, Confidence.low
    out.blocks[5].text = "Pay the $50 interview fee today with Google Play gift cards."
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body(SNAP))
    assert res.scam_risk == "likely" and res.document_type == DocumentType.other_notice
    assert res.document_type_confidence == "low"


async def test_the_type_fixes_the_category_and_the_disclaimer(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """F4/CQ-7: TAXONOMY §2 gives medicaid_renewal benefits and w2_1099 employment."""
    medical = medicaid_out(category=DocumentCategory.medical)
    install(app, settings, analyze_single=lambda kw: medical)
    res = await analyze(client, demo_body())
    assert res.category == DocumentCategory.benefits
    assert res.disclaimer_kind == "benefits_information_only"
    w2 = out_of("w2_form")
    w2.category = DocumentCategory.tax
    w2.form_numbers = ["Form W-2 Wage and Tax Statement 2025"]
    install(app, settings, analyze_single=lambda kw: w2)
    res = await analyze(client, demo_body("w2_form"))
    assert res.category == DocumentCategory.employment
    assert res.disclaimer_kind == "legal_information_only"
    assert res.entities.form_numbers == ["W-2"], "F7: the printed number, not the model's label"


async def test_long_form_labels_still_bring_the_form_tag_and_card(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    out = out_of("uscis_i797c_receipt_i765")
    out.form_numbers = ["I-797C, Notice of Action", "Form I-765, Application for Employment "
                        "Authorization"]  # fmt: skip
    out.resource_tags = []
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body("uscis_i797c_receipt_i765"))
    assert res.entities.form_numbers == ["I-797C", "I-765"]
    assert "work_permit" in res.resource_tags
    assert any(f.kind == "ead_receipt_not_work_authorization" for f in res.red_flags)


async def test_an_unreadable_paper_is_unknown(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """F5 / TAXONOMY §3.11: whatever type the model guessed for a blurry page."""
    out = out_of("blurry_unreadable_page")
    out.document_type, out.category = DocumentType.other_notice, DocumentCategory.tax
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body("blurry_unreadable_page"))
    assert res.quality.readable is False
    assert res.document_type == DocumentType.unknown and res.category == DocumentCategory.other
    assert res.disclaimer_kind == "general_information" and res.resource_tags == []


async def test_crisis_tags_need_an_emergency(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """F6/CQ-6: no crisis, DV or trafficking resources for a pharmacy label without one."""
    out = out_of("prescription_label")
    out.resource_tags = ["prescription_help", "primary_care_uninsured", "language_access",
                         "crisis", "domestic_violence", "trafficking"]  # fmt: skip
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body("prescription_label"))
    assert res.safety.emergency is False
    assert res.resource_tags == ["prescription_help", "primary_care_uninsured", "language_access"]
