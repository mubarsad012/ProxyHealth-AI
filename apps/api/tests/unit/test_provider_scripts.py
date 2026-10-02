"""``scripts/provider_check.py`` and the ``--provider openai_compat`` switches of
``scripts/spike_schema.py`` / ``scripts/eval_golden.py`` (free-ai-providers §4.10). No network:
the openai_compat provider's client is pointed at an ``httpx.MockTransport``."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

from proxyhealth_api.ai.openai_compat import OpenAICompatProvider
from proxyhealth_api.demo.fixtures import FixtureStore
from proxyhealth_api.settings import DATA_DIR
from tests.conftest import make_settings
from tests.contract.test_openai_compat_config import FakeModel

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
SAMPLE = "medicaid_address_confirmation"


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up there
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def check() -> ModuleType:
    return load("provider_check")


def env(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def local_env(monkeypatch: pytest.MonkeyPatch) -> None:
    env(monkeypatch, AI_PROVIDER="openai_compat", OPENAI_COMPAT_DATA_TIER="local",
        OPENAI_COMPAT_MODEL_LABEL="Qwen")  # fmt: skip


def fake_provider(module: ModuleType, monkeypatch: pytest.MonkeyPatch, model: Any) -> None:
    real = module.build_provider

    def build(*args: Any, **kwargs: Any) -> Any:
        provider, keypool = real(*args, **kwargs)
        if isinstance(provider, OpenAICompatProvider):
            provider._client = httpx.AsyncClient(transport=httpx.MockTransport(model))
        return provider, keypool

    monkeypatch.setattr(module, "build_provider", build)


def printed_sentences() -> list[str]:
    fx = FixtureStore.load(DATA_DIR / "fixtures").get(SAMPLE)
    assert fx is not None
    out = fx.analysis_out("en")
    assert out is not None
    return [b.text for b in out.blocks if len(b.text) > 12] + [out.summary_body_en]


# ---------------------------------------------------------------------------- provider_check


def test_provider_check_on_the_mock_is_content_free(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env(monkeypatch, AI_PROVIDER="mock", MOCK_LATENCY_MIN_MS="0", MOCK_LATENCY_MAX_MS="0")
    assert check.main([]) == 0
    out = capsys.readouterr().out
    assert f"{SAMPLE}: ok schema_valid=yes" in out and "verified=" in out
    assert not any(text in out for text in printed_sentences())


def test_provider_check_runs_the_local_model_and_reports_the_json_mode(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    local_env(monkeypatch)
    model = FakeModel()
    fake_provider(check, monkeypatch, model)
    assert check.main(["--json"]) == 0
    raw = capsys.readouterr().out
    report = json.loads(raw[raw.index("{\n"):])
    assert report["provider"] == "openai_compat" and report["data_use_tier"] == "local"
    assert report["host"] == "127.0.0.1" and "11434" not in raw
    paper = report["papers"][0]
    assert paper["ok"] and paper["schema_valid"] and paper["verified_facts"] > 0
    assert paper["calls"][0]["task"] == "analyze_single"
    assert paper["calls"][0]["json_mode"] == "json_schema"
    assert not any(text in raw for text in printed_sentences())


def test_provider_check_image_runs_only_on_real_paper_tiers(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    page = DATA_DIR / "fixtures" / SAMPLE / "page-1.png"
    env(monkeypatch, AI_PROVIDER="openai_compat", OPENAI_COMPAT_VENDOR_NAME="Groq")
    assert check.main(["--image", str(page)]) == 2  # unpaid: samples only
    assert "--image needs" in capsys.readouterr().err
    local_env(monkeypatch)
    fake_provider(check, monkeypatch, FakeModel())
    assert check.main(["--image", str(page)]) == 0
    out = capsys.readouterr().out
    assert "image: ok schema_valid=yes" in out


def test_provider_check_refuses_unknown_fixtures_and_unreadable_images(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env(monkeypatch, AI_PROVIDER="mock")
    assert check.main(["--fixture", "nope"]) == 2
    local_env(monkeypatch)
    junk = tmp_path / "junk.bin"
    junk.write_bytes(b"not a picture")
    assert check.main(["--image", str(junk)]) == 2
    assert check.main(["--image", str(tmp_path / "missing.png")]) == 2


def test_provider_check_fails_when_the_model_is_unusable(
    check: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    local_env(monkeypatch)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    fake_provider(check, monkeypatch, down)
    assert check.main([]) == 1
    assert "FAILED (503 provider_not_configured)" in capsys.readouterr().out


# ----------------------------------------------------------------- spike_schema + eval_golden


async def test_spike_schema_runs_against_openai_compat(tmp_path: Path) -> None:
    spike = load("spike_schema")
    settings = make_settings(
        tmp_path, ai_provider="openai_compat", openai_compat_data_tier="local",
        openai_compat_model_label="Qwen",
    )  # fmt: skip
    service, recorder = spike.build_service(settings)
    assert isinstance(recorder.inner, OpenAICompatProvider)
    recorder.inner._client = httpx.AsyncClient(transport=httpx.MockTransport(FakeModel()))
    fx = spike.SpikeFixture(SAMPLE, "document", [(DATA_DIR / "fixtures" / SAMPLE / "page-1.png")
                                                 .read_bytes()])  # fmt: skip
    report = await spike.run_spike(service, recorder, settings, [fx], probe_tasks=False)
    assert report.model_pro == "qwen3.5:4b" and report.fixtures[0].mode == "single"
    await recorder.inner.aclose()


def test_spike_schema_openai_compat_refuses_a_bad_configuration(tmp_path: Path) -> None:
    spike = load("spike_schema")
    bad = make_settings(tmp_path, openai_compat_data_tier="local")  # mock; no model label
    assert spike.main(["--provider", "openai_compat"], settings=bad) == 2
    assert spike.main([], settings=make_settings(tmp_path)) == 2  # gemini default: no keys


def test_eval_golden_openai_compat_refuses_a_bad_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    golden = load("eval_golden")
    env(monkeypatch, OPENAI_COMPAT_DATA_TIER="local")  # no OPENAI_COMPAT_MODEL_LABEL
    assert golden.main(["--provider", "openai_compat", "--fixture", SAMPLE]) == 2
    assert "OPENAI_COMPAT_* configuration refused" in capsys.readouterr().err
