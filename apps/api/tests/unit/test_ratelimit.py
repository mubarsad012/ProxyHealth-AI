"""``ratelimit.py`` (D-08): HMAC install hash with a daily salt, IP classes, token buckets."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from proxyhealth_api.errors import ApiError
from proxyhealth_api.ratelimit import RateLimiter, daily_salt, install_hash, ip_class
from tests.conftest import make_settings


def test_install_hash_is_hmac_and_rotates_daily() -> None:
    a = install_hash("device-1", "secret", date(2026, 9, 24))
    assert len(a) == 64 and "device-1" not in a
    assert a == install_hash("device-1", "secret", date(2026, 9, 24))
    assert a != install_hash("device-1", "secret", date(2026, 9, 25))  # daily salt
    assert a != install_hash("device-2", "secret", date(2026, 9, 24))
    assert a != install_hash("device-1", "other", date(2026, 9, 24))
    assert daily_salt("s", date(2026, 9, 24)) != daily_salt("s", date(2026, 9, 25))


def test_ip_class_is_coarse() -> None:
    assert ip_class("203.0.113.77") == "v4:203.0.113"
    assert ip_class("2001:db8:1234:5678::1") == "v6:2001:db8:1234"
    assert ip_class(None) == "unknown" and ip_class("") == "unknown"


def test_per_install_hour_bucket(tmp_path: Path) -> None:
    limiter = RateLimiter(make_settings(tmp_path, rate_limit_analyze_per_hour=2))
    ihash = limiter.check(install_id="abc", client_host="10.0.0.1")
    assert ihash is not None and ihash == limiter.check(install_id="abc", client_host="10.0.0.1")
    with pytest.raises(ApiError) as exc:
        limiter.check(install_id="abc", client_host="10.0.0.1")
    err = exc.value
    assert err.status == 429 and err.code == "rate_limited" and err.key_exhausted is False
    assert err.retry_after is not None and err.retry_after >= 1
    assert err.details == {"window": "hour", "limit": 2}
    assert limiter.check(install_id="other", client_host="10.0.0.1") is not None


def test_per_ip_class_bucket_without_install_id(tmp_path: Path) -> None:
    limiter = RateLimiter(make_settings(tmp_path, rate_limit_ip_per_minute=1))
    assert limiter.check(install_id=None, client_host="10.0.0.1") is None
    with pytest.raises(ApiError):
        limiter.check(install_id="  ", client_host="10.0.0.2")  # same /24 class
    assert limiter.check(install_id=None, client_host="10.0.1.1") is None
    limiter.reset()
    assert limiter.check(install_id=None, client_host="10.0.0.1") is None


def test_hash_uses_injected_clock_day(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    limiter = RateLimiter(settings, clock=lambda: datetime(2026, 9, 24, 23, 59, tzinfo=UTC))
    assert limiter.hash_for("abc") == install_hash("abc", "test", date(2026, 9, 24))
