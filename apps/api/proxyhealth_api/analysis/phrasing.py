"""Phrasing lint — information, not advice (D-17; DOCUMENT_TAXONOMY §8; AI_PROMPTS §11.9).

Every model-authored sentence is linted against ``data/safety/phrasing.yaml`` (English always;
the text's own language only when its section is reviewed, i.e. ``reviewed_by`` is set —
otherwise English only plus ``phrasing_lint_unavailable``, TAXONOMY §8.1/§8.6). A hit gets
**one** rewrite through the caller's ``rewrite`` callable (task ``phrasing_rewrite``, template
"The paper says X. A {professional} can tell you what it means for you."); the rewrite must
pass the lint and contain no contact the original sentence did not already carry (contacts
printed on the paper were vetted by ``contacts_filter.py`` and are left alone here). Otherwise
the family's fixed hedge — an existing ``chat.refusal.*`` template via ``t`` — replaces the
sentence; for ``dramatize`` the offending clause is deleted instead (and the sentence dropped
when nothing remains). Each replacement counts in ``verification.phrasing_rewrites``. Fixed
copy never passes through here; quotes never do either.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from proxyhealth_api.analysis.contacts_filter import new_contacts
from proxyhealth_api.analysis.i18n import Translator
from proxyhealth_api.analysis.verify import normalize
from proxyhealth_api.contracts.enums import DocumentCategory, ReferTo, RefusalKind, WarningCode
from proxyhealth_api.settings import DATA_DIR

PHRASING_YAML = DATA_DIR / "safety" / "phrasing.yaml"
DRAMATIZE = "dramatize"
MAX_REWRITE_CHARS = 400
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。؟।])\s+")
_FAMILY_REFUSAL: Mapping[str, RefusalKind] = {
    "chat.refusal.eligibility": RefusalKind.eligibility,
    "chat.refusal.filing_advice": RefusalKind.filing_advice,
    "chat.refusal.outcome": RefusalKind.outcome,
    "chat.refusal.medical_interpretation": RefusalKind.medical_interpretation,
    "chat.refusal.contact_request": RefusalKind.contact_request,
}

Rewriter = Callable[[str, str], Awaitable[str | None]]
"""``async rewrite(sentence, professional) -> str | None`` (the pipeline wraps ``AIService``
with task ``phrasing_rewrite``; ``None`` when the fast tier is unavailable)."""


@dataclass(frozen=True)
class Family:
    """One pattern family for one language."""

    id: str
    domains: frozenset[str]
    skip_when_attributed: bool
    patterns: tuple[re.Pattern[str], ...]
    medical_words: re.Pattern[str] | None = None

    def applies_to(self, category: DocumentCategory | None, sentence: str) -> bool:
        """``all`` domains, the paper's category, or a medicine/test word for medical rules."""
        if "all" in self.domains or category is None or category.value in self.domains:
            return True
        return bool(self.medical_words and self.medical_words.search(sentence))


@dataclass(frozen=True)
class PhrasingConfig:
    """Parsed ``phrasing.yaml`` (schema DOCUMENT_TAXONOMY §8.6)."""

    version: str
    attribution: re.Pattern[str]
    professional_by_category: Mapping[str, str]
    refer_to_by_category: Mapping[str, str]
    hedge_key_by_family: Mapping[str, str | None]
    professional_words: tuple[str, ...]
    languages: Mapping[str, tuple[Family, ...]]
    reviewed_by: Mapping[str, str | None]
    # §8.3 attribution exemption per language (``languages.<tag>.attribution_regex``), used on
    # top of the English ``attribution`` when that language's families are linted.
    attribution_by_language: Mapping[str, re.Pattern[str]] = field(default_factory=dict)


