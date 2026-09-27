"""Key-pool state machine (D-07). WP0 ships the signatures only; WP1 implements them."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from proxyhealth_api.contracts.admin import AdminKeysResponse
from proxyhealth_api.contracts.config import KeySlotSummary
from proxyhealth_api.contracts.enums import ModelTier
from proxyhealth_api.settings import KeySlotConfig

Outcome = Literal["ok", "429", "5xx", "4xx_fatal", "400"]


@dataclass(frozen=True)
class Slot:
    index: int
    config: KeySlotConfig


class KeyPool:
    """Per-slot, per-tier state as D-07: ``healthy | cooling | rpd_exhausted | disabled``."""

    def __init__(
        self, slots: list[KeySlotConfig], var_dir: Path, clock: Callable[[], datetime]
    ) -> None:
        self.slots = slots
        self.var_dir = var_dir
        self.clock = clock

    def acquire(self, tier: ModelTier) -> Slot | None:
        raise NotImplementedError("KeyPool.acquire is built by WP1")

    def report(
        self,
        slot: Slot,
        tier: ModelTier,
        *,
        outcome: Outcome,
        retry_after: int | None,
        error_text: str | None,
    ) -> None:
        raise NotImplementedError("KeyPool.report is built by WP1")

    def snapshot(self) -> AdminKeysResponse:
        raise NotImplementedError("KeyPool.snapshot is built by WP1")

    def summary(self) -> KeySlotSummary:
        raise NotImplementedError("KeyPool.summary is built by WP1")

    def persist(self) -> None:
        raise NotImplementedError("KeyPool.persist is built by WP1")

    def restore(self) -> None:
        raise NotImplementedError("KeyPool.restore is built by WP1")
