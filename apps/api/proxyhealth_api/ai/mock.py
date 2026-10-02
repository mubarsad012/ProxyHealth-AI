"""``MockProvider`` — zero-key mode as a real product surface (D-29; AI_PROMPTS §10.1; BUILD_PLAN
§5.8 mock-parity table). Deterministic apart from the simulated latency
(``MOCK_LATENCY_MIN_MS``–``MOCK_LATENCY_MAX_MS``; 0 in tests).

Resolution for the reading tasks (``analyze_single``, ``explain``, ``transcribe``):
``hints["demo_sample_id"]`` → that fixture; else the 16×16 dHash of the first page against the
document fixtures (Hamming ≤ ``MOCK_PHASH_MAX_HAMMING``); else the generic "not recognised"
output (``legibility=poor``, ``readable_reason="mock_no_match"``). A matched fixture serves
``out.<target_language>.json`` when recorded, otherwise its English output with a visible ``⟦tag⟧``
marker on every user-facing string. ``troubleshoot`` does the same against screenshot fixtures.
``chat`` answers from the request's ``AnalysisContext`` only (``demo/chat_mock.py``). Language
packs are pseudo-localised. ``clerk_translate`` serves the recorded translation of exactly that
English card (``data/fixtures/<id>/clerk.<lang>.json``, AI_PROMPTS §5.5.4) — so a sample read in
a recorded language shows a real "What this card says" — and the ``⟦tag⟧`` pseudo text only when
no recording of that card in that language exists. Small tasks return fixed, validator-clean
shapes.

Nothing is logged or stored: the page bytes are hashed in memory and dropped (ARCHITECTURE §7);
a page that must be hashed (no ``demo_sample_id``) is handled off the event loop.
Mock is never a silent fallback for a real request — it is only built when ``AI_PROVIDER=mock``.
"""

from __future__ import annotations

import asyncio
import functools
import json
import random
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ValidationError

from proxyhealth_api.ai.provider import Part, StructuredResult, Task, Usage
from proxyhealth_api.contracts.chat import AnalysisContext
from proxyhealth_api.contracts.enums import (
    Confidence,
    DigitSystem,
    Direction,
    DocumentType,
    ModelTier,
    Provider,
    ThinkingLevel,
)
from proxyhealth_api.contracts.model_out import (
    AnalysisModelOut,
    ExplainOut,
    KeyValue,
    LanguagePackModelOut,
    LanguageResolveOut,
    RewriteOut,
    TaggingModelOut,
    TranscriptOut,
    TroubleshootModelOut,
)
from proxyhealth_api.demo.chat_mock import chat_answer
from proxyhealth_api.demo.fixtures import Fixture, FixtureKind, FixtureStore
from proxyhealth_api.demo.mock_outputs import (
    DOCUMENT_TYPE_TAGS,
    generic_screen,
    generic_unreadable,
    marker,
    pseudo_analysis,
    pseudo_troubleshoot,
)
from proxyhealth_api.settings import DATA_DIR, Settings

MOCK_MODEL_ID = "mock"
# BUILD_PLAN §5.8: base language subtags written right-to-left.
RTL_BASES = frozenset({"ar", "prs", "ps", "fa", "ur", "he", "rhg", "ug", "sd", "ckb"})
_CALL1_FIELDS = frozenset({"legibility", "readable_reason", "blocks"})
# Reading tasks that may dHash the first page against the fixtures (no demo_sample_id).
_HASHING_TASKS = frozenset({Task.analyze_single, Task.explain, Task.transcribe, Task.troubleshoot})
_DOC_TYPE_RE = re.compile(r"\b(" + "|".join(sorted(DocumentType, key=len, reverse=True)) + r")\b")


@functools.cache
def language_table() -> dict[str, dict[str, Any]]:
    """``data/languages.yaml`` (WP0 seed; committed data, read once)."""
    raw = yaml.safe_load((DATA_DIR / "languages.yaml").read_text("utf-8")) or {}
    return {str(tag): dict(row) for tag, row in raw.items()}


def direction_for(tag: str) -> Direction:
    row = language_table().get(tag)
    if row and row.get("direction") in ("ltr", "rtl"):
        return Direction(row["direction"])
    return Direction.rtl if tag.split("-")[0].lower() in RTL_BASES else Direction.ltr


def _digit_system(tag: str) -> DigitSystem:
    value = str((language_table().get(tag) or {}).get("digit_system") or "")
    return DigitSystem(value) if value in DigitSystem.__members__ else DigitSystem.western


def _texts(parts: Sequence[Part]) -> list[str]:
    return [p.text for p in parts if p.kind == "text" and p.text]


def _first_media(parts: Sequence[Part]) -> bytes | None:
    for p in parts:
        if p.kind == "bytes" and p.data and (p.mime_type or "").startswith("image/"):
            return p.data
    return None


def _strings_to_translate(parts: Sequence[Part], hints: Mapping[str, str]) -> dict[str, str]:
    raw = hints.get("strings_json")
    candidates = [raw] if raw else _texts(parts)
    for text in candidates:
        try:
            data = json.loads(text or "")
        except ValueError:
            continue
        if isinstance(data, dict) and data and all(isinstance(v, str) for v in data.values()):
            return {str(k): str(v) for k, v in data.items()}
    return {}


