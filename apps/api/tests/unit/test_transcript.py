"""WP2 — ``analysis/transcript.py`` (AI_PROMPTS §11.1; D-19 SSN / ID masks)."""

from __future__ import annotations

import pytest

from proxyhealth_api.analysis import transcript as tr
from proxyhealth_api.contracts.analysis import RedFlag
from proxyhealth_api.contracts.enums import Legibility, RedFlagKind, Severity, WarningCode
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


# --- missing pages are decided in code (AI_PROMPTS §4 ``red_flags`` row) ------------------------


def _paper(*texts: tuple[str, int], received: int) -> tr.Transcript:
    blocks = [block(f"p{page}b{i}", text, page=page) for i, (text, page) in enumerate(texts, 1)]
    return tr.assemble_transcript(blocks, pages_received=received)


def _flag(kind: RedFlagKind, quote: str | None, span_ids: list[str]) -> RedFlag:
    return RedFlag(
        kind=kind, text="model text", source_quote=quote, span_ids=span_ids, page=1,
        severity=Severity.medium, fixed_copy_key=None, verified=True,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("texts", "received", "gap"),
    [
        ([("Notice of hearing", 1), ("Page 1 of 3", 1)], 1, True),
        ([("Page 1 of 1", 1)], 1, False),
        ([("Página 1 de 2", 1), ("Página 2 de 2", 2)], 2, False),
        ([("صفحة 1 من 2", 1)], 1, True),
        ([("صفحه ۱ از ۲", 1), ("صفحه ۲ از ۲", 2)], 2, False),
        ([("Page 1/2", 1), ("Page 1/2", 2)], 2, True),  # the same page sent twice; 2 is missing
        ([("Page 1 of 2", 1), ("More notes", 2)], 2, False),  # page 2 prints no marker
        ([("Received Date\tPriority Date\tPage\n08/17/2026 | 08/17/2026 | 1 of 1", 1)], 1, False),
        ([("Please see the additional information on the back.", 1)], 1, False),
        ([("This is a single page notice. There are no missing pages.", 1)], 1, False),
    ],
)
def test_missing_pages_needs_a_printed_page_marker(
    texts: list[tuple[str, int]], received: int, gap: bool
) -> None:
    found = tr.missing_pages(_paper(*texts, received=received), received)
    assert (found is not None) is gap
    if found is not None:
        assert found.quote in " ".join(t for t, _ in texts) and found.block_id.startswith("p")


def test_the_gap_evidence_names_the_marker() -> None:
    found = tr.missing_pages(_paper(("Notice", 1), ("Page 1 of 3", 1), received=1), 1)
    assert found == tr.MissingPages("Page 1 of 3", "p1b2", 1, 3, 1)


FOOTER = "SAMPLE — synthetic document made for demonstration. Not a real letter."


@pytest.mark.parametrize(
    ("marker", "total"),
    [
        ("1 of 3", 3),  # an English footer without the word "Page"
        ("- 1 of 3 -", 3),
        ("Page 1 sur 3", 3),
        ("Trang 1/3", 3),
        ("第 1 页，共 3 页", 3),
        ("共 3 页 第 1 页", 3),
        ("Paj 1 sou 3", 3),
        ("Страница 1 из 3", 3),
        ("Seite 1 von 3", 3),
        ("Hoja 1 de 3", 3),
        ("Page 1\nof 3", 3),  # "Page 1" and "of 3" on two lines
        ("Page 1 of 3", 3),
        ("Página 1 de 3", 3),
    ],
)
def test_page_markers_in_many_forms_are_recognised(marker: str, total: int) -> None:
    paper = _paper(("Notice about your benefits.", 1), (marker, 1), received=1)
    marks = tr.page_marks(paper)
    assert [(m.number, m.total, m.block.id) for m in marks] == [(1, total, "p1b2")]
    assert tr.missing_pages(paper, 1) is not None


