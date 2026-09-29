"""Typed language → BCP-47 tag (D-25; API_CONTRACT §3.4; AI_PROMPTS §4.8, §5.5 Part B).

Order: (1) ``data/languages.yaml`` — tag, English name, native name, the parenthesised alias
("Persian (Farsi)" → "farsi") and a few common aliases, compared case- and accent-insensitively;
a region/script variant of a known primary tag ("es-MX") maps to it; (2) the fast model
(``Task.resolve_language``) only for names the table does not know — its tag is accepted when it
matches ``LanguageTag`` and ``confidence != low``; (3) otherwise the private-use ``x-<slug>`` of
the typed name. A query with no letters at all ("123", "!!!") is ``422 language_unresolved``
before any model call; a typed private tag ("x-foo") resolves to itself without one.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from proxyhealth_api.ai.failover import AIService
from proxyhealth_api.ai.provider import Part, Task
from proxyhealth_api.contracts.enums import Confidence, DigitSystem, Direction, ErrorCode
from proxyhealth_api.contracts.model_out import LanguageResolveOut
from proxyhealth_api.errors import ApiError
from proxyhealth_api.packs.base import LanguageTable
from proxyhealth_api.packs.cache import is_valid_tag
from proxyhealth_api.packs.prompts import resolve_prompt, system_prompt

# Everyday names people type for languages in the table (keys are already folded).
ALIASES: dict[str, str] = {
    "farsi": "fa", "persian": "fa", "dari persian": "prs", "afghan persian": "prs",
    "filipino": "tl", "pilipino": "tl", "tagalog": "tl",
    "creole": "ht", "haitian": "ht", "kreyol": "ht", "haitian creole": "ht",
    "chinese": "zh-Hans", "mandarin": "zh-Hans", "simplified chinese": "zh-Hans",
    "cantonese": "zh-Hant", "traditional chinese": "zh-Hant",
    "portuguese": "pt-BR", "brazilian": "pt-BR", "brazilian portuguese": "pt-BR",
    "espanol": "es", "castellano": "es", "arabi": "ar", "arabic": "ar",
    "bangla": "bn", "punjabi": "pa", "panjabi": "pa", "myanmar": "my", "burmese": "my",
    "pushto": "ps", "pashtu": "ps", "kiswahili": "sw", "amharigna": "am", "kinyarwanda": "rw",
}  # fmt: skip

_NON_SLUG = re.compile(r"[^a-z0-9]+")
_SLUG_MAX = 32


@dataclass(frozen=True)
class Resolution:
    """Outcome of resolving a typed query; names/direction come from the model when unknown."""

    tag: str
    source: str  # "table" | "model" | "private"
    name_en: str
    name_native: str
    direction: Direction = Direction.ltr
    script: str | None = None
    digit_system: DigitSystem = DigitSystem.western


def fold(text: str) -> str:
    """Case-fold and strip accents/diacritics ("Español" → "espanol", "Kreyòl" → "kreyol")."""
    decomposed = unicodedata.normalize("NFKD", text.strip().casefold())
    return " ".join("".join(ch for ch in decomposed if not unicodedata.combining(ch)).split())


def slugify(query: str) -> str:
    """``x-<slug>`` body: ASCII letters/digits and ``-``; non-Latin names get a short hash.

    ``""`` when the query has no letter at all (nothing in it names a language). A typed private
    tag keeps its body ("x-foo" → "foo"), so it never becomes ``x-x-foo``.
    """
    folded = fold(query)
    if folded.startswith("x-"):
        folded = folded[2:]
    if not any(ch.isalpha() for ch in folded):
        return ""
    slug = _NON_SLUG.sub("-", folded).strip("-")[:_SLUG_MAX].strip("-")
    if any(ch.isalpha() for ch in slug):
        return slug
    return "u" + hashlib.sha256(folded.encode("utf-8")).hexdigest()[:10]


def resolve_in_table(query: str, languages: LanguageTable) -> str | None:
    """Table-only resolution; ``None`` when the query is not a known name or tag."""
    raw = query.strip()
    if not raw:
        return None
    q = fold(raw)
    by_tag = {tag.casefold(): tag for tag in languages.entries}
    if q in by_tag:
        return by_tag[q]
    for tag, entry in languages.entries.items():
        name_en = fold(entry.name_en)
        names = {name_en, fold(entry.name_native), name_en.split(" (")[0]}
        if "(" in name_en:
            names.add(name_en.split("(", 1)[1].rstrip(")").strip())
        if q in names:
            return tag
    alias = ALIASES.get(q)
    if alias and alias in languages.entries:
        return alias
    primary = q.split("-", 1)[0].split("_", 1)[0]
    if primary != q and primary in by_tag and is_valid_tag(raw.replace("_", "-")):
        return by_tag[primary]
    return None


async def resolve_language(
    query: str, languages: LanguageTable, ai: AIService, *, request_id: str
) -> Resolution:
    """Full resolution chain; raises ``ApiError(422 language_unresolved)`` for garbage."""
    raw = query.strip()
    known = resolve_in_table(raw, languages)
    if known is not None:
        entry = languages.entries[known]
        return Resolution(
            tag=known, source="table", name_en=entry.name_en, name_native=entry.name_native,
            direction=entry.direction, script=entry.script, digit_system=entry.digit_system,
        )  # fmt: skip
    slug = slugify(raw)
    if not slug:
        raise ApiError(
            ErrorCode.language_unresolved, 422, "The typed language could not be resolved."
        )
    folded = fold(raw)
    if folded.startswith("x-") and is_valid_tag(folded) and folded == f"x-{slug}":
        return Resolution(tag=folded, source="private", name_en=raw, name_native=raw)
    outcome = await ai.generate(
        task=Task.resolve_language,
        parts=[Part.of_text(resolve_prompt(raw))],
        system=system_prompt(),
        schema=LanguageResolveOut,
        request_id=request_id,
        hints={"language_query": raw},
    )
    out = outcome.result.parsed
    if isinstance(out, LanguageResolveOut):
        tag = (out.language_tag or "").strip()
        if tag and out.confidence is not Confidence.low and is_valid_tag(tag):
            table_hit = resolve_in_table(tag, languages)
            if table_hit is not None:
                entry = languages.entries[table_hit]
                return Resolution(
                    tag=table_hit, source="table", name_en=entry.name_en,
                    name_native=entry.name_native, direction=entry.direction,
                    script=entry.script, digit_system=entry.digit_system,
                )  # fmt: skip
            return Resolution(
                tag=tag, source="model", name_en=out.language_name_en or raw,
                name_native=out.language_name_native or raw, direction=out.direction,
                script=out.script, digit_system=out.digit_system,
            )  # fmt: skip
        return Resolution(
            tag=f"x-{slug}", source="private", name_en=raw, name_native=raw,
            direction=out.direction, script=out.script, digit_system=out.digit_system,
        )  # fmt: skip
    return Resolution(tag=f"x-{slug}", source="private", name_en=raw, name_native=raw)
