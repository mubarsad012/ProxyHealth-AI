"""Generate a language pack with the fast model (D-25; API_CONTRACT §3.4; AI_PROMPTS §4.7, §5.5).

The base pack is split into 60-key chunks; each chunk is one ``Task.langpack_chunk`` call
through ``AIService`` (key pool + failover), at most ``CONCURRENCY`` in flight. The model's list
of pairs becomes a map, every string passes ``packs/qa.py`` (failures fall back to English and
are listed in ``fallback_keys``), and ``direction``/``script``/``digit_system`` come from
``data/languages.yaml`` when the tag is known (AI_PROMPTS §7.4), else from the model.

A chunk whose output is invalid or blocked falls back to English for its keys; quota and
upstream errors (429/503) abort the whole pack so the client can retry later. When no chunk at
all produces valid output the pack is ``503 upstream_unavailable`` with ``Retry-After`` (the
errors API_CONTRACT §3.4 declares for this route; the model is retried later). Mock mode returns
a pseudo-localized pack (``⟦tag⟧ English``) through the same path.
"""

import asyncio
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from proxyhealth_api.ai.failover import UPSTREAM_UNAVAILABLE_RETRY_AFTER_S, AIService
from proxyhealth_api.ai.provider import Part, Task
from proxyhealth_api.contracts.enums import (
    Confidence,
    DigitSystem,
    Direction,
    ErrorCode,
    PackSource,
    PackTier,
)
from proxyhealth_api.contracts.langpack import LanguagePack
from proxyhealth_api.contracts.model_out import LanguagePackModelOut
from proxyhealth_api.errors import ApiError
from proxyhealth_api.packs.base import BasePack, LanguageEntry, pack_etag
from proxyhealth_api.packs.prompts import chunk_prompt, strings_block, system_prompt
from proxyhealth_api.packs.qa import QaReport, merge_with_fallback

CHUNK_SIZE = 60
CONCURRENCY = 4
# Chunk failures that fall back to English instead of failing the pack.
_SOFT_ERRORS = frozenset({ErrorCode.model_output_invalid, ErrorCode.content_blocked})
_RANK = {Confidence.low: 0, Confidence.medium: 1, Confidence.high: 2}


@dataclass(frozen=True)
class Target:
    """What to generate: the resolved tag plus the best-known names and script facts."""

    tag: str
    name_en: str
    name_native: str
    entry: LanguageEntry | None = None
    direction: Direction | None = None
    script: str | None = None
    digit_system: DigitSystem | None = None


@dataclass
class GeneratedPack:
    pack: LanguagePack
    qa: QaReport
    failed_chunks: int


def _worst(confidences: Sequence[Confidence]) -> Confidence:
    return min(confidences, key=lambda c: _RANK[c]) if confidences else Confidence.low


def _qa_confidence(model: Confidence, coverage: float) -> Confidence:
    """Model self-assessment capped by QA coverage (API_CONTRACT §3.3 ``confidence``)."""
    if coverage < 0.9:
        return Confidence.low
    if coverage < 0.98 and model is Confidence.high:
        return Confidence.medium
    return model


async def generate_pack(
    target: Target,
    base: BasePack,
    ai: AIService,
    *,
    request_id: str,
    chunk_size: int = CHUNK_SIZE,
    clock: Callable[[], datetime] | None = None,
) -> GeneratedPack:
    """Translate every base key into ``target`` and return a QA'd ``LanguagePack``."""
    entry = target.entry
    chunks = base.chunks(chunk_size)
    system = system_prompt()
    semaphore = asyncio.Semaphore(CONCURRENCY)
    hint_direction = entry.direction.value if entry else (
        target.direction.value if target.direction else "unknown")
    hint_script = (entry.script if entry else target.script) or "unknown"
    hint_digits = entry.digit_system.value if entry else (
        target.digit_system.value if target.digit_system else "unknown")  # fmt: skip

    async def run_chunk(index: int, keys: list[str]) -> LanguagePackModelOut | None:
        chunk_strings = {k: base.strings[k] for k in keys}
        prompt = chunk_prompt(
            chunk_index=index + 1, chunk_count=len(chunks), language_tag=target.tag,
            language_name_en=target.name_en, script_hint=hint_script,
            direction_hint=hint_direction, digit_hint=hint_digits,
            block=strings_block(keys, base.strings, base.contexts),
        )  # fmt: skip
        async with semaphore:
            try:
                outcome = await ai.generate(
                    task=Task.langpack_chunk,
                    parts=[Part.of_text(prompt)],
                    system=system,
                    schema=LanguagePackModelOut,
                    request_id=request_id,
                    hints={
                        "language_tag": target.tag,
                        "language_name_en": target.name_en,
                        "language_name_native": target.name_native,
                        "strings_json": json.dumps(chunk_strings, ensure_ascii=False),
                    },
                )
            except ApiError as exc:
                if exc.code in _SOFT_ERRORS:
                    return None
                raise
        parsed = outcome.result.parsed
        return parsed if isinstance(parsed, LanguagePackModelOut) else None

    outs = await asyncio.gather(*(run_chunk(i, keys) for i, keys in enumerate(chunks)))
    good = [o for o in outs if o is not None]
    if not good:
        raise ApiError(
            ErrorCode.upstream_unavailable,
            503,
            "No language-pack chunk produced valid output; retry later.",
            retry_after=UPSTREAM_UNAVAILABLE_RETRY_AFTER_S,
        )
    translated: dict[str, str] = {}
    model_fallback: set[str] = set()
    for out in good:
        for kv in out.strings:
            if kv.key in base.strings and kv.key not in translated:
                value = kv.value
                if "\n" in base.strings[kv.key]:
                    value = value.replace("\\n", "\n")  # undo the strings-block escaping
                translated[kv.key] = value
        model_fallback.update(k for k in out.fallback_keys if k in base.strings)
    for key in model_fallback:
        translated.pop(key, None)
    strings, fallback_keys, report = merge_with_fallback(base.strings, translated)
    coverage = round(1 - len(fallback_keys) / max(len(strings), 1), 4)
    first = good[0]
    now = (clock or (lambda: datetime.now(UTC)))()
    pack = LanguagePack(
        language_tag=target.tag,
        language_name_native=entry.name_native if entry else (
            target.name_native or first.language_name_native),
        language_name_en=entry.name_en if entry else (target.name_en or first.language_name_en),
        direction=entry.direction if entry else (target.direction or first.direction),
        script=entry.script if entry else (target.script or first.script),
        digit_system=entry.digit_system if entry else (
            target.digit_system or first.digit_system),
        font_hint=entry.font_hint if entry else None,
        tier=entry.tier if entry else PackTier.tier_3,
        source=PackSource.generated,
        pack_version=base.version,
        etag=pack_etag(target.tag, base.version, strings),
        strings=strings,
        fallback_keys=fallback_keys,
        coverage=coverage,
        machine_translated=True,
        reviewed_by=None,
        confidence=_qa_confidence(_worst([o.confidence for o in good]), coverage),
        generated_at=now,
        tts_tag=entry.tts_tag if entry else None,
        tts_fallback_tag=entry.tts_fallback_tag if entry else None,
    )  # fmt: skip
    return GeneratedPack(pack=pack, qa=report, failed_chunks=len(outs) - len(good))
