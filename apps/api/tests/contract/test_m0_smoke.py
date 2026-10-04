"""M0 gate (BUILD_PLAN §2): the mock API answers every day-0 call with contract-shaped bodies."""

import httpx

from proxyhealth_api.contracts.analysis import AnalysisResult
from proxyhealth_api.contracts.chat import ChatAnswer
from proxyhealth_api.contracts.config import HealthResponse, ServerConfig
from proxyhealth_api.contracts.demo import DemoFixture
from proxyhealth_api.contracts.errors import ErrorResponse
from proxyhealth_api.contracts.langpack import LanguagePack
from proxyhealth_api.contracts.troubleshoot import TroubleshootResult


def _analyze_body(png_b64: str) -> dict[str, object]:
    return {
        "pages": [{"mime_type": "image/png", "data_base64": png_b64}],
        "target_language": "en",
        "client_platform": "web",
    }


async def test_health(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    body = HealthResponse.model_validate(r.json())
    assert body.provider == "mock" and body.keys_configured == 0
    assert r.headers["X-Contract-Version"] == "1"
    assert r.headers["X-Data-Use-Tier"] == "demo"
    assert r.headers["X-Request-Id"]


async def test_config(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/config")
    assert r.status_code == 200
    cfg = ServerConfig.model_validate(r.json())
    assert cfg.data_use_tier == "demo"
    assert cfg.features.real_documents_allowed is True
    assert cfg.consent_version == "2026-10-04"
    assert {lang.tag for lang in cfg.languages} >= {"en", "es", "prs", "ar", "rhg"}
    assert len(cfg.base_pack_version) == 64


async def test_analyze_with_consent(
    client: httpx.AsyncClient, consent_headers: dict[str, str], tiny_png_base64: str
) -> None:
    r = await client.post(
        "/v1/analyze", json=_analyze_body(tiny_png_base64), headers=consent_headers
    )
    assert r.status_code == 200, r.text
    result = AnalysisResult.model_validate(r.json())
    # A blank page matches no sample (dHash, D-29): the mock must not invent a document.
    assert result.document_type == "unknown"
    assert result.quality.readable is False
    assert result.demands == [] and result.red_flags == []
    assert result.model_meta.provider == "mock" and result.model_meta.demo is True
    assert result.request_id == r.headers["X-Request-Id"]


async def test_analyze_without_consent_is_428(
    client: httpx.AsyncClient, tiny_png_base64: str
) -> None:
    r = await client.post("/v1/analyze", json=_analyze_body(tiny_png_base64))
    assert r.status_code == 428
    err = ErrorResponse.model_validate(r.json()).error
    assert err.code == "consent_required" and err.user_message_key == "err.consent_required"


async def test_analyze_demo_sample_skips_consent(client: httpx.AsyncClient) -> None:
    body = {
        "pages": [], "target_language": "es", "client_platform": "ios",
        "demo_sample_id": "medicaid_address_confirmation",
    }  # fmt: skip
    r = await client.post("/v1/analyze", json=body)
    assert r.status_code == 200, r.text
    result = AnalysisResult.model_validate(r.json())
    assert result.quality.pages_received == 1 and "demo_sample" in result.warnings


async def test_analyze_validation_error_is_400(
    client: httpx.AsyncClient, consent_headers: dict[str, str]
) -> None:
    r = await client.post("/v1/analyze", json={"target_language": "en"}, headers=consent_headers)
    assert r.status_code == 400
    assert ErrorResponse.model_validate(r.json()).error.code == "invalid_request"


async def test_demo_fixtures_list_all_samples(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/demo/fixtures")
    assert r.status_code == 200
    fixtures = [DemoFixture.model_validate(f) for f in r.json()]
    ids = [f.id for f in fixtures]
    assert len(ids) == 18 and "medicaid_address_confirmation" in ids  # BUILD_PLAN §4.5
    medicaid = next(f for f in fixtures if f.id == "medicaid_address_confirmation")
    page = await client.get(medicaid.thumbnail_url)
    assert page.status_code == 200 and page.headers["content-type"] == "image/png"
    assert page.content.startswith(b"\x89PNG")
    missing = await client.get("/v1/demo/fixtures/nope/pages/1")
    assert missing.status_code == 404


async def test_language_pack_en_and_unknown(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/language-packs/en")
    assert r.status_code == 200
    pack = LanguagePack.model_validate(r.json())
    assert pack.strings["langpack.adapting"] == "Adapting system environment to your language..."
    assert r.headers["ETag"] == pack.etag
    again = await client.get("/v1/language-packs/en", headers={"If-None-Match": pack.etag})
    assert again.status_code == 304
    missing = await client.get("/v1/language-packs/xx")
    assert missing.status_code == 404
    assert ErrorResponse.model_validate(missing.json()).error.code == "not_found"


async def test_troubleshoot_and_chat(
    client: httpx.AsyncClient, consent_headers: dict[str, str], tiny_png_base64: str
) -> None:
    t = await client.post(
        "/v1/troubleshoot",
        json={
            "screenshot": {"mime_type": "image/png", "data_base64": tiny_png_base64},
            "target_language": "en", "client_platform": "android",
        },  # fmt: skip
        headers=consent_headers,
    )
    assert t.status_code == 200, t.text
    TroubleshootResult.model_validate(t.json())
    a = await client.post(
        "/v1/analyze",
        json={"pages": [], "target_language": "en", "client_platform": "web",
              "demo_sample_id": "medicaid_address_confirmation"},  # fmt: skip
    )
    analysis = a.json()
    context = {k: analysis[k] for k in (
        "analysis_id", "category", "document_type", "detected_language", "sender_as_written",
        "summary", "demands", "unverified", "plan_steps", "red_flags", "glossary",
        "original_text", "urgency",
    )}  # fmt: skip
    c = await client.post(
        "/v1/chat",
        json={"analysis": context, "messages": [], "question": "When is it due?",
              "target_language": "en"},  # fmt: skip
        headers=consent_headers,
    )
    assert c.status_code == 200, c.text
    answer = ChatAnswer.model_validate(c.json())
    # The Medicaid sample prints a deadline, so the answer quotes it (BUILD_PLAN §5.8 chat row).
    assert answer.not_in_document is False
    deadline_spans = {s for d in analysis["demands"] for s in d["span_ids"]}
    assert answer.grounded_span_ids and set(answer.grounded_span_ids) <= deadline_spans
