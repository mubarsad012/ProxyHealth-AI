"""``packs/qa.py`` rules and the bundled packs (D-25; BUILD_PLAN §5.2 step 6)."""

import json
from pathlib import Path

import pytest

from proxyhealth_api.contracts.langpack import LanguagePack
from proxyhealth_api.packs.base import BasePack, pack_etag
from proxyhealth_api.packs.qa import check_pack, check_string, max_length, merge_with_fallback
from proxyhealth_api.settings import DATA_DIR

LANGPACKS = DATA_DIR / "langpacks"
REQUIRED_BUNDLED = ("es", "prs", "ar", "ps")
BUNDLED = sorted(
    p.stem for p in LANGPACKS.glob("*.json") if not p.name.startswith("_") and p.stem != "en"
)


def checks(key: str, english: str, value: str) -> set[str]:
    return {i.check for i in check_string(key, english, value)}


def test_good_translation_passes() -> None:
    english, spanish = "Try again in {minutes} minutes.", "Intente en {minutes} minutos."
    assert checks("err.quota", english, spanish) == set()


def test_empty() -> None:
    assert checks("a.b", "Hello", "  ") == {"empty"}
    assert checks("a.b", "", "") == set()


def test_placeholders_must_match_exactly() -> None:
    assert checks("a.b", "Due {date}", "Vence {fecha}") == {"placeholders"}
    assert checks("a.b", "Due {date}", "Vence") == {"placeholders"}
    assert checks("a.b", "{n} of {max_pages}", "{max_pages} de {n}") == set()  # order is free


def test_length_ratio_with_short_string_slack() -> None:
    english = "Take a photo of your paper now"  # 30 chars → 48 allowed
    assert max_length("home.cta", english) == 48
    assert checks("home.cta", english, "x" * 48) == set()
    assert checks("home.cta", english, "x" * 49) == {"length"}
    assert max_length("btn.ok", "OK") == 18  # slack for very short strings
    assert max_length("btn.long_label_here", "x" * 40) == 80  # 2x for buttons
    assert checks("btn.cancel", "Cancel", "Cancelar") == set()


def test_html_and_markup() -> None:
    assert checks("a.b", "Hello", "<b>Hola</b>") == {"html"}
    assert checks("a.b", "Hello", "Hola &nbsp;") == {"html"}


def test_digit_runs_are_phone_guard() -> None:
    assert checks("a.b", "Call 911", "Llame al 911") == set()
    assert checks("a.b", "Call for help", "Llame al 555 1234") == {"digits"}
    assert checks("a.b", "Call 988", "اتصل بـ ٩٨٨") == set()  # Arabic-Indic digits normalized
    assert checks("a.b", "Call a helpline", "اتصل بـ ٩٨٨٧٧") == {"digits"}
    assert checks("a.b", "Page {page} of {n}", "Página {page} de {n}") == set()


def test_check_pack_and_merge_fill_english() -> None:
    base = {"a": "Hello", "b": "Due {date}", "c": "Bye"}
    report = check_pack(base, {"a": "Hola", "b": "Vence"})
    assert report.missing == ["c"] and report.failed_keys == ["b"]
    assert report.fallback_keys == ["b", "c"] and not report.ok
    strings, fallback, _ = merge_with_fallback(base, {"a": "Hola", "b": "Vence"})
    assert strings == {"a": "Hola", "b": "Due {date}", "c": "Bye"}
    assert fallback == ["b", "c"]


def test_required_bundled_packs_exist() -> None:
    missing = [tag for tag in REQUIRED_BUNDLED if not (LANGPACKS / f"{tag}.json").is_file()]
    assert not missing, f"bundled packs missing: {missing}"


@pytest.mark.parametrize("tag", BUNDLED)
def test_bundled_pack_passes_qa(tag: str) -> None:
    base = BasePack.load(LANGPACKS / "en.json")
    path: Path = LANGPACKS / f"{tag}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    pack = LanguagePack.model_validate(raw)
    assert pack.language_tag == tag and pack.source == "bundled"
    assert pack.machine_translated is True and pack.reviewed_by is None
    report = check_pack(base.strings, pack.strings)
    assert not report.issues, [f"{i.key}: {i.check} ({i.detail})" for i in report.issues[:20]]
    # en.json may grow while packs are authored; the server fills new keys with English
    # (PackCache rebases), and `scripts/gen_packs.py --rebase` records them as fallback_keys.
    assert len(report.missing) <= 0.05 * len(base.strings), report.missing[:20]
    assert set(pack.strings) <= set(base.strings), sorted(set(pack.strings) - set(base.strings))
    assert pack.etag == pack_etag(tag, pack.pack_version, pack.strings)
    assert pack.strings["app.name"] == base.strings["app.name"]