@pytest.mark.parametrize(
    "text",
    [
        "Page\n08/17/2026",  # a table's "Page" header over a date row
        "Payment 1 of 12 is due.",
        "Step 1 of 3: sign the form.",
        "Installment | 1 of 2",  # a "1 of 2" cell under no "Page" header
        "10/22/2026",
    ],
)
def test_other_numbers_are_no_page_marker(text: str) -> None:
    assert tr.page_marks(_paper((text, 1), received=1)) == []


def test_a_page_cell_under_a_page_header_is_a_marker() -> None:
    """The I-797C prints "Received Date | Priority Date | Page" over "… | 1 of 1"."""
    paper = _paper(("Received Date | Priority Date | Page", 1),
                   ("08/17/2026 | 08/17/2026 | 1 of 1", 1), received=1)  # fmt: skip
    assert [(m.number, m.total, m.block.id) for m in tr.page_marks(paper)] == [(1, 1, "p1b2")]


def test_a_verified_missing_pages_flag_stays_without_a_printed_marker() -> None:
    """No marker is no evidence either way: the verified model flag stays (one of them), as it
    did before the marker check, for every provider."""
    back = "Please see the additional information on the back."
    paper = _paper(("Notice", 1), (back, 1), received=1)
    first = _flag(RedFlagKind.missing_pages, back, ["p1b2"])
    second = _flag(RedFlagKind.missing_pages, "Notice", ["p1b1"])
    settled = tr.settle_page_flags([first, second], paper, pages_received=1)
    assert settled == tr.SettledFlags([first], 0)


def test_a_printed_gap_keeps_the_flag_citing_the_marker() -> None:
    short = _paper(("Page 1 of 2", 1), (FOOTER, 1), received=1)
    first = _flag(RedFlagKind.missing_pages, FOOTER, ["p1b2"])
    marker = _flag(RedFlagKind.missing_pages, "Page 1 of 2", ["p1b1"])
    assert tr.settle_page_flags([first, marker], short, pages_received=1) == tr.SettledFlags(
        [marker], 0
    )


@pytest.mark.parametrize(
    ("texts", "received"),
    [
        ([("Notice", 1), ("Page 1 of 1", 1)], 1),
        ([("Notice", 1), ("1 of 1", 1)], 1),
        ([("Página 1 de 2", 1), ("Página 2 de 2", 2)], 2),
        ([("Received Date | Priority Date | Page", 1), ("08/17/2026 | 08/17/2026 | 1 of 1", 1),
          ("Please see the additional information on the back.", 1)], 1),
    ],
)  # fmt: skip
def test_markers_that_account_for_every_page_reject_the_flag(
    texts: list[tuple[str, int]], received: int
) -> None:
    """Positive counter-evidence: every printed marker's total is at most the pages received
    (and no number is skipped). Each dropped flag counts as a rejected fact."""
    paper = _paper(*texts, received=received)
    last = paper.blocks[-1]
    flags = [
        _flag(RedFlagKind.missing_pages, last.text, [last.id]),
        _flag(RedFlagKind.missing_pages, texts[0][0], ["p1b1"]),
        _flag(RedFlagKind.contradiction, texts[0][0], ["p1b1"]),
    ]
    settled = tr.settle_page_flags(flags, paper, pages_received=received)
    assert settled == tr.SettledFlags([flags[2]], 2)


def test_settling_page_flags_never_drops_a_repeat_or_the_sentinel() -> None:
    """Repeats are ``scam.screen_model_flags``' job (keyed on kind, quote and the sentinel); a
    second pass keyed on kind and quote alone dropped the ``[multiple_documents]`` sentinel when
    a plain flag with the same quote came first."""
    paper = _paper(("Sample County Clinic", 1), ("Sample County Health Department", 2), received=2)
    office = _flag(RedFlagKind.other, "Sample County Health Department", ["p2b2"])
    sentinel = office.model_copy(update={"text": "[multiple_documents]"})
    again = office.model_copy()
    settled = tr.settle_page_flags([office, sentinel, again], paper, pages_received=2)
    assert settled.flags == [office, sentinel, again] and settled.rejected == 0
