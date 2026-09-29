"""Matcher tests (RESOURCE_DB §6, §10; BUILD_PLAN §5.4 step 3). Assert ORDER, not raw scores.

Where a §6.11 worked-example table disagrees with the §6.1–§6.7 formula applied to the §11 seed,
the formula wins and the test says why (the tables used 0.8 language credit for several entries
that list ``es`` and a pre-final ``nvfs`` tag set; see the WP3 report).
"""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Any

import pytest

from proxyhealth_api.contracts.enums import (
    DisclaimerKind,
    OrgType,
    ResourceTag,
    ScamRisk,
    StatusNoteKey,
)
from proxyhealth_api.contracts.resources import ResourceMatchRequest, ResourceMatchResponse
from proxyhealth_api.resources import matcher
from tests.unit._fixtures_wp3 import SEED_TODAY, make_repo, make_resource, real_meta, real_repo


def run(**kwargs: Any) -> ResourceMatchResponse:
    return matcher.match(ResourceMatchRequest(**kwargs), real_repo(), today=SEED_TODAY)


def ids(resp: ResourceMatchResponse) -> list[str]:
    return [m.resource.id for m in resp.results]


def fallback_ids(resp: ResourceMatchResponse) -> list[str]:
    return [r.id for r in resp.national_fallbacks]


EXAMPLE_A: dict[str, Any] = {
    "tags": ["medical_bill", "charity_care"],
    "document_type": "medical_bill",
    "state": "VA",
    "county": "Fairfax",
    "zip3": "220",
    "language": "fr",
    "institutions_as_written": ["Inova Health System"],
    "limit": 4,
}
EXAMPLE_C: dict[str, Any] = {
    "tags": ["eviction", "housing_counseling"],
    "document_type": "eviction_summons",
    "state": "VA",
    "county": "Fairfax",
    "language": "es",
    "limit": 8,
}


# ---- §6.11 worked examples ----------------------------------------------------------------


def test_example_a_inova_first_and_order() -> None:
    resp = run(**EXAMPLE_A)
    assert ids(resp) == ["inova_fa", "dollarfor", "irs_501r", "cms_medical_bill_rights"]
    by_id = {m.resource.id: m for m in resp.results}
    assert by_id["inova_fa"].why_keys == [
        "why.institution_match",
        "why.for_medical_bill",
        "why.serves_your_county",
    ]
    assert by_id["inova_fa"].why[0] == "Named on your paper (Inova Health System)"
    assert by_id["inova_fa"].why[2] == "Serves Fairfax County"
    assert by_id["dollarfor"].why_keys == [
        "why.for_this_paper",
        "why.for_medical_bill",
        "why.anywhere_in_us",
    ]
    assert by_id["irs_501r"].why_keys == ["why.for_medical_bill", "why.anywhere_in_us"]
    assert by_id["cms_medical_bill_rights"].why_keys == [
        "why.for_this_paper",
        "why.for_medical_bill",
        "why.anywhere_in_us",
        "why.speaks_your_language",
    ]
    assert fallback_ids(resp) == ["211", "hrsa_fqhc"]
    # §6.10: fr request and English-only YAML → the english-only note (the table omits it).
    assert resp.notes_keys == ["notes.resource_text_english_only", "notes.verify_before_going"]
    assert resp.disclaimer_kind == DisclaimerKind.general_information
    assert resp.resource_db_version == real_meta().resource_db_version
    assert [m.score for m in resp.results] == sorted((m.score for m in resp.results), reverse=True)


def test_example_a_lajc_is_the_one_cut_by_limit() -> None:
    resp = run(**{**EXAMPLE_A, "limit": 5})
    assert ids(resp)[4] == "lajc"


def test_example_a_inova_checklist_resource_keys_then_prepare_yaml() -> None:
    resp = run(**EXAMPLE_A)
    inova = resp.results[0]
    keys = [item.key for item in inova.checklist]
    own = list(inova.resource.prepare_checklist_keys)
    assert keys[: len(own)] == own
    assert keys[len(own) :] == ["bring_itemized_bill_request", "bring_insurance_card"]
    assert len(keys) == len(set(keys)) <= 8
    assert all(item.text_en for item in inova.checklist)


