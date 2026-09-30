"""Generate a language pack with the fast model (D-25; API_CONTRACT §3.4; AI_PROMPTS §7).

The base pack is split into 60-key chunks in file order; each chunk is one ``Task.langpack_chunk``
call through ``AIService`` (key pool + failover), at most ``CONCURRENCY`` (2) in flight because
the fast tier's RPM is shared with chat. The model's list of pairs becomes a map (a key returned
twice keeps its first value) and every string passes ``packs/qa.py``. A chunk whose call was
invalid or blocked, or whose output fails QA on more than 20 % of its keys, is retried once with
only the failing keys; whatever still fails falls back to English and is listed in
``fallback_keys``.

``direction``/``script``/``digit_system`` come from ``data/languages.yaml`` when the tag is known
(authoritative); otherwise the model's values pass the §7.6 sanity table (RTL scripts → ``rtl``,
any other script → ``ltr``, unknown script → ``null``/``ltr``/``western``). ``confidence`` is
``low`` when the model said so or coverage < 0.9, and at most ``medium`` for Tier 3 and ``x-``
tags (§7.7).

Failure mapping (§7.9): a quota or upstream error (429/503) stops the chunks that have not
started. If any chunk already produced output the result is a partial pack (never a 429 after
work was done); otherwise that error is raised. When every chunk was invalid or blocked the pack
is ``503 upstream_unavailable`` with ``Retry-After`` (the errors API_CONTRACT §3.4 declares for
this route; CL-029(b)). Mock mode returns a pseudo-localized pack (``⟦tag⟧ English``) through the
same path; the router never caches it (§7.10).
"""

import asyncio
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
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
from proxyhealth_api.packs.qa import QaReport, check_pack, merge_with_fallback

CHUNK_SIZE = 60
CONCURRENCY = 2  # AI_PROMPTS §7.4: the fast tier's RPM is shared with chat
# A chunk with more than this share of failing keys is retried once (AI_PROMPTS §7.5).
RETRY_FAILURE_RATIO = 0.2
# Chunk failures that fall back to English instead of failing the pack.
_SOFT_ERRORS = frozenset({ErrorCode.model_output_invalid, ErrorCode.content_blocked})
_RANK = {Confidence.low: 0, Confidence.medium: 1, Confidence.high: 2}
# AI_PROMPTS §7.6: these scripts are always right-to-left; every other known script is ltr.
RTL_SCRIPTS = frozenset({"Arab", "Hebr", "Syrc", "Thaa", "Nkoo", "Adlm", "Rohg"})
_SCRIPT_RE = re.compile(r"^[A-Z][a-z]{3}$")  # ISO 15924


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


@dataclass
class _ChunkRun:
    """One chunk's model outputs, its QA-accepted strings, and the hard error that stopped it."""

    outs: list[LanguagePackModelOut] = field(default_factory=list)
    accepted: dict[str, str] = field(default_factory=dict)
    error: ApiError | None = None


def script_facts(
    script: str | None, digit_system: DigitSystem | None
) -> tuple[str | None, Direction, DigitSystem]:
    """AI_PROMPTS §7.6 sanity table for tags that are not in ``languages.yaml``."""
    code = (script or "").strip()
    if not _SCRIPT_RE.match(code):
        return None, Direction.ltr, DigitSystem.western
    direction = Direction.rtl if code in RTL_SCRIPTS else Direction.ltr
    return code, direction, digit_system or DigitSystem.western


def _worst(confidences: Sequence[Confidence]) -> Confidence:
    return min(confidences, key=lambda c: _RANK[c]) if confidences else Confidence.low


def _qa_confidence(model: Confidence, coverage: float, *, capped: bool = False) -> Confidence:
    """Model self-assessment capped by QA coverage and tier (AI_PROMPTS §7.7).

    ``capped`` is true for Tier 3 and ``x-`` tags: their packs are never better than ``medium``.
    """
    if model is Confidence.low or coverage < 0.9:
        return Confidence.low
    if model is Confidence.high and (capped or coverage < 0.98):
        return Confidence.medium
    return model


