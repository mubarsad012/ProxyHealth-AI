"""Server-side redaction with Pillow, entirely in memory (D-19; D-15 masking path).

``redact_image`` takes one uploaded image and returns new bytes with (1) the EXIF orientation
applied and every EXIF/XMP/ICC block dropped, (2) the client-requested ``rotation`` applied,
(3) every ``MaskRect`` burned pure black. Masks are normalized 0–1 rectangles in the frame the
user saw, i.e. **after** EXIF orientation and ``rotation``. The unmasked bytes live only in the
caller's request memory; nothing here opens a file path, and ``test_redaction.py`` patches
``open`` for write modes to prove it.

Formats Pillow cannot decode here (HEIC/HEIF without a codec) pass through unchanged — EXIF
included — when there is nothing to burn; asking to burn a mask on such an image is a
``400 invalid_request`` because silently sending unmasked bytes would break the consent promise.
"""

from __future__ import annotations

import io
import math
from collections.abc import Sequence
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from proxyhealth_api.contracts.common import MaskRect, Rotation
from proxyhealth_api.contracts.enums import ErrorCode
from proxyhealth_api.errors import ApiError

JPEG_QUALITY = 90
MAX_PIXELS = 40_000_000  # decompression-bomb guard; the client sends ≤ 1600 px edges (D-21)
_ENCODE_FORMAT: dict[str, str] = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}


@dataclass(frozen=True)
class RedactedImage:
    """Result of ``redact_image``/``mask_regions``; ``passthrough`` = bytes returned unchanged."""

    data: bytes
    mime_type: str
    width: int
    height: int
    masks_burned: int
    passthrough: bool = False


Box = tuple[float, float, float, float]


def _too_large() -> ApiError:
    return ApiError(ErrorCode.payload_too_large, 413, "The image has too many pixels.")


def _open(data: bytes) -> Image.Image | None:
    """Decode ``data``; ``None`` when Pillow cannot read it, ``413`` for a decompression bomb.

    The pixel count is checked from the header, before any pixel data is decoded.
    """
    try:
        image = Image.open(io.BytesIO(data))
    except Image.DecompressionBombError as exc:
        raise _too_large() from exc
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    if image.width * image.height > MAX_PIXELS:
        raise _too_large()
    try:
        image.load()
    except Image.DecompressionBombError as exc:
        raise _too_large() from exc
    except (OSError, ValueError):
        return None
    return image


def _orient_and_rotate(image: Image.Image, rotation: Rotation) -> Image.Image:
    oriented = ImageOps.exif_transpose(image) or image
    if rotation:
        # PIL rotates counter-clockwise; the contract's rotation is clockwise degrees.
        oriented = oriented.rotate(-rotation, expand=True)
    return oriented


def _burnable(image: Image.Image) -> Image.Image:
    """``image`` in a mode a black rectangle can be drawn on: RGB, RGBA or L.

    Palette/alpha modes become RGBA, bilevel ``1`` becomes L, 16/32-bit grey is scaled (not
    clipped) to L, and CMYK/YCbCr/LAB/HSV become RGB (where CMYK "0" would otherwise be white).
    """
    mode = image.mode
    if mode in ("RGB", "RGBA", "L"):
        return image
    if mode in ("P", "PA", "LA", "La", "RGBa"):
        return image.convert("RGBA")
    if mode == "1":
        return image.convert("L")
    if mode.startswith("I") or mode == "F":
        grey = image.convert("F")
        hi = grey.getextrema()[1]
        if isinstance(hi, (int, float)) and hi > 255:
            scale = 255.0 / float(hi)
            grey = grey.point(lambda v: v * scale)
        return grey.convert("L")
    return image.convert("RGB")


def _black(mode: str) -> int | tuple[int, ...]:
    if mode == "L":
        return 0
    return (0, 0, 0, 255) if mode == "RGBA" else (0, 0, 0)