def test_example_b_medicaid_dari_preview() -> None:
    resp = run(
        tags=["medicaid_renewal", "benefits_navigation"],
        document_type="medicaid_renewal",
        state="VA",
        zip3="220",
        language="prs",
        limit=3,
    )
    assert ids(resp) == ["medicaid_state", "healthcare_gov", "insurekidsnow"]
    assert resp.results[0].eligibility_note_key == StatusNoteKey.hhs_funded_health
    assert resp.results[0].why_keys[0] == "why.for_this_paper"
    req = ResourceMatchRequest(
        tags=["medicaid_renewal", "benefits_navigation"],
        document_type="medicaid_renewal",
        state="VA",
        zip3="220",
        language="prs",
        limit=3,
    )
    scored, _ = matcher.score_candidates(req, real_repo(), today=SEED_TODAY)
    fourth = scored[3]  # first one cut by limit=3 (county 1.0, Dari listed 1.0)
    assert fourth.resource.id == "fairfax_csp"
    assert (fourth.geo, fourth.language) == (1.0, 1.0)


def test_example_c_eviction_order_cap_and_lsc_note() -> None:
    resp = run(**EXAMPLE_C)
    # Formula order with the seed (the §6.11-C table scored lawhelp/va_courts/usa_housing_help
    # with language 0.8 although they list ``es``, and gave nvfs a tag it does not carry).
    assert ids(resp) == [
        "va_eviction_helpline",
        "hud_counselor",
        "va_courts_landlord_tenant",
        "fairfax_sheriff_eviction",
        "usa_housing_help",
        "lawhelp",
        "lajc",
    ]
    # Capped: 3rd government (va_code_pay_or_quit), 3rd/4th directory (lsc_eviction_db, lsc_find).
    for capped in ("va_code_pay_or_quit", "lsc_find", "lsc_eviction_db"):
        assert capped not in ids(resp)
    lawhelp = next(m for m in resp.results if m.resource.id == "lawhelp")
    assert lawhelp.eligibility_note_key == StatusNoteKey.lsc_restricted
    assert resp.notes_keys[0] == "notes.lsc_restricted_explained"
    assert resp.notes_keys[-1] == "notes.verify_before_going"
    assert fallback_ids(resp) == ["211"]
    court = [m for m in resp.results if "warn.court_date_is_the_deadline" in m.resource.warnings]
    assert {m.resource.id for m in court} == {
        "va_courts_landlord_tenant",
        "fairfax_sheriff_eviction",
    }


def test_example_d_scam_forced_block_by_priority_and_capped() -> None:
    resp = run(
        tags=["scam_report", "immigration_legal_help"], scam_risk="likely", language="en", limit=8
    )
    got = ids(resp)
    assert got[:4] == ["dhs_oig", "uscis_scams", "ftc_reportfraud", "eoir_roster"]
    for m in resp.results[:4]:
        assert m.why_keys[0] == "why.report_scam"
    # Only two government scam pages survive the cap.
    for dropped in ("ftc_immigrant_scams", "irs_scams", "ssa_scams", "uscis_find_legal"):
        assert dropped not in got
    assert "aila" not in got  # never_show_with_tags: [scam_report]
    fallbacks = fallback_ids(resp)
    assert fallbacks[0] == "211"
    assert "dhs_oig" not in fallbacks and "ftc_reportfraud" not in fallbacks
    counts: dict[OrgType, int] = {}
    for m in resp.results:
        counts[m.resource.org_type] = counts.get(m.resource.org_type, 0) + 1
    assert max(counts.values()) <= 2


