"""Summary card repairs before the lint (AI_PROMPTS §11.9; API_CONTRACT §3.5 ``SummaryCard``).

Two shape faults of model summaries are mended in code, for every provider, before the contact
scrubber, the phrasing lint and the prose-date check run on the result. Nothing here writes words
of its own except the "…" that marks a cut title:

* ``summary_title`` cut off at the schema cap (``model_out.Str80``: strict JSON-schema decoding
  ends the string there, mid-word or mid-date — "… asking you to pay $1,240.00 by October 2").
  A title is cut when it reached the cap with no final stop, or — one or two characters short —
  ends on a dangling connector or a month name cut short (``is_cut``); a whole 78-79 character
  label ending on a date or an amount the paper prints ("… by Jan 5, 2027") is left alone, while
  one ending on a figure the paper does not print as it stands ("… pay $1,24" for "$1,240.00")
  is cut (``printed``, the paper's text, given by the pipeline). Only words go: the
  word the cap split (or a month name it cut short, "Octo"), then trailing tokens with a digit,
  month names, currency signs and dangling connector words
  (``phrasing.yaml`` ``title_connectors``); "…" is added. No partial date or amount stays on the
  title card, and no whole clause is cut away — the clause after a comma is often the one that
  carries "but" or "unless" ("… from the IRS, but real IRS letters never ask for gift car").
  A body that goes on with the cut sentence ("to appear for jury service on …") gets the title's
  words back in front of it, so the reader still sees the whole sentence — unless the cut lost a
  word, a number or a month there, which the body must not inherit; such a body only gets a
  capital letter.
* For an English reader ``summary.body`` and ``summary.body_en`` are one text (AI_PROMPTS §4:
  "the same in English"). A ``body_en`` that only repeats the title, or opens with it, is
  mended from the body; a body written in another language (the paper's) gives way to the
  English ``body_en``; otherwise the body is used for both. When both only repeat the title,
  the body stays as written.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from proxyhealth_api.analysis import deadline_rules as dr
from proxyhealth_api.analysis.phrasing import split_sentences, title_connectors
from proxyhealth_api.analysis.verify import ascii_digits, check_value, normalize
from proxyhealth_api.contracts.model_out import AnalysisModelOut

TITLE_CAP = 80
"""``model_out.Str80`` on ``summary_title`` (a test keeps the two equal)."""
ELLIPSIS = "…"
MIN_MONTH_PREFIX = 3
"""A cut last word of at least this many letters that starts an English month name ("Octo")."""
_TERMINAL = (".", "?", "!", "。", "؟", "।", ELLIPSIS)
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


def is_cut(
    title: str, cap: int = TITLE_CAP, *, language: str | None = "en", printed: str | None = None
) -> bool:
    """True when the schema cap cut the title off: it ends without a terminator and reached the
    cap (strict decoding stops exactly there), or — one or two characters short of it — ends on a
    dangling connector word ("… Virginia, asking you"), a month name cut short ("Octo") or, given
    the paper's text ``printed``, a figure the paper does not print as it stands ("… pay $1,24"
    when it prints "$1,240.00": the next token would not fit). A 78-79 character title ending on
    any other word, or on a date or an amount the paper prints, is whole (a full-size model
    writes labels without a final period: "… by Jan 5, 2027") and keeps every word."""
    text = title.rstrip()
    if not text or text.endswith(_TERMINAL) or len(title) < cap - 2:
        return False
    if len(title) >= cap:
        return True
    last = text.split()[-1]
    if printed is not None and _unprinted_figure(last, printed):
        return True
    return _fold(last.strip(_TOKEN_EDGES)) in title_connectors(language) or _month_prefix(
        last, language
    )


def _unprinted_figure(token: str, printed: str) -> bool:
    """True when ``token`` holds a digit and the paper does not print it as it stands, on token
    boundaries (``verify.check_value``; digits compared as ASCII): "$1,24" or "$1,2" of a printed
    "$1,240.00" — a figure the cap cut short. A whole printed "$1,240.00" or "2027" is not."""
    word = token.strip(_TOKEN_EDGES)
    if not any(ch.isdigit() for ch in word):
        return False
    return check_value(ascii_digits(word), ascii_digits(printed)) is not None


def _is_latin(word: str) -> bool:
    return all(ord(ch) < 0x0250 for ch in word)


@lru_cache(maxsize=32)
def _month_languages(language: str | None) -> frozenset[str]:
    return frozenset({"en", _base(language)} - {""})


def _is_month(word: str, language: str | None) -> bool:
    """A month name or abbreviation (``deadline_rules`` table) of English or the title language;
    another language's month counts only when it cannot be an English word — written in another
    script, or at least five letters ("agosto") — so "out", "set" or "ago" stay in an English
    title."""
    meanings = dr._TOKEN_MONTHS.get(word)
    if not meanings:
        return False
    if any(_base(lang) in _month_languages(language) for lang in meanings):
        return True
    return not _is_latin(word) or len(word) >= 5


@lru_cache(maxsize=32)
def _month_names(language: str | None) -> frozenset[str]:
    """English month names plus the title language's own (``deadline_rules`` table, folded)."""
    langs = _month_languages(language)
    return frozenset(
        token for token, meanings in dr._TOKEN_MONTHS.items()
        if any(_base(lang) in langs for lang in meanings)
    )  # fmt: skip


