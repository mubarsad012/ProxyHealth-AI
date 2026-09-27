"""``ApiError`` and the exception handlers that emit the §0.1 ``ErrorResponse`` envelope."""

import uuid
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from proxyhealth_api.contracts.enums import ErrorCode
from proxyhealth_api.contracts.errors import ERROR_HTTP_STATUS, ErrorBody, ErrorResponse
from proxyhealth_api.logging_ import log_event
from proxyhealth_api.settings import CONTRACT_VERSION

Details = dict[str, str | int | bool]


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
    if status in (429, 503):
        headers["Retry-After"] = str(retry_after if retry_after is not None else 30)
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"), headers=headers)


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
        log_event(request_id=rid, route=request.url.path, status=exc.status, error_code=exc.code)
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
        locs = sorted({".".join(str(p) for p in e.get("loc", ())) for e in exc.errors()})
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
        rid = request_id_of(request)
        log_event(request_id=rid, route=request.url.path, status=500, error_code="internal")
        return error_response(
            request_id=rid,
            code=ErrorCode.internal,
            status=ERROR_HTTP_STATUS[ErrorCode.internal],
            message="Unexpected server error.",
            extra_headers=tier_header,
        )


def error_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """``responses={status: {"model": ErrorResponse}}`` for a route (API_CONTRACT §5)."""
    return {status: {"model": ErrorResponse} for status in statuses}
