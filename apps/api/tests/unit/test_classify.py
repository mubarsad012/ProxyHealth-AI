"""``analysis/classify.py`` — code checks on what the paper is (DOCUMENT_TAXONOMY §2, §3 rule 16).

A small local model fell back to ``other_notice`` on a SNAP interview notice whose heading reads
"Notice of Interview"; a USCIS receipt and an IRS CP14 lost their types to the scam scorer; the
model's category disagreed with the §2 table on a Medicaid letter and a W-2. These tests pin the
deterministic corrections and, above all, what they must never do: replace a specific type the
model chose on anything but a printed form label (never a sentence that mentions a form, never a
floor-protected type), let a later page or another paper decide, or touch a curated fixture.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

from proxyhealth_api.analysis import classify as cl
from proxyhealth_api.analysis.transcript import Transcript, assemble_transcript
from proxyhealth_api.contracts.analysis import RedFlag
from proxyhealth_api.contracts.common import TextBlock
from proxyhealth_api.contracts.enums import (
    Confidence,
    DocumentCategory,
    DocumentType,
    PlanStepKind,
    RedFlagKind,
    ScamRisk,
    Severity,
)
from proxyhealth_api.contracts.model_out import AnalysisModelOut, PlanStepOut, RedFlagOut
from proxyhealth_api.demo.fixtures import SAMPLE_FOOTER, FixtureStore
from proxyhealth_api.settings import DATA_DIR
from tests.unit._fixtures_wp2 import block

DT = DocumentType
DC = DocumentCategory
STORE = FixtureStore.load(DATA_DIR / "fixtures")
TAXONOMY = Path(__file__).resolve().parents[4] / "docs" / "DOCUMENT_TAXONOMY.md"


def top(i: int) -> list[float]:
    """A bbox whose top edge sits ``i`` tenths down the page."""
    return [0.1, i / 10, 0.9, i / 10 + 0.05]


def lines(*texts: str) -> list[TextBlock]:
    """Blocks ``p1b1`` … in reading order, each one tenth further down the page."""
    return [block(f"p1b{i}", text, bbox=top(i - 1)) for i, text in enumerate(texts, 1)]


def reading(
    blocks: list[TextBlock],
    document_type: DocumentType = DT.other_notice,
    confidence: Confidence = Confidence.low,
    category: DocumentCategory = DC.other,
) -> tuple[AnalysisModelOut, Transcript]:
    base = STORE.get("medicaid_address_confirmation").analysis_out("en")  # type: ignore[union-attr]
    assert base is not None
    out = base.model_copy(update={
        "blocks": blocks, "document_type": document_type, "document_type_confidence": confidence,
        "category": category,
    })  # fmt: skip
    return out, assemble_transcript(blocks, pages_received=1)


def check(blocks: list[TextBlock], *args: object) -> cl.TypeCheck:
    out, paper = reading(blocks, *args)  # type: ignore[arg-type]
    return cl.check_document_type(out, paper)


# --- Tier A: a printed form label (§3.1, §3.2, §3.9) -------------------------------------------

@pytest.mark.parametrize(
    ("label", "expected"),
    [("Form I-862", DT.nta), ("I-797E, Notice of Action", DT.uscis_rfe),
     ("I-797A, Notice of Action", DT.uscis_approval), ("Form N-445", DT.uscis_interview),
     ("Form I-220A", DT.ice_checkin), ("Form W-2 Wage and Tax Statement 2025", DT.w2_1099),
     ("Form 1099-NEC", DT.w2_1099), ("Form I-9", DT.i9), ("Form W-7", DT.itin)],
)  # fmt: skip
def test_a_header_form_label_decides_the_type(label: str, expected: DocumentType) -> None:
    got = check(lines("Sample Office", label, "Please read this letter."))
    assert (got.document_type, got.confidence, got.rule) == (expected, Confidence.medium, "form")
    assert got.model_type is DT.other_notice


def test_a_form_number_outside_the_header_or_in_a_sentence_decides_nothing() -> None:
    body = [f"Paragraph {i}." for i in range(1, 5)]
    low = lines(*body, "Form I-862")  # block 5, top edge at 0.4
    assert check(low).rule is None
    sentence = "If you got a Form I-862 you may ask a lawyer for free help in your case today."
    assert check(lines("Legal Aid Flyer", sentence)).rule is None


def test_when_a_form_label_may_replace_a_specific_type() -> None:
    # The model was unsure: the label decides.
    got = check(lines("Form I-862", "Notice"), DT.hearing_notice, Confidence.low)
    assert (got.document_type, got.confidence, got.rule) == (DT.nta, Confidence.medium, "form")
    # The model was sure: only a strong label of a type in the same §2 category that keeps every
    # urgency protection (hearing_notice and nta share the floor and the critical hearing date) …
    approval = check(lines("USCIS", "I-797A, Notice of Action"), DT.uscis_receipt, Confidence.high)
    assert approval.document_type is DT.uscis_approval and approval.rule == "form"
    nta = check(lines("Form I-862", "Notice"), DT.hearing_notice, Confidence.high)
    assert (nta.document_type, nta.confidence) == (DT.nta, Confidence.medium)
    # … never one that loses a floor or a driving role, another category, or a bare number.
    assert cl.keeps_protections(DT.hearing_notice, DT.nta)
    assert not cl.keeps_protections(DT.uscis_noid, DT.uscis_rfe)  # the high floor
    assert not cl.keeps_protections(DT.eviction_summons, DT.w2_1099)
    assert not cl.keeps_protections(DT.i9, DT.w2_1099)  # response_due, expiry
    assert check(lines("Form I-9"), DT.w2_1099, Confidence.high).document_type is DT.i9
    assert check(lines("Form W-2"), DT.i9, Confidence.high).rule is None
    assert check(lines("Form W-2"), DT.medicaid_renewal, Confidence.medium).rule is None
    stub = lines("Sample Staffing LLC", "W-2 Wages", "Earnings Statement")
    assert check(stub, DT.pay_stub, Confidence.high).rule is None
    assert check(stub, DT.pay_stub, Confidence.low).document_type is DT.w2_1099
    # Two labels that disagree decide nothing.
    assert check(lines("Form I-862", "Form W-2"), DT.lease, Confidence.low).rule is None


def test_form_label_shape() -> None:
    assert cl.form_label("Form I-862") == cl.FormLabel("I862", strong=True)
    assert cl.form_label("I-797C, Notice of Action") == cl.FormLabel("I797C", strong=True)
    assert cl.form_label("Notice CP14 Tax year 2025 Notice date: September 21, 2026") == (
        cl.FormLabel("CP14", strong=True)
    )
    assert cl.form_label("W-2 Wage and Tax Statement 2025") == cl.FormLabel("W2", strong=False)
    for mention in ("Bring Form W-2 and your ID.", "your W-2 or recent pay stubs,", "W-2 or stubs.",
                    "Form I-9 must be completed by your employer", "On day one, complete Form I-9",
                    "IOE0912345678 I765 - Application for Employment Authorization"):  # fmt: skip
        assert cl.form_label(mention) is None, mention


@pytest.mark.parametrize(
    ("texts", "doc_type", "category"),
    [
        (["Virginia Department of Medical Assistance Services", "Medicaid Renewal",
          "Send proof of income, such as\nyour W-2 or recent pay stubs,\nby November 1, 2026."],
         DT.medicaid_renewal, DC.benefits),
        (["Fairfax County Housing Authority", "Annual Recertification",
          "Bring Form W-2 and your ID.", "Your appointment is November 3, 2026."],
         DT.section8_recert, DC.housing),
        (["ACME Corp", "Offer of Employment", "On day one, complete Form I-9.",
          "Start date: November 3, 2026"], DT.offer_letter, DC.employment),
        (["GENERAL DISTRICT COURT", "SUMMONS FOR UNLAWFUL DETAINER",
          "Plaintiff seeks rent; bring Form W-2 if you claim hardship."],
         DT.eviction_summons, DC.housing),
        (["County DSS", "SNAP", "Notice of Interview", "Bring your W-2 or pay stubs."],
         DT.snap_notice, DC.benefits),
    ],
)  # fmt: skip
def test_a_header_sentence_that_mentions_a_form_is_no_label(
    texts: list[str], doc_type: DocumentType, category: DocumentCategory
) -> None:
    """Review of package B: a W-2 or I-9 mentioned in a page-1 sentence turned a Medicaid
    renewal, a recertification, an offer letter, an eviction summons and a SNAP notice into
    w2_1099/i9 (losing their urgency roles, floor and never-estimate rule)."""
    for confidence in Confidence:
        assert check(lines(*texts), doc_type, confidence, category).rule is None


def test_i797e_reads_its_heading_and_keeps_a_noid() -> None:
    """USCIS prints RFEs and NOIDs on I-797E alike; a NOID (floor high) never becomes an RFE."""
    noid = lines("U.S. Citizenship and Immigration Services", "I-797E, Notice of Action",
                 "Notice of Intent to Deny")  # fmt: skip
    assert check(noid, DT.uscis_noid, Confidence.high).rule is None
    assert check(noid).document_type is DT.uscis_noid
    assert check(noid, DT.uscis_rfe, Confidence.high).document_type is DT.uscis_noid
    bare = lines("USCIS", "I-797E, Notice of Action", "Please read this letter.")
    assert check(bare, DT.uscis_noid, Confidence.medium).rule is None
    assert check(bare, DT.uscis_noid, Confidence.low).rule is None
    assert check(bare).document_type is DT.uscis_rfe
    rfe = lines("USCIS", "I-797E, Notice of Action", "Request for Evidence")
    assert check(rfe, DT.uscis_noid, Confidence.high).rule is None


def test_i797c_reads_its_first_line_heading() -> None:
    receipt = check(lines("U.S. Citizenship and Immigration Services", "I-797C, Notice of Action",
                          "Notice Type: Receipt Notice"))  # fmt: skip
    assert receipt.document_type is DT.uscis_receipt and receipt.rule == "form"
    rejected = lines("USCIS", "I-797C, Notice of Action", "Notice Type: Rejection Notice")
    rejection = check(rejected, DT.uscis_receipt, Confidence.low)
    assert (rejection.document_type, rejection.confidence) == (DT.uscis_denial, Confidence.medium)
    # A receipt the model was sure of keeps its expiry role (an extension it may print).
    assert check(rejected, DT.uscis_receipt, Confidence.high).rule is None
    assert check(lines("USCIS", "I-797C, Notice of Action", "We received your case.")).rule is None


def test_cp_numbers_need_the_irs_name() -> None:
    irs = check(lines("Internal Revenue Service", "Notice CP14", "Balance due"))
    assert irs.document_type is DT.irs_notice
    assert check(lines("Sample Collections LLC", "Notice CP14", "Balance due")).rule is None
    assert check(lines("Internal Revenue Service", "Notice CP566")).document_type is DT.itin


# --- Tier B: a heading upgrades other_notice / unknown only ------------------------------------

def test_snap_notice_of_interview_needs_a_snap_cue() -> None:
    snap = check(lines("Sample County Department of Social Services",
                       "Supplemental Nutrition Assistance Program (SNAP)", "Notice of Interview",
                       "Your interview is by phone on October 9, 2026."))  # fmt: skip
    assert (snap.document_type, snap.confidence, snap.rule) == (
        DT.snap_notice, Confidence.medium, "heading"
    )
    uscis = check(lines("U.S. Citizenship and Immigration Services", "Notice of Interview"))
    assert uscis.rule is None


def test_notice_to_appear_needs_an_eoir_cue() -> None:
    eoir = check(lines("Executive Office for Immigration Review", "NOTICE TO APPEAR"))
    assert eoir.document_type is DT.nta and eoir.rule == "heading"
    assert check(lines("Sample County Police", "NOTICE TO APPEAR")).rule is None


def test_a_heading_never_replaces_a_specific_type_or_a_confident_other_notice() -> None:
    pay_or_quit = lines("Oak Hollow Property Management LLC", "14-DAY NOTICE TO PAY RENT OR QUIT")
    assert check(pay_or_quit).document_type is DT.pay_or_quit
    assert check(pay_or_quit, DT.lease, Confidence.medium).rule is None
    assert check(pay_or_quit, DT.other_notice, Confidence.high).rule is None
    assert check(pay_or_quit, DT.unknown, Confidence.low).document_type is DT.pay_or_quit
    assert check(lines("Form I-862"), DT.other_notice, Confidence.high).rule is None


def test_two_headings_of_different_types_decide_nothing() -> None:
    assert check(lines("Explanation of Benefits", "Disconnection Notice")).rule is None


def test_a_later_page_or_another_paper_never_types_the_upload() -> None:
    """Review of package B: an EOB stapled behind a bill made the bill an ``eob`` (and its fixed
    "this is not a bill" card). Headings count on page 1 only; ``[multiple_documents]`` stops
    every correction."""
    blocks = [
        block("p1b1", "Riverside Medical Group", bbox=top(0)),
        block("p1b2", "Balance due: $2,410.00. Please pay by November 30, 2026.", bbox=top(1)),
        block("p2b1", "Explanation of Benefits", page=2, bbox=top(0)),
        block("p2b2", "Acme Health Plan", page=2, bbox=top(1)),
    ]
    out, _ = reading(blocks, DT.other_notice, Confidence.medium, DC.medical)
    paper = assemble_transcript(blocks, pages_received=2)
    assert cl.check_document_type(out, paper).rule is None
    eob_first = [block("p1b1", "Explanation of Benefits", bbox=top(0)),
                 block("p1b2", "Acme Health Plan", bbox=top(1))]  # fmt: skip
    out, paper = reading(eob_first, DT.other_notice, Confidence.medium, DC.medical)
    assert cl.check_document_type(out, paper).document_type is DT.eob
    sentinel = RedFlagOut(kind=RedFlagKind.other, text="[multiple_documents]", source_quote=None,
                          span_ids=[], page=None)  # fmt: skip
    two = out.model_copy(update={"red_flags": [sentinel]})
    assert cl.check_document_type(two, paper).rule is None
    labelled = lines("Form I-862", "Notice")
    out, paper = reading(labelled)
    assert cl.check_document_type(out.model_copy(update={"red_flags": [sentinel]}),
                                  paper).rule is None  # fmt: skip


def test_only_short_first_lines_are_headings() -> None:
    long_line = "We are writing to tell you about your explanation of benefits for this month"
    assert check(lines("Sample Health Plan", long_line)).rule is None
    second_line = [block("p1b1", "Sample Health Plan\nExplanation of Benefits")]
    assert check(second_line).rule is None


@pytest.mark.parametrize(
    ("fid", "lang"),
    [(f.id, lang) for f in STORE.all() if f.kind == "document" for lang in f.languages],
)
def test_curated_fixtures_are_untouched_and_never_mistyped(fid: str, lang: str) -> None:
    out = STORE.get(fid).analysis_out(lang)  # type: ignore[union-attr]
    assert out is not None
    paper = assemble_transcript(out.blocks, pages_received=max([1, *(b.page for b in out.blocks)]))
    assert cl.check_document_type(out, paper).rule is None
    assert cl.apply_type_check(out, cl.check_document_type(out, paper)) == out
    forced = out.model_copy(update={"document_type": DT.other_notice,
                                    "document_type_confidence": Confidence.low})  # fmt: skip
    assert cl.check_document_type(forced, paper).document_type in {out.document_type,
                                                                   DT.other_notice}  # fmt: skip


def test_forced_other_notice_recovers_the_form_and_heading_fixtures() -> None:
    recovered = set()
    for fx in STORE.all():
        out = fx.analysis_out("en") if fx.kind == "document" else None
        if out is None or out.document_type in (DT.other_notice, DT.unknown):
            continue
        forced = out.model_copy(update={"document_type": DT.other_notice,
                                        "document_type_confidence": Confidence.low})  # fmt: skip
        paper = assemble_transcript(out.blocks, pages_received=1)
        if cl.check_document_type(forced, paper).document_type is out.document_type:
            recovered.add(fx.id)
    assert {"nta_hearing_date", "uscis_rfe_87d", "uscis_i797c_receipt_i765", "irs_cp_notice",
            "w2_form", "snap_interview_notice", "jury_summons", "va_pay_or_quit_14d"} <= recovered


# --- category from the type (§2) ----------------------------------------------------------------

def test_every_type_but_other_notice_fixes_its_category() -> None:
    assert set(cl.TYPE_CATEGORY) == set(DocumentType) - {DT.other_notice}
    assert cl.category_for(DT.medicaid_renewal, DC.medical) is DC.benefits
    assert cl.category_for(DT.w2_1099, DC.tax) is DC.employment
    assert cl.category_for(DT.other_notice, DC.immigration) is DC.immigration
    assert cl.category_for(DT.unknown, DC.tax) is DC.other


def test_type_category_matches_the_master_table() -> None:
    if not TAXONOMY.exists():
        pytest.skip("docs/ not shipped with this checkout")
    text = TAXONOMY.read_text("utf-8")
    master = text[text.index("## 2. Master table") : text.index("## 3. Classification rules")]
    rows = re.findall(r"^\| `(\w+)` \| (\w+) \|", master, re.MULTILINE)
    table = {DocumentType(t): c for t, c in rows if t in DocumentType.__members__}
    assert set(table) == set(DocumentType)
    for doc_type, category in table.items():
        if doc_type is not DT.other_notice:
            assert cl.TYPE_CATEGORY[doc_type].value == category, doc_type


def test_every_phrase_and_form_label_is_in_the_taxonomy() -> None:
    if not TAXONOMY.exists():
        pytest.skip("docs/ not shipped with this checkout")
    doc = TAXONOMY.read_text("utf-8").casefold()
    phrases = {p for p, _t, cues in cl.HEADINGS for p in (p, *cues)}
    phrases |= {p for table in cl.FORM_HEADINGS.values() for p, _t in table} | {cl.IRS_NAME}
    for phrase in phrases - {"i-797c", "i-797e"}:  # the I-797 cue variants: "I-797C"/"I-797E" below
        assert phrase in doc, phrase
    printed = {"I862": "I-862", "I797E": "I-797E", "I797A": "I-797A", "I797B": "I-797B",
               "N445": "N-445", "I220A": "I-220A", "I220B": "I-220B", "W2": "W-2",
               "1099NEC": "1099-NEC/MISC/K", "1099MISC": "1099-NEC/MISC/K",
               "1099K": "1099-NEC/MISC/K", "I9": "Form I-9", "W7": "W-7", "CP565": "CP565",
               "CP566": "CP566", "CP567": "CP567"}  # fmt: skip
    assert set(printed) == set(cl.FORM_TYPES)
    for key, spelled in printed.items():
        assert spelled.casefold() in doc, key
    assert "i-797c" in doc and "i-797e" in doc


def test_apply_type_check_sets_type_confidence_and_category() -> None:
    out, paper = reading(lines("Supplemental Nutrition Assistance Program (SNAP)",
                               "Notice of Interview"), category=DC.other)  # fmt: skip
    applied = cl.apply_type_check(out, cl.check_document_type(out, paper))
    assert applied.document_type is DT.snap_notice and applied.category is DC.benefits
    assert applied.document_type_confidence is Confidence.medium
    medicaid, paper = reading(lines("Medicaid"), DT.medicaid_renewal, Confidence.high, DC.medical)
    fixed = cl.apply_type_check(medicaid, cl.check_document_type(medicaid, paper))
    assert fixed.category is DC.benefits and fixed.document_type_confidence is Confidence.high


# --- after the scam scorer (§3.11, §6.5) --------------------------------------------------------

def test_a_code_upgraded_type_never_survives_a_likely_scam() -> None:
    out, paper = reading(lines("Supplemental Nutrition Assistance Program (SNAP)",
                               "Notice of Interview", "Pay the $50 fee with gift cards today."),
                         category=DC.benefits)  # fmt: skip
    type_check = cl.check_document_type(out, paper)
    upgraded = cl.apply_type_check(out, type_check)
    assert upgraded.document_type is DT.snap_notice
    final, doc_type = cl.after_scam(upgraded, type_check, upgraded.document_type, ScamRisk.likely)
    assert doc_type is DT.other_notice and final.document_type is DT.other_notice
    assert final.category is DC.benefits and final.document_type_confidence is Confidence.low
    kept, doc_type = cl.after_scam(upgraded, type_check, upgraded.document_type, ScamRisk.possible)
    assert doc_type is DT.snap_notice and kept == upgraded


def test_a_scam_retype_is_low_confidence_and_a_reverted_agency_type_is_retyped() -> None:
    out, paper = reading(lines("USCIS"), DT.uscis_rfe, Confidence.high, DC.immigration)
    same = cl.check_document_type(out, paper)
    final, doc_type = cl.after_scam(out, same, DT.other_notice, ScamRisk.likely)
    assert doc_type is DT.other_notice and final.document_type_confidence is Confidence.low
    assert final.category is DC.immigration  # §6.5 "category unchanged"
    # The model said irs_notice (unsure), a CP565 label made it itin; a likely scam re-types the
    # model's own agency type, it never keeps the code's itin.
    irs, paper = reading(lines("Internal Revenue Service", "Notice CP565"), DT.irs_notice,
                         Confidence.low, DC.tax)  # fmt: skip
    corrected = cl.check_document_type(irs, paper)
    assert corrected.document_type is DT.itin
    final, doc_type = cl.after_scam(cl.apply_type_check(irs, corrected), corrected,
                                    DT.other_notice, ScamRisk.likely)  # fmt: skip
    assert doc_type is DT.other_notice and final.document_type_confidence is Confidence.low


I797C_FAKE = lines(
    "Form I-797C, Notice of Action", "Receipt Notice", "U.S. Citizenship and Immigration Services",
    "Your I-765 case is on hold. Check status at www.uscis-case-help.example.com",
)
NTA = lines("Form I-862", "Notice to Appear", "Executive Office for Immigration Review",
            "You are ordered to appear before an immigration judge.")  # fmt: skip


def test_a_code_upgraded_agency_type_never_survives_a_possible_scam() -> None:
    """Integration review, issue 17: a printed fake I-797C label upgraded a model-suspected scam
    (scored possible) to uscis_receipt, adding the agency's fixed card and pins and pushing the
    scam-report help out of the preview. A court type keeps its label (§6.5)."""
    out, paper = reading(I797C_FAKE, DT.other_notice, Confidence.medium, DC.immigration)
    type_check = cl.check_document_type(out, paper)
    upgraded = cl.apply_type_check(out, type_check)
    assert upgraded.document_type is DT.uscis_receipt
    final, doc_type = cl.after_scam(upgraded, type_check, upgraded.document_type, ScamRisk.possible)
    assert doc_type is DT.other_notice and final.document_type is DT.other_notice
    assert final.document_type_confidence is Confidence.medium and final.category is DC.immigration
    kept, doc_type = cl.after_scam(upgraded, type_check, upgraded.document_type, ScamRisk.none)
    assert doc_type is DT.uscis_receipt and kept == upgraded
    nta, paper = reading(NTA, DT.other_notice, Confidence.medium, DC.immigration)
    nta_check = cl.check_document_type(nta, paper)
    court = cl.apply_type_check(nta, nta_check)
    assert court.document_type is DT.nta
    assert cl.after_scam(court, nta_check, court.document_type, ScamRisk.possible)[1] is DT.nta


def test_the_models_scam_hints_never_decide_a_type() -> None:
    """D-13: ``is_likely_scam`` / ``scam_signals`` are hints. A small model called genuine papers
    fake in the sweep; on a real USCIS paper the label's type (its floors and verify line) stays
    unless the code scorer finds a possible or likely scam (``after_scam``)."""
    out, paper = reading(I797C_FAKE, DT.other_notice, Confidence.medium, DC.immigration)
    suspect = out.model_copy(update={"is_likely_scam": True, "scam_signals": ["impersonation"]})
    type_check = cl.check_document_type(suspect, paper)
    assert (type_check.document_type, type_check.rule) == (DT.uscis_receipt, "form")
    upgraded = cl.apply_type_check(suspect, type_check)
    assert cl.after_scam(upgraded, type_check, upgraded.document_type, ScamRisk.none)[1] is (
        DT.uscis_receipt
    )


def test_unreadable_reading_is_unknown_other() -> None:
    out, _ = reading(lines("blur"), DT.other_notice, Confidence.medium, DC.tax)
    got = cl.unreadable_reading(out)
    assert (got.document_type, got.category, got.document_type_confidence) == (
        DT.unknown, DC.other, Confidence.low
    )


# --- printed form numbers (entities, form tags) -------------------------------------------------

def test_printed_form_numbers_keep_the_printed_number_only() -> None:
    text = "Form W-2 Wage and Tax Statement 2025\nWe received your Form I-765.\nNotice CP14"
    assert cl.printed_form_numbers(["Form W-2 Wage and Tax Statement 2025"], text) == ["W-2"]
    assert cl.printed_form_numbers(
        ["Form I-765, Application for Employment Authorization"], text
    ) == ["I-765"]
    assert cl.printed_form_numbers(["I-765", "I765", "Notice CP 14"], text) == ["I-765", "CP14"]
    assert cl.printed_form_numbers(["Form I-485"], text) == []  # not printed
    assert cl.printed_form_numbers(["I-797C"], "I-797C, Notice of Action") == ["I-797C"]
    assert cl.printed_form_numbers(["EOIR-33/IC"], "Form EOIR-33/IC") == ["EOIR-33"]
    assert cl.printed_form_numbers(["Sample tax form"], "Sample Tax Form") == ["Sample tax form"]
    assert cl.printed_form_numbers(["I 765"], "Case type: I 765") == ["I-765"]


def test_a_form_number_must_be_printed_as_a_whole() -> None:
    """Review of package B: letters and digits run together across words ("HI 96817" → I9,
    "W 2B" → W2) never count as a printed form."""
    text = "Kalihi Clinic\n1234 King St, Honolulu, HI 96817\nYour appointment is Nov 3. Room W 2B."
    model = ["Form I-9, Employment Eligibility Verification", "Form W-2 Wage and Tax Statement",
             "Form I-90"]  # fmt: skip
    assert cl.printed_form_numbers(model, text) == []


def test_canonical_form_spelling() -> None:
    assert [cl.canonical_form(t) for t in ("I765", "w2", "EOIR33", "CP 14", "1099NEC")] == [
        "I-765", "W-2", "EOIR-33", "CP14", "1099-NEC",
    ]  # fmt: skip


# --- the SAMPLE footer of a demo paper ----------------------------------------------------------

FOOTER_BLOCK = block("p1b9", SAMPLE_FOOTER, bbox=[0.25, 0.97, 0.75, 0.99])


def flag(quote: str, span_ids: list[str], kind: RedFlagKind = RedFlagKind.impersonation) -> RedFlag:
    return RedFlag(
        kind=kind, text="The paper says it is not real.", source_quote=quote, span_ids=span_ids,
        page=1, severity=Severity.high, fixed_copy_key=None, verified=True,
    )  # fmt: skip


def step(text: str, span_ids: list[str]) -> PlanStepOut:
    return PlanStepOut(id="s1", text=text, kind=PlanStepKind.wait, resource_tags=[],
                       span_ids=span_ids, demand_id=None)  # fmt: skip


def test_the_footer_and_its_pieces_are_the_banner_and_nothing_else_is() -> None:
    assert cl.is_sample_banner(SAMPLE_FOOTER)
    slip = "SAMPLE - synthetic document made for demonstation. Not a real letter"
    assert cl.is_sample_banner(slip)
    assert cl.is_sample_banner("Not a real letter.") and cl.is_sample_banner("SAMPLE")
    for other in ("SAMPLE PATIENT", "Pay with gift cards. " + SAMPLE_FOOTER, "Real letter", "",
                  None, "Sample County Courthouse"):  # fmt: skip
        assert not cl.is_sample_banner(other), other
    paper = assemble_transcript([*lines("Notice", "Pay by October 9."), FOOTER_BLOCK],
                                pages_received=1)  # fmt: skip
    assert cl.sample_banner_ids(paper) == {"p1b9"}


def test_make_fixtures_prints_the_footer_the_pipeline_recognises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = Path(__file__).resolve().parents[2] / "scripts" / "make_fixtures.py"
    spec = importlib.util.spec_from_file_location("make_fixtures_footer_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    assert module.FOOTER_TEXT == SAMPLE_FOOTER and cl.is_sample_banner(module.FOOTER_TEXT)


def test_footer_flags_and_footer_steps_are_dropped() -> None:
    paper = assemble_transcript([*lines("Notice", "Pay by October 9."), FOOTER_BLOCK],
                                pages_received=1)  # fmt: skip
    banner = cl.sample_banner_ids(paper)
    real = flag("Pay by October 9.", ["p1b2"], RedFlagKind.urgency_pressure)
    flags = [flag(SAMPLE_FOOTER, ["p1b9"]), flag("Not a real letter.", ["p1b2"]),
             flag("SAMPLE", ["p1b9"]), real]  # fmt: skip
    assert cl.drop_banner_flags(flags, banner) == [real]
    steps = [step("If the paper says it is a sample, do not pay or go to court.", ["p1b9"]),
             step("Ask the office that sent this if it is a real letter.", []),
             step("Look at the bottom to see if it says this is a sample.", []),
             step("Pay by October 9.", ["p1b2", "p1b9"]), step("Keep this paper.", [])]
    kept = cl.drop_banner_steps(steps, paper, banner)
    assert [s.text for s in kept] == ["Pay by October 9.", "Keep this paper."]


def test_scam_advice_that_mentions_a_real_letter_stays() -> None:
    """Review of package B: "A real letter from USCIS never asks for gift cards" is safety
    advice on the scam sample, not the footer's claim."""
    paper = assemble_transcript([*lines("Notice", "Pay with gift cards."), FOOTER_BLOCK],
                                pages_received=1)  # fmt: skip
    banner = cl.sample_banner_ids(paper)
    steps = [step("Do not pay. A real letter from USCIS never asks for gift cards.", ["p1b2"]),
             step("If this is a real letter, report the gift card request as a scam.", []),
             step("If the paper is real, talk to a licensed lawyer about your ticket.", [])]
    assert cl.drop_banner_steps(steps, paper, banner) == steps


@pytest.mark.parametrize("risk", [ScamRisk.possible, ScamRisk.likely])
def test_on_a_scam_sample_asking_whether_the_letter_is_real_stays(risk: ScamRisk) -> None:
    """Integration review, issue 18: on the in-app scam demo, "Ask USCIS whether this is a real
    letter before you pay" was dropped as the footer's claim. On a paper scored possible/likely
    (the footer itself is never scored) only a step naming the footer's own words goes."""
    paper = assemble_transcript([*lines("Notice", "Pay with Google Play cards."), FOOTER_BLOCK],
                                pages_received=1)  # fmt: skip
    banner = cl.sample_banner_ids(paper)
    ask = step("Ask USCIS whether this is a real letter before you pay.", ["p1b1"])
    sample = step("If the paper says it is a sample, do not pay.", [])
    footer_only = step("Read the line at the bottom.", ["p1b9"])
    assert cl.drop_banner_steps([ask, sample, footer_only], paper, banner, scam_risk=risk) == [ask]
    assert cl.drop_banner_steps([ask, sample, footer_only], paper, banner) == []
