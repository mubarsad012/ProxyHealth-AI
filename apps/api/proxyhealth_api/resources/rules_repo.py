"""``RulesRepo`` (BUILD_PLAN §4.1). WP0 stub: empty collections, version ``"0"``."""

from dataclasses import dataclass
from pathlib import Path

from proxyhealth_api.contracts.enums import DocumentType, RedFlagKind, Severity
from proxyhealth_api.contracts.rules import DeadlineRule


@dataclass(frozen=True)
class FixedNotice:
    kind: RedFlagKind
    severity: Severity
    fixed_copy_key: str


class RulesRepo:
    def __init__(self, rules: list[DeadlineRule], version: str) -> None:
        self._rules = rules
        self._version = version

    @classmethod
    def load(cls, dir: Path) -> "RulesRepo":  # noqa: A002 - name fixed by BUILD_PLAN §4.1
        return cls([], "0")

    def deadline_rules(self) -> list[DeadlineRule]:
        return list(self._rules)

    def fixed_notices(self, doc_type: DocumentType) -> list[FixedNotice]:
        return []

    def clerk_need(self, doc_type: DocumentType) -> str:
        return ""

    def prepare_items(self, doc_type: DocumentType) -> list[str]:
        return []

    @property
    def version(self) -> str:
        return self._version
