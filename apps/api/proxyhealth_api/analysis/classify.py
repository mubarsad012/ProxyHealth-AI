"""What kind of paper this is — code checks on the model's reading (DOCUMENT_TAXONOMY §2, §3).

The model classifies from the taxonomy; code then checks its answer against the transcript with
the two signals §3 rule 1 says decide a type (§3 rule 16, ``check_document_type``):

* **Form number** (§3.1, §3.2, §3.9): a form label printed in the page-1 header — a line of at
  most 10 words in one of the first three blocks of page 1, or in a block whose top edge lies in
  the top quarter of the page — that names exactly one type (``FORM_TYPES``; an I-797C by its
  first-line heading, §3.2; a CP/LTR number only on a paper that prints "Internal Revenue
  Service"). It may replace any type the model chose.
* **Heading** (§3.1 and the §4 **RB** lines): a block's first line (at most 8 words) holding one
  of ``HEADINGS`` — some only with a cue printed elsewhere (a USCIS, EOIR or SNAP name). It only
  upgrades ``other_notice``/``unknown``, never another specific type.

A correction needs exactly one candidate type, never runs when the model said ``other_notice``
with ``document_type_confidence=high`` (§4.10: the model must not be pushed to a finer type it
ruled out) and sets the confidence to ``medium``. The phrases are English (a no-op on other
papers); form numbers work in any language. A type the code chose never survives a likely scam:
``after_scam`` puts the model's type back before the §6.5 re-type, and any re-type leaves
``document_type_confidence=low``.

Also here: ``category_for`` (the §2 master table gives every specific type one category; only
``other_notice`` keeps the model's best fit), ``unreadable_reading`` (§3.11: an unreadable paper
is ``unknown``/``other``), ``printed_form_numbers`` (the printed form number, not the model's
whole label: "Form W-2 Wage and Tax Statement 2025" → ``W-2``) and the SAMPLE footer of a demo
paper (``sample_banner_ids``, ``drop_banner_flags``, ``drop_banner_steps``): it is no part of the
paper, so no red flag, plan step or scam signal may rest on it (DOCUMENT_TAXONOMY §6.3). Pure;
nothing is logged.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import Literal

from proxyhealth_api.analysis import scam
from proxyhealth_api.analysis.transcript import Transcript
from proxyhealth_api.analysis.verify import normalize
from proxyhealth_api.contracts.analysis import RedFlag
from proxyhealth_api.contracts.common import TextBlock
from proxyhealth_api.contracts.enums import Confidence, DocumentCategory, DocumentType, ScamRisk
from proxyhealth_api.contracts.model_out import AnalysisModelOut, PlanStepOut
from proxyhealth_api.demo.fixtures import SAMPLE_FOOTER

DT = DocumentType
DC = DocumentCategory
TypeRule = Literal["form", "heading"]

# §2 master table, "Category" column. ``other_notice`` ("any") keeps the model's category.
TYPE_CATEGORY: Mapping[DocumentType, DocumentCategory] = {
    **dict.fromkeys(
        (DT.uscis_receipt, DT.uscis_rfe, DT.uscis_noid, DT.uscis_biometrics, DT.uscis_interview,
         DT.uscis_approval, DT.uscis_denial, DT.ead_related, DT.green_card_related,
         DT.tps_related, DT.asylum_fee_notice, DT.parole_related, DT.ice_checkin),
        DC.immigration,
    ),
    **dict.fromkeys(
        (DT.nta, DT.hearing_notice, DT.ij_decision, DT.bia_notice, DT.traffic_court), DC.court
    ),
    **dict.fromkeys(
        (DT.medical_bill, DT.eob, DT.insurance_denial, DT.prior_auth, DT.lab_result,
         DT.prescription_label, DT.discharge_instructions, DT.vaccine_record,
         DT.appointment_reminder),
        DC.medical,
    ),
    **dict.fromkeys((DT.medicaid_renewal, DT.snap_notice, DT.wic_notice, DT.ssa_letter),
                    DC.benefits),
    **dict.fromkeys(
        (DT.pay_or_quit, DT.eviction_summons, DT.lease, DT.rent_increase, DT.section8_recert,
         DT.utility_shutoff),
        DC.housing,
    ),
    **dict.fromkeys(
        (DT.school_enrollment, DT.immunization_notice, DT.iep_504_notice, DT.school_meals,
         DT.report_card),
        DC.school,
    ),
    **dict.fromkeys((DT.w2_1099, DT.i9, DT.offer_letter, DT.pay_stub), DC.employment),
    **dict.fromkeys((DT.irs_notice, DT.itin), DC.tax),
    DT.jury_summons: DC.civic,
    DT.unknown: DC.other,
}  # fmt: skip

# A form number as printed ("Form I-862", "I-797C,", "Notice CP14", "W-2", "1099-NEC").
FORM_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9-])((?:EOIR|AR|DS|SS|I|N|G|W)-?\d{1,4}[A-Z]?|CP ?\d{1,4}[A-Z]?"
    r"|LTR ?\d{3,4}[A-Z]?|1099-?(?:NEC|MISC|K))(?![A-Za-z0-9])"
)
_HYPHENATED_RE = re.compile(r"^(EOIR|AR|DS|SS|I|N|G|W)(\d.*)$")
_IRS_NUMBER_RE = re.compile(r"^(CP\d{1,4}[A-Z]?|LTR\d{3,4}[A-Z]?)$")
# Form label → type (§3.1, §3.9, §4.1 headings, §4.2 ice_checkin RB, §4.3 nta). EOIR-33 (printed
# on NTAs and hearing notices alike) and a bare I-797 (several USCIS types) decide nothing.
FORM_TYPES: Mapping[str, DocumentType] = {
    "I862": DT.nta, "I797E": DT.uscis_rfe, "I797A": DT.uscis_approval,
    "I797B": DT.uscis_approval, "N445": DT.uscis_interview, "I220A": DT.ice_checkin,
    "I220B": DT.ice_checkin, "W2": DT.w2_1099, "1099NEC": DT.w2_1099, "1099MISC": DT.w2_1099,
    "1099K": DT.w2_1099, "I9": DT.i9, "W7": DT.itin, "CP565": DT.itin, "CP566": DT.itin,
    "CP567": DT.itin,
}  # fmt: skip
IRS_NAME = "internal revenue service"
# §3.2: "I-797C is not one type. Read the first bold line."
I797C_HEADINGS: tuple[tuple[str, DocumentType], ...] = (
    ("receipt notice", DT.uscis_receipt), ("transfer notice", DT.uscis_receipt),
    ("asc appointment notice", DT.uscis_biometrics), ("biometrics", DT.uscis_biometrics),
    ("interview notice", DT.uscis_interview),
    ("request for applicant to appear", DT.uscis_interview),
    ("rejection notice", DT.uscis_denial),
)  # fmt: skip
USCIS_CUES = ("u.s. citizenship and immigration services", "uscis", "i-797", "i-797c", "i-797e")
EOIR_CUES = ("executive office for immigration review", "immigration judge",
             "board of immigration appeals", "immigration court")  # §3.4  # fmt: skip
SNAP_CUES = ("supplemental nutrition assistance program", "snap", "food assistance", "ebt")
# Heading → type, with the cues one of which must be printed too (§3.1, §3.3–§3.8, §4 RB lines).
HEADINGS: tuple[tuple[str, DocumentType, tuple[str, ...]], ...] = (
    ("request for evidence", DT.uscis_rfe, USCIS_CUES),
    ("notice of intent to deny", DT.uscis_noid, USCIS_CUES),
    ("receipt notice", DT.uscis_receipt, USCIS_CUES),
    ("asc appointment notice", DT.uscis_biometrics, USCIS_CUES),
    ("notice to appear", DT.nta, EOIR_CUES),  # a traffic "Notice to Appear" is no NTA (§3.4)
    ("notice of hearing in removal proceedings", DT.hearing_notice, ()),
    ("order of the immigration judge", DT.ij_decision, ()),
    ("explanation of benefits", DT.eob, ()), ("this is not a bill", DT.eob, ()),
    ("adverse benefit determination", DT.insurance_denial, ()),
    ("unlawful detainer", DT.eviction_summons, ()),
    ("complaint for possession", DT.eviction_summons, ()),
    ("disconnection notice", DT.utility_shutoff, ()),
    ("notice to pay rent or quit", DT.pay_or_quit, ()),
    ("notice to cure or quit", DT.pay_or_quit, ()),
    ("notice of rent increase", DT.rent_increase, ()),
    ("residential lease agreement", DT.lease, ()),
    ("summons for jury service", DT.jury_summons, ()),
    ("juror qualification questionnaire", DT.jury_summons, ()),
    ("uniform summons", DT.traffic_court, ()), ("traffic citation", DT.traffic_court, ()),
    ("wage and tax statement", DT.w2_1099, ()),
    ("employment eligibility verification", DT.i9, ()),
    ("earnings statement", DT.pay_stub, ()), ("offer of employment", DT.offer_letter, ()),
    ("notice of interview", DT.snap_notice, SNAP_CUES),
    ("notice of missed interview", DT.snap_notice, SNAP_CUES),
    ("prior written notice", DT.iep_504_notice, ()),
    ("discharge instructions", DT.discharge_instructions, ()),
    ("after visit summary", DT.discharge_instructions, ()),
    ("immunization record", DT.vaccine_record, ()),
    ("immunization compliance", DT.immunization_notice, ()),
    ("appointment reminder", DT.appointment_reminder, ()),
)  # fmt: skip
HEADER_TOP = 0.25  # a header block's top edge lies in the top quarter of page 1
HEADER_BLOCKS = 3  # … or it is one of the first three blocks
LABEL_MAX_WORDS = 10  # a form label, not a sentence that mentions a form
HEADING_MAX_WORDS = 8
_UPGRADABLE = frozenset({DT.other_notice, DT.unknown})


def _norm(text: str) -> str:
    """``verify.normalize``, case-folded, whitespace collapsed (the phrase-matching key)."""
    return " ".join(normalize(text).casefold().split())


def _has(phrase: str, text: str) -> bool:
    """``phrase`` occurs in ``text`` as whole words."""
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def form_key(token: str) -> str:
    """``"Form I-797C"`` → ``"FORMI797C"``; a printed token ``"I 797C"`` → ``"I797C"``."""
    return re.sub(r"[^A-Z0-9]", "", token.upper())


def canonical_form(token: str) -> str:
    """A form token as the agencies print it: ``I-765``, ``W-2``, ``EOIR-33``, ``CP14``,
    ``1099-NEC``."""
    key = form_key(token)
    if m := _HYPHENATED_RE.match(key):
        return f"{m[1]}-{m[2]}"
    if key.startswith("1099") and len(key) > 4:
        return f"1099-{key[4:]}"
    return key


def category_for(document_type: DocumentType, model_category: DocumentCategory) -> DocumentCategory:
    """§2: the category the type fixes; ``other_notice`` keeps the model's best fit (§4.10)."""
    return TYPE_CATEGORY.get(document_type, model_category)


