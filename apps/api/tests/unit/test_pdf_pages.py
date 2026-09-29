"""WP2 — ``analysis/pdf_pages.py``: page counts, thumbnail rasterisation, all in memory."""

from __future__ import annotations

import base64
import builtins
import io
from collections.abc import Iterator
from typing import Any

import pytest
from PIL import Image

from proxyhealth_api.analysis import pdf_pages
from proxyhealth_api.errors import ApiError
from tests.unit._fixtures_wp2 import pdf_bytes

_real_open = builtins.open


@pytest.fixture(autouse=True)
def forbid_disk_writes(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def guarded(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if any(flag in mode for flag in "wax+"):
            raise AssertionError(f"disk write attempted: open({file!r}, {mode!r})")
        return _real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded)
    yield


def test_page_count() -> None:
    assert pdf_pages.page_count(pdf_bytes(pages=4)) == 4
    with pytest.raises(ApiError) as exc:
        pdf_pages.page_count(b"%PDF-1.4 nope")
    assert exc.value.status == 400


def test_rasterize_all_pages_as_png_with_longest_edge() -> None:
    thumbs = pdf_pages.rasterize(pdf_bytes(pages=2, size=(200, 300)), longest_edge=600)
    assert [t.page for t in thumbs] == [1, 2]
    for t in thumbs:
        assert t.mime_type == "image/png"
        raw = base64.b64decode(t.data_base64)
        assert raw.startswith(b"\x89PNG")
        im = Image.open(io.BytesIO(raw))
        assert (im.width, im.height) == (t.width, t.height)
        assert max(t.width, t.height) == 600
        assert t.width == 400 and t.height == 600


def test_rasterize_respects_page_selection_and_cap() -> None:
    data = pdf_bytes(pages=3)
    thumbs = pdf_pages.rasterize(data, pages=[3, 1, 9], longest_edge=100)
    assert [t.page for t in thumbs] == [3, 1]
    assert len(pdf_pages.rasterize(data, longest_edge=100, max_pages=2)) == 2


def test_page_sizes_match_thumbnails() -> None:
    data = pdf_bytes(pages=2, size=(200, 300))
    sizes = pdf_pages.page_sizes(data, longest_edge=600)
    thumbs = pdf_pages.rasterize(data, longest_edge=600)
    assert sizes == [(t.width, t.height) for t in thumbs] == [(400, 600), (400, 600)]


def test_render_page_png() -> None:
    png = pdf_pages.render_page_png(pdf_bytes(pages=1), 1, longest_edge=120)
    assert png.startswith(b"\x89PNG")
    with pytest.raises(ApiError):
        pdf_pages.render_page_png(pdf_bytes(pages=1), 2)
