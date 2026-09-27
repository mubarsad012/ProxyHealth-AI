"""``/v1/resources`` (API_CONTRACT §3.8, §3.9). WP0 stubs over the empty ``ResourceRepo``."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from proxyhealth_api.contracts.common import LanguageTag
from proxyhealth_api.contracts.enums import DisclaimerKind, ErrorCode, ResourceTag
from proxyhealth_api.contracts.resources import (
    Resource,
    ResourceList,
    ResourceMatchRequest,
    ResourceMatchResponse,
)
from proxyhealth_api.deps import get_resources
from proxyhealth_api.errors import ApiError, error_responses
from proxyhealth_api.resources.loader import ResourceRepo

router = APIRouter(prefix="/v1/resources", tags=["resources"])


@router.post("/match", response_model=ResourceMatchResponse, responses=error_responses(400))
async def match_resources(
    req: ResourceMatchRequest, repo: Annotated[ResourceRepo, Depends(get_resources)]
) -> ResourceMatchResponse:
    return ResourceMatchResponse(
        results=[],
        national_fallbacks=[],
        notes_keys=["notes.no_local_results"],
        disclaimer_kind=DisclaimerKind.general_information,
        resource_db_version=repo.version,
    )


@router.get("", response_model=ResourceList, responses=error_responses(400))
async def list_resources(
    repo: Annotated[ResourceRepo, Depends(get_resources)],
    tag: ResourceTag | None = None,
    state: str | None = None,
    language: LanguageTag | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ResourceList:
    items = repo.all()
    if tag is not None:
        items = [r for r in items if tag in r.tags]
    if q:
        needle = q.casefold()
        items = [r for r in items if needle in r.name.casefold()]
    return ResourceList(
        items=items[offset : offset + limit], total=len(items), resource_db_version=repo.version
    )


@router.get("/{id}", response_model=Resource, responses=error_responses(404))
async def get_resource(id: str, repo: Annotated[ResourceRepo, Depends(get_resources)]) -> Resource:
    resource = repo.get(id)
    if resource is None:
        raise ApiError(ErrorCode.not_found, 404, f"No resource with id {id!r}.")
    return resource