def resolve_language(query: str) -> LanguageResolveOut:
    """Case-insensitive lookup on tag, ``name_en`` and ``name_native``; unknown → ``None``."""
    wanted = " ".join(query.casefold().split())
    for tag, row in language_table().items():
        names = {tag.casefold(), str(row.get("name_en", "")).casefold(),
                 str(row.get("name_native", "")).casefold()}  # fmt: skip
        if wanted and wanted in names:
            return LanguageResolveOut(
                language_tag=tag, language_name_en=str(row.get("name_en", tag)),
                language_name_native=row.get("name_native"), script=row.get("script"),
                direction=direction_for(tag), digit_system=_digit_system(tag),
                confidence=Confidence.high,
            )  # fmt: skip
    return LanguageResolveOut(
        language_tag=None, language_name_en=query.strip()[:80], language_name_native=None,
        script=None, direction=Direction.ltr, digit_system=DigitSystem.western,
        confidence=Confidence.low,
    )  # fmt: skip


def _pack(
    tag: str, values: Mapping[str, str], hints: Mapping[str, str], *, confidence: Confidence,
    note: str,
) -> LanguagePackModelOut:
    row = language_table().get(tag) or {}
    return LanguagePackModelOut(
        language_tag=tag,
        language_name_native=hints.get("language_name_native") or row.get("name_native") or tag,
        language_name_en=hints.get("language_name_en") or row.get("name_en") or tag,
        direction=direction_for(tag),
        script=row.get("script"),
        digit_system=_digit_system(tag),
        strings=[KeyValue(key=k, value=v) for k, v in values.items()],
        fallback_keys=[],
        confidence=confidence,
        notes_for_reviewer=note,
    )


def pseudo_pack(
    tag: str, strings: Mapping[str, str], hints: Mapping[str, str]
) -> LanguagePackModelOut:
    """``"⟦<tag>⟧ " + english`` per key (BUILD_PLAN §5.8): visibly not a translation."""
    values = {k: marker(tag) + v for k, v in strings.items()}
    return _pack(tag, values, hints, confidence=Confidence.low,
                 note="Mock pseudo-localization; not a translation.")  # fmt: skip


def recorded_pack(
    tag: str, key: str, translated: str, hints: Mapping[str, str]
) -> LanguagePackModelOut:
    """A recorded sample translation (``clerk.<tag>.json``) served as the one-line answer."""
    return _pack(tag, {key: translated}, hints, confidence=Confidence.high,
                 note="Mock: recorded sample clerk-card translation.")  # fmt: skip


