"""Task → model-tier routing (BUILD_PLAN §4.1; AI_PROMPTS §3; D-04). WP0 table, WP1 adds tests."""

from dataclasses import dataclass
from typing import Literal

from proxyhealth_api.ai.provider import Task
from proxyhealth_api.contracts.enums import ModelTier, ThinkingLevel
from proxyhealth_api.logging_ import log_event
from proxyhealth_api.settings import Settings

MediaResolution = Literal["high", "medium"]


@dataclass(frozen=True)
class RouteConfig:
    tier: ModelTier
    model_id: str
    thinking: ThinkingLevel | None
    media_resolution: MediaResolution | None
    max_output_tokens: int


# AI_PROMPTS §3 — (tier, thinking, has_media, max_output_tokens). ``thinking`` for the two
# page-count-dependent tasks is resolved in ``route()``.
_TABLE: dict[Task, tuple[ModelTier, ThinkingLevel, bool, int]] = {
    Task.analyze_single: (ModelTier.pro, ThinkingLevel.high, True, 16384),
    Task.transcribe: (ModelTier.pro, ThinkingLevel.medium, True, 8192),
    Task.explain: (ModelTier.pro, ThinkingLevel.high, False, 16384),
    Task.troubleshoot: (ModelTier.pro, ThinkingLevel.medium, True, 4096),
    Task.chat: (ModelTier.fast, ThinkingLevel.low, False, 2048),
    Task.langpack_chunk: (ModelTier.fast, ThinkingLevel.minimal, False, 4096),
    Task.clerk_translate: (ModelTier.fast, ThinkingLevel.minimal, False, 512),
    Task.tag: (ModelTier.fast, ThinkingLevel.minimal, False, 1024),
    Task.resolve_language: (ModelTier.fast, ThinkingLevel.minimal, False, 256),
    Task.phrasing_rewrite: (ModelTier.fast, ThinkingLevel.minimal, False, 256),
}

_PAGE_DEPENDENT = frozenset({Task.analyze_single, Task.explain})


def route(
    task: Task,
    *,
    pages: int = 1,
    is_pdf: bool = False,
    degraded: bool = False,
    settings: Settings,
) -> RouteConfig:
    tier, thinking, has_media, max_tokens = _TABLE[task]
    if task in _PAGE_DEPENDENT and pages > 8:
        thinking = ThinkingLevel.medium
    model_id = settings.model_pro if tier is ModelTier.pro else settings.model_fast
    if degraded and tier is ModelTier.pro:
        tier = ModelTier.fast
        model_id = settings.model_fast
        thinking = settings.model_pro_degraded_thinking
    if model_id.startswith("gemini-3.8") and thinking is ThinkingLevel.minimal:
        thinking = ThinkingLevel.low
        log_event(route="routing.thinking_downgraded", model=model_id, tier=tier.value)
    media: MediaResolution | None = None
    if has_media:
        media = "medium" if is_pdf else "high"
    return RouteConfig(
        tier=tier,
        model_id=model_id,
        thinking=thinking,
        media_resolution=media,
        max_output_tokens=max_tokens,
    )
