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
copy never passes through here; quotes never do either. Plan steps also pass §8.4's checks:
``fit_professional_step`` (a DOJ-accredited representative only where one fits, no copied
"Before that date,") and ``ensure_professional`` (a referral when the step names nobody, in
English or the step's own language). On a paper scored ``possible`` or ``likely`` scam no
referral or rewrite professional points back at the paper's own contact (TAXONOMY §6.4;
``scam_refer_to_by_category``, ``scam_professional_by_category``).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from proxyhealth_api.analysis.contacts_filter import new_contacts
from proxyhealth_api.analysis.i18n import Translator
from proxyhealth_api.analysis.verify import normalize
from proxyhealth_api.contracts.enums import (
    DocumentCategory,
    DocumentType,
    ReferTo,
    RefusalKind,
    ScamRisk,
    WarningCode,
)
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
    # Types whose professional differs from their category's (``nta`` is a court paper whose
    # professional includes DOJ-accredited representatives; a traffic ticket's does not).
    professional_by_document_type: Mapping[str, str] = field(default_factory=dict)
    # §8.4 per language (``languages.<tag>.professional_words``), checked on top of the English
    # ``professional_words``.
    professional_words_by_language: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    # §8.4 plan-step fit (``fit_professional_step``): the categories where a step may name a
    # DOJ-accredited representative, the patterns naming one (every language, then per
    # language), and the prompt openers a step with no demand loses.
    accredited_rep_categories: frozenset[str] = frozenset()
    accredited_rep_patterns: tuple[re.Pattern[str], ...] = ()
    accredited_rep_by_language: Mapping[str, tuple[re.Pattern[str], ...]] = field(
        default_factory=dict
    )
    copied_step_openers: tuple[re.Pattern[str], ...] = ()
    # Dangling words ``summary_text.repair_title`` drops from a cut title, per language.
    title_connectors_by_language: Mapping[str, frozenset[str]] = field(default_factory=dict)
    # TAXONOMY §6.4: on a possible/likely scam these replace ``refer_to_by_category`` and
    # ``professional_by_category`` where those point back at the paper's own contact.
    scam_refer_to_by_category: Mapping[str, str] = field(default_factory=dict)
    scam_professional_by_category: Mapping[str, str] = field(default_factory=dict)


def _compile(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


def _fold(text: str) -> str:
    """NFKC + case folding (word lists are compared in this form)."""
    return unicodedata.normalize("NFKC", text).casefold()


def _words(raw: Any, where: str) -> list[str]:
    """A YAML word list; a bare ``on``/``yes``/``no`` that YAML read as a boolean (or any other
    non-string) is an error, not a silent ``"true"``."""
    items = list(raw or [])
    bad = [w for w in items if not isinstance(w, str)]
    if bad:
        raise ValueError(f"phrasing.yaml {where}: quote these entries: {bad!r}")
    return items


def parse_config(data: Mapping[str, Any]) -> PhrasingConfig:
    """Compile a loaded ``phrasing.yaml`` mapping (raises on a bad regex)."""
    languages: dict[str, tuple[Family, ...]] = {}
    reviewed: dict[str, str | None] = {}
    attribution: dict[str, re.Pattern[str]] = {}
    pro_words: dict[str, tuple[str, ...]] = {}
    rep_patterns: dict[str, tuple[re.Pattern[str], ...]] = {}
    connectors: dict[str, frozenset[str]] = {}
    for tag, raw in (data.get("languages") or {}).items():
        if raw.get("attribution_regex"):
            attribution[str(tag)] = _compile(str(raw["attribution_regex"]))
        pro_words[str(tag)] = tuple(
            _fold(w) for w in _words(raw.get("professional_words"), f"{tag}.professional_words")
        )
        rep_patterns[str(tag)] = tuple(
            _compile(str(p)) for p in raw.get("accredited_rep_patterns") or []
        )
        connectors[str(tag)] = frozenset(
            _fold(w) for w in _words(raw.get("title_connectors"), f"{tag}.title_connectors")
        )
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
        professional_words=tuple(
            w.lower() for w in _words(data.get("professional_words"), "professional_words")
        ),
        languages=languages,
        reviewed_by=reviewed,
        attribution_by_language=attribution,
        professional_by_document_type=dict(data.get("professional_by_document_type") or {}),
        professional_words_by_language=pro_words,
        accredited_rep_categories=frozenset(
            str(c) for c in data.get("accredited_rep_categories") or []
        ),
        accredited_rep_patterns=tuple(
            _compile(str(p)) for p in data.get("accredited_rep_patterns") or []
        ),
        accredited_rep_by_language=rep_patterns,
        copied_step_openers=tuple(_compile(str(p)) for p in data.get("copied_step_openers") or []),
        title_connectors_by_language=connectors,
        scam_refer_to_by_category=dict(data.get("scam_refer_to_by_category") or {}),
        scam_professional_by_category=dict(data.get("scam_professional_by_category") or {}),
    )


