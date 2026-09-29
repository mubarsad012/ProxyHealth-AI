"""Disclaimers and the final warnings list (D-17; AI_PROMPTS §11.11; TAXONOMY §3.14).

The model never writes a disclaimer: ``disclaimer_kind`` comes from the document category and
``disclaimers[]`` from facts about the call (translation, degraded model, data-use tier, demo).
The client renders the fixed copy (``disclaimer.*`` / ``banner.*`` keys). ``final_warnings`` is
the ordered, de-duplicated union of every step's warnings plus the call-level ones.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from proxyhealth_api.contracts.common import ModelMeta
from proxyhealth_api.contracts.enums import (
    DataUseTier,
    DisclaimerKind,
    DocumentCategory,
    ModelQuality,
    WarningCode,
)

DK = DisclaimerKind
PRIMARY_BY_CATEGORY: Mapping[DocumentCategory, DisclaimerKind] = {
    DocumentCategory.immigration: DK.legal_information_only,
    DocumentCategory.court: DK.legal_information_only,
    DocumentCategory.civic: DK.legal_information_only,
    DocumentCategory.employment: DK.legal_information_only,
    DocumentCategory.medical: DK.medical_information_only,
    DocumentCategory.benefits: DK.benefits_information_only,
    DocumentCategory.housing: DK.housing_information_only,
    DocumentCategory.school: DK.general_information,
    DocumentCategory.tax: DK.general_information,
    DocumentCategory.other: DK.general_information,
}
UNPAID_TIERS = frozenset({DataUseTier.unpaid, DataUseTier.mixed})
# Order of the call-level warnings appended after the step warnings.
_CALL_WARNINGS = (
    WarningCode.translation_partial,
    WarningCode.document_language_differs,
    WarningCode.degraded_model,
    WarningCode.unpaid_tier,
    WarningCode.demo_sample,
)


def disclaimer_kind(category: DocumentCategory | None) -> DisclaimerKind:
    """Primary disclaimer by category (troubleshoot uses ``general_information``)."""
    if category is None:
        return DK.general_information
    return PRIMARY_BY_CATEGORY.get(category, DK.general_information)


def _base(tag: str | None) -> str:
    return (tag or "").split("-")[0].lower()


def language_differs(detected_language: str | None, target_language: str | None) -> bool:
    """TAXONOMY §3.14: the paper's language differs from the target language **and** from ``en``."""
    detected, target = _base(detected_language), _base(target_language)
    return bool(detected) and detected != target and detected != "en"


def secondary_disclaimers(
    *,
    detected_language: str | None,
    target_language: str,
    pack_machine_translated: bool,
    model_meta: ModelMeta | None = None,
    data_use_tier: DataUseTier | None = None,
    degraded: bool | None = None,
    demo: bool | None = None,
) -> list[DisclaimerKind]:
    """``disclaimers[]``: always ``ai_generated`` + ``verify_with_sender``; ``machine_translation``
    when the explanation is not in the paper's language or the pack is machine translated;
    ``degraded_model``, ``unpaid_tier_warning``, ``demo_sample`` as applicable. ``degraded`` /
    ``demo`` / ``data_use_tier`` default to ``model_meta``'s values."""
    if model_meta is not None:
        degraded = model_meta.quality is ModelQuality.degraded if degraded is None else degraded
        demo = model_meta.demo if demo is None else demo
        data_use_tier = data_use_tier or model_meta.data_use_tier
    out = [DK.ai_generated, DK.verify_with_sender]
    translated = bool(detected_language) and _base(detected_language) != _base(target_language)
    if translated or pack_machine_translated:
        out.append(DK.machine_translation)
    if degraded:
        out.append(DK.degraded_model)
    if data_use_tier in UNPAID_TIERS:
        out.append(DK.unpaid_tier_warning)
    if demo:
        out.append(DK.demo_sample)
    return out


def final_warnings(
    step_warnings: Iterable[WarningCode],
    *,
    translation_partial: bool = False,
    detected_language: str | None = None,
    target_language: str | None = None,
    degraded: bool = False,
    data_use_tier: DataUseTier | None = None,
    demo: bool = False,
) -> list[WarningCode]:
    """Ordered, de-duplicated ``warnings[]``: step warnings in the order they were raised, then
    ``translation_partial``, ``document_language_differs``, ``degraded_model``, ``unpaid_tier``,
    ``demo_sample``. ``blocked_partial`` is reserved (never produced in v1)."""
    flags = {
        WarningCode.translation_partial: translation_partial,
        WarningCode.document_language_differs: language_differs(detected_language,
                                                                  target_language),
        WarningCode.degraded_model: degraded,
        WarningCode.unpaid_tier: data_use_tier in UNPAID_TIERS,
        WarningCode.demo_sample: demo,
    }  # fmt: skip
    out: list[WarningCode] = []
    for w in step_warnings:
        if w is not WarningCode.blocked_partial and w not in out:
            out.append(w)
    for w in _CALL_WARNINGS:
        if flags[w] and w not in out:
            out.append(w)
    return out


__all__ = [
    "PRIMARY_BY_CATEGORY",
    "UNPAID_TIERS",
    "disclaimer_kind",
    "final_warnings",
    "language_differs",
    "secondary_disclaimers",
]
