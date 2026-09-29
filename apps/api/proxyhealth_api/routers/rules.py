"""``GET /v1/rules`` (API_CONTRACT §3.10): the deadline rules table from ``RulesRepo`` (WP3)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from proxyhealth_api.contracts.rules import RulesResponse
from proxyhealth_api.deps import get_rules
from proxyhealth_api.resources.rules_repo import RulesRepo

router = APIRouter(prefix="/v1", tags=["resources"])


@router.get("/rules", response_model=RulesResponse)
async def rules(repo: Annotated[RulesRepo, Depends(get_rules)]) -> RulesResponse:
    return RulesResponse(rules_version=repo.version, rules=repo.deadline_rules())
