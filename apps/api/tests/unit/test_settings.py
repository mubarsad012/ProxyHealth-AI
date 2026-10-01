"""``settings.py`` boot rules (ARCHITECTURE §6.1; D-01, D-03, D-04; BUILD_PLAN §5.2 step 1)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from proxyhealth_api.contracts.enums import DataUseTier, Provider
from proxyhealth_api.main import create_app
from proxyhealth_api.settings import KeySlotConfig, Settings
from tests.conftest import make_settings


def keys(*billing: bool, same_project: bool = False) -> list[KeySlotConfig]:
    return [
        KeySlotConfig.model_validate(
            {"key": f"AIzaTEST{i:04d}", "project": "p" if same_project else f"p{i}", "billing": b}
        )
        for i, b in enumerate(billing)
    ]


def test_defaults_match_architecture_table(tmp_path: Path) -> None:
    s = make_settings(tmp_path)
    assert s.env == "development" and s.ai_provider == "mock"
    assert s.model_pro == "gemini-3.8-flash" and s.model_fast == "gemini-3.5-flash-lite"
    assert s.model_pro_degraded_thinking == "medium" and s.allow_degraded is True
    assert (s.max_pages, s.max_page_bytes, s.max_pdf_bytes, s.max_pdf_pages) == (
        12, 4_194_304, 12_582_912, 60,
    )  # fmt: skip
    assert (s.max_request_bytes, s.max_upstream_inline_bytes, s.max_chat_history) == (
        20_971_520, 18_874_368, 8,
    )  # fmt: skip
    assert (s.upstream_timeout_s, s.failover_deadline_s, s.translate_full_max_pages) == (90, 100, 4)
    assert (s.rate_limit_analyze_per_hour, s.rate_limit_analyze_per_day) == (20, 100)
    assert s.rate_limit_ip_per_minute == 60 and s.langpack_cache_ttl_days == 180
    assert s.rate_limit_ip_per_day == 1000 and s.trusted_proxy_hops == 0
    assert s.cors_origin_list == ["http://localhost:8081"]
    assert s.provider is Provider.mock and s.data_use_tier is DataUseTier.demo


@pytest.mark.parametrize(
    "model",
    ["gemini-1.5-pro", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-flash-latest", " "],
)
def test_forbidden_model_ids(tmp_path: Path, model: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path, model_pro=model)
    with pytest.raises(ValidationError):
        make_settings(tmp_path, model_fast=model)


def test_preview_pro_model_needs_every_key_billed(tmp_path: Path) -> None:
    ok = make_settings(
        tmp_path, ai_provider="gemini", gemini_keys=keys(True), model_pro="gemini-3.1-pro-preview"
    )
    assert ok.model_pro == "gemini-3.1-pro-preview"
    with pytest.raises(ValidationError, match="billed"):
        make_settings(
            tmp_path, ai_provider="gemini", gemini_keys=keys(True, False),
            model_pro="gemini-3.1-pro-preview",
        )  # fmt: skip


def test_projects_must_be_distinct(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="distinct"):
        make_settings(
            tmp_path, ai_provider="gemini", gemini_keys=keys(True, True, same_project=True)
        )


def test_empty_key_is_refused(tmp_path: Path) -> None:
    bad = [KeySlotConfig.model_validate({"key": " ", "project": "p", "billing": True})]
    with pytest.raises(ValidationError, match="empty key"):
        make_settings(tmp_path, ai_provider="gemini", gemini_keys=bad)


def test_production_rules(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="ALLOW_UNPAID_REAL_DOCUMENTS"):
        make_settings(tmp_path, env="production", allow_unpaid_real_documents=True)
    with pytest.raises(ValidationError, match="billing:false"):
        make_settings(tmp_path, env="production", ai_provider="gemini", gemini_keys=keys(False))
    allowed = make_settings(
        tmp_path, env="production", ai_provider="gemini", gemini_keys=keys(True, False),
        allow_unpaid_keys=True,
    )  # fmt: skip
    assert allowed.data_use_tier is DataUseTier.mixed
    assert allowed.features.real_documents_allowed is False
    assert allowed.unbilled_slot_indexes == [1]
    dev = make_settings(tmp_path, ai_provider="gemini", gemini_keys=keys(False))
    assert dev.data_use_tier is DataUseTier.unpaid  # development boots unbilled keys


def test_validate_runtime(tmp_path: Path) -> None:
    make_settings(tmp_path, ai_provider="gemini").validate_runtime()  # development: tier none
    with pytest.raises(ValueError, match="zero GEMINI_KEYS"):
        make_settings(tmp_path, ai_provider="gemini", env="staging").validate_runtime()
    with pytest.raises(ValueError, match="LATER"):
        make_settings(
            tmp_path, ai_provider="gemini_interactions", gemini_keys=keys(True)
        ).validate_runtime()


async def test_lifespan_refuses_to_boot_on_invalid_runtime(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path, ai_provider="gemini", env="staging"))
    with pytest.raises(ValueError):
        async with app.router.lifespan_context(app):
            pass


def test_tier_matrix_properties(tmp_path: Path) -> None:
    cases = {
        (True,): DataUseTier.paid,
        (True, True): DataUseTier.paid,
        (False,): DataUseTier.unpaid,
        (True, False): DataUseTier.mixed,
    }
    for billing, tier in cases.items():
        s = make_settings(tmp_path, ai_provider="gemini", gemini_keys=keys(*billing))
        assert s.data_use_tier is tier and s.provider is Provider.gemini
        assert s.real_documents_allowed is (tier is DataUseTier.paid)
    assert make_settings(tmp_path, ai_provider="gemini").data_use_tier is DataUseTier.none


def test_misc_validators(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path, log_level="loud")
    assert make_settings(tmp_path, log_level="WARNING").log_level == "warning"
    with pytest.raises(ValidationError):
        make_settings(tmp_path, mock_latency_min_ms=10, mock_latency_max_ms=5)
    with pytest.raises(ValidationError):
        make_settings(tmp_path, max_pages=0)
    with pytest.raises(ValidationError):
        make_settings(tmp_path, not_a_setting=1)  # extra="forbid"
    s = make_settings(tmp_path, cors_origins="http://a.test, https://b.test ,")
    assert s.cors_origin_list == ["http://a.test", "https://b.test"]


def test_gemini_keys_json_from_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = [
        {"key": "AIzaENV-A-1234", "project": "proj-a", "billing": True},
        {"key": "AIzaENV-B-5678", "project": "proj-b", "billing": False},
    ]
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_KEYS", json.dumps(raw))
    monkeypatch.setenv("VAR_DIR", str(tmp_path / "var"))
    s = Settings(_env_file=None)
    assert [k.project for k in s.gemini_keys] == ["proj-a", "proj-b"]
    assert s.data_use_tier is DataUseTier.mixed
    text = repr(s) + str(s.model_dump())
    assert "AIzaENV-A-1234" not in text and "AIzaENV-B-5678" not in text  # SecretStr


def test_install_hash_secret_is_random_per_process_when_unset() -> None:
    a = Settings(_env_file=None)
    b = Settings(_env_file=None)
    assert a.install_hash_secret.get_secret_value() != b.install_hash_secret.get_secret_value()


LEAKY_KEY = "AIzaSyA1b2C3d4E5f6G7h8I9j0KlMnOpQrStUvW"


@pytest.mark.parametrize(
    "raw",
    [
        [{"key": LEAKY_KEY}],  # missing project/billing
        [{"key": LEAKY_KEY, "project": "p1", "billing": "maybe"}],
        [
            {"key": LEAKY_KEY, "project": "p1", "billing": True},
            {"key": "AIzaSyOTHER", "project": "p1", "billing": True},  # duplicate project
        ],
        {"key": LEAKY_KEY},  # not a list
    ],
)
def test_malformed_gemini_keys_never_echo_the_key(
    monkeypatch: pytest.MonkeyPatch, raw: object
) -> None:
    """ARCHITECTURE §2.1: secrets never appear in logs — including the boot traceback."""
    monkeypatch.setenv("GEMINI_KEYS", json.dumps(raw))
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    text = str(exc.value) + repr(exc.value)  # what a boot traceback prints
    assert LEAKY_KEY not in text and LEAKY_KEY[:12] not in text


def test_unparseable_gemini_keys_json_never_echoes_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_KEYS", '[{"key":"' + LEAKY_KEY)
    with pytest.raises(ValidationError, match="JSON list") as exc:
        Settings(_env_file=None)
    assert LEAKY_KEY[:12] not in str(exc.value) + repr(exc.value)
    assert exc.value.__cause__ is None and exc.value.__context__ is None


def test_invalid_slot_model_hides_input_too() -> None:
    with pytest.raises(ValidationError) as exc:
        KeySlotConfig.model_validate({"key": LEAKY_KEY, "project": ""})
    assert LEAKY_KEY[:12] not in str(exc.value)


@pytest.mark.parametrize("blank", ["", "   "])
def test_empty_gemini_keys_means_no_slots(monkeypatch: pytest.MonkeyPatch, blank: str) -> None:
    """BUILD_PLAN §5.2 step 7: ``GEMINI_KEYS=`` boots (no slots) instead of a JSON error."""
    monkeypatch.setenv("GEMINI_KEYS", blank)
    s = Settings(_env_file=None)
    assert s.gemini_keys == [] and s.data_use_tier is DataUseTier.demo


def test_env_file_falls_back_to_apps_api_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repo-root commands read ``apps/api/.env``; the current directory's ``.env`` wins."""
    from proxyhealth_api import settings as settings_module

    assert settings_module.API_ENV_FILE == Path(settings_module.__file__).parents[1] / ".env"
    assert Settings.model_config["env_file"] == (settings_module.API_ENV_FILE, ".env")
    api_env = tmp_path / "api" / ".env"
    api_env.parent.mkdir()
    api_env.write_text("ADMIN_TOKEN=from-api-dotenv\nCONSENT_VERSION=2026-01-01\n")
    elsewhere = tmp_path / "repo-root"
    elsewhere.mkdir()
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("CONSENT_VERSION", raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", (api_env, ".env"))
    monkeypatch.chdir(elsewhere)
    assert Settings().admin_token.get_secret_value() == "from-api-dotenv"
    (elsewhere / ".env").write_text("ADMIN_TOKEN=from-cwd-dotenv\n")
    s = Settings()
    assert s.admin_token.get_secret_value() == "from-cwd-dotenv"
    assert s.consent_version == "2026-01-01"  # still read from apps/api/.env
