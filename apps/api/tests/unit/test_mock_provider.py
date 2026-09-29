"""``MockProvider`` — one test per row of the BUILD_PLAN §5.8 mock-parity table (D-29).

Rows that are served without a model (``/v1/resources/*``, ``/v1/rules``, ``/v1/feedback``,
``/v1/demo/*``) are asserted here to never reach the provider; their payloads are tested by their
owners (WP3) and by ``tests/contract/test_demo.py`` / ``test_feedback.py`` (WP7).
"""

import io
import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image
from pydantic import BaseModel

from proxyhealth_api.ai.mock import MockProvider, direction_for, resolve_language
from proxyhealth_api.ai.provider import AIProvider, Part, StructuredResult, Task
from proxyhealth_api.ai.recording import RecordingProvider
from proxyhealth_api.contracts.enums import Confidence, Direction, ModelTier
from proxyhealth_api.contracts.model_out import (
    AnalysisModelOut,
    ChatModelOut,
    ExplainOut,
    LanguagePackModelOut,
    LanguageResolveOut,
    RewriteOut,
    TaggingModelOut,
    TranscriptOut,
    TroubleshootModelOut,
)
from proxyhealth_api.demo.fixtures import FixtureStore
from proxyhealth_api.demo.mock_outputs import en_strings
from proxyhealth_api.settings import DATA_DIR, Settings
from tests.conftest import make_settings

STORE = FixtureStore.load(DATA_DIR / "fixtures")


@pytest.fixture
def mock(tmp_path: Path) -> MockProvider:
    return MockProvider(STORE, make_settings(tmp_path))


async def call(
    provider: AIProvider, task: Task, parts: Sequence[Part] = (), **hints: str
) -> BaseModel:
    result: StructuredResult = await provider.generate_structured(
        task=task, tier=ModelTier.pro, parts=list(parts), system="", schema=BaseModel,
        thinking=None, media_resolution=None, max_output_tokens=1024, request_id="t",
        hints=hints,
    )  # fmt: skip
    assert result.model_id == "mock" and result.finish_reason == "STOP"
    assert result.parsed is not None and result.raw_text
    return result.parsed


