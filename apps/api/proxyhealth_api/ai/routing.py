"""Task → model-tier routing (BUILD_PLAN §4.1; AI_PROMPTS §3; D-04).

``route()`` is pure: it reads model ids from ``Settings`` only (never a literal model id), applies
the page-count downgrade (D-06), the degraded swap (D-07) and the ``minimal`` → ``low`` guard for
``gemini-3.8*`` models. The response schema and prompt name are looked up by the pipeline from
the ``Task``, not returned here.
"""

from dataclasses import dataclass
from typing import Literal

from proxyhealth_api.ai.provider import Task
from proxyhealth_api.contracts.enums import ModelTier, ThinkingLevel
from proxyhealth_api.logging_ import log_event
from proxyhealth_api.settings import Settings

MediaResolution = Literal["high", "medium"]

# Model families that refuse ``thinking_level="minimal"`` (gemini.md warnings; D-04).
NO_MINIMAL_PREFIX = "gemini-3.8"

# Pages above this drop ``high`` → ``medium`` for the page-dependent tasks (D-06).
HIGH_THINKING_MAX_PAGES = 8


@dataclass(frozen=True)
class RouteConfig:
    tier: ModelTier
    model_id: str
    thinking: ThinkingLevel | None
    media_resolution: MediaResolution | None
    max_output_tokens: int


# AI_PROMPTS §3 — (tier, thinking, has_media, max_output_tokens). ``thinking`` for the two
# page-count-dependent tasks is resolved in ``route()``.
TABLE: dict[Task, tuple[ModelTier, ThinkingLevel, bool, int]] = {
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

PAGE_DEPENDENT: frozenset[Task] = frozenset({Task.analyze_single, Task.explain})

# The only tasks that may run degraded on ``MODEL_FAST`` (D-07: fast tasks never escalate).
DEGRADABLE_TASKS: frozenset[Task] = frozenset(
    {Task.analyze_single, Task.transcribe, Task.explain, Task.troubleshoot}
)

PRO_TASKS: frozenset[Task] = frozenset(t for t, row in TABLE.items() if row[0] is ModelTier.pro)
FAST_TASKS: frozenset[Task] = frozenset(t for t, row in TABLE.items() if row[0] is ModelTier.fast)


def guard_thinking(model_id: str, thinking: ThinkingLevel | None) -> ThinkingLevel | None:
    """``minimal`` is never sent to a ``gemini-3.8*`` model → ``low`` with a content-free log."""
    if thinking is ThinkingLevel.minimal and model_id.startswith(NO_MINIMAL_PREFIX):
        log_event(route="routing.thinking_downgraded", model=model_id)
        return ThinkingLevel.low
    return thinking


def route(
    task: Task,
    *,
    pages: int = 1,
    is_pdf: bool = False,
    degraded: bool = False,
    settings: Settings,
) -> RouteConfig:
    tier, thinking_row, has_media, max_tokens = TABLE[task]
    thinking: ThinkingLevel | None = thinking_row
    if task in PAGE_DEPENDENT and pages > HIGH_THINKING_MAX_PAGES:
        thinking = ThinkingLevel.medium
    # Model ids of the active provider (free-ai-providers §4.2 rule 6), so logs name the real one.
    model_id = settings.active_model_pro if tier is ModelTier.pro else settings.active_model_fast
    if degraded and tier is ModelTier.pro:
        # D-07 degraded path: the fast model with MODEL_PRO_DEGRADED_THINKING; tier reports fast
        # so ``model_meta.tier="fast"`` (AI_PROMPTS §8.5) and the provider picks MODEL_FAST.
        tier = ModelTier.fast
        model_id = settings.active_model_fast
        thinking = settings.model_pro_degraded_thinking
    if settings.ai_provider == "openai_compat" and settings.openai_compat_reasoning != "mapped":
        # §4.5: thinking is switched off (or left to the endpoint), so ``model_meta`` says none.
        thinking = None
    guarded = guard_thinking(model_id, thinking)
    media: MediaResolution | None = None
    if has_media:
        media = "medium" if is_pdf else "high"
    return RouteConfig(
        tier=tier,
        model_id=model_id,
        thinking=guarded,
        media_resolution=media,
        max_output_tokens=max_tokens,
    )
