"""WP2 — ``analysis/transcript.py`` (AI_PROMPTS §11.1; D-19 SSN / ID masks)."""

from __future__ import annotations

import pytest

from proxyhealth_api.analysis import transcript as tr
from proxyhealth_api.contracts.enums import Legibility, WarningCode
from tests.unit._fixtures_wp2 import block


def test_ssn_masks_always_keep_last_four() -> None:
    assert tr.mask_ssn("SSN 123-45-6789 on file") == "SSN ***-**-6789 on file"
    masked = tr.mask_ssn("Social Security Number: 123456789.")
    assert masked == "Social Security Number: ***-**-6789."
    # a bare 9-digit run without the SSN cue is left alone (could be a case number)
    assert tr.mask_ssn("Case 123456789") == "Case 123456789"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Social Security Number: 123 45 6789", "Social Security Number: ***-**-6789"),
        ("SSN: 123\u201345\u20136789", "SSN: ***-**-6789"),  # en dashes
        ("Your SSN is 123.45.6789", "Your SSN is ***-**-6789"),
        ("SSN: 123 - 45 - 6789.", "SSN: ***-**-6789."),
        ("Número de Seguro Social: 123 45 6789", "Número de Seguro Social: ***-**-6789"),
        ("123 45 6789 is your SSN.", "***-**-6789 is your SSN."),  # cue after the number
        ("Ref 123\u201445\u20146789", "Ref ***-**-6789"),  # dashed form needs no cue
    ],
)
def test_ssn_masks_accept_dash_space_and_dot_separators(text: str, expected: str) -> None:
    """D-19: every SSN-like pattern becomes ``***-**-1234`` (API_CONTRACT ``original_text``)."""
    assert tr.mask_ssn(text) == expected
    assert "6789" in expected and "123" not in tr.mask_sensitive(text)


@pytest.mark.parametrize(
    "text",
    [
        "Room 123 45 6789",  # spaced digits without an SSN cue
        "Call Social Security at 800 772 1213.",  # a phone number next to the cue
        "Phone 703-555-0142",
    ],
)
def test_ssn_masks_leave_other_numbers_alone(text: str) -> None:
    assert tr.mask_ssn(text) == text


@pytest.mark.parametrize(
    "text", ["A 123-456-789", "A123456789", "A-123 456 789", "A# 123-456-789"]
)
def test_grouped_a_numbers_are_masked_when_requested(text: str) -> None:
    assert tr.mask_sensitive(text) == text
    assert tr.mask_sensitive(text, hide_id_numbers=True) == "A•••••6789"


def test_id_numbers_masked_only_when_requested() -> None:
    text = "A-Number A123456789, receipt IOE0912345678"
    assert tr.mask_sensitive(text) == text
    masked = tr.mask_sensitive(text, hide_id_numbers=True)
    assert "A•••••6789" in masked and "IOE••••••5678" in masked
    assert "A123456789" not in masked and "0912345678" not in masked


def test_clamp_bbox() -> None:
    assert tr.clamp_bbox([-0.1, 0.2, 1.4, 0.9]) == [0.0, 0.2, 1.0, 0.9]
    assert tr.clamp_bbox([0.5, 0.5, 0.5, 0.9]) is None  # zero width
    assert tr.clamp_bbox([0.9, 0.1, 0.2, 0.5]) is None  # inverted
    assert tr.clamp_bbox([0.1, 0.1]) is None and tr.clamp_bbox(None) is None


def test_assemble_fixes_ids_and_records_mapping() -> None:
    blocks = [
        block("p1b1", "Hello"),
        block("weird", "Second"),
        block("p1b1", "Duplicate id"),
        block("p2b1", "Page two", page=2),
    ]
    t = tr.assemble_transcript(blocks, pages_received=2)
    ids = [b.id for b in t.blocks]
    assert ids[0] == "p1b1" and ids[3] == "p2b1"
    assert all(tr.BLOCK_ID_RE.match(i) for i in ids) and len(set(ids)) == 4
    assert t.resolve("weird") == ids[1]
    weird = t.block("weird")
    assert weird is not None and weird.text == "Second"
    assert t.text_of(["p1b1", "nope", "weird"]) == "Hello Second"
    assert t.existing(["weird", "weird", "zzz"]) == [ids[1]]
    assert [p.page for p in t.pages] == [1, 2]
    assert t.page_of(["p2b1"]) == 2 and t.page_of(["zzz"]) is None


def test_assemble_masks_text_and_sets_sizes_and_entity_flags() -> None:
    blocks = [
        block("p1b1", "SSN 123-45-6789 Receipt IOE0912345678", bbox=[0, 0, 2, 2]),
    ]
    t = tr.assemble_transcript(blocks, pages_received=2, page_sizes=[(800, 1000), None])
    assert t.blocks[0].text.startswith("SSN ***-**-6789")
    assert t.blocks[0].bbox == [0.0, 0.0, 1.0, 1.0]
    assert (t.pages[0].width, t.pages[0].height) == (800, 1000)
    assert t.pages[1].width is None and t.pages[1].blocks == []
    assert t.has_receipt_number and not t.has_case_number
    t2 = tr.assemble_transcript([block("p1b1", "Case No. AB-12345 A098765432")], pages_received=1)
    assert t2.has_case_number


def test_compute_quality() -> None:
    t = tr.assemble_transcript([block("p1b1", "x")], pages_received=2)
    q, w = tr.compute_quality(Legibility.good, None, t, pages_received=2)
    assert q.readable and q.pages_received == 2 and q.pages_unreadable == [2]
    assert w == [WarningCode.partial_pages]
    q2, w2 = tr.compute_quality(Legibility.poor, "blurry", t, pages_received=2)
    assert not q2.readable and q2.reason == "blurry" and w2 == [WarningCode.low_quality_image]
    q3, w3 = tr.compute_quality(Legibility.partial, None, t, pages_received=2)
    assert q3.readable and WarningCode.low_quality_image in w3
