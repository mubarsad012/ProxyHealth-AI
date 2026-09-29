"""``packs/resolve.py``: table → model → ``x-<slug>`` (D-25; AI_PROMPTS §4.8)."""

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from proxyhealth_api.ai.failover import GenerateOutcome
from proxyhealth_api.ai.provider import Part, StructuredResult, Task, Usage
from proxyhealth_api.ai.routing import RouteConfig
from proxyhealth_api.contracts.enums import (
    Confidence,
    DigitSystem,
    Direction,
    ModelQuality,
    ModelTier,
)
from proxyhealth_api.contracts.model_out import LanguageResolveOut
from proxyhealth_api.errors import ApiError
from proxyhealth_api.packs.base import LanguageTable
from proxyhealth_api.packs.resolve import fold, resolve_in_table, resolve_language, slugify
from proxyhealth_api.settings import DATA_DIR


@pytest.fixture(scope="module")
def languages() -> LanguageTable:
    return LanguageTable.load(DATA_DIR / "languages.yaml", DATA_DIR / "langpacks")


class FakeAI:
    """Stands in for ``AIService``; answers ``resolve_language`` with a fixed model output."""

    def __init__(self, out: LanguageResolveOut | None) -> None:
        self.out = out
        self.calls: list[tuple[Task, Mapping[str, str] | None, str]] = []

    async def generate(
        self, *, task: Task, parts: Sequence[Part], system: str, schema: Any,
        pages: int = 1, is_pdf: bool = False, request_id: str,
        hints: Mapping[str, str] | None = None,
    ) -> GenerateOutcome:  # fmt: skip
        self.calls.append((task, hints, parts[0].text or ""))
        route = RouteConfig(
            tier=ModelTier.fast, model_id="gemini-3.5-flash-lite", thinking=None,
            media_resolution=None, max_output_tokens=256,
        )  # fmt: skip
        result = StructuredResult(
            parsed=self.out, raw_text=None, model_id=route.model_id, usage=Usage()
        )
        return GenerateOutcome(
            result=result, route=route, quality=ModelQuality.full, slot_index=None, attempts=1,
            warnings=[],
        )  # fmt: skip


def model_out(tag: str | None, confidence: Confidence = Confidence.high) -> LanguageResolveOut:
    return LanguageResolveOut(
        language_tag=tag, language_name_en="Hakha Chin", language_name_native="Laiholh",
        script="Latn", direction=Direction.ltr, digit_system=DigitSystem.western,
        confidence=confidence,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("query", "tag"),
    [
        ("es", "es"), ("ES", "es"), ("Spanish", "es"), ("español", "es"), ("Espanol", "es"),
        ("  Dari ", "prs"), ("دری", "prs"), ("Pashto", "ps"), ("پښتو", "ps"),
        ("Farsi", "fa"), ("Persian", "fa"), ("zh-hant", "zh-Hant"), ("Filipino", "tl"),
        ("Haitian Creole", "ht"), ("kreyol", "ht"), ("es-MX", "es"), ("ar_EG", "ar"),
        ("Arabic", "ar"), ("Rohingya", "rhg"),
    ],
)  # fmt: skip
def test_table_resolution(languages: LanguageTable, query: str, tag: str) -> None:
    assert resolve_in_table(query, languages) == tag


def test_unknown_names_are_not_in_table(languages: LanguageTable) -> None:
    for query in ("Hakha Chin", "Kaqchikel", "", "   ", "xx-YY"):
        assert resolve_in_table(query, languages) is None


def test_fold_and_slugify() -> None:
    assert fold("  Kreyòl  Ayisyen ") == "kreyol ayisyen"
    assert slugify("Hakha Chin") == "hakha-chin"
    assert slugify("K'iche'") == "k-iche"
    assert slugify("x" * 50) == "x" * 32
    non_latin = slugify("ᏣᎳᎩ")
    assert non_latin.startswith("u") and len(non_latin) == 11 and non_latin == slugify("ᏣᎳᎩ")
    assert slugify("!!! 123 ???") == ""  # no letter: nothing names a language (422)
    assert slugify("123") == "" and slugify("٣٤٥") == "" and slugify("x-123") == ""
    assert slugify("!!! ???") == ""
    assert slugify("x-foo") == "foo" and slugify("X-Foo") == "foo"  # never x-x-foo
    assert slugify("123abc") == "123abc"


async def test_table_hit_never_calls_the_model(languages: LanguageTable) -> None:
    ai = FakeAI(model_out("cnh"))
    res = await resolve_language("Dari", languages, ai, request_id="r")  # type: ignore[arg-type]
    assert res.tag == "prs" and res.source == "table" and res.direction == "rtl"
    assert ai.calls == []


async def test_model_tag_accepted_when_confident(languages: LanguageTable) -> None:
    ai = FakeAI(model_out("cnh"))
    res = await resolve_language("Hakha Chin", languages, ai, request_id="r")  # type: ignore[arg-type]
    assert res.tag == "cnh" and res.source == "model" and res.name_native == "Laiholh"
    task, hints, prompt = ai.calls[0]
    assert task is Task.resolve_language and hints == {"language_query": "Hakha Chin"}
    assert "<<<Hakha Chin>>>" in prompt  # typed text wrapped as data


async def test_model_tag_in_table_maps_to_table_entry(languages: LanguageTable) -> None:
    ai = FakeAI(model_out("fa"))
    res = await resolve_language("Parsi", languages, ai, request_id="r")  # type: ignore[arg-type]
    assert res.tag == "fa" and res.source == "table" and res.name_en == "Persian (Farsi)"


@pytest.mark.parametrize(
    "out",
    [model_out(None), model_out("cnh", Confidence.low), model_out("not a tag!"), None],
    ids=["null", "low", "invalid", "no-output"],
)
async def test_private_tag_fallback(
    languages: LanguageTable, out: LanguageResolveOut | None
) -> None:
    ai = FakeAI(out)
    res = await resolve_language("Hakha Chin", languages, ai, request_id="r")  # type: ignore[arg-type]
    assert res.tag == "x-hakha-chin" and res.source == "private"
    assert res.name_en == "Hakha Chin"


async def test_garbage_is_422(languages: LanguageTable) -> None:
    ai = FakeAI(model_out(None))
    with pytest.raises(ApiError) as exc:
        await resolve_language("?!?!", languages, ai, request_id="r")  # type: ignore[arg-type]
    assert exc.value.status == 422 and exc.value.code == "language_unresolved"
    assert ai.calls == []


@pytest.mark.parametrize("query", ["123", "!!! 123 ???", "x-42"])
async def test_digits_only_is_422_without_a_model_call(
    languages: LanguageTable, query: str
) -> None:
    ai = FakeAI(model_out("cnh"))
    with pytest.raises(ApiError) as exc:
        await resolve_language(query, languages, ai, request_id="r")  # type: ignore[arg-type]
    assert exc.value.status == 422 and exc.value.code == "language_unresolved"
    assert ai.calls == []


async def test_typed_private_tag_resolves_to_itself(languages: LanguageTable) -> None:
    ai = FakeAI(model_out("cnh"))
    res = await resolve_language("x-foo", languages, ai, request_id="r")  # type: ignore[arg-type]
    assert res.tag == "x-foo" and res.source == "private" and ai.calls == []
