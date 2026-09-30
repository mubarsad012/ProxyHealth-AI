"""Clerk card (D-18; PRODUCT_SPEC §8; AI_PROMPTS §11.10 and §5.5.4).

``clerk_message.english`` is the fixed template "Hello. I speak {Language}. I am here about:
{document}. I need help with: {need}. Please speak slowly or write it down. Thank you." Only the
need line may come from the model (``clerk_need_en``): it must survive the contact filter and the
phrasing lint and fit in 200 characters (cut at the last word boundary); otherwise the fixed
per-type line from ``data/rules/clerk_needs.yaml`` is used (``need_line_source="template"``).
``sender_as_written`` is model output too (D-10): when a ``scrubber`` would replace anything in it
(an organisation or contact not on the paper nor in the resource DB), the "from …" part is left
out of the card, so both ``english`` and ``translated`` read "a Medicaid letter" rather than
carrying an invented name or a target-language marker.
``clerk.interpreter_hhs`` is appended only for HHS-funded settings (matched resource, a
hospital/clinic/pharmacy/insurer sender, or a Medicaid renewal) — never on a landlord, court or
school card. ``translated`` comes from the optional ``clerk_translate`` callable; on failure it is
the pack's fixed ``clerk.generic_card`` in the target language (``t``) around the untranslated
English need line (AI_PROMPTS §5.5.4) — or the English card when no ``t`` is given — and
``translation_partial`` is warned.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol

from proxyhealth_api.analysis.contacts_filter import ContactScrubber, has_contact
from proxyhealth_api.analysis.i18n import Translator
from proxyhealth_api.analysis.phrasing import lint_sentence
from proxyhealth_api.contracts.analysis import ClerkMessage
from proxyhealth_api.contracts.enums import DocumentType, SenderKind, WarningCode

DT = DocumentType
INTERPRETER_KEY = "clerk.interpreter_hhs"
GENERIC_NEED_KEY = "clerk.generic_need"
GENERIC_CARD_KEY = "clerk.generic_card"
MAX_NEED_CHARS = 200
MAX_SENDER_CHARS = 80
HHS_SENDERS = frozenset({SenderKind.hospital_or_clinic, SenderKind.pharmacy, SenderKind.insurer})
NO_INTERPRETER_SENDERS = frozenset({SenderKind.landlord, SenderKind.court, SenderKind.school})
TEMPLATE = (
    "Hello. I speak {language}. I am here about: {document}. I need help with: {need}. "
    "Please speak slowly or write it down. Thank you."
)
GENERIC_TEMPLATE = (
    "Hello. I speak {language}. I need help with: {need}. Please speak slowly or write it down. "
    "Thank you."
)

PLAIN_DOCUMENT: Mapping[DocumentType, str] = {
    DT.uscis_receipt: "a USCIS receipt notice", DT.uscis_rfe: "a USCIS request for evidence",
    DT.uscis_noid: "a USCIS notice of intent to deny",
    DT.uscis_biometrics: "a USCIS fingerprint appointment notice",
    DT.uscis_interview: "a USCIS interview notice", DT.uscis_approval: "a USCIS approval notice",
    DT.uscis_denial: "a USCIS decision letter", DT.nta: "a Notice to Appear",
    DT.hearing_notice: "an immigration court hearing notice",
    DT.ij_decision: "an immigration judge's decision",
    DT.bia_notice: "a Board of Immigration Appeals notice", DT.ice_checkin: "an ICE check-in paper",
    DT.ead_related: "a work permit paper", DT.green_card_related: "a Green Card paper",
    DT.tps_related: "a Temporary Protected Status paper",
    DT.asylum_fee_notice: "an asylum fee notice", DT.parole_related: "a parole paper",
    DT.medical_bill: "a medical bill", DT.eob: "an insurance statement",
    DT.insurance_denial: "an insurance denial letter",
    DT.prior_auth: "a prior authorization letter", DT.lab_result: "a lab test report",
    DT.prescription_label: "a medicine label",
    DT.discharge_instructions: "hospital discharge instructions",
    DT.vaccine_record: "a vaccine record", DT.appointment_reminder: "an appointment reminder",
    DT.medicaid_renewal: "a Medicaid letter", DT.snap_notice: "a SNAP notice",
    DT.wic_notice: "a WIC notice", DT.ssa_letter: "a Social Security letter",
    DT.pay_or_quit: "a notice from my landlord",
    DT.eviction_summons: "a court paper about eviction",
    DT.lease: "a lease", DT.rent_increase: "a rent increase notice",
    DT.section8_recert: "a housing voucher paper", DT.utility_shutoff: "a utility shutoff notice",
    DT.school_enrollment: "a school enrollment paper",
    DT.immunization_notice: "a school vaccine notice",
    DT.iep_504_notice: "a school meeting notice", DT.school_meals: "a school meals letter",
    DT.report_card: "a report card", DT.w2_1099: "a tax form from my employer",
    DT.i9: "a work eligibility form (I-9)", DT.offer_letter: "a job offer letter",
    DT.pay_stub: "a pay stub", DT.irs_notice: "an IRS letter", DT.itin: "an ITIN letter",
    DT.jury_summons: "a jury summons", DT.traffic_court: "a traffic court notice",
    DT.other_notice: "a letter", DT.unknown: "a paper",
}  # fmt: skip

NeedSource = Literal["ai", "template"]
ClerkTranslate = Callable[[str], Awaitable[str | None]]
"""``async translate(english_card) -> str | None`` (task ``clerk_translate``; ``None`` = failed)."""


class ClerkRules(Protocol):
    """The ``RulesRepo`` surface this module reads (BUILD_PLAN §4.1)."""

    def clerk_need(self, doc_type: DocumentType) -> str: ...


def cut_at_word(text: str, limit: int = MAX_NEED_CHARS) -> str:
    """``text`` shortened to ≤ ``limit`` characters at the last word boundary (``""`` if none)."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit + 1]
    space = cut.rfind(" ")
    return cut[:space].rstrip(" ,;:—-") if space > 0 else ""


