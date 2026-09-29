"""Upload validation (ARCHITECTURE §2 "Upload validation"; D-21).

Decode base64 → sniff magic bytes → compare with the declared MIME → enforce per-page, total
and PDF-page caps → reject mixed images + PDF → count PDF pages in memory with pypdfium2 →
check the inline-bytes budget before any provider call. Nothing here touches disk or logs page
content; error messages name positions and limits only.

Error mapping (API_CONTRACT §0.1):
* bad base64 → ``400 invalid_request``
* unknown or mismatching magic bytes → ``415 unsupported_media_type``
* page/PDF/body/inline caps → ``413 payload_too_large``
* more than ``MAX_PAGES`` images, or images mixed with a PDF → ``400 too_many_pages``
* PDF with more than ``MAX_PDF_PAGES`` pages → ``400 pdf_too_long``
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Sequence
from dataclasses import dataclass

import pypdfium2 as pdfium

from proxyhealth_api.ai.provider import Part
from proxyhealth_api.contracts.common import MaskRect, PageInput, Rotation
from proxyhealth_api.contracts.enums import ErrorCode
from proxyhealth_api.errors import ApiError
from proxyhealth_api.settings import Settings

PDF_MIME = "application/pdf"
HEIF_BRANDS = frozenset(
    {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"heif"}
)
# Declared MIME → sniffed MIMEs that are accepted for it (HEIC/HEIF share one container).
_COMPATIBLE: dict[str, frozenset[str]] = {
    "image/jpeg": frozenset({"image/jpeg"}),
    "image/png": frozenset({"image/png"}),
    "image/webp": frozenset({"image/webp"}),
    "image/heic": frozenset({"image/heic", "image/heif"}),
    "image/heif": frozenset({"image/heic", "image/heif"}),
    PDF_MIME: frozenset({PDF_MIME}),
}


@dataclass(frozen=True)
class DecodedPage:
    """One decoded upload page. ``pdf_pages`` is set only for the PDF."""

    index: int
    mime_type: str
    sniffed_mime: str
    data: bytes
    masks: tuple[MaskRect, ...]
    rotation: Rotation
    pdf_pages: int | None


@dataclass(frozen=True)
class DecodedUpload:
    """All pages of one request after validation."""

    pages: tuple[DecodedPage, ...]
    is_pdf: bool
    total_bytes: int
    page_count: int
    """Images: number of images; PDF: its page count (what ``quality.pages_received`` reports)."""

    def parts(self) -> list[Part]:
        """Media ``Part``s in page order (bytes as uploaded; redaction may replace them)."""
        return [Part.of_bytes(p.data, p.mime_type) for p in self.pages]


def sniff_mime(data: bytes) -> str | None:
    """Return the MIME type from magic bytes, or ``None`` when the bytes match no allowed type."""
    head = data[:16]
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return PDF_MIME
    if len(data) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in HEIF_BRANDS:
            return "image/heic" if brand.startswith(b"he") else "image/heif"
    return None


def pdf_page_count(data: bytes) -> int:
    """Page count of a PDF held in memory (pypdfium2); ``400 invalid_request`` if unreadable."""
    try:
        doc = pdfium.PdfDocument(data)
    except Exception as exc:  # pdfium raises its own error types
        raise ApiError(ErrorCode.invalid_request, 400, "The PDF could not be opened.") from exc
    try:
        return len(doc)
    finally:
        doc.close()


def decode_base64(value: str, position: int) -> bytes:
    """Strict standard-base64 decode of ``pages[position].data_base64`` (``400`` on failure)."""
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ApiError(
            ErrorCode.invalid_request, 400, f"pages[{position}].data_base64 is not base64."
        ) from exc


def decode_pages(pages: Sequence[PageInput], settings: Settings) -> DecodedUpload:
    """Validate and decode every page of an ``AnalyzeRequest``/``TroubleshootRequest``.

    Order of checks follows ARCHITECTURE §2: base64 → magic bytes vs declared MIME → per-page
    cap → mixed/too many pages → PDF page count → total bytes. Pages may be empty only for a demo
    request; callers handle that before calling.
    """
    declared_pdf = [p.mime_type == PDF_MIME for p in pages]
    is_pdf = any(declared_pdf)
    if is_pdf and len(pages) > 1:
        raise ApiError(
            ErrorCode.too_many_pages, 400, "Send photos or one PDF, not both.",
            details={"pages": len(pages)},
        )  # fmt: skip
    if len(pages) > settings.max_pages:
        raise ApiError(
            ErrorCode.too_many_pages, 400, f"At most {settings.max_pages} pages per request.",
            details={"max_pages": settings.max_pages, "pages": len(pages)},
        )  # fmt: skip
    decoded: list[DecodedPage] = []
    total = 0
    for position, page in enumerate(pages):
        data = decode_base64(page.data_base64, position)
        sniffed = sniff_mime(data)
        if sniffed is None or sniffed not in _COMPATIBLE[page.mime_type]:
            raise ApiError(
                ErrorCode.unsupported_media_type, 415,
                f"pages[{position}] is not a {page.mime_type} file.",
                details={"page": position + 1, "declared": page.mime_type},
            )  # fmt: skip
        cap = settings.max_pdf_bytes if sniffed == PDF_MIME else settings.max_page_bytes
        if len(data) > cap:
            raise ApiError(
                ErrorCode.payload_too_large, 413, f"Page {position + 1} exceeds the size limit.",
                details={"max_bytes": cap, "page": position + 1},
            )  # fmt: skip
        pdf_pages: int | None = None
        if sniffed == PDF_MIME:
            pdf_pages = pdf_page_count(data)
            if pdf_pages > settings.max_pdf_pages:
                raise ApiError(
                    ErrorCode.pdf_too_long, 400,
                    f"The PDF has {pdf_pages} pages; the limit is {settings.max_pdf_pages}.",
                    details={"max_pdf_pages": settings.max_pdf_pages, "pages": pdf_pages},
                )  # fmt: skip
            if pdf_pages < 1:
                raise ApiError(ErrorCode.invalid_request, 400, "The PDF has no pages.")
        total += len(data)
        decoded.append(
            DecodedPage(
                index=position + 1, mime_type=page.mime_type, sniffed_mime=sniffed, data=data,
                masks=tuple(page.masks), rotation=page.rotation, pdf_pages=pdf_pages,
            )  # fmt: skip
        )
    if total > settings.max_request_bytes:
        raise ApiError(
            ErrorCode.payload_too_large, 413, "The pages together exceed the size limit.",
            details={"max_bytes": settings.max_request_bytes, "total_bytes": total},
        )  # fmt: skip
    first_pdf = decoded[0].pdf_pages if is_pdf and decoded else None
    page_count = first_pdf if first_pdf else len(decoded)
    return DecodedUpload(
        pages=tuple(decoded), is_pdf=is_pdf, total_bytes=total, page_count=page_count
    )


def inline_bytes(parts: Sequence[Part]) -> int:
    """Total media bytes that would be sent inline to the provider."""
    return sum(len(p.data) for p in parts if p.kind == "bytes" and p.data)


def check_inline_budget(parts: Sequence[Part], settings: Settings) -> None:
    """D-21: refuse (``413``) before the call when inline media exceeds the Gemini inline cap."""
    size = inline_bytes(parts)
    if size > settings.max_upstream_inline_bytes:
        raise ApiError(
            ErrorCode.payload_too_large, 413, "The pages are too large to send together.",
            details={"max_bytes": settings.max_upstream_inline_bytes, "inline_bytes": size},
        )  # fmt: skip


__all__ = [
    "PDF_MIME",
    "DecodedPage",
    "DecodedUpload",
    "check_inline_budget",
    "decode_base64",
    "decode_pages",
    "inline_bytes",
    "pdf_page_count",
    "sniff_mime",
]
