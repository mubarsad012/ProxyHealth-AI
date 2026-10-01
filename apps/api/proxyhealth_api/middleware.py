"""Pure ASGI middlewares plus the consent + tier gate dependency (BUILD_PLAN §4.1).

Order (outermost first): CORS → request context (request id, ``X-Contract-Version`` /
``X-Data-Use-Tier`` headers, optional ``X-App-Token`` check, content-free access log) →
unhandled-error guard → body-size limit. CORS is outermost (ARCHITECTURE §2.1 lists it after the
body limit) so that the 401/413/500 envelopes written by the inner layers still carry CORS
headers and a browser client can read them. The guard turns any unexpected exception into the
content-free ``500 internal`` envelope and never re-raises it, so uvicorn has no traceback (and
no exception text) to print and the access log records the real ``500``.

The body limit answers ``413`` from the declared ``Content-Length`` before any
byte is read, and for bodies without that header it buffers at most ``MAX_REQUEST_BYTES`` and
answers ``413`` the moment the stream passes it — in both cases before JSON parsing.

The consent + tier gate is a FastAPI dependency because it needs the JSON body
(``demo_sample_id``); the rate limit (``ratelimit.py``) is a dependency for the same reason.
WP2's three gated routers attach both. The gate also copies the body's contract field
``client_platform`` (API_CONTRACT §3.5/§3.6) to ``request.state`` for the access log.
"""

import hmac
import re
import time
import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import Headers, MutableHeaders

from proxyhealth_api.contracts.enums import DataUseTier, ErrorCode
from proxyhealth_api.deps import get_settings
from proxyhealth_api.errors import ApiError, error_response, internal_error_response
from proxyhealth_api.logging_ import log_event
from proxyhealth_api.settings import CONTRACT_VERSION, Settings

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_RID_MAX = 64
_PLATFORMS = frozenset({"ios", "android", "web"})
_CONSENT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CORS_ALLOW_HEADERS = [
    "Content-Type", "Accept-Language", "X-Consent-Version", "X-Install-Id", "X-Request-Id",
    "X-App-Token", "X-Admin-Token", "If-None-Match",
]  # fmt: skip
CORS_EXPOSE_HEADERS = [
    "X-Request-Id", "X-Data-Use-Tier", "X-Contract-Version", "Retry-After", "ETag",
]  # fmt: skip


def clean_request_id(raw: str | None) -> str:
    """Echo a sane client id (≤ 64 printable chars, no spaces); otherwise mint a UUID v4."""
    if raw and len(raw) <= _RID_MAX and raw.isprintable() and " " not in raw:
        return raw
    return str(uuid.uuid4())


