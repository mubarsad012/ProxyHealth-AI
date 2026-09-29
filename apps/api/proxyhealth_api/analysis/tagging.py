"""Resource tags (D-10, D-13, D-14; AI_PROMPTS §11.10; DOCUMENT_TAXONOMY §2).

The model proposes ``resource_tags`` as free strings; only values of the ``ResourceTag`` enum
survive (de-duplicated, at most 6). An empty list falls back to the document type's primary tags
(TAXONOMY §2 master table) plus form-specific tags; when that is still empty and the paper is
readable the pipeline may run task ``tag`` once (``TagOutcome.needs_tag_call``). ``crisis`` goes
first when the emergency lexicon fired, then ``scam_report`` when ``scam_risk == likely``.
Resources themselves only ever come from the vetted DB through the matcher.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from proxyhealth_api.contracts.analysis import RedFlag
from proxyhealth_api.contracts.enums import (
    DocumentCategory,
    DocumentType,
    RedFlagKind,
    ResourceTag,
    ScamRisk,
)

MAX_TAGS = 6
DT = DocumentType
RT = ResourceTag
PRIMARY_TAGS: Mapping[DocumentType, tuple[ResourceTag, ...]] = {
    DT.uscis_receipt: (RT.immigration_legal_help,), DT.uscis_rfe: (RT.immigration_legal_help,),
    DT.uscis_noid: (RT.immigration_legal_help,), DT.uscis_biometrics: (RT.immigration_legal_help,),
    DT.uscis_interview: (RT.immigration_legal_help,),
    DT.uscis_approval: (RT.immigration_legal_help,),
    DT.uscis_denial: (RT.immigration_legal_help,),
    DT.ead_related: (RT.work_permit, RT.immigration_legal_help),
    DT.green_card_related: (RT.green_card, RT.immigration_legal_help),
    DT.tps_related: (RT.daca_tps, RT.work_permit, RT.immigration_legal_help),
    DT.asylum_fee_notice: (RT.asylum, RT.immigration_legal_help),
    DT.parole_related: (RT.refugee_services, RT.immigration_legal_help),
    DT.ice_checkin: (RT.removal_proceedings, RT.immigration_legal_help),
    DT.nta: (RT.removal_proceedings, RT.court_notice, RT.change_of_address),
    DT.hearing_notice: (RT.removal_proceedings, RT.court_notice, RT.change_of_address),
    DT.ij_decision: (RT.removal_proceedings, RT.immigration_legal_help),
    DT.bia_notice: (RT.removal_proceedings, RT.immigration_legal_help),
    DT.traffic_court: (RT.traffic_court, RT.immigration_legal_help),
    DT.medical_bill: (RT.medical_bill, RT.charity_care), DT.eob: (RT.medical_bill,),
    DT.insurance_denial: (RT.insurance_denial,), DT.prior_auth: (RT.insurance_denial,),
    DT.lab_result: (RT.lab_results, RT.primary_care_uninsured),
    DT.prescription_label: (RT.prescription_help, RT.language_access),
    DT.discharge_instructions: (RT.primary_care_uninsured, RT.language_access, RT.medical_bill),
    DT.vaccine_record: (RT.vaccine_records, RT.school_enrollment),
    DT.appointment_reminder: (RT.language_access,),
    DT.medicaid_renewal: (RT.medicaid_renewal, RT.benefits_navigation),
    DT.snap_notice: (RT.snap, RT.food, RT.benefits_navigation), DT.wic_notice: (RT.wic, RT.food),
    DT.ssa_letter: (RT.ssa_benefits, RT.benefits_navigation),
    DT.pay_or_quit: (RT.eviction, RT.housing_counseling, RT.rent_assistance),
    DT.eviction_summons: (RT.eviction, RT.housing_counseling),
    DT.lease: (RT.housing_counseling,),
    DT.rent_increase: (RT.housing_counseling, RT.rent_assistance),
    DT.section8_recert: (RT.section8, RT.housing_counseling),
    DT.utility_shutoff: (RT.utility_shutoff, RT.rent_assistance),
    DT.school_enrollment: (RT.school_enrollment, RT.homeless_students),
    DT.immunization_notice: (RT.vaccine_records, RT.school_enrollment),
    DT.iep_504_notice: (RT.special_education,), DT.school_meals: (RT.school_meals, RT.food),
    DT.report_card: (RT.language_access,), DT.w2_1099: (RT.tax_notice,),
    DT.i9: (RT.work_permit, RT.workers_rights), DT.offer_letter: (RT.workers_rights,),
    DT.pay_stub: (RT.wage_theft, RT.workers_rights), DT.irs_notice: (RT.tax_notice,),
    DT.itin: (RT.itin, RT.tax_notice), DT.jury_summons: (RT.jury_summons,),
    DT.other_notice: (), DT.unknown: (),
}  # fmt: skip
CATEGORY_TAGS: Mapping[DocumentCategory, tuple[ResourceTag, ...]] = {
    DocumentCategory.immigration: (RT.immigration_legal_help,),
    DocumentCategory.court: (RT.court_notice,),
    DocumentCategory.medical: (RT.primary_care_uninsured,),
    DocumentCategory.benefits: (RT.benefits_navigation,),
    DocumentCategory.housing: (RT.housing_counseling,),
    DocumentCategory.school: (RT.school_enrollment,),
    DocumentCategory.employment: (RT.workers_rights,),
    DocumentCategory.tax: (RT.tax_notice,),
    DocumentCategory.civic: (),
    DocumentCategory.other: (),
}
# USCIS form number → case tag (TAXONOMY §2 "+work_permit/green_card/naturalization by form").
FORM_TAGS: Mapping[str, ResourceTag] = {
    "I765": RT.work_permit, "I485": RT.green_card, "I90": RT.green_card,
    "I751": RT.green_card, "I829": RT.green_card, "I130": RT.green_card,
    "N400": RT.naturalization, "N600": RT.naturalization, "I589": RT.asylum,
    "I821": RT.daca_tps, "I821D": RT.daca_tps, "I912": RT.fee_waiver, "AR11": RT.change_of_address,
    "EOIR33": RT.change_of_address,
}  # fmt: skip
SCAM_FLAG_KINDS = frozenset(
    {RedFlagKind.scam_payment_method, RedFlagKind.impersonation, RedFlagKind.notario}
)


def validate_tags(raw: Iterable[str]) -> list[ResourceTag]:
    """Keep only ``ResourceTag`` values (case/space-insensitive), de-duplicated, at most 6."""
    valid = {t.value: t for t in ResourceTag}
    out: list[ResourceTag] = []
    for item in raw:
        key = re.sub(r"[\s-]+", "_", str(item).strip().lower())
        tag = valid.get(key)
        if tag is not None and tag not in out:
            out.append(tag)
        if len(out) == MAX_TAGS:
            break
    return out


def form_tags(form_numbers: Iterable[str]) -> list[ResourceTag]:
    """Case tags implied by printed form numbers (``I-765`` → ``work_permit`` …)."""
    out: list[ResourceTag] = []
    for form in form_numbers:
        tag = FORM_TAGS.get(re.sub(r"[^A-Z0-9]", "", form.upper()))
        if tag is not None and tag not in out:
            out.append(tag)
    return out


def primary_tags(
    document_type: DocumentType,
    category: DocumentCategory | None = None,
    form_numbers: Sequence[str] = (),
) -> list[ResourceTag]:
    """TAXONOMY §2 primary tags for the type (``other_notice`` → by category) + form tags."""
    base = list(PRIMARY_TAGS.get(document_type, ()))
    if not base and document_type is DT.other_notice and category is not None:
        base = list(CATEGORY_TAGS.get(category, ()))
    for tag in form_tags(form_numbers) if document_type in _USCIS_FORM_TYPES else []:
        if tag not in base:
            base.append(tag)
    return base[:MAX_TAGS]


_USCIS_FORM_TYPES = frozenset(
    {DT.uscis_receipt, DT.uscis_rfe, DT.uscis_noid, DT.uscis_biometrics, DT.uscis_interview,
     DT.uscis_approval, DT.uscis_denial}
)  # fmt: skip


def _front(tags: list[ResourceTag], tag: ResourceTag) -> list[ResourceTag]:
    return [tag, *[t for t in tags if t is not tag]]


@dataclass(frozen=True)
class TagOutcome:
    """Final ``resource_tags``; ``needs_tag_call`` asks the pipeline to run task ``tag`` once."""

    tags: list[ResourceTag]
    needs_tag_call: bool = False
    source: str = "model"
    """``model`` · ``type`` (primary-tag fallback) · ``tag_call`` · ``none``."""


def finalize_tags(
    model_tags: Iterable[str],
    *,
    document_type: DocumentType,
    category: DocumentCategory | None = None,
    form_numbers: Sequence[str] = (),
    readable: bool = True,
    scam_risk: ScamRisk = ScamRisk.none,
    emergency: bool = False,
    red_flags: Iterable[RedFlag] = (),
    tag_call_tags: Iterable[str] | None = None,
) -> TagOutcome:
    """AI_PROMPTS §11.10 tagging. Call once with the model's tags; if ``needs_tag_call`` comes
    back true and the pipeline ran task ``tag``, call again passing ``tag_call_tags``."""
    tags = validate_tags(model_tags)
    source = "model"
    if not tags:
        tags, source = primary_tags(document_type, category, form_numbers), "type"
    if not tags and tag_call_tags is not None:
        tags, source = validate_tags(tag_call_tags), "tag_call"
    needs_call = not tags and readable and tag_call_tags is None
    if not tags:
        source = "none"
    if any(f.verified and f.kind in SCAM_FLAG_KINDS for f in red_flags) and category is not None:
        for tag in CATEGORY_TAGS.get(category, ()):
            if tag not in tags:
                tags.append(tag)
    if scam_risk is ScamRisk.likely:
        tags = _front(tags, RT.scam_report)
    if emergency:
        tags = _front(tags, RT.crisis)
    return TagOutcome(tags=tags[:MAX_TAGS], needs_tag_call=needs_call, source=source)


__all__ = [
    "CATEGORY_TAGS",
    "FORM_TAGS",
    "MAX_TAGS",
    "PRIMARY_TAGS",
    "TagOutcome",
    "finalize_tags",
    "form_tags",
    "primary_tags",
    "validate_tags",
]