def jpeg_copy(png: bytes) -> bytes:
    with Image.open(io.BytesIO(png)) as img:
        rgb = img.convert("RGB")
        rgb = rgb.resize((rgb.width // 2, rgb.height // 2), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def white_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (400, 500), "white").save(buf, format="PNG")
    return buf.getvalue()


# --- POST /v1/analyze (analyze_single, transcribe, explain) ------------------------------------


async def test_analyze_demo_sample_serves_recorded_language(mock: MockProvider) -> None:
    out = await call(mock, Task.analyze_single, demo_sample_id="uscis_rfe_87d",
                     target_language="prs")  # fmt: skip
    fixture = STORE.get("uscis_rfe_87d")
    assert fixture is not None
    assert isinstance(out, AnalysisModelOut) and out == fixture.analysis_out("prs")


async def test_analyze_unrecorded_language_is_marked_english(mock: MockProvider) -> None:
    out = await call(mock, Task.analyze_single, demo_sample_id="w2_form", target_language="vi")
    english = STORE.get("w2_form")
    assert english is not None and isinstance(out, AnalysisModelOut)
    en_out = english.analysis_out("en")
    assert en_out is not None
    assert out.summary_title.startswith("⟦vi⟧ ") and out.summary_body.startswith("⟦vi⟧ ")
    assert all(s.text.startswith("⟦vi⟧ ") for s in out.plan_steps)
    assert all(g.explanation.startswith("⟦vi⟧ ") for g in out.glossary)
    assert out.summary_body_en == en_out.summary_body_en and out.blocks == en_out.blocks
    assert [g.term_as_written for g in out.glossary] == [g.term_as_written for g in en_out.glossary]


async def test_analyze_dhash_match_without_sample_id(mock: MockProvider) -> None:
    fixture = STORE.get("inova_final_notice")
    assert fixture is not None
    page = Part.of_bytes(jpeg_copy(fixture.page_png(1)), "image/jpeg")
    out = await call(mock, Task.analyze_single, [Part.of_text("x"), page], target_language="ar")
    assert out == fixture.analysis_out("ar")


async def test_analyze_no_match_is_generic_unreadable(mock: MockProvider) -> None:
    page = Part.of_bytes(white_png(), "image/png")
    out = await call(mock, Task.analyze_single, [page], target_language="en")
    assert isinstance(out, AnalysisModelOut)
    assert out.document_type == "unknown" and out.category == "other"
    assert out.legibility == "poor" and out.readable_reason == "mock_no_match"
    assert out.demands == [] and out.blocks == [] and out.plan_steps == []
    assert out.summary_body == en_strings()["state.sample_not_recognised"]


async def test_analyze_screenshot_id_is_not_a_document(mock: MockProvider) -> None:
    out = await call(mock, Task.analyze_single, demo_sample_id="portal_file_too_large")
    assert isinstance(out, AnalysisModelOut) and out.readable_reason == "mock_no_match"


async def test_explain_and_transcribe_split_the_same_output(mock: MockProvider) -> None:
    full = await call(mock, Task.analyze_single, demo_sample_id="medicaid_address_confirmation")
    explain = await call(mock, Task.explain, demo_sample_id="medicaid_address_confirmation")
    seen = await call(mock, Task.transcribe, demo_sample_id="medicaid_address_confirmation")
    assert isinstance(full, AnalysisModelOut) and isinstance(explain, ExplainOut)
    assert isinstance(seen, TranscriptOut)
    assert explain.demands == full.demands and seen.blocks == full.blocks
    assert seen.legibility == full.legibility


# --- POST /v1/troubleshoot ----------------------------------------------------------------------


async def test_troubleshoot_demo_sample_per_language(mock: MockProvider) -> None:
    fixture = STORE.get("portal_file_too_large")
    assert fixture is not None
    for lang in ("en", "es", "prs", "ar"):
        out = await call(mock, Task.troubleshoot, demo_sample_id=fixture.id, target_language=lang)
        assert out == fixture.troubleshoot_out(lang)
    marked = await call(mock, Task.troubleshoot, demo_sample_id=fixture.id, target_language="so")
    assert isinstance(marked, TroubleshootModelOut)
    assert marked.screen_summary.startswith("⟦so⟧ ") and "Upload" in marked.screen_text


async def test_troubleshoot_dhash_and_generic(mock: MockProvider) -> None:
    fixture = STORE.get("portal_file_too_large")
    assert fixture is not None
    shot = Part.of_bytes(jpeg_copy(fixture.page_png(1)), "image/jpeg")
    assert await call(mock, Task.troubleshoot, [shot]) == fixture.troubleshoot_out("en")
    letter = STORE.get("jury_summons")
    assert letter is not None
    other = Part.of_bytes(jpeg_copy(letter.page_png(1)), "image/jpeg")
    out = await call(mock, Task.troubleshoot, [other])
    assert isinstance(out, TroubleshootModelOut)
    assert out.screen_summary == en_strings()["troubleshoot.mock_unrecognised"]
    assert out.steps == [] and out.screen_text == [] and out.needs_human_help
    assert out.confidence == Confidence.low


# --- POST /v1/chat ------------------------------------------------------------------------------


async def analysis_context(client: httpx.AsyncClient, sample: str) -> dict[str, Any]:
    r = await client.post("/v1/analyze", json={
        "pages": [], "target_language": "en", "client_platform": "web", "demo_sample_id": sample,
    })  # fmt: skip
    assert r.status_code == 200, r.text
    a = r.json()
    keys = ("analysis_id", "category", "document_type", "detected_language", "sender_as_written",
            "summary", "demands", "unverified", "plan_steps", "red_flags", "glossary",
            "original_text", "urgency")  # fmt: skip
    return {k: a[k] for k in keys}


async def ask(mock: MockProvider, ctx: Mapping[str, Any], question: str, lang: str) -> ChatModelOut:
    parts = [Part.of_text(json.dumps(ctx)), Part.of_text("[]"), Part.of_text(question)]
    out = await call(mock, Task.chat, parts, question=question, target_language=lang)
    assert isinstance(out, ChatModelOut)
    return out


@pytest.mark.parametrize(
    ("question", "lang"),
    [("When is it due?", "en"), ("¿Cuál es la fecha?", "es"), ("تاریخ آن چه وقت است؟", "prs"),
     ("متى الموعد؟", "ar")],
)  # fmt: skip
async def test_chat_date_words_quote_the_first_deadline(
    client: httpx.AsyncClient, mock: MockProvider, question: str, lang: str
) -> None:
    ctx = await analysis_context(client, "medicaid_address_confirmation")
    out = await ask(mock, ctx, question, lang)
    first = ctx["demands"][0]
    assert first["kind"] == "deadline"
    assert first["source_quote"] in out.answer and out.grounded_span_ids == first["span_ids"]
    assert out.not_in_document is False and out.refusal_kind == "none"


async def test_chat_scam_words_ground_on_red_flags(
    client: httpx.AsyncClient, mock: MockProvider
) -> None:
    ctx = await analysis_context(client, "scam_gift_card_letter")
    if not ctx["red_flags"]:  # WP0's stub pipeline drops model red flags; WP2 keeps verified ones
        fixture = STORE.get("scam_gift_card_letter")
        assert fixture is not None and (en := fixture.analysis_out("en")) is not None
        ctx["red_flags"] = [
            r.model_dump(mode="json")
            | {"severity": "high", "fixed_copy_key": None, "verified": True}
            for r in en.red_flags
        ]
    out = await ask(mock, ctx, "Is this a scam?", "en")
    flag = ctx["red_flags"][0]
    assert flag["source_quote"] in out.answer and out.grounded_span_ids == flag["span_ids"]
    assert "scam_report" in out.resource_tags


@pytest.mark.parametrize(
    ("sample", "question", "lang", "refusal", "refer"),
    [("nta_hearing_date", "Will I win my case?", "en", "outcome", "lawyer_or_accredited_rep"),
     ("snap_interview_notice", "Do I qualify for SNAP?", "en", "eligibility", "benefits_office"),
     ("va_pay_or_quit_14d", "¿Debo firmar algo?", "es", "filing_advice", "housing_counselor"),
     ("jury_summons", "کدام فورم را پر کنم؟", "prs", "filing_advice", "lawyer_or_accredited_rep"),
     ("inova_final_notice", "هل أنا مؤهل للمساعدة؟", "ar", "eligibility", "clinician")],
)  # fmt: skip
async def test_chat_advice_words_refuse_and_refer_by_category(
    client: httpx.AsyncClient, mock: MockProvider, sample: str, question: str, lang: str,
    refusal: str, refer: str,
) -> None:
    ctx = await analysis_context(client, sample)
    out = await ask(mock, ctx, question, lang)
    assert out.refusal_kind == refusal and out.refer_to_professional == refer
    assert out.grounded_span_ids == []


async def test_chat_otherwise_not_in_document(
    client: httpx.AsyncClient, mock: MockProvider
) -> None:
    ctx = await analysis_context(client, "w2_form")
    out = await ask(mock, ctx, "What color is the envelope?", "en")
    assert out.not_in_document is True
    assert out.grounded_span_ids == ctx["summary"]["span_ids"]


# --- language packs, tag, phrasing_rewrite, clerk_translate ------------------------------------


def test_resolve_language_lookup() -> None:
    assert resolve_language("dari").language_tag == "prs"
    assert resolve_language("العربية").language_tag == "ar"
    unknown = resolve_language("Klingonese")
    assert isinstance(unknown, LanguageResolveOut)
    assert unknown.language_tag is None and unknown.confidence == Confidence.low


async def test_langpack_chunk_pseudo_localises(mock: MockProvider) -> None:
    strings = {"home.greeting": "Hello {name}", "btn.ok": "OK"}
    out = await call(mock, Task.langpack_chunk, [Part.of_text(json.dumps(strings))],
                     language_tag="ckb")  # fmt: skip
    assert isinstance(out, LanguagePackModelOut)
    assert {kv.key: kv.value for kv in out.strings} == {
        "home.greeting": "⟦ckb⟧ Hello {name}", "btn.ok": "⟦ckb⟧ OK",
    }  # fmt: skip
    assert out.direction == Direction.rtl and out.confidence == Confidence.low
    assert out.fallback_keys == []
    for tag in ("ar", "prs", "ps", "fa", "ur", "he", "rhg", "ug", "sd", "ckb"):
        assert direction_for(tag) == Direction.rtl
    assert direction_for("es") == Direction.ltr


async def test_clerk_translate_returns_one_key(mock: MockProvider) -> None:
    out = await call(mock, Task.clerk_translate,
                     [Part.of_text(json.dumps({"clerk.need": "I need help", "x.y": "z"}))],
                     language_tag="es")  # fmt: skip
    assert isinstance(out, LanguagePackModelOut)
    assert [(kv.key, kv.value) for kv in out.strings] == [("clerk.need", "⟦es⟧ I need help")]


async def test_tag_from_fixture_or_document_type(mock: MockProvider) -> None:
    by_id = await call(mock, Task.tag, demo_sample_id="inova_final_notice")
    assert isinstance(by_id, TaggingModelOut) and by_id.tags == ["medical_bill", "charity_care"]
    assert by_id.geo_state == "VA"
    by_type = await call(mock, Task.tag, [Part.of_text("document_type=pay_or_quit")])
    assert isinstance(by_type, TaggingModelOut)
    assert by_type.tags == ["eviction", "housing_counseling", "rent_assistance"]


async def test_phrasing_rewrite_hedges(mock: MockProvider) -> None:
    out = await call(mock, Task.phrasing_rewrite, sentence="You must pay by Friday.")
    assert isinstance(out, RewriteOut) and out.sentence == "The paper says you must pay by Friday."


# --- endpoints that never reach the provider --------------------------------------------------


QUICKSHEET_BODY: dict[str, Any] = {
    "title": "Your paper", "language_tag": "en", "direction": "ltr", "font_hint": None,
    "sections": [{"heading": "What it asks", "heading_en": "What it asks",
                  "lines": ["Send proof of address."]}],
    "resources": [], "footer": "Not legal advice.", "generated_on": "2026-09-27",
}  # fmt: skip
FEEDBACK_BODY: dict[str, Any] = {
    "kind": "clear", "surface": "summary", "language_tag": "en", "app_version": "1.0.0",
    "platform": "web",
}  # fmt: skip


class CountingMock(MockProvider):
    calls = 0

    async def generate_structured(self, **kwargs: Any) -> StructuredResult:
        CountingMock.calls += 1
        return await super().generate_structured(**kwargs)


async def test_status_and_data_routes_use_no_model(app: FastAPI, settings: Settings) -> None:
    counting = CountingMock(app.state.fixtures, settings)
    app.state.provider = counting
    app.state.ai.provider = counting
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        health = (await c.get("/health")).json()
        assert health["provider"] == "mock" and health["keys_configured"] == 0
        assert health["keys_healthy"] == 0
        config = (await c.get("/v1/config")).json()
        assert config["data_use_tier"] == "demo"
        assert config["features"]["real_documents_allowed"] is True
        assert config["key_slots"] == {
            "total": 0, "healthy": 0, "cooling": 0, "rpd_exhausted": 0, "disabled": 0,
        }  # fmt: skip
        assert (await c.get("/v1/language-packs/en")).status_code == 200
        assert (await c.get("/v1/language-packs/xx")).status_code == 404
        for path in ("/v1/rules", "/v1/resources", "/v1/demo/fixtures"):
            assert (await c.get(path)).status_code == 200, path
        sheet = await c.post("/v1/quicksheet/pdf", json=QUICKSHEET_BODY)
        assert sheet.status_code == 200 and sheet.content.startswith(b"%PDF"), sheet.text[:200]
        feedback = await c.post("/v1/feedback", json=FEEDBACK_BODY)
        assert feedback.status_code == 200 and feedback.json()["received"] is True
    assert CountingMock.calls == 0


async def test_admin_keys_in_mock_mode(tmp_path: Path) -> None:
    from proxyhealth_api.main import create_app

    application = create_app(make_settings(tmp_path, admin_token="secret"))
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/v1/admin/keys", headers={"X-Admin-Token": "secret"})
    assert r.status_code == 200, r.text
    assert r.json() == {"data_use_tier": "demo", "slots": []}


# --- ai/recording.py (dev-only RecordingProvider) ----------------------------------------------


async def test_recording_provider_is_dev_gemini_only(tmp_path: Path) -> None:
    from proxyhealth_api.ai.recording import RecordingRefused, wrap_if_enabled

    mock_settings = make_settings(tmp_path)
    inner = MockProvider(STORE, mock_settings)
    with pytest.raises(RecordingRefused):
        RecordingProvider(inner, mock_settings)
    assert wrap_if_enabled(inner, mock_settings) is inner
    prod = make_settings(tmp_path, ai_provider="gemini", record_fixtures=True, env="staging",
                         gemini_keys=[{"key": "k" * 20, "project": "p", "billing": True}])
    with pytest.raises(RecordingRefused):
        RecordingProvider(inner, prod)


def dev_recorder(tmp_path: Path, today: date) -> tuple[RecordingProvider, Path]:
    """A ``RecordingProvider`` over the mock, writing into a copy of the ``w2_form`` folder."""
    dev = make_settings(tmp_path, ai_provider="gemini", record_fixtures=True, env="development")
    out_dir = tmp_path / "fixtures"
    (out_dir / "w2_form").mkdir(parents=True)
    (out_dir / "w2_form" / "manifest.yaml").write_text("id: w2_form\n", "utf-8")
    source = DATA_DIR / "fixtures" / "w2_form" / "page-1.png"
    (out_dir / "w2_form" / "page-1.png").write_bytes(source.read_bytes())
    recorder = RecordingProvider(
        MockProvider(STORE, make_settings(tmp_path)), dev, out_dir=out_dir, today=lambda: today
    )
    return recorder, out_dir


async def test_recording_provider_writes_sample_outputs_only(tmp_path: Path) -> None:
    recorder, out_dir = dev_recorder(tmp_path, date(2026, 9, 27))
    page = Part.of_bytes((out_dir / "w2_form" / "page-1.png").read_bytes(), "image/png")
    await call(
        recorder, Task.analyze_single, [page], demo_sample_id="w2_form", target_language="en"
    )
    await call(recorder, Task.analyze_single, [Part.of_bytes(white_png(), "image/png")])
    await call(recorder, Task.analyze_single, [page], demo_sample_id="../etc", target_language="en")
    written = sorted(p.relative_to(out_dir).as_posix() for p in out_dir.rglob("out.*.json"))
    assert written == ["w2_form/out.en.json"]
    body = json.loads((out_dir / "w2_form" / "out.en.json").read_text("utf-8"))
    assert body["_meta"]["recorded_by"] == "recording_provider"
    assert body["_meta"]["recorded_on"] == "2026-09-27" and body["_meta"]["model_id"] == "mock"
    assert AnalysisModelOut.model_validate({k: v for k, v in body.items() if k != "_meta"})


async def test_recording_provider_never_records_a_non_fixture_image(tmp_path: Path) -> None:
    # AI_PROMPTS §10.4 "fixture bytes only — never a user upload": a demo_sample_id next to any
    # other image (or next to no image, or mixed with the real page) must write nothing.
    recorder, out_dir = dev_recorder(tmp_path, date(2026, 9, 27))
    page = Part.of_bytes((out_dir / "w2_form" / "page-1.png").read_bytes(), "image/png")
    user_photo = Part.of_bytes(white_png(), "image/png")
    near_copy = Part.of_bytes(jpeg_copy(page.data or b""), "image/jpeg")
    hints = {"demo_sample_id": "w2_form", "target_language": "en"}
    await call(recorder, Task.analyze_single, [user_photo], **hints)
    await call(recorder, Task.analyze_single, [near_copy], **hints)
    await call(recorder, Task.analyze_single, [page, user_photo], **hints)
    await call(recorder, Task.analyze_single, [], **hints)
    assert list(out_dir.rglob("out.*.json")) == []
    assert recorder.recorded == []
