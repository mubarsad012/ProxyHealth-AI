"""Hour-one ``MockProvider`` (BUILD_PLAN §5.0; D-29). WP7 replaces it with the fixture set.

Returns the inline fixture's ``AnalysisModelOut`` for any analysis input, fixed troubleshoot and
chat outputs, pseudo-localized packs (``⟦tag⟧ `` prefix) and neutral small-task outputs.
"""

import asyncio
import json
import random
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel

from proxyhealth_api.ai.provider import Part, StructuredResult, Task, Usage
from proxyhealth_api.contracts.enums import (
    Confidence,
    DigitSystem,
    Direction,
    ModelTier,
    Provider,
    ReferTo,
    RefusalKind,
    ThinkingLevel,
)
from proxyhealth_api.contracts.model_out import (
    AnalysisModelOut,
    ChatModelOut,
    ExplainOut,
    KeyValue,
    LanguagePackModelOut,
    LanguageResolveOut,
    RewriteOut,
    TaggingModelOut,
    TranscriptOut,
    TroubleshootModelOut,
)
from proxyhealth_api.contracts.troubleshoot import TroubleshootStep
from proxyhealth_api.demo.fixtures import Fixture, FixtureStore
from proxyhealth_api.settings import Settings

_RTL = frozenset({"ar", "prs", "ps", "fa", "ur", "rhg", "he", "yi"})
_CALL1_FIELDS = frozenset({"legibility", "readable_reason", "blocks"})


def fixed_troubleshoot_out() -> TroubleshootModelOut:
    return TroubleshootModelOut(
        screen_summary="The screen shows an upload error: the file you chose is too large.",
        screen_text=["File exceeds the maximum size of 5 MB", "Back", "Choose File", "Upload"],
        error_text_quoted="File exceeds the maximum size of 5 MB",
        error_meaning="The photo or file you picked is bigger than this website allows.",
        steps=[
            TroubleshootStep(
                order=1, text="Tap the button that says Back.", ui_target_as_written="Back"
            ),
            TroubleshootStep(
                order=2,
                text="Take a new photo or pick a smaller file, then tap Choose File.",
                ui_target_as_written="Choose File",
            ),
            TroubleshootStep(order=3, text="Tap Upload again.", ui_target_as_written="Upload"),
        ],
        cautions=[],
        asks_for_credentials_or_payment=False,
        is_likely_scam=False,
        scam_signals=[],
        needs_human_help=False,
        red_flags=[],
        resource_tags=["benefits_navigation"],
        confidence=Confidence.medium,
    )


def fixed_chat_out() -> ChatModelOut:
    return ChatModelOut(
        answer="The paper does not say. You can ask the office that sent it.",
        grounded_span_ids=[],
        not_in_document=True,
        refusal_kind=RefusalKind.none,
        refer_to_professional=ReferTo.none,
        distress_acknowledged=False,
        suggested_questions=["What is the deadline?", "Who sent this letter?"],
        resource_tags=[],
    )


def _strings_to_translate(parts: Sequence[Part], hints: Mapping[str, str]) -> dict[str, str]:
    raw = hints.get("strings_json")
    candidates = [raw] if raw else [p.text for p in parts if p.kind == "text" and p.text]
    for text in candidates:
        try:
            data = json.loads(text or "")
        except ValueError:
            continue
        if isinstance(data, dict) and all(isinstance(v, str) for v in data.values()):
            return {str(k): str(v) for k, v in data.items()}
    return {}


class MockProvider:
    name: Provider = Provider.mock

    def __init__(self, fixtures: FixtureStore, settings: Settings) -> None:
        self.fixtures = fixtures
        self.settings = settings

    def _fixture(self, hints: Mapping[str, str]) -> Fixture:
        wanted = hints.get("demo_sample_id")
        return (self.fixtures.get(wanted) if wanted else None) or self.fixtures.default()

    def _analysis(self, hints: Mapping[str, str]) -> AnalysisModelOut:
        out = self._fixture(hints).out("en")
        if isinstance(out, AnalysisModelOut):
            return out
        default = self.fixtures.default().out("en")
        assert isinstance(default, AnalysisModelOut)
        return default

    def _build(self, task: Task, parts: Sequence[Part], hints: Mapping[str, str]) -> BaseModel:
        match task:
            case Task.analyze_single:
                return self._analysis(hints)
            case Task.explain:
                data = self._analysis(hints).model_dump(exclude=set(_CALL1_FIELDS))
                return ExplainOut.model_validate(data)
            case Task.transcribe:
                a = self._analysis(hints)
                return TranscriptOut(
                    blocks=a.blocks, detected_language=a.detected_language,
                    legibility=a.legibility, readable_reason=a.readable_reason,
                )  # fmt: skip
            case Task.troubleshoot:
                out = self._fixture(hints).out("en")
                return out if isinstance(out, TroubleshootModelOut) else fixed_troubleshoot_out()
            case Task.chat:
                return fixed_chat_out()
            case Task.langpack_chunk | Task.clerk_translate:
                tag = hints.get("language_tag") or "x-unknown"
                base = tag.split("-")[0].lower()
                return LanguagePackModelOut(
                    language_tag=tag,
                    language_name_native=hints.get("language_name_native") or tag,
                    language_name_en=hints.get("language_name_en") or tag,
                    direction=Direction.rtl if base in _RTL else Direction.ltr,
                    script=None,
                    digit_system=DigitSystem.western,
                    strings=[
                        KeyValue(key=k, value=f"⟦{tag}⟧ {v}")
                        for k, v in _strings_to_translate(parts, hints).items()
                    ],
                    fallback_keys=[],
                    confidence=Confidence.low,
                    notes_for_reviewer="Mock pseudo-localization; not a translation.",
                )
            case Task.resolve_language:
                return LanguageResolveOut(
                    language_tag=None, language_name_en=hints.get("language_query", ""),
                    language_name_native=None, script=None, direction=Direction.ltr,
                    digit_system=DigitSystem.western, confidence=Confidence.low,
                )  # fmt: skip
            case Task.tag:
                return TaggingModelOut(
                    tags=[], geo_state=None, geo_county=None, geo_city=None, geo_zip=None,
                    institutions_as_written=[], emergency=False,
                )  # fmt: skip
            case Task.phrasing_rewrite:
                text_parts = [p.text for p in parts if p.kind == "text" and p.text]
                s = (hints.get("sentence") or (text_parts[-1] if text_parts else "")).strip()
                sentence = f"The paper says {s[0].lower()}{s[1:]}" if s else "The paper says this."
                return RewriteOut(sentence=sentence[:400])

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
        parsed = self._build(task, parts, hints or {})
        return StructuredResult(
            parsed=parsed,
            raw_text=parsed.model_dump_json(),
            model_id="mock",
            usage=Usage(),
            blocked_reason=None,
            finish_reason="STOP",
            incomplete=False,
        )
