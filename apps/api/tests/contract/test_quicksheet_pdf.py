"""``POST /v1/quicksheet/pdf`` contract (API_CONTRACT §3.11; BUILD_PLAN §5.4 step 5)."""

from __future__ import annotations

import httpx
import pypdfium2 as pdfium

from proxyhealth_api.contracts.errors import ErrorResponse
from tests.unit._fixtures_wp3 import DARI_EXAMPLE, ENGLISH_EXAMPLE


async def test_dari_example_returns_pdf_attachment(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/quicksheet/pdf", json=DARI_EXAMPLE)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == 'attachment; filename="proxyhealth-quick-sheet.pdf"'
    assert r.content.startswith(b"%PDF")
    assert len(r.content) <= 200 * 1024
    assert b"NotoNaskhArabic" in r.content
    assert len(pdfium.PdfDocument(r.content)) == 1


async def test_english_example_drops_unknown_phone(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/quicksheet/pdf", json=ENGLISH_EXAMPLE)
    assert r.status_code == 200
    text = pdfium.PdfDocument(r.content)[0].get_textpage().get_text_range()
    assert "211" in text
    assert "555" not in text


async def test_invalid_request_is_400(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/quicksheet/pdf", json={**ENGLISH_EXAMPLE, "direction": "up"})
    assert r.status_code == 400
    assert ErrorResponse.model_validate(r.json()).error.code == "invalid_request"
    too_many = [{"heading": "h", "heading_en": "h", "lines": ["x"]}] * 9
    r = await client.post("/v1/quicksheet/pdf", json={**ENGLISH_EXAMPLE, "sections": too_many})
    assert r.status_code == 400
