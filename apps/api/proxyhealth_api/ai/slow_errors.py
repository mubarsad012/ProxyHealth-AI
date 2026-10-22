"""The honest "too slow" / "busy" errors of ``AI_PROVIDER=openai_compat`` (free-ai-providers §4.7;
LOCAL_AI.md §5, §9).

A local model at ``temperature: 0`` that runs out of time on a paper runs out again on a retry, so
these errors carry their own pack keys instead of the Gemini meaning of ``503`` ("a transient
upstream hiccup, try again in a minute"). The code and status stay ``503 upstream_unavailable``
(API_CONTRACT §0.1); an app whose pack lacks a key falls back to ``err.upstream_unavailable``.
Messages are fixed server text: never an upstream body, a prompt or model output.

Its own module because both ``openai_compat`` and ``failover`` raise them (``failover`` cannot
import the provider module: that would be an import cycle through ``analysis``).
"""

from proxyhealth_api.ai.provider import Task
from proxyhealth_api.contracts.enums import ErrorCode
from proxyhealth_api.errors import ApiError

AI_TOO_SLOW_KEY = "err.ai_too_slow"
AI_BUSY_KEY = "err.ai_busy"
AI_BUSY_RETRY_AFTER_S = 60
# The tasks that read a paper; the others keep the generic err.upstream_unavailable copy.
PAPER_TASKS = frozenset({Task.analyze_single, Task.transcribe, Task.explain})


def too_slow_error(task: Task, budget_s: float, *, reason: str) -> ApiError:
    """The call's budget (``reason`` ``ai_timeout``) or the request's deadline (``deadline``) ran
    out. No short retry hint is set (the envelope still carries the §0.1 default
    ``Retry-After``)."""
    return ApiError(
        ErrorCode.upstream_unavailable, 503,
        f"The AI server did not finish within {int(budget_s)} s.",
        user_message_key=AI_TOO_SLOW_KEY if task in PAPER_TASKS else None,
        details={"reason": reason, "timeout_s": int(budget_s)},
    )  # fmt: skip


def busy_error(waited_s: float) -> ApiError:
    """The call's budget went on waiting for the provider's semaphore (another request held the
    one loopback slot)."""
    return ApiError(
        ErrorCode.upstream_unavailable, 503, "The AI server is busy with another request.",
        user_message_key=AI_BUSY_KEY, retry_after=AI_BUSY_RETRY_AFTER_S,
        details={"reason": "ai_busy", "waited_s": int(waited_s)},
    )  # fmt: skip