def test_example_e_emergency_crisis_lines_first_then_bills() -> None:
    resp = run(tags=["medical_bill"], emergency=True, language="en", limit=8)
    got = ids(resp)
    assert got[:4] == ["988", "poison", "dv_hotline", "trafficking"]
    for m in resp.results[:4]:
        assert m.why_keys[0] == "why.crisis_line"
    assert got[4:] == ["dollarfor", "cms_medical_bill_rights", "irs_501r"]
    assert "988" not in fallback_ids(resp)  # already in results
    assert fallback_ids(resp) == ["211", "hrsa_fqhc"]


# ---- geography (§5) -------------------------------------------------------------------------


def test_state_unknown_only_national_and_region_note() -> None:
    resp = run(tags=["medical_bill", "charity_care"], language="en", limit=12)
    assert resp.results
    assert all(m.resource.serves.scope.value == "national" for m in resp.results)
    assert "notes.set_region_for_local_help" in resp.notes_keys
    assert "inova_fa" not in ids(resp)


def test_county_mismatch_excludes_inova() -> None:
    resp = run(**{**EXAMPLE_A, "county": "Montgomery", "zip3": "208", "limit": 12})
    assert "inova_fa" not in ids(resp)


def test_zip3_alone_matches_inova_at_full_geo() -> None:
    req = ResourceMatchRequest(**{**EXAMPLE_A, "county": None, "zip3": "220"})
    scored, _ = matcher.score_candidates(req, real_repo(), today=SEED_TODAY)
    inova = next(c for c in scored if c.resource.id == "inova_fa")
    assert inova.geo == 1.0
    assert inova.geo_key == "why.serves_your_area"


def test_state_only_gives_check_service_area_and_county_note() -> None:
    req = ResourceMatchRequest(**{**EXAMPLE_A, "county": None, "zip3": None, "limit": 12})
    scored, _ = matcher.score_candidates(req, real_repo(), today=SEED_TODAY)
    inova = next(c for c in scored if c.resource.id == "inova_fa")
    assert inova.geo == 0.9
    assert inova.geo_key == "why.check_service_area"
    resp = matcher.match(req, real_repo(), today=SEED_TODAY)
    assert "notes.county_unknown" in resp.notes_keys


def test_other_state_excludes_state_and_county_entries() -> None:
    resp = run(tags=["eviction"], state="MD", language="en", limit=12)
    for m in resp.results:
        assert m.resource.serves.scope.value == "national" or "MD" in m.resource.serves.states
    assert "notes.no_local_results" in resp.notes_keys


# ---- filters, penalties, cap, forcing -------------------------------------------------------


def test_never_show_with_tags_hides_aila_with_scam_report() -> None:
    with_scam = run(tags=["immigration_legal_help", "scam_report"], language="en", limit=12)
    assert "aila" not in ids(with_scam)
    req = ResourceMatchRequest(tags=["immigration_legal_help"], language="en", limit=12)
    scored, _ = matcher.score_candidates(req, real_repo(), today=SEED_TODAY)
    assert "aila" in {c.resource.id for c in scored}


def test_lsc_restricted_is_penalised_but_shown() -> None:
    req = ResourceMatchRequest(**EXAMPLE_C)
    scored, _ = matcher.score_candidates(req, real_repo(), today=SEED_TODAY)
    lawhelp = next(c for c in scored if c.resource.id == "lawhelp")
    assert lawhelp.penalties == pytest.approx(0.2)
    resp = run(tags=["traffic_court"], language="en")
    assert ids(resp) == ["lawhelp"]  # the only traffic_court entry is never hidden
    assert resp.results[0].eligibility_note_key == StatusNoteKey.lsc_restricted
    assert "notes.lsc_restricted_explained" in resp.notes_keys


def test_diversity_cap_two_per_org_type_but_crisis_exempt() -> None:
    for tags in (["eviction"], ["immigration_legal_help"], ["benefits_navigation", "food"]):
        resp = run(tags=tags, state="VA", county="Fairfax", language="en", limit=12)
        counts: dict[OrgType, int] = {}
        for m in resp.results:
            counts[m.resource.org_type] = counts.get(m.resource.org_type, 0) + 1
        assert max(counts.values()) <= 2, tags
    crisis = run(tags=["medical_bill"], emergency=True, language="en", limit=12)
    hotlines = [m for m in crisis.results if m.resource.org_type == OrgType.hotline]
    assert len(hotlines) >= 4


