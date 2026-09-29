"""WP0 — every language-pack key the server emits must exist in ``en.json``.

Scans ``proxyhealth_api/**/*.py`` and ``data/**/*.yaml`` for string literals shaped like a
server-emitted pack key (``status_note.*``, ``why.*``, ``notes.*``, ``warn.*``, ``prepare.*``,
``fixed.*``, ``err.*``, ``urgency.*``, ``scam.*``, ``chat.refusal.*``, ``chat.refer.*``,
``clerk.*``, ``fixture.*``) and asserts each one is a key of ``data/langpacks/en.json``.
Also asserts the ``en.json`` invariants from BUILD_PLAN §4.4 / Appendix C and the
``languages.yaml`` font invariant from Appendix E.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

API_ROOT = Path(__file__).resolve().parents[2]
EN_JSON = API_ROOT / "data" / "langpacks" / "en.json"
CONTEXTS_JSON = API_ROOT / "data" / "langpacks" / "_contexts.json"
LANGUAGES_YAML = API_ROOT / "data" / "languages.yaml"
FONTS_DIR = API_ROOT / "data" / "fonts"
PACKAGE_DIR = API_ROOT / "proxyhealth_api"
DATA_DIR = API_ROOT / "data"

SERVER_KEY_RE = re.compile(
    r"^(status_note|why|notes|warn|prepare|fixed|err|urgency|scam|chat\.refusal|chat\.refer|clerk|fixture)"
    # a.b.c — but not filename-like literals such as prepare.yaml or deadlines.json
    r"\.(?!(?:[a-z0-9_.]*\.)?(?:ya?ml|json|py|md|txt)$)[a-z0-9_.]+$"
)
# Python string literals ('…' or "…") that might hold a pack key; short, single-line, no escapes.
PY_LITERAL_RE = re.compile(r"""(?<![\w.])(?:"([^"\\\n]{3,120})"|'([^'\\\n]{3,120})')""")
# YAML: quoted scalars, plus bare scalars that look like keys (after ':' or '- ').
YAML_LITERAL_RE = re.compile(
    r"""(?:"([^"\\\n]{3,120})"|'([^'\\\n]{3,120})'|(?:^|[:\-]\s+)([a-z_]+(?:\.[a-z0-9_]+)+)(?=\s|$|,|\]))""",
    re.MULTILINE,
)

FLAT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")
IDENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _load_en() -> dict[str, str]:
    def reject_duplicates(pairs: list[tuple[str, str]]) -> dict[str, str]:
        d = dict(pairs)
        if len(d) != len(pairs):
            seen: set[str] = set()
            dupes: set[str] = set()
            for k, _ in pairs:
                (dupes if k in seen else seen).add(k)
            raise AssertionError(f"duplicate keys in en.json: {sorted(dupes)}")
        return d

    with EN_JSON.open(encoding="utf-8") as f:
        data: dict[str, str] = json.load(f, object_pairs_hook=reject_duplicates)
    return data


@pytest.fixture(scope="module")
def en() -> dict[str, str]:
    return _load_en()


def _collect_server_keys() -> dict[str, set[str]]:
    """Return {key: {"<file>:<line>", …}} for every server-emitted-looking literal."""
    found: dict[str, set[str]] = {}

    def note(key: str, where: str) -> None:
        if SERVER_KEY_RE.match(key):
            found.setdefault(key, set()).add(where)

    def scan(path: Path, pattern: re.Pattern[str]) -> None:
        rel = path.relative_to(API_ROOT)
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in pattern.finditer(line):
                literal = next((g for g in m.groups() if g), "")
                note(literal, f"{rel}:{lineno}")

    if PACKAGE_DIR.is_dir():
        for path in sorted(PACKAGE_DIR.rglob("*.py")):
            scan(path, PY_LITERAL_RE)
    if DATA_DIR.is_dir():
        for path in sorted(DATA_DIR.rglob("*.yaml")):
            scan(path, YAML_LITERAL_RE)
    return found


def test_en_json_loads_with_unique_flat_keys(en: dict[str, str]) -> None:
    assert en, "en.json is empty"
    bad = [k for k in en if not FLAT_KEY_RE.match(k)]
    assert not bad, f"keys must be flat `area.name[.sub]`: {bad}"
    assert list(en) == sorted(en), "en.json must be written with sort_keys=True"
    not_str = [k for k, v in en.items() if not isinstance(v, str) or not v.strip()]
    assert not not_str, f"every value must be a non-empty string: {not_str}"


