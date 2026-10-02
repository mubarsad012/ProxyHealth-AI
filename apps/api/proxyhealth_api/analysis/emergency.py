"""Emergency lexicon (D-14; COMPLIANCE_PRIVACY §7; AI_PROMPTS §11.7).

``data/safety/emergency.yaml`` holds per-language keyword lists for nine kinds (chest pain,
breathing, overdose, poison, self-harm, stroke, bleeding, allergic reaction, violence). The scan
runs over the transcript (analysis), ``question`` + ``messages`` (chat) or ``screen_text`` +
``user_goal`` (troubleshoot) in the detected language, the target language and always ``en`` +
``es``; what the user typed runs through every language's list. Any hit — or a non-empty model
``emergency_terms_found`` / ``TaggingModelOut.emergency`` / a chat or troubleshoot ``crisis``
tag — sets ``Safety.emergency`` so the client shows the fixed emergency card first. A detected or
target language without a list adds ``warnings: [emergency_lexicon_unavailable]``. The bias is to
over-trigger: a language's ``exclude`` phrases ("Poison Control", "If swallowed") are removed
only from printed text (``texts``), never from what the user typed (``user_texts``: the chat
question, the troubleshoot ``user_goal``). A language's optional ``proclitics`` (Arabic و ف ب ل ك,
written attached to the next word) may stand before a term, so "ولا أستطيع التنفس" matches "لا
أستطيع التنفس". Pure functions; nothing logged.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast

import yaml

from proxyhealth_api.analysis.verify import normalize
from proxyhealth_api.contracts.analysis import Safety
from proxyhealth_api.contracts.enums import WarningCode
from proxyhealth_api.settings import DATA_DIR

EMERGENCY_YAML = DATA_DIR / "safety" / "emergency.yaml"
KINDS: tuple[str, ...] = (
    "chest_pain", "breathing", "overdose", "poison", "self_harm", "stroke", "bleeding",
    "allergic", "violence",
)  # fmt: skip
MatchMode = Literal["word", "prefix", "substring"]
# Zero-width space/joiners (Persian ZWNJ in "نمی\u200cتوانم") become spaces; term parts then
# match with or without the gap, so the spaced, joined and ZWNJ spellings are the same.
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), " ")
# Arabic-script spellings people type interchangeably fold to one letter (terms and texts alike):
# hamza-carrying alefs → ا, Arabic yeh/alef maksura ↔ Persian yeh, Arabic ↔ Persian kaf, teh
# marbuta/heh-yeh → ه; harakat and tatweel are dropped. "انتحر" then matches "أنتحر".
_ARABIC_FOLD = {
    **dict.fromkeys(map(ord, "أإآٱ"), "ا"), **dict.fromkeys(map(ord, "يى"), "ی"),
    ord("ك"): "ک", **dict.fromkeys(map(ord, "ةۀ"), "ه"),
    **dict.fromkeys([*range(0x064B, 0x0660), 0x0670, 0x0640], None),
}  # fmt: skip
# Latin letters written with or without their accent match each other ("tomo" = "tomó",
# "suicidarme" typed without accents): each accented vowel of a term becomes a class.
_ACCENT_CLASS = {
    "á": "[áa]", "à": "[àa]", "â": "[âa]", "ã": "[ãa]", "é": "[ée]", "è": "[èe]", "ê": "[êe]",
    "í": "[íi]", "ì": "[ìi]", "î": "[îi]", "ó": "[óo]", "ò": "[òo]", "ô": "[ôo]", "õ": "[õo]",
    "ú": "[úu]", "ù": "[ùu]", "û": "[ûu]", "ü": "[üu]", "ñ": "[ñn]", "ç": "[çc]",
}  # fmt: skip
_TAG_ALIASES: Mapping[str, str] = {
    "zh": "zh-Hans", "zh-cn": "zh-Hans", "zh-sg": "zh-Hans", "zh-hans": "zh-Hans",
    "zh-tw": "zh-Hant", "zh-hk": "zh-Hant", "zh-mo": "zh-Hant", "zh-hant": "zh-Hant",
    "pt": "pt-BR", "pt-br": "pt-BR", "pt-pt": "pt-BR", "fa-af": "prs", "fil": "tl",
}  # fmt: skip


def normalize_for_match(text: str) -> str:
    """The D-09 normaliser, zero-width joiners as spaces, case-folded (terms and texts alike)."""
    return normalize(text.translate(_ZERO_WIDTH)).casefold().translate(_ARABIC_FOLD)


def _escape_part(part: str) -> str:
    return "".join(_ACCENT_CLASS.get(ch) or re.escape(ch) for ch in part)


def _term_regex(term: str, mode: MatchMode, proclitics: str = "") -> str:
    """One term as a regex. ``proclitics`` (an alternation of attached one-letter prefixes such
    as Arabic و/ف/ب/ل/ك) may stand before the term's first word: "ولا أستطيع التنفس" ("and I
    cannot breathe") then matches the term "لا أستطيع التنفس"."""
    raw = normalize_for_match(term)
    open_end = raw.endswith("*")
    raw = raw.rstrip("*")
    body = r"\s*".join(_escape_part(part) for part in raw.split(" ") if part)
    if mode == "substring":
        return body
    lead = rf"(?:{proclitics}){{0,2}}" if proclitics else ""
    if mode == "prefix" or open_end:
        return rf"(?<!\w){lead}{body}"
    return rf"(?<!\w){lead}{body}(?!\w)"


