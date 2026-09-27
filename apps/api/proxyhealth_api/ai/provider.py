"""Provider seam (BUILD_PLAN §4.1, permanent): ``Task``, ``Part``, ``StructuredResult``,
``AIProvider``.

Upstream errors propagate as exceptions; the failover engine reads
``getattr(exc, "status_code", None) or getattr(exc, "code", None)`` (D-05).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel

from proxyhealth_api.contracts.enums import ModelTier, Provider, ThinkingLevel


class Task(StrEnum):
    analyze_single = "analyze_single"
    transcribe = "transcribe"
    explain = "explain"
    troubleshoot = "troubleshoot"
    chat = "chat"
    langpack_chunk = "langpack_chunk"
    resolve_language = "resolve_language"
    tag = "tag"
    phrasing_rewrite = "phrasing_rewrite"
    clerk_translate = "clerk_translate"


@dataclass(frozen=True)
class Part:
    """One content part; text parts always precede media parts (D-04)."""

    kind: Literal["text", "bytes"]
    text: str | None = None
    data: bytes | None = None
    mime_type: str | None = None

    @staticmethod
    def of_text(s: str) -> "Part":
        return Part(kind="text", text=s)

    @staticmethod
    def of_bytes(data: bytes, mime_type: str) -> "Part":
        return Part(kind="bytes", data=data, mime_type=mime_type)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0


@dataclass
class StructuredResult:
    parsed: BaseModel | None
    raw_text: str | None
    model_id: str
    usage: Usage
    blocked_reason: str | None = None
    finish_reason: str | None = None
    incomplete: bool = False


class AIProvider(Protocol):
    name: Provider

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
    ) -> StructuredResult: ...
