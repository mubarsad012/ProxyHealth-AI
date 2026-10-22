"""What kind of paper this is — code checks on the model's reading (DOCUMENT_TAXONOMY §2, §3).

The model classifies from the taxonomy; code then checks its answer against the transcript with
the two signals §3 rule 1 says decide a type (§3 rule 16, ``check_document_type``):

* **Form label** (§3.1, §3.2, §3.9): a page-1 header line (at most 10 words, in one of the first
  three blocks of page 1 or in a block whose top edge lies in the top quarter of the page) that
  *is* a form label — it starts with the form number, alone or after "Form"/"Notice"/"Letter"
  ("Form I-862", "I-797C, Notice of Action", "Notice CP14"), is no sentence (no closing
  punctuation, no "you"/"bring"/"send"/"complete" …) — and names exactly one type
  (``FORM_TYPES``; an I-797C or I-797E by its page-1 first-line heading, §3.2/§3.3; a CP/LTR
  number only on a paper that prints "Internal Revenue Service"). "Send proof of income, such as
  your W-2" mentions a form; it labels nothing. A label upgrades ``other_notice``/``unknown`` and
  replaces a type the model gave with ``document_type_confidence=low``; a type the model was sure
  of (medium/high) only from a "Form …"/"Notice …"/"…, Notice of Action" label of a type in the
  same §2 category that keeps every urgency protection of the model's type — its floor,
  never-estimate and past-date rules, critical roles and driving roles (``keeps_protections``:
  ``hearing_notice`` → ``nta`` may happen, ``uscis_noid`` → ``uscis_rfe`` never).
* **Heading** (§3.1 and the §4 **RB** lines): a page-1 block's first line (at most 8 words)
  holding one of ``HEADINGS`` — some only with a cue printed elsewhere (a USCIS, EOIR or SNAP
  name). It only upgrades ``other_notice``/``unknown``, never another specific type. A later page
  may be a different paper (§3.8 ``[multiple_documents]``), so it decides nothing.

A correction needs exactly one candidate type, never runs when the model said ``other_notice``
with ``document_type_confidence=high`` (§4.10: the model must not be pushed to a finer type it
ruled out) or flagged ``[multiple_documents]``, and sets the confidence to ``medium``. The
phrases are English (a no-op on other papers); form numbers work in any language. A corrected
type is a label only: the scam scorer still reads the model's own type, so a correction never
lowers ``scam_risk`` (pipeline). A type the code chose never survives a likely scam:
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
from typing import Literal

from proxyhealth_api.analysis import scam
from proxyhealth_api.analysis.deadline_rules import NEVER_ESTIMATE_TYPES
from proxyhealth_api.analysis.transcript import Transcript
from proxyhealth_api.analysis.urgency import (
    CRITICAL_SET,
    DRIVING_ROLES,
    FLOORS,
    PAST_CRITICAL_TYPES,
)
from proxyhealth_api.analysis.verify import MULTIPLE_DOCUMENTS_SENTINEL, normalize
from proxyhealth_api.contracts.analysis import RedFlag
from proxyhealth_api.contracts.common import TextBlock
from proxyhealth_api.contracts.enums import Confidence, DocumentCategory, DocumentType, ScamRisk
from proxyhealth_api.contracts.model_out import AnalysisModelOut, PlanStepOut
from proxyhealth_api.demo.fixtures import is_sample_banner

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
_TOKEN = (
    r"(?:EOIR|AR|DS|SS|I|N|G|W)-?\d{1,4}[A-Z]?|CP ?\d{1,4}[A-Z]?|LTR ?\d{3,4}[A-Z]?"
    r"|1099-?(?:NEC|MISC|K)"
)
FORM_TOKEN_RE = re.compile(rf"(?<![A-Za-z0-9-])({_TOKEN})(?![A-Za-z0-9])")
# The same anywhere in a transcript, a space allowed after the letters ("I 765", "CP 14").
_PRINTED_FORM_RE = re.compile(
    r"(?<![A-Za-z0-9-])((?:EOIR|AR|DS|SS|I|N|G|W)[- ]?\d{1,4}[A-Z]?|CP ?\d{1,4}[A-Z]?"
    r"|LTR ?\d{3,4}[A-Z]?|1099[- ]?(?:NEC|MISC|K))(?![A-Za-z0-9])"
)
# A label line: the form number first, alone or after "Form"/"Notice"/"Letter" (§4.1 "form label
# top-right", §4.9 "notice number top-right"). ``prefix`` makes it a strong label.
_LABEL_RE = re.compile(
    rf"^\(?(?P<prefix>(?i:form|notice|letter|formulario|aviso|carta)\s+)?"
    rf"(?P<token>{_TOKEN})(?![A-Za-z0-9])(?P<rest>.*)$"
)
_NOTICE_OF_ACTION_RE = re.compile(r"^[\s,:-]*notice of action\b", re.IGNORECASE)
# Sentence words: a line holding one mentions a form ("Bring Form W-2 and your ID"), it is no label.
_SENTENCE_RE = re.compile(
    r"\b(you|your|we|our|please|bring|send|complete|submit|attach|fill|include|provide|mail|"
    r"sign|return|enclose|need|needs|must|should|if|when|usted|su|sus|traiga|env[ií]e|presente|"
    r"adjunte|debe)\b",
    re.IGNORECASE,
)
_HYPHENATED_RE = re.compile(r"^(EOIR|AR|DS|SS|I|N|G|W)(\d.*)$")
_IRS_NUMBER_RE = re.compile(r"^(CP\d{1,4}[A-Z]?|LTR\d{3,4}[A-Z]?)$")
# Form label → type (§3.1, §3.9, §4.1 headings, §4.2 ice_checkin RB, §4.3 nta). EOIR-33 (printed
# on NTAs and hearing notices alike) and a bare I-797 (several USCIS types) decide nothing; an
# I-797C or I-797E is read by its heading (``FORM_HEADINGS``).
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
# §3.3: USCIS prints RFEs and NOIDs alike on I-797E; the heading tells them apart. With none, an
# I-797E is an RFE (``FORM_TYPES``) unless the model read it as a NOID.
I797E_HEADINGS: tuple[tuple[str, DocumentType], ...] = (
    ("request for evidence", DT.uscis_rfe), ("notice of intent to deny", DT.uscis_noid),
)  # fmt: skip
FORM_HEADINGS: Mapping[str, tuple[tuple[str, DocumentType], ...]] = {
    "I797C": I797C_HEADINGS, "I797E": I797E_HEADINGS,
}  # fmt: skip
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
# Type groups with an urgency protection (DOCUMENT_TAXONOMY §5.2 floor and past-date rules, §5.3
# never-estimate): a header label never moves a type the model was sure of out of one.
PROTECTION_GROUPS: tuple[frozenset[DocumentType], ...] = (
    FLOORS, NEVER_ESTIMATE_TYPES, PAST_CRITICAL_TYPES,
)  # fmt: skip


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


def _page_one(blocks: Sequence[TextBlock]) -> list[TextBlock]:
    return [b for b in blocks if b.page == 1]


def _header_blocks(blocks: Sequence[TextBlock]) -> list[TextBlock]:
    return [b for i, b in enumerate(_page_one(blocks))
            if i < HEADER_BLOCKS or (b.bbox is not None and b.bbox[1] <= HEADER_TOP)]  # fmt: skip


def normalize_lines(text: str) -> list[str]:
    """The block's printed lines, each through ``verify.normalize`` (dashes unified)."""
    return [normalize(line) for line in text.splitlines() if line.strip()]


