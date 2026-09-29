"""``POST /v1/quicksheet/pdf`` (API_CONTRACT §3.11). Returns PDF bytes; nothing is stored."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from proxyhealth_api.contracts.quicksheet import QuickSheetRequest
from proxyhealth_api.deps import get_packs, get_resources
from proxyhealth_api.errors import error_responses
from proxyhealth_api.packs.base import BasePack
from proxyhealth_api.quicksheet.render import render
from proxyhealth_api.resources.loader import ResourceRepo

router = APIRouter(prefix="/v1/quicksheet", tags=["quicksheet"])

PDF_RESPONSE = {
    "description": "Text-only PDF, ≤ ~200 KB",
    "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
}


@router.post(
    "/pdf",
    response_class=Response,
    responses={200: PDF_RESPONSE, **error_responses(400, 413)},
)
async def quicksheet_pdf(
    req: QuickSheetRequest,
    repo: Annotated[ResourceRepo, Depends(get_resources)],
    packs: Annotated[BasePack, Depends(get_packs)],
) -> Response:
    """Resources are re-validated against the DB inside ``render`` (RESOURCE_DB §7)."""
    # CPU-bound (reshape, bidi, reportlab): off the event loop so other routes keep serving.
    pdf = await run_in_threadpool(render, req, repo, en_strings=packs.strings)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="proxyhealth-quick-sheet.pdf"'},
    )
