"""Golden-test helpers (BUILD_PLAN §4.1 ``tests/<dir>/_fixtures_<wp>.py``; imported explicitly).

Builds ``PipelineDeps`` around a call-counting ``MockProvider`` with the fixture's frozen
``today`` as the clock, and runs ``run_analysis`` / ``run_troubleshoot`` exactly as the router
does. ``PipelineDeps`` is WP2's dataclass and may gain fields while WP2 builds; unknown required
fields make the pipeline tests xfail with the field name instead of erroring.
"""

from __future__ import annotations

import base64
import dataclasses
import importlib.util
import re
from collections.abc import Callable
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any

from proxyhealth_api.ai.failover import AIService
from proxyhealth_api.ai.mock import MockProvider
from proxyhealth_api.ai.provider import StructuredResult
from proxyhealth_api.analysis.pipeline import PipelineDeps, run_analysis
from proxyhealth_api.analysis.troubleshoot_pipeline import run_troubleshoot
from proxyhealth_api.contracts.analysis import AnalysisResult, AnalyzeRequest
from proxyhealth_api.contracts.common import PageInput
from proxyhealth_api.contracts.troubleshoot import TroubleshootRequest, TroubleshootResult
from proxyhealth_api.demo.fixtures import Fixture, FixtureStore
from proxyhealth_api.resources.loader import ResourceRepo
from proxyhealth_api.resources.rules_repo import RulesRepo
from proxyhealth_api.settings import DATA_DIR, Settings
from tests.conftest import make_settings

STORE = FixtureStore.load(DATA_DIR / "fixtures")
RESOURCES = ResourceRepo.load(DATA_DIR / "resources")
RULES = RulesRepo.load(DATA_DIR / "rules")

# Same shapes as AI_PROMPTS §11.3 (phones, URLs/bare domains, e-mails).
PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
URL_RE = re.compile(r"https?://\S+|www\.\S+|\b[\w-]+\.(?:gov|org|com|net|us|edu|info)\b(?:/\S*)?")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")


def has_module(name: str) -> bool:
    """True when a WP2/WP3 module the assertion depends on exists on disk."""
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


WP2_MODULES = ("urgency", "deadline_rules", "scam", "fixed_notices", "clerk", "contacts_filter")


def pipeline_wired() -> bool:
    """True once ``analysis/pipeline.py`` references every WP2 §11 module (not just on disk)."""
    import sys

    import proxyhealth_api.analysis.pipeline as pipeline

    wanted = {f"proxyhealth_api.analysis.{m}" for m in WP2_MODULES}
    if not all(has_module(m) for m in wanted):
        return False
    used: set[str] = set()
    for value in vars(pipeline).values():
        name = getattr(value, "__module__", None) or getattr(value, "__name__", None)
        if isinstance(name, str) and name in wanted:
            used.add(name)
    return used == wanted and all(m in sys.modules for m in wanted)


WP2_PIPELINE = pipeline_wired()


def cases() -> list[tuple[str, str]]:
    return [(f.id, lang) for f in STORE.all() for lang in f.languages]


def document_cases() -> list[tuple[str, str]]:
    return [(fid, lang) for fid, lang in cases() if fixture(fid).kind == "document"]


def screenshot_cases() -> list[tuple[str, str]]:
    return [(fid, lang) for fid, lang in cases() if fixture(fid).kind == "screenshot"]


def fixture(fid: str) -> Fixture:
    found = STORE.get(fid)
    assert found is not None, fid
    return found


def frozen_clock(fx: Fixture) -> Callable[[], datetime]:
    moment = datetime.combine(fx.today, time(14, 0), tzinfo=UTC)
    return lambda: moment


class CountingMock(MockProvider):
    """The real mock, plus a call counter (the unreadable fixture must cost exactly one call)."""

    def __init__(self, store: FixtureStore, settings: Settings) -> None:
        super().__init__(store, settings)
        self.calls = 0

    async def generate_structured(self, **kwargs: Any) -> StructuredResult:
        self.calls += 1
        return await super().generate_structured(**kwargs)


class DepsUnavailable(Exception):
    """``PipelineDeps`` grew a required field these helpers do not know yet."""


def build_deps(fx: Fixture, tmp_path: Path) -> tuple[PipelineDeps, CountingMock]:
    settings = make_settings(tmp_path)
    provider = CountingMock(STORE, settings)
    known: dict[str, Any] = {
        "settings": settings,
        "ai": AIService(provider, None, settings),
        "resources": RESOURCES,
        "rules": RULES,
        "fixtures": STORE,
        "request_id": f"golden-{fx.id}",
        "data_use_tier": settings.data_use_tier,
        "clock": frozen_clock(fx),
    }
    kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(PipelineDeps):
        if f.name in known:
            kwargs[f.name] = known[f.name]
        elif f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            raise DepsUnavailable(f.name)
    return PipelineDeps(**kwargs), provider


def state_of(fx: Fixture) -> str | None:
    value = fx.expected.get("state")
    return str(value) if value else None


async def analyze(fx: Fixture, lang: str, tmp_path: Path) -> tuple[AnalysisResult, int]:
    deps, provider = build_deps(fx, tmp_path)
    req = AnalyzeRequest(
        pages=[], target_language=lang, client_platform="web", demo_sample_id=fx.id,
        state=state_of(fx),
    )  # fmt: skip
    result = await run_analysis(req, deps)
    return AnalysisResult.model_validate(result.model_dump()), provider.calls


async def troubleshoot(fx: Fixture, lang: str, tmp_path: Path) -> TroubleshootResult:
    deps, _ = build_deps(fx, tmp_path)
    shot = PageInput.model_validate(
        {"mime_type": "image/png", "data_base64": base64.b64encode(fx.page_png(1)).decode()}
    )
    req = TroubleshootRequest(
        screenshot=shot, target_language=lang, client_platform="android", demo_sample_id=fx.id
    )
    result = await run_troubleshoot(req, deps)
    return TroubleshootResult.model_validate(result.model_dump())


def contacts_in(text: str) -> list[str]:
    return [m.group(0) for r in (PHONE_RE, URL_RE, EMAIL_RE) for m in r.finditer(text)]


def digits(text: str) -> str:
    return re.sub(r"\D", "", text)


__all__ = [
    "STORE",
    "WP2_PIPELINE",
    "CountingMock",
    "DepsUnavailable",
    "analyze",
    "build_deps",
    "cases",
    "contacts_in",
    "digits",
    "document_cases",
    "fixture",
    "frozen_clock",
    "has_module",
    "screenshot_cases",
    "troubleshoot",
]
