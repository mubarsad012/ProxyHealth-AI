"""The only path from pipelines to providers (BUILD_PLAN §4.1).

WP0 ships a pass-through ``AIService`` (one call, slot 0, no retries) and the tiny
``UnconfiguredGeminiProvider`` that stands in for ``ai/gemini.py`` until WP1 builds it.
WP1 replaces the body with the D-07 budgets, degradation and error mapping.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from proxyhealth_api.ai.keypool import KeyPool
from proxyhealth_api.ai.provider import AIProvider, Part, StructuredResult, Task
from proxyhealth_api.ai.routing import RouteConfig, route
from proxyhealth_api.contracts.enums import (
    ErrorCode,
    ModelQuality,
    ModelTier,
    Provider,
    ThinkingLevel,
    WarningCode,
)
from proxyhealth_api.errors import ApiError
from proxyhealth_api.settings import Settings


@dataclass
class GenerateOutcome:
    result: StructuredResult
    route: RouteConfig
    quality: ModelQuality
    slot_index: int | None
    attempts: int
    warnings: list[WarningCode] = field(default_factory=list)


class SchemaFallbackNeeded(Exception):
    """Single-call output rejected/incomplete → the pipeline switches to ``two_call``."""


class UnconfiguredGeminiProvider:
    """``AI_PROVIDER=gemini`` before WP1 lands ``ai/gemini.py``: every call is a 503."""

    name: Provider = Provider.gemini

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
        raise ApiError(
            ErrorCode.provider_not_configured,
            503,
            "AI_PROVIDER=gemini but no usable provider is configured (ai/gemini.py is WP1).",
            retry_after=60,
        )


class AIService:
    def __init__(self, provider: AIProvider, keypool: KeyPool | None, settings: Settings) -> None:
        self.provider = provider
        self.keypool = keypool
        self.settings = settings

    async def generate(
        self,
        *,
        task: Task,
        parts: Sequence[Part],
        system: str,
        schema: type[BaseModel],
        pages: int = 1,
        is_pdf: bool = False,
        request_id: str,
        hints: Mapping[str, str] | None = None,
    ) -> GenerateOutcome:
        cfg = route(task, pages=pages, is_pdf=is_pdf, degraded=False, settings=self.settings)
        result = await self.provider.generate_structured(
            task=task,
            tier=cfg.tier,
            parts=parts,
            system=system,
            schema=schema,
            thinking=cfg.thinking,
            media_resolution=cfg.media_resolution,
            max_output_tokens=cfg.max_output_tokens,
            request_id=request_id,
            slot_index=0,
            hints=hints,
        )
        if result.blocked_reason:
            raise ApiError(
                ErrorCode.content_blocked,
                422,
                "Upstream blocked the generation.",
                details={"block_reason": result.blocked_reason.lower()},
            )
        return GenerateOutcome(
            result=result, route=cfg, quality=ModelQuality.full, slot_index=0, attempts=1
        )