@lru_cache(maxsize=4)
def load_config(path: Path = PHRASING_YAML) -> PhrasingConfig:
    """Load and cache ``phrasing.yaml``."""
    return parse_config(yaml.safe_load(path.read_text(encoding="utf-8")))


def _base(tag: str | None) -> str | None:
    return tag.split("-")[0].lower() if tag else None


def _section(language: str | None, c: PhrasingConfig) -> str | None:
    """The ``languages`` section for a BCP-47 tag (exact tag first, then its base)."""
    if not language:
        return None
    if language in c.languages:
        return language
    return next((t for t in c.languages if _base(t) == _base(language)), None)


def lint_languages(
    language: str | None, cfg: PhrasingConfig | None = None
) -> tuple[list[str], bool]:
    """(languages to lint with, ``unavailable``): ``en`` plus the text's language when its
    section is reviewed (TAXONOMY §8.1/§8.6: an unlisted *or unreviewed* language lints English
    only, and the caller warns ``phrasing_lint_unavailable``). A section with no families (only
    professional words, §8.4) lints nothing, so it counts as unavailable even when reviewed."""
    c = cfg or load_config()
    tags = ["en"]
    if language and _base(language) != "en":
        match = _section(language, c)
        if match is None or not c.reviewed_by.get(match) or not c.languages.get(match):
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


def _is_scam(scam_risk: ScamRisk) -> bool:
    return scam_risk is not ScamRisk.none


def professional_for(
    category: DocumentCategory | None,
    cfg: PhrasingConfig | None = None,
    document_type: DocumentType | None = None,
    *,
    scam_risk: ScamRisk = ScamRisk.none,
) -> str:
    """PRODUCT_SPEC §7.2 professional words for the rewrite template (the document type's own
    entry first: "a DOJ-accredited representative" only for immigration papers). On a possible or
    likely scam a category whose professional is the paper's own sender ("the office that sent
    this paper") gets ``scam_professional_by_category`` instead (TAXONOMY §6.4)."""
    c = cfg or load_config()
    key = category.value if category else "other"
    if _is_scam(scam_risk) and key in c.scam_professional_by_category:
        return c.scam_professional_by_category[key]
    if document_type is not None and document_type.value in c.professional_by_document_type:
        return c.professional_by_document_type[document_type.value]
    return c.professional_by_category.get(key) or c.professional_by_category.get(
        "other", "a professional"
    )


