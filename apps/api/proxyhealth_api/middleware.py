"""Pure ASGI middlewares plus the consent + tier gate dependency (BUILD_PLAN §4.1, §5.0).

Middlewares: request id + ``X-Contract-Version``/``X-Data-Use-Tier`` headers + optional
``X-App-Token`` check, body-size limit (Content-Length only on day 0), content-free access log,
CORS. The gate is a FastAPI dependency because it needs the JSON body (``demo_sample_id``).
"""

import time
import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import Headers, MutableHeaders

from proxyhealth_api.contracts.enums import DataUseTier, ErrorCode
from proxyhealth_api.deps import get_settings
from proxyhealth_api.errors import ApiError, error_response
from proxyhealth_api.logging_ import log_event
from proxyhealth_api.settings import CONTRACT_VERSION, Settings

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_RID_MAX = 64


def _clean_request_id(raw: str | None) -> str:
    if raw and len(raw) <= _RID_MAX and raw.isprintable() and " " not in raw:
        return raw
    return str(uuid.uuid4())


class RequestContextMiddleware:
    """Request id, contract/tier headers, ``X-App-Token`` enforcement, content-free access log."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        request_id = _clean_request_id(headers.get("x-request-id"))
        scope.setdefault("state", {})["request_id"] = request_id
        tier: DataUseTier = self.settings.data_use_tier
        started = time.perf_counter()
        status_holder = {"status": 0}

        expected = self.settings.app_token.get_secret_value()
        if expected and headers.get("x-app-token") != expected:
            response = error_response(
                request_id=request_id,
                code=ErrorCode.unauthorized,
                status=401,
                message="Missing or invalid X-App-Token.",
                extra_headers={"X-Data-Use-Tier": tier.value},
            )
            await response(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = int(message["status"])
                out = MutableHeaders(scope=message)
                if "x-request-id" not in out:
                    out["X-Request-Id"] = request_id
                if "x-contract-version" not in out:
                    out["X-Contract-Version"] = str(CONTRACT_VERSION)
                if "x-data-use-tier" not in out:
                    out["X-Data-Use-Tier"] = tier.value
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            log_event(
                request_id=request_id,
                route=scope.get("path", ""),
                status=status_holder["status"],
                latency_ms=int((time.perf_counter() - started) * 1000),
                data_use_tier=tier,
            )


class BodyLimitMiddleware:
    """413 when the declared ``Content-Length`` exceeds ``MAX_REQUEST_BYTES`` (WP1 streams)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            declared = Headers(scope=scope).get("content-length")
            if declared and declared.isdigit() and int(declared) > self.max_bytes:
                rid = str(scope.get("state", {}).get("request_id") or uuid.uuid4())
                response = error_response(
                    request_id=rid,
                    code=ErrorCode.payload_too_large,
                    status=413,
                    message="Request body exceeds limits.max_request_bytes.",
                    details={"max_request_bytes": self.max_bytes},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def install_middlewares(app: FastAPI, settings: Settings) -> None:
    """Order (outermost first): request context → body limit → CORS."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=[
            "Content-Type", "Accept-Language", "X-Consent-Version", "X-Install-Id",
            "X-Request-Id", "X-App-Token", "X-Admin-Token", "If-None-Match",
        ],
        expose_headers=[
            "X-Request-Id", "X-Data-Use-Tier", "X-Contract-Version", "Retry-After", "ETag",
        ],
    )  # fmt: skip
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(RequestContextMiddleware, settings=settings)


async def _demo_sample_id(request: Request) -> str | None:
    try:
        body = await request.json()
    except Exception:
        return None
    if isinstance(body, dict):
        value = body.get("demo_sample_id")
        if isinstance(value, str) and value:
            return value
    return None


async def consent_and_tier_gate(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> None:
    """428 without a current ``X-Consent-Version``; 403 on unpaid/mixed tiers (D-01)."""
    demo_id = await _demo_sample_id(request)
    if demo_id is not None:
        return
    consent = request.headers.get("x-consent-version")
    if not consent or consent < settings.consent_version:
        raise ApiError(
            ErrorCode.consent_required,
            428,
            "X-Consent-Version is missing or older than the current consent version.",
            details={"consent_version": settings.consent_version},
        )
    tier = settings.data_use_tier
    if tier in (DataUseTier.unpaid, DataUseTier.mixed) and not settings.allow_unpaid_real_documents:
        raise ApiError(
            ErrorCode.unpaid_tier_real_documents_disabled,
            403,
            "Real documents are disabled on the unpaid/mixed tier; use a demo_sample_id.",
            details={"data_use_tier": tier.value},
        )
