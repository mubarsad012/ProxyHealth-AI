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


async def test_feedback_rejects_free_text_resource_id(client: httpx.AsyncClient) -> None:
    # CL-026: resource_id must match ^[a-z0-9_]{1,64}$, so a name or case number is a 400 and
    # nothing is counted.
    for value in ("John Smith 12 Oak St", "A-123456789", "", "x" * 65):
        r = await client.post("/v1/feedback", json={**BODY, "resource_id": value})
        assert r.status_code == 400, value
        assert ErrorResponse.model_validate(r.json()).error.code == "invalid_request"


async def test_feedback_rejects_free_text_app_version_and_model_id(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    bad: list[tuple[str, str]] = [
        ("app_version", "My landlord says pay by Friday"), ("app_version", "1.0"),
        ("app_version", "\u0661.\u0660.\u0660"), ("app_version", "1.0.0-" + "a" * 21),
        ("app_version", "1" * 37 + ".0.0"), ("model_id", "Maria Lopez"),
        ("model_id", "models/gemini-3.8-flash"), ("model_id", "g" * 65),
    ]  # fmt: skip
    for field, value in bad:
        r = await client.post("/v1/feedback", json={**BODY, field: value})
        assert r.status_code == 400, (field, value)
    assert app.state.feedback_store.counts() == []


async def test_feedback_accepts_identifier_shapes(client: httpx.AsyncClient) -> None:
    for field, value in (
        ("app_version", "1.2.3-beta.1"), ("app_version", "10.20.30+build.7"),
        ("model_id", "mock"), ("model_id", "gemini-3.5-flash-lite"), ("resource_id", "dhs_oig"),
    ):  # fmt: skip
        r = await client.post("/v1/feedback", json={**BODY, field: value})
        assert r.status_code == 200, (field, value)


async def test_feedback_counts_unvetted_identifiers_as_other(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    # Values that pass the coarse contract patterns but are not a vetted-DB resource id or a
    # model id are still counted as "other": feedback/store.py is the privacy boundary (CL-052).
    r = await client.post(
        "/v1/feedback",
        json={**BODY, "resource_id": "john_smith", "model_id": "maria-lopez-12-oak-st"},
    )
    assert r.status_code == 200
    rows = app.state.feedback_store.counts()
    assert rows == [("unclear", "demands", "prs", "medicaid_renewal", "other", "1.0.0", "other",
                     "1")]  # fmt: skip
    ok = await client.post("/v1/feedback", json={**BODY, "resource_id": "dhs_oig"})
    assert ok.status_code == 200
    assert any(row[4] == "dhs_oig" for row in app.state.feedback_store.counts())


async def test_feedback_app_surface_for_non_ai_screens(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    # CL-028(b): S18 "Report a problem" posts surface "app", not "summary".
    body = {"kind": "unclear", "surface": "app", "language_tag": "en", "app_version": "1.0.0",
            "platform": "web"}  # fmt: skip
    r = await client.post("/v1/feedback", json=body)
    assert r.status_code == 200 and r.json()["received"] is True
    assert app.state.feedback_store.counts() == [("unclear", "app", "en", "", "", "1.0.0", "", "1")]
    unknown = await client.post("/v1/feedback", json={**body, "surface": "settings"})
    assert unknown.status_code == 400
