"""PDF pages in memory with pypdfium2 (D-21; API_CONTRACT §3.5 ``page_thumbnails``).

Rasterises pages to PNG bytes held in memory so the client can draw crops from
``original_text[].blocks[].bbox``; nothing is written to disk and no path is ever opened.
"""

from __future__ import annotations

import base64
import io
from collections.abc import Sequence

import pypdfium2 as pdfium

from proxyhealth_api.contracts.analysis import PageThumbnail
from proxyhealth_api.contracts.enums import ErrorCode
from proxyhealth_api.errors import ApiError

THUMBNAIL_LONGEST_EDGE = 1200
POINTS_PER_INCH = 72.0


def _open(data: bytes) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(data)
    except Exception as exc:
        raise ApiError(ErrorCode.invalid_request, 400, "The PDF could not be opened.") from exc


def page_count(data: bytes) -> int:
    """Number of pages in the PDF bytes (``400 invalid_request`` when unreadable)."""
    doc = _open(data)
    try:
        return len(doc)
    finally:
        doc.close()


def page_sizes(data: bytes, *, longest_edge: int = THUMBNAIL_LONGEST_EDGE) -> list[tuple[int, int]]:
    """``(width, height)`` in pixels of every page **as the thumbnails would be rendered**.

    These are the ``PageText.width/height`` values that make ``bbox`` crops line up with the
    thumbnails ``rasterize`` produces at the same ``longest_edge``.
    """
    doc = _open(data)
    try:
        sizes: list[tuple[int, int]] = []
        for index in range(len(doc)):
            w_pt, h_pt = doc.get_page_size(index)
            scale = _scale_for(w_pt, h_pt, longest_edge)
            sizes.append((max(1, round(w_pt * scale)), max(1, round(h_pt * scale))))
        return sizes
    finally:
        doc.close()


def _scale_for(w_pt: float, h_pt: float, longest_edge: int) -> float:
    longest = max(w_pt, h_pt, 1.0)
    return longest_edge / longest


def rasterize(
    data: bytes,
    *,
    pages: Sequence[int] | None = None,
    longest_edge: int = THUMBNAIL_LONGEST_EDGE,
    max_pages: int = 60,
) -> list[PageThumbnail]:
    """Render pages (1-based; default all, capped at ``max_pages``) to PNG thumbnails in memory.

    The longest edge is ``longest_edge`` px (≤ 1200 per API_CONTRACT §3.5). Returned
    ``PageThumbnail`` objects carry standard base64 PNG bytes plus pixel size.
    """
    doc = _open(data)
    try:
        total = len(doc)
        wanted = list(pages) if pages is not None else list(range(1, total + 1))
        out: list[PageThumbnail] = []
        for number in wanted[:max_pages]:
            if number < 1 or number > total:
                continue
            page = doc[number - 1]
            w_pt, h_pt = page.get_size()
            scale = _scale_for(w_pt, h_pt, longest_edge)
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil()
            if image.mode not in ("RGB", "RGBA", "L"):
                image = image.convert("RGB")
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            out.append(
                PageThumbnail(
                    page=number,
                    mime_type="image/png",
                    data_base64=base64.b64encode(buf.getvalue()).decode("ascii"),
                    width=image.width,
                    height=image.height,
                )
            )
            page.close()
        return out
    finally:
        doc.close()


def render_page_png(data: bytes, page: int, *, longest_edge: int = THUMBNAIL_LONGEST_EDGE) -> bytes:
    """One page as raw PNG bytes (used to build image ``Part``s or to mask a PDF page)."""
    thumbs = rasterize(data, pages=[page], longest_edge=longest_edge, max_pages=1)
    if not thumbs:
        raise ApiError(ErrorCode.invalid_request, 400, f"The PDF has no page {page}.")
    return base64.b64decode(thumbs[0].data_base64)


__all__ = [
    "THUMBNAIL_LONGEST_EDGE",
    "page_count",
    "page_sizes",
    "rasterize",
    "render_page_png",
]