def test_langpack_adapting_is_verbatim(en: dict[str, str]) -> None:
    assert en["langpack.adapting"] == "Adapting system environment to your language..."


def test_placeholders_are_well_formed(en: dict[str, str]) -> None:
    bad: list[str] = []
    for key, text in en.items():
        if text.count("{") != text.count("}"):
            bad.append(f"{key}: unbalanced braces")
            continue
        for name in PLACEHOLDER_RE.findall(text):
            if not IDENT_RE.match(name):
                bad.append(f"{key}: bad placeholder {{{name}}}")
    assert not bad, bad


def test_contexts_json_keys_exist(en: dict[str, str]) -> None:
    with CONTEXTS_JSON.open(encoding="utf-8") as f:
        contexts = json.load(f)
    assert isinstance(contexts, dict)
    missing = sorted(k for k in contexts if k not in en)
    assert not missing, f"_contexts.json refers to keys absent from en.json: {missing}"
    assert all(isinstance(v, str) for v in contexts.values())


def test_server_emitted_keys_exist(en: dict[str, str]) -> None:
    found = _collect_server_keys()
    missing = {k: sorted(v) for k, v in found.items() if k not in en}
    assert not missing, (
        "server code / data emits pack keys missing from en.json "
        "(WP0 adds keys on a CL-nnn request):\n"
        + "\n".join(f"  {k}  <- {', '.join(w)}" for k, w in sorted(missing.items()))
    )


def test_error_code_keys_exist(en: dict[str, str]) -> None:
    """One ``err.<code>`` per API_CONTRACT §1 ``ErrorCode`` value, plus client network/timeout."""
    codes = [
        "invalid_request", "too_many_pages", "pdf_too_long", "unauthorized",
        "unpaid_tier_real_documents_disabled", "not_found", "pack_version_mismatch",
        "payload_too_large", "unsupported_media_type", "content_blocked",
        "language_unresolved", "consent_required", "rate_limited", "quota_exhausted",
        "internal", "model_output_invalid", "provider_not_configured", "upstream_unavailable",
    ]
    try:
        from proxyhealth_api.contracts.enums import ErrorCode
    except ImportError:  # contracts may not exist yet on day 0
        pass
    else:
        codes = [str(c.value) for c in ErrorCode]
    missing = [f"err.{c}" for c in codes if f"err.{c}" not in en]
    assert not missing, missing
    assert "err.network" in en and "err.timeout" in en


def test_fixture_titles_exist(en: dict[str, str]) -> None:
    ids = [
        "medicaid_address_confirmation", "uscis_i797c_receipt_i765", "uscis_rfe_87d",
        "nta_hearing_date", "inova_final_notice", "insurance_denial_180d", "prescription_label",
        "school_immunization_notice", "va_pay_or_quit_14d", "snap_interview_notice",
        "irs_cp_notice", "jury_summons", "scam_gift_card_letter", "blurry_unreadable_page",
        "spanish_lease", "w2_form", "traffic_court_notice", "portal_file_too_large",
    ]
    assert len(ids) == 18
    missing = [f"fixture.{i}" for i in ids if f"fixture.{i}" not in en]
    assert not missing, missing


def test_languages_yaml_font_hints_match_bundled_fonts() -> None:
    with LANGUAGES_YAML.open(encoding="utf-8") as f:
        langs = yaml.safe_load(f)
    assert isinstance(langs, dict) and "en" in langs and "rhg" in langs
    required = {
        "name_native", "name_en", "direction", "script", "digit_system",
        "font_hint", "tier", "tts_tag", "tts_fallback_tag",
    }
    for tag, info in langs.items():
        assert set(info) == required, f"{tag}: fields {sorted(set(info) ^ required)}"
        assert info["direction"] in {"ltr", "rtl"}, tag
        assert info["tier"] in {1, 2, 3}, tag
    hints = {info["font_hint"] for info in langs.values() if info["font_hint"] is not None}
    assert len(hints) == 9, sorted(hints)
    families = {p.stem.split("-")[0] for p in FONTS_DIR.glob("*.ttf")}
    assert hints <= families, f"font_hint values without a TTF: {sorted(hints - families)}"
    for family in hints:
        assert (FONTS_DIR / f"{family}-Regular.ttf").exists(), family
        assert (FONTS_DIR / f"{family}-Bold.ttf").exists(), family
