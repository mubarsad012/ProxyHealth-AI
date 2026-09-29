"""Resource loader / validator tests (RESOURCE_DB §8, §10; BUILD_PLAN §5.4 step 2).

Bad inputs are generated under ``tmp_path`` (a copy of the seed plus one bad file) instead of a
checked-in ``tests/fixtures/resources_bad/`` tree; each must refuse boot with ``path:line``.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from proxyhealth_api.contracts.enums import (
    DocumentType,
    GeoScope,
    ResourceTag,
    StatusNoteKey,
)
from proxyhealth_api.contracts.resources import Resource
from proxyhealth_api.resources.loader import (
    ResourceLoadError,
    ResourceRepo,
    _apply_defaults,
    load_meta,
    normalize_county,
    normalize_org_name,
)
from proxyhealth_api.settings import DATA_DIR
from tests.unit._fixtures_wp3 import (
    MINIMAL_ENTRY,
    RESOURCES_DIR,
    RULES_DIR,
    SEED_TODAY,
    copy_seed,
    real_meta,
    real_repo,
    write_entries,
)

SEED_FILES = {
    "national_immigration.yaml": 42,
    "national_health.yaml": 13,
    "national_benefits_food.yaml": 10,
    "national_housing.yaml": 6,
    "national_crisis.yaml": 4,
    "national_school_work_tax.yaml": 12,
    "regional/va_nova.yaml": 14,
}


def load_dir(directory: Path) -> ResourceRepo:
    return ResourceRepo.load(directory, today=SEED_TODAY, prepare_path=RULES_DIR / "prepare.yaml")


def entry(**overrides: Any) -> dict[str, Any]:
    raw = {**MINIMAL_ENTRY, "id": "zz_bad_entry", **overrides}
    return {k: v for k, v in raw.items() if v is not ...}


# ---- the real seed ---------------------------------------------------------------------------


def test_real_seed_loads_101_entries() -> None:
    repo = real_repo()
    assert repo.count() == 101 == sum(SEED_FILES.values())
    assert repo.count() >= 70
    assert len(repo.all()) == len(repo.active()) == 101
    assert repo.stale_ids() == frozenset()
    assert repo.version == "2026-09-27"


def test_seed_file_counts_match_resource_db_section_11() -> None:
    for name, expected in SEED_FILES.items():
        data = yaml.safe_load((RESOURCES_DIR / name).read_text(encoding="utf-8"))
        assert len(data) == expected, name


def test_every_entry_has_verified_on_and_english_copy() -> None:
    for res in real_repo().all():
        assert res.verified_on <= SEED_TODAY
        assert res.what_it_does["en"] and res.eligibility_plain["en"]


def test_warnings_prefixed_and_x_meta_stripped() -> None:
    repo = real_repo()
    jury = repo.get("uscourts_jury")
    assert jury is not None
    assert jury.warnings == ["warn.jury_never_check_citizen", "warn.jury_never_register_to_vote"]
    assert "x_meta" not in jury.model_dump()
    x_meta = repo.x_meta("lawhelp")
    assert x_meta is not None and x_meta["source"]
    for res in repo.all():
        assert all(w.startswith("warn.") for w in res.warnings)


def test_every_resource_tag_has_an_active_entry_or_is_fallback_only() -> None:
    covered = {t for r in real_repo().active() for t in r.tags}
    missing = set(ResourceTag) - covered
    assert missing <= set(real_meta().fallback_only_tags)


def test_repo_surface_for_other_modules() -> None:
    repo = real_repo()
    assert repo.well_known("scam_card_phone") == "dhs_oig"
    assert repo.well_known("scam_card_url") == "ftc_reportfraud"
    assert repo.well_known("verify_court_date") == "eoir_hotline"
    assert repo.well_known_ids("fallback_always") == ["211"]
    assert repo.is_hhs_funded("inova_fa")  # hospital_program with residency_required
    assert repo.is_hhs_funded("medicaid_state")  # status note hhs_funded_health
    assert not repo.is_hhs_funded("lawhelp")
    assert not repo.is_hhs_funded("nope")
    names = repo.org_names()
    assert normalize_org_name("Inova Financial Assistance") in names
    assert any(normalize_org_name("Inova Health System") in n for n in names)
    index = repo.phone_index()
    dhs = repo.get("dhs_oig")
    assert dhs is not None and dhs.phone is not None and index[dhs.phone] == "dhs_oig"
    assert index["988"] == "988"
    assert "Inova Financial Assistance" in repo.names()
    assert repo.prepare_items(DocumentType.jury_summons) == ["bring_the_summons"]


def test_list_filters() -> None:
    repo = real_repo()
    items, total = repo.list(tag=ResourceTag.jury_summons)
    assert [r.id for r in items] == ["uscourts_jury"] and total == 1
    items, total = repo.list(state="VA", q="inova")
    assert [r.id for r in items] == ["inova_fa"] and total == 1
    md, _ = repo.list(state="MD", limit=200)
    assert all(r.serves.scope == GeoScope.national or "MD" in r.serves.states for r in md)
    assert "inova_fa" not in {r.id for r in md}
    page, total = repo.list(limit=10, offset=10)
    assert len(page) == 10 and total == 101
    priorities = [r.priority for r in repo.list(limit=200)[0]]
    assert priorities == sorted(priorities, reverse=True)
    dari, _ = repo.list(language="prs", limit=200)
    assert all("prs" in r.languages or "interpreters_200+" in r.languages for r in dari)


def test_meta_keys_in_en_json() -> None:
    en: dict[str, str] = json.loads((DATA_DIR / "langpacks" / "en.json").read_text("utf-8"))
    meta = real_meta()
    expected = [
        *meta.why,
        *meta.notes,
        *(f"warn.{k}" for k in meta.warning_keys),
        *(f"prepare.{k}" for k in meta.checklist),
        *(f"status_note.{k.value}" for k in StatusNoteKey),
    ]
    missing = sorted(k for k in expected if k not in en)
    assert missing == []
    for key, text in {**meta.why, **meta.notes}.items():
        assert en[key] == text, key


def test_apply_defaults_makes_minimal_compact_form_valid() -> None:
    res = Resource.model_validate(_apply_defaults(dict(MINIMAL_ENTRY)))
    assert res.alt_urls == [] and res.phone is None and res.warnings == []
    assert res.serves.states == [] and res.serves.zip3 == []
    assert res.never_show_with_tags == [] and res.status_note_key is None


def test_normalizers() -> None:
    assert normalize_county("Fairfax County") == "fairfax"
    assert normalize_county("Prince  George’s") == "prince george's"
    assert normalize_org_name("The Inova Health System, Inc.") == "inova"


def test_meta_missing_section_refuses(tmp_path: Path) -> None:
    data = yaml.safe_load((RESOURCES_DIR / "_meta.yaml").read_text(encoding="utf-8"))
    del data["well_known_ids"]
    path = tmp_path / "_meta.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ResourceLoadError, match="well_known_ids"):
        load_meta(path)


# ---- boot refusals name path:line ------------------------------------------------------------

BAD_ENTRIES: list[tuple[str, dict[str, Any], str]] = [
    ("duplicate_id", entry(id="211"), "duplicate id"),
    ("bad_tag", entry(tags=["not_a_tag"]), "tags"),
    ("county_suffix", entry(serves={"scope": "county", "states": ["VA"],
                                    "counties": ["Fairfax County"]}), "canonical"),
    ("national_with_states", entry(serves={"scope": "national", "states": ["VA"]}), "national"),
    ("phone_format", entry(phone="800-375-5283"), "phone"),
    ("missing_en", entry(what_it_does={"es": "Ayuda."}), "en"),
    ("empty_tags_without_pin", entry(tags=[]), "doc_type_pins"),
    ("unknown_checklist_key", entry(prepare_checklist_keys=["bring_unicorn"]), "checklist"),
    ("utm_url", entry(url="https://example.org/?utm_source=x"), "utm_"),
    ("fragment_url", entry(url="https://example.org/#top"), "fragment"),
    ("manual_verify_without_note", entry(verification_method="manual_verify"), "manual_verify"),
    ("prefixed_warning_key", entry(warnings=["warn.forms_are_free"]), "unprefixed"),
    ("unknown_warning_key", entry(warnings=["made_up_warning"]), "unknown warnings"),
    ("unknown_field", entry(colour="red"), "unknown fields"),
    ("future_verified_on", entry(verified_on="2027-01-01"), "verified_on"),
    ("too_old_verified_on", entry(verified_on="2025-12-31"), "verified_on"),
    ("bad_id", entry(id="Bad-Id"), "id"),
    ("never_show_overlap", entry(never_show_with_tags=["benefits_navigation"]), "overlaps"),
    ("forbidden_phrasing", entry(what_it_does={"en": "If you qualify, they help."}), "forbidden"),
    ("bad_zip3", entry(serves={"scope": "county", "states": ["VA"], "counties": ["Fairfax"],
                               "zip3": ["22"]}), "zip3"),
    ("city_without_county", entry(serves={"scope": "city", "states": ["VA"],
                                          "cities": ["Herndon"]}), "city"),
    ("bad_state", entry(serves={"scope": "state", "states": ["XX"]}), "state"),
]  # fmt: skip


@pytest.mark.parametrize(
    ("case", "bad", "fragment"), BAD_ENTRIES, ids=[c for c, _, _ in BAD_ENTRIES]
)
def test_bad_entry_refuses_boot_with_path_line(
    tmp_path: Path, case: str, bad: dict[str, Any], fragment: str
) -> None:
    directory = copy_seed(tmp_path)
    good = entry(id="zz_good_entry")
    path = write_entries(directory / "zz_bad.yaml", [good, bad])
    lines = path.read_text(encoding="utf-8").splitlines()
    bad_line = next(i + 1 for i, text in enumerate(lines) if i > 0 and text.startswith("- "))
    with pytest.raises(ResourceLoadError) as err:
        load_dir(directory)
    message = str(err.value)
    assert message.startswith(f"{path}:{bad_line}:"), message
    assert fragment in message, message


def test_yaml_syntax_error_names_path_and_line(tmp_path: Path) -> None:
    directory = copy_seed(tmp_path)
    path = directory / "zz_broken.yaml"
    path.write_text("- id: fine_entry\n  name: Fine\n- id: [unclosed\n", encoding="utf-8")
    with pytest.raises(ResourceLoadError) as err:
        load_dir(directory)
    assert str(err.value).startswith(f"{path}:")
    assert "YAML syntax error" in str(err.value)


def test_meta_reference_to_unknown_id_refuses(tmp_path: Path) -> None:
    directory = copy_seed(tmp_path)
    meta_path = directory / "_meta.yaml"
    data = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    data["well_known_ids"]["scam_card_phone"] = "no_such_id"
    meta_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ResourceLoadError, match="no_such_id"):
        load_dir(directory)


# ---- inactive entries, freshness, sidecars ---------------------------------------------------


def test_broken_entry_is_loaded_inactive(tmp_path: Path) -> None:
    directory = copy_seed(tmp_path)
    write_entries(directory / "zz_extra.yaml", [entry(id="zz_broken", link_health="broken")])
    repo = load_dir(directory)
    assert repo.count() == 102
    assert repo.get("zz_broken") is None
    assert "zz_broken" not in {r.id for r in repo.all()}
    assert "zz_broken" not in {r.id for r in repo.active()}
    assert any("zz_broken is broken" in w for w in repo.warnings)


def test_freshness_warns_after_120_days_and_excludes_after_365() -> None:
    repo = ResourceRepo.load(RESOURCES_DIR, today=SEED_TODAY + timedelta(days=150))
    assert len(repo.stale_ids()) == 101
    assert len(repo.active()) == 101
    assert any("> 120 days" in w for w in repo.warnings)


def test_entries_older_than_365_days_are_browsable_not_matchable(tmp_path: Path) -> None:
    directory = copy_seed(tmp_path)
    write_entries(directory / "zz_extra.yaml", [entry(id="zz_old", verified_on="2026-01-02")])
    later = SEED_TODAY + timedelta(days=100)  # 2027-01-05: zz_old is 368 days old
    repo = ResourceRepo.load(directory, today=later, prepare_path=RULES_DIR / "prepare.yaml")
    assert repo.get("zz_old") is not None
    assert repo.is_stale_excluded("zz_old")
    assert "zz_old" not in {r.id for r in repo.active()}


def _age_entry(directory: Path, resource_id: str, verified_on: str) -> None:
    """Rewrite one seed entry's ``verified_on`` in place (compact flow-mapping form)."""
    for path in directory.rglob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        start = text.find(f"id: {resource_id},")
        if start < 0:
            continue
        at = text.index("verified_on: ", start)
        end = at + len("verified_on: 2026-09-27")
        path.write_text(text[:at] + f"verified_on: {verified_on}" + text[end:], encoding="utf-8")
        return
    raise AssertionError(f"{resource_id} not found in the seed copy")