@dataclass(frozen=True)
class FormLabel:
    """A form label printed in the page-1 header."""

    key: str
    """``form_key`` of the printed number (``I862``, ``CP14`` …)."""
    strong: bool
    """"Form …"/"Notice …"/"Letter …" or "…, Notice of Action": the paper names its own form."""


def form_label(line: str) -> FormLabel | None:
    """The form label ``line`` is, or ``None`` when it is a sentence or a phrase that merely
    mentions a form ("Bring Form W-2 and your ID.", "your W-2 or recent pay stubs,")."""
    text = line.strip()
    if not text or len(text.split()) > LABEL_MAX_WORDS or text.rstrip(" )")[-1:] in ".!?,;":
        return None
    m = _LABEL_RE.match(text)
    if m is None or _SENTENCE_RE.search(m["rest"]):
        return None
    strong = bool(m["prefix"]) or bool(_NOTICE_OF_ACTION_RE.match(m["rest"]))
    return FormLabel(form_key(m["token"]), strong)


def header_form_labels(blocks: Sequence[TextBlock]) -> list[FormLabel]:
    """The form labels printed in the page-1 header, in reading order (one per key, strong
    when any of its lines is)."""
    out: dict[str, FormLabel] = {}
    for b in _header_blocks(blocks):
        for line in normalize_lines(b.text):
            label = form_label(line)
            if label is not None and not (label.key in out and out[label.key].strong):
                out[label.key] = label
    return list(out.values())


