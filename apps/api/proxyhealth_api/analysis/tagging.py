"""Resource tags (D-10, D-13, D-14; AI_PROMPTS §11.10; DOCUMENT_TAXONOMY §2).

The model proposes ``resource_tags`` as free strings; only values of the ``ResourceTag`` enum
survive (de-duplicated, at most 6). The document type's primary tags (TAXONOMY §2 master table)
plus form-specific tags follow the model's own (an empty list is just those); when that is still
empty and the paper is readable the pipeline may run task ``tag`` once
(``TagOutcome.needs_tag_call``). ``crisis`` goes first when the emergency lexicon fired, then
``scam_report`` when ``scam_risk == likely``. Emergency and scam status are code decisions
(D-13, D-14), so on the final call (``gate_sensitive=True``) a model ``crisis`` / ``poison`` tag
needs ``emergency``; a ``domestic_violence`` / ``trafficking`` tag needs ``emergency`` or a
printed abuse context (a protective order, VAWA, a U/T visa, I-914/I-918/I-360 …; a language
without a cue list keeps it); any of them stands when it is one of the type's own primary tags.
``scam_report`` needs ``scam_risk != none`` or a verified scam red flag. Resources themselves
only ever come from the vetted DB through the matcher.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from proxyhealth_api.analysis.verify import normalize
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
# Tags whose resources (crisis lines, poison help) answer an immediate danger: only an emergency
# the code detected may bring them (D-14).
DANGER_TAGS = frozenset({RT.crisis, RT.poison})
# DV and trafficking help also serves a paper about abuse that prints no emergency term (a
# protective order, a VAWA self-petition, a U/T-visa form): such a tag needs an emergency or a
# printed abuse context (``prints_abuse_context``).
ABUSE_TAGS = frozenset({RT.domestic_violence, RT.trafficking})
EMERGENCY_TAGS = DANGER_TAGS | ABUSE_TAGS
# Printed abuse context per language (every list runs on every text). A paper in a language with
# no list keeps the model's DV/trafficking tags: there is nothing to judge them by.
ABUSE_CONTEXT: Mapping[str, re.Pattern[str]] = {
    "en": re.compile(
        r"\b(protective|protection|restraining|no[- ]contact|stay[- ]away|peace) orders?\b"
        r"|\b(family|domestic|dating|intimate[- ]partner|spousal|elder|child|sexual) "
        r"(abuse|violence|assault)\b|\babus(e|ed|er|ers|ive)\b|\bbattered\b"
        r"|\bstalk(ing|ed|er|ers)?\b|\bvawa\b|\bviolence against women\b"
        r"|\btraffick(ing|ed|er|ers)?\b|\bforced (labor|labour)\b|\bcontinued presence\b"
        r"|\b(u|t)[- ](visas?|nonimmigrant)\b|\bi-?(914|918|360)\b",
        re.IGNORECASE,
    ),
    "es": re.compile(
        r"\b[oó]rden(es)? de (protecci[oó]n|alejamiento|restricci[oó]n)\b"
        r"|\bviolencia (dom[eé]stica|familiar|intrafamiliar|de g[eé]nero|de pareja|sexual)\b"
        r"|\babus(o|os|ador|adora|ivo|iva)\b|\bmaltrato\b|\bacoso\b|\bvisas? (u|t)\b"
        r"|\btrata de personas\b|\btrabajo forzoso\b",
        re.IGNORECASE,
    ),
}


def prints_abuse_context(text: str, language: str | None) -> bool:
    """True when a model ``domestic_violence``/``trafficking`` tag may stand without an
    emergency: the paper prints an abuse context, or its language (``None`` = not known) has no
    ``ABUSE_CONTEXT`` list."""
    if (language or "").split("-")[0].lower() not in ABUSE_CONTEXT:
        return True
    norm = normalize(text)
    return any(p.search(norm) for p in ABUSE_CONTEXT.values())


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
    gate_sensitive: bool = False,
    printed_text: str = "",
    language: str | None = None,
) -> TagOutcome:
    """AI_PROMPTS §11.10 tagging. Call once with the model's tags; if ``needs_tag_call`` comes
    back true and the pipeline ran task ``tag``, call again passing ``tag_call_tags``.

    The type's primary tags the model left out follow its own. ``gate_sensitive`` (the final
    call, once ``scam_risk``, ``emergency`` and the verified ``red_flags`` are known) drops model
    and tag-call ``crisis``/``poison`` tags without an emergency, ``domestic_violence``/
    ``trafficking`` tags without an emergency or an abuse context in ``printed_text`` (the
    transcript, in the paper's ``language``; ``prints_abuse_context``), and ``scam_report``
    without scam evidence."""
    flags = list(red_flags)
    primary = primary_tags(document_type, category, form_numbers)
    scam_flag = any(f.verified and f.kind in SCAM_FLAG_KINDS for f in flags)
    abuse = emergency or not gate_sensitive or prints_abuse_context(printed_text, language)

    def backed(tags: list[ResourceTag]) -> list[ResourceTag]:
        if not gate_sensitive:
            return tags
        return [
            t for t in tags
            if t in primary or not (
                (t in DANGER_TAGS and not emergency) or (t in ABUSE_TAGS and not abuse)
                or (t is RT.scam_report and scam_risk is ScamRisk.none and not scam_flag)
            )
        ]  # fmt: skip

    tags = backed(validate_tags(model_tags))
    source = "model"
    if tags:
        tags += [t for t in primary if t not in tags]
    else:
        tags, source = list(primary), "type"
    if not tags and tag_call_tags is not None:
        tags, source = backed(validate_tags(tag_call_tags)), "tag_call"
    needs_call = not tags and readable and tag_call_tags is None
    if not tags:
        source = "none"
    if scam_flag and category is not None:
        for tag in CATEGORY_TAGS.get(category, ()):
            if tag not in tags:
                tags.append(tag)
    if scam_risk is ScamRisk.likely:
        tags = _front(tags, RT.scam_report)
    if emergency:
        tags = _front(tags, RT.crisis)
    return TagOutcome(tags=tags[:MAX_TAGS], needs_tag_call=needs_call, source=source)


__all__ = [
    "ABUSE_CONTEXT",
    "ABUSE_TAGS",
    "CATEGORY_TAGS",
    "DANGER_TAGS",
    "EMERGENCY_TAGS",
    "FORM_TAGS",
    "MAX_TAGS",
    "PRIMARY_TAGS",
    "TagOutcome",
    "finalize_tags",
    "form_tags",
    "primary_tags",
    "prints_abuse_context",
    "validate_tags",
]
