"""Readability gate for the English base pack (BUILD_PLAN §5.9 step 4, COMPLIANCE_PRIVACY §5).

No readability package is installed (BUILD_PLAN Appendix F, F-4), so the grade-5 target is
approximated with two checks on every ``apps/api/data/langpacks/en.json`` value:

1. the average sentence length is at most 12 words;
2. no word has more than 3 syllables (vowel-group heuristic with a small correction table),
   unless the word is on the allow-list.

``readability_allowlist.txt`` (next to this file) has three kinds of lines:

* ``word`` — a long word that is allowed everywhere: proper nouns, agency and form names,
  unavoidable legal or medical terms. Nothing else belongs here.
* ``key:<en.json key>`` (``*`` may end the key) — a string whose wording is legally or
  contractually fixed (COMPLIANCE_PRIVACY §4, §5, §6; D-02; D-20; D-25) and therefore exempt.
* ``pending:<en.json key>`` — a string that fails today and is queued for a plain-language
  rewrite by the ``en.json`` owner (DECISIONS §14). It is skipped here; when the rewrite lands
  and the string passes, the test warns that the line is stale so the list only shrinks.
"""

import json
import re
import warnings
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path

import pytest

from proxyhealth_api.settings import DATA_DIR

EN_JSON = DATA_DIR / "langpacks" / "en.json"
ALLOWLIST = Path(__file__).with_name("readability_allowlist.txt")

MAX_AVG_SENTENCE_WORDS = 12
MAX_SYLLABLES = 3

_PLACEHOLDER = re.compile(r"\{[^{}]*\}")
_URL = re.compile(r"https?://\S+|\b[\w.-]+\.(?:gov|org|com|net|edu|us)\b\S*", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’.-]*")
_LETTERS = re.compile(r"[a-z]+")
_VOWEL_GROUPS = re.compile(r"[aeiouy]+")
_SILENT_E_BEFORE_SUFFIX = re.compile(r"(?<=[^aeiouy])e(?=(?:ly|ful|fully|ness|ment|ments|less)$)")

# Words the vowel-group heuristic over-counts (syllables per the CMU pronouncing dictionary).
SYLLABLE_OVERRIDES: dict[str, int] = {
    "everything": 3,
    "everyone": 3,
    "everybody": 4,
    "caseworker": 3,
    "caseworkers": 3,
    "someone": 2,
    "somewhere": 2,
    "whenever": 3,
    "wherever": 3,
}


def syllables(word: str) -> int:
    """Approximate English syllables: vowel groups, minus silent final/suffix ``e``."""
    w = "".join(_LETTERS.findall(word.lower()))
    if not w:
        return 0
    if w in SYLLABLE_OVERRIDES:
        return SYLLABLE_OVERRIDES[w]
    if len(w) <= 3:
        return 1
    w = _SILENT_E_BEFORE_SUFFIX.sub("", w)
    if w.endswith("le") and len(w) > 2 and w[-3] not in "aeiouy":
        w = w[:-2] + "el"  # "table", "people": the final "le" is its own syllable
    elif w.endswith("es") and w[-3:-2] not in ("s", "x", "z", "c", "g", "h", ""):
        w = w[:-2]  # "makes", "dates" -> one syllable less; "boxes", "pages" keep it
    elif w.endswith("ed") and w[-3:-2] not in ("t", "d", ""):
        w = w[:-2]  # "asked", "saved" -> silent; "dated", "needed" keep it
    elif w.endswith("e") and not w.endswith(("ee", "ye")):
        w = w[:-1]  # silent final e ("phone", "date")
    if w.startswith("y"):
        w = w[1:]
    return max(1, len(_VOWEL_GROUPS.findall(w)))


def _clean(text: str) -> str:
    return _URL.sub(" ", _PLACEHOLDER.sub(" X ", text))


def sentences(text: str) -> list[str]:
    parts = [p for p in _SENTENCE_END.split(_clean(text).strip()) if re.search("[A-Za-z]", p)]
    return parts


def words(text: str) -> list[str]:
    return _WORD.findall(_clean(text))


def average_sentence_words(text: str) -> float:
    sents = sentences(text)
    if not sents:
        return 0.0
    return len(words(text)) / len(sents)


def long_words(text: str, allowed: set[str]) -> list[str]:
    """Words over the syllable limit; acronyms, numbers and allow-listed words are skipped."""
    found: list[str] = []
    for token in words(text):
        for part in re.split(r"[-’'./]", token):
            if not part or any(ch.isdigit() for ch in part):
                continue
            if len(part) > 1 and part.isupper():
                continue  # USCIS, SNAP, ICE: read letter by letter or as a name
            if part.lower() in allowed:
                continue
            if syllables(part) > MAX_SYLLABLES:
                found.append(part)
    return found


