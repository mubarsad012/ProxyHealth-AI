"""``GET /v1/demo/fixtures`` and page PNGs (API_CONTRACT §3.13)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from proxyhealth_api.contracts.demo import DemoFixture
from proxyhealth_api.contracts.enums import ErrorCode
from proxyhealth_api.demo.fixtures import FixtureStore
from proxyhealth_api.deps import get_fixtures
from proxyhealth_api.errors import ApiError, error_responses

router = APIRouter(prefix="/v1/demo", tags=["demo"])

PNG_RESPONSE = {
    "description": "Synthetic sample page watermarked SAMPLE",
    "content": {"image/png": {"schema": {"type": "string", "format": "binary"}}},
}


@router.get("/fixtures", response_model=list[DemoFixture])
async def list_fixtures(
    fixtures: Annotated[FixtureStore, Depends(get_fixtures)],
) -> list[DemoFixture]:
    return fixtures.list()


@router.get(
    "/fixtures/{id}/pages/{n}",
    response_class=Response,
    responses={200: PNG_RESPONSE, **error_responses(404)},
)
async def fixture_page(
    id: str, n: int, fixtures: Annotated[FixtureStore, Depends(get_fixtures)]
) -> Response:
    fixture = fixtures.get(id)
    if fixture is None:
        raise ApiError(ErrorCode.not_found, 404, f"No fixture with id {id!r}.")
    try:
        png = fixture.page_png(n)
    except KeyError as exc:
        raise ApiError(ErrorCode.not_found, 404, f"Fixture {id!r} has no page {n}.") from exc
    return Response(content=png, media_type="image/png")