def test_tag_whose_only_carrier_is_over_365_days_old_boots_with_warning(tmp_path: Path) -> None:
    """RESOURCE_DB §8.1/§8.3.5: freshness never refuses boot; the stale carrier is not matched."""
    directory = copy_seed(tmp_path)
    _age_entry(directory, "uscourts_jury", "2026-01-02")  # sole jury_summons carrier + pin
    repo = ResourceRepo.load(
        directory, today=date(2027, 1, 10), prepare_path=RULES_DIR / "prepare.yaml"
    )
    assert repo.count() == 101
    assert repo.get("uscourts_jury") is not None  # still browsable
    assert repo.is_stale_excluded("uscourts_jury")
    assert "uscourts_jury" not in {r.id for r in repo.active()}
    assert any("jury_summons" in w and "365" in w for w in repo.warnings)
    assert any("uscourts_jury" in w and "_meta.yaml" in w for w in repo.warnings)
    items, _total = repo.list(tag=ResourceTag.jury_summons)
    assert [r.id for r in items] == ["uscourts_jury"]


def test_untouched_seed_still_boots_a_year_and_a_day_later() -> None:
    repo = ResourceRepo.load(
        RESOURCES_DIR, today=SEED_TODAY + timedelta(days=366),
        prepare_path=RULES_DIR / "prepare.yaml",
    )  # fmt: skip
    assert repo.count() == 101
    assert repo.active() == []
    assert len(repo.all()) == 101