@dataclass(frozen=True)
class TypeCheck:
    """``check_document_type`` result: the type to use and, when code changed it, the rule."""

    document_type: DocumentType
    confidence: Confidence
    rule: TypeRule | None
    model_type: DocumentType
    model_confidence: Confidence
    model_category: DocumentCategory


def _header_blocks(blocks: Sequence[TextBlock]) -> list[TextBlock]:
    first = [b for b in blocks if b.page == 1]
    return [b for i, b in enumerate(first)
            if i < HEADER_BLOCKS or (b.bbox is not None and b.bbox[1] <= HEADER_TOP)]  # fmt: skip


def normalize_lines(text: str) -> list[str]:
    """The block's printed lines, each through ``verify.normalize`` (dashes unified)."""
    return [normalize(line) for line in text.splitlines() if line.strip()]


def header_form_keys(blocks: Sequence[TextBlock]) -> list[str]:
    """Form-number keys printed as a label in the page-1 header (``I862``, ``CP14`` …)."""
    out: list[str] = []
    for b in _header_blocks(blocks):
        for line in normalize_lines(b.text):
            if len(line.split()) > LABEL_MAX_WORDS:
                continue
            for m in FORM_TOKEN_RE.finditer(line):
                key = form_key(m.group(1))
                if key not in out:
                    out.append(key)
    return out