def _month_prefix(token: str, language: str | None = "en") -> bool:
    """A last word the cap may have cut short inside a month name of English or the title's
    language ("Octo", "Septem"; Spanish "ago" for "agosto")."""
    word = _fold(token.strip(_TOKEN_EDGES)).rstrip(".")
    return len(word) >= MIN_MONTH_PREFIX and any(
        m.startswith(word) and m != word for m in _month_names(language)
    )


def _drop_kind(token: str, connectors: frozenset[str], language: str | None) -> str | None:
    """``"content"`` (a digit, currency sign or month name), ``"connector"`` or ``None`` (keep)."""
    word = token.strip(_TOKEN_EDGES)
    if not word or any(ch.isdigit() for ch in word):
        return "content"
    if all(unicodedata.category(ch) == "Sc" for ch in word):
        return "content"
    folded = _fold(word).rstrip(".")
    if _is_month(folded, language):
        return "content"
    return "connector" if folded in connectors else None


def _trim(title: str, language: str | None, cap: int) -> tuple[list[str], bool]:
    """(kept words, ``lost``) for a cut title. ``lost`` is True when more than connector words
    went: the word the cap split, or a token with a digit, a currency sign or a month name."""
    tokens = title.rstrip().split()
    lost = False
    if len(tokens) > 1 and (
        (len(title) >= cap and title[-1:].isalnum()) or _month_prefix(tokens[-1], language)
    ):
        tokens.pop()
        lost = True
    connectors = title_connectors(language)
    while tokens and (kind := _drop_kind(tokens[-1], connectors, language)):
        lost = lost or kind == "content"
        tokens.pop()
    return tokens, lost


def repair_title(
    title: str, *, language: str | None = "en", cap: int = TITLE_CAP, printed: str | None = None
) -> str:
    """The title, or — when the schema cap cut it — the title less the word the cap split and
    any trailing digits, month names, currency signs and connector words, plus "…". Only words
    go, never a whole clause. A title with nothing left after that is returned as it came (the
    prose-date check still runs on it)."""
    if not is_cut(title, cap, language=language, printed=printed):
        return title
    tokens, _ = _trim(title, language, cap)
    kept = " ".join(tokens).rstrip(_TOKEN_EDGES + " ")
    return kept + ELLIPSIS if kept else title


