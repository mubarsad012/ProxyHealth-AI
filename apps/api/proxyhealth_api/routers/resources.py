"""``/v1/resources`` (API_CONTRACT §3.8, §3.9; RESOURCE_DB §7). WP3 bodies over ``ResourceRepo``."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from proxyhealth_api.contracts.common import LanguageTag
from proxyhealth_api.contracts.enums import ErrorCode, ResourceTag
from proxyhealth_api.contracts.resources import (
    Resource,
    ResourceList,
    ResourceMatchRequest,
    ResourceMatchResponse,
)
from proxyhealth_api.deps import get_packs, get_resources
from proxyhealth_api.errors import ApiError, error_responses
from proxyhealth_api.packs.base import BasePack
from proxyhealth_api.resources import matcher
from proxyhealth_api.resources.loader import ResourceRepo

router = APIRouter(prefix="/v1/resources", tags=["resources"])


@router.post("/match", response_model=ResourceMatchResponse, responses=error_responses(400))
async def match_resources(
    req: ResourceMatchRequest,
    repo: Annotated[ResourceRepo, Depends(get_resources)],
    packs: Annotated[BasePack, Depends(get_packs)],
) -> ResourceMatchResponse:
    """Deterministic matcher (RESOURCE_DB §6); 200 always — an empty ``results`` is fine."""
    return matcher.match(req, repo, en_strings=packs.strings)


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
    """Browse the DB: ``tag`` exact; ``state`` keeps national + serving entries; ``q`` substring."""
    items, total = repo.list(
        tag=tag, state=state, language=language, q=q, limit=limit, offset=offset
    )
    return ResourceList(items=items, total=total, resource_db_version=repo.version)


@router.get("/{id}", response_model=Resource, responses=error_responses(404))
async def get_resource(id: str, repo: Annotated[ResourceRepo, Depends(get_resources)]) -> Resource:
    resource = repo.get(id)
    if resource is None:
        raise ApiError(ErrorCode.not_found, 404, f"No resource with id {id!r}.")
    return resource