def test_meta_reference_to_broken_entry_still_refuses(tmp_path: Path) -> None:
    directory = copy_seed(tmp_path)
    for path in directory.rglob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        start = text.find("id: uscourts_jury,")
        if start >= 0:
            at = text.index("link_health: ok", start)
            end = at + len("link_health: ok")
            path.write_text(text[:at] + "link_health: broken" + text[end:], encoding="utf-8")
    with pytest.raises(ResourceLoadError, match="uscourts_jury|jury_summons"):
        load_dir(directory)


def test_i18n_sidecar_is_merged_and_not_read_as_resources(tmp_path: Path) -> None:
    directory = copy_seed(tmp_path)
    sidecar = directory / "i18n" / "es.yaml"
    sidecar.parent.mkdir()
    sidecar.write_text(
        yaml.safe_dump({"inova_fa": {"what_it_does": "Ayuda con facturas del hospital."}}),
        encoding="utf-8",
    )
    repo = load_dir(directory)
    assert repo.count() == 101
    inova = repo.get("inova_fa")
    assert inova is not None and inova.what_it_does["es"].startswith("Ayuda")
    seed_inova = real_repo().get("inova_fa")
    assert seed_inova is not None and inova.what_it_does["en"] == seed_inova.what_it_does["en"]


def test_i18n_sidecar_unknown_id_refuses(tmp_path: Path) -> None:
    directory = copy_seed(tmp_path)
    sidecar = directory / "i18n" / "es.yaml"
    sidecar.parent.mkdir()
    sidecar.write_text(yaml.safe_dump({"nope": {"what_it_does": "x"}}), encoding="utf-8")
    with pytest.raises(ResourceLoadError) as err:
        load_dir(directory)
    assert str(err.value).startswith(f"{sidecar}:1:")