def _burn(image: Image.Image, boxes: Sequence[Box]) -> int:
    """Draw every box pure black on ``image`` (already ``_burnable``); returns boxes drawn."""
    if not boxes:
        return 0
    draw = ImageDraw.Draw(image)
    fill = _black(image.mode)
    w, h = image.size
    burned = 0
    for x0, y0, x1, y1 in boxes:
        # floor the top-left and ceil the bottom-right so a fractional edge row/column is burned
        left = math.floor(max(0.0, min(x0, x1)) * w)
        top = math.floor(max(0.0, min(y0, y1)) * h)
        right = min(w, math.ceil(min(1.0, max(x0, x1)) * w))
        bottom = min(h, math.ceil(min(1.0, max(y0, y1)) * h))
        if right <= left or bottom <= top:
            continue
        # -1 because PIL's rectangle is inclusive of the end pixel.
        draw.rectangle((left, top, min(right, w) - 1, min(bottom, h) - 1), fill=fill)
        burned += 1
    return burned


def _encode(image: Image.Image, mime_type: str) -> tuple[bytes, str]:
    fmt = _ENCODE_FORMAT.get(mime_type, "JPEG")
    out_mime = mime_type if mime_type in _ENCODE_FORMAT else "image/jpeg"
    if fmt == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    elif fmt == "PNG" and image.mode not in ("RGB", "RGBA", "L", "LA"):
        image = image.convert("RGBA")
    elif fmt == "WEBP" and image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    # Pillow falls back to ``image.info`` for some blocks (the JPEG COM comment, PNG/WebP ICC
    # profiles); keep only transparency, which is pixel data, not metadata.
    image.info = {k: v for k, v in image.info.items() if k == "transparency"}
    buf = io.BytesIO()
    if fmt == "JPEG":
        image.save(buf, format=fmt, quality=JPEG_QUALITY, optimize=True)
    else:
        image.save(buf, format=fmt)  # no exif/icc kwargs → metadata dropped
    return buf.getvalue(), out_mime


def _process(
    data: bytes, mime_type: str, boxes: Sequence[Box], rotation: Rotation
) -> RedactedImage:
    image = _open(data)
    if image is None:
        if boxes:
            raise ApiError(
                ErrorCode.invalid_request, 400,
                "Parts to hide cannot be applied to this image format; send a JPEG or PNG.",
            )  # fmt: skip
        return RedactedImage(data, mime_type, 0, 0, 0, passthrough=True)
    image = _burnable(_orient_and_rotate(image, rotation))
    burned = _burn(image, boxes)
    out, out_mime = _encode(image, mime_type)
    return RedactedImage(out, out_mime, image.width, image.height, burned)


def redact_image(
    data: bytes, mime_type: str, masks: Sequence[MaskRect] = (), rotation: Rotation = 0
) -> RedactedImage:
    """Orient, rotate, burn ``masks`` black and re-encode ``data`` without metadata, in memory.

    For every format Pillow decodes, EXIF (GPS, device) is gone even when ``masks`` is empty.
    HEIC/HEIF without a decoder is the one exception: it is returned unchanged, metadata
    included (``passthrough=True``), unless masks were requested (then ``400 invalid_request``);
    D-21 clients send JPEG, so this only affects hand-made requests.
    """
    boxes = [(m.x0, m.y0, m.x1, m.y1) for m in masks]
    return _process(data, mime_type, boxes, rotation)


def mask_regions(data: bytes, mime_type: str, bboxes: Sequence[Sequence[float]]) -> RedactedImage:
    """D-15 re-run helper: burn black over transcript ``bbox``es (``[x0, y0, x1, y1]``, 0–1).

    The image is assumed already oriented (it is the bytes the first call saw), so no rotation is
    applied. Boxes with fewer than four numbers or zero area are ignored.
    """
    boxes: list[Box] = []
    for b in bboxes:
        if len(b) >= 4:
            boxes.append((float(b[0]), float(b[1]), float(b[2]), float(b[3])))
    return _process(data, mime_type, boxes, 0)


def image_size(data: bytes) -> tuple[int, int] | None:
    """``(width, height)`` of the image as it would be delivered (EXIF orientation applied)."""
    image = _open(data)
    if image is None:
        return None
    oriented = ImageOps.exif_transpose(image) or image
    return oriented.width, oriented.height


def has_exif(data: bytes) -> bool:
    """True when the encoded bytes still carry an EXIF block (test helper)."""
    image = _open(data)
    return bool(image is not None and image.getexif())


__all__ = [
    "JPEG_QUALITY",
    "RedactedImage",
    "has_exif",
    "image_size",
    "mask_regions",
    "redact_image",
]