def _translations(out: LanguagePackModelOut, keys: Sequence[str], base: BasePack) -> dict[str, str]:
    """One output as ``{key: value}`` over ``keys``: first value wins, model fallbacks dropped."""
    wanted = set(keys)
    dropped = set(out.fallback_keys)
    result: dict[str, str] = {}
    for kv in out.strings:
        if kv.key in wanted and kv.key not in dropped and kv.key not in result:
            value = kv.value
            if "\n" in base.strings[kv.key]:
                value = value.replace("\\n", "\n")  # undo the strings-block escaping
            result[kv.key] = value
    return result


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
    stop = asyncio.Event()  # set by the first quota/upstream error: start no new calls
    hint_direction = entry.direction.value if entry else (
        target.direction.value if target.direction else "unknown")
    hint_script = (entry.script if entry else target.script) or "unknown"
    hint_digits = entry.digit_system.value if entry else (
        target.digit_system.value if target.digit_system else "unknown")  # fmt: skip

    async def call(index: int, keys: list[str]) -> LanguagePackModelOut | None:
        """One model call; ``None`` for invalid/blocked output; re-raises 429/503 errors."""
        chunk_strings = {k: base.strings[k] for k in keys}
        prompt = chunk_prompt(
            chunk_index=index + 1, chunk_count=len(chunks), language_tag=target.tag,
            language_name_en=target.name_en, script_hint=hint_script,
            direction_hint=hint_direction, digit_hint=hint_digits,
            block=strings_block(keys, base.strings, base.contexts),
        )  # fmt: skip
        async with semaphore:
            if stop.is_set():
                return None
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
                stop.set()
                raise
        parsed = outcome.result.parsed
        return parsed if isinstance(parsed, LanguagePackModelOut) else None

    def qa(keys: list[str], out: LanguagePackModelOut) -> tuple[dict[str, str], list[str]]:
        english = {k: base.strings[k] for k in keys}
        report = check_pack(english, _translations(out, keys, base), language_tag=target.tag)
        return report.accepted, report.fallback_keys

    async def run_chunk(index: int, keys: list[str]) -> _ChunkRun:
        run = _ChunkRun()
        failing = keys
        try:
            first = await call(index, keys)
            if first is not None:
                run.outs.append(first)
                run.accepted, failing = qa(keys, first)
            if failing and (first is None or len(failing) > RETRY_FAILURE_RATIO * len(keys)):
                second = await call(index, failing)  # one retry, only the failing keys
                if second is not None:
                    run.outs.append(second)
                    run.accepted.update(qa(failing, second)[0])
        except ApiError as exc:
            run.error = exc
        return run

    runs = await asyncio.gather(*(run_chunk(i, keys) for i, keys in enumerate(chunks)))
    outs = [out for run in runs for out in run.outs]
    if not outs:
        hard = next((run.error for run in runs if run.error is not None), None)
        if hard is not None:
            raise hard  # quota gone or upstream down before any work was done
        raise ApiError(
            ErrorCode.upstream_unavailable,
            503,
            "No language-pack chunk produced valid output; retry later.",
            retry_after=UPSTREAM_UNAVAILABLE_RETRY_AFTER_S,
        )
    translated = {key: value for run in runs for key, value in run.accepted.items()}
    strings, fallback_keys, report = merge_with_fallback(
        base.strings, translated, language_tag=target.tag
    )
    coverage = round(1 - len(fallback_keys) / max(len(strings), 1), 4)
    first = outs[0]
    if entry is not None:
        script, direction, digits = entry.script, entry.direction, entry.digit_system
        name_native, name_en, tier = entry.name_native, entry.name_en, entry.tier
    else:
        script, direction, digits = script_facts(
            target.script or first.script, target.digit_system or first.digit_system
        )
        name_native = target.name_native or first.language_name_native
        name_en = target.name_en or first.language_name_en
        tier = PackTier.tier_3
    capped = tier is PackTier.tier_3 or target.tag.startswith("x-")
    now = (clock or (lambda: datetime.now(UTC)))()
    pack = LanguagePack(
        language_tag=target.tag,
        language_name_native=name_native,
        language_name_en=name_en,
        direction=direction,
        script=script,
        digit_system=digits,
        font_hint=entry.font_hint if entry else None,
        tier=tier,
        source=PackSource.generated,
        pack_version=base.version,
        etag=pack_etag(target.tag, base.version, strings),
        strings=strings,
        fallback_keys=fallback_keys,
        coverage=coverage,
        machine_translated=True,
        reviewed_by=None,
        confidence=_qa_confidence(_worst([o.confidence for o in outs]), coverage, capped=capped),
        generated_at=now,
        tts_tag=entry.tts_tag if entry else None,
        tts_fallback_tag=entry.tts_fallback_tag if entry else None,
    )
    failed_chunks = sum(1 for run in runs if not run.outs)
    return GeneratedPack(pack=pack, qa=report, failed_chunks=failed_chunks)
