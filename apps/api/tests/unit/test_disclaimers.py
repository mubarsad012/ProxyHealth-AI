"""WP2 — ``analysis/disclaimers.py`` (D-17; AI_PROMPTS §11.11; TAXONOMY §3.14)."""

from __future__ import annotations

import pytest

from proxyhealth_api.analysis import disclaimers as dc
from proxyhealth_api.contracts.common import ModelMeta
from proxyhealth_api.contracts.enums import (
    AnalysisMode,
    DataUseTier,
    DisclaimerKind,
    DocumentCategory,
    ModelQuality,
    ModelTier,
    Provider,
    WarningCode,
)

DK = DisclaimerKind
C = DocumentCategory


@pytest.mark.parametrize(
    ("category", "kind"),
    [
        (C.immigration, DK.legal_information_only), (C.court, DK.legal_information_only),
        (C.civic, DK.legal_information_only), (C.employment, DK.legal_information_only),
        (C.medical, DK.medical_information_only), (C.benefits, DK.benefits_information_only),
        (C.housing, DK.housing_information_only), (C.school, DK.general_information),
        (C.tax, DK.general_information), (C.other, DK.general_information),
        (None, DK.general_information),
    ],
)  # fmt: skip
def test_primary_disclaimer_by_category(category: DocumentCategory | None, kind: DK) -> None:
    assert dc.disclaimer_kind(category) is kind
    assert set(dc.PRIMARY_BY_CATEGORY) == set(DocumentCategory)


def meta(quality: ModelQuality = ModelQuality.full, tier: DataUseTier = DataUseTier.paid,
         demo: bool = False) -> ModelMeta:  # fmt: skip
    return ModelMeta(
        provider=Provider.mock, tier=ModelTier.pro, model_id="mock", thinking_level=None,
        quality=quality, analysis_mode=AnalysisMode.mock, data_use_tier=tier, demo=demo,
        latency_ms=0,
    )  # fmt: skip


def test_secondary_disclaimers() -> None:
    plain = dc.secondary_disclaimers(
        detected_language="en", target_language="en", pack_machine_translated=False,
        model_meta=meta(),
    )  # fmt: skip
    assert plain == [DK.ai_generated, DK.verify_with_sender]
    everything = dc.secondary_disclaimers(
        detected_language="en", target_language="prs", pack_machine_translated=True,
        model_meta=meta(ModelQuality.degraded, DataUseTier.mixed, demo=True),
    )  # fmt: skip
    assert everything == [
        DK.ai_generated, DK.verify_with_sender, DK.machine_translation, DK.degraded_model,
        DK.unpaid_tier_warning, DK.demo_sample,
    ]  # fmt: skip
    pack_only = dc.secondary_disclaimers(
        detected_language="es", target_language="es-MX", pack_machine_translated=True
    )
    assert DK.machine_translation in pack_only
    same = dc.secondary_disclaimers(
        detected_language="es", target_language="es-MX", pack_machine_translated=False
    )
    assert DK.machine_translation not in same


def test_language_differs_rule() -> None:
    assert dc.language_differs("es", "en")  # Spanish lease explained in English
    assert not dc.language_differs("en", "prs")  # English paper → no banner (translation normal)
    assert not dc.language_differs("es", "es-US")
    assert not dc.language_differs(None, "en")


def test_final_warnings_order_and_dedup() -> None:
    steps = [
        WarningCode.contacts_stripped, WarningCode.low_quality_image,
        WarningCode.contacts_stripped, WarningCode.blocked_partial,
    ]  # fmt: skip
    out = dc.final_warnings(
        steps, translation_partial=True, detected_language="es", target_language="en",
        degraded=True, data_use_tier=DataUseTier.unpaid, demo=True,
    )  # fmt: skip
    assert out == [
        WarningCode.contacts_stripped, WarningCode.low_quality_image,
        WarningCode.translation_partial, WarningCode.document_language_differs,
        WarningCode.degraded_model, WarningCode.unpaid_tier, WarningCode.demo_sample,
    ]  # fmt: skip
    assert dc.final_warnings([], data_use_tier=DataUseTier.paid) == []
