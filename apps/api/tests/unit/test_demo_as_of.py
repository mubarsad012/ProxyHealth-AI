"""Sample papers compute dates and urgency as of ``DEMO_AS_OF`` (demo/as_of.py; POLISH item 1).

Sample papers print fixed dates, so on the wall clock their urgency would drift into "past due".
A ``demo_sample_id`` request, or an upload the mock matches to a fixture by dHash, runs
``deadline_rules`` and ``urgency`` as of ``DEMO_AS_OF``; a real paper keeps the real clock. The
offline bundle (``sync_to_mobile.py``) must hold the same values.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from proxyhealth_api.ai.failover import AIService
from proxyhealth_api.ai.provider import Part
from proxyhealth_api.analysis.pipeline import analysis_today, is_sample_paper, run_analysis
from proxyhealth_api.contracts.analysis import AnalysisResult, AnalyzeRequest
from proxyhealth_api.contracts.enums import Provider, UrgencyLevel
from proxyhealth_api.demo.as_of import DEMO_AS_OF, DEMO_AS_OF_MOMENT
from proxyhealth_api.demo.fixtures import Fixture, FixtureKind
from proxyhealth_api.settings import DATA_DIR
from tests.golden._fixtures_wp7 import STORE, CountingMock, build_deps, fixture, state_of
from tests.unit._fixtures_wp2 import image_bytes

LATE = datetime(2027, 3, 1, 14, 0, tzinfo=UTC)  # five months after the samples' dates
MEDICAID = "medicaid_address_confirmation"
MOBILE_FIXTURES = DATA_DIR.parents[1] / "mobile" / "assets" / "fixtures"
DOCUMENTS = [f.id for f in STORE.all() if f.kind == "document" and f.expected.get("urgency_level")]


class KeyedStandIn(CountingMock):
    """Reports as ``gemini`` and reads every page as the Medicaid sample (a real paper that
    happens to print the sample's dates)."""

    name = Provider.gemini

    def resolve_fixture(
        self, parts: Sequence[Part], hints: Any, kind: FixtureKind
    ) -> Fixture | None:
        return STORE.get(MEDICAID)


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def request(fid: str | None = None, pages: Sequence[bytes] = (), **extra: Any) -> AnalyzeRequest:
    body: dict[str, Any] = {
        "pages": [{"mime_type": "image/png", "data_base64": b64(p)} for p in pages],
        "target_language": "en", "client_platform": "web", "demo_sample_id": fid, **extra,
    }  # fmt: skip
    return AnalyzeRequest.model_validate(body)


async def analyze_at(
    moment: datetime, req: AnalyzeRequest, tmp_path: Path, *, keyed: bool = False
) -> AnalysisResult:
    deps, _ = build_deps(fixture(MEDICAID), tmp_path)
    deps.clock = lambda: moment
    if keyed:
        deps.ai = AIService(KeyedStandIn(STORE, deps.settings), None, deps.settings)
    return await run_analysis(req, deps)


def expected_days(fx: Fixture) -> int | None:
    nearest = fx.expected.get("nearest_date_iso")
    return (date.fromisoformat(str(nearest)) - DEMO_AS_OF).days if nearest else None


def test_every_fixture_is_frozen_at_demo_as_of() -> None:
    # The goldens, Appendix D and demo.as_of_note all assume this one date.
    assert {f.today for f in STORE.all()} == {DEMO_AS_OF}
    assert DEMO_AS_OF_MOMENT.date() == DEMO_AS_OF


def test_analysis_today_pins_only_samples() -> None:
    assert analysis_today(LATE, "VA", sample=True) == DEMO_AS_OF
    assert analysis_today(LATE, "VA", sample=False) == date(2027, 3, 1)
    # A zone ahead of UTC never moves the pinned day.
    assert analysis_today(datetime(2027, 3, 1, 23, tzinfo=UTC), "GU", sample=True) == DEMO_AS_OF


@pytest.mark.parametrize("fid", DOCUMENTS)
async def test_sample_keeps_its_appendix_d_urgency_on_a_late_clock(
    fid: str, tmp_path: Path
) -> None:
    fx = fixture(fid)
    late = await analyze_at(LATE, request(fid, state=state_of(fx)), tmp_path)
    frozen = await analyze_at(DEMO_AS_OF_MOMENT, request(fid, state=state_of(fx)), tmp_path)
    assert late.urgency.level.value in fx.expected["urgency_level"]
    assert late.urgency == frozen.urgency
    assert [d.date for d in late.demands] == [d.date for d in frozen.demands]
    if expected_days(fx) is not None:
        assert late.urgency.days_until == expected_days(fx)
    assert late.created_at == LATE  # only dates and urgency are pinned


async def test_photographed_sample_in_mock_mode_is_pinned(tmp_path: Path) -> None:
    page = fixture(MEDICAID).page_png(1)
    res = await analyze_at(LATE, request(pages=[page], state="VA"), tmp_path)
    assert res.urgency.level is UrgencyLevel.high and res.urgency.days_until == 12
    assert res.demands[0].date is not None
    assert res.demands[0].date.value_iso == "2026-10-14"


async def test_real_paper_keeps_the_real_clock(tmp_path: Path) -> None:
    # Same printed dates, but a keyed provider and a non-sample upload: 2026-10-14 is long past.
    real = await analyze_at(LATE, request(pages=[image_bytes()], state="VA"), tmp_path, keyed=True)
    assert real.urgency.level is UrgencyLevel.info and real.urgency.days_until is None
    assert real.model_meta.demo is False
    demo = await analyze_at(LATE, request(MEDICAID, state="VA"), tmp_path, keyed=True)
    assert demo.urgency.level is UrgencyLevel.high and demo.urgency.days_until == 12


def test_is_sample_paper(tmp_path: Path) -> None:
    deps, _ = build_deps(fixture(MEDICAID), tmp_path)
    sample = [Part.of_bytes(fixture(MEDICAID).page_png(1), "image/png")]
    blank = [Part.of_bytes(image_bytes(), "image/png")]
    assert is_sample_paper(deps, MEDICAID, [])
    assert is_sample_paper(deps, None, sample)
    assert not is_sample_paper(deps, None, blank)
    assert not is_sample_paper(deps, None, [Part.of_bytes(b"%PDF-1.7", "application/pdf")])
    deps.ai = AIService(KeyedStandIn(STORE, deps.settings), None, deps.settings)
    assert not is_sample_paper(deps, None, sample)  # keyed: only demo_sample_id counts


@pytest.mark.parametrize("fid", DOCUMENTS)
def test_offline_bundle_holds_the_pinned_urgency(fid: str) -> None:
    path = MOBILE_FIXTURES / f"{fid}.result.en.json"
    bundled = json.loads(path.read_text(encoding="utf-8"))
    fx = fixture(fid)
    assert bundled["urgency"]["level"] in fx.expected["urgency_level"]
    if expected_days(fx) is not None:
        assert bundled["urgency"]["days_until"] == expected_days(fx)