def _proclitic_alternation(values: Iterable[object]) -> str:
    folded = [normalize_for_match(str(v)).strip() for v in values]
    return "|".join(re.escape(v) for v in dict.fromkeys(folded) if v)


@dataclass(frozen=True)
class LanguageLexicon:
    """One language's compiled lists."""

    tag: str
    reviewed_by: str | None
    match: MatchMode
    patterns: Mapping[str, re.Pattern[str]]
    exclude: tuple[str, ...]


@dataclass(frozen=True)
class Lexicon:
    """The whole ``emergency.yaml``."""

    version: str
    kinds: tuple[str, ...]
    fallback_languages: tuple[str, ...]
    languages: Mapping[str, LanguageLexicon]

    def resolve(self, tag: str | None) -> str | None:
        """The lexicon tag for a BCP-47-ish tag (``es-MX`` → ``es``, ``zh-TW`` → ``zh-Hant``)."""
        if not tag:
            return None
        if tag in self.languages:
            return tag
        low = tag.lower()
        for known in self.languages:
            if known.lower() == low:
                return known
        alias = _TAG_ALIASES.get(low) or _TAG_ALIASES.get(low.split("-")[0])
        if alias and alias in self.languages:
            return alias
        primary = low.split("-")[0]
        return primary if primary in self.languages else None


def parse_lexicon(data: Mapping[str, Any]) -> Lexicon:
    """Compile a loaded ``emergency.yaml`` mapping (raises on an unknown kind or mode)."""
    kinds = tuple(str(k) for k in data.get("kinds") or KINDS)
    languages: dict[str, LanguageLexicon] = {}
    for tag, raw in (data.get("languages") or {}).items():
        raw_mode = str(raw.get("match") or "word")
        if raw_mode not in ("word", "prefix", "substring"):
            raise ValueError(f"emergency.yaml: {tag}: unknown match mode {raw_mode!r}")
        mode = cast(MatchMode, raw_mode)
        proclitics = _proclitic_alternation(raw.get("proclitics") or [])
        patterns: dict[str, re.Pattern[str]] = {}
        for kind, terms in (raw.get("terms") or {}).items():
            if kind not in kinds:
                raise ValueError(f"emergency.yaml: {tag}: unknown kind {kind!r}")
            alts = [_term_regex(str(t), mode, proclitics) for t in terms or [] if str(t).strip()]
            if alts:
                patterns[str(kind)] = re.compile("|".join(alts))
        languages[str(tag)] = LanguageLexicon(
            tag=str(tag), reviewed_by=raw.get("reviewed_by"), match=mode,
            patterns=patterns,
            exclude=tuple(normalize_for_match(str(x)) for x in raw.get("exclude") or []),
        )  # fmt: skip
    return Lexicon(
        version=str(data.get("version", "0")),
        kinds=kinds,
        fallback_languages=tuple(str(x) for x in data.get("fallback_languages") or ["en", "es"]),
        languages=languages,
    )


@lru_cache(maxsize=4)
def load_lexicon(path: Path = EMERGENCY_YAML) -> Lexicon:
    """Load and cache ``emergency.yaml``."""
    return parse_lexicon(yaml.safe_load(path.read_text(encoding="utf-8")))


def languages_to_scan(
    detected_language: str | None,
    target_language: str | None,
    lexicon: Lexicon | None = None,
) -> tuple[list[str], bool]:
    """(lexicon tags to run, ``unavailable``): detected + target + the en/es fallbacks.

    ``unavailable`` is true when the detected or target language has no list of its own.
    """
    lex = lexicon or load_lexicon()
    tags: list[str] = []
    unavailable = False
    for tag in (detected_language, target_language):
        if not tag:
            continue
        resolved = lex.resolve(tag)
        if resolved is None:
            unavailable = True
        elif resolved not in tags:
            tags.append(resolved)
    for fb in lex.fallback_languages:
        if fb in lex.languages and fb not in tags:
            tags.append(fb)
    return tags, unavailable


