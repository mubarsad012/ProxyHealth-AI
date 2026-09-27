"""Per-install soft rate limiting (D-08). WP0: install-id hashing plus a no-op dependency."""

import hashlib
import hmac
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request


def install_hash(install_id: str, secret: str) -> str:
    """HMAC-SHA256 of the client's random install id; the only per-device value ever logged."""
    return hmac.new(secret.encode("utf-8"), install_id.encode("utf-8"), hashlib.sha256).hexdigest()


def rate_limit_dependency() -> Callable[[Request], Coroutine[Any, Any, None]]:
    """Return a FastAPI dependency; WP0's does nothing, WP1 wires slowapi behind it."""

    async def _noop(request: Request) -> None:
        return None

    return _noop
