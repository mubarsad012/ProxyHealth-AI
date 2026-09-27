"""Structured-output schema guard (D-06; API_CONTRACT §4; AI_PROMPTS §4; BUILD_PLAN §5.1 step 4).

Gemini's ``response_schema`` accepts only a JSON-Schema subset and rejects deeply nested schemas
(``docs/research/gemini.md``). ``assert_subset_safe`` walks a Pydantic model's JSON schema and
raises ``SchemaGuardError`` unless every rule below holds:

* nesting depth ≤ 3 — root object (0) → list (1) → object (2) → scalars or lists of scalars (3);
* no ``dict`` / free-form object (``additionalProperties``), no ``Any`` (empty schema), no tuples;
* no recursive ``$ref`` chains;
* unions only of the form ``X | None`` (``anyOf`` with exactly one non-null branch);
* enums (and ``Literal``) with ≤ 64 values;
* every property named ``bbox`` is ``list[float]`` of exactly four items (optionally ``| None``).

The walk runs on ``model.model_json_schema()`` so it checks exactly what the SDK sends upstream.
"""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

MAX_DEPTH = 3
MAX_ENUM_VALUES = 64
BBOX_LENGTH = 4

_ALLOWED_TYPES = frozenset({"string", "integer", "number", "boolean", "array", "object", "null"})
_FORBIDDEN_KEYWORDS = frozenset(
    {
        "oneOf",
        "allOf",
        "not",
        "if",
        "then",
        "else",
        "patternProperties",
        "prefixItems",
        "dependentSchemas",
        "unevaluatedProperties",
        "unevaluatedItems",
    }
)


class SchemaGuardError(ValueError):
    """A model-output schema violates the structured-output subset (D-06)."""

    def __init__(self, model_name: str, path: str, reason: str) -> None:
        self.model_name = model_name
        self.path = path
        self.reason = reason
        super().__init__(f"{model_name}: {path}: {reason}")


class _Walker:
    def __init__(
        self,
        model_name: str,
        defs: Mapping[str, Any],
        max_depth: int,
        max_enum_values: int,
    ) -> None:
        self._model_name = model_name
        self._defs = defs
        self._max_depth = max_depth
        self._max_enum_values = max_enum_values

    def fail(self, path: str, reason: str) -> SchemaGuardError:
        return SchemaGuardError(self._model_name, path, reason)

    def check(
        self,
        node: Any,
        path: str,
        depth: int,
        stack: tuple[str, ...],
        prop_name: str | None = None,
    ) -> None:
        if node is True or node == {}:
            raise self.fail(path, "untyped schema (Any) is not allowed")
        if not isinstance(node, Mapping):
            raise self.fail(path, f"unexpected schema node {node!r}")
        forbidden = _FORBIDDEN_KEYWORDS.intersection(node.keys())
        if forbidden:
            raise self.fail(path, f"unsupported keyword(s): {', '.join(sorted(forbidden))}")

        if "$ref" in node:
            name = str(node["$ref"]).rsplit("/", 1)[-1]
            if name in stack:
                raise self.fail(path, f"recursive reference to {name}")
            target = self._defs.get(name)
            if target is None:
                raise self.fail(path, f"unresolvable $ref {node['$ref']!r}")
            self.check(target, path, depth, (*stack, name), prop_name)
            return

        if "anyOf" in node:
            branches = list(node["anyOf"])
            non_null = [
                b for b in branches if not (isinstance(b, Mapping) and b.get("type") == "null")
            ]
            if len(branches) != 2 or len(non_null) != 1:
                raise self.fail(path, "unions must be exactly `X | None`")
            self.check(non_null[0], path, depth, stack, prop_name)
            return

        if "enum" in node:
            values = list(node["enum"])
            if len(values) > self._max_enum_values:
                raise self.fail(
                    path, f"enum has {len(values)} values (max {self._max_enum_values})"
                )

        type_ = node.get("type")
        if type_ is None:
            if "enum" in node or "const" in node:
                return
            raise self.fail(path, "schema without `type` (Any) is not allowed")
        if not isinstance(type_, str) or type_ not in _ALLOWED_TYPES:
            raise self.fail(path, f"unsupported type {type_!r}")

        if prop_name == "bbox":
            self._check_bbox(node, path)

        if type_ == "object":
            self._check_object(node, path, depth, stack)
        elif type_ == "array":
            self._check_array(node, path, depth, stack)

    def _check_object(
        self, node: Mapping[str, Any], path: str, depth: int, stack: tuple[str, ...]
    ) -> None:
        if depth > self._max_depth:
            raise self.fail(path, f"object nested at depth {depth} (max {self._max_depth})")
        extra = node.get("additionalProperties")
        if extra not in (None, False):
            raise self.fail(path, "free-form dict / additionalProperties is not allowed")
        properties = node.get("properties")
        if not isinstance(properties, Mapping) or not properties:
            raise self.fail(path, "object without declared properties is not allowed")
        for name, prop in properties.items():
            self.check(prop, f"{path}.{name}", depth + 1, stack, prop_name=str(name))

    def _check_array(
        self, node: Mapping[str, Any], path: str, depth: int, stack: tuple[str, ...]
    ) -> None:
        if depth > self._max_depth:
            raise self.fail(path, f"array nested at depth {depth} (max {self._max_depth})")
        items = node.get("items")
        if items is None:
            raise self.fail(path, "array without `items` (Any) is not allowed")
        self.check(items, f"{path}[]", depth + 1, stack)

    def _check_bbox(self, node: Mapping[str, Any], path: str) -> None:
        items = node.get("items")
        ok = (
            node.get("type") == "array"
            and isinstance(items, Mapping)
            and items.get("type") == "number"
            and node.get("minItems") == BBOX_LENGTH
            and node.get("maxItems") == BBOX_LENGTH
        )
        if not ok:
            raise self.fail(path, "bbox must be `list[float]` of exactly 4 items")


def assert_subset_safe(
    model: type[BaseModel],
    *,
    max_depth: int = MAX_DEPTH,
    max_enum_values: int = MAX_ENUM_VALUES,
) -> None:
    """Raise ``SchemaGuardError`` unless the model's JSON schema fits the D-06 subset."""
    schema: dict[str, Any] = model.model_json_schema()
    defs: Mapping[str, Any] = schema.get("$defs", {})
    walker = _Walker(model.__name__, defs, max_depth, max_enum_values)
    root = {k: v for k, v in schema.items() if k != "$defs"}
    walker.check(root, model.__name__, 0, (model.__name__,))


def is_subset_safe(model: type[BaseModel]) -> bool:
    """``True`` when ``assert_subset_safe`` would not raise."""
    try:
        assert_subset_safe(model)
    except SchemaGuardError:
        return False
    return True