def first_lines(blocks: Sequence[TextBlock]) -> list[str]:
    """Each block's first printed line, as a matching key, when it is heading-short."""
    out: list[str] = []
    for b in blocks:
        lines = normalize_lines(b.text)
        line = _norm(lines[0]).strip(" :.-") if lines else ""
        if line and len(line.split()) <= HEADING_MAX_WORDS:
            out.append(line)
    return out


def _form_types(blocks: Sequence[TextBlock], full: str) -> set[DocumentType]:
    implied: set[DocumentType] = set()
    for key in header_form_keys(blocks):
        if key in FORM_TYPES:
            implied.add(FORM_TYPES[key])
        elif _IRS_NUMBER_RE.match(key) and _has(IRS_NAME, full):
            implied.add(DT.irs_notice)
        elif key == "I797C":
            lines = first_lines(blocks)
            hits = {t for phrase, t in I797C_HEADINGS for line in lines if _has(phrase, line)}
            if len(hits) == 1:
                implied |= hits
    return implied


def _heading_types(blocks: Sequence[TextBlock], full: str) -> set[DocumentType]:
    lines = first_lines(blocks)
    return {
        t for phrase, t, cues in HEADINGS for line in lines
        if _has(phrase, line) and (not cues or any(_has(c, full) for c in cues))
    }  # fmt: skip