def template_need_line(rules: ClerkRules, document_type: DocumentType, t: Translator) -> str:
    """The fixed need line for the type: YAML text, else its pack key, else ``clerk.generic_need``.
    """
    text = rules.clerk_need(document_type)
    if text:
        return text
    key_of = getattr(rules, "clerk_need_key", None)
    key = key_of(document_type) if callable(key_of) else None
    return t(str(key) if key else GENERIC_NEED_KEY)


def document_phrase(document_type: DocumentType, sender_as_written: str | None) -> str:
    """"a Medicaid letter from Virginia Department of Medical Assistance Services"."""
    plain = PLAIN_DOCUMENT.get(document_type, "a paper")
    sender = re.sub(r"\s+", " ", (sender_as_written or "")).strip()
    if not sender:
        return plain
    return f"{plain} from {cut_at_word(sender, MAX_SENDER_CHARS) or sender[:MAX_SENDER_CHARS]}"


def checked_sender(sender_as_written: str | None, scrubber: ContactScrubber | None) -> str | None:
    """The sender for the card: ``None`` when the contact filter would change any part of it."""
    sender = re.sub(r"\s+", " ", (sender_as_written or "")).strip()
    if not sender:
        return None
    if scrubber is not None and scrubber.would_change(sender):
        return None
    return sender


