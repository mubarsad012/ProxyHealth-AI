"""``ApiError`` and the exception handlers that emit the §0.1 ``ErrorResponse`` envelope."""

import importlib
import pkgutil
import uuid
from collections.abc import Mapping, Sequence
from functools import cache
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from proxyhealth_api import contracts
from proxyhealth_api.contracts.enums import ErrorCode
from proxyhealth_api.contracts.errors import ERROR_HTTP_STATUS, ErrorBody, ErrorResponse
from proxyhealth_api.logging_ import log_event
from proxyhealth_api.settings import CONTRACT_VERSION

Details = dict[str, str | int | bool]

DEFAULT_RETRY_AFTER_S = 30  # every 429/503 carries Retry-After, even when the raiser gave none
_PARAM_LOCS = frozenset({"query", "header", "path", "cookie"})
_REDACTED = "<extra>"


class ApiError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        status: int,
        message: str,
        *,
        user_message_key: str | None = None,
        retry_after: int | None = None,
        key_exhausted: bool = False,
        details: Details | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message
        self.user_message_key = user_message_key or f"err.{code.value}"
        self.retry_after = retry_after
        self.key_exhausted = key_exhausted
        self.details = details


def route_of(request: Request) -> str:
    """The matched route template (never a raw path with ids or typed names) for logging."""
    path = getattr(request.scope.get("route"), "path", None)
    return path if isinstance(path, str) else "unmatched"


def request_id_of(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    if isinstance(rid, str) and rid:
        return rid
    return str(uuid.uuid4())


def error_response(
    *,
    request_id: str,
    code: ErrorCode,
    status: int,
    message: str,
    user_message_key: str | None = None,
    retry_after: int | None = None,
    key_exhausted: bool = False,
    details: Details | None = None,
    extra_headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    if status in (429, 503) and retry_after is None:
        retry_after = DEFAULT_RETRY_AFTER_S  # body mirrors the header (API_CONTRACT §0.1)
    body = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            user_message_key=user_message_key or f"err.{code.value}",
            retry_after_seconds=retry_after,
            key_exhausted=key_exhausted,
            request_id=request_id,
            details=details,
        )
    )
    headers: dict[str, str] = {
        "X-Request-Id": request_id,
        "X-Contract-Version": str(CONTRACT_VERSION),
    }
    if extra_headers:
        headers.update(extra_headers)
    if status in (429, 503) and retry_after is not None:  # always set for 429/503 (above)
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"), headers=headers)


def internal_error_response(
    request_id: str, extra_headers: Mapping[str, str] | None = None
) -> JSONResponse:
    """The fixed, content-free ``500 internal`` envelope (never the exception's text)."""
    return error_response(
        request_id=request_id,
        code=ErrorCode.internal,
        status=ERROR_HTTP_STATUS[ErrorCode.internal],
        message="Unexpected server error.",
        extra_headers=extra_headers,
    )


@cache
def _declared_field_names() -> frozenset[str]:
    """Every field name and alias of every contract model: the only body keys we echo back."""
    names: set[str] = set()
    for info in pkgutil.iter_modules(contracts.__path__):
        module = importlib.import_module(f"{contracts.__name__}.{info.name}")
        for obj in vars(module).values():
            if isinstance(obj, type) and issubclass(obj, BaseModel):
                for name, field in obj.model_fields.items():
                    names.add(name)
                    if field.alias:
                        names.add(field.alias)
    return frozenset(names)


def _safe_loc(loc: Sequence[Any]) -> str:
    """A validation ``loc`` with client-chosen keys replaced by ``<extra>`` (API_CONTRACT §0.1).

    Query/header/path/cookie locations only ever name declared parameters. In a body location,
    indexes and declared field names are kept; any other key (an unknown field, a dict key, a
    union-member label) was typed by the client or is noise, so it is never echoed.
    """
    if not loc:
        return ""
    root, rest = str(loc[0]), loc[1:]
    if root in _PARAM_LOCS:
        return ".".join([root, *(str(p) for p in rest)])
    known = _declared_field_names()
    parts = [root]
    for part in rest:
        keep = isinstance(part, int) or (isinstance(part, str) and part in known)
        parts.append(str(part) if keep else _REDACTED)
    return ".".join(parts)


def _is_disallowed_mime(error: Mapping[str, Any]) -> bool:
    """A body ``mime_type`` outside the ``PageMimeType`` allow-list (a Literal mismatch)."""
    loc = tuple(error.get("loc", ()))
    return (
        error.get("type") == "literal_error"
        and len(loc) > 1
        and loc[0] == "body"
        and loc[-1] == "mime_type"
    )


# Starlette HTTP errors that are not already ``ApiError`` (404 on unknown paths, 405, ...).
_STATUS_TO_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.invalid_request,
    401: ErrorCode.unauthorized,
    404: ErrorCode.not_found,
    413: ErrorCode.payload_too_large,
    415: ErrorCode.unsupported_media_type,
    428: ErrorCode.consent_required,
    429: ErrorCode.rate_limited,
    500: ErrorCode.internal,
    503: ErrorCode.upstream_unavailable,
}


def install_handlers(app: FastAPI) -> None:
    tier_header = {"X-Data-Use-Tier": app.state.settings.data_use_tier.value}

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        rid = request_id_of(request)
        log_event(request_id=rid, route=route_of(request), status=exc.status, error_code=exc.code)
        return error_response(
            request_id=rid,
            code=exc.code,
            status=exc.status,
            message=exc.message,
            user_message_key=exc.user_message_key,
            retry_after=exc.retry_after,
            key_exhausted=exc.key_exhausted,
            details=exc.details,
            extra_headers=tier_header,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        rid = request_id_of(request)
        errors = exc.errors()
        locs = sorted({_safe_loc(e.get("loc", ())) for e in errors})
        if any(_is_disallowed_mime(e) for e in errors):  # API_CONTRACT §0.1: 415 for MIME
            return error_response(
                request_id=rid,
                code=ErrorCode.unsupported_media_type,
                status=415,
                message="Declared mime_type is not in the allow-list at: " + ", ".join(locs[:10]),
                extra_headers=tier_header,
            )
        return error_response(
            request_id=rid,
            code=ErrorCode.invalid_request,
            status=400,
            message="Request validation failed at: " + ", ".join(locs[:10]),
            details={"error_count": len(exc.errors())},
            extra_headers=tier_header,
        )

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException) -> JSONResponse:
        rid = request_id_of(request)
        code = _STATUS_TO_CODE.get(exc.status_code)
        if code is None:
            code = ErrorCode.internal if exc.status_code >= 500 else ErrorCode.invalid_request
        detail = exc.detail if isinstance(exc.detail, str) else code.value.replace("_", " ")
        return error_response(
            request_id=rid,
            code=code,
            status=exc.status_code,
            message=detail,
            extra_headers=tier_header,
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Backstop only: ``middleware.UnhandledErrorMiddleware`` answers every exception raised
        # inside the stack, so this runs just for a failure in the outer middlewares themselves.
        # Starlette re-raises after it; ``logging_.ContentFreeFilter`` keeps the traceback out.
        rid = request_id_of(request)
        log_event(request_id=rid, route=route_of(request), status=500, error_code="internal")
        return internal_error_response(rid, tier_header)


def error_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """``responses={status: {"model": ErrorResponse}}`` for a route (API_CONTRACT §5)."""
    return {status: {"model": ErrorResponse} for status in statuses}
