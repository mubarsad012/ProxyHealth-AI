"""Transcript assembly and quality (AI_PROMPTS §11.1; D-19 SSN / ID-number masks).

Pure functions over the model's ``blocks``: block ids are made well-formed and unique (with a
mapping so later ``span_ids`` still resolve), ``bbox`` is clamped, SSN-like patterns are masked
everywhere, A-numbers/receipt numbers are masked only when ``hide_id_numbers`` is on, and
``Quality`` + its warnings are computed. Nothing here logs or stores text.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from proxyhealth_api.contracts.analysis import Quality
from proxyhealth_api.contracts.common import PageText, TextBlock
from proxyhealth_api.contracts.enums import Legibility, WarningCode

BLOCK_ID_RE = re.compile(r"^p\d+b\d+$")

_SSN_DASHED_RE = re.compile(r"\b\d{3}-\d{2}-(\d{4})\b")
_SSN_BARE_RE = re.compile(r"((?:SSN|Social Security)[^\d\n]{0,40})\b\d{5}(\d{4})\b", re.IGNORECASE)
_A_NUMBER_RE = re.compile(r"\bA[- ]?\d{4,5}(\d{4})\b")
_RECEIPT_RE = re.compile(r"\b([A-Z]{3})\d{6}(\d{4})\b")
_CASE_NUMBER_RE = re.compile(
    r"\bA[- ]?\d{8,9}\b"
    r"|\b(?:case|docket|file)\s*(?:no\.?|number|#)\s*[:#]?\s*[A-Z0-9][A-Z0-9-]{4,}",
    re.IGNORECASE,
)


def mask_ssn(text: str) -> str:
    """``123-45-6789`` → ``***-**-6789``; a bare 9-digit run only after ``SSN``/``Social Security``.
    """
    text = _SSN_DASHED_RE.sub(r"***-**-\1", text)
    return _SSN_BARE_RE.sub(r"\1***-**-\2", text)


def mask_id_numbers(text: str) -> str:
    """A-numbers → ``A•••••1234``; receipt numbers → ``IOE••••••1234`` (D-19 opt-in)."""
    text = _A_NUMBER_RE.sub(r"A•••••\1", text)
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


__all__ = [
    "BLOCK_ID_RE",
    "Transcript",
    "assemble_transcript",
    "clamp_bbox",
    "compute_quality",
    "mask_id_numbers",
    "mask_sensitive",
    "mask_ssn",
]
