"""``GET /v1/admin/keys`` (API_CONTRACT §3.14). Always mounted; 404 while ``ADMIN_TOKEN`` unset."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from proxyhealth_api.ai.keypool import KeyPool
from proxyhealth_api.contracts.admin import AdminKeysResponse
from proxyhealth_api.contracts.enums import ErrorCode
from proxyhealth_api.deps import get_keypool, get_settings
from proxyhealth_api.errors import ApiError, error_responses
from proxyhealth_api.settings import Settings

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/keys", response_model=AdminKeysResponse, responses=error_responses(401, 404))
async def admin_keys(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    keypool: Annotated[KeyPool | None, Depends(get_keypool)],
) -> AdminKeysResponse:
    expected = settings.admin_token.get_secret_value()
    if not expected:
        raise ApiError(ErrorCode.not_found, 404, "Admin endpoint is disabled (ADMIN_TOKEN unset).")
    given = request.headers.get("x-admin-token", "")
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise ApiError(ErrorCode.unauthorized, 401, "Missing or invalid X-Admin-Token.")
    if keypool is None:
        return AdminKeysResponse(data_use_tier=settings.data_use_tier, slots=[])
    return keypool.snapshot()
