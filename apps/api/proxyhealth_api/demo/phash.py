"""Perceptual hash for sample-paper matching (AI_PROMPTS §10.3; D-29).

16×16 difference hash: the image is greyscaled and box-averaged to 17×16 so that each row yields
16 left-vs-right comparisons, giving a 256-bit integer. Two renderings of the same page (a JPEG
re-encode, a half-size copy, a photograph of the printed SAMPLE sheet) land within a small
Hamming distance; a different paper lands far away, so zero-key mode never fabricates a reading
of a real letter (it falls through to the generic "not recognised" result).

Two deliberate refinements over the AI_PROMPTS §10.3 sketch (same size, same bit layout, same
Hamming threshold), measured on the 18 fixtures with ``scripts/make_fixtures.py --distances``:

* ``BOX`` (area average) instead of ``LANCZOS`` for the 17×16 reduction — the plain mean of each
  cell is what a re-encoded or re-scaled copy preserves best;
* a bit is set only when the left cell is brighter by more than ``DEAD_ZONE`` grey levels, so the
  many almost-equal neighbours on a mostly white page stop flipping under JPEG noise.

Worst own-distance over JPEG 50–80 % at 0.3–1.0 scale dropped from 13 to 6 bits while the
nearest other fixture stayed ≥ 25 bits away.
"""

from io import BytesIO

from PIL import Image, UnidentifiedImageError

HASH_SIDE = 16
HASH_BITS = HASH_SIDE * HASH_SIDE
DEAD_ZONE = 2


class HashError(ValueError):
    """The bytes are not an image Pillow can decode."""


def dhash(png_or_jpeg: bytes) -> int:
    """256-bit dHash of an image given as encoded bytes (PNG, JPEG, WebP; anything Pillow reads)."""
    try:
        with Image.open(BytesIO(png_or_jpeg)) as opened:
            img = opened.convert("L").resize((HASH_SIDE + 1, HASH_SIDE), Image.Resampling.BOX)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise HashError("not a decodable image") from exc
    row_len = HASH_SIDE + 1
    px = img.tobytes()  # 8-bit grey, row-major, (HASH_SIDE + 1) bytes per row
    bits = 0
    for y in range(HASH_SIDE):
        base = y * row_len
        for x in range(HASH_SIDE):
            bits = (bits << 1) | (1 if px[base + x] > px[base + x + 1] + DEAD_ZONE else 0)
    return bits


def hamming(a: int, b: int) -> int:
    """Number of differing bits between two hashes."""
    return (a ^ b).bit_count()


def hash_to_hex(value: int) -> str:
    """Fixed-width lower-case hex (64 chars) for ``manifest.yaml``."""
    return f"{value:0{HASH_BITS // 4}x}"


def hex_to_hash(text: str) -> int:
    return int(text, 16)


__all__ = [
    "DEAD_ZONE",
    "HASH_BITS",
    "HASH_SIDE",
    "HashError",
    "dhash",
    "hamming",
    "hash_to_hex",
    "hex_to_hash",
]
