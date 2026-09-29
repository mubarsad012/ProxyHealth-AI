"""Language-pack QA (D-25; AI_PROMPTS §5.5 rules; ARCHITECTURE §2 ``packs/qa.py``).

Every translated string is checked against its English base string:

* ``empty``        — the translation is blank while the English is not;
* ``placeholders`` — the set of ``{name}`` placeholders differs (the app fills them later);
* ``length``       — longer than 1.6× the English (2× for ``btn.*`` keys), with a small absolute
  allowance for very short strings ("OK" → "Aceptar" is fine);
* ``html``         — an HTML tag or entity the English does not have;
* ``digits``       — a run of 3+ digits (any script) that the English does not contain, so the
  model can never smuggle in a phone number (D-10 applies to packs too).

A key that fails any check is filled with English and listed in ``fallback_keys``. Bundled packs
(``data/langpacks/<tag>.json``) must pass with zero failures (``tests/unit/test_packs_qa.py``).
"""

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field

PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
HTML_RE = re.compile(r"</?[A-Za-z][^<>]*>|&[A-Za-z]+;|&#\d+;")
DIGIT_RUN_RE = re.compile(r"\d{3,}")

LENGTH_RATIO = 1.6
LENGTH_RATIO_BUTTON = 2.0
# Short strings get this many extra characters before the ratio applies.
LENGTH_SLACK_CHARS = 16

CHECKS = ("empty", "placeholders", "length", "html", "digits")


@dataclass(frozen=True)
class QaIssue:
    key: str
    check: str
    detail: str


@dataclass
class QaReport:
    """Result of checking one pack; ``accepted`` holds the translations that passed."""

    accepted: dict[str, str] = field(default_factory=dict)
    issues: list[QaIssue] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def failed_keys(self) -> list[str]:
        return sorted({i.key for i in self.issues})

    @property
    def fallback_keys(self) -> list[str]:
        return sorted(set(self.failed_keys) | set(self.missing))

    @property
    def ok(self) -> bool:
        return not self.issues and not self.missing


def placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER_RE.findall(text))


def normalize_digits(text: str) -> str:
    """Map every Unicode decimal digit (Arabic-Indic, Persian, Devanagari, ...) to ASCII."""
    return "".join(
        str(unicodedata.decimal(ch)) if ch.isdecimal() and not ch.isascii() else ch for ch in text
    )


def _digit_runs(text: str) -> set[str]:
    return set(DIGIT_RUN_RE.findall(normalize_digits(PLACEHOLDER_RE.sub(" ", text))))


def max_length(key: str, english: str) -> int:
    ratio = LENGTH_RATIO_BUTTON if key.startswith("btn.") else LENGTH_RATIO
    return max(int(len(english) * ratio), len(english) + LENGTH_SLACK_CHARS)


def check_string(key: str, english: str, translated: str) -> list[QaIssue]:
    """All issues for one ``key``; an empty list means the translation is accepted."""
    issues: list[QaIssue] = []
    value = translated.strip()
    if not value:
        if english.strip():
            issues.append(QaIssue(key, "empty", "translation is empty"))
        return issues
    want, got = placeholders(english), placeholders(translated)
    if want != got:
        issues.append(QaIssue(key, "placeholders", f"expected {sorted(want)}, got {sorted(got)}"))
    limit = max_length(key, english)
    if len(translated) > limit:
        issues.append(QaIssue(key, "length", f"{len(translated)} chars > limit {limit}"))
    if HTML_RE.search(translated) and not HTML_RE.search(english):
        issues.append(QaIssue(key, "html", "contains HTML markup"))
    extra_runs = _digit_runs(translated) - _digit_runs(english)
    if extra_runs:
        issues.append(QaIssue(key, "digits", f"digit runs not in English: {sorted(extra_runs)}"))
    return issues


def check_pack(base: Mapping[str, str], translated: Mapping[str, str]) -> QaReport:
    """QA every base key; keys absent from ``translated`` are reported as ``missing``."""
    report = QaReport()
    for key, english in base.items():
        value = translated.get(key)
        if value is None:
            report.missing.append(key)
            continue
        found = check_string(key, english, value)
        if found:
            report.issues.extend(found)
        else:
            report.accepted[key] = value
    report.missing.sort()
    return report


def merge_with_fallback(
    base: Mapping[str, str], translated: Mapping[str, str]
) -> tuple[dict[str, str], list[str], QaReport]:
    """Base-ordered strings with every failed/missing key filled from English."""
    report = check_pack(base, translated)
    strings = {key: report.accepted.get(key, english) for key, english in base.items()}
    return strings, report.fallback_keys, report