def continues(
    title: str, body: str, *, language: str | None = "en", printed: str | None = None
) -> bool:
    """True when ``body`` carries on the title's sentence: it starts with a lower-case letter and
    the title was cut or ends on a connector word ("… asking you" + "to appear …")."""
    head = body.lstrip()[:1]
    last = title.split()[-1:] if title.strip() else []
    if not head.islower() or title.rstrip().endswith(_TERMINAL) or not last:
        return False
    return is_cut(title, language=language, printed=printed) or _fold(
        last[0].strip(_TOKEN_EDGES)
    ) in title_connectors(language)


def join_continuation(
    title: str, body: str, *, language: str | None = "en", printed: str | None = None
) -> str:
    """``body`` with the title's words in front when it continues the title's sentence. When
    the cut lost a word, a number or a month there ("… by October 2" for October 28), the body
    does not inherit it: it only gets a capital letter."""
    if not continues(title, body, language=language, printed=printed):
        return body
    if is_cut(title, language=language, printed=printed) and _trim(title, language, TITLE_CAP)[1]:
        rest = body.lstrip()
        return rest[:1].upper() + rest[1:]
    return f"{title.rstrip()} {body.lstrip()}"


def _key(text: str) -> str:
    return normalize(text).casefold().rstrip(" .!?…")


def without_title(title: str, text: str) -> str:
    """``text`` without a first sentence that only repeats the title."""
    sentences = split_sentences(text)
    if sentences and title.strip() and _key(sentences[0]) == _key(title):
        return " ".join(sentences[1:])
    return text


def title_in_body(title: str, body: str) -> bool:
    """True when ``body`` holds the whole (repaired) ``title`` — a body that carries on the
    title's sentence (``join_continuation``) or copies it. Every date or phrasing fault of the
    title is then the body's too, so the pipeline counts it once, with the body."""
    head = _key(title.removesuffix(ELLIPSIS))
    return bool(head) and head in _key(body)


def _english_words(text: str) -> int:
    return sum(1 for w in _fold(text).split() if w.strip(_TOKEN_EDGES + ".!?") in _EN_WORDS)


def english_bodies(title: str, body: str, body_en: str) -> tuple[str, str]:
    """(``body``, ``body_en``) for an English reader: one English text in both fields (the body
    as written when both only repeat the title — never an empty card)."""
    written = body if body.strip() else body_en
    body, body_en = without_title(title, body), without_title(title, body_en)
    if not body.strip() and not body_en.strip():
        return written, written
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


def tidy(
    title: str, body: str, body_en: str, *, target_language: str, printed: str | None = None
) -> SummaryFields:
    """Both repairs (module docstring); a non-English reader's ``body_en`` is left as written
    because its title is in another language. ``printed`` is the paper's text (``is_cut``)."""
    body = join_continuation(title, body, language=target_language, printed=printed)
    if _base(target_language) == "en":
        body_en = join_continuation(title, body_en, language="en", printed=printed)
        body, body_en = english_bodies(title, body, body_en)
    title = repair_title(title, language=target_language, printed=printed)
    return SummaryFields(title, body, body_en)


def tidy_update(
    out: AnalysisModelOut, target_language: str, *, printed: str | None = None
) -> dict[str, str]:
    """``AnalysisModelOut.model_copy(update=…)`` values for ``summary_title/body/body_en``;
    ``printed`` is the paper's (masked) text, for a title cut inside a figure (``is_cut``)."""
    fields = tidy(
        out.summary_title, out.summary_body, out.summary_body_en,
        target_language=target_language, printed=printed,
    )  # fmt: skip
    return {
        "summary_title": fields.title,
        "summary_body": fields.body,
        "summary_body_en": fields.body_en,
    }


__all__ = [
    "ELLIPSIS",
    "MIN_MONTH_PREFIX",
    "TITLE_CAP",
    "SummaryFields",
    "continues",
    "english_bodies",
    "is_cut",
    "join_continuation",
    "repair_title",
    "tidy",
    "title_in_body",
    "tidy_update",
    "without_title",
]
