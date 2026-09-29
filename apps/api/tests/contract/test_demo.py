"""``GET /v1/demo/fixtures`` and page PNGs (API_CONTRACT §3.13; BUILD_PLAN §5.8 step 2)."""

import base64
import io

import httpx
import pytest
from PIL import Image

from proxyhealth_api.contracts.analysis import AnalysisResult
from proxyhealth_api.contracts.demo import DemoFixture
from proxyhealth_api.contracts.errors import ErrorResponse
from proxyhealth_api.contracts.troubleshoot import TroubleshootResult

FIXTURE_IDS = {
    "medicaid_address_confirmation", "uscis_i797c_receipt_i765", "uscis_rfe_87d",
    "nta_hearing_date", "inova_final_notice", "insurance_denial_180d", "prescription_label",
    "school_immunization_notice", "va_pay_or_quit_14d", "snap_interview_notice", "irs_cp_notice",
    "jury_summons", "scam_gift_card_letter", "blurry_unreadable_page", "spanish_lease", "w2_form",
    "traffic_court_notice", "portal_file_too_large",
}  # fmt: skip
DEMO_FIXTURES = {
    "medicaid_address_confirmation", "uscis_rfe_87d", "nta_hearing_date", "inova_final_notice",
    "va_pay_or_quit_14d", "scam_gift_card_letter", "jury_summons", "portal_file_too_large",
}  # fmt: skip


async def listing(client: httpx.AsyncClient) -> list[DemoFixture]:
    r = await client.get("/v1/demo/fixtures")
    assert r.status_code == 200
    return [DemoFixture.model_validate(f) for f in r.json()]


async def test_list_has_all_eighteen(client: httpx.AsyncClient) -> None:
    fixtures = await listing(client)
    assert len(fixtures) == 18 and {f.id for f in fixtures} == FIXTURE_IDS
    kinds = {f.id: f.kind for f in fixtures}
    assert [i for i, k in kinds.items() if k == "screenshot"] == ["portal_file_too_large"]


async def test_available_languages_follow_appendix_d(client: httpx.AsyncClient) -> None:
    for f in await listing(client):
        expected = ["en", "es", "prs", "ar"] if f.id in DEMO_FIXTURES else ["en"]
        assert f.available_target_languages == expected, f.id
        assert f.title_key == f"fixture.{f.id}"
        assert f.thumbnail_url == f"/v1/demo/fixtures/{f.id}/pages/1"


async def test_every_page_is_a_1600px_png(client: httpx.AsyncClient) -> None:
    for f in await listing(client):
        for n in range(1, f.pages + 1):
            r = await client.get(f"/v1/demo/fixtures/{f.id}/pages/{n}")
            assert r.status_code == 200 and r.headers["content-type"] == "image/png"
            assert r.content.startswith(b"\x89PNG")
            with Image.open(io.BytesIO(r.content)) as img:
                assert img.width == 1600, f.id


@pytest.mark.parametrize(
    "path",
    ["/v1/demo/fixtures/nope/pages/1", "/v1/demo/fixtures/w2_form/pages/2",
     "/v1/demo/fixtures/w2_form/pages/0"],
)  # fmt: skip
async def test_unknown_fixture_or_page_is_404(client: httpx.AsyncClient, path: str) -> None:
    r = await client.get(path)
    assert r.status_code == 404
    assert ErrorResponse.model_validate(r.json()).error.code == "not_found"


async def test_demo_sample_analyze_without_consent(client: httpx.AsyncClient) -> None:
    body = {"pages": [], "target_language": "ar", "client_platform": "web",
            "demo_sample_id": "va_pay_or_quit_14d"}  # fmt: skip
    r = await client.post("/v1/analyze", json=body)
    assert r.status_code == 200, r.text
    result = AnalysisResult.model_validate(r.json())
    assert result.document_type == "pay_or_quit" and result.model_meta.demo is True
    assert "demo_sample" in result.warnings
    assert result.summary.title.startswith("إشعار")


async def test_demo_sample_troubleshoot(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/demo/fixtures/portal_file_too_large/pages/1")
    shot = {"mime_type": "image/png", "data_base64": base64.b64encode(r.content).decode()}
    body = {"screenshot": shot, "target_language": "es", "client_platform": "android",
            "demo_sample_id": "portal_file_too_large"}  # fmt: skip
    t = await client.post("/v1/troubleshoot", json=body)
    assert t.status_code == 200, t.text
    result = TroubleshootResult.model_validate(t.json())
    assert [s.ui_target_as_written for s in result.steps if s.ui_target_as_written] == [
        "Choose File", "Upload", "Back",
    ]  # fmt: skip
    assert any("Submit Application" in c for c in result.cautions)
    assert result.safety.emergency is False
