"""``AI_PROVIDER=openai_compat`` settings and boot rules (free-ai-providers §4.2, §4.5, §4.6, §5.2):
loopback-only ``local``, production refusal, ``attested`` requirements and host denylist, the
``unpaid`` gate, deadline/timeout defaults, active model ids and the client time limits."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from proxyhealth_api.ai.provider import Task
from proxyhealth_api.ai.routing import route
from proxyhealth_api.contracts.enums import DataUseTier, Provider, ThinkingLevel
from proxyhealth_api.main import create_app
from proxyhealth_api.settings import (
    ATTESTED_HOST_DENYLIST,
    Settings,
    host_is_denylisted,
    is_loopback_host,
)
from tests.conftest import make_settings

KEY = "sk-very-secret-key-4242"


def compat(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "ai_provider": "openai_compat",
        "openai_compat_data_tier": "local",
        "openai_compat_model_label": "Qwen",
    }
    values.update(overrides)
    return make_settings(tmp_path, **values)


def attested(tmp_path: Path, host: str = "api.groq.com", **overrides: object) -> Settings:
    values: dict[str, object] = {
        "openai_compat_data_tier": "attested",
        "openai_compat_base_url": f"https://{host}/openai/v1",
        "openai_compat_api_key": KEY,
        "openai_compat_vendor_name": "Groq",
        "openai_compat_no_training_attested": True,
    }
    values.update(overrides)
    return compat(tmp_path, **values)


def refused(tmp_path: Path, **overrides: object) -> str:
    with pytest.raises(ValidationError) as info:
        compat(tmp_path, **overrides)
    text = str(info.value)
    assert KEY not in text  # hide_input_in_errors + messages that never name the key
    return text


# ------------------------------------------------------------------------- local (rule 1)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434/v1",
        "http://127.8.9.10:1234/v1/",
        "http://localhost:11434/v1",
        "http://[::1]:11434/v1",
        "http://LOCALHOST.:11434/v1",
    ],
)
def test_local_boots_on_a_loopback_base_url(tmp_path: Path, url: str) -> None:
    s = compat(tmp_path, openai_compat_base_url=url)
    assert s.provider is Provider.openai_compat and s.data_use_tier is DataUseTier.local
    assert s.real_documents_allowed is True and s.samples_only is False
    assert s.features.chat is True and s.features.real_documents_allowed is True
    assert not s.openai_compat_base_url.endswith("/")


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example.com/v1",
        "http://192.168.1.5:11434/v1",
        "http://10.0.0.2:11434/v1",
        "http://localhost.evil.example:11434/v1",
        "http://0.0.0.0:11434/v1",
    ],
)
def test_local_refuses_any_non_loopback_host(tmp_path: Path, url: str) -> None:
    text = refused(tmp_path, openai_compat_base_url=url, openai_compat_api_key=KEY)
    assert "loopback" in text


def test_local_needs_a_model_label(tmp_path: Path) -> None:
    assert "OPENAI_COMPAT_MODEL_LABEL" in refused(tmp_path, openai_compat_model_label="  ")


@pytest.mark.parametrize("model", ["gemma4:cloud", "gemma4:31b-cloud", "glm-5.3:CLOUD"])
def test_local_refuses_ollama_cloud_models(tmp_path: Path, model: str) -> None:
    assert "cloud" in refused(tmp_path, openai_compat_model_pro=model)
    assert "cloud" in refused(tmp_path, openai_compat_model_fast=model)


@pytest.mark.parametrize("url", ["ftp://127.0.0.1/v1", "127.0.0.1:11434/v1", "http:///v1"])
def test_base_url_must_be_http_with_a_host(tmp_path: Path, url: str) -> None:
    assert "http(s) URL" in refused(tmp_path, openai_compat_base_url=url)


def test_credentials_in_the_base_url_are_refused_without_echoing_them(tmp_path: Path) -> None:
    text = refused(tmp_path, openai_compat_base_url=f"http://user:{KEY}@127.0.0.1:11434/v1")
    assert "credentials" in text


def test_hosted_endpoint_needs_an_api_key(tmp_path: Path) -> None:
    text = refused(
        tmp_path, openai_compat_data_tier="unpaid", openai_compat_vendor_name="Groq",
        openai_compat_base_url="https://api.groq.com/openai/v1",
    )  # fmt: skip
    assert "OPENAI_COMPAT_API_KEY" in text


# -------------------------------------------------------------------------- production (rule 4)


@pytest.mark.parametrize("tier", ["local", "attested", "unpaid"])
def test_production_refuses_openai_compat(tmp_path: Path, tier: str) -> None:
    text = refused(
        tmp_path, env="production", openai_compat_data_tier=tier,
        openai_compat_vendor_name="V", openai_compat_no_training_attested=True,
    )  # fmt: skip
    assert "production" in text


def test_staging_allows_local_and_unpaid(tmp_path: Path) -> None:
    assert compat(tmp_path, env="staging").data_use_tier is DataUseTier.local
    s = compat(tmp_path, env="staging", openai_compat_data_tier="unpaid",
               openai_compat_vendor_name="Local test")  # fmt: skip
    assert s.data_use_tier is DataUseTier.unpaid
    s.validate_runtime()  # no GEMINI_KEYS needed outside development for openai_compat


# ----------------------------------------------------------------------- attested (rule 2)


def test_attested_boots_in_development_with_vendor_attestation_and_allowed_host(
    tmp_path: Path,
) -> None:
    s = attested(tmp_path)
    assert s.data_use_tier is DataUseTier.attested and s.real_documents_allowed is True
    assert s.samples_only is False and s.ai_vendor_name == "Groq"
    assert KEY not in repr(s) and KEY not in str(s.model_dump())


def test_attested_is_development_only(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="development"):
        attested(tmp_path, env="staging")


def test_attested_needs_the_vendor_name(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="OPENAI_COMPAT_VENDOR_NAME"):
        attested(tmp_path, openai_compat_vendor_name="")


def test_attested_needs_the_explicit_no_training_statement(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="OPENAI_COMPAT_NO_TRAINING_ATTESTED"):
        attested(tmp_path, openai_compat_no_training_attested=False)


@pytest.mark.parametrize(
    "host",
    [
        "api.deepseek.com", "open.bigmodel.cn", "dashscope.aliyuncs.cn", "api.moonshot.ai",
        "api.moonshot.cn", "api.kimi.ai", "kimi.ai", "api.minimax.io", "api.stepfun.ai",
        "integrate.api.nvidia.com", "generativelanguage.googleapis.com", "api.z.ai",
        "api.siliconflow.com", "qianfan.baidubce.com", "api.stepfun.com", "api.minimaxi.com",
        "api.minimax.chat",
    ],
)  # fmt: skip
def test_attested_refuses_denylisted_hosts(tmp_path: Path, host: str) -> None:
    with pytest.raises(ValidationError, match="ATTESTED_HOST_DENYLIST"):
        attested(tmp_path, host=host)


@pytest.mark.parametrize(
    "host",
    [
        "api.groq.com", "dashscope-intl.aliyuncs.com", "api.cerebras.ai", "nvidia.com",
        "zai.example.org",
    ],  # fmt: skip
)
def test_attested_allows_hosts_off_the_denylist(tmp_path: Path, host: str) -> None:
    assert attested(tmp_path, host=host).data_use_tier is DataUseTier.attested


def test_denylist_matching_rules() -> None:
    assert "*.cn" in ATTESTED_HOST_DENYLIST
    assert host_is_denylisted("a.b.cn") and host_is_denylisted("API.DEEPSEEK.COM.")
    assert not host_is_denylisted("cnn.com") and not host_is_denylisted("moonshotx.ai")
    assert host_is_denylisted("x.moonshot.y") and not host_is_denylisted("api.groq.com")


def test_loopback_detection() -> None:
    assert all(map(is_loopback_host, ["localhost", "127.0.0.1", "127.255.0.9", "::1"]))
    assert is_loopback_host("::ffff:127.0.0.1")
    assert not any(map(is_loopback_host, ["0.0.0.0", "10.0.0.1", "localhost.com", "", "::"]))


# ------------------------------------------------------------------------- unpaid (rule 3)


def test_unpaid_needs_a_vendor_name_and_is_samples_only(tmp_path: Path) -> None:
    assert "OPENAI_COMPAT_VENDOR_NAME" in refused(tmp_path, openai_compat_data_tier="unpaid")
    s = compat(tmp_path, openai_compat_data_tier="unpaid", openai_compat_vendor_name="Groq")
    assert s.data_use_tier is DataUseTier.unpaid and s.samples_only is True
    assert s.real_documents_allowed is False and s.features.chat is False
    bypass = compat(tmp_path, openai_compat_data_tier="unpaid", openai_compat_vendor_name="Groq",
                    allow_unpaid_real_documents=True)  # fmt: skip
    assert bypass.real_documents_allowed is True and bypass.samples_only is True


def test_unpaid_is_the_default_tier(tmp_path: Path) -> None:
    s = make_settings(tmp_path, ai_provider="openai_compat", openai_compat_vendor_name="Me")
    assert s.openai_compat_data_tier == "unpaid" and s.data_use_tier is DataUseTier.unpaid


# ------------------------------------------------------------- deadline, timeouts (rule 5, §4.6)


def test_unset_failover_deadline_is_raised_to_cover_one_call(tmp_path: Path) -> None:
    s = compat(tmp_path)
    assert s.openai_compat_timeout == 300 and s.failover_deadline_s == 310
    assert compat(tmp_path, openai_compat_timeout_s=60).failover_deadline_s == 100  # kept


def test_explicit_failover_deadline_must_cover_one_call(tmp_path: Path) -> None:
    assert "FAILOVER_DEADLINE_S" in refused(tmp_path, failover_deadline_s=100)
    assert compat(tmp_path, failover_deadline_s=400).failover_deadline_s == 400


def test_hosted_defaults_timeout_90_and_concurrency_4(tmp_path: Path) -> None:
    s = compat(
        tmp_path, openai_compat_data_tier="unpaid", openai_compat_vendor_name="Groq",
        openai_compat_base_url="https://api.groq.com/openai/v1", openai_compat_api_key=KEY,
    )  # fmt: skip
    assert (s.openai_compat_timeout, s.openai_compat_concurrency_limit) == (90, 4)
    assert s.failover_deadline_s == 100
    local = compat(tmp_path)
    assert local.openai_compat_concurrency_limit == 1
    assert compat(tmp_path, openai_compat_concurrency=2).openai_compat_concurrency_limit == 2


def test_blank_timeout_and_concurrency_mean_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_COMPAT_TIMEOUT_S", "")
    monkeypatch.setenv("OPENAI_COMPAT_CONCURRENCY", " ")
    s = Settings(_env_file=None, var_dir=tmp_path)
    assert s.openai_compat_timeout_s is None and s.openai_compat_concurrency is None


def test_client_timeouts_cover_the_server_budget_on_openai_compat(tmp_path: Path) -> None:
    t = compat(tmp_path).client_timeouts
    assert (t.analyze_s, t.troubleshoot_s, t.language_pack_s, t.chat_s) == (625, 625, 625, 625)
    assert t.default_s == 30
    base = make_settings(tmp_path).client_timeouts
    assert (base.analyze_s, base.troubleshoot_s, base.language_pack_s, base.chat_s,
            base.default_s) == (120, 60, 60, 30, 30)  # fmt: skip


# ---------------------------------------------------------- models, routing, degraded (6, §4.5)


def test_gemini_model_rules_never_apply_to_openai_compat_models(tmp_path: Path) -> None:
    s = compat(tmp_path, openai_compat_model_pro="qwen-2.5-latest",
               openai_compat_model_fast="gemini-2.5-flash")  # fmt: skip
    assert (s.active_model_pro, s.active_model_fast) == ("qwen-2.5-latest", "gemini-2.5-flash")
    assert "must not be empty" in refused(tmp_path, openai_compat_model_pro=" ")


def test_route_takes_model_ids_from_the_active_provider(tmp_path: Path) -> None:
    s = compat(tmp_path, openai_compat_model_pro="qwen3.5:9b", openai_compat_model_fast="q:2b")
    assert route(Task.analyze_single, settings=s).model_id == "qwen3.5:9b"
    assert route(Task.chat, settings=s).model_id == "q:2b"
    gemini = make_settings(tmp_path)
    assert route(Task.analyze_single, settings=gemini).model_id == "gemini-3.8-flash"


def test_thinking_is_reported_off_unless_mapped(tmp_path: Path) -> None:
    assert route(Task.analyze_single, settings=compat(tmp_path)).thinking is None
    mapped = compat(tmp_path, openai_compat_reasoning="mapped")
    assert route(Task.analyze_single, settings=mapped).thinking is ThinkingLevel.high
    assert route(Task.tag, settings=mapped).thinking is ThinkingLevel.minimal  # not gemini-3.8


def test_degraded_path_is_off_for_openai_compat(tmp_path: Path) -> None:
    s = compat(tmp_path, allow_degraded=True)
    assert s.degraded_enabled is False and s.features.degraded_fallback is False
    assert make_settings(tmp_path).degraded_enabled is True


def test_labels_per_provider(tmp_path: Path) -> None:
    s = compat(tmp_path, openai_compat_vendor_name="  Alibaba   Cloud ")
    assert (s.ai_model_label, s.ai_vendor_name) == ("Qwen", "Alibaba Cloud")
    assert (make_settings(tmp_path).ai_model_label, make_settings(tmp_path).ai_vendor_name) == (
        None, None,
    )  # fmt: skip
    gemini = make_settings(tmp_path, ai_provider="gemini")
    assert (gemini.ai_model_label, gemini.ai_vendor_name) == ("Gemini", "Google")


def test_openai_compat_fields_are_ignored_by_other_providers(tmp_path: Path) -> None:
    s = make_settings(tmp_path, openai_compat_base_url="https://api.example.com/v1",
                      openai_compat_data_tier="local")  # fmt: skip
    assert s.data_use_tier is DataUseTier.demo and s.provider is Provider.mock


async def test_app_refuses_to_build_with_a_remote_local_tier(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        create_app(compat(tmp_path, openai_compat_base_url="https://api.example.com/v1"))
