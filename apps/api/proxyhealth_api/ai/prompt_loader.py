"""Prompt loader (AI_PROMPTS §2; WP2). The only way pipelines obtain prompt text.

Prompt files live in ``ai/prompts/`` (system prompts, ``preamble.md``) and ``ai/prompts/user/``
(user templates); their text is copied verbatim from ``docs/AI_PROMPTS.md`` §5 and checked by
``tests/unit/test_prompts_match_doc.py``. Files contain no ``{`` / ``}`` except the §2
placeholders (``{name}`` with ``[a-z_]+``).

``render`` substitutes every placeholder in **one pass** over the template, so a value that itself
contains braces (the language-pack ``{strings_block}`` with ``{minutes}``, a transcript line, a
user's question) is inserted as data and never re-scanned — ``str.format_map`` is never used.
Every placeholder of a template must be supplied (``KeyError`` otherwise); extra variables are
ignored, so one ``vars`` mapping serves both ``system()`` and ``user()`` of a task.

Text typed by the reader (document hint, goal, question, calendar notes, language name) goes
through ``untrusted()``, which wraps it in fixed marker strings the prompts describe as data.
Nothing here logs or stores prompt text.
"""

import functools
import re
import unicodedata
from collections.abc import Mapping
from pathlib import Path

from proxyhealth_api.ai.provider import Task
from proxyhealth_api.contracts.enums import (
    DocumentCategory,
    DocumentType,
    PlanStepKind,
    RedFlagKind,
    ResourceTag,
)

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
VERSION_FILE = PROMPTS_DIR / "VERSION"
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
USER_TEXT_BEGIN = "<<<USER_TEXT_BEGIN>>>"
USER_TEXT_END = "<<<USER_TEXT_END>>>"
NONE_TEXT = "(none)"
PREAMBLE = "preamble.md"

# AI_PROMPTS §3 "System prompt" column (the pipeline's ``TASK_PROMPT`` mirrors this map).
SYSTEM_PROMPT: Mapping[Task, str] = {
    Task.analyze_single: "analyze.md",
    Task.transcribe: "transcribe.md",
    Task.explain: "explain.md",
    Task.troubleshoot: "troubleshoot.md",
    Task.chat: "chat.md",
    Task.langpack_chunk: "langpack.md",
    Task.clerk_translate: "langpack.md",
    Task.resolve_language: "langpack.md",
    Task.tag: "tag.md",
    Task.phrasing_rewrite: "phrasing_rewrite.md",
}
# AI_PROMPTS §1 / §5: one user template per task (clerk_translate reuses the chunk template).
USER_PROMPT: Mapping[Task, str] = {
    Task.analyze_single: "user/analyze_user.md",
    Task.transcribe: "user/transcribe_user.md",
    Task.explain: "user/explain_user.md",
    Task.troubleshoot: "user/troubleshoot_user.md",
    Task.chat: "user/chat_user.md",
    Task.langpack_chunk: "user/langpack_user.md",
    Task.clerk_translate: "user/langpack_user.md",
    Task.resolve_language: "user/resolve_language_user.md",
    Task.tag: "user/tag_user.md",
    Task.phrasing_rewrite: "user/phrasing_rewrite_user.md",
}

# AI_PROMPTS §5.1.3 — the 13 scam signal keys, in this order (``scam_reasons`` chips).
SCAM_SIGNAL_KEYS: tuple[str, ...] = (
    "scam.gift_card",
    "scam.wire_transfer",
    "scam.payment_app",
    "scam.crypto",
    "scam.arrest_threat",
    "scam.deportation_threat",
    "scam.guaranteed",
    "scam.notario",
    "scam.non_gov_domain",
    "scam.expedite_fee",
    "scam.fee_for_free_form",
    "scam.urgency_pressure",
    "scam.impersonation",
)
# API_CONTRACT §3.5 ``Demand.role``.
DEMAND_ROLES: tuple[str, ...] = (
    "hearing_date",
    "response_due",
    "payment_due",
    "appointment",
    "notice_date",
    "decision_date",
    "move_date",
    "expiry",
    "other",
)
# AI_PROMPTS §2 ``{red_flag_kinds}``: code adds these kinds itself, the model never emits them.
CODE_ONLY_RED_FLAG_KINDS = frozenset(
    {
        RedFlagKind.injection_suspected,
        RedFlagKind.jury_citizenship_warning,
        RedFlagKind.ead_receipt_not_work_authorization,
        RedFlagKind.not_a_court_order,
        RedFlagKind.court_date_is_the_deadline,
        RedFlagKind.no_fee_waiver,
        RedFlagKind.address_change_multi_agency,
    }
)
MODEL_RED_FLAG_KINDS: tuple[RedFlagKind, ...] = tuple(
    k for k in RedFlagKind if k not in CODE_ONLY_RED_FLAG_KINDS
)

_KEEP_CONTROLS = frozenset("\n\t")


