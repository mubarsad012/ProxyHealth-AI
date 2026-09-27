"""Error envelope of every non-2xx response (API_CONTRACT §0.1)."""

from pydantic import BaseModel, Field

from proxyhealth_api.contracts.enums import ErrorCode


class ErrorBody(BaseModel):
    """API_CONTRACT §0.1 — body of the error envelope; never contains user content."""

    code: ErrorCode
    message: str = Field(description="English, for developers.")
    user_message_key: str = Field(description="i18n key, e.g. ``err.quota_exhausted``.")
    retry_after_seconds: int | None = None
    key_exhausted: bool = False
    request_id: str
    details: dict[str, str | int | bool] | None = None


class ErrorResponse(BaseModel):
    """API_CONTRACT §0.1 — ``{"error": ErrorBody}`` envelope."""

    error: ErrorBody


# API_CONTRACT §0.1 — HTTP status per code (the table under "Error envelope").
ERROR_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.invalid_request: 400,
    ErrorCode.too_many_pages: 400,
    ErrorCode.pdf_too_long: 400,
    ErrorCode.unauthorized: 401,
    ErrorCode.unpaid_tier_real_documents_disabled: 403,
    ErrorCode.not_found: 404,
    ErrorCode.pack_version_mismatch: 409,
    ErrorCode.payload_too_large: 413,
    ErrorCode.unsupported_media_type: 415,
    ErrorCode.content_blocked: 422,
    ErrorCode.language_unresolved: 422,
    ErrorCode.consent_required: 428,
    ErrorCode.rate_limited: 429,
    ErrorCode.quota_exhausted: 429,
    ErrorCode.internal: 500,
    ErrorCode.model_output_invalid: 502,
    ErrorCode.provider_not_configured: 503,
    ErrorCode.upstream_unavailable: 503,
}