def refer_to_for(
    category: DocumentCategory | None,
    cfg: PhrasingConfig | None = None,
    *,
    scam_risk: ScamRisk = ScamRisk.none,
) -> ReferTo:
    """TAXONOMY §8.5 default ``refer_to_professional`` by category. On a possible or likely scam
    a referral back to the paper's own contact (``sender``, ``benefits_office``) gives way to
    ``scam_refer_to_by_category`` (TAXONOMY §6.4: the reader checks with the real office)."""
    c = cfg or load_config()
    key = category.value if category else "other"
    value = c.refer_to_by_category.get(key, "sender")
    if _is_scam(scam_risk):
        value = c.scam_refer_to_by_category.get(key, value)
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
    document_type: DocumentType | None = None,
    scam_risk: ScamRisk = ScamRisk.none,
) -> PhrasingResult:
    """Lint every sentence of one model-authored string; rewrite once, else hedge.

    ``language`` is the language the string is written in (``summary.body`` → target language,
    ``body_en`` → ``en``); an unlisted or unreviewed language lints English only and warns
    ``phrasing_lint_unavailable``. ``rewrite`` is optional: without it (or when it returns
    ``None``/a still-failing sentence) the fixed hedge is used directly. A replacement sentence
    already in the string (the rewrite template's referral, a repeated hedge) is not added again.
    ``scam_risk`` keeps the template's professional off the paper's own sender (§6.4).
    """
    c = cfg or load_config()
    langs, unavailable = lint_languages(language, c)
    result = PhrasingResult(text=text)
    if unavailable:
        result.warnings.append(WarningCode.phrasing_lint_unavailable)
    if not text or not text.strip():
        return result
    out: list[str] = []
    seen: set[str] = set()
    for sentence in split_sentences(text):
        fams = lint_sentence(sentence, category=category, languages=langs, cfg=c)
        if not fams:
            out.append(sentence)
            seen.add(normalize(sentence))
            continue
        result.families += [f for f in fams if f not in result.families]
        replacement: str | None = None
        if rewrite is not None:
            candidate = await rewrite(
                sentence, professional_for(category, c, document_type, scam_risk=scam_risk)
            )
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
        for part in split_sentences(replacement or ""):
            if normalize(part) not in seen:
                out.append(part)
                seen.add(normalize(part))
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


def optional_prose(
    text: str,
    *,
    category: DocumentCategory | None = None,
    language: str | None = "en",
    cfg: PhrasingConfig | None = None,
) -> str | None:
    """Optional model prose (a glossary definition, a plan step that is not the professional
    one and points at no demand) after the lint, with no rewrite: unchanged when clean; else each
    failing sentence is dropped (a ``dramatize``-only hit just loses its clause) and the clean
    sentences stay. ``None`` (drop the entry) when nothing is left. The rewrite template would
    put "The paper says …" in front of a sentence the paper never printed."""
    c = cfg or load_config()
    hits = lint_text(text, category=category, language=language, cfg=c)
    if not hits:
        return text
    failing = dict(hits)
    kept: list[str] = []
    for sentence in split_sentences(text):
        fams = failing.get(sentence)
        if fams is None:
            kept.append(sentence)
        elif all(f == DRAMATIZE for f in fams) and (calm := remove_dramatize(sentence, c)):
            kept.append(calm)
    return " ".join(kept) or None


def _is_latin(word: str) -> bool:
    return all(ord(ch) < 0x0250 for ch in word)


def names_professional(
    step_text: str, cfg: PhrasingConfig | None = None, language: str | None = None
) -> bool:
    """True when a ``professional`` plan step already names who can help (§8.4): an English
    ``professional_words`` entry, or one of the step language's own (``abogado``, ``محامٍ``,
    ``وکیل``). Latin-script words match at a word start; other scripts anywhere in the text,
    because a preposition may be joined to the word ("لمحامٍ")."""
    c = cfg or load_config()
    low = _fold(step_text)
    if any(re.search(rf"\b{re.escape(w)}", low) for w in c.professional_words):
        return True
    section = _section(language, c)
    for w in c.professional_words_by_language.get(section or "", ()):
        if (re.search(rf"\b{re.escape(w)}", low) if _is_latin(w) else w in low):
            return True
    return False


def ensure_professional(
    step_text: str,
    category: DocumentCategory | None,
    t: Translator,
    cfg: PhrasingConfig | None = None,
    *,
    language: str | None = None,
    scam_risk: ScamRisk = ScamRisk.none,
) -> str:
    """Append the category referral (``chat.refer.<ReferTo>``) to a professional step that names
    nobody ("a tax professional", "a free tax-help site" count as naming one); leave steps that
    already name a professional — in English or in ``language``, the step's own — or already
    carry the referral unchanged. On a possible or likely scam the referral never points back at
    the paper's own contact (``refer_to_for``)."""
    if names_professional(step_text, cfg, language):
        return step_text
    referral = t(f"chat.refer.{refer_to_for(category, cfg, scam_risk=scam_risk).value}")
    if normalize(referral) in normalize(step_text):
        return step_text
    base = step_text.rstrip()
    if base and not base.endswith((".", "!", "?", "。", "؟", "।")):
        base += "."
    return f"{base} {referral}".strip()


