"""Transcript assembly and quality (AI_PROMPTS §11.1; D-19 SSN / ID-number masks).

Pure functions over the model's ``blocks``: block ids are made well-formed and unique (with a
mapping so later ``span_ids`` still resolve), ``bbox`` is clamped, SSN-like patterns are masked
everywhere, A-numbers/receipt numbers are masked only when ``hide_id_numbers`` is on, and
``Quality`` + its warnings are computed. Missing pages are a structural fact checked here: a
printed "Page 1 of 3" with fewer pages received (or a skipped page number) is evidence of a gap,
and printed markers that account for every page are evidence against one — the only case in
which a verified model ``missing_pages`` flag is rejected (``page_marks``, ``missing_pages``,
``settle_page_flags``). Nothing here logs or stores text.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from proxyhealth_api.contracts.analysis import Quality, RedFlag
from proxyhealth_api.contracts.common import PageText, TextBlock
from proxyhealth_api.contracts.enums import Legibility, RedFlagKind, WarningCode

BLOCK_ID_RE = re.compile(r"^p\d+b\d+$")

# Hyphen-like separators an OCR'd or typed SSN may carry: ASCII hyphen, U+2010–U+2015, minus.
_DASH = "\\-\u2010-\u2015\u2212"
# ``123-45-6789`` with any hyphen or dash: SSN-shaped wherever it appears.
_SSN_DASHED_RE = re.compile(rf"\b\d{{3}}[{_DASH}]\d{{2}}[{_DASH}](\d{{4}})\b")
# Next to an SSN cue (within ~40 characters, before or after) the groups may also be split by
# spaces or dots, or not split at all: ``SSN: 123 45 6789``, ``123.45.6789``, ``123456789``.
_SSN_CUE = r"(?:SSN|S\.S\.N\.?|SS\s?#|Social\s+Security|Seguro\s+Social)"
_SSN_SEP = rf"(?:[ \t\u00a0]*[.{_DASH}][ \t\u00a0]*|[ \t\u00a0]+)?"
_SSN_GROUPS = rf"\b\d{{3}}{_SSN_SEP}\d{{2}}{_SSN_SEP}(\d{{4}})\b"
_SSN_CUED_BEFORE_RE = re.compile(rf"({_SSN_CUE}[^\d\n]{{0,40}}){_SSN_GROUPS}", re.IGNORECASE)
_SSN_CUED_AFTER_RE = re.compile(rf"{_SSN_GROUPS}(?=[^\d\n]{{0,40}}{_SSN_CUE})", re.IGNORECASE)
# A-numbers: ``A`` + 8–9 digits, printed solid or grouped (``A 123-456-789``, ``A# 12 345 678``).
_A_SEP = rf"[ \t\u00a0{_DASH}]?"
_A_NUMBER_RE = re.compile(
    rf"\bA{_A_SEP}#?[ \t\u00a0]?(\d{{2,3}}{_A_SEP}\d{{3}}{_A_SEP}\d{{3}})\b"
)
_RECEIPT_RE = re.compile(r"\b([A-Z]{3})\d{6}(\d{4})\b")
_CASE_NUMBER_RE = re.compile(
    r"\bA[- ]?\d{8,9}\b"
    r"|\b(?:case|docket|file)\s*(?:no\.?|number|#)\s*[:#]?\s*[A-Z0-9][A-Z0-9-]{4,}",
    re.IGNORECASE,
)


def mask_ssn(text: str) -> str:
    """``123-45-6789`` (any dash) → ``***-**-6789``; space/dot-separated or unseparated 9-digit
    runs only within ~40 characters of an SSN cue (``SSN``, ``Social Security``, …)."""
    text = _SSN_DASHED_RE.sub(r"***-**-\1", text)
    text = _SSN_CUED_BEFORE_RE.sub(r"\1***-**-\2", text)
    return _SSN_CUED_AFTER_RE.sub(r"***-**-\1", text)


def _mask_a_number(match: re.Match[str]) -> str:
    return "A•••••" + re.sub(r"\D", "", match.group(1))[-4:]


def mask_id_numbers(text: str) -> str:
    """A-numbers → ``A•••••1234``; receipt numbers → ``IOE••••••1234`` (D-19 opt-in)."""
    text = _A_NUMBER_RE.sub(_mask_a_number, text)
    return _RECEIPT_RE.sub(r"\1••••••\2", text)


def mask_sensitive(text: str, *, hide_id_numbers: bool = False) -> str:
    """SSN masks always; ID-number masks when the user enabled "Hide ID numbers"."""
    out = mask_ssn(text)
    return mask_id_numbers(out) if hide_id_numbers else out


def clamp_bbox(bbox: Sequence[float] | None) -> list[float] | None:
    """Clamp into ``[0, 1]``; ``None`` for a missing, short, inverted or zero-area box."""
    if bbox is None or len(bbox) != 4:
        return None
    x0, y0, x1, y1 = (min(1.0, max(0.0, float(v))) for v in bbox)
    if x1 <= x0 or y1 <= y0:
        return None
    return [x0, y0, x1, y1]


@dataclass
class Transcript:
    """Cleaned ``original_text`` plus lookups the validators need."""

    pages: list[PageText]
    id_map: dict[str, str] = field(default_factory=dict)
    has_case_number: bool = False
    has_receipt_number: bool = False
    hide_id_numbers: bool = False
    _by_id: dict[str, TextBlock] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._by_id = {b.id: b for p in self.pages for b in p.blocks}

    @property
    def blocks(self) -> list[TextBlock]:
        """Every block of every page, in reading order (page, then block order)."""
        return [b for p in self.pages for b in p.blocks]

    @property
    def full_text(self) -> str:
        """All block text (masked) joined by newlines — the regex corpus for the scanners."""
        return "\n".join(b.text for b in self.blocks)

    def mask(self, text: str) -> str:
        """Apply the same SSN (and opted-in ID-number) masks as the blocks (§11.1: every block,
        quote and value), so a model quote copied from the unmasked page still matches."""
        return mask_sensitive(text, hide_id_numbers=self.hide_id_numbers)

    def resolve(self, span_id: str) -> str:
        """Map a model span id through the rename table (unchanged when it was valid)."""
        return self.id_map.get(span_id, span_id)

    def block(self, span_id: str) -> TextBlock | None:
        """The block a (possibly renamed) model span id points to, or ``None`` when unknown."""
        return self._by_id.get(self.resolve(span_id))

    def existing(self, span_ids: Iterable[str]) -> list[str]:
        """Resolved ids that exist, de-duplicated, in order."""
        out: list[str] = []
        for sid in span_ids:
            rid = self.resolve(sid)
            if rid in self._by_id and rid not in out:
                out.append(rid)
        return out

    def blocks_for(self, span_ids: Iterable[str]) -> list[TextBlock]:
        """The existing blocks for ``span_ids`` (resolved, de-duplicated, unknown ids dropped)."""
        return [self._by_id[sid] for sid in self.existing(span_ids)]

    def text_of(self, span_ids: Iterable[str]) -> str:
        """``" ".join(block.text)`` over the referenced blocks that exist (the D-09 corpus)."""
        return " ".join(b.text for b in self.blocks_for(span_ids))

    def page_of(self, span_ids: Iterable[str]) -> int | None:
        """Page of the first existing block among ``span_ids``; ``None`` when none exists."""
        blocks = self.blocks_for(span_ids)
        return blocks[0].page if blocks else None


def assemble_transcript(
    blocks: Sequence[TextBlock],
    *,
    pages_received: int,
    page_sizes: Sequence[tuple[int, int] | None] | None = None,
    hide_id_numbers: bool = False,
) -> Transcript:
    """Build the ``Transcript`` (§11.1): ids fixed, boxes clamped, SSN/ID masks applied.

    ``page_sizes[i]`` is the pixel ``(width, height)`` of page ``i+1`` after redaction/rotation
    (or the PDF raster size); ``None`` entries leave ``PageText.width/height`` null.
    """
    raw_text = "\n".join(b.text for b in blocks)
    page_count = max(pages_received, max((b.page for b in blocks), default=1), 1)
    used: set[str] = {b.id for b in blocks if BLOCK_ID_RE.match(b.id)}
    seen: set[str] = set()
    counters: dict[int, int] = {}
    id_map: dict[str, str] = {}
    cleaned: list[TextBlock] = []
    for b in blocks:
        page = b.page if 1 <= b.page <= page_count else max(1, min(page_count, b.page))
        new_id = b.id
        if not BLOCK_ID_RE.match(new_id) or new_id in seen:
            n = counters.get(page, 0)
            while True:
                n += 1
                candidate = f"p{page}b{n}"
                if candidate not in used and candidate not in seen:
                    break
            counters[page] = n
            if new_id not in id_map and new_id not in seen:
                id_map[new_id] = candidate
            new_id = candidate
        seen.add(new_id)
        cleaned.append(
            TextBlock(
                id=new_id, page=page, text=mask_sensitive(b.text, hide_id_numbers=hide_id_numbers),
                bbox=clamp_bbox(b.bbox), is_handwriting=b.is_handwriting, is_unclear=b.is_unclear,
            )  # fmt: skip
        )
    pages: list[PageText] = []
    for number in range(1, page_count + 1):
        size = page_sizes[number - 1] if page_sizes and number - 1 < len(page_sizes) else None
        pages.append(
            PageText(
                page=number,
                width=size[0] if size else None,
                height=size[1] if size else None,
                blocks=[b for b in cleaned if b.page == number],
            )
        )
    return Transcript(
        pages=pages,
        id_map=id_map,
        has_case_number=bool(_CASE_NUMBER_RE.search(raw_text)),
        has_receipt_number=bool(_RECEIPT_RE.search(raw_text)),
        hide_id_numbers=hide_id_numbers,
    )


def compute_quality(
    legibility: Legibility,
    readable_reason: str | None,
    transcript: Transcript,
    *,
    pages_received: int,
) -> tuple[Quality, list[WarningCode]]:
    """``Quality`` per §11.1: ``readable=false`` only for ``poor``; empty pages listed; warnings."""
    readable = legibility is not Legibility.poor
    empty = [p.page for p in transcript.pages if not p.blocks]
    warnings: list[WarningCode] = []
    if legibility is not Legibility.good:
        warnings.append(WarningCode.low_quality_image)
    if readable and empty and len(empty) < len(transcript.pages):
        warnings.append(WarningCode.partial_pages)
    return (
        Quality(
            readable=readable,
            legibility=legibility,
            reason=readable_reason,
            pages_received=pages_received,
            pages_unreadable=empty,
        ),
        warnings,
    )


# --- missing pages (AI_PROMPTS §4 ``red_flags`` row; DOCUMENT_TAXONOMY §3 "Page 1 of N") --------

MAX_PRINTED_PAGES = 99
_SP = r"[ \t ]*"
# The number and its "of N" may sit on two lines ("Page 1" / "of 3"); the page word and the number
# never do (a table's "Page" header over a "08/17/2026" row is no marker).
_GAP = r"[ \t ]*(?:\n[ \t ]*)?"
_PAGE_WORD = (
    r"(?:(?<![^\W\d_])(?:page|pg\.?|p[aá]g(?:ina)?\.?|paj|trang|seite|hoja|страница|стр\.?)"
    r"|صفحة|صفحه)"
)
_OF = r"(?:of|de|di|sur|sou|von|из|trên|của|/|من|از)"
_TOTAL = r"(?P<m>\d{1,3})(?!\d|/\d)"  # never a date ("Page 08/17/2026")
# "Page 1 of 3", "Page 1/3", "Pg. 2 of 3", "Página 2 de 2", "Page 1 sur 3", "Paj 1 sou 3",
# "Trang 1/3", "Seite 1 von 3", "Страница 1 из 3", "صفحة 1 من 3", "صفحه ۱ از ۳"; Chinese
# "第 1 页，共 3 页" or "共 3 页 第 1 页".
_PAGE_OF_RES = (
    re.compile(rf"{_PAGE_WORD}{_SP}(?P<n>\d{{1,3}}){_GAP}{_OF}{_SP}{_TOTAL}", re.IGNORECASE),
    re.compile(r"第\s*(?P<n>\d{1,3})\s*[页頁]\s*[，,、/／]?\s*共\s*(?P<m>\d{1,3})\s*[页頁]"),
    re.compile(r"共\s*(?P<m>\d{1,3})\s*[页頁]\s*[，,、/／]?\s*第\s*(?P<n>\d{1,3})\s*[页頁]"),
)
# A footer line that is only "1 of 3" ("- 1 of 3 -", "(1/3)"), or a table cell under a "Page"
# header cell (the I-797C's "Received Date | Priority Date | Page" over "… | 1 of 1").
_BARE_RE = re.compile(
    rf"[-–—(\[]?{_SP}(?P<n>\d{{1,3}}){_SP}{_OF}{_SP}{_TOTAL}{_SP}[-–—)\]]?", re.IGNORECASE
)
_PAGE_HEADER_RE = re.compile(rf"{_PAGE_WORD}s?:?|[页頁]", re.IGNORECASE)
_CELL_SPLIT_RE = re.compile(r"\t|[ \t ]*\|[ \t ]*")


@dataclass(frozen=True)
class PageMark:
    """One printed "page N of M" marker: its block, the printed text, N and M."""

    block: TextBlock
    quote: str
    number: int
    total: int


def _cells(line: str) -> list[str]:
    return [c.strip() for c in _CELL_SPLIT_RE.split(line.strip())]


def page_marks(transcript: Transcript) -> list[PageMark]:
    """Every printed page marker of the transcript, in reading order (``1 ≤ N ≤ M ≤ 99``)."""
    marks: list[PageMark] = []

    def add(block: TextBlock, m: re.Match[str]) -> None:
        number, total = int(m.group("n")), int(m.group("m"))
        if 1 <= number <= total <= MAX_PRINTED_PAGES:
            marks.append(PageMark(block, m.group(0).strip(), number, total))

    for page in transcript.pages:
        header: list[str] = []
        for block in page.blocks:
            for pattern in _PAGE_OF_RES:
                for found in pattern.finditer(block.text):
                    add(block, found)
            for line in block.text.split("\n"):
                cells = _cells(line)
                if len(cells) == 1 and (bare := _BARE_RE.fullmatch(cells[0])):
                    add(block, bare)
                elif len(cells) > 1 and len(cells) == len(header):
                    for head, cell in zip(header, cells, strict=True):
                        if _PAGE_HEADER_RE.fullmatch(head) and (bare := _BARE_RE.fullmatch(cell)):
                            add(block, bare)
                if line.strip():
                    header = cells
    return marks


@dataclass(frozen=True)
class MissingPages:
    """Code evidence that pages are missing: the printed marker and what was received."""

    quote: str
    block_id: str
    page: int
    printed_total: int
    pages_received: int


def missing_pages(transcript: Transcript, pages_received: int) -> MissingPages | None:
    """The printed "page N of M" marker proving a gap, or ``None``.

    A gap is a printed total above the pages received, or — when every received page prints its
    own marker — a page number that never appears ("1 of 3", "3 of 3", "3 of 3"). Text such as
    "see the back" or "there are no missing pages" is no evidence either way.
    """
    marks = page_marks(transcript)
    if not marks:
        return None
    total = max(mark.total for mark in marks)
    found = next(mark for mark in marks if mark.total == total)
    marked_pages = {mark.block.page for mark in marks}
    numbers = {mark.number for mark in marks if mark.total == total}
    every_page_marked = marked_pages >= set(range(1, pages_received + 1))
    if total > pages_received or (every_page_marked and numbers != set(range(1, total + 1))):
        return MissingPages(found.quote, found.block.id, found.block.page, total, pages_received)
    return None


@dataclass(frozen=True)
class SettledFlags:
    """``settle_page_flags``' result: the flags that stay and how many were rejected."""

    flags: list[RedFlag]
    rejected: int


