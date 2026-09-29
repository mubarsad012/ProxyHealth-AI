"""``ai/keypool.KeyPool`` — every D-07 transition with an injected clock (BUILD_PLAN §5.2
acceptance; AI_PROMPTS §8.1–§8.3). WP1 lane 1B. No monkey-patching of ``datetime``."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr

from proxyhealth_api.ai.keypool import (
    DAILY_RE,
    KeyPool,
    Slot,
    backoff_seconds,
    next_pacific_midnight,
)
from proxyhealth_api.contracts.admin import AdminKeysResponse
from proxyhealth_api.contracts.enums import DataUseTier, ModelTier
from proxyhealth_api.settings import KeySlotConfig, Settings

NOW = datetime(2026, 9, 24, 14, 0, 0, tzinfo=UTC)  # conftest FROZEN_NOW; 07:00 PDT
PACIFIC_MIDNIGHT = datetime(2026, 9, 25, 7, 0, 0, tzinfo=UTC)  # API_CONTRACT §3.14 example
KEY_A = "AIzaSy-test-key-alpha-Qx7A"
KEY_B = "AIzaSy-test-key-bravo-Zz9B"
KEY_C = "AIzaSy-test-key-charlie-Mm3C"
PRO = ModelTier.pro
FAST = ModelTier.fast


class FakeClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now = self.now + timedelta(**delta)


def cfg(key: str, project: str, billing: bool = True) -> KeySlotConfig:
    return KeySlotConfig(key=SecretStr(key), project=project, billing=billing)


def two_slots() -> list[KeySlotConfig]:
    return [cfg(KEY_A, "proj-a"), cfg(KEY_B, "proj-b")]


def make_pool(
    tmp_path: Path, slots: list[KeySlotConfig] | None = None
) -> tuple[KeyPool, FakeClock]:
    clock = FakeClock()
    pool = KeyPool(slots if slots is not None else two_slots(), tmp_path / "var", clock)
    return pool, clock


def must_acquire(pool: KeyPool, tier: ModelTier) -> Slot:
    slot = pool.acquire(tier)
    assert slot is not None
    return slot


# ------------------------------------------------------------------------- selection


def test_acquire_returns_least_recently_used_healthy_slot(tmp_path: Path) -> None:
    pool, clock = make_pool(tmp_path)
    first = must_acquire(pool, PRO)
    pool.report(first, PRO, outcome="ok", retry_after=None, error_text=None)
    clock.advance(seconds=1)
    second = must_acquire(pool, PRO)
    assert second.index != first.index
    pool.report(second, PRO, outcome="ok", retry_after=None, error_text=None)
    clock.advance(seconds=1)
    assert must_acquire(pool, PRO).index == first.index  # LRU wraps around


def test_concurrent_acquires_spread_across_slots_before_any_report(tmp_path: Path) -> None:
    pool, _ = make_pool(tmp_path)
    a = must_acquire(pool, PRO)
    b = must_acquire(pool, PRO)
    assert a.index != b.index
    assert pool.tier_state(a, PRO).last_used_at == NOW


def test_acquire_prefers_billed_slots(tmp_path: Path) -> None:
    pool, _ = make_pool(tmp_path, [cfg(KEY_A, "free", billing=False), cfg(KEY_B, "paid")])
    assert must_acquire(pool, PRO).config.project == "paid"
    assert must_acquire(pool, FAST).config.project == "paid"


def test_acquire_falls_back_to_unbilled_when_no_billed_slot_is_healthy(tmp_path: Path) -> None:
    pool, _ = make_pool(tmp_path, [cfg(KEY_A, "free", billing=False), cfg(KEY_B, "paid")])
    paid = must_acquire(pool, PRO)
    pool.report(paid, PRO, outcome="429", retry_after=30, error_text="rate")
    assert must_acquire(pool, PRO).config.project == "free"


def test_acquire_exclude_skips_already_tried_slots(tmp_path: Path) -> None:
    pool, _ = make_pool(tmp_path)
    first = must_acquire(pool, PRO)
    other = pool.acquire(PRO, exclude={first.index})
    assert other is not None and other.index != first.index
    assert pool.acquire(PRO, exclude={0, 1}) is None


def test_acquire_returns_none_when_no_slots_configured(tmp_path: Path) -> None:
    pool, _ = make_pool(tmp_path, [])
    assert pool.acquire(PRO) is None
    assert pool.summary().total == 0
    assert pool.data_use_tier() is DataUseTier.none


def test_distinct_project_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="distinct"):
        KeyPool([cfg(KEY_A, "same"), cfg(KEY_B, "same")], tmp_path / "var", FakeClock())


def test_soft_cap_skips_slots_at_the_cap(tmp_path: Path) -> None:
    clock = FakeClock()
    pool = KeyPool(two_slots(), tmp_path / "var", clock, soft_caps={PRO: 2})
    a = must_acquire(pool, PRO)
    pool.report(a, PRO, outcome="ok", retry_after=None, error_text=None)
    pool.report(a, PRO, outcome="ok", retry_after=None, error_text=None)
    assert pool.tier_state(a, PRO).rpd_count == 2
    picked = {must_acquire(pool, PRO).index for _ in range(3)}
    assert picked == {1 - a.index}  # slot ``a`` is skipped for pro
    assert must_acquire(pool, FAST) is not None  # cap is per tier; fast has none


def test_soft_cap_zero_means_disabled(tmp_path: Path) -> None:
    clock = FakeClock()
    pool = KeyPool([cfg(KEY_A, "only")], tmp_path / "var", clock, soft_caps={PRO: 0})
    slot = must_acquire(pool, PRO)
    for _ in range(50):
        pool.report(slot, PRO, outcome="ok", retry_after=None, error_text=None)
    assert must_acquire(pool, PRO).index == slot.index


def test_from_settings_reads_soft_caps(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        ai_provider="gemini",
        gemini_keys=two_slots(),
        var_dir=tmp_path / "var",
        rpd_soft_cap_pro=5,
        rpd_soft_cap_fast=9,
    )
    pool = KeyPool.from_settings(settings, FakeClock())
    assert pool.soft_caps == {PRO: 5, FAST: 9}
    assert pool.var_dir == tmp_path / "var"
    assert len(pool.slots) == 2


# ------------------------------------------------------------------------ 429 → cooling


def test_429_rotates_to_the_next_slot(tmp_path: Path) -> None:
    pool, _ = make_pool(tmp_path)
    first = must_acquire(pool, PRO)
    pool.report(first, PRO, outcome="429", retry_after=None, error_text="RESOURCE_EXHAUSTED")
    assert pool.effective_state(first, PRO) == "cooling"
    nxt = must_acquire(pool, PRO)
    assert nxt.index != first.index
    assert pool.effective_state(nxt, PRO) == "healthy"


def test_429_with_retry_after_cools_for_exactly_that_many_seconds(tmp_path: Path) -> None:
    pool, clock = make_pool(tmp_path, [cfg(KEY_A, "only")])
    slot = must_acquire(pool, PRO)
    pool.report(slot, PRO, outcome="429", retry_after=17, error_text="Quota exceeded")
    ts = pool.tier_state(slot, PRO)
    assert ts.state == "cooling"
    assert ts.cooldown_until == NOW + timedelta(seconds=17)
    assert ts.consecutive_429 == 1 and ts.last_error_code == 429
    assert pool.min_cooldown_seconds(PRO) == 17
    clock.advance(seconds=16, milliseconds=999)
    assert pool.acquire(PRO) is None
    assert pool.min_cooldown_seconds(PRO) == 1
    clock.advance(milliseconds=1)
    assert pool.effective_state(slot, PRO) == "healthy"
    assert pool.tier_state(slot, PRO).cooldown_until is None
    assert must_acquire(pool, PRO).index == slot.index
    assert pool.min_cooldown_seconds(PRO) is None


def test_429_without_retry_after_backs_off_exponentially_capped_at_900(tmp_path: Path) -> None:
    pool, clock = make_pool(tmp_path, [cfg(KEY_A, "only")])
    slot = must_acquire(pool, PRO)
    expected = [30, 60, 120, 240, 480, 900, 900]
    for n, secs in enumerate(expected, start=1):
        pool.report(slot, PRO, outcome="429", retry_after=None, error_text="rate limit")
        ts = pool.tier_state(slot, PRO)
        assert ts.consecutive_429 == n
        assert ts.cooldown_until == clock.now + timedelta(seconds=secs)
        clock.advance(seconds=secs)  # heal, then hit 429 again
        assert pool.effective_state(slot, PRO) == "healthy"
    assert [backoff_seconds(n) for n in range(1, 8)] == expected


def test_ok_resets_consecutive_429_and_counts_rpd(tmp_path: Path) -> None:
    pool, clock = make_pool(tmp_path, [cfg(KEY_A, "only")])
    slot = must_acquire(pool, PRO)
    pool.report(slot, PRO, outcome="429", retry_after=1, error_text="x")
    clock.advance(seconds=1)
    pool.report(slot, PRO, outcome="ok", retry_after=None, error_text=None)
    ts = pool.tier_state(slot, PRO)
    assert ts.consecutive_429 == 0 and ts.rpd_count == 1 and ts.last_error_code is None
    assert ts.last_used_at == clock.now
    assert len(ts.rpm_window) == 2  # both reports fell inside the sliding 60 s window


def test_tiers_are_independent(tmp_path: Path) -> None:
    pool, _ = make_pool(tmp_path, [cfg(KEY_A, "only")])
    slot = must_acquire(pool, PRO)
    pool.report(slot, PRO, outcome="429", retry_after=60, error_text="x")
    assert pool.acquire(PRO) is None
    assert must_acquire(pool, FAST).index == slot.index
    assert pool.effective_state(slot, FAST) == "healthy"


def test_plain_429_never_benches_a_key_for_the_day(tmp_path: Path) -> None:
    pool, _ = make_pool(tmp_path, [cfg(KEY_A, "only")])
    slot = must_acquire(pool, PRO)
    for text in (
        "RESOURCE_EXHAUSTED",
        "Too many requests",
        "requests per minute exceeded",
        "quotaId: GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
        None,
    ):
        pool.report(slot, PRO, outcome="429", retry_after=5, error_text=text)
        assert pool.tier_state(slot, PRO).state == "cooling"


def test_rpm_window_is_a_sliding_60s_deque(tmp_path: Path) -> None:
    pool, clock = make_pool(tmp_path, [cfg(KEY_A, "only")])
    slot = must_acquire(pool, PRO)
    for _ in range(3):
        pool.report(slot, PRO, outcome="ok", retry_after=None, error_text=None)
        clock.advance(seconds=10)
    assert pool.snapshot().slots[0].tiers["pro"].rpm_last_minute == 3
    clock.advance(seconds=31)  # first report is now 61 s old
    assert pool.snapshot().slots[0].tiers["pro"].rpm_last_minute == 2


# ------------------------------------------------------------------ 429 → rpd_exhausted


@pytest.mark.parametrize(
    "text",
    [
        "Quota exceeded for quota metric 'GenerateRequestsPerDay'",
        "You exceeded your current quota: requests per day",
        "Daily limit reached",
        "limit: 20 RPD",
        "Resource has been exhausted (per day)",
        "quotaId: GenerateContentInputTokensPerModelPerDay-FreeTier",
    ],
)
def test_daily_quota_429_marks_rpd_exhausted_until_pacific_midnight(
    tmp_path: Path, text: str
) -> None:
    pool, clock = make_pool(tmp_path, [cfg(KEY_A, "only")])
    slot = must_acquire(pool, PRO)
    assert DAILY_RE.search(text)
    pool.report(slot, PRO, outcome="429", retry_after=17, error_text=text)
    ts = pool.tier_state(slot, PRO)
    assert ts.state == "rpd_exhausted"
    assert ts.cooldown_until is None  # not a timed cooldown: the day is burned
    assert ts.rpd_reset_at == PACIFIC_MIDNIGHT
    assert pool.acquire(PRO) is None
    assert pool.min_cooldown_seconds(PRO) == int((PACIFIC_MIDNIGHT - NOW).total_seconds())
    clock.now = PACIFIC_MIDNIGHT - timedelta(seconds=1)
    assert pool.acquire(PRO) is None
    clock.now = PACIFIC_MIDNIGHT
    assert pool.effective_state(slot, PRO) == "healthy"
    ts = pool.tier_state(slot, PRO)
    assert ts.rpd_count == 0
    assert ts.rpd_reset_at == datetime(2026, 9, 26, 7, 0, 0, tzinfo=UTC)
    assert must_acquire(pool, PRO).index == slot.index


def test_rpd_count_resets_at_pacific_midnight_for_healthy_slots(tmp_path: Path) -> None:
    pool, clock = make_pool(tmp_path, [cfg(KEY_A, "only")])
    slot = must_acquire(pool, PRO)
    pool.report(slot, PRO, outcome="ok", retry_after=None, error_text=None)
    assert pool.tier_state(slot, PRO).rpd_count == 1
    clock.now = PACIFIC_MIDNIGHT
    assert pool.effective_state(slot, PRO) == "healthy"
    assert pool.tier_state(slot, PRO).rpd_count == 0


def test_next_pacific_midnight_handles_pdt_and_pst() -> None:
    assert next_pacific_midnight(NOW) == PACIFIC_MIDNIGHT  # PDT: 00:00 = 07:00Z
    winter = datetime(2026, 12, 10, 14, 0, tzinfo=UTC)
    assert next_pacific_midnight(winter) == datetime(2026, 12, 11, 8, 0, tzinfo=UTC)  # PST
    # 23:30 Pacific (06:30Z next calendar day in UTC) → still the coming local midnight.
    late = datetime(2026, 9, 25, 6, 30, tzinfo=UTC)
    assert next_pacific_midnight(late) == PACIFIC_MIDNIGHT
    assert next_pacific_midnight(PACIFIC_MIDNIGHT) > PACIFIC_MIDNIGHT  # strictly after


# ------------------------------------------------------------- 5xx / 400 / 401 / 403


def test_5xx_changes_no_state(tmp_path: Path) -> None:
    pool, _ = make_pool(tmp_path, [cfg(KEY_A, "only")])
    slot = must_acquire(pool, PRO)
    pool.report(slot, PRO, outcome="5xx", retry_after=None, error_text=None, code=503)
    ts = pool.tier_state(slot, PRO)
    assert ts.state == "healthy" and ts.last_error_code == 503 and ts.consecutive_429 == 0
    assert must_acquire(pool, PRO).index == slot.index


def test_400_aborts_without_rotation_or_state_change(tmp_path: Path) -> None:
    pool, _ = make_pool(tmp_path)
    slot = must_acquire(pool, PRO)
    pool.report(slot, PRO, outcome="400", retry_after=None, error_text="bad request")
    ts = pool.tier_state(slot, PRO)
    assert ts.state == "healthy" and ts.last_error_code == 400
    assert pool.acquire(PRO, exclude=set()) is not None
    assert pool.summary().healthy == 2


@pytest.mark.parametrize("code", [401, 403])
def test_401_403_disable_the_slot_for_that_tier(tmp_path: Path, code: int) -> None:
    pool, clock = make_pool(tmp_path)
    slot = must_acquire(pool, PRO)
    pool.report(slot, PRO, outcome="4xx_fatal", retry_after=None, error_text="denied", code=code)
    ts = pool.tier_state(slot, PRO)
    assert ts.state == "disabled" and ts.last_error_code == code
    clock.advance(days=3)  # disabled never heals by itself
    assert pool.effective_state(slot, PRO) == "disabled"
    assert must_acquire(pool, PRO).index != slot.index
    assert pool.acquire(PRO, exclude={1 - slot.index}) is None
    assert pool.counts(PRO)["disabled"] == 1
    assert pool.summary().disabled == 1


# ---------------------------------------------------------------------- persistence


def test_persist_writes_keypool_json_without_any_key_string(tmp_path: Path) -> None:
    pool, _ = make_pool(tmp_path, [cfg(KEY_A, "proj-a"), cfg(KEY_B, "proj-b", billing=False)])
    slot = must_acquire(pool, PRO)
    pool.report(slot, PRO, outcome="429", retry_after=17, error_text="rate")
    path = tmp_path / "var" / "keypool.json"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    for key in (KEY_A, KEY_B):
        assert key not in text
        assert key[:-4] not in text  # not even the prefix
    data = json.loads(text)
    assert data["version"] == 1 and "saved_at" in data
    assert [s["project"] for s in data["slots"]] == ["proj-a", "proj-b"]
    assert [s["key_last4"] for s in data["slots"]] == [KEY_A[-4:], KEY_B[-4:]]
    assert set(data["slots"][0]["tiers"]) == {"pro", "fast"}
    pro = data["slots"][slot.index]["tiers"]["pro"]
    assert pro["state"] == "cooling" and pro["consecutive_429"] == 1
    assert set(pro) == {
        "state", "cooldown_until", "consecutive_429", "rpm_last_minute", "rpd_count",
        "rpd_reset_at", "last_error_code", "last_used_at",
    }  # fmt: skip
    assert not list((tmp_path / "var").glob(".keypool.json.*.tmp"))  # atomic replace


def test_restore_reloads_state_after_a_restart(tmp_path: Path) -> None:
    pool, clock = make_pool(tmp_path)
    a = must_acquire(pool, PRO)
    pool.report(a, PRO, outcome="429", retry_after=600, error_text="rate")
    b = must_acquire(pool, PRO)
    pool.report(b, PRO, outcome="429", retry_after=5, error_text="quota per day")
    pool.report(b, FAST, outcome="ok", retry_after=None, error_text=None)
    clock.advance(seconds=30)
    restarted = KeyPool(two_slots(), tmp_path / "var", clock)
    assert restarted.effective_state(a, PRO) == "cooling"
    assert restarted.tier_state(a, PRO).cooldown_until == NOW + timedelta(seconds=600)
    assert restarted.effective_state(b, PRO) == "rpd_exhausted"
    assert restarted.tier_state(b, FAST).rpd_count == 1
    assert restarted.acquire(PRO) is None  # the burned quota survived the restart


def test_restore_matches_by_project_and_key_last4(tmp_path: Path) -> None:
    pool, clock = make_pool(tmp_path)
    a = must_acquire(pool, PRO)
    pool.report(a, PRO, outcome="4xx_fatal", retry_after=None, error_text=None, code=403)
    rotated = [cfg(KEY_C, "proj-a"), cfg(KEY_B, "proj-b")]  # same project, new key → fresh
    restarted = KeyPool(rotated, tmp_path / "var", clock)
    assert restarted.effective_state(0, PRO) == "healthy"
    renamed = [cfg(KEY_A, "proj-renamed"), cfg(KEY_B, "proj-b")]  # same key, new label → fresh
    assert KeyPool(renamed, tmp_path / "var", clock).effective_state(0, PRO) == "healthy"
    assert KeyPool(two_slots(), tmp_path / "var", clock).effective_state(0, PRO) == "disabled"


def test_restore_heals_an_rpd_exhausted_slot_whose_reset_passed(tmp_path: Path) -> None:
    pool, clock = make_pool(tmp_path, [cfg(KEY_A, "only")])
    slot = must_acquire(pool, PRO)
    pool.report(slot, PRO, outcome="429", retry_after=None, error_text="per day")
    clock.now = PACIFIC_MIDNIGHT + timedelta(hours=1)
    restarted = KeyPool([cfg(KEY_A, "only")], tmp_path / "var", clock)
    ts = restarted.tier_state(slot, PRO)
    assert restarted.effective_state(slot, PRO) == "healthy"
    assert ts.rpd_count == 0 and ts.rpd_reset_at > clock.now


def test_restore_ignores_corrupt_or_foreign_files(tmp_path: Path) -> None:
    var = tmp_path / "var"
    var.mkdir()
    (var / "keypool.json").write_text("{not json", encoding="utf-8")
    assert KeyPool(two_slots(), var, FakeClock()).summary().healthy == 2
    (var / "keypool.json").write_text(json.dumps({"version": 99, "slots": []}), encoding="utf-8")
    assert KeyPool(two_slots(), var, FakeClock()).summary().healthy == 2


# ------------------------------------------------------------- snapshot and summary


def test_snapshot_matches_admin_contract(tmp_path: Path) -> None:
    pool, _ = make_pool(tmp_path, [cfg(KEY_A, "proxyhealth-prod-a"), cfg(KEY_B, "b", False)])
    slot = must_acquire(pool, PRO)
    pool.report(slot, PRO, outcome="429", retry_after=480, error_text="rate")
    snap = pool.snapshot()
    assert isinstance(snap, AdminKeysResponse)
    assert snap.data_use_tier is DataUseTier.mixed
    first = snap.slots[slot.index]
    assert first.key_last4 == KEY_A[-4:] and first.project == "proxyhealth-prod-a"
    assert first.tiers["pro"].state == "cooling"
    assert first.tiers["pro"].cooldown_until == NOW + timedelta(seconds=480)
    assert first.tiers["pro"].rpd_reset_at == PACIFIC_MIDNIGHT
    assert first.tiers["fast"].state == "healthy"
    dumped = snap.model_dump_json()
    assert KEY_A not in dumped and KEY_B not in dumped


def test_summary_reports_slot_level_worst_state(tmp_path: Path) -> None:
    pool, _ = make_pool(tmp_path, [cfg(KEY_A, "a"), cfg(KEY_B, "b"), cfg(KEY_C, "c")])
    pool.report(pool.slot(0), PRO, outcome="429", retry_after=30, error_text="x")
    pool.report(
        pool.slot(1), FAST, outcome="4xx_fatal", retry_after=None, error_text=None, code=401
    )
    summary = pool.summary()
    assert (summary.total, summary.healthy, summary.cooling, summary.disabled) == (3, 1, 1, 1)
    assert summary.rpd_exhausted == 0
    assert pool.data_use_tier() is DataUseTier.paid
