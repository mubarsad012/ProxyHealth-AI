"""``POST /v1/quicksheet/pdf`` (API_CONTRACT §3.11). Returns PDF bytes; nothing is stored."""

from fastapi import APIRouter
from fastapi.responses import Response

from proxyhealth_api.contracts.quicksheet import QuickSheetRequest
from proxyhealth_api.errors import error_responses
from proxyhealth_api.quicksheet.render import render

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
async def quicksheet_pdf(req: QuickSheetRequest) -> Response:
    return Response(
        content=render(req),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="proxyhealth-quick-sheet.pdf"'},
    )
