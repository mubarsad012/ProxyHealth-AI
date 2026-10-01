"""``ratelimit.py`` (D-08): HMAC install hash with a daily salt, IP classes, token buckets.

The IP-class buckets apply to every request ("also"), so a client that rotates ``X-Install-Id``
never escapes them; a rejected request consumes nothing.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from proxyhealth_api.errors import ApiError
from proxyhealth_api.ratelimit import (
    RateLimiter,
    client_address,
    daily_salt,
    install_hash,
    ip_class,
)
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


def test_ip_class_normalises_spellings() -> None:
    # One network, several spellings: none may open a fresh bucket.
    assert ip_class("2001:db8::1") == ip_class("2001:0db8:0000::2") == "v6:2001:db8:0"
    assert ip_class("[2001:db8:1234::9]") == "v6:2001:db8:1234"
    assert ip_class("::ffff:203.0.113.9") == ip_class("203.0.113.200") == "v4:203.0.113"
    assert ip_class("testclient") == "v4:testclient"  # unparseable: the old coarse split


def test_per_install_hour_bucket(tmp_path: Path) -> None:
    limiter = RateLimiter(make_settings(tmp_path, rate_limit_analyze_per_hour=2))
    ihash = limiter.check(install_id="abc", client_host="10.0.0.1")
    assert ihash is not None and ihash == limiter.check(install_id="abc", client_host="10.0.0.1")
    with pytest.raises(ApiError) as exc:
        limiter.check(install_id="abc", client_host="10.0.0.1")
    err = exc.value
    assert err.status == 429 and err.code == "rate_limited" and err.key_exhausted is False
    assert err.retry_after is not None and err.retry_after >= 1
    assert err.details == {"window": "hour", "limit": 2, "bucket": "install"}
    assert limiter.check(install_id="other", client_host="10.0.0.1") is not None


def test_per_ip_class_bucket_without_install_id(tmp_path: Path) -> None:
    limiter = RateLimiter(make_settings(tmp_path, rate_limit_ip_per_minute=1))
    assert limiter.check(install_id=None, client_host="10.0.0.1") is None
    with pytest.raises(ApiError):
        limiter.check(install_id="  ", client_host="10.0.0.2")  # same /24 class
    assert limiter.check(install_id=None, client_host="10.0.1.1") is None
    limiter.reset()
    assert limiter.check(install_id=None, client_host="10.0.0.1") is None


def test_rotating_install_ids_still_hit_the_ip_class_bucket(tmp_path: Path) -> None:
    """Regression: a fresh X-Install-Id per request used to skip every bucket (ratelimit.py:81)."""
    limiter = RateLimiter(make_settings(tmp_path, rate_limit_ip_per_minute=3))
    for i in range(3):
        assert limiter.check(install_id=f"rot-{i}", client_host="198.51.100.7") is not None
    with pytest.raises(ApiError) as exc:
        limiter.check(install_id="rot-fresh", client_host="198.51.100.99")  # same /24
    assert exc.value.status == 429 and exc.value.key_exhausted is False
    assert exc.value.details == {"window": "minute", "limit": 3, "bucket": "ip_class"}
    # the block holds for a fresh id too, and for no id; another class is unaffected
    with pytest.raises(ApiError):
        limiter.check(install_id=None, client_host="198.51.100.1")
    assert limiter.check(install_id="rot-fresh", client_host="198.51.101.7") is not None


def test_daily_ip_class_cap(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, rate_limit_ip_per_minute=100, rate_limit_ip_per_day=2)
    limiter = RateLimiter(settings)
    limiter.check(install_id="a", client_host="192.0.2.1")
    limiter.check(install_id="b", client_host="192.0.2.2")
    with pytest.raises(ApiError) as exc:
        limiter.check(install_id="c", client_host="192.0.2.3")
    assert exc.value.details == {"window": "day", "limit": 2, "bucket": "ip_class"}
    assert exc.value.retry_after is not None and exc.value.retry_after > 3600


def test_rejected_request_consumes_no_bucket(tmp_path: Path) -> None:
    limiter = RateLimiter(make_settings(tmp_path, rate_limit_ip_per_minute=1))
    ihash = limiter.check(install_id="dev", client_host="10.9.8.7")
    assert ihash is not None
    for _ in range(5):
        with pytest.raises(ApiError):
            limiter.check(install_id="dev", client_host="10.9.8.7")
    _reset, remaining = limiter._limiter.get_window_stats(limiter.per_hour, "install", ihash)
    assert remaining == limiter.per_hour.amount - 1  # only the admitted request counted
    for n in range(20):  # rejected fresh ids leave no key behind
        with pytest.raises(ApiError):
            limiter.check(install_id=f"fresh-{n}", client_host="10.9.8.7")
    fresh = limiter.hash_for("fresh-0")
    assert limiter._limiter.get_window_stats(limiter.per_day, "install", fresh)[1] == (
        limiter.per_day.amount
    )


def test_client_address_trusts_only_the_proxy_appended_entry() -> None:
    xff = ["9.9.9.9, 203.0.113.5"]  # client-supplied 9.9.9.9, then what the proxy saw
    assert client_address("169.254.1.1", xff, 0) == "169.254.1.1"  # hops 0: the socket peer
    assert client_address("169.254.1.1", xff, 1) == "203.0.113.5"
    assert client_address("169.254.1.1", xff, 2) == "9.9.9.9"
    assert client_address("169.254.1.1", ["203.0.113.5"], 2) == "203.0.113.5"  # short chain
    assert client_address("169.254.1.1", [], 1) == "169.254.1.1"  # no header: the peer
    assert client_address("169.254.1.1", ["evil, not-an-ip"], 1) == "169.254.1.1"
    assert client_address(None, ["1.1.1.1", "2001:db8::7"], 1) == "2001:db8::7"  # two lines


def test_hash_uses_injected_clock_day(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    limiter = RateLimiter(settings, clock=lambda: datetime(2026, 9, 24, 23, 59, tzinfo=UTC))
    assert limiter.hash_for("abc") == install_hash("abc", "test", date(2026, 9, 24))
