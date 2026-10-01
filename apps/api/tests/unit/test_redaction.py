"""WP2 — ``analysis/redaction.py`` (D-19): black burns, EXIF stripped, rotation, no disk."""

from __future__ import annotations

import builtins
import io
from collections.abc import Iterator
from typing import Any

import pytest
from PIL import Image

from proxyhealth_api.analysis import redaction
from proxyhealth_api.contracts.common import MaskRect
from proxyhealth_api.errors import ApiError

_real_open = builtins.open


@pytest.fixture(autouse=True)
def forbid_disk_writes(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Any ``open`` in a write/append/create mode fails the test (D-19: nothing touches disk)."""

    def guarded(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if any(flag in mode for flag in "wax+"):
            raise AssertionError(f"disk write attempted: open({file!r}, {mode!r})")
        return _real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded)
    yield


def _jpeg_with_exif(size: tuple[int, int] = (40, 20), orientation: int | None = None) -> bytes:
    im = Image.new("RGB", size, "white")
    exif = Image.Exif()
    exif[0x010F] = "TestMaker"
    exif[0x0110] = "TestModel"
    if orientation is not None:
        exif[0x0112] = orientation
    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _png(size: tuple[int, int] = (40, 20)) -> bytes:
    im = Image.new("RGB", size, "white")
    im.putpixel((0, 0), (255, 0, 0))  # marker pixel top-left
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_burned_pixels_are_black_and_others_untouched() -> None:
    mask = MaskRect(x0=0.5, y0=0.5, x1=1.0, y1=1.0)
    out = redaction.redact_image(_png((100, 100)), "image/png", [mask])
    im = Image.open(io.BytesIO(out.data)).convert("RGB")
    assert out.masks_burned == 1 and out.mime_type == "image/png"
    assert im.getpixel((75, 75)) == (0, 0, 0)
    assert im.getpixel((99, 99)) == (0, 0, 0)
    assert im.getpixel((50, 50)) == (0, 0, 0)
    assert im.getpixel((49, 49)) == (255, 255, 255)
    assert im.getpixel((10, 90)) == (255, 255, 255)


def test_exif_is_stripped_and_orientation_applied() -> None:
    src = _jpeg_with_exif((40, 20), orientation=6)  # 6 = rotate 90° CW to display
    assert redaction.has_exif(src)
    out = redaction.redact_image(src, "image/jpeg")
    assert not out.passthrough and out.mime_type == "image/jpeg"
    assert not redaction.has_exif(out.data)
    assert (out.width, out.height) == (20, 40)
    im = Image.open(io.BytesIO(out.data))
    assert not im.getexif() and "exif" not in im.info


def test_exif_stripped_even_without_masks_or_rotation() -> None:
    out = redaction.redact_image(_jpeg_with_exif(), "image/jpeg")
    assert out.masks_burned == 0 and not redaction.has_exif(out.data)


def test_rotation_is_applied_clockwise() -> None:
    out = redaction.redact_image(_png((40, 20)), "image/png", rotation=90)
    assert (out.width, out.height) == (20, 40)
    im = Image.open(io.BytesIO(out.data)).convert("RGB")
    # top-left marker moves to top-right after a 90° clockwise turn
    assert im.getpixel((19, 0)) == (255, 0, 0)
    assert im.getpixel((0, 0)) == (255, 255, 255)


def test_mask_coordinates_are_in_the_rotated_frame() -> None:
    # 40x20 rotated 90° CW → 20x40; a mask over the bottom half burns rows 20..39.
    out = redaction.redact_image(
        _png((40, 20)), "image/png", [MaskRect(x0=0.0, y0=0.5, x1=1.0, y1=1.0)], rotation=90
    )
    im = Image.open(io.BytesIO(out.data)).convert("RGB")
    assert im.getpixel((10, 30)) == (0, 0, 0)
    assert im.getpixel((10, 10)) == (255, 255, 255)


def test_webp_and_png_keep_their_format_and_jpeg_reencodes() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (30, 30), "white").save(buf, format="WEBP")
    mask = MaskRect(x0=0, y0=0, x1=0.5, y1=0.5)
    out = redaction.redact_image(buf.getvalue(), "image/webp", [mask])
    assert out.mime_type == "image/webp" and out.data[:4] == b"RIFF"
    out2 = redaction.redact_image(_jpeg_with_exif(), "image/jpeg")
    assert out2.data[:3] == b"\xff\xd8\xff"


def test_undecodable_bytes_pass_through_without_masks_but_refuse_masks() -> None:
    fake_heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64
    out = redaction.redact_image(fake_heic, "image/heic")
    assert out.passthrough and out.data == fake_heic and out.masks_burned == 0
    with pytest.raises(ApiError) as exc:
        redaction.redact_image(fake_heic, "image/heic", [MaskRect(x0=0, y0=0, x1=0.5, y1=0.5)])
    assert exc.value.status == 400


def test_mask_regions_burns_transcript_bboxes() -> None:
    boxes = [[0.0, 0.0, 0.5, 1.0], [0.1, 0.1], [0.9, 0.9, 0.9, 0.9]]
    out = redaction.mask_regions(_png((100, 50)), "image/png", boxes)
    assert out.masks_burned == 1
    im = Image.open(io.BytesIO(out.data)).convert("RGB")
    assert im.getpixel((10, 10)) == (0, 0, 0) and im.getpixel((80, 10)) == (255, 255, 255)


def test_degenerate_or_swapped_boxes_are_safe() -> None:
    out = redaction.mask_regions(_png((20, 20)), "image/png", [[0.9, 0.9, 0.1, 0.1]])
    assert out.masks_burned == 1  # swapped corners are normalised, not dropped
    out2 = redaction.mask_regions(_png((20, 20)), "image/png", [[0.5, 0.5, 0.5, 0.5]])
    assert out2.masks_burned == 0


def test_image_size_applies_orientation() -> None:
    assert redaction.image_size(_jpeg_with_exif((40, 20), orientation=6)) == (20, 40)
    assert redaction.image_size(_png((40, 20))) == (40, 20)
    assert redaction.image_size(b"not an image") is None


def _encoded(image: Image.Image, fmt: str) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


@pytest.mark.parametrize(
    ("mode", "fmt", "mime", "color"),
    [
        ("L", "PNG", "image/png", 200),
        ("L", "JPEG", "image/jpeg", 200),
        ("LA", "PNG", "image/png", (200, 255)),
        ("1", "PNG", "image/png", 1),
        ("I;16", "PNG", "image/png", 40000),
        ("CMYK", "JPEG", "image/jpeg", (0, 0, 0, 0)),
    ],
)
def test_single_band_and_other_modes_can_be_masked(
    mode: str, fmt: str, mime: str, color: Any
) -> None:
    data = _encoded(Image.new(mode, (40, 20), color), fmt)
    out = redaction.redact_image(data, mime, [MaskRect(x0=0, y0=0, x1=0.5, y1=1)])
    assert out.masks_burned == 1
    rgb = Image.open(io.BytesIO(out.data)).convert("RGB")
    assert rgb.getpixel((5, 5)) == (0, 0, 0)
    light = rgb.getpixel((35, 5))
    assert isinstance(light, tuple) and sum(light) > 300  # the unmasked half stays light
    again = redaction.mask_regions(data, mime, [[0.0, 0.0, 0.5, 1.0]])
    assert again.masks_burned == 1


def test_decompression_bombs_are_413_before_decoding() -> None:
    huge = _encoded(Image.new("1", (20000, 10000)), "PNG")  # beyond Pillow's own bomb limit
    with pytest.raises(ApiError) as exc:
        redaction.redact_image(huge, "image/png", [])
    assert exc.value.status == 413 and exc.value.code.value == "payload_too_large"
    big = _encoded(Image.new("1", (9000, 9000)), "PNG")  # beyond MAX_PIXELS only
    with pytest.raises(ApiError) as exc2:
        redaction.redact_image(big, "image/png", [])
    assert exc2.value.status == 413


def test_jpeg_comment_and_icc_profile_are_dropped() -> None:
    im = Image.new("RGB", (40, 20), "white")
    buf = io.BytesIO()
    im.save(buf, format="JPEG", comment=b"secret comment", icc_profile=b"secret-icc-profile")
    src = buf.getvalue()
    assert b"secret comment" in src
    out = redaction.redact_image(src, "image/jpeg")
    assert b"secret comment" not in out.data and b"secret-icc-profile" not in out.data
    reopened = Image.open(io.BytesIO(out.data))
    assert "comment" not in reopened.info and "icc_profile" not in reopened.info
    png = io.BytesIO()
    im.save(png, format="PNG", icc_profile=b"secret-icc-profile")
    out_png = redaction.redact_image(png.getvalue(), "image/png")
    assert b"secret-icc-profile" not in out_png.data


def test_fractional_mask_edges_are_burned_not_floored() -> None:
    mask = MaskRect(x0=0.0, y0=0.0, x1=0.55, y1=0.55)
    out = redaction.redact_image(_png((10, 10)), "image/png", [mask])
    im = Image.open(io.BytesIO(out.data)).convert("RGB")
    # pixel 5 is half covered by the mask (0.55 × 10 = 5.5): it must be black
    assert im.getpixel((5, 5)) == (0, 0, 0) and im.getpixel((5, 0)) == (0, 0, 0)
    assert im.getpixel((6, 6)) == (255, 255, 255) and im.getpixel((6, 0)) == (255, 255, 255)


def test_pixel_cap_is_close_to_the_client_cap() -> None:
    """D-21 clients send ≤ 1600 px edges; a flat 40 MP PNG (~116 KB) must not reach the decoder
    (seconds of CPU and ~0.5 GB per page)."""
    assert redaction.MAX_PIXELS <= 16_000_000
    over = _encoded(Image.new("1", (6324, 6324)), "PNG")  # 40 MP, a few KB compressed
    with pytest.raises(ApiError) as exc:
        redaction.redact_image(over, "image/png", [], 0)
    assert exc.value.status == 413
    ok = redaction.redact_image(_encoded(Image.new("L", (1600, 1200)), "PNG"), "image/png", [], 0)
    assert (ok.width, ok.height) == (1600, 1200)
