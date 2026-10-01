"""Shared builders for the WP2 lane-2A validator tests (BUILD_PLAN §4.1: ``_fixtures_<wp>.py``).

Kept free of ``conftest`` fixtures so these tests also run with ``pytest --noconftest`` while
other packages' modules are mid-build.
"""

from __future__ import annotations

import base64
import io
from datetime import UTC, date, datetime
from pathlib import Path

from PIL import Image

from proxyhealth_api.analysis.i18n import Translator, english_translator
from proxyhealth_api.contracts.common import TextBlock
from proxyhealth_api.contracts.enums import Confidence, DemandKind
from proxyhealth_api.contracts.model_out import DemandOut, RedFlagOut
from proxyhealth_api.settings import Settings

FROZEN_NOW = datetime(2026, 9, 24, 14, 0, 0, tzinfo=UTC)
TODAY = date(2026, 9, 24)


def settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "ai_provider": "mock",
        "var_dir": tmp_path / "var",
        "mock_latency_min_ms": 0,
        "mock_latency_max_ms": 0,
        "install_hash_secret": "test",
        "consent_version": "2026-10-01",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def image_bytes(fmt: str = "PNG", size: tuple[int, int] = (64, 48), color: str = "white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


def pdf_bytes(pages: int = 1, size: tuple[int, int] = (200, 300)) -> bytes:
    buf = io.BytesIO()
    first = Image.new("RGB", size, "white")
    rest = [Image.new("RGB", size, "white") for _ in range(pages - 1)]
    first.save(buf, format="PDF", save_all=True, append_images=rest)
    return buf.getvalue()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def en_t() -> Translator:
    return english_translator()


def block(
    block_id: str,
    text: str,
    *,
    page: int = 1,
    bbox: list[float] | None = None,
    unclear: bool = False,
    handwriting: bool = False,
) -> TextBlock:
    if bbox is None:
        bbox = [0.1, 0.1, 0.9, 0.2]
    return TextBlock(
        id=block_id, page=page, text=text, bbox=bbox, is_handwriting=handwriting,
        is_unclear=unclear,
    )  # fmt: skip


def demand_out(
    demand_id: str,
    *,
    kind: DemandKind = DemandKind.deadline,
    text: str = "Answer by the date.",
    value_verbatim: str,
    source_quote: str,
    span_ids: list[str],
    page: int = 1,
    date_text: str | None = None,
    time_text: str | None = None,
    relative_rule_text: str | None = None,
    anchor_span_id: str | None = None,
    amount_text: str | None = None,
    currency: str | None = None,
    role: str | None = None,
    confidence: Confidence = Confidence.high,
    documents: list[str] | None = None,
) -> DemandOut:
    return DemandOut(
        id=demand_id, kind=kind, text=text, value_verbatim=value_verbatim,
        source_quote=source_quote, span_ids=span_ids, page=page, date_text=date_text,
        time_text=time_text, relative_rule_text=relative_rule_text,
        anchor_span_id=anchor_span_id, amount_text=amount_text, currency=currency,
        documents=documents or [], role=role, confidence=confidence, ambiguity_note=None,
    )  # fmt: skip


def red_flag_out(
    kind: str, text: str, *, source_quote: str | None, span_ids: list[str], page: int | None = 1
) -> RedFlagOut:
    from proxyhealth_api.contracts.enums import RedFlagKind

    return RedFlagOut(
        kind=RedFlagKind(kind), text=text, source_quote=source_quote, span_ids=span_ids, page=page
    )
