"""``POST /v1/feedback`` (API_CONTRACT §3.12; D-31): counts only, no free text accepted."""

import re

import httpx
from fastapi import FastAPI

from proxyhealth_api.contracts.errors import ErrorResponse
from proxyhealth_api.contracts.feedback import FeedbackResponse

BODY: dict[str, object] = {
    "kind": "unclear", "surface": "demands", "language_tag": "prs",
    "document_category": "benefits", "document_type": "medicaid_renewal", "card_id": "d2",
    "resource_id": None, "app_version": "1.0.0", "platform": "android",
    "model_id": "gemini-3.8-flash",
}  # fmt: skip


async def test_feedback_counts_and_returns_ulid(client: httpx.AsyncClient, app: FastAPI) -> None:
    first = await client.post("/v1/feedback", json=BODY)
    second = await client.post("/v1/feedback", json=BODY)
    assert first.status_code == 200 and second.status_code == 200
    ids = [FeedbackResponse.model_validate(r.json()) for r in (first, second)]
    assert all(r.received for r in ids) and ids[0].id != ids[1].id
    assert all(re.match(r"^fb_[0-9A-HJKMNP-TV-Z]{26}$", r.id) for r in ids)
    rows = app.state.feedback_store.counts()
    assert rows == [("unclear", "demands", "prs", "medicaid_renewal", "", "1.0.0",
                     "gemini-3.8-flash", "2")]  # fmt: skip


async def test_feedback_rejects_free_text(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/feedback", json={**BODY, "comment": "the date is wrong"})
    assert r.status_code == 400
    assert ErrorResponse.model_validate(r.json()).error.code == "invalid_request"


async def test_feedback_rejects_text_in_card_id(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/feedback", json={**BODY, "card_id": "My rent is late"})
    assert r.status_code == 400


async def test_feedback_needs_no_consent_header(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/feedback", json={**BODY, "kind": "clear", "surface": "summary"})
    assert r.status_code == 200


async def test_feedback_counts_free_text_identifiers_as_other(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    # resource_id / app_version / model_id are plain str in the contract; the route only keeps
    # vetted-DB resource ids, semver-like versions and configured/model-style ids (D-31).
    text = "John Smith 12 Oak St"
    r = await client.post(
        "/v1/feedback",
        json={**BODY, "resource_id": "john_smith", "app_version": text, "model_id": text},
    )
    assert r.status_code == 200
    rows = app.state.feedback_store.counts()
    assert rows == [("unclear", "demands", "prs", "medicaid_renewal", "other", "other", "other",
                     "1")]  # fmt: skip
    ok = await client.post("/v1/feedback", json={**BODY, "resource_id": "dhs_oig"})
    assert ok.status_code == 200
    assert any(row[4] == "dhs_oig" for row in app.state.feedback_store.counts())