def first_lines(blocks: Sequence[TextBlock]) -> list[str]:
    """Each page-1 block's first printed line, as a matching key, when it is heading-short."""
    out: list[str] = []
    for b in _page_one(blocks):
        lines = normalize_lines(b.text)
        line = _norm(lines[0]).strip(" :.-") if lines else ""
        if line and len(line.split()) <= HEADING_MAX_WORDS:
            out.append(line)
    return out


def _form_types(
    blocks: Sequence[TextBlock], full: str, model_type: DocumentType
) -> dict[DocumentType, bool]:
    """Type → strong for every type a header label names (``FORM_TYPES``, ``FORM_HEADINGS``)."""
    implied: dict[DocumentType, bool] = {}

    def add(doc_type: DocumentType, strong: bool) -> None:
        implied[doc_type] = implied.get(doc_type, False) or strong

    for label in header_form_labels(blocks):
        key = label.key
        if key in FORM_HEADINGS:
            table = FORM_HEADINGS[key]
            lines = first_lines(blocks)
            hits = {t for phrase, t in table for line in lines if _has(phrase, line)}
            if len(hits) == 1:
                add(next(iter(hits)), label.strong)
            elif not hits and key in FORM_TYPES:
                # No heading: the form's own type, unless the model read another type it carries.
                carried = {t for _phrase, t in table}
                add(model_type if model_type in carried else FORM_TYPES[key], label.strong)
        elif key in FORM_TYPES:
            add(FORM_TYPES[key], label.strong)
        elif _IRS_NUMBER_RE.match(key) and _has(IRS_NAME, full):
            add(DT.irs_notice, label.strong)
    return implied


def _heading_types(blocks: Sequence[TextBlock], full: str) -> set[DocumentType]:
    lines = first_lines(blocks)
    return {
        t for phrase, t, cues in HEADINGS for line in lines
        if _has(phrase, line) and (not cues or any(_has(c, full) for c in cues))
    }  # fmt: skip


def keeps_protections(model_type: DocumentType, found: DocumentType) -> bool:
    """``found`` keeps every urgency protection ``model_type`` has: its floor, never-estimate and
    past-date groups (``PROTECTION_GROUPS``), its critical roles and its driving roles (§5.2)."""
    none: frozenset[str] = frozenset()
    return (
        all(found in group for group in PROTECTION_GROUPS if model_type in group)
        and CRITICAL_SET.get(model_type, none) <= CRITICAL_SET.get(found, none)
        and DRIVING_ROLES.get(model_type, none) <= DRIVING_ROLES.get(found, none)
    )


def label_may_replace(
    model_type: DocumentType, confidence: Confidence, found: DocumentType, strong: bool
) -> bool:
    """Whether a header form label naming ``found`` may replace the model's type: always an
    ``other_notice``/``unknown`` or a low-confidence reading; a type the model was sure of only
    from a strong label of the same §2 category that ``keeps_protections``."""
    if model_type in _UPGRADABLE or confidence is Confidence.low:
        return True
    return (
        strong and TYPE_CATEGORY.get(found) is TYPE_CATEGORY.get(model_type)
        and keeps_protections(model_type, found)
    )  # fmt: skip