def scan_text(
    text: str,
    tags: Sequence[str],
    lexicon: Lexicon | None = None,
    *,
    apply_exclude: bool = True,
) -> list[str]:
    """Kinds whose terms occur in ``text`` for any of ``tags`` (fixed kind order, de-duplicated).

    ``apply_exclude=False`` keeps the ``exclude`` phrases (use it for text the user typed).
    """
    lex = lexicon or load_lexicon()
    if not text:
        return []
    norm = normalize_for_match(text)
    for tag in tags if apply_exclude else ():
        lang = lex.languages.get(tag)
        if lang is None:
            continue
        for phrase in lang.exclude:
            if phrase:
                norm = norm.replace(phrase, " ")
    hits: set[str] = set()
    for tag in tags:
        lang = lex.languages.get(tag)
        if lang is None:
            continue
        for kind, pattern in lang.patterns.items():
            if kind not in hits and pattern.search(norm):
                hits.add(kind)
    return [k for k in lex.kinds if k in hits]


def map_model_terms(terms: Iterable[str], lexicon: Lexicon | None = None) -> list[str]:
    """Kinds for the model's ``emergency_terms_found`` (every language's lists are tried)."""
    lex = lexicon or load_lexicon()
    joined = "\n".join(t for t in terms if t and t.strip())
    return scan_text(joined, list(lex.languages), lex) if joined else []


@dataclass
class EmergencyOutcome:
    """``detect_emergency`` result: the contract ``Safety`` plus warnings to merge."""

    safety: Safety
    warnings: list[WarningCode] = field(default_factory=list)
    languages_scanned: list[str] = field(default_factory=list)
    model_only: bool = False


def detect_emergency(
    texts: Iterable[str],
    *,
    detected_language: str | None,
    target_language: str | None,
    model_terms: Iterable[str] = (),
    model_flag: bool = False,
    credential_or_payment_request: bool = False,
    lexicon: Lexicon | None = None,
    user_texts: Iterable[str] = (),
) -> EmergencyOutcome:
    """Run the lexicon over ``texts`` (printed or quoted text: transcript blocks, troubleshoot
    ``screen_text``, assistant chat turns) and ``user_texts`` (typed by the user: the chat
    ``question`` and the user's own earlier turns, the troubleshoot ``user_goal``), and fold in
    the model's own emergency hints.

    ``exclude`` phrases are removed from ``texts`` only, so "should I call poison control?"
    typed by the user still counts.

    ``model_terms`` = ``emergency_terms_found``; ``model_flag`` = ``TaggingModelOut.emergency``.
    Either one alone sets ``emergency=true`` (over-trigger bias) with kinds mapped by keyword
    where possible. ``credential_or_payment_request`` is copied into ``Safety`` (troubleshoot).
    """
    lex = lexicon or load_lexicon()
    tags, unavailable = languages_to_scan(detected_language, target_language, lex)
    kinds: set[str] = set()
    for text in texts:
        kinds.update(scan_text(text, tags, lex))
    # What the reader typed may be in any language (a Dari speaker asking about a Spanish paper
    # in English …): it is short, so every list runs over it.
    every = [*tags, *(tag for tag in lex.languages if tag not in tags)]
    for text in user_texts:
        kinds.update(scan_text(text, every, lex, apply_exclude=False))
    model_list = [t for t in model_terms if t and t.strip()]
    model_kinds = map_model_terms(model_list, lex)
    lexicon_hit = bool(kinds)
    kinds.update(model_kinds)
    emergency = lexicon_hit or bool(model_list) or model_flag
    safety = Safety(
        emergency=emergency,
        emergency_kinds=[k for k in lex.kinds if k in kinds],
        credential_or_payment_request=credential_or_payment_request,
    )
    warnings = [WarningCode.emergency_lexicon_unavailable] if unavailable else []
    return EmergencyOutcome(
        safety=safety, warnings=warnings, languages_scanned=tags,
        model_only=emergency and not lexicon_hit,
    )  # fmt: skip


def has_lexicon(tag: str, lexicon: Lexicon | None = None) -> bool:
    """True when ``tag`` resolves to a language with its own list."""
    return (lexicon or load_lexicon()).resolve(tag) is not None


__all__ = [
    "EMERGENCY_YAML",
    "KINDS",
    "EmergencyOutcome",
    "LanguageLexicon",
    "Lexicon",
    "detect_emergency",
    "has_lexicon",
    "languages_to_scan",
    "load_lexicon",
    "map_model_terms",
    "normalize_for_match",
    "parse_lexicon",
    "scan_text",
]