class PromptError(Exception):
    """A prompt file is missing or malformed (a deployment bug, never user-facing)."""


@functools.cache
def load(name: str) -> str:
    """Raw text of ``ai/prompts/<name>`` (cached; ``PromptError`` when the file is missing)."""
    path = (PROMPTS_DIR / name).resolve()
    if PROMPTS_DIR not in path.parents or path.suffix != ".md":
        raise PromptError(f"not a prompt file: {name}")
    try:
        return path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except OSError as exc:
        raise PromptError(f"prompt file missing: {name}") from exc


def placeholders(name: str) -> list[str]:
    """Placeholder names of one prompt file, in order of first appearance."""
    return list(dict.fromkeys(PLACEHOLDER.findall(load(name))))


def render(name: str, **vars: str) -> str:
    """Fill every ``{placeholder}`` of ``name`` in one pass; missing variable → ``KeyError``."""
    text = load(name)
    missing = [p for p in placeholders(name) if p not in vars]
    if missing:
        raise KeyError(f"{name}: missing prompt variables {missing}")
    return PLACEHOLDER.sub(lambda m: str(vars[m.group(1)]), text).rstrip("\n")


def system(task: Task, **vars: str) -> str:
    """``preamble.md`` + one blank line + the task's system prompt, rendered."""
    return render(PREAMBLE, **vars) + "\n\n" + render(SYSTEM_PROMPT[task], **vars)


def user(task: Task, **vars: str) -> str:
    """The task's user template (``user/<task>_user.md``), rendered."""
    return render(USER_PROMPT[task], **vars)


def _strip_markers(text: str) -> str:
    previous = None
    while previous != text:
        previous = text
        for marker in (USER_TEXT_BEGIN, USER_TEXT_END):
            text = text.replace(marker, "")
    return text


def untrusted(text: str | None, max_chars: int) -> str:
    """Wrap reader-typed text so the model can tell it apart from our instructions.

    Strips the marker strings themselves (repeatedly, so split markers cannot re-form), control
    characters other than newline and tab, and anything beyond ``max_chars``. Empty input →
    ``(none)`` (unwrapped, as the prompts expect).
    """
    if not text:
        return NONE_TEXT
    cleaned = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    cleaned = "".join(
        ch for ch in cleaned if ch in _KEEP_CONTROLS or unicodedata.category(ch) != "Cc"
    )
    cleaned = _strip_markers(cleaned)[: max(max_chars, 0)]
    cleaned = _strip_markers(cleaned).strip()
    if not cleaned:
        return NONE_TEXT
    return f"{USER_TEXT_BEGIN}{cleaned}{USER_TEXT_END}"


@functools.cache
def catalog_vars() -> dict[str, str]:
    """The closed-list placeholders, generated from the enums (never hand-typed; AI_PROMPTS §2)."""
    return {
        "taxonomy_ids": ", ".join(t.value for t in DocumentType),
        "category_ids": ", ".join(c.value for c in DocumentCategory),
        "tag_list": ", ".join(t.value for t in ResourceTag),
        "red_flag_kinds": ", ".join(k.value for k in MODEL_RED_FLAG_KINDS),
        "plan_step_kinds": ", ".join(k.value for k in PlanStepKind),
        "scam_signal_keys": ", ".join(SCAM_SIGNAL_KEYS),
        "demand_roles": ", ".join(DEMAND_ROLES),
    }


@functools.cache
def prompts_version() -> str:
    """``2026-09-27.1`` from ``ai/prompts/VERSION`` (``prompts_version = <v>``)."""
    raw = VERSION_FILE.read_text(encoding="utf-8").strip()
    m = re.fullmatch(r"prompts_version = (\d{4}-\d{2}-\d{2}\.\d+)", raw)
    if m is None:
        raise PromptError("ai/prompts/VERSION must read 'prompts_version = YYYY-MM-DD.n'")
    return m.group(1)


def all_prompt_files() -> list[str]:
    """Every prompt file name relative to ``ai/prompts`` (system first, then ``user/``)."""
    top = sorted(p.name for p in PROMPTS_DIR.glob("*.md"))
    users = sorted(f"user/{p.name}" for p in (PROMPTS_DIR / "user").glob("*.md"))
    return top + users


__all__ = [
    "CODE_ONLY_RED_FLAG_KINDS",
    "DEMAND_ROLES",
    "MODEL_RED_FLAG_KINDS",
    "NONE_TEXT",
    "PLACEHOLDER",
    "PREAMBLE",
    "PROMPTS_DIR",
    "SCAM_SIGNAL_KEYS",
    "SYSTEM_PROMPT",
    "USER_PROMPT",
    "USER_TEXT_BEGIN",
    "USER_TEXT_END",
    "PromptError",
    "all_prompt_files",
    "catalog_vars",
    "load",
    "placeholders",
    "prompts_version",
    "render",
    "system",
    "untrusted",
    "user",
]