def _route_template(scope: Scope) -> str:
    """The matched route template (``/v1/resources/{id}``); never a raw path with ids in it."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


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
        request_id = clean_request_id(headers.get("x-request-id"))
        state: dict[str, Any] = scope.setdefault("state", {})
        state["request_id"] = request_id
        tier: DataUseTier = self.settings.data_use_tier
        started = time.perf_counter()
        status_holder = {"status": 0}

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
            expected = self.settings.app_token.get_secret_value()
            if expected and scope.get("method") != "OPTIONS" and not _token_ok(headers, expected):
                response = error_response(
                    request_id=request_id,
                    code=ErrorCode.unauthorized,
                    status=401,
                    message="Missing or invalid X-App-Token.",
                )
                await response(scope, receive, send_wrapper)
                return
            await self.app(scope, receive, send_wrapper)
        finally:
            platform = state.get("client_platform")  # set by consent_and_tier_gate from the body
            log_event(
                request_id=request_id,
                route=_route_template(scope),
                status=status_holder["status"],
                latency_ms=int((time.perf_counter() - started) * 1000),
                data_use_tier=tier,
                install_id_hash=state.get("install_id_hash"),
                client_platform=platform if platform in _PLATFORMS else None,
            )


def _token_ok(headers: Headers, expected: str) -> bool:
    given = headers.get("x-app-token", "")
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


class UnhandledErrorMiddleware:
    """Unexpected exception → ``500 internal`` envelope, logged without content, not re-raised.

    Without it Starlette's ``ServerErrorMiddleware`` (outside every user middleware) sends the
    envelope and then re-raises, uvicorn prints the traceback with the exception message (e.g.
    pydantic's ``input_value='…'``) to its error log (ARCHITECTURE §7 item 1), and the response
    bypasses CORS and the access log's status. If the response had already started, nothing more
    can be sent; the exception is still swallowed and uvicorn closes the connection.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:  # noqa: BLE001 — every exception type, by design
            rid = str(scope.get("state", {}).get("request_id") or uuid.uuid4())
            log_event(
                request_id=rid, route=_route_template(scope), status=500,
                error_code=ErrorCode.internal,
            )  # fmt: skip
            if not started:
                await internal_error_response(rid)(scope, receive, send)


def _too_large(request_id: str, max_bytes: int) -> ASGIApp:
    return error_response(
        request_id=request_id,
        code=ErrorCode.payload_too_large,
        status=413,
        message="Request body exceeds limits.max_request_bytes.",
        details={"max_request_bytes": max_bytes},
    )


class BodyLimitMiddleware:
    """``413 payload_too_large`` before parsing (D-21 caps; API_CONTRACT §0.1).

    * ``Content-Length`` declared and too big → 413 without reading a byte. When it is declared
      and within the cap the server's HTTP layer enforces the framing, so the body passes through.
    * No ``Content-Length`` (chunked) → the body is buffered up to the cap; one byte more → 413
      and the rest is never read. The buffered body is then replayed to the app unchanged.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = str(scope.get("state", {}).get("request_id") or uuid.uuid4())
        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.strip().isdigit():
            if int(declared) > self.max_bytes:
                await _too_large(rid, self.max_bytes)(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return
        if scope.get("method") in ("GET", "HEAD", "OPTIONS", "DELETE"):
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        seen = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break  # client disconnected; let the app see an empty body
            body = message.get("body", b"")
            seen += len(body)
            if seen > self.max_bytes:
                await _too_large(rid, self.max_bytes)(scope, receive, send)
                return
            chunks.append(body)
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def install_middlewares(app: FastAPI, settings: Settings) -> None:
    """Outermost first: CORS → request context → error guard → body limit (prepends)."""
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(RequestContextMiddleware, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=CORS_ALLOW_HEADERS,
        expose_headers=CORS_EXPOSE_HEADERS,
    )


async def _json_object(request: Request) -> dict[str, Any] | None:
    """The request body as a JSON object, or ``None`` (the route's own validation answers 400)."""
    try:
        body = await request.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


def _known_demo_sample_id(request: Request, body: dict[str, Any]) -> str | None:
    """The body's ``demo_sample_id`` when it names a bundled fixture, else ``None``.

    Only an id that exists in ``app.state.fixtures`` exempts a request from the gate: an unknown
    id is treated like no id, so it cannot smuggle real pages past the 428/403 checks.
    """
    value = body.get("demo_sample_id")
    if not isinstance(value, str) or not value.strip():
        return None
    fixtures = getattr(request.app.state, "fixtures", None)
    if fixtures is None or fixtures.get(value) is None:
        return None
    return value


# Routes whose whole body is client material the server never swaps for the fixture on disk:
# chat re-sends the analysis context (original_text, sender, summary, demands) plus the history and
# the typed question, so a demo_sample_id there does not make the content a sample (D-01).
_CLIENT_TEXT_ROUTES = frozenset({"/v1/chat"})
# Free-text fields a demo request can still carry next to the fixture (the troubleshoot goal).
_CLIENT_TEXT_FIELDS = ("user_goal",)


def _carries_client_text(request: Request, body: dict[str, Any]) -> bool:
    """True when a demo request still sends words the user typed (or a client-built analysis) that
    the server does not replace with fixture data from disk — they would reach the model as is."""
    route = getattr(request.scope.get("route"), "path", None) or request.url.path
    if route in _CLIENT_TEXT_ROUTES:
        return True
    return any(
        isinstance(body.get(name), str) and bool(body[name].strip()) for name in _CLIENT_TEXT_FIELDS
    )


def consent_is_current(given: str | None, required: str) -> bool:
    """``X-Consent-Version`` must be a ``YYYY-MM-DD`` date no older than ``CONSENT_VERSION``.

    A non-date ``CONSENT_VERSION`` (operator choice) is compared for exact equality instead.
    """
    if not given:
        return False
    value = given.strip()
    if not _CONSENT_RE.match(required):
        return value == required
    return bool(_CONSENT_RE.match(value)) and value >= required


async def consent_and_tier_gate(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> None:
    """428 without a current ``X-Consent-Version``; 403 on unpaid/mixed tiers (D-01, D-02).

    A request whose ``demo_sample_id`` names a bundled fixture is exempt from both: the server
    loads the fixture from disk, so no user paper is needed. An unknown id gets no exemption.
    On the ``unpaid``/``mixed`` tiers (Google may use and human-review what reaches those keys)
    the exemption also requires that the demo request carries no client text the server keeps:
    ``/v1/chat`` (client analysis context, history, question) and a troubleshoot ``user_goal``
    are gated exactly like a real paper there, so sample questions are answered on paid/demo tiers
    only (or with the dev-only ``ALLOW_UNPAID_REAL_DOCUMENTS`` and a current consent).
    """
    body = await _json_object(request)
    platform = body.get("client_platform") if body is not None else None
    if isinstance(platform, str) and platform in _PLATFORMS:
        request.state.client_platform = platform  # contract field; logged by the access log
    tier = settings.data_use_tier
    unpaid_keys = tier in (DataUseTier.unpaid, DataUseTier.mixed)
    if body is not None and _known_demo_sample_id(request, body) is not None:
        if not (unpaid_keys and _carries_client_text(request, body)):
            return
    if not consent_is_current(request.headers.get("x-consent-version"), settings.consent_version):
        raise ApiError(
            ErrorCode.consent_required,
            428,
            "X-Consent-Version is missing or older than the current consent version.",
            details={"consent_version": settings.consent_version},
        )
    if not unpaid_keys:
        return
    if tier is DataUseTier.mixed:
        for index in settings.unbilled_slot_indexes:  # D-01: warn per request per unbilled slot
            log_event(
                request_id=getattr(request.state, "request_id", None),
                route="gate.mixed_pool_unbilled_slot",
                data_use_tier=tier,
                slot_index=index,
            )
    if not settings.allow_unpaid_real_documents:
        raise ApiError(
            ErrorCode.unpaid_tier_real_documents_disabled,
            403,
            "Real documents and typed text are disabled on the unpaid/mixed tier; use a "
            "demo_sample_id without chat or a user_goal.",
            details={"data_use_tier": tier.value},
        )
