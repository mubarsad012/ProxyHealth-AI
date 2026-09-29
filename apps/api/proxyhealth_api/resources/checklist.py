"""Prepare-checklist builder (RESOURCE_DB §4.4, §4.8, §6.8).

``build()`` merges a resource's own ``prepare_checklist_keys`` with the document-type items from
``data/rules/prepare.yaml`` (resource items first, then document items), de-duplicates while
keeping order and caps the list at ``MAX_ITEMS``. Every key renders as ``prepare.<key>`` on the
client; the English ``text_en`` comes from ``_meta.yaml.checklist``.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from pathlib import Path

import yaml

from proxyhealth_api.contracts.enums import DocumentType
from proxyhealth_api.contracts.resources import ChecklistItem, Resource

MAX_ITEMS = 8


class PrepareLoadError(Exception):
    """``prepare.yaml`` is present but invalid; the message starts with ``<path>:<line>:``."""


def _key_lines(text: str) -> dict[str, int]:
    """1-based line of every top-level mapping key (for ``path:line`` messages)."""
    node = yaml.compose(text)
    if node is None or not isinstance(node, yaml.MappingNode):
        return {}
    return {str(key.value): key.start_mark.line + 1 for key, _ in node.value}


def load_prepare(
    path: Path, *, allowed_keys: Collection[str] | None = None
) -> dict[DocumentType, list[str]]:
    """Parse ``prepare.yaml``: ``{document_type: [checklist_key, …]}``.

    A missing file yields ``{}`` (callers log the warning). Unknown document types, non-list
    values and — when ``allowed_keys`` is given — keys outside ``_meta.yaml.checklist`` raise
    ``PrepareLoadError`` naming the file and line.
    """
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
        lines = _key_lines(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 1 if mark is not None else 1
        raise PrepareLoadError(f"{path}:{line}: YAML syntax error: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise PrepareLoadError(f"{path}:1: prepare.yaml must map document types to key lists")
    out: dict[DocumentType, list[str]] = {}
    for raw_key, values in data.items():
        line = lines.get(str(raw_key), 1)
        try:
            doc_type = DocumentType(str(raw_key))
        except ValueError as exc:
            raise PrepareLoadError(f"{path}:{line}: unknown document type {raw_key!r}") from exc
        if values is None:
            values = []
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise PrepareLoadError(f"{path}:{line}: {raw_key}: value must be a list of keys")
        keys = [str(v) for v in values]
        if allowed_keys is not None:
            unknown = [k for k in keys if k not in allowed_keys]
            if unknown:
                raise PrepareLoadError(
                    f"{path}:{line}: {raw_key}: unknown checklist keys {unknown}"
                )
        if doc_type in out:
            raise PrepareLoadError(f"{path}:{line}: duplicate document type {raw_key!r}")
        out[doc_type] = keys
    return out


def merge_keys(
    resource_keys: Collection[str], document_keys: Collection[str], *, limit: int = MAX_ITEMS
) -> list[str]:
    """Resource items first, then document items; de-duplicated in order; at most ``limit``."""
    seen: set[str] = set()
    merged: list[str] = []
    for key in (*resource_keys, *document_keys):
        if key in seen:
            continue
        seen.add(key)
        merged.append(key)
        if len(merged) >= limit:
            break
    return merged


def build(
    resource: Resource,
    document_type: DocumentType | None,
    *,
    checklist_text: Mapping[str, str],
    prepare: Mapping[DocumentType, list[str]],
) -> list[ChecklistItem]:
    """RESOURCE_DB §6.8: ``ChecklistItem{key, text_en}`` list for one match (≤ ``MAX_ITEMS``).

    Keys without an English text in ``_meta.yaml.checklist`` are skipped (the loader already
    refuses such keys in the seed, so this only guards hand-built repos in tests).
    """
    document_keys: Collection[str] = prepare.get(document_type, []) if document_type else []
    items: list[ChecklistItem] = []
    for key in merge_keys(resource.prepare_checklist_keys, document_keys):
        text = checklist_text.get(key)
        if text is None:
            continue
        items.append(ChecklistItem(key=key, text_en=text))
    return items


__all__ = ["MAX_ITEMS", "PrepareLoadError", "build", "load_prepare", "merge_keys"]
