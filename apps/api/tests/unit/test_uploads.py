"""WP2 — ``analysis/uploads.py`` (D-21; ARCHITECTURE §2 upload validation)."""

from __future__ import annotations

from pathlib import Path

import pytest

from proxyhealth_api.ai.provider import Part
from proxyhealth_api.analysis import uploads
from proxyhealth_api.contracts.common import PageInput
from proxyhealth_api.contracts.enums import ErrorCode
from proxyhealth_api.errors import ApiError
from tests.unit._fixtures_wp2 import b64, image_bytes, pdf_bytes, settings


def _page(data: bytes, mime: str, **kw: object) -> PageInput:
    return PageInput(mime_type=mime, data_base64=b64(data), **kw)


def test_sniff_mime_recognises_every_allowed_type() -> None:
    assert uploads.sniff_mime(image_bytes("PNG")) == "image/png"
    assert uploads.sniff_mime(image_bytes("JPEG")) == "image/jpeg"
    assert uploads.sniff_mime(image_bytes("WEBP")) == "image/webp"
    assert uploads.sniff_mime(pdf_bytes()) == "application/pdf"
    heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic"
    assert uploads.sniff_mime(heic) == "image/heic"
    assert uploads.sniff_mime(b"\x00\x00\x00\x18ftypmif1" + b"\x00" * 8) == "image/heif"
    assert uploads.sniff_mime(b"GIF89a....") is None
    assert uploads.sniff_mime(b"") is None


def test_declared_mime_must_match_sniffed(tmp_path: Path) -> None:
    s = settings(tmp_path)
    with pytest.raises(ApiError) as exc:
        uploads.decode_pages([_page(image_bytes("PNG"), "image/jpeg")], s)
    assert exc.value.status == 415 and exc.value.code is ErrorCode.unsupported_media_type
    with pytest.raises(ApiError) as exc:
        uploads.decode_pages([_page(b"GIF89a" + b"\x00" * 40, "image/png")], s)
    assert exc.value.status == 415


def test_heic_and_heif_are_interchangeable(tmp_path: Path) -> None:
    s = settings(tmp_path)
    heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 24
    up = uploads.decode_pages([_page(heic, "image/heif")], s)
    assert up.pages[0].sniffed_mime == "image/heic" and up.pages[0].mime_type == "image/heif"


def test_bad_base64_is_400(tmp_path: Path) -> None:
    with pytest.raises(ApiError) as exc:
        bad = PageInput(mime_type="image/png", data_base64="@@@")
        uploads.decode_pages([bad], settings(tmp_path))
    assert exc.value.status == 400 and exc.value.code is ErrorCode.invalid_request


def test_page_over_cap_is_413(tmp_path: Path) -> None:
    s = settings(tmp_path, max_page_bytes=50)
    with pytest.raises(ApiError) as exc:
        uploads.decode_pages([_page(image_bytes("PNG"), "image/png")], s)
    assert exc.value.status == 413 and exc.value.code is ErrorCode.payload_too_large
    assert exc.value.details == {"max_bytes": 50, "page": 1}


def test_total_over_request_cap_is_413(tmp_path: Path) -> None:
    png = image_bytes("PNG")
    s = settings(tmp_path, max_request_bytes=len(png) + 10)
    with pytest.raises(ApiError) as exc:
        uploads.decode_pages([_page(png, "image/png"), _page(png, "image/png")], s)
    assert exc.value.status == 413


def test_mixed_images_and_pdf_is_400_too_many_pages(tmp_path: Path) -> None:
    with pytest.raises(ApiError) as exc:
        uploads.decode_pages(
            [_page(image_bytes("JPEG"), "image/jpeg"), _page(pdf_bytes(), "application/pdf")],
            settings(tmp_path),
        )
    assert exc.value.status == 400 and exc.value.code is ErrorCode.too_many_pages


def test_more_than_max_pages_is_400(tmp_path: Path) -> None:
    s = settings(tmp_path, max_pages=2)
    pages = [_page(image_bytes("PNG"), "image/png") for _ in range(3)]
    with pytest.raises(ApiError) as exc:
        uploads.decode_pages(pages, s)
    assert exc.value.code is ErrorCode.too_many_pages


def test_pdf_page_count_via_pypdfium2(tmp_path: Path) -> None:
    data = pdf_bytes(pages=3)
    assert uploads.pdf_page_count(data) == 3
    up = uploads.decode_pages([_page(data, "application/pdf")], settings(tmp_path))
    assert up.is_pdf and up.page_count == 3 and up.pages[0].pdf_pages == 3


def test_pdf_too_long_is_400(tmp_path: Path) -> None:
    s = settings(tmp_path, max_pdf_pages=2)
    with pytest.raises(ApiError) as exc:
        uploads.decode_pages([_page(pdf_bytes(pages=3), "application/pdf")], s)
    assert exc.value.status == 400 and exc.value.code is ErrorCode.pdf_too_long
    assert exc.value.details == {"max_pdf_pages": 2, "pages": 3}


def test_pdf_uses_pdf_cap_not_page_cap(tmp_path: Path) -> None:
    data = pdf_bytes()
    s = settings(tmp_path, max_page_bytes=10, max_pdf_bytes=len(data) + 1)
    up = uploads.decode_pages([_page(data, "application/pdf")], s)
    assert up.total_bytes == len(data)


def test_corrupt_pdf_is_400(tmp_path: Path) -> None:
    with pytest.raises(ApiError) as exc:
        uploads.decode_pages([_page(b"%PDF-1.7 garbage", "application/pdf")], settings(tmp_path))
    assert exc.value.status == 400 and exc.value.code is ErrorCode.invalid_request


def test_images_decode_in_order_with_masks_and_rotation(tmp_path: Path) -> None:
    pages = [
        _page(image_bytes("PNG"), "image/png", rotation=90),
        _page(
            image_bytes("JPEG"), "image/jpeg",
            masks=[{"x0": 0.1, "y0": 0.1, "x1": 0.5, "y1": 0.5}],
        ),  # fmt: skip
    ]
    up = uploads.decode_pages(pages, settings(tmp_path))
    assert not up.is_pdf and up.page_count == 2
    assert [p.index for p in up.pages] == [1, 2]
    assert up.pages[0].rotation == 90 and len(up.pages[1].masks) == 1
    parts = up.parts()
    assert [p.mime_type for p in parts] == ["image/png", "image/jpeg"]
    assert all(p.kind == "bytes" for p in parts)


def test_inline_budget(tmp_path: Path) -> None:
    parts = [Part.of_text("x"), Part.of_bytes(b"a" * 100, "image/png")]
    assert uploads.inline_bytes(parts) == 100
    uploads.check_inline_budget(parts, settings(tmp_path, max_upstream_inline_bytes=100))
    with pytest.raises(ApiError) as exc:
        uploads.check_inline_budget(parts, settings(tmp_path, max_upstream_inline_bytes=99))
    assert exc.value.status == 413 and exc.value.details == {"max_bytes": 99, "inline_bytes": 100}