def _multiple_documents(out: AnalysisModelOut) -> bool:
    return any(f.text.strip() == MULTIPLE_DOCUMENTS_SENTINEL for f in out.red_flags)


def check_document_type(out: AnalysisModelOut, paper: Transcript) -> TypeCheck:
    """§3 rule 16: the model's type, or the one a printed header form label or a page-1 heading
    (``other_notice``/``unknown`` only) decides — see the module docstring. Readable papers
    only (the pipeline stops at an unreadable one first)."""
    kept = TypeCheck(
        out.document_type, out.document_type_confidence, None, out.document_type,
        out.document_type_confidence, out.category,
    )  # fmt: skip
    if out.document_type is DT.other_notice and out.document_type_confidence is Confidence.high:
        return kept
    if _multiple_documents(out):
        return kept  # another paper's label or heading must not type this one (§3.8)
    blocks = paper.blocks
    full = _norm(paper.full_text)
    forms = _form_types(blocks, full, out.document_type)
    if len(forms) == 1:
        ((found, strong),) = forms.items()
        if found is out.document_type or not label_may_replace(
            out.document_type, out.document_type_confidence, found, strong
        ):
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
    for Employment Authorization" → ``I-765``). A token counts only when the transcript prints it
    as a whole form number ("HI 96817" prints no I-9, "Room W 2B" no W-2). A string holding no
    form token ("Form SSA-1099", "Schedule A") is kept whole when its letters and digits are
    printed, as before."""
    printed = {form_key(m.group(1)) for m in _PRINTED_FORM_RE.finditer(normalize(full_text))}
    corpus = form_key(full_text)
    out: list[str] = []
    for form in form_numbers:
        tokens = [m.group(1) for m in _PRINTED_FORM_RE.finditer(normalize(form))]
        if tokens:
            found = [canonical_form(t) for t in tokens if form_key(t) in printed]
        else:
            key = form_key(form)
            found = [form.strip()[:40]] if key and key in corpus else []
        out += [f for f in found if f not in out]
    return out


# ----------------------------------------------------------------------------- SAMPLE footer

# A sample paper's plan step that turns the footer's claim into a condition ("Ask the office that
# sent this if it is a real letter", "If the paper says it is a sample, …") is about the footer,
# not the paper — unless it also warns about a scam ("A real letter from USCIS never asks for
# gift cards" carries no condition and stays anyway).
_FOOTER_CLAIM_RE = re.compile(r"\b(if|whether)\b.*\b(real letter|a sample|synthetic)\b")
_SCAM_WARNING_RE = re.compile(r"\b(scams?|scammers?|fraud\w*|gift cards?|never)\b")


def _words(text: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", _norm(text)).split())


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
    """Model plan steps of a sample paper minus those about the SAMPLE footer: the step cites only
    the footer's block ("If the paper says it is a sample, do not pay or go to court"), or makes
    the footer's claim its condition ("Ask the office … if it is a real letter") without warning
    about a scam."""
    kept: list[PlanStepOut] = []
    for step in steps:
        cited = paper.existing(step.span_ids)
        if cited and set(cited) <= set(banner_ids):
            continue
        words = _words(step.text)
        if _FOOTER_CLAIM_RE.search(words) and not _SCAM_WARNING_RE.search(words):
            continue
        kept.append(step)
    return kept


__all__ = [
    "FORM_HEADINGS",
    "FORM_TOKEN_RE",
    "FORM_TYPES",
    "HEADINGS",
    "I797C_HEADINGS",
    "I797E_HEADINGS",
    "PROTECTION_GROUPS",
    "TYPE_CATEGORY",
    "FormLabel",
    "TypeCheck",
    "after_scam",
    "apply_type_check",
    "canonical_form",
    "category_for",
    "check_document_type",
    "drop_banner_flags",
    "drop_banner_steps",
    "form_key",
    "form_label",
    "header_form_labels",
    "is_sample_banner",
    "keeps_protections",
    "label_may_replace",
    "printed_form_numbers",
    "sample_banner_ids",
    "unreadable_reading",
]
