"""Contract tests for ``/v1/resources`` (API_CONTRACT §3.8–§3.9; RESOURCE_DB §7, §10)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI

from proxyhealth_api.contracts.config import HealthResponse
from proxyhealth_api.contracts.errors import ErrorResponse
from proxyhealth_api.contracts.resources import Resource, ResourceList, ResourceMatchResponse
from proxyhealth_api.resources.loader import ResourceRepo
from tests.unit._fixtures_wp3 import MINIMAL_ENTRY, RESOURCES_DIR, RULES_DIR, copy_seed

# API_CONTRACT §3.8 request, verbatim.
INOVA_EXAMPLE: dict[str, Any] = {
    "tags": ["medical_bill", "charity_care"],
    "document_type": "medical_bill",
    "category": "medical",
    "state": "VA",
    "county": "Fairfax",
    "zip3": "220",
    "language": "fr",
    "institutions_as_written": ["Inova Health System"],
    "scam_risk": "none",
    "emergency": False,
    "limit": 4,
}


def seed_entry_count() -> int:
    total = 0
    for path in RESOURCES_DIR.rglob("*.yaml"):
        if not path.name.startswith("_"):
            total += len(yaml.safe_load(path.read_text(encoding="utf-8")))
    return total


async def test_health_counts_every_yaml_entry(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    body = HealthResponse.model_validate(r.json())
    assert body.resources_loaded == seed_entry_count() == 101
    assert body.resources_loaded >= 70


async def test_match_inova_example_puts_inova_first(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/resources/match", json=INOVA_EXAMPLE)
    assert r.status_code == 200, r.text
    body = ResourceMatchResponse.model_validate(r.json())
    assert [m.resource.id for m in body.results] == [
        "inova_fa",
        "dollarfor",
        "irs_501r",
        "cms_medical_bill_rights",
    ]
    inova = body.results[0]
    assert inova.why == [
        "Named on your paper (Inova Health System)",
        "For hospital and doctor bills",
        "Serves Fairfax County",
    ]
    assert inova.eligibility_note_key == "residency_required"
    assert [c.key for c in inova.checklist][:4] == inova.resource.prepare_checklist_keys
    assert [r.id for r in body.national_fallbacks] == ["211", "hrsa_fqhc"]
    assert body.notes_keys[-1] == "notes.verify_before_going"
    assert body.disclaimer_kind == "general_information"
    assert body.resource_db_version == "2026-09-27"


async def test_match_without_state_is_national_only(client: httpx.AsyncClient) -> None:
    body = {**INOVA_EXAMPLE, "state": None, "county": None, "zip3": None, "limit": 12}
    r = await client.post("/v1/resources/match", json=body)
    assert r.status_code == 200
    resp = ResourceMatchResponse.model_validate(r.json())
    assert all(m.resource.serves.scope == "national" for m in resp.results)
    assert "notes.set_region_for_local_help" in resp.notes_keys


async def test_match_unknown_tag_is_400(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/resources/match", json={**INOVA_EXAMPLE, "tags": ["nope"]})
    assert r.status_code == 400
    assert ErrorResponse.model_validate(r.json()).error.code == "invalid_request"


async def test_match_extra_field_is_400(client: httpx.AsyncClient) -> None:
    r = await client.post("/v1/resources/match", json={**INOVA_EXAMPLE, "city": "Herndon"})
    assert r.status_code == 400


async def test_list_by_jury_tag(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/resources", params={"tag": "jury_summons"})
    assert r.status_code == 200
    body = ResourceList.model_validate(r.json())
    assert [item.id for item in body.items] == ["uscourts_jury"]
    assert body.total == 1
    assert body.items[0].warnings == [
        "warn.jury_never_check_citizen",
        "warn.jury_never_register_to_vote",
    ]
    assert body.resource_db_version == "2026-09-27"


async def test_list_state_and_query(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/resources", params={"state": "VA", "q": "inova"})
    body = ResourceList.model_validate(r.json())
    assert [item.id for item in body.items] == ["inova_fa"] and body.total == 1
    r = await client.get("/v1/resources", params={"limit": 5, "offset": 5})
    page = ResourceList.model_validate(r.json())
    assert len(page.items) == 5 and page.total == 101


async def test_get_one_and_404_envelope(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/resources/211")
    assert r.status_code == 200
    assert Resource.model_validate(r.json()).phone == "211"
    r = await client.get("/v1/resources/does_not_exist")
    assert r.status_code == 404
    err = ErrorResponse.model_validate(r.json()).error
    assert err.code == "not_found"
    assert err.user_message_key == "err.not_found"


async def test_broken_entries_are_never_listed_or_served(
    app: FastAPI, client: httpx.AsyncClient, tmp_path: Path
) -> None:
    directory = copy_seed(tmp_path)
    broken = {**MINIMAL_ENTRY, "id": "zz_broken", "link_health": "broken"}
    (directory / "zz_extra.yaml").write_text(yaml.safe_dump([broken]), encoding="utf-8")
    app.state.resources = ResourceRepo.load(directory, prepare_path=RULES_DIR / "prepare.yaml")
    r = await client.get("/v1/resources", params={"q": "zz_broken"})
    assert ResourceList.model_validate(r.json()).items == []
    assert (await client.get("/v1/resources/zz_broken")).status_code == 404
    r = await client.post(
        "/v1/resources/match", json={"tags": ["benefits_navigation"], "language": "en"}
    )
    ids = [m["resource"]["id"] for m in r.json()["results"]]
    assert "zz_broken" not in ids
