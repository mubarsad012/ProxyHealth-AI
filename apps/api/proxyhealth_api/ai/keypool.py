"""Key-pool state machine (D-07; AI_PROMPTS §8.1–§8.3).

Per slot and per tier: ``healthy | cooling | rpd_exhausted | disabled`` with an injected
``clock`` (tests freeze it; no ``datetime`` monkey-patching). State is persisted to
``var/keypool.json`` after every transition; the file never contains a key string, a request
or any user field (D-08).
"""

import json
import os
import re
from collections import deque
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from proxyhealth_api.contracts.admin import AdminKeysResponse, KeySlotState, SlotState, TierState
from proxyhealth_api.contracts.config import KeySlotSummary
from proxyhealth_api.contracts.enums import DataUseTier, ModelTier
from proxyhealth_api.logging_ import log_event
from proxyhealth_api.settings import KeySlotConfig, Settings

Outcome = Literal["ok", "429", "5xx", "4xx_fatal", "400"]

PERSIST_VERSION = 1
PERSIST_FILENAME = "keypool.json"
RPM_WINDOW = timedelta(seconds=60)
MAX_BACKOFF_S = 900
BASE_BACKOFF_S = 30
_PACIFIC = ZoneInfo("America/Los_Angeles")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# D-07: only a 429 that names the daily quota benches a key for the day. ``per ?day`` also covers
# Gemini quota ids such as ``GenerateContentInputTokensPerModelPerDay`` (per-minute ids say
# ``PerMinute`` and never match).
DAILY_RE = re.compile(r"(per ?day|RPD|daily|requests per day|GenerateRequestsPerDay)", re.I)

# Worst-first ordering for the slot-level summary (a slot is only "healthy" on both tiers).
_SEVERITY: dict[SlotState, int] = {"healthy": 0, "cooling": 1, "rpd_exhausted": 2, "disabled": 3}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def next_pacific_midnight(now: datetime) -> datetime:
    """The next 00:00 America/Los_Angeles strictly after ``now`` (RPD reset; gemini.md)."""
    local = _aware(now).astimezone(_PACIFIC)
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(UTC)


def backoff_seconds(consecutive_429: int) -> int:
    """``min(30 · 2^(n-1), 900)`` for the n-th consecutive 429 without a Retry-After."""
    exponent = min(max(consecutive_429 - 1, 0), 16)
    return min(BASE_BACKOFF_S * (1 << exponent), MAX_BACKOFF_S)


@dataclass(frozen=True)
class Slot:
    index: int
    config: KeySlotConfig

    @property
    def key_last4(self) -> str:
        return self.config.key.get_secret_value()[-4:]


@dataclass
class _TierState:
    """Mutable per-slot, per-tier state (AI_PROMPTS §8.1 ``TierState``)."""

    rpd_reset_at: datetime
    state: SlotState = "healthy"
    cooldown_until: datetime | None = None
    consecutive_429: int = 0
    rpm_window: deque[datetime] = field(default_factory=deque)
    rpd_count: int = 0
    last_error_code: int | None = None
    last_used_at: datetime | None = None

    def to_contract(self, now: datetime) -> TierState:
        self._trim(now)
        return TierState(
            state=self.state,
            cooldown_until=self.cooldown_until,
            consecutive_429=self.consecutive_429,
            rpm_last_minute=len(self.rpm_window),
            rpd_count=self.rpd_count,
            rpd_reset_at=self.rpd_reset_at,
            last_error_code=self.last_error_code,
            last_used_at=self.last_used_at,
        )

    def _trim(self, now: datetime) -> None:
        cutoff = now - RPM_WINDOW
        while self.rpm_window and self.rpm_window[0] <= cutoff:
            self.rpm_window.popleft()