def _compile(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


def parse_config(data: Mapping[str, Any]) -> PhrasingConfig:
    """Compile a loaded ``phrasing.yaml`` mapping (raises on a bad regex)."""
    languages: dict[str, tuple[Family, ...]] = {}
    reviewed: dict[str, str | None] = {}
    attribution: dict[str, re.Pattern[str]] = {}
    for tag, raw in (data.get("languages") or {}).items():
        if raw.get("attribution_regex"):
            attribution[str(tag)] = _compile(str(raw["attribution_regex"]))
        fams: list[Family] = []
        for f in raw.get("families") or []:
            words = f.get("medical_words")
            fams.append(
                Family(
                    id=str(f["id"]),
                    domains=frozenset(str(d) for d in f.get("domains") or ["all"]),
                    skip_when_attributed=bool(f.get("skip_when_attributed", False)),
                    patterns=tuple(_compile(str(p)) for p in f.get("patterns") or []),
                    medical_words=_compile(str(words)) if words else None,
                )
            )
        languages[str(tag)] = tuple(fams)
        reviewed[str(tag)] = raw.get("reviewed_by")
    return PhrasingConfig(
        version=str(data.get("version", "0")),
        attribution=_compile(str(data["attribution_regex"])),
        professional_by_category=dict(data.get("professional_by_category") or {}),
        refer_to_by_category=dict(data.get("refer_to_by_category") or {}),
        hedge_key_by_family=dict(data.get("hedge_key_by_family") or {}),
        professional_words=tuple(str(w).lower() for w in data.get("professional_words") or []),
        languages=languages,
        reviewed_by=reviewed,
        attribution_by_language=attribution,
    )


@lru_cache(maxsize=4)
def load_config(path: Path = PHRASING_YAML) -> PhrasingConfig:
    """Load and cache ``phrasing.yaml``."""
    return parse_config(yaml.safe_load(path.read_text(encoding="utf-8")))


def _base(tag: str | None) -> str | None:
    return tag.split("-")[0].lower() if tag else None


def lint_languages(
    language: str | None, cfg: PhrasingConfig | None = None
) -> tuple[list[str], bool]:
    """(languages to lint with, ``unavailable``): ``en`` plus the text's language when its
    section is reviewed (TAXONOMY §8.1/§8.6: an unlisted *or unreviewed* language lints English
    only, and the caller warns ``phrasing_lint_unavailable``)."""
    c = cfg or load_config()
    tags = ["en"]
    if language and _base(language) != "en":
        match = next((t for t in c.languages if t == language or _base(t) == _base(language)), None)
        if match is None or not c.reviewed_by.get(match):
            return tags, True
        tags.append(match)
    return tags, False


def split_sentences(text: str) -> list[str]:
    """Sentences split after ``.!?`` and the CJK/Arabic/Devanagari terminators ``。؟।``."""
    return [s for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s]


def is_attributed(
    sentence: str, cfg: PhrasingConfig | None = None, languages: Sequence[str] = ("en",)
) -> bool:
    """True when the sentence reports what the paper says ("The letter says …", "It says …";
    "La carta dice …" with the ``es`` section's own ``attribution_regex``)."""
    c = cfg or load_config()
    text = normalize(sentence)
    if c.attribution.search(text):
        return True
    return any(
        (rx := c.attribution_by_language.get(tag)) is not None and rx.search(text)
        for tag in languages
    )


def lint_sentence(
    sentence: str,
    *,
    category: DocumentCategory | None = None,
    languages: Sequence[str] = ("en",),
    cfg: PhrasingConfig | None = None,
    original: str | None = None,
) -> list[str]:
    """Family ids the sentence violates (de-duplicated, table order); ``[]`` = clean.

    Contacts are ``contacts_filter.py``'s job, so a sentence is never failed for carrying one.
    When ``original`` is given, ``sentence`` is a rewrite candidate for it and also reports
    ``contact_like`` if it adds a phone/URL/e-mail/address the original did not have
    (DOCUMENT_TAXONOMY §8.2: a rewrite never re-introduces one).
    """
    c = cfg or load_config()
    text = normalize(sentence)
    attributed = is_attributed(text, c, languages)
    hits: list[str] = []
    for tag in languages:
        for fam in c.languages.get(tag, ()):
            if fam.id in hits or (fam.skip_when_attributed and attributed):
                continue
            if not fam.applies_to(category, text):
                continue
            if any(p.search(text) for p in fam.patterns):
                hits.append(fam.id)
    if original is not None and "contact_like" not in hits and new_contacts(text, original):
        hits.append("contact_like")
    return hits


def professional_for(category: DocumentCategory | None, cfg: PhrasingConfig | None = None) -> str:
    """PRODUCT_SPEC §7.2 professional words for the rewrite template."""
    c = cfg or load_config()
    key = category.value if category else "other"
    return c.professional_by_category.get(key) or c.professional_by_category.get(
        "other", "a professional"
    )


def refer_to_for(category: DocumentCategory | None, cfg: PhrasingConfig | None = None) -> ReferTo:
    """TAXONOMY §8.5 default ``refer_to_professional`` by category."""
    c = cfg or load_config()
    value = c.refer_to_by_category.get(category.value if category else "other", "sender")
    return ReferTo(value)


def hedge_key(families: Sequence[str], cfg: PhrasingConfig | None = None) -> str | None:
    """The first non-null ``hedge_key_by_family`` for the hit families (``None`` = dramatize)."""
    c = cfg or load_config()
    for fam in families:
        key = c.hedge_key_by_family.get(fam)
        if key:
            return key
    return None


def refusal_kind_for(families: Sequence[str], cfg: PhrasingConfig | None = None) -> RefusalKind:
    """Chat: the ``RefusalKind`` implied by the hedge that replaced an answer sentence."""
    key = hedge_key(families, cfg)
    return _FAMILY_REFUSAL.get(key or "", RefusalKind.none)


_DRAMA_TOKEN_RE = re.compile(r"\b(URGENT|WARNING|IMMEDIATELY)\b[:!,]?\s*")
_CLAUSE_SPLIT_RE = re.compile(r"\s*(?:[,;:—–]|\s-\s)\s*")


def remove_dramatize(sentence: str, cfg: PhrasingConfig | None = None) -> str:
    """Delete the dramatizing clause/tokens; ``""`` when nothing calm remains."""
    c = cfg or load_config()
    text = _DRAMA_TOKEN_RE.sub("", sentence).replace("!", ".")
    text = re.sub(r"\.{2,}", ".", text).strip()
    drama = next((f for f in c.languages.get("en", ()) if f.id == DRAMATIZE), None)
    if drama is None:
        return text
    clauses = [cl for cl in _CLAUSE_SPLIT_RE.split(text.rstrip(".")) if cl]
    kept = [cl for cl in clauses if not any(p.search(cl) for p in drama.patterns)]
    if not kept:
        return ""
    out = ", ".join(kept).strip()
    if not out:
        return ""
    out = out[0].upper() + out[1:]
    return out if out.endswith((".", "?")) else out + "."


@dataclass
class PhrasingResult:
    """Outcome of linting one string."""

    text: str
    replacements: int = 0
    hedged: int = 0
    rewritten: int = 0
    families: list[str] = field(default_factory=list)
    warnings: list[WarningCode] = field(default_factory=list)


def _fallback(sentence: str, families: list[str], t: Translator, c: PhrasingConfig) -> str:
    key = hedge_key([f for f in families if f != DRAMATIZE], c)
    if key is None:
        return remove_dramatize(sentence, c)
    return t(key)


async def enforce(
    text: str,
    *,
    t: Translator,
    category: DocumentCategory | None = None,
    language: str | None = "en",
    rewrite: Rewriter | None = None,
    cfg: PhrasingConfig | None = None,
) -> PhrasingResult:
    """Lint every sentence of one model-authored string; rewrite once, else hedge.

    ``language`` is the language the string is written in (``summary.body`` → target language,
    ``body_en`` → ``en``); an unlisted or unreviewed language lints English only and warns
    ``phrasing_lint_unavailable``. ``rewrite`` is optional: without it (or when it returns
    ``None``/a still-failing sentence) the fixed hedge is used directly.
    """
    c = cfg or load_config()
    langs, unavailable = lint_languages(language, c)
    result = PhrasingResult(text=text)
    if unavailable:
        result.warnings.append(WarningCode.phrasing_lint_unavailable)
    if not text or not text.strip():
        return result
    out: list[str] = []
    for sentence in split_sentences(text):
        fams = lint_sentence(sentence, category=category, languages=langs, cfg=c)
        if not fams:
            out.append(sentence)
            continue
        result.families += [f for f in fams if f not in result.families]
        replacement: str | None = None
        if rewrite is not None:
            candidate = await rewrite(sentence, professional_for(category, c))
            if candidate:
                candidate = candidate.strip()[:MAX_REWRITE_CHARS]
                if candidate and not lint_sentence(
                    candidate, category=category, languages=langs, cfg=c, original=sentence
                ):
                    replacement = candidate
                    result.rewritten += 1
        if replacement is None:
            replacement = _fallback(sentence, fams, t, c)
            result.hedged += 1
        result.replacements += 1
        if replacement and (not out or out[-1] != replacement):
            out.append(replacement)
    result.text = " ".join(out)
    return result


def lint_text(
    text: str,
    *,
    category: DocumentCategory | None = None,
    language: str | None = "en",
    cfg: PhrasingConfig | None = None,
) -> list[tuple[str, list[str]]]:
    """(sentence, families) for every failing sentence — the golden-test / CI helper."""
    c = cfg or load_config()
    langs, _ = lint_languages(language, c)
    out: list[tuple[str, list[str]]] = []
    for sentence in split_sentences(text or ""):
        fams = lint_sentence(sentence, category=category, languages=langs, cfg=c)
        if fams:
            out.append((sentence, fams))
    return out


def names_professional(step_text: str, cfg: PhrasingConfig | None = None) -> bool:
    """True when a ``professional`` plan step already names who can help (§8.4)."""
    c = cfg or load_config()
    low = step_text.casefold()
    return any(re.search(rf"\b{re.escape(w)}", low) for w in c.professional_words)


def ensure_professional(
    step_text: str,
    category: DocumentCategory | None,
    t: Translator,
    cfg: PhrasingConfig | None = None,
) -> str:
    """Append the category referral (``chat.refer.<ReferTo>``) to a professional step that names
    nobody; leave steps that already name a professional unchanged."""
    if names_professional(step_text, cfg):
        return step_text
    referral = t(f"chat.refer.{refer_to_for(category, cfg).value}")
    base = step_text.rstrip()
    if base and not base.endswith((".", "!", "?", "。", "؟", "।")):
        base += "."
    return f"{base} {referral}".strip()


__all__ = [
    "DRAMATIZE",
    "MAX_REWRITE_CHARS",
    "PHRASING_YAML",
    "Family",
    "PhrasingConfig",
    "PhrasingResult",
    "Rewriter",
    "enforce",
    "ensure_professional",
    "hedge_key",
    "is_attributed",
    "lint_languages",
    "lint_sentence",
    "lint_text",
    "load_config",
    "names_professional",
    "parse_config",
    "professional_for",
    "refer_to_for",
    "refusal_kind_for",
    "remove_dramatize",
    "split_sentences",
]