class MockProvider:
    """``AIProvider`` for ``AI_PROVIDER=mock`` backed by the committed fixture set."""

    name: Provider = Provider.mock

    def __init__(self, fixtures: FixtureStore, settings: Settings) -> None:
        self.fixtures = fixtures
        self.settings = settings

    # ---------------------------------------------------------------- fixture resolution

    def resolve_fixture(
        self, parts: Sequence[Part], hints: Mapping[str, str], kind: FixtureKind
    ) -> Fixture | None:
        wanted = hints.get("demo_sample_id")
        if wanted:
            fixture = self.fixtures.get(wanted)
            return fixture if fixture is not None and fixture.kind == kind else None
        media = _first_media(parts)
        if media is None:
            return None
        return self.fixtures.match_dhash(media, self.settings.mock_phash_max_hamming, kind=kind)

    def analysis(self, parts: Sequence[Part], hints: Mapping[str, str]) -> AnalysisModelOut:
        fixture = self.resolve_fixture(parts, hints, "document")
        if fixture is None:
            return generic_unreadable()
        tag = hints.get("target_language") or "en"
        out = fixture.analysis_out(tag)
        if out is not None:
            return out
        english = fixture.analysis_out("en")
        return pseudo_analysis(english, tag) if english is not None else generic_unreadable()

    def troubleshoot(self, parts: Sequence[Part], hints: Mapping[str, str]) -> TroubleshootModelOut:
        fixture = self.resolve_fixture(parts, hints, "screenshot")
        if fixture is None:
            return generic_screen()
        tag = hints.get("target_language") or "en"
        out = fixture.troubleshoot_out(tag)
        if out is not None:
            return out
        english = fixture.troubleshoot_out("en")
        return pseudo_troubleshoot(english, tag) if english is not None else generic_screen()

    def tagging(self, parts: Sequence[Part], hints: Mapping[str, str]) -> TaggingModelOut:
        fixture = self.fixtures.get(hints.get("demo_sample_id") or "")
        english = fixture.analysis_out("en") if fixture else None
        if english is not None:
            return TaggingModelOut(
                tags=list(english.resource_tags), geo_state=english.geo_state,
                geo_county=english.geo_county, geo_city=english.geo_city, geo_zip=english.geo_zip,
                institutions_as_written=list(english.institutions_as_written),
                emergency=bool(english.emergency_terms_found),
            )  # fmt: skip
        doc_type: DocumentType | None = None
        hinted = hints.get("document_type") or ""
        if hinted in DocumentType.__members__:
            doc_type = DocumentType(hinted)
        else:
            for text in _texts(parts):
                m = _DOC_TYPE_RE.search(text)
                if m:
                    doc_type = DocumentType(m.group(1))
                    break
        tags = list(DOCUMENT_TYPE_TAGS.get(doc_type, [])) if doc_type else []
        return TaggingModelOut(
            tags=tags, geo_state=None, geo_county=None, geo_city=None, geo_zip=None,
            institutions_as_written=[], emergency=False,
        )  # fmt: skip

    @staticmethod
    def chat(parts: Sequence[Part], hints: Mapping[str, str]) -> BaseModel:
        texts = _texts(parts)
        ctx: AnalysisContext | None = None
        if texts:
            try:
                ctx = AnalysisContext.model_validate_json(texts[0])
            except ValidationError:
                ctx = None
        question = hints.get("question") or (texts[-1] if texts else "")
        return chat_answer(ctx, question, hints.get("target_language") or "en")

    def clerk_translate(
        self, parts: Sequence[Part], hints: Mapping[str, str]
    ) -> LanguagePackModelOut:
        """One key: the recorded translation of exactly this English card in this language
        (any document fixture's ``clerk.<tag>.json``), else ``"⟦<tag>⟧ " + english``."""
        tag = hints.get("language_tag") or "x-unknown"
        strings = _strings_to_translate(parts, hints)
        if not strings:
            english = hints.get("english") or (_texts(parts) or [""])[-1]
            strings = {hints.get("key") or "clerk_message": english}
        key, english = next(iter(strings.items()))
        recorded = self.fixtures.clerk_translation(tag, english)
        if recorded is not None:
            return recorded_pack(tag, key, recorded, hints)
        return pseudo_pack(tag, {key: english}, hints)

    @staticmethod
    def rewrite(parts: Sequence[Part], hints: Mapping[str, str]) -> RewriteOut:
        text_parts = _texts(parts)
        s = (hints.get("sentence") or (text_parts[-1] if text_parts else "")).strip()
        sentence = f"The paper says {s[0].lower()}{s[1:]}" if s else "The paper says this."
        return RewriteOut(sentence=sentence[:400])

    def build(self, task: Task, parts: Sequence[Part], hints: Mapping[str, str]) -> BaseModel:
        match task:
            case Task.analyze_single:
                return self.analysis(parts, hints)
            case Task.explain:
                data = self.analysis(parts, hints).model_dump(exclude=set(_CALL1_FIELDS))
                return ExplainOut.model_validate(data)
            case Task.transcribe:
                a = self.analysis(parts, hints)
                return TranscriptOut(
                    blocks=a.blocks, detected_language=a.detected_language,
                    legibility=a.legibility, readable_reason=a.readable_reason,
                )  # fmt: skip
            case Task.troubleshoot:
                return self.troubleshoot(parts, hints)
            case Task.chat:
                return self.chat(parts, hints)
            case Task.langpack_chunk:
                tag = hints.get("language_tag") or "x-unknown"
                return pseudo_pack(tag, _strings_to_translate(parts, hints), hints)
            case Task.clerk_translate:
                return self.clerk_translate(parts, hints)
            case Task.resolve_language:
                query = hints.get("language_query") or (_texts(parts) or [""])[-1]
                return resolve_language(query)
            case Task.tag:
                return self.tagging(parts, hints)
            case Task.phrasing_rewrite:
                return self.rewrite(parts, hints)

    async def generate_structured(
        self,
        *,
        task: Task,
        tier: ModelTier,
        parts: Sequence[Part],
        system: str,
        schema: type[BaseModel],
        thinking: ThinkingLevel | None,
        media_resolution: Literal["high", "medium"] | None,
        max_output_tokens: int,
        request_id: str,
        slot_index: int | None = None,
        hints: Mapping[str, str] | None = None,
    ) -> StructuredResult:
        lo, hi = self.settings.mock_latency_min_ms, self.settings.mock_latency_max_ms
        if hi > 0:
            await asyncio.sleep(random.uniform(min(lo, hi), hi) / 1000)  # noqa: S311
        hints = dict(hints or {})
        if task in _HASHING_TASKS and not hints.get("demo_sample_id") and _first_media(parts):
            # The dHash decode + resize of an uploaded page is CPU work: keep it off the loop.
            parsed = await asyncio.to_thread(self.build, task, parts, hints)
        else:
            parsed = self.build(task, parts, hints)
        return StructuredResult(
            parsed=parsed,
            raw_text=parsed.model_dump_json(),
            model_id=MOCK_MODEL_ID,
            usage=Usage(),
            blocked_reason=None,
            finish_reason="STOP",
            incomplete=False,
        )


__all__ = [
    "MOCK_MODEL_ID",
    "RTL_BASES",
    "MockProvider",
    "direction_for",
    "pseudo_pack",
    "recorded_pack",
    "resolve_language",
]