class KeyPool:
    """Per-slot, per-tier state as D-07: ``healthy | cooling | rpd_exhausted | disabled``.

    ``soft_caps`` maps a tier to ``RPD_SOFT_CAP_*`` (``0`` = disabled). The constructor restores
    ``var/keypool.json`` when present, so a restart never forgets a burned daily quota.
    ``data_use_tier`` overrides the tier computed from billing flags: ``AI_PROVIDER=openai_compat``
    runs one synthetic slot whose tier is ``OPENAI_COMPAT_DATA_TIER`` (free-ai-providers §4.2
    rule 7, §4.7).
    """

    def __init__(
        self,
        slots: list[KeySlotConfig],
        var_dir: Path,
        clock: Callable[[], datetime],
        *,
        soft_caps: Mapping[ModelTier, int] | None = None,
        data_use_tier: DataUseTier | None = None,
    ) -> None:
        projects = [s.project for s in slots]
        if len(set(projects)) != len(projects):
            dupes = sorted({p for p in projects if projects.count(p) > 1})
            raise ValueError(f"GEMINI_KEYS projects must be distinct (D-07); duplicated: {dupes}")
        self.slots = slots
        self.tier_override = data_use_tier
        self.var_dir = var_dir
        self.clock = clock
        self.soft_caps: dict[ModelTier, int] = {
            ModelTier.pro: 0,
            ModelTier.fast: 0,
            **(dict(soft_caps) if soft_caps else {}),
        }
        self._slots = [Slot(index=i, config=cfg) for i, cfg in enumerate(slots)]
        now = self._now()
        self._state: list[dict[ModelTier, _TierState]] = [
            {tier: _TierState(rpd_reset_at=next_pacific_midnight(now)) for tier in ModelTier}
            for _ in self._slots
        ]
        self.restore()

    @classmethod
    def from_settings(cls, settings: Settings, clock: Callable[[], datetime]) -> "KeyPool":
        """``GEMINI_KEYS`` + ``VAR_DIR`` + ``RPD_SOFT_CAP_*`` from ``Settings`` (lane 1A wiring)."""
        return cls(
            list(settings.gemini_keys),
            settings.var_dir,
            clock,
            soft_caps={
                ModelTier.pro: settings.rpd_soft_cap_pro,
                ModelTier.fast: settings.rpd_soft_cap_fast,
            },
        )

    # ------------------------------------------------------------------ helpers

    @property
    def path(self) -> Path:
        return self.var_dir / PERSIST_FILENAME

    def _now(self) -> datetime:
        return _aware(self.clock())

    def slot(self, index: int) -> Slot:
        return self._slots[index]

    def tier_state(self, slot: Slot | int, tier: ModelTier) -> _TierState:
        index = slot if isinstance(slot, int) else slot.index
        return self._state[index][tier]

    def effective_state(self, slot: Slot | int, tier: ModelTier) -> SlotState:
        """Lazily heal timed states (AI_PROMPTS §8.2 ``effective_state``)."""
        ts = self.tier_state(slot, tier)
        now = self._now()
        if ts.state == "cooling" and ts.cooldown_until is not None and now >= ts.cooldown_until:
            ts.state = "healthy"
            ts.cooldown_until = None
        if ts.state == "rpd_exhausted" and now >= ts.rpd_reset_at:
            ts.state = "healthy"
            ts.rpd_count = 0
            ts.rpd_reset_at = next_pacific_midnight(now)
        elif now >= ts.rpd_reset_at:
            ts.rpd_count = 0
            ts.rpd_reset_at = next_pacific_midnight(now)
        return ts.state

    # ---------------------------------------------------------------- selection

    def acquire(self, tier: ModelTier, *, exclude: Collection[int] = ()) -> Slot | None:
        """Least-recently-used healthy slot for ``tier``, billed slots first (§8.3)."""
        cap = self.soft_caps.get(tier, 0)
        candidates = [
            s
            for s in self._slots
            if s.index not in exclude
            and self.effective_state(s, tier) == "healthy"
            and not (cap and self.tier_state(s, tier).rpd_count >= cap)
        ]
        if not candidates:
            return None
        billed = [s for s in candidates if s.config.billing]
        pool = billed or candidates
        chosen = min(pool, key=lambda s: self.tier_state(s, tier).last_used_at or _EPOCH)
        # Stamp at hand-out so concurrent requests spread across slots instead of all taking the
        # same LRU slot before any of them reports (``report`` stamps again on completion).
        self.tier_state(chosen, tier).last_used_at = self._now()
        if not chosen.config.billing and any(s.config.billing for s in self._slots):
            log_event(route="keypool.unbilled_slot_used", slot_index=chosen.index, tier=tier)
        return chosen

    # -------------------------------------------------------------- transitions

    def report(
        self,
        slot: Slot,
        tier: ModelTier,
        *,
        outcome: Outcome,
        retry_after: int | None = None,
        error_text: str | None = None,
        code: int | None = None,
    ) -> None:
        """Apply one D-07 transition and persist (AI_PROMPTS §8.2)."""
        ts = self.tier_state(slot, tier)
        now = self._now()
        self.effective_state(slot, tier)
        ts.last_used_at = now
        ts.rpm_window.append(now)
        ts._trim(now)
        if outcome == "ok":
            ts.consecutive_429 = 0
            ts.rpd_count += 1
            ts.last_error_code = None
        elif outcome == "429":
            ts.consecutive_429 += 1
            ts.last_error_code = 429
            if DAILY_RE.search(error_text or ""):
                ts.state = "rpd_exhausted"
                ts.cooldown_until = None
                ts.rpd_reset_at = next_pacific_midnight(now)
            else:
                secs = retry_after
                if secs is None:
                    secs = backoff_seconds(ts.consecutive_429)
                ts.state = "cooling"
                ts.cooldown_until = now + timedelta(seconds=max(secs, 0))
        elif outcome == "5xx":
            ts.last_error_code = code if code is not None else 503
        elif outcome == "400":
            ts.last_error_code = 400
        elif outcome == "4xx_fatal":
            ts.state = "disabled"
            ts.cooldown_until = None
            ts.last_error_code = code if code is not None else 403
            log_event(route="keypool.slot_disabled", slot_index=slot.index, tier=tier, status=code)
        self.persist()

    # ------------------------------------------------------------------ queries

    def min_cooldown_seconds(self, tier: ModelTier) -> int | None:
        """Seconds until the earliest cooling/exhausted slot for ``tier`` heals; None if none."""
        now = self._now()
        waits: list[int] = []
        for s in self._slots:
            state = self.effective_state(s, tier)
            ts = self.tier_state(s, tier)
            until: datetime | None = None
            if state == "cooling":
                until = ts.cooldown_until
            elif state == "rpd_exhausted":
                until = ts.rpd_reset_at
            if until is not None:
                waits.append(max(int((until - now).total_seconds() + 0.999), 1))
        return min(waits) if waits else None

    def counts(self, tier: ModelTier) -> dict[SlotState, int]:
        result: dict[SlotState, int] = {
            "healthy": 0, "cooling": 0, "rpd_exhausted": 0, "disabled": 0,
        }  # fmt: skip
        for s in self._slots:
            result[self.effective_state(s, tier)] += 1
        return result

    def data_use_tier(self) -> DataUseTier:
        if self.tier_override is not None:
            return self.tier_override
        if not self._slots:
            return DataUseTier.none
        billed = [s.config.billing for s in self._slots]
        if all(billed):
            return DataUseTier.paid
        if not any(billed):
            return DataUseTier.unpaid
        return DataUseTier.mixed

    def snapshot(self) -> AdminKeysResponse:
        now = self._now()
        states: list[KeySlotState] = []
        for s in self._slots:
            tiers: dict[str, TierState] = {}
            for tier in ModelTier:
                self.effective_state(s, tier)
                tiers[tier.value] = self.tier_state(s, tier).to_contract(now)
            states.append(
                KeySlotState(
                    index=s.index,
                    project=s.config.project,
                    billing=s.config.billing,
                    key_last4=s.key_last4,
                    tiers=tiers,
                )
            )
        return AdminKeysResponse(data_use_tier=self.data_use_tier(), slots=states)

    def summary(self) -> KeySlotSummary:
        """Slot-level counts: a slot is healthy only when every tier is; otherwise worst tier."""
        counts: dict[SlotState, int] = {
            "healthy": 0, "cooling": 0, "rpd_exhausted": 0, "disabled": 0,
        }  # fmt: skip
        for s in self._slots:
            worst = max((self.effective_state(s, t) for t in ModelTier), key=_SEVERITY.__getitem__)
            counts[worst] += 1
        return KeySlotSummary(total=len(self._slots), **counts)

    # ------------------------------------------------------------- persistence

    def _tier_json(self, slot: Slot, tier: ModelTier, now: datetime) -> dict[str, Any]:
        data: dict[str, Any] = self.tier_state(slot, tier).to_contract(now).model_dump(mode="json")
        return data

    def persist(self) -> None:
        """Atomic write of ``var/keypool.json`` (temp file + ``os.replace``); never a key."""
        now = self._now()
        payload: dict[str, Any] = {
            "version": PERSIST_VERSION,
            "saved_at": now.isoformat(),
            "slots": [
                {
                    "project": s.config.project,
                    "key_last4": s.key_last4,
                    "tiers": {
                        tier.value: self._tier_json(s, tier, now) for tier in ModelTier
                    },
                }
                for s in self._slots
            ],
        }
        self.var_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{PERSIST_FILENAME}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)

    def restore(self) -> None:
        """Load saved states matched by ``project`` **and** ``key_last4``; heal expired ones."""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict) or raw.get("version") != PERSIST_VERSION:
            return
        saved = {
            (entry.get("project"), entry.get("key_last4")): entry.get("tiers", {})
            for entry in raw.get("slots", [])
            if isinstance(entry, dict)
        }
        now = self._now()
        for s in self._slots:
            tiers = saved.get((s.config.project, s.key_last4))
            if not isinstance(tiers, dict):
                continue
            for tier in ModelTier:
                data = tiers.get(tier.value)
                if not isinstance(data, dict):
                    continue
                try:
                    parsed = TierState.model_validate(data)
                except ValueError:
                    continue
                ts = self.tier_state(s, tier)
                ts.state = parsed.state
                ts.cooldown_until = parsed.cooldown_until
                ts.consecutive_429 = parsed.consecutive_429
                ts.rpd_count = parsed.rpd_count
                ts.rpd_reset_at = parsed.rpd_reset_at
                ts.last_error_code = parsed.last_error_code
                ts.last_used_at = parsed.last_used_at
                ts.rpm_window.clear()
                if ts.rpd_reset_at <= now:
                    ts.rpd_reset_at = next_pacific_midnight(now)
                    ts.rpd_count = 0
                    if ts.state == "rpd_exhausted":
                        ts.state = "healthy"
                self.effective_state(s, tier)