def names_accredited_rep(
    text: str, cfg: PhrasingConfig | None = None, language: str | None = "en"
) -> bool:
    """True when the text names a DOJ-accredited representative ("DOJ" next to an accreditation
    word in any language — not the DOJ as an agency — plus the English and the text language's
    own ``accredited_rep_patterns``)."""
    c = cfg or load_config()
    folded = _fold(text)
    patterns = [*c.accredited_rep_patterns, *c.accredited_rep_by_language.get("en", ())]
    section = _section(language, c)
    if section and section != "en":
        patterns += c.accredited_rep_by_language.get(section, ())
    return any(p.search(folded) for p in patterns)


def accredited_rep_fits(
    category: DocumentCategory | None,
    document_type: DocumentType | None = None,
    cfg: PhrasingConfig | None = None,
) -> bool:
    """§8.4: a plan step may name a DOJ-accredited representative only on the paper categories
    analyze.md Step 4 lists (``accredited_rep_categories``), and not when the type's own
    professional names none (``w2_1099``, ``itin``)."""
    c = cfg or load_config()
    if category is None or category.value not in c.accredited_rep_categories:
        return False
    own = c.professional_by_document_type.get(document_type.value) if document_type else None
    return own is None or names_accredited_rep(own, c)


def fit_professional_step(
    text: str,
    *,
    category: DocumentCategory | None,
    document_type: DocumentType | None,
    demand_id: str | None,
    t: Translator,
    language: str | None = "en",
    cfg: PhrasingConfig | None = None,
    scam_risk: ScamRisk = ScamRisk.none,
) -> tuple[str, bool]:
    """(step text, ``replaced``) — §8.4 checks on one model plan step (any kind).

    A step naming a DOJ-accredited representative on a paper where none fits (a medical bill, a
    lease, a tax or school notice) becomes the category's fixed ``chat.refer.<ReferTo>`` sentence
    (``replaced``; reviewed copy, so no model text and no organisation or contact is added) —
    on a possible or likely scam never one that points back at the paper's own contact
    (``refer_to_for``; TAXONOMY §6.4). A step with no ``demand_id`` that opens with the prompt's
    own example "Before that date," loses the opener; no date is put in its place.
    """
    c = cfg or load_config()
    if names_accredited_rep(text, c, language) and not accredited_rep_fits(
        category, document_type, c
    ):
        return t(f"chat.refer.{refer_to_for(category, c, scam_risk=scam_risk).value}"), True
    if demand_id is None:
        for opener in c.copied_step_openers:
            m = opener.match(text)
            rest = text[m.end() :].strip() if m else ""
            if rest:
                return rest[0].upper() + rest[1:], False
    return text, False


def title_connectors(language: str | None, cfg: PhrasingConfig | None = None) -> frozenset[str]:
    """English ``title_connectors`` plus the title language's own (folded)."""
    c = cfg or load_config()
    words = set(c.title_connectors_by_language.get("en", frozenset()))
    words |= c.title_connectors_by_language.get(_section(language, c) or "", frozenset())
    return frozenset(words)


__all__ = [
    "DRAMATIZE",
    "MAX_REWRITE_CHARS",
    "PHRASING_YAML",
    "Family",
    "PhrasingConfig",
    "PhrasingResult",
    "Rewriter",
    "accredited_rep_fits",
    "enforce",
    "ensure_professional",
    "fit_professional_step",
    "hedge_key",
    "is_attributed",
    "lint_languages",
    "lint_sentence",
    "lint_text",
    "load_config",
    "names_accredited_rep",
    "names_professional",
    "optional_prose",
    "parse_config",
    "professional_for",
    "refer_to_for",
    "refusal_kind_for",
    "remove_dramatize",
    "split_sentences",
    "title_connectors",
]
