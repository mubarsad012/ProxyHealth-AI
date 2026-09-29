"""Per-install soft rate limiting (D-08; ARCHITECTURE §2.1 "Rate limiting").

The client may send ``X-Install-Id`` (a random UUID it can rotate). The server never stores or
logs it: it is HMAC-SHA256-hashed with ``INSTALL_HASH_SECRET`` and a daily-rotating salt
(``sha256(secret + YYYY-MM-DD)``) and the hash keys token buckets — ``RATE_LIMIT_ANALYZE_PER_HOUR``
and ``RATE_LIMIT_ANALYZE_PER_DAY`` per install, plus a coarse per-IP-class bucket
(``RATE_LIMIT_IP_PER_MINUTE``) for clients that send no install id. Over limit →
``429 rate_limited`` with ``key_exhausted=false`` and ``Retry-After``.

The buckets are slowapi's engine (the ``limits`` package: ``MovingWindowRateLimiter`` over
``MemoryStorage``) used directly, because the limits come from ``Settings`` at app-build time and
the gated routers (WP2) attach the dependency returned by ``rate_limit_dependency()``.
"""

import hashlib
import hmac
from collections.abc import Callable, Coroutine
from datetime import UTC, date, datetime
from typing import Any

from fastapi import Request
from limits import RateLimitItem, RateLimitItemPerDay, RateLimitItemPerHour, RateLimitItemPerMinute
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from proxyhealth_api.contracts.enums import ErrorCode
from proxyhealth_api.errors import ApiError
from proxyhealth_api.settings import Settings

Clock = Callable[[], datetime]


def daily_salt(secret: str, day: date) -> str:
    """D-08: ``sha256(secret + YYYY-MM-DD)`` — rotates the install hash every UTC day."""
    return hashlib.sha256((secret + day.isoformat()).encode("utf-8")).hexdigest()


def install_hash(install_id: str, secret: str, day: date | None = None) -> str:
    """HMAC-SHA256 of the client's random install id; the only per-device value ever logged."""
    salt = daily_salt(secret, day or datetime.now(UTC).date())
    return hmac.new(salt.encode("utf-8"), install_id.encode("utf-8"), hashlib.sha256).hexdigest()


def ip_class(client_host: str | None) -> str:
    """Coarse network class (``/24`` for IPv4, ``/48`` for IPv6); never the full address."""
    if not client_host:
        return "unknown"
    if ":" in client_host:
        return "v6:" + ":".join(client_host.split(":")[:3])
    return "v4:" + ".".join(client_host.split(".")[:3])


class RateLimiter:
    """Token buckets for the model-calling routes; one per app (``app.state.ratelimiter``)."""

    def __init__(self, settings: Settings, *, clock: Clock | None = None) -> None:
        self.settings = settings
        self._clock: Clock = clock or (lambda: datetime.now(UTC))
        self._storage = MemoryStorage()
        self._limiter = MovingWindowRateLimiter(self._storage)
        self.per_hour: RateLimitItem = RateLimitItemPerHour(settings.rate_limit_analyze_per_hour)
        self.per_day: RateLimitItem = RateLimitItemPerDay(settings.rate_limit_analyze_per_day)
        self.per_minute_ip: RateLimitItem = RateLimitItemPerMinute(
            settings.rate_limit_ip_per_minute
        )

    def hash_for(self, install_id: str) -> str:
        secret = self.settings.install_hash_secret.get_secret_value()
        return install_hash(install_id, secret, self._clock().date())

    def _retry_after(self, item: RateLimitItem, key: str) -> int:
        reset_at, _remaining = self._limiter.get_window_stats(item, key)
        return max(1, int(reset_at - self._clock().timestamp()) + 1)

    def check(self, *, install_id: str | None, client_host: str | None) -> str | None:
        """Consume one request; return the install hash (for logging) or raise ``429``."""
        ihash: str | None = None
        checks: list[tuple[RateLimitItem, str, str]]
        if install_id and install_id.strip():
            ihash = self.hash_for(install_id.strip())
            checks = [(self.per_hour, ihash, "hour"), (self.per_day, ihash, "day")]
        else:
            checks = [(self.per_minute_ip, ip_class(client_host), "minute")]
        for item, key, window in checks:
            if not self._limiter.hit(item, key):
                raise ApiError(
                    ErrorCode.rate_limited,
                    429,
                    f"Too many requests for this {window}; try again later.",
                    retry_after=self._retry_after(item, key),
                    key_exhausted=False,
                    details={"window": window, "limit": item.amount},
                )
        return ihash

    def reset(self) -> None:
        self._storage.reset()


def rate_limit_dependency() -> Callable[[Request], Coroutine[Any, Any, None]]:
    """The FastAPI dependency the gated routers attach as ``Depends(rate_limit_dependency())``."""

    async def _rate_limit(request: Request) -> None:
        limiter: RateLimiter | None = getattr(request.app.state, "ratelimiter", None)
        if limiter is None:
            return None
        client = request.client
        ihash = limiter.check(
            install_id=request.headers.get("x-install-id"),
            client_host=client.host if client else None,
        )
        if ihash is not None:
            request.state.install_id_hash = ihash
        return None

    return _rate_limit