def settle_page_flags(
    flags: Sequence[RedFlag], transcript: Transcript, *, pages_received: int
) -> SettledFlags:
    """Verified model flags once code has checked ``missing_pages`` against the printed markers.

    A model ``missing_pages`` flag (one, the first citing a gap's marker block, else the first)
    stays unless the paper proves every page arrived: it prints page markers and
    ``missing_pages`` finds no gap (the total is at most the pages received and, when every page
    is marked, no number is skipped). Then every such flag is rejected (counted in
    ``rejected``: it passed span verification and was counted as checked). Without a recognised
    marker the verified flag stays, as for any other kind. Other flags — and the quote-less
    ``[multiple_documents]`` sentinel — pass untouched; repeats were already removed
    (``scam.screen_model_flags``). (A code flag with fixed text needs a base-pack key first.)
    """
    page_flags = [f for f in flags if f.kind is RedFlagKind.missing_pages]
    if not page_flags:
        return SettledFlags(list(flags), 0)
    found = missing_pages(transcript, pages_received)
    if found is None and page_marks(transcript):
        rest = [f for f in flags if f.kind is not RedFlagKind.missing_pages]
        return SettledFlags(rest, len(page_flags))
    keep = next(
        (f for f in page_flags if found is not None and found.block_id in f.span_ids),
        page_flags[0],
    )
    return SettledFlags(
        [f for f in flags if f.kind is not RedFlagKind.missing_pages or f is keep], 0
    )


__all__ = [
    "BLOCK_ID_RE",
    "MAX_PRINTED_PAGES",
    "MissingPages",
    "PageMark",
    "SettledFlags",
    "Transcript",
    "assemble_transcript",
    "clamp_bbox",
    "compute_quality",
    "mask_id_numbers",
    "mask_sensitive",
    "mask_ssn",
    "missing_pages",
    "page_marks",
    "settle_page_flags",
]