def _clean_need(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(".").strip()


def choose_need_line(
    clerk_need_en: str | None,
    template_line: str,
    *,
    scrubber: ContactScrubber | None = None,
    hedged: bool = False,
) -> tuple[str, NeedSource]:
    """(need line, ``"ai"``/``"template"``) per D-18: contact filter, phrasing lint, 200 chars."""
    fallback = _clean_need(template_line)
    if hedged or not clerk_need_en or not clerk_need_en.strip():
        return fallback, "template"
    candidate = _clean_need(clerk_need_en)
    if scrubber is not None and (
        scrubber.would_change(candidate) or scrubber.marker in candidate
    ):
        return fallback, "template"
    if lint_sentence(candidate) or has_contact(candidate):
        return fallback, "template"
    cut = cut_at_word(candidate)
    if not cut:
        return fallback, "template"
    return cut, "ai"


def wants_interpreter_line(
    document_type: DocumentType,
    sender_kind: SenderKind,
    *,
    first_resource_hhs_funded: bool = False,
) -> bool:
    """D-18: HHS-funded resource or sender, or a Medicaid renewal; never landlord/court/school."""
    if sender_kind in NO_INTERPRETER_SENDERS:
        return False
    return (
        first_resource_hhs_funded
        or sender_kind in HHS_SENDERS
        or document_type is DocumentType.medicaid_renewal
    )


@dataclass
class ClerkOutcome:
    """``build_clerk_message`` result: the contract ``ClerkMessage`` plus warnings to merge."""

    message: ClerkMessage
    warnings: list[WarningCode] = field(default_factory=list)


async def build_clerk_message(
    *,
    language_name_en: str,
    document_type: DocumentType,
    sender_as_written: str | None,
    sender_kind: SenderKind,
    clerk_need_en: str | None,
    template_line: str,
    target_language: str,
    scrubber: ContactScrubber | None = None,
    hedged: bool = False,
    first_resource_hhs_funded: bool = False,
    translate: ClerkTranslate | None = None,
    t: Translator | None = None,
) -> ClerkOutcome:
    """Compose the clerk card. ``template_line`` = ``template_need_line(rules, type, t)``;
    ``hedged`` = the phrasing step replaced ``clerk_need_en``; ``translate`` = the optional
    ``clerk_translate`` call (its output is contact-scrubbed with ``scrubber``). The sender is
    dropped from the card when ``scrubber`` would replace any part of it (``checked_sender``).
    ``t`` = ``t_server`` for the target language: when the translation fails, ``translated`` is
    ``clerk.generic_card`` in that language with the English need line (AI_PROMPTS §5.5.4)."""
    need, source = choose_need_line(
        clerk_need_en, template_line, scrubber=scrubber, hedged=hedged
    )
    english = TEMPLATE.format(
        language=language_name_en.strip() or "English",
        document=document_phrase(document_type, checked_sender(sender_as_written, scrubber)),
        need=need,
    )
    keys = (
        [INTERPRETER_KEY]
        if wants_interpreter_line(
            document_type, sender_kind, first_resource_hhs_funded=first_resource_hhs_funded
        )
        else []
    )
    warnings: list[WarningCode] = []
    translated = english
    if target_language.split("-")[0].lower() != "en":
        value: str | None = None
        if translate is not None:
            try:
                value = await translate(english)
            except Exception:  # quota, QA or upstream failure → English card + warning
                value = None
        if value and value.strip():
            translated = scrubber.scrub(value.strip()) if scrubber is not None else value.strip()
        else:
            if t is not None:  # the pack's fixed pieces + the untranslated English need line
                language = language_name_en.strip() or "English"
                translated = t(GENERIC_CARD_KEY, language=language, need=need)
            warnings.append(WarningCode.translation_partial)
    message = ClerkMessage(
        english=english, translated=translated, need_line_source=source,
        appended_line_keys=keys,
    )  # fmt: skip
    return ClerkOutcome(message, warnings)


def generic_card(language_name_en: str, need: str) -> str:
    """PRODUCT_SPEC §8.4 generic card (no analysis); no interpreter line is ever appended."""
    return GENERIC_TEMPLATE.format(language=language_name_en, need=_clean_need(need))


__all__ = [
    "GENERIC_CARD_KEY",
    "GENERIC_NEED_KEY",
    "HHS_SENDERS",
    "INTERPRETER_KEY",
    "MAX_NEED_CHARS",
    "PLAIN_DOCUMENT",
    "TEMPLATE",
    "ClerkOutcome",
    "ClerkRules",
    "ClerkTranslate",
    "build_clerk_message",
    "checked_sender",
    "choose_need_line",
    "cut_at_word",
    "document_phrase",
    "generic_card",
    "template_need_line",
    "wants_interpreter_line",
]
