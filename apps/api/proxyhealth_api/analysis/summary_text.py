"""Summary card repairs before the lint (AI_PROMPTS §11.9; API_CONTRACT §3.5 ``SummaryCard``).

Two shape faults of model summaries are mended in code, for every provider, before the contact
scrubber, the phrasing lint and the prose-date check run on the result. Nothing here writes words
of its own except the "…" that marks a cut title:

* ``summary_title`` cut off at the schema cap (``model_out.Str80``: strict JSON-schema decoding
  ends the string there, mid-word or mid-date — "… asking you to pay $1,240.00 by October 2").
  The title goes back to its last clause boundary, then trailing tokens with a digit, month
  names, currency signs and dangling connector words (``phrasing.yaml`` ``title_connectors``) are
  dropped and "…" is added, so no partial date or amount stays on the title card. A body that
  goes on with the cut sentence ("to appear for jury service on …") gets the title's words back
  in front of it, so the reader still sees the whole sentence.
* For an English reader ``summary.body`` and ``summary.body_en`` are one text (AI_PROMPTS §4:
  "the same in English"). A ``body_en`` that only repeats the title, or opens with it, is
  mended from the body; a body written in another language (the paper's) gives way to the
  English ``body_en``; otherwise the body is used for both.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from proxyhealth_api.analysis import deadline_rules as dr
from proxyhealth_api.analysis.phrasing import split_sentences, title_connectors
from proxyhealth_api.analysis.verify import normalize
from proxyhealth_api.contracts.model_out import AnalysisModelOut

TITLE_CAP = 80
"""``model_out.Str80`` on ``summary_title`` (a test keeps the two equal)."""
ELLIPSIS = "…"
MIN_CLAUSE_INDEX = 24
"""A clause boundary earlier than this would leave too short a title; the whole text is kept."""
_TERMINAL = (".", "?", "!", "。", "؟", "।", ELLIPSIS)
_CLAUSE_BREAKS = (", ", "; ", ": ", " — ", " – ")
_TOKEN_EDGES = ",;:—–-()[]\"'“”‘’«»"
# English function words: a body with none of them while ``body_en`` has some is not English.
_EN_WORDS = frozenset(
    {"the", "is", "are", "was", "this", "that", "to", "of", "and", "you", "your", "for", "it",
     "with", "from", "have", "will", "be", "by", "on", "they", "their", "about", "says", "asks",
     "not"}
)  # fmt: skip


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _base(tag: str | None) -> str:
    return tag.split("-")[0].lower() if tag else ""


def is_cut(title: str, cap: int = TITLE_CAP) -> bool:
    """True when the title reached the cap (or two short of it) and ends without a terminator."""
    return len(title) >= cap - 2 and not title.rstrip().endswith(_TERMINAL)


def _droppable(token: str, connectors: frozenset[str]) -> bool:
    word = token.strip(_TOKEN_EDGES)
    if not word or any(ch.isdigit() for ch in word):
        return True
    if all(unicodedata.category(ch) == "Sc" for ch in word):
        return True
    folded = _fold(word).rstrip(".")
    return folded in dr._TOKEN_MONTHS or folded in connectors


def repair_title(title: str, *, language: str | None = "en", cap: int = TITLE_CAP) -> str:
    """The title, or — when the schema cap cut it — its last whole clause with trailing digits,
    month names, currency signs and connector words dropped, plus "…". A word the cap split in
    two goes first. A title with nothing left after that is returned as it came (the prose-date
    check still runs on it)."""
    if not is_cut(title, cap):
        return title
    text = title.rstrip()
    cut = max(text.rfind(b) for b in _CLAUSE_BREAKS)
    if cut >= MIN_CLAUSE_INDEX:
        text = text[:cut]
    elif len(title) >= cap and title[-1:].isalnum():
        text = text.rsplit(maxsplit=1)[0] if len(text.split()) > 1 else text
    connectors = title_connectors(language)
    tokens = text.split()
    while tokens and _droppable(tokens[-1], connectors):
        tokens.pop()
    kept = " ".join(tokens).rstrip(_TOKEN_EDGES + " ")
    return kept + ELLIPSIS if kept else title


def continues(title: str, body: str, *, language: str | None = "en") -> bool:
    """True when ``body`` carries on the title's sentence: it starts with a lower-case letter and
    the title was cut or ends on a connector word ("… asking you" + "to appear …")."""
    head = body.lstrip()[:1]
    last = title.split()[-1:] if title.strip() else []
    if not head.islower() or title.rstrip().endswith(_TERMINAL) or not last:
        return False
    return is_cut(title) or _fold(last[0].strip(_TOKEN_EDGES)) in title_connectors(language)


def join_continuation(title: str, body: str, *, language: str | None = "en") -> str:
    """``body`` with the title's words in front when it continues the title's sentence."""
    if continues(title, body, language=language):
        return f"{title.rstrip()} {body.lstrip()}"
    return body


def _key(text: str) -> str:
    return normalize(text).casefold().rstrip(" .!?…")


def without_title(title: str, text: str) -> str:
    """``text`` without a first sentence that only repeats the title."""
    sentences = split_sentences(text)
    if sentences and title.strip() and _key(sentences[0]) == _key(title):
        return " ".join(sentences[1:])
    return text


def _english_words(text: str) -> int:
    return sum(1 for w in _fold(text).split() if w.strip(_TOKEN_EDGES + ".!?") in _EN_WORDS)


def english_bodies(title: str, body: str, body_en: str) -> tuple[str, str]:
    """(``body``, ``body_en``) for an English reader: one English text in both fields."""
    body, body_en = without_title(title, body), without_title(title, body_en)
    if not body_en.strip() or _key(body_en) == _key(title):
        return body, body
    if not body.strip() or _key(body) == _key(title):
        return body_en, body_en
    if _english_words(body) == 0 < _english_words(body_en):
        return body_en, body_en  # the body is in the paper's language, not the reader's
    return body, body


@dataclass(frozen=True)
class SummaryFields:
    """The three model summary fields after the repairs (still unlinted, unscrubbed)."""

    title: str
    body: str
    body_en: str


def tidy(title: str, body: str, body_en: str, *, target_language: str) -> SummaryFields:
    """Both repairs (module docstring); a non-English reader's ``body_en`` is left as written
    because its title is in another language."""
    body = join_continuation(title, body, language=target_language)
    if _base(target_language) == "en":
        body_en = join_continuation(title, body_en, language="en")
        body, body_en = english_bodies(title, body, body_en)
    return SummaryFields(repair_title(title, language=target_language), body, body_en)


def tidy_update(out: AnalysisModelOut, target_language: str) -> dict[str, str]:
    """``AnalysisModelOut.model_copy(update=…)`` values for ``summary_title/body/body_en``."""
    fields = tidy(
        out.summary_title, out.summary_body, out.summary_body_en, target_language=target_language
    )
    return {
        "summary_title": fields.title,
        "summary_body": fields.body,
        "summary_body_en": fields.body_en,
    }


__all__ = [
    "ELLIPSIS",
    "MIN_CLAUSE_INDEX",
    "TITLE_CAP",
    "SummaryFields",
    "continues",
    "english_bodies",
    "is_cut",
    "join_continuation",
    "repair_title",
    "tidy",
    "tidy_update",
    "without_title",
]
