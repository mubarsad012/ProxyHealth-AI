"""Per-install and per-IP-class soft rate limiting (D-08; ARCHITECTURE §2.1 "Rate limiting").

The client may send ``X-Install-Id`` (a random UUID it can rotate). The server never stores or
logs it: it is HMAC-SHA256-hashed with ``INSTALL_HASH_SECRET`` and a daily-rotating salt
(``sha256(secret + YYYY-MM-DD)``) and the hash keys token buckets — ``RATE_LIMIT_ANALYZE_PER_HOUR``
and ``RATE_LIMIT_ANALYZE_PER_DAY`` per install. The coarse per-IP-class buckets
(``RATE_LIMIT_IP_PER_MINUTE`` and ``RATE_LIMIT_IP_PER_DAY``) apply to EVERY request as well —
D-08's "also": the client chooses its install id, so a limit keyed only on that id is no limit (a
fresh random id per request would skip every bucket). Over any limit → ``429 rate_limited`` with
``key_exhausted=false`` and ``Retry-After``. Every bucket is tested before any is hit, so a
rejected request consumes nothing and adds no key to the store.

The rate-limited address is the socket peer or, behind ``TRUSTED_PROXY_HOPS`` proxies that each
append to ``X-Forwarded-For`` (Cloud Run: 1), the entry that many places from the right; entries
further left are client-supplied and never trusted. Only the coarse class is kept (in memory).

The buckets are slowapi's engine (the ``limits`` package: ``MovingWindowRateLimiter`` over
``MemoryStorage``) used directly, because the limits come from ``Settings`` at app-build time and
the gated routers (WP2) attach the dependency returned by ``rate_limit_dependency()``.
"""

import hashlib
import hmac
import ipaddress
from collections.abc import Callable, Coroutine, Sequence
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


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        addr = ipaddress.ip_address(value.strip().strip("[]"))
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    return addr


def ip_class(client_host: str | None) -> str:
    """Coarse network class (``/24`` for IPv4, ``/48`` for IPv6); never the full address.

    A parseable address is normalised first (``2001:db8::1`` and ``2001:0db8:0:0::1`` share a
    class; an IPv4-mapped IPv6 address gets its IPv4 class), so a spelling never opens a bucket.
    """
    if not client_host:
        return "unknown"
    addr = _parse_ip(client_host)
    if isinstance(addr, ipaddress.IPv4Address):
        return "v4:" + ".".join(str(addr).split(".")[:3])
    if isinstance(addr, ipaddress.IPv6Address):
        return "v6:" + ":".join(format(int(h, 16), "x") for h in addr.exploded.split(":")[:3])
    if ":" in client_host:
        return "v6:" + ":".join(client_host.split(":")[:3])
    return "v4:" + ".".join(client_host.split(".")[:3])


def client_address(peer: str | None, forwarded_for: Sequence[str], trusted_hops: int) -> str | None:
    """The address to rate-limit: the socket ``peer``, or the ``X-Forwarded-For`` entry that the
    outermost of ``trusted_hops`` proxies appended (the ``trusted_hops``-th from the right).

    Entries left of it came from the client and are ignored, so sending ``X-Forwarded-For`` never
    lets a client choose its class. A chain shorter than ``trusted_hops`` (every entry was added
    by a trusted proxy) uses its leftmost entry; no chain or an unparseable entry → the peer.
    """
    if trusted_hops <= 0:
        return peer
    entries = [e.strip() for value in forwarded_for for e in value.split(",") if e.strip()]
    if not entries:
        return peer
    candidate = entries[-trusted_hops] if len(entries) >= trusted_hops else entries[0]
    return candidate if _parse_ip(candidate) is not None else peer


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
        self.per_day_ip: RateLimitItem = RateLimitItemPerDay(settings.rate_limit_ip_per_day)

    def hash_for(self, install_id: str) -> str:
        secret = self.settings.install_hash_secret.get_secret_value()
        return install_hash(install_id, secret, self._clock().date())

    def _retry_after(self, item: RateLimitItem, key: tuple[str, str]) -> int:
        reset_at, _remaining = self._limiter.get_window_stats(item, *key)
        return max(1, int(reset_at - self._clock().timestamp()) + 1)

    def check(self, *, install_id: str | None, client_host: str | None) -> str | None:
        """Consume one request; return the install hash (for logging) or raise ``429``.

        The install buckets (when an id is sent) and the IP-class buckets (always) must all have
        room; none is consumed unless every one does.
        """
        ihash: str | None = None
        klass = ("ip", ip_class(client_host))
        checks: list[tuple[RateLimitItem, tuple[str, str], str]] = []
        if install_id and install_id.strip():
            ihash = self.hash_for(install_id.strip())
            key = ("install", ihash)
            checks += [(self.per_hour, key, "hour"), (self.per_day, key, "day")]
        checks += [(self.per_minute_ip, klass, "minute"), (self.per_day_ip, klass, "day")]
        for item, key, window in checks:
            if not self._limiter.test(item, *key):
                bucket = "install" if key[0] == "install" else "ip_class"
                raise ApiError(
                    ErrorCode.rate_limited,
                    429,
                    f"Too many requests for this {window}; try again later.",
                    retry_after=self._retry_after(item, key),
                    key_exhausted=False,
                    details={"window": window, "limit": item.amount, "bucket": bucket},
                )
        for item, key, _window in checks:
            self._limiter.hit(item, *key)
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
        host = client_address(
            client.host if client else None,
            request.headers.getlist("x-forwarded-for"),
            limiter.settings.trusted_proxy_hops,
        )
        ihash = limiter.check(install_id=request.headers.get("x-install-id"), client_host=host)
        if ihash is not None:
            request.state.install_id_hash = ihash
        return None

    return _rate_limit
