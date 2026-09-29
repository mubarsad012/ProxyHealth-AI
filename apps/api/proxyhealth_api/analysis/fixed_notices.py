"""Fixed high-severity notices by document type (D-20; DOCUMENT_TAXONOMY §7; AI_PROMPTS §11.10).

``RulesRepo.fixed_notices(document_type)`` returns the YAML rows of
``data/rules/fixed_notices.yaml`` (``FixedNotice{kind, severity, fixed_copy_key, id,
document_types, when}``); this module evaluates the ``when`` grammar and emits reviewed fixed-copy
``RedFlag``s: ``text = t(fixed_copy_key)`` (target language, English fallback),
``source_quote=None``, ``span_ids=[]``, ``page=None``, ``verified=True``. They bypass the phrasing
linter and the contact filter. ``merge_red_flags`` orders the final list so a high fixed card
leads. The ``[multiple_documents]`` sentinel from ``verify.py`` becomes
``fixed.multiple_documents``.

Grammar: ``always`` · ``form_numbers_any`` (hyphen-insensitive, entities or transcript) ·
``text_regex_any`` / ``text_regex_none`` · ``date_on_or_after: {role, iso, when_missing}`` ·
``has_verified_role`` · ``has_red_flag`` · ``scam_risk`` · ``document_type_confidence_min``
(default ``medium``; type-specific cards only).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from proxyhealth_api.analysis.i18n import Translator
from proxyhealth_api.analysis.verify import MULTIPLE_DOCUMENTS_SENTINEL, normalize
from proxyhealth_api.contracts.analysis import Demand, RedFlag
from proxyhealth_api.contracts.enums import (
    Confidence,
    DateKind,
    DocumentType,
    RedFlagKind,
    ScamRisk,
    Severity,
)

MULTIPLE_DOCUMENTS_KEY = "fixed.multiple_documents"
ANY_DOC_TYPE = "any"
_CONFIDENCE_RANK = {Confidence.low: 0, Confidence.medium: 1, Confidence.high: 2}
_SEVERITY_RANK = {Severity.high: 0, Severity.medium: 1, Severity.low: 2}
KNOWN_CONDITIONS = frozenset(
    {
        "form_numbers_any", "text_regex_any", "text_regex_none", "date_on_or_after",
        "has_verified_role", "has_red_flag", "scam_risk", "document_type_confidence_min",
    }
)  # fmt: skip


class NoticeRow(Protocol):
    """``resources.rules_repo.FixedNotice`` as this module reads it."""

    @property
    def kind(self) -> RedFlagKind: ...
    @property
    def severity(self) -> Severity: ...
    @property
    def fixed_copy_key(self) -> str: ...
    @property
    def document_types(self) -> tuple[str, ...]: ...
    @property
    def when(self) -> Any: ...


class NoticeRules(Protocol):
    """The ``RulesRepo`` surface used here (BUILD_PLAN §4.1)."""

    def fixed_notices(self, doc_type: DocumentType) -> Sequence[NoticeRow]: ...


@dataclass(frozen=True)
class NoticeFacts:
    """What the conditions look at; everything comes from verified, code-checked data."""

    document_type: DocumentType
    document_type_confidence: Confidence = Confidence.high
    transcript_text: str = ""
    form_numbers: Sequence[str] = ()
    demands: Sequence[Demand] = ()
    red_flags: Sequence[RedFlag] = ()
    scam_risk: ScamRisk = ScamRisk.none


def _form_key(value: str) -> str:
    return re.sub(r"[\s\-‐‑–—_.]", "", normalize(value)).upper()


def _has_form(facts: NoticeFacts, wanted: Iterable[str]) -> bool:
    printed = {_form_key(f) for f in facts.form_numbers}
    text = _form_key(facts.transcript_text)
    return any(_form_key(w) in printed or _form_key(w) in text for w in wanted)


def _stated(facts: NoticeFacts, role: str) -> list[str]:
    return [
        d.date.value_iso
        for d in facts.demands
        if d.verified and d.role == role and d.date is not None
        and d.date.kind is DateKind.stated and d.date.value_iso
    ]  # fmt: skip


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    return [str(v) for v in value] if isinstance(value, list | tuple) else [str(value)]


def condition_holds(when: Any, facts: NoticeFacts, *, type_specific: bool = True) -> bool:
    """Evaluate one notice's ``when`` (``"always"`` or a mapping of conditions, all must hold).

    An unknown condition name fails closed (the notice is not shown).
    """
    if when is None or when == "always":
        conditions: Mapping[str, Any] = {}
    elif isinstance(when, Mapping):
        conditions = when
    else:
        return False
    if any(name not in KNOWN_CONDITIONS for name in conditions):
        return False
    minimum = Confidence(str(conditions.get("document_type_confidence_min", "medium")))
    if type_specific and _CONFIDENCE_RANK[facts.document_type_confidence] < _CONFIDENCE_RANK[
        minimum
    ]:  # fmt: skip
        return False
    text = normalize(facts.transcript_text)
    if "form_numbers_any" in conditions and not _has_form(
        facts, _as_list(conditions["form_numbers_any"])
    ):
        return False
    any_rx = _as_list(conditions.get("text_regex_any"))
    if any_rx and not any(re.search(p, text, re.IGNORECASE) for p in any_rx):
        return False
    none_rx = _as_list(conditions.get("text_regex_none"))
    if any(re.search(p, text, re.IGNORECASE) for p in none_rx):
        return False
    date_rule = conditions.get("date_on_or_after")
    if isinstance(date_rule, Mapping):
        dates = _stated(facts, str(date_rule.get("role", "notice_date")))
        if dates:
            if not any(d >= str(date_rule.get("iso", "")) for d in dates):
                return False
        elif str(date_rule.get("when_missing", "show")) != "show":
            return False
    role = conditions.get("has_verified_role")
    if role is not None and not any(d.verified and d.role == str(role) for d in facts.demands):
        return False
    flag_kind = conditions.get("has_red_flag")
    if flag_kind is not None and not any(
        f.verified and f.kind.value == str(flag_kind) for f in facts.red_flags
    ):
        return False
    risk = conditions.get("scam_risk")
    return risk is None or facts.scam_risk.value == str(risk)


def fixed_red_flag(kind: RedFlagKind, severity: Severity, key: str, t: Translator) -> RedFlag:
    """A reviewed fixed-copy card as a ``RedFlag``."""
    return RedFlag(
        kind=kind, text=t(key), source_quote=None, span_ids=[], page=None, severity=severity,
        fixed_copy_key=key, verified=True,
    )  # fmt: skip


def evaluate_notices(rules: NoticeRules, facts: NoticeFacts, t: Translator) -> list[RedFlag]:
    """Fixed cards for ``facts.document_type`` whose conditions hold (one per copy key)."""
    out: list[RedFlag] = []
    seen: set[str] = set()
    for row in rules.fixed_notices(facts.document_type):
        if row.fixed_copy_key in seen:
            continue
        type_specific = ANY_DOC_TYPE not in row.document_types
        if condition_holds(row.when, facts, type_specific=type_specific):
            out.append(fixed_red_flag(row.kind, row.severity, row.fixed_copy_key, t))
            seen.add(row.fixed_copy_key)
    return out


def replace_multiple_documents_sentinel(flags: Iterable[RedFlag], t: Translator) -> list[RedFlag]:
    """Swap the ``[multiple_documents]`` sentinel flag for the ``fixed.multiple_documents`` card
    (once), keeping every other flag."""
    out: list[RedFlag] = []
    swapped = False
    for f in flags:
        if f.text.strip() == MULTIPLE_DOCUMENTS_SENTINEL:
            if not swapped:
                out.append(
                    fixed_red_flag(RedFlagKind.other, Severity.medium, MULTIPLE_DOCUMENTS_KEY, t)
                )
                swapped = True
            continue
        out.append(f)
    return out


def merge_red_flags(model_flags: Iterable[RedFlag], code_flags: Iterable[RedFlag]) -> list[RedFlag]:
    """Final ``red_flags``: severity high → low, fixed cards before other flags of the same
    severity, then input order; duplicate fixed keys dropped."""
    combined: list[RedFlag] = []
    keys: set[str] = set()
    for f in [*code_flags, *model_flags]:
        if f.fixed_copy_key:
            if f.fixed_copy_key in keys:
                continue
            keys.add(f.fixed_copy_key)
        combined.append(f)
    order = {id(f): i for i, f in enumerate(combined)}
    return sorted(
        combined,
        key=lambda f: (_SEVERITY_RANK[f.severity], 0 if f.fixed_copy_key else 1, order[id(f)]),
    )


__all__ = [
    "KNOWN_CONDITIONS",
    "MULTIPLE_DOCUMENTS_KEY",
    "NoticeFacts",
    "NoticeRow",
    "NoticeRules",
    "condition_holds",
    "evaluate_notices",
    "fixed_red_flag",
    "merge_red_flags",
    "replace_multiple_documents_sentinel",
]