def test_emergency_puts_988_first_even_with_unrelated_tags() -> None:
    resp = run(tags=["jury_summons"], emergency=True, language="en", state="VA")
    assert ids(resp)[0] == "988"
    assert "uscourts_jury" in ids(resp)


def test_scam_likely_puts_dhs_oig_first() -> None:
    resp = run(tags=["scam_report"], scam_risk="likely", language="en")
    assert ids(resp)[0] == "dhs_oig"
    both = run(tags=["medical_bill"], scam_risk="likely", emergency=True, language="en")
    first_scam = next(
        i for i, m in enumerate(both.results) if ResourceTag.scam_report in m.resource.tags
    )
    assert all(matcher.is_dedicated_crisis(m.resource) for m in both.results[:first_scam])


def test_stale_penalty_and_exclusion() -> None:
    fresh = make_resource(id="fresh_org", verified_on=SEED_TODAY.isoformat())
    old = (SEED_TODAY - timedelta(days=200)).isoformat()
    stale = make_resource(id="stale_org", verified_on=old)
    assert matcher.penalties(fresh, SEED_TODAY) == 0
    assert matcher.penalties(stale, SEED_TODAY) == pytest.approx(0.3)
    later = SEED_TODAY + timedelta(days=300)
    repo = make_repo([fresh, stale], today=later)
    assert [r.id for r in repo.active()] == ["fresh_org"]  # stale_org is 500 days old


# ---- fallbacks, language, determinism --------------------------------------------------------


def test_national_fallbacks_composition() -> None:
    repo = real_repo()
    req = ResourceMatchRequest(
        tags=["asylum", "medical_bill"], scam_risk=ScamRisk.possible, emergency=True, language="en"
    )
    assert [r.id for r in matcher.national_fallbacks(req, repo, set())] == [
        "211", "immlawhelp", "hrsa_fqhc", "ftc_reportfraud", "dhs_oig", "988",
    ]  # fmt: skip
    plain = ResourceMatchRequest(tags=["jury_summons"], language="en")
    assert [r.id for r in matcher.national_fallbacks(plain, repo, set())] == ["211"]
    assert matcher.national_fallbacks(plain, repo, {"211"}) == []


@pytest.mark.parametrize(
    ("req_lang", "langs", "expected"),
    [
        ("zh-Hant", ["en", "zh-Hans"], 0.9),
        ("prs", ["en", "fa"], 0.9),
        ("ar", ["en"], 0.8),
        ("es", ["en", "es"], 1.0),
        ("ti", ["en", "interpreters_200+"], 1.0),
        ("pt-BR", ["pt"], 0.9),
    ],
)
def test_language_credit(req_lang: str, langs: list[str], expected: float) -> None:
    assert matcher.language_credit(req_lang, langs, real_meta()) == expected


def test_institution_fuzzy_match() -> None:
    inova = real_repo().get("inova_fa")
    assert inova is not None
    assert matcher.institution_match(["INOVA HEALTH SYSTEM, INC."], inova) is not None
    assert matcher.institution_match(["Kaiser Permanente"], inova) is None


def test_determinism_under_shuffled_repo_order() -> None:
    base = run(**EXAMPLE_C)
    resources = real_repo().all()
    rng = random.Random(7)
    for _ in range(3):
        shuffled = list(resources)
        rng.shuffle(shuffled)
        repo = make_repo(shuffled)
        again = matcher.match(ResourceMatchRequest(**EXAMPLE_C), repo, today=SEED_TODAY)
        assert again.model_dump() == base.model_dump()


def test_en_strings_override_meta_copy() -> None:
    req = ResourceMatchRequest(**EXAMPLE_A)
    resp = matcher.match(
        req, real_repo(), en_strings={"why.for_medical_bill": "Bills!"}, today=SEED_TODAY
    )
    assert resp.results[0].why[1] == "Bills!"
