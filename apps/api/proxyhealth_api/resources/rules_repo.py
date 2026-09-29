"""``RulesRepo`` (BUILD_PLAN §4.1; API_CONTRACT §3.10; D-11, D-18, D-20).

Loads WP2's ``data/rules/{deadlines,fixed_notices,clerk_needs}.yaml`` and WP3's
``data/rules/prepare.yaml``. A **missing** file is tolerated (warning, empty collection, version
``"0"``) because WP2 writes those files in parallel; a **present but invalid** file refuses boot
with ``RulesLoadError('<path>:<line>: …')`` like the resource loader does.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from proxyhealth_api.contracts.enums import DocumentType, RedFlagKind, Severity
from proxyhealth_api.contracts.rules import DeadlineRule
from proxyhealth_api.resources.checklist import PrepareLoadError, load_prepare

logger = logging.getLogger("proxyhealth.rules")

ANY_DOC_TYPE = "any"


class RulesLoadError(Exception):
    """Boot refusal for an invalid rules file; the message starts with ``<path>:<line>:``."""


@dataclass(frozen=True)
class FixedNotice:
    """One D-20 fixed notice. ``kind``/``severity``/``fixed_copy_key`` are the BUILD_PLAN §4.1
    fields; ``id``, ``document_types`` and ``when`` carry the rest of WP2's YAML row so
    ``analysis/fixed_notices.py`` can evaluate the condition grammar."""

    kind: RedFlagKind
    severity: Severity
    fixed_copy_key: str
    id: str = ""
    document_types: tuple[str, ...] = ()
    when: Any = "always"


@dataclass(frozen=True)
class ClerkNeed:
    """``clerk_needs.yaml`` value: fixed English text **or** a pack key (``{key: clerk.…}``)."""

    text: str = ""
    key: str | None = None


def _yaml_error(path: Path, exc: yaml.YAMLError) -> RulesLoadError:
    mark = getattr(exc, "problem_mark", None)
    line = mark.line + 1 if mark is not None else 1
    return RulesLoadError(f"{path}:{line}: YAML syntax error: {exc}")


def _item_lines(text: str, key: str) -> list[int]:
    """1-based start line of each item of the top-level sequence ``key`` (for messages)."""
    node = yaml.compose(text)
    if node is None or not isinstance(node, yaml.MappingNode):
        return []
    for k, v in node.value:
        if str(k.value) == key and isinstance(v, yaml.SequenceNode):
            return [child.start_mark.line + 1 for child in v.value]
    return []


def _read_mapping(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise _yaml_error(path, exc) from exc
    if data is None:
        return {}, text
    if not isinstance(data, dict):
        raise RulesLoadError(f"{path}:1: file must be a mapping")
    return {str(k): v for k, v in data.items()}, text


def load_deadlines(path: Path) -> tuple[list[DeadlineRule], str]:
    """``deadlines.yaml`` → (rules, rules_version). Missing file → ``([], "0")``."""
    if not path.is_file():
        logger.warning("deadlines.yaml missing at %s; /v1/rules serves an empty table", path)
        return [], "0"
    data, text = _read_mapping(path)
    raw_rules = data.get("rules") or []
    if not isinstance(raw_rules, list):
        raise RulesLoadError(f"{path}:1: 'rules' must be a list")
    lines = _item_lines(text, "rules")
    rules: list[DeadlineRule] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_rules):
        line = lines[index] if index < len(lines) else 1
        try:
            rule = DeadlineRule.model_validate(raw)
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first["loc"])
            raise RulesLoadError(f"{path}:{line}: {loc}: {first['msg']}") from exc
        if rule.id in seen:
            raise RulesLoadError(f"{path}:{line}: duplicate rule id {rule.id!r}")
        seen.add(rule.id)
        rules.append(rule)
    version = str(data.get("rules_version") or "0")
    return rules, version


def load_fixed_notices(path: Path) -> tuple[list[FixedNotice], str]:
    """``fixed_notices.yaml`` → (notices, version). Missing file → ``([], "0")``."""
    if not path.is_file():
        logger.warning("fixed_notices.yaml missing at %s; no fixed notices", path)
        return [], "0"
    data, text = _read_mapping(path)
    raw_notices = data.get("notices") or []
    if not isinstance(raw_notices, list):
        raise RulesLoadError(f"{path}:1: 'notices' must be a list")
    lines = _item_lines(text, "notices")
    notices: list[FixedNotice] = []
    for index, raw in enumerate(raw_notices):
        line = lines[index] if index < len(lines) else 1
        if not isinstance(raw, dict):
            raise RulesLoadError(f"{path}:{line}: notice must be a mapping")
        try:
            kind = RedFlagKind(str(raw["kind"]))
            severity = Severity(str(raw["severity"]))
        except (KeyError, ValueError) as exc:
            raise RulesLoadError(f"{path}:{line}: notice kind/severity invalid: {exc}") from exc
        key = str(raw.get("fixed_copy_key") or "")
        if not key.startswith("fixed."):
            raise RulesLoadError(f"{path}:{line}: fixed_copy_key must start with 'fixed.'")
        doc_types = raw.get("document_types") or []
        if not isinstance(doc_types, list) or not doc_types:
            raise RulesLoadError(f"{path}:{line}: document_types must be a non-empty list")
        for dt in doc_types:
            if str(dt) != ANY_DOC_TYPE:
                try:
                    DocumentType(str(dt))
                except ValueError as exc:
                    raise RulesLoadError(f"{path}:{line}: unknown document type {dt!r}") from exc
        notices.append(
            FixedNotice(
                kind=kind,
                severity=severity,
                fixed_copy_key=key,
                id=str(raw.get("id") or ""),
                document_types=tuple(str(dt) for dt in doc_types),
                when=raw.get("when", "always"),
            )
        )
    return notices, str(data.get("version") or "0")


def load_clerk_needs(path: Path) -> tuple[dict[DocumentType, ClerkNeed], str]:
    """``clerk_needs.yaml`` → (needs, version). Missing file → ``({}, "0")``."""
    if not path.is_file():
        logger.warning("clerk_needs.yaml missing at %s; clerk needs fall back to the pack", path)
        return {}, "0"
    data, _text = _read_mapping(path)
    raw_needs = data.get("needs") or {}
    if not isinstance(raw_needs, dict):
        raise RulesLoadError(f"{path}:1: 'needs' must be a mapping")
    needs: dict[DocumentType, ClerkNeed] = {}
    for raw_key, value in raw_needs.items():
        try:
            doc_type = DocumentType(str(raw_key))
        except ValueError as exc:
            raise RulesLoadError(f"{path}:1: unknown document type {raw_key!r}") from exc
        if isinstance(value, str):
            if len(value) > 200:
                raise RulesLoadError(f"{path}:1: {raw_key}: need line longer than 200 characters")
            needs[doc_type] = ClerkNeed(text=value)
        elif isinstance(value, dict) and isinstance(value.get("key"), str):
            needs[doc_type] = ClerkNeed(key=str(value["key"]))
        else:
            raise RulesLoadError(f"{path}:1: {raw_key}: value must be text or {{key: …}}")
    return needs, str(data.get("version") or "0")


class RulesRepo:
    """Read-only rules tables; built once in ``main.create_app()`` and injected via ``deps``."""

    def __init__(
        self,
        rules: list[DeadlineRule],
        version: str,
        *,
        notices: list[FixedNotice] | None = None,
        needs: dict[DocumentType, ClerkNeed] | None = None,
        prepare: dict[DocumentType, list[str]] | None = None,
        notices_version: str = "0",
        needs_version: str = "0",
    ) -> None:
        self._rules = list(rules)
        self._version = version
        self._notices = list(notices or [])
        self._needs = dict(needs or {})
        self._prepare = dict(prepare or {})
        self._notices_version = notices_version
        self._needs_version = needs_version

    @classmethod
    def load(cls, dir: Path) -> RulesRepo:  # noqa: A002 - name fixed by BUILD_PLAN §4.1
        rules, version = load_deadlines(dir / "deadlines.yaml")
        notices, notices_version = load_fixed_notices(dir / "fixed_notices.yaml")
        needs, needs_version = load_clerk_needs(dir / "clerk_needs.yaml")
        prepare_path = dir / "prepare.yaml"
        try:
            prepare = load_prepare(prepare_path)
        except PrepareLoadError as exc:
            raise RulesLoadError(str(exc)) from exc
        if not prepare_path.is_file():
            logger.warning("prepare.yaml missing at %s", prepare_path)
        logger.info(
            "rules_loaded=%d notices=%d clerk_needs=%d prepare_types=%d version=%s",
            len(rules), len(notices), len(needs), len(prepare), version,
        )  # fmt: skip
        return cls(
            rules,
            version,
            notices=notices,
            needs=needs,
            prepare=prepare,
            notices_version=notices_version,
            needs_version=needs_version,
        )

    def deadline_rules(self) -> list[DeadlineRule]:
        return list(self._rules)

    def rule(self, id: str) -> DeadlineRule | None:  # noqa: A002
        return next((r for r in self._rules if r.id == id), None)

    def fixed_notices(self, doc_type: DocumentType) -> list[FixedNotice]:
        """Notices whose ``document_types`` names ``doc_type`` or ``any`` (``when`` unevaluated)."""
        return [
            n
            for n in self._notices
            if doc_type.value in n.document_types or ANY_DOC_TYPE in n.document_types
        ]

    def all_fixed_notices(self) -> list[FixedNotice]:
        return list(self._notices)

    def clerk_need(self, doc_type: DocumentType) -> str:
        """Fixed English need line, or ``""`` when the type maps to a pack key / is unknown."""
        need = self._needs.get(doc_type)
        return need.text if need is not None else ""

    def clerk_need_key(self, doc_type: DocumentType) -> str | None:
        """Pack key (``clerk.generic_need``) for types whose row is ``{key: …}``; else ``None``."""
        need = self._needs.get(doc_type)
        return need.key if need is not None else None

    def prepare_items(self, doc_type: DocumentType) -> list[str]:
        return list(self._prepare.get(doc_type, []))

    @property
    def version(self) -> str:
        return self._version

    @property
    def notices_version(self) -> str:
        return self._notices_version

    @property
    def needs_version(self) -> str:
        return self._needs_version


__all__ = [
    "ClerkNeed",
    "FixedNotice",
    "RulesLoadError",
    "RulesRepo",
    "load_clerk_needs",
    "load_deadlines",
    "load_fixed_notices",
]
