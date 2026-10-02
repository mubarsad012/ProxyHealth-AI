"""Deterministic outputs the ``MockProvider`` builds without a fixture (BUILD_PLAN §5.8 table).

* ``generic_unreadable()`` — no sample matched: ``document_type=unknown``, ``legibility=poor``,
  ``readable_reason="mock_no_match"``; the pipeline renders it as ``quality.readable=false``.
* ``generic_screen()`` — no sample screenshot matched: ``needs_human_help=true``, no steps.
* ``pseudo_analysis`` / ``pseudo_troubleshoot`` — a recorded English output for a target language
  that has no recording: every user-facing string gets a visible ``⟦tag⟧`` prefix (D-29) while
  quotes, block text, digits and English-only fields stay untouched.
* ``DOCUMENT_TYPE_TAGS`` — primary ``resource_tags`` per type (DOCUMENT_TAXONOMY §2) for task
  ``tag`` when no sample id is given.

English copy comes from the bundled ``en.json`` pack so the words match the rest of the app.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

from proxyhealth_api.contracts.analysis import GlossaryTerm
from proxyhealth_api.contracts.common import TranslatedPage
from proxyhealth_api.contracts.enums import (
    Confidence,
    DocumentCategory,
    DocumentType,
    Legibility,
    SenderKind,
)
from proxyhealth_api.contracts.model_out import (
    AnalysisModelOut,
    DemandOut,
    PlanStepOut,
    RedFlagOut,
    TroubleshootModelOut,
)
from proxyhealth_api.contracts.troubleshoot import TroubleshootStep
from proxyhealth_api.settings import DATA_DIR

EN_PACK_PATH = DATA_DIR / "langpacks" / "en.json"
NO_MATCH_REASON = "mock_no_match"
GENERIC_CLERK_NEED = "reading a paper I got"

# DOCUMENT_TAXONOMY §2 "Primary resource_tags" (conditional extras left to the matcher).
DOCUMENT_TYPE_TAGS: dict[DocumentType, list[str]] = {
    DocumentType.uscis_receipt: ["immigration_legal_help"],
    DocumentType.uscis_rfe: ["immigration_legal_help"],
    DocumentType.uscis_noid: ["immigration_legal_help"],
    DocumentType.uscis_biometrics: ["immigration_legal_help"],
    DocumentType.uscis_interview: ["immigration_legal_help"],
    DocumentType.uscis_approval: ["immigration_legal_help"],
    DocumentType.uscis_denial: ["immigration_legal_help"],
    DocumentType.ead_related: ["work_permit", "immigration_legal_help"],
    DocumentType.green_card_related: ["green_card", "immigration_legal_help"],
    DocumentType.tps_related: ["daca_tps", "work_permit", "immigration_legal_help"],
    DocumentType.asylum_fee_notice: ["asylum", "immigration_legal_help"],
    DocumentType.parole_related: ["refugee_services", "immigration_legal_help"],
    DocumentType.ice_checkin: ["removal_proceedings", "immigration_legal_help"],
    DocumentType.nta: ["removal_proceedings", "court_notice", "change_of_address"],
    DocumentType.hearing_notice: ["removal_proceedings", "court_notice", "change_of_address"],
    DocumentType.ij_decision: ["removal_proceedings", "immigration_legal_help"],
    DocumentType.bia_notice: ["removal_proceedings", "immigration_legal_help"],
    DocumentType.traffic_court: ["traffic_court", "immigration_legal_help"],
    DocumentType.medical_bill: ["medical_bill", "charity_care"],
    DocumentType.eob: ["medical_bill"],
    DocumentType.insurance_denial: ["insurance_denial"],
    DocumentType.prior_auth: ["insurance_denial"],
    DocumentType.lab_result: ["lab_results", "primary_care_uninsured"],
    DocumentType.prescription_label: ["prescription_help", "language_access"],
    DocumentType.discharge_instructions: ["primary_care_uninsured", "language_access"],
    DocumentType.vaccine_record: ["vaccine_records", "school_enrollment"],
    DocumentType.appointment_reminder: ["language_access"],
    DocumentType.medicaid_renewal: ["medicaid_renewal", "benefits_navigation"],
    DocumentType.snap_notice: ["snap", "food", "benefits_navigation"],
    DocumentType.wic_notice: ["wic", "food"],
    DocumentType.ssa_letter: ["ssa_benefits", "benefits_navigation"],
    DocumentType.pay_or_quit: ["eviction", "housing_counseling", "rent_assistance"],
    DocumentType.eviction_summons: ["eviction", "housing_counseling"],
    DocumentType.lease: ["housing_counseling"],
    DocumentType.rent_increase: ["housing_counseling", "rent_assistance"],
    DocumentType.utility_shutoff: ["utility_shutoff", "rent_assistance"],
    DocumentType.school_enrollment: ["school_enrollment", "homeless_students"],
    DocumentType.immunization_notice: ["vaccine_records", "school_enrollment"],
    DocumentType.school_meals: ["school_meals", "food"],
    DocumentType.report_card: ["language_access"],
    DocumentType.offer_letter: ["workers_rights"],
    DocumentType.pay_stub: ["wage_theft", "workers_rights"],
    DocumentType.irs_notice: ["tax_notice"],
    DocumentType.itin: ["itin", "tax_notice"],
    DocumentType.jury_summons: ["jury_summons"],
    DocumentType.section8_recert: ["housing_counseling"],
    DocumentType.iep_504_notice: ["special_education"],
    DocumentType.w2_1099: ["tax_notice", "itin"],
    DocumentType.i9: ["work_permit", "workers_rights"],
    DocumentType.other_notice: [],
    DocumentType.unknown: [],
}
@functools.cache
def en_strings(path: Path = EN_PACK_PATH) -> dict[str, str]:
    """The bundled English pack (read once; the file is committed, never user content)."""
    data = json.loads(path.read_text("utf-8"))
    return {str(k): str(v) for k, v in data.items()}


def en(key: str, fallback: str) -> str:
    return en_strings().get(key, fallback)


def generic_unreadable() -> AnalysisModelOut:
    """AI_PROMPTS §10.1 ``GENERIC_UNREADABLE`` — the page matched no sample paper."""
    line = en("state.sample_not_recognised", "I can only read sample papers in this mode.")
    return AnalysisModelOut(
        document_type=DocumentType.unknown, category=DocumentCategory.other,
        document_type_confidence=Confidence.low, sender_as_written=None,
        sender_kind=SenderKind.unknown, detected_language="und",
        translated_pages=[TranslatedPage(page=1, text="")],
        summary_title=line[:80], summary_body=line, summary_body_en=line, summary_span_ids=[],
        demands=[], plan_steps=[], glossary=[], red_flags=[], questions_to_ask=[],
        clerk_need_en=GENERIC_CLERK_NEED, emergency_terms_found=[], is_likely_scam=False,
        scam_signals=[], resource_tags=[], institutions_as_written=[], form_numbers=[],
        geo_state=None, geo_county=None, geo_city=None, geo_zip=None,
        legibility=Legibility.poor, readable_reason=NO_MATCH_REASON, blocks=[],
    )  # fmt: skip


def generic_screen() -> TroubleshootModelOut:
    """AI_PROMPTS §10.1 ``GENERIC_SCREEN`` — the screenshot matched no sample screen."""
    line = en("troubleshoot.mock_unrecognised", "Sample mode: I only know the sample screens.")
    return TroubleshootModelOut(
        screen_summary=line[:300], screen_text=[], error_text_quoted=None,
        error_meaning=line[:300], steps=[], cautions=[], asks_for_credentials_or_payment=False,
        is_likely_scam=False, scam_signals=[], needs_human_help=True, red_flags=[],
        resource_tags=[], confidence=Confidence.low,
    )  # fmt: skip


def marker(tag: str) -> str:
    return f"⟦{tag}⟧ "


def _mark(text: str, tag: str, cap: int) -> str:
    if not text:
        return text
    return (marker(tag) + text)[:cap]


def pseudo_analysis(out: AnalysisModelOut, tag: str) -> AnalysisModelOut:
    """Prefix every target-language string with ``⟦tag⟧`` (quotes and ``*_en`` untouched)."""
    demands = [
        DemandOut.model_validate(
            d.model_dump()
            | {
                "text": _mark(d.text, tag, 200),
                "ambiguity_note": _mark(d.ambiguity_note, tag, 160) if d.ambiguity_note else None,
            }
        )
        for d in out.demands
    ]
    steps = [
        PlanStepOut.model_validate(s.model_dump() | {"text": _mark(s.text, tag, 220)})
        for s in out.plan_steps
    ]
    glossary = [
        GlossaryTerm(term_as_written=g.term_as_written, explanation=_mark(g.explanation, tag, 400))
        for g in out.glossary
    ]
    flags = [
        RedFlagOut.model_validate(r.model_dump() | {"text": _mark(r.text, tag, 220)})
        for r in out.red_flags
    ]
    pages = [
        TranslatedPage(page=p.page, text=_mark(p.text, tag, 100_000)) for p in out.translated_pages
    ]
    return out.model_copy(
        update={
            "translated_pages": pages,
            "summary_title": _mark(out.summary_title, tag, 80),
            "summary_body": _mark(out.summary_body, tag, 400),
            "demands": demands,
            "plan_steps": steps,
            "glossary": glossary,
            "red_flags": flags,
            "questions_to_ask": [_mark(q, tag, 140) for q in out.questions_to_ask],
        }
    )


def pseudo_troubleshoot(out: TroubleshootModelOut, tag: str) -> TroubleshootModelOut:
    """Same marker rule for a screenshot output; ``screen_text`` stays exactly as shown."""
    steps = [
        TroubleshootStep(
            order=s.order, text=_mark(s.text, tag, 200), ui_target_as_written=s.ui_target_as_written
        )
        for s in out.steps
    ]
    flags = [
        RedFlagOut.model_validate(r.model_dump() | {"text": _mark(r.text, tag, 220)})
        for r in out.red_flags
    ]
    return out.model_copy(
        update={
            "screen_summary": _mark(out.screen_summary, tag, 300),
            "error_meaning": _mark(out.error_meaning, tag, 300),
            "steps": steps,
            "cautions": [_mark(c, tag, 400) for c in out.cautions],
            "red_flags": flags,
        }
    )


__all__ = [
    "DOCUMENT_TYPE_TAGS",
    "GENERIC_CLERK_NEED",
    "NO_MATCH_REASON",
    "en",
    "en_strings",
    "generic_screen",
    "generic_unreadable",
    "marker",
    "pseudo_analysis",
    "pseudo_troubleshoot",
]
