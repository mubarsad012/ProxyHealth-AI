"""``RecordingProvider`` — dev-only capture of live model output for the goldens (D-16; AI_PROMPTS
§10.4; CL-010).

Wraps a real provider. When a call succeeds for a **sample paper** (``hints["demo_sample_id"]``
names an existing ``data/fixtures/<id>/``) and the task is ``analyze_single`` or
``troubleshoot``, it writes ``out.<target_language>.json`` with ``_meta.recorded_by =
"recording_provider"``, the model id and the current ``ai/prompts/VERSION``. It refuses to exist
unless ``ENV=development``, ``AI_PROVIDER=gemini`` and ``RECORD_FIXTURES=1``. A call is recorded
only when it carries at least one media part and **every** media part is byte-identical to one of
that fixture's own ``page-<n>.png`` files (AI_PROMPTS §10.4 "fixture bytes only — never a user
upload"): a sample id alongside any other image, or with no image at all, is passed through
untouched and nothing is written, so a user's paper is never recorded (ARCHITECTURE §7).

Recordings are reviewed by a human before commit. ``scripts/make_fixtures.py`` keeps a recorded
file (``_meta.recorded_by == "recording_provider"``) instead of overwriting or deleting it, and
``--check`` reports it as drift, until the reviewer folds it into that fixture's
``template.yaml`` (the templates stay the single source) or deletes it.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from proxyhealth_api.ai import prompt_loader
from proxyhealth_api.ai.provider import AIProvider, Part, StructuredResult, Task
from proxyhealth_api.contracts.enums import ModelTier, Provider, ThinkingLevel
from proxyhealth_api.contracts.model_out import AnalysisModelOut, TroubleshootModelOut
from proxyhealth_api.settings import DATA_DIR, Settings

RECORDED_TASKS = frozenset({Task.analyze_single, Task.troubleshoot})
_ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")
_LANG_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


class RecordingRefused(RuntimeError):
    """Recording was requested outside development, without Gemini, or without the flag."""


def recording_allowed(settings: Settings) -> bool:
    return (
        settings.env == "development"
        and settings.ai_provider == "gemini"
        and settings.record_fixtures
    )


def prompts_version() -> str:
    """``prompt_loader.prompts_version()`` (the one parser), or ``unknown`` if unreadable."""
    try:
        return prompt_loader.prompts_version()
    except (OSError, prompt_loader.PromptError):
        return "unknown"


class RecordingProvider:
    """``AIProvider`` decorator that records sample-paper outputs (dev only)."""

    def __init__(
        self,
        inner: AIProvider,
        settings: Settings,
        *,
        out_dir: Path = DATA_DIR / "fixtures",
        today: Callable[[], date] = date.today,
    ) -> None:
        if not recording_allowed(settings):
            raise RecordingRefused(
                "RecordingProvider needs ENV=development, AI_PROVIDER=gemini, RECORD_FIXTURES=1"
            )
        self.inner = inner
        self.name: Provider = inner.name
        self.out_dir = out_dir
        self.today = today
        self.recorded: list[Path] = []
        self._page_digests: dict[str, frozenset[bytes]] = {}

    def target(self, task: Task, hints: Mapping[str, str]) -> Path | None:
        """Where a successful call would be recorded, or ``None`` (not a sample call)."""
        sample = hints.get("demo_sample_id") or ""
        lang = hints.get("target_language") or "en"
        if task not in RECORDED_TASKS or not _ID_RE.match(sample) or not _LANG_RE.match(lang):
            return None
        folder = self.out_dir / sample
        if not (folder / "manifest.yaml").is_file():
            return None
        return folder / f"out.{lang}.json"

    def fixture_digests(self, folder: Path) -> frozenset[bytes]:
        """SHA-256 digests of the committed ``page-<n>.png`` files of one fixture folder."""
        cached = self._page_digests.get(folder.name)
        if cached is None:
            cached = frozenset(
                hashlib.sha256(png.read_bytes()).digest()
                for png in sorted(folder.glob("page-*.png"))
                if png.is_file()
            )
            self._page_digests[folder.name] = cached
        return cached

    def media_is_fixture(self, path: Path, parts: Sequence[Part]) -> bool:
        """True only when there is media and every media part is one of the fixture's pages."""
        media = [p for p in parts if p.kind == "bytes"]
        if not media:
            return False
        pages = self.fixture_digests(path.parent)
        return all(p.data is not None and hashlib.sha256(p.data).digest() in pages for p in media)

    def write(self, path: Path, result: StructuredResult) -> None:
        parsed = result.parsed
        assert isinstance(parsed, AnalysisModelOut | TroubleshootModelOut)
        body = {
            "_meta": {
                "prompts_version": prompts_version(),
                "recorded_by": "recording_provider",
                "recorded_on": self.today().isoformat(),
                "model_id": result.model_id,
            },
            **parsed.model_dump(mode="json"),
        }
        path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", "utf-8")
        self.recorded.append(path)

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
        result = await self.inner.generate_structured(
            task=task, tier=tier, parts=parts, system=system, schema=schema, thinking=thinking,
            media_resolution=media_resolution, max_output_tokens=max_output_tokens,
            request_id=request_id, slot_index=slot_index, hints=hints,
        )  # fmt: skip
        path = self.target(task, hints or {})
        ok = (
            path is not None
            and self.media_is_fixture(path, parts)
            and result.blocked_reason is None
            and not result.incomplete
            and isinstance(result.parsed, AnalysisModelOut | TroubleshootModelOut)
        )
        if ok and path is not None:
            self.write(path, result)
        return result


def wrap_if_enabled(provider: AIProvider, settings: Settings) -> AIProvider:
    """``RecordingProvider(provider)`` when recording is allowed, else ``provider`` unchanged."""
    return RecordingProvider(provider, settings) if recording_allowed(settings) else provider


__all__ = [
    "RECORDED_TASKS",
    "RecordingProvider",
    "RecordingRefused",
    "recording_allowed",
    "wrap_if_enabled",
]
