"""``ai/routing.route`` — every row of AI_PROMPTS §3, the page downgrade (D-06), the degraded
swap (D-07) and the ``minimal`` → ``low`` guard on ``gemini-3.8*`` (D-04). WP1 lane 1B."""

import pytest

from proxyhealth_api.ai.provider import Task
from proxyhealth_api.ai.routing import (
    DEGRADABLE_TASKS,
    FAST_TASKS,
    PRO_TASKS,
    TABLE,
    RouteConfig,
    guard_thinking,
    route,
)
from proxyhealth_api.contracts.enums import ModelTier, ThinkingLevel
from proxyhealth_api.settings import Settings

PRO = "gemini-3.8-flash"
FAST = "gemini-3.5-flash-lite"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"ai_provider": "mock", "model_pro": PRO, "model_fast": FAST}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


# AI_PROMPTS §3 rows: task → (tier, model, thinking, media for image input, max_output_tokens).
ROWS: list[tuple[Task, ModelTier, str, ThinkingLevel, str | None, int]] = [
    (Task.analyze_single, ModelTier.pro, PRO, ThinkingLevel.high, "high", 16384),
    (Task.transcribe, ModelTier.pro, PRO, ThinkingLevel.medium, "high", 8192),
    (Task.explain, ModelTier.pro, PRO, ThinkingLevel.high, None, 16384),
    (Task.troubleshoot, ModelTier.pro, PRO, ThinkingLevel.medium, "high", 4096),
    (Task.chat, ModelTier.fast, FAST, ThinkingLevel.low, None, 2048),
    (Task.langpack_chunk, ModelTier.fast, FAST, ThinkingLevel.minimal, None, 4096),
    (Task.clerk_translate, ModelTier.fast, FAST, ThinkingLevel.minimal, None, 512),
    (Task.tag, ModelTier.fast, FAST, ThinkingLevel.minimal, None, 1024),
    (Task.resolve_language, ModelTier.fast, FAST, ThinkingLevel.minimal, None, 256),
    (Task.phrasing_rewrite, ModelTier.fast, FAST, ThinkingLevel.minimal, None, 256),
]


@pytest.mark.parametrize(("task", "tier", "model", "thinking", "media", "max_tokens"), ROWS)
def test_table_row(
    task: Task,
    tier: ModelTier,
    model: str,
    thinking: ThinkingLevel,
    media: str | None,
    max_tokens: int,
) -> None:
    cfg = route(task, pages=1, is_pdf=False, settings=_settings())
    assert cfg == RouteConfig(
        tier=tier,
        model_id=model,
        thinking=thinking,
        media_resolution=media,  # type: ignore[arg-type]
        max_output_tokens=max_tokens,
    )


def test_every_task_has_a_row() -> None:
    assert set(TABLE) == set(Task)
    assert PRO_TASKS | FAST_TASKS == set(Task)
    assert PRO_TASKS.isdisjoint(FAST_TASKS)
    assert DEGRADABLE_TASKS <= PRO_TASKS


@pytest.mark.parametrize("task", [Task.analyze_single, Task.explain])
def test_pages_above_eight_downgrade_high_to_medium(task: Task) -> None:
    s = _settings()
    assert route(task, pages=8, settings=s).thinking is ThinkingLevel.high
    assert route(task, pages=9, settings=s).thinking is ThinkingLevel.medium
    assert route(task, pages=12, settings=s).thinking is ThinkingLevel.medium


@pytest.mark.parametrize("task", [Task.transcribe, Task.troubleshoot, Task.chat])
def test_pages_do_not_change_other_tasks(task: Task) -> None:
    s = _settings()
    assert route(task, pages=1, settings=s).thinking is route(task, pages=12, settings=s).thinking


@pytest.mark.parametrize("task", [Task.analyze_single, Task.transcribe])
def test_media_resolution_pdf_vs_image(task: Task) -> None:
    s = _settings()
    assert route(task, is_pdf=True, settings=s).media_resolution == "medium"
    assert route(task, is_pdf=False, settings=s).media_resolution == "high"


def test_text_only_tasks_never_set_media_resolution() -> None:
    s = _settings()
    for task in (Task.explain, Task.chat, Task.langpack_chunk, Task.tag, Task.phrasing_rewrite):
        assert route(task, is_pdf=True, settings=s).media_resolution is None


@pytest.mark.parametrize("task", sorted(DEGRADABLE_TASKS))
def test_degraded_swaps_to_fast_model_with_degraded_thinking(task: Task) -> None:
    s = _settings(model_pro_degraded_thinking="medium")
    base = route(task, pages=2, is_pdf=True, settings=s)
    cfg = route(task, pages=2, is_pdf=True, degraded=True, settings=s)
    assert cfg.tier is ModelTier.fast  # model_meta.tier="fast" (AI_PROMPTS §8.5)
    assert cfg.model_id == FAST
    assert cfg.thinking is ThinkingLevel.medium
    assert cfg.media_resolution == base.media_resolution
    assert cfg.max_output_tokens == base.max_output_tokens


def test_degraded_thinking_is_configurable() -> None:
    s = _settings(model_pro_degraded_thinking="low")
    assert route(Task.analyze_single, degraded=True, settings=s).thinking is ThinkingLevel.low


@pytest.mark.parametrize("task", sorted(FAST_TASKS))
def test_degraded_flag_is_a_no_op_for_fast_tasks(task: Task) -> None:
    s = _settings()
    assert route(task, degraded=True, settings=s) == route(task, degraded=False, settings=s)


def test_minimal_downgraded_to_low_on_gemini_38_fast_model() -> None:
    # Misconfiguration guard: MODEL_FAST pointed at a 3.8 model must never receive ``minimal``.
    s = _settings(model_fast="gemini-3.8-flash")
    for task in (Task.langpack_chunk, Task.tag, Task.clerk_translate, Task.resolve_language):
        assert route(task, settings=s).thinking is ThinkingLevel.low
    assert route(Task.chat, settings=s).thinking is ThinkingLevel.low  # unchanged: already low


def test_minimal_kept_on_flash_lite() -> None:
    assert route(Task.tag, settings=_settings()).thinking is ThinkingLevel.minimal


def test_guard_thinking_only_touches_minimal_on_38() -> None:
    assert guard_thinking("gemini-3.8-flash", ThinkingLevel.minimal) is ThinkingLevel.low
    assert guard_thinking("gemini-3.8-flash-001", ThinkingLevel.minimal) is ThinkingLevel.low
    assert guard_thinking("gemini-3.8-flash", ThinkingLevel.high) is ThinkingLevel.high
    assert guard_thinking("gemini-3.5-flash-lite", ThinkingLevel.minimal) is ThinkingLevel.minimal
    assert guard_thinking("gemini-3.8-flash", None) is None


def test_model_ids_come_only_from_settings() -> None:
    s = _settings(model_pro="gemini-3.7-flash", model_fast="gemini-3.1-flash-lite")
    assert route(Task.analyze_single, settings=s).model_id == "gemini-3.7-flash"
    assert route(Task.chat, settings=s).model_id == "gemini-3.1-flash-lite"
    assert route(Task.troubleshoot, degraded=True, settings=s).model_id == "gemini-3.1-flash-lite"


def test_route_is_pure_and_frozen() -> None:
    cfg = route(Task.chat, settings=_settings())
    with pytest.raises(AttributeError):
        cfg.tier = ModelTier.pro  # type: ignore[misc]