def check_document_type(out: AnalysisModelOut, paper: Transcript) -> TypeCheck:
    """§3 rule 16: the model's type, or the one a printed form label (any type) or heading
    (``other_notice``/``unknown`` only) decides — see the module docstring. Readable papers
    only (the pipeline stops at an unreadable one first)."""
    kept = TypeCheck(
        out.document_type, out.document_type_confidence, None, out.document_type,
        out.document_type_confidence, out.category,
    )  # fmt: skip
    if out.document_type is DT.other_notice and out.document_type_confidence is Confidence.high:
        return kept
    blocks = paper.blocks
    full = _norm(paper.full_text)
    forms = _form_types(blocks, full)
    if len(forms) == 1:
        (found,) = forms
        if found is out.document_type:
            return kept
        return replace(kept, document_type=found, confidence=Confidence.medium, rule="form")
    if forms or out.document_type not in _UPGRADABLE:
        return kept  # two form labels disagree, or a specific type no heading may replace
    heads = _heading_types(blocks, full)
    if len(heads) == 1:
        (found,) = heads
        return replace(kept, document_type=found, confidence=Confidence.medium, rule="heading")
    return kept


def apply_type_check(out: AnalysisModelOut, check: TypeCheck) -> AnalysisModelOut:
    """The model output with the checked type and confidence and the category that type fixes
    (§2; a correct type with the wrong model category gets the table's category too)."""
    return out.model_copy(update={
        "document_type": check.document_type, "document_type_confidence": check.confidence,
        "category": category_for(check.document_type, check.model_category),
    })  # fmt: skip


def after_scam(
    out: AnalysisModelOut, check: TypeCheck, retyped: DocumentType, scam_risk: ScamRisk
) -> tuple[AnalysisModelOut, DocumentType]:
    """After the scorer (``retyped`` = ``scam.retype_for_scam(out.document_type, …)``): a type
    the code chose never survives a likely scam — the model's own type and category come back,
    then the §6.5 re-type applies to them — and a re-typed paper is low confidence (§6.5)."""
    if check.rule is not None and scam_risk is ScamRisk.likely:
        retyped = scam.retype_for_scam(check.model_type, scam_risk)
        confidence = Confidence.low if retyped is not check.model_type else check.model_confidence
        category = category_for(check.model_type, check.model_category)
        return out.model_copy(update={
            "document_type": retyped, "document_type_confidence": confidence,
            "category": category,
        }), retyped  # fmt: skip
    if retyped is not out.document_type:
        return out.model_copy(update={
            "document_type": retyped, "document_type_confidence": Confidence.low,
        }), retyped  # fmt: skip
    return out, retyped


