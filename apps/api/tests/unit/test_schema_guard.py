"""``ai/schema_guard`` rules (D-06) and every ``contracts/model_out.py`` class (BUILD_PLAN §5.1)."""

from enum import StrEnum
from typing import Any

import pytest
from pydantic import BaseModel, create_model

from proxyhealth_api.ai.schema_guard import (
    MAX_DEPTH,
    MAX_ENUM_VALUES,
    SchemaGuardError,
    assert_subset_safe,
    is_subset_safe,
)
from proxyhealth_api.contracts import model_out
from proxyhealth_api.contracts.common import TextBlock
from proxyhealth_api.contracts.enums import Confidence, DocumentType, ResourceTag


def _classes_defined_in_model_out() -> list[type[BaseModel]]:
    return [
        obj
        for obj in vars(model_out).values()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and obj.__module__ == model_out.__name__
    ]


@pytest.mark.parametrize("cls", _classes_defined_in_model_out(), ids=lambda c: str(c.__name__))
def test_every_model_out_class_is_subset_safe(cls: type[BaseModel]) -> None:
    assert_subset_safe(cls)


@pytest.mark.parametrize("cls", model_out.MODEL_OUT_CLASSES, ids=lambda c: str(c.__name__))
def test_registered_response_schemas_are_subset_safe(cls: type[BaseModel]) -> None:
    assert is_subset_safe(cls)


def test_registry_lists_every_public_top_level_schema() -> None:
    public = {name for name in model_out.__all__ if name.endswith("Out")}
    registered = {cls.__name__ for cls in model_out.MODEL_OUT_CLASSES}
    nested_items = {"DemandOut", "PlanStepOut", "RedFlagOut"}
    assert public - nested_items == registered


def test_shared_contract_items_reused_by_model_out_pass() -> None:
    assert_subset_safe(TextBlock)


def test_bbox_of_text_block_is_four_floats() -> None:
    schema = TextBlock.model_json_schema()["properties"]["bbox"]
    array = next(b for b in schema["anyOf"] if b.get("type") == "array")
    assert array["items"] == {"type": "number"}
    assert (array["minItems"], array["maxItems"]) == (4, 4)


def test_explain_out_is_analysis_minus_seeing_fields() -> None:
    analysis = set(model_out.AnalysisModelOut.model_fields)
    explain = set(model_out.ExplainOut.model_fields)
    assert analysis - explain == {"blocks", "legibility", "readable_reason"}
    assert "translated_pages" in explain
    assert set(model_out.TranscriptOut.model_fields) == {
        "blocks",
        "detected_language",
        "legibility",
        "readable_reason",
    }


def test_language_pack_strings_are_a_list_of_pairs() -> None:
    props = model_out.LanguagePackModelOut.model_json_schema()["properties"]
    assert props["strings"]["type"] == "array"
    assert set(model_out.KeyValue.model_fields) == {"key", "value"}


# --- negative cases -------------------------------------------------------------------------


def test_rejects_dict_field() -> None:
    class M(BaseModel):
        strings: dict[str, str]

    with pytest.raises(SchemaGuardError, match="additionalProperties"):
        assert_subset_safe(M)


def test_rejects_any_field() -> None:
    class M(BaseModel):
        payload: Any

    with pytest.raises(SchemaGuardError, match="Any"):
        assert_subset_safe(M)


def test_rejects_recursive_model() -> None:
    class Node(BaseModel):
        name: str
        children: list["Node"]

    Node.model_rebuild()
    with pytest.raises(SchemaGuardError, match="recursive"):
        assert_subset_safe(Node)


def test_rejects_union_of_two_types() -> None:
    class M(BaseModel):
        value: str | int

    with pytest.raises(SchemaGuardError, match="X \\| None"):
        assert_subset_safe(M)


def test_rejects_union_of_two_types_plus_none() -> None:
    class M(BaseModel):
        value: str | int | None

    with pytest.raises(SchemaGuardError, match="X \\| None"):
        assert_subset_safe(M)


def test_accepts_optional_scalar_and_optional_enum() -> None:
    class M(BaseModel):
        note: str | None
        confidence: Confidence | None

    assert_subset_safe(M)


def test_rejects_enum_with_more_than_64_values() -> None:
    names = [f"v{i}" for i in range(MAX_ENUM_VALUES + 1)]
    big = StrEnum("Big", names)  # type: ignore[misc]
    model = create_model("M", kind=(big, ...))

    with pytest.raises(SchemaGuardError, match="65 values"):
        assert_subset_safe(model)


def test_contract_enums_used_by_model_out_fit_the_cap() -> None:
    assert len(DocumentType) <= MAX_ENUM_VALUES
    assert len(ResourceTag) <= MAX_ENUM_VALUES


def test_depth_three_is_allowed() -> None:
    class Leaf(BaseModel):
        words: list[str]

    class Root(BaseModel):
        items: list[Leaf]

    assert_subset_safe(Root)
    assert MAX_DEPTH == 3


def test_depth_four_is_rejected() -> None:
    class Inner(BaseModel):
        text: str

    class Leaf(BaseModel):
        inner: list[Inner]

    class Root(BaseModel):
        items: list[Leaf]

    with pytest.raises(SchemaGuardError, match="depth 4"):
        assert_subset_safe(Root)


def test_rejects_bbox_without_fixed_length() -> None:
    class M(BaseModel):
        bbox: list[float]

    with pytest.raises(SchemaGuardError, match="bbox"):
        assert_subset_safe(M)


def test_rejects_bbox_of_wrong_item_type() -> None:
    class M(BaseModel):
        bbox: str

    with pytest.raises(SchemaGuardError, match="bbox"):
        assert_subset_safe(M)


def test_rejects_tuple_field() -> None:
    class M(BaseModel):
        pair: tuple[float, float]

    with pytest.raises(SchemaGuardError, match="prefixItems"):
        assert_subset_safe(M)


def test_error_names_model_and_path() -> None:
    class Inner(BaseModel):
        extra: dict[str, int]

    class Outer(BaseModel):
        inner: Inner

    with pytest.raises(SchemaGuardError) as info:
        assert_subset_safe(Outer)
    assert info.value.model_name == "Outer"
    assert info.value.path == "Outer.inner.extra"
