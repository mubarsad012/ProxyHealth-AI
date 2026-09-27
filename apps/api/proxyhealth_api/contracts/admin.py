"""Key-pool state for operators: ``GET /v1/admin/keys`` (API_CONTRACT §3.14)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from proxyhealth_api.contracts.enums import DataUseTier

# API_CONTRACT §3.14 — per-tier slot state (mirrors the D-07 state machine).
SlotState = Literal["healthy", "cooling", "rpd_exhausted", "disabled"]


class TierState(BaseModel):
    """API_CONTRACT §3.14 — one key slot's state for one model tier; no key material."""

    state: SlotState
    cooldown_until: datetime | None
    consecutive_429: int
    rpm_last_minute: int
    rpd_count: int
    rpd_reset_at: datetime
    last_error_code: int | None
    last_used_at: datetime | None


class KeySlotState(BaseModel):
    """API_CONTRACT §3.14 — one configured key slot; ``key_last4`` is the only key-derived value."""

    index: int
    project: str
    billing: bool
    key_last4: str
    tiers: dict[str, TierState]


class AdminKeysResponse(BaseModel):
    """API_CONTRACT §3.14 — the whole key pool, content-free."""

    data_use_tier: DataUseTier
    slots: list[KeySlotState]