def unreadable_reading(out: AnalysisModelOut) -> AnalysisModelOut:
    """§3.11: an unreadable paper is ``unknown`` / ``other`` whatever the model guessed."""
    return out.model_copy(update={
        "document_type": DT.unknown, "category": DC.other,
        "document_type_confidence": Confidence.low,
    })  # fmt: skip


def printed_form_numbers(form_numbers: Sequence[str], full_text: str) -> list[str]:
    """Form numbers the model listed that are really printed (``I-765`` ≈ ``I 765``), as the
    printed number ("Form W-2 Wage and Tax Statement 2025" → ``W-2``, "Form I-765, Application
    for Employment Authorization" → ``I-765``). A string holding no form token is kept whole when
    it is printed (``AR-11``-style numbers outside ``FORM_TOKEN_RE``)."""
    corpus = form_key(full_text)
    out: list[str] = []
    for form in form_numbers:
        tokens = [m.group(1) for m in FORM_TOKEN_RE.finditer(normalize(form))]
        if tokens:
            found = [canonical_form(t) for t in tokens if form_key(t) in corpus]
        else:
            key = form_key(form)
            found = [form.strip()[:40]] if key and key in corpus else []
        out += [f for f in found if f not in out]
    return out


# ----------------------------------------------------------------------------- SAMPLE footer

# The footer's claim; a sample paper's plan step that repeats it ("Ask the office that sent this
# if it is a real letter") is about the footer, not the paper.
_FOOTER_PHRASE = "real letter"
BANNER_RATIO = 0.9


def _words(text: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", _norm(text)).split())


_FOOTER_WORDS = _words(SAMPLE_FOOTER)


def is_sample_banner(text: str | None) -> bool:
    """``text`` is the SAMPLE footer of a demo paper, a piece of it ("Not a real letter.") or
    the bare SAMPLE watermark — nothing else is printed in it."""
    words = _words(text or "")
    if not words:
        return False
    if words == "sample" or (len(words.split()) >= 3 and f" {words} " in f" {_FOOTER_WORDS} "):
        return True
    # The whole footer with a transcription slip ("demonstation") still counts.
    return SequenceMatcher(None, words, _FOOTER_WORDS, autojunk=False).ratio() >= BANNER_RATIO


def sample_banner_ids(paper: Transcript) -> frozenset[str]:
    """Ids of the blocks that hold only the SAMPLE footer (or watermark) of a sample paper."""
    return frozenset(b.id for b in paper.blocks if is_sample_banner(b.text))


def drop_banner_flags(flags: Sequence[RedFlag], banner_ids: Collection[str]) -> list[RedFlag]:
    """Verified model flags of a sample paper minus those that quote the SAMPLE footer or rest
    only on its block (a "Not a real letter" footer is no sign of a fake or scam paper)."""
    return [
        f for f in flags
        if not is_sample_banner(f.source_quote)
        and not (f.span_ids and set(f.span_ids) <= set(banner_ids))
    ]  # fmt: skip


def drop_banner_steps(
    steps: Sequence[PlanStepOut], paper: Transcript, banner_ids: Collection[str]
) -> list[PlanStepOut]:
    """Model plan steps of a sample paper minus those about the SAMPLE footer: the step repeats
    its claim ("… if it is a real letter") or cites only the footer's block ("If the paper says
    it is a sample, do not pay or go to court")."""
    kept: list[PlanStepOut] = []
    for step in steps:
        cited = paper.existing(step.span_ids)
        if f" {_FOOTER_PHRASE} " in f" {_words(step.text)} ":
            continue
        if cited and set(cited) <= set(banner_ids):
            continue
        kept.append(step)
    return kept


__all__ = [
    "FORM_TOKEN_RE",
    "FORM_TYPES",
    "HEADINGS",
    "TYPE_CATEGORY",
    "TypeCheck",
    "after_scam",
    "apply_type_check",
    "canonical_form",
    "category_for",
    "check_document_type",
    "drop_banner_flags",
    "drop_banner_steps",
    "form_key",
    "header_form_keys",
    "is_sample_banner",
    "printed_form_numbers",
    "sample_banner_ids",
    "unreadable_reading",
]
