"""Prompt-injection detection in the paper itself (D-15; AI_PROMPTS §11.8).

``data/safety/injection.yaml`` lists phrases addressed to a model rather than to the reader
("ignore previous instructions", "system prompt", "as an AI", forged ``=== BEGIN`` fences …).
Every transcript block is scanned (NFKC, case-folded). On a hit the pipeline re-runs **once**:
single mode burns black boxes over the hit blocks' ``bbox``es (``mask_boxes`` →
``redaction.mask_regions``; a hit block without a box forces two-call mode instead), two-call mode
re-runs ``explain`` with those blocks rendered as ``[p1b9] [text addressed to computers removed]``
(``render_transcript``). The result then carries ``injection_red_flag`` + ``warnings:
[injection_masked]`` + ``verification.injection_masked``. Chat questions are checked with
``text_has_injection`` (no re-run). Pure functions; nothing logged.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from proxyhealth_api.analysis.i18n import Translator
from proxyhealth_api.analysis.transcript import Transcript
from proxyhealth_api.analysis.verify import normalize
from proxyhealth_api.contracts.analysis import RedFlag
from proxyhealth_api.contracts.enums import RedFlagKind, Severity, WarningCode
from proxyhealth_api.settings import DATA_DIR

INJECTION_YAML = DATA_DIR / "safety" / "injection.yaml"
WARNING_KEY = "warning.injection_masked"
DEFAULT_MASK_TEXT = "[text addressed to computers removed]"


@dataclass(frozen=True)
class InjectionConfig:
    """Parsed ``injection.yaml``."""

    version: str
    mask_text: str
    markers: tuple[str, ...]
    patterns: tuple[re.Pattern[str], ...]


def parse_config(data: Mapping[str, Any]) -> InjectionConfig:
    """Compile a loaded ``injection.yaml`` mapping (raises on a bad regex)."""
    patterns: list[re.Pattern[str]] = []
    for items in (data.get("patterns") or {}).values():
        patterns += [re.compile(str(p), re.IGNORECASE) for p in items or []]
    return InjectionConfig(
        version=str(data.get("version", "0")),
        mask_text=str(data.get("mask_text") or DEFAULT_MASK_TEXT),
        markers=tuple(str(m).casefold() for m in data.get("markers") or []),
        patterns=tuple(patterns),
    )


@lru_cache(maxsize=4)
def load_config(path: Path = INJECTION_YAML) -> InjectionConfig:
    """Load and cache ``injection.yaml``."""
    return parse_config(yaml.safe_load(path.read_text(encoding="utf-8")))


def is_injection(text: str, cfg: InjectionConfig | None = None) -> bool:
    """True when ``text`` contains a marker string or an injection phrase."""
    c = cfg or load_config()
    if not text:
        return False
    norm = normalize(text).casefold()
    if any(m and m in norm for m in c.markers):
        return True
    return any(p.search(norm) for p in c.patterns)


@dataclass
class InjectionScan:
    """Blocks whose text is addressed to computers."""

    hit_ids: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        """True when at least one block matched (the D-15 masked re-run is needed)."""
        return bool(self.hit_ids)


def detect_injection(transcript: Transcript, cfg: InjectionConfig | None = None) -> InjectionScan:
    """Scan every transcript block; hit ids in transcript order."""
    c = cfg or load_config()
    return InjectionScan([b.id for b in transcript.blocks if is_injection(b.text, c)])


def text_has_injection(texts: Iterable[str], cfg: InjectionConfig | None = None) -> bool:
    """Chat/troubleshoot helper: any of ``texts`` (question, messages, user_goal) is a hit."""
    c = cfg or load_config()
    return any(is_injection(t, c) for t in texts if t)


def render_transcript(
    transcript: Transcript,
    masked_ids: Iterable[str] = (),
    cfg: InjectionConfig | None = None,
) -> str:
    """``[p1b1] text`` lines for the two-call ``explain`` prompt, masked blocks replaced by the
    fixed mask text (``[p1b9] [text addressed to computers removed]``)."""
    c = cfg or load_config()
    masked = set(masked_ids)
    lines = []
    for b in transcript.blocks:
        lines.append(f"[{b.id}] {c.mask_text if b.id in masked else b.text}")
    return "\n".join(lines)


@dataclass(frozen=True)
class MaskPlan:
    """Single-mode re-run plan: boxes to burn per page; ``needs_two_call`` when a hit block has
    no ``bbox`` (AI_PROMPTS §11.8: no whole-page fallback — switch to text masking)."""

    boxes_by_page: Mapping[int, list[list[float]]]
    needs_two_call: bool


def mask_boxes(transcript: Transcript, hit_ids: Sequence[str]) -> MaskPlan:
    """Group the hit blocks' boxes by page for ``redaction.mask_regions``."""
    boxes: dict[int, list[list[float]]] = {}
    missing = False
    for block in transcript.blocks_for(hit_ids):
        if block.bbox is None:
            missing = True
            continue
        boxes.setdefault(block.page, []).append(list(block.bbox))
    return MaskPlan(boxes_by_page=boxes, needs_two_call=missing)


def injection_red_flag(
    transcript: Transcript, hit_ids: Sequence[str], t: Translator | None = None
) -> RedFlag:
    """The ``injection_suspected`` red flag (text ``warning.injection_masked`` in the pack)."""
    ids = transcript.existing(hit_ids)
    return RedFlag(
        kind=RedFlagKind.injection_suspected, text=t(WARNING_KEY) if t else WARNING_KEY,
        source_quote=None, span_ids=ids, page=transcript.page_of(ids), severity=Severity.medium,
        fixed_copy_key=None, verified=True,
    )  # fmt: skip


INJECTION_WARNING = WarningCode.injection_masked

__all__ = [
    "DEFAULT_MASK_TEXT",
    "INJECTION_WARNING",
    "INJECTION_YAML",
    "WARNING_KEY",
    "InjectionConfig",
    "InjectionScan",
    "MaskPlan",
    "detect_injection",
    "injection_red_flag",
    "is_injection",
    "load_config",
    "mask_boxes",
    "parse_config",
    "render_transcript",
    "text_has_injection",
]
