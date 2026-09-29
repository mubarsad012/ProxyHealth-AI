"""``demo/phash.py`` and ``FixtureStore.match_dhash`` (BUILD_PLAN §5.8; AI_PROMPTS §10.3).

Every fixture page, re-encoded at JPEG 80 % and half size, must match its own fixture within
``MOCK_PHASH_MAX_HAMMING`` (10) and stay farther than that from every other fixture.
"""

import io

import pytest
from PIL import Image

from proxyhealth_api.demo.fixtures import FixtureStore
from proxyhealth_api.demo.phash import (
    HASH_BITS,
    HashError,
    dhash,
    hamming,
    hash_to_hex,
    hex_to_hash,
)
from proxyhealth_api.settings import DATA_DIR

MAX_HAMMING = 10
STORE = FixtureStore.load(DATA_DIR / "fixtures")
PAGES = [(f.id, n) for f in STORE.all() for n in range(1, f.manifest.pages + 1)]


def reencode(png: bytes, *, scale: float = 0.5, quality: int = 80) -> bytes:
    with Image.open(io.BytesIO(png)) as img:
        rgb = img.convert("RGB")
        small = rgb.resize(
            (int(rgb.width * scale), int(rgb.height * scale)), Image.Resampling.LANCZOS
        )
    buf = io.BytesIO()
    small.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def test_hash_is_256_bits_and_hex_round_trips() -> None:
    png = STORE.all()[0].page_png(1)
    value = dhash(png)
    assert 0 <= value < 1 << HASH_BITS
    text = hash_to_hex(value)
    assert len(text) == 64 and hex_to_hash(text) == value


def test_hamming_counts_bits() -> None:
    assert hamming(0b1011, 0b0001) == 2
    assert hamming(5, 5) == 0


def test_undecodable_bytes_raise_hash_error() -> None:
    with pytest.raises(HashError):
        dhash(b"not an image")


def test_all_eighteen_fixtures_are_loaded() -> None:
    assert len(STORE) == 18


def test_manifest_hash_matches_the_page_on_disk() -> None:
    for fixture in STORE.all():
        assert dhash(fixture.page_png(1)) == fixture.dhash, fixture.id


@pytest.mark.parametrize(("fixture_id", "page"), PAGES)
def test_reencoded_page_matches_its_own_fixture_only(fixture_id: str, page: int) -> None:
    fixture = STORE.get(fixture_id)
    assert fixture is not None
    copy = reencode(fixture.page_png(page))
    value = dhash(copy)
    assert fixture.distance(value) <= MAX_HAMMING
    for other in STORE.all():
        if other.id != fixture_id:
            assert other.distance(value) > MAX_HAMMING, (fixture_id, other.id)
    matched = STORE.match_dhash(copy, MAX_HAMMING, kind=fixture.kind)
    assert matched is not None and matched.id == fixture_id


def test_match_respects_kind() -> None:
    screenshot = STORE.get("portal_file_too_large")
    assert screenshot is not None
    copy = reencode(screenshot.page_png(1))
    assert STORE.match_dhash(copy, MAX_HAMMING, kind="document") is None
    matched = STORE.match_dhash(copy, MAX_HAMMING, kind="screenshot")
    assert matched is not None and matched.id == "portal_file_too_large"


def test_unrelated_images_do_not_match() -> None:
    blank = io.BytesIO()
    Image.new("RGB", (800, 1000), "white").save(blank, format="PNG")
    noise = io.BytesIO()
    Image.effect_noise((800, 1000), 64).convert("RGB").save(noise, format="JPEG")
    for data in (blank.getvalue(), noise.getvalue(), b"garbage"):
        assert STORE.match_dhash(data, MAX_HAMMING, kind=None) is None
