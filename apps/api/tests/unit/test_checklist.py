"""Checklist builder tests (RESOURCE_DB §4.4, §4.8, §6.8, §10; BUILD_PLAN §5.4 step 3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from proxyhealth_api.contracts.enums import DocumentType
from proxyhealth_api.contracts.resources import ChecklistItem
from proxyhealth_api.resources import checklist
from proxyhealth_api.resources.checklist import PrepareLoadError, build, load_prepare, merge_keys
from tests.unit._fixtures_wp3 import RULES_DIR, make_resource, real_meta, real_repo


def keys_of(items: list[ChecklistItem]) -> list[str]:
    return [i.key for i in items]


def test_merge_order_resource_first_then_document() -> None:
    assert merge_keys(["a", "b"], ["c", "d"]) == ["a", "b", "c", "d"]


def test_merge_dedups_keeping_first_position() -> None:
    assert merge_keys(["bring_notice", "b"], ["b", "bring_notice", "c"]) == [
        "bring_notice",
        "b",
        "c",
    ]


def test_merge_caps_at_eight() -> None:
    merged = merge_keys([f"r{i}" for i in range(6)], [f"d{i}" for i in range(6)])
    assert len(merged) == checklist.MAX_ITEMS == 8
    assert merged[:6] == [f"r{i}" for i in range(6)]
    assert merged[6:] == ["d0", "d1"]


def test_build_uses_prepare_yaml_for_document_type() -> None:
    res = make_resource(prepare_checklist_keys=["bring_proof_income", "bring_the_bill"])
    items = build(
        res,
        DocumentType.medical_bill,
        checklist_text=real_meta().checklist,
        prepare=real_repo().prepare_map(),
    )
    assert keys_of(items) == [
        "bring_proof_income",
        "bring_the_bill",
        "bring_itemized_bill_request",
        "bring_insurance_card",
    ]
    assert all(i.text_en == real_meta().checklist[i.key] for i in items)


def test_unknown_or_missing_doc_type_gives_resource_keys_only() -> None:
    res = make_resource(prepare_checklist_keys=["bring_photo_id"])
    prepare = real_repo().prepare_map()
    assert DocumentType.unknown not in prepare
    for doc_type in (None, DocumentType.unknown):
        items = build(res, doc_type, checklist_text=real_meta().checklist, prepare=prepare)
        assert keys_of(items) == ["bring_photo_id"]


def test_build_skips_keys_without_english_text() -> None:
    res = make_resource(prepare_checklist_keys=["bring_photo_id"])
    items = build(res, None, checklist_text={}, prepare={})
    assert items == []


def test_seed_prepare_yaml_loads_and_keys_exist_in_meta() -> None:
    prepare = load_prepare(RULES_DIR / "prepare.yaml", allowed_keys=real_meta().checklist)
    assert len(prepare) == 28
    assert prepare[DocumentType.jury_summons] == ["bring_the_summons"]
    assert real_repo().prepare_items(DocumentType.eviction_summons) == [
        "bring_the_summons",
        "bring_lease",
        "bring_proof_rent_utilities",
    ]


def test_prepare_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_prepare(tmp_path / "prepare.yaml") == {}


@pytest.mark.parametrize(
    ("body", "line", "fragment"),
    [
        ("uscis_rfe: [bring_notice]\nnot_a_type: [bring_notice]\n", 2, "unknown document type"),
        ("uscis_rfe: [bring_notice, bring_unicorn]\n", 1, "unknown checklist keys"),
        ("uscis_rfe: bring_notice\n", 1, "must be a list"),
        ("uscis_rfe: [bring_notice\n", 2, "YAML syntax error"),
    ],
)
def test_prepare_errors_name_path_and_line(
    tmp_path: Path, body: str, line: int, fragment: str
) -> None:
    path = tmp_path / "prepare.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(PrepareLoadError) as err:
        load_prepare(path, allowed_keys=real_meta().checklist)
    assert str(err.value).startswith(f"{path}:{line}:")
    assert fragment in str(err.value)