@dataclass
class Allowlist:
    words: set[str] = field(default_factory=set)
    key_patterns: list[str] = field(default_factory=list)
    pending: set[str] = field(default_factory=set)

    def key_exempt(self, key: str) -> bool:
        return any(fnmatchcase(key, pat) for pat in self.key_patterns)


def load_allowlist(path: Path = ALLOWLIST) -> Allowlist:
    allow = Allowlist()
    for raw in path.read_text("utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("key:"):
            allow.key_patterns.append(line[4:].strip())
        elif line.startswith("pending:"):
            allow.pending.add(line[8:].strip())
        else:
            if " " in line:
                raise ValueError(f"{path.name}: one word per line, got {line!r}")
            allow.words.add(line.lower())
    return allow


def load_strings() -> dict[str, str]:
    data = json.loads(EN_JSON.read_text("utf-8"))
    return {k: v for k, v in data.items() if isinstance(v, str)}


def problems(text: str, allow: Allowlist) -> list[str]:
    out: list[str] = []
    avg = average_sentence_words(text)
    if avg > MAX_AVG_SENTENCE_WORDS:
        out.append(f"average sentence {avg:.1f} words > {MAX_AVG_SENTENCE_WORDS}")
    lw = long_words(text, allow.words)
    if lw:
        out.append(f"words over {MAX_SYLLABLES} syllables: {', '.join(sorted(set(lw)))}")
    return out


# --- the heuristic itself ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("paper", 2), ("date", 1), ("phone", 1), ("saved", 1), ("needed", 2), ("pages", 2),
        ("makes", 1), ("people", 2), ("table", 2), ("family", 3), ("remember", 3),
        ("carefully", 3), ("privately", 3), ("statement", 2), ("everything", 3),
        ("information", 4), ("immigration", 4), ("representative", 5), ("available", 4),
        ("yes", 1), ("the", 1), ("Medicaid", 3), ("appointment", 3),
    ],
)  # fmt: skip
def test_syllable_heuristic(word: str, expected: int) -> None:
    assert syllables(word) == expected


def test_sentence_average_counts_placeholders_and_ignores_urls() -> None:
    assert average_sentence_words("Call {name} today. See https://www.uscis.gov/forms now.") == 2.5
    assert sentences("One. Two words! Three here?") == ["One.", "Two words!", "Three here?"]
    assert average_sentence_words("Save") == 1.0


def test_long_words_skip_acronyms_numbers_and_allowlist() -> None:
    assert long_words("USCIS sent form I-765 on 2026-10-14.", set()) == []
    assert long_words("Ask an interpreter.", set()) == ["interpreter"]
    assert long_words("Ask an interpreter.", {"interpreter"}) == []


# --- the gate ---------------------------------------------------------------------------------


def test_allowlist_is_well_formed() -> None:
    allow = load_allowlist()
    strings = load_strings()
    assert allow.words, "the allow-list has no words"
    for key in allow.pending:
        assert key in strings, f"pending:{key} is not an en.json key"
        assert not allow.key_exempt(key), f"pending:{key} is also key-exempt"
    for pat in allow.key_patterns:
        assert any(fnmatchcase(k, pat) for k in strings), f"key:{pat} matches no en.json key"


def test_every_en_string_is_plain_language() -> None:
    allow = load_allowlist()
    failures: list[str] = []
    for key, text in sorted(load_strings().items()):
        if allow.key_exempt(key) or key in allow.pending:
            continue
        for issue in problems(text, allow):
            failures.append(f"{key}: {issue} — {text!r}")
    assert not failures, (
        "en.json strings above the grade-5 approximation (rewrite them, or — only for proper "
        "nouns, agency/form names and unavoidable legal/medical terms — add the word to "
        f"{ALLOWLIST.name}):\n" + "\n".join(failures)
    )


def test_pending_rewrites_are_still_needed() -> None:
    """A ``pending:`` line whose string now passes is stale: warn so the list keeps shrinking."""
    allow = load_allowlist()
    strings = load_strings()
    stale = sorted(k for k in allow.pending if k in strings and not problems(strings[k], allow))
    if stale:
        warnings.warn(
            f"{ALLOWLIST.name}: these pending rewrites now pass; delete their lines: {stale}",
            UserWarning,
            stacklevel=1,
        )
