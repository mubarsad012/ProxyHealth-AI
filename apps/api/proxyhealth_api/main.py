"""App factory (ARCHITECTURE §2.1; BUILD_PLAN §4.1). ``create_app(settings=None)`` and ``app``.

``create_app`` never touches globals: tests pass ``Settings(...)`` and run the lifespan. The
lifespan refuses to boot on an invalid configuration (``Settings.validate_runtime``), a bad
resource/rules YAML or an unreadable base pack, and persists the key pool on shutdown.
"""

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from proxyhealth_api import __version__
from proxyhealth_api.ai.failover import AIService
from proxyhealth_api.ai.gemini import build_gemini_stack
from proxyhealth_api.ai.keypool import KeyPool
from proxyhealth_api.ai.mock import MockProvider
from proxyhealth_api.ai.provider import AIProvider
from proxyhealth_api.ai.recording import wrap_if_enabled
from proxyhealth_api.demo.fixtures import FixtureStore
from proxyhealth_api.errors import install_handlers
from proxyhealth_api.feedback.store import FeedbackStore
from proxyhealth_api.logging_ import configure_logging, log_event, serving
from proxyhealth_api.middleware import install_middlewares
from proxyhealth_api.packs.base import BasePack, LanguageTable
from proxyhealth_api.packs.cache import PackCache
from proxyhealth_api.ratelimit import RateLimiter
from proxyhealth_api.resources.loader import ResourceRepo
from proxyhealth_api.resources.rules_repo import RulesRepo
from proxyhealth_api.routers import ALL_ROUTERS
from proxyhealth_api.settings import DATA_DIR, Settings

_AUTO_422_SCHEMAS = ("HTTPValidationError", "ValidationError")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def build_provider(
    settings: Settings, fixtures: FixtureStore, clock: Callable[[], datetime]
) -> tuple[AIProvider, KeyPool | None]:
    """Mock, or Gemini + key pool (CL-017), wrapped by WP7's recorder when enabled (CL-020).

    ``AI_PROVIDER=gemini`` with zero slots (``ENV=development`` only) gets the 503 stand-in.
    """
    if settings.ai_provider == "mock":
        return MockProvider(fixtures, settings), None
    provider, keypool = build_gemini_stack(settings, clock=clock)
    return wrap_if_enabled(provider, settings), keypool


def _build_state(app: FastAPI, settings: Settings) -> None:
    """Order per ARCHITECTURE §2.1: validators → resources → rules → packs → fixtures → AI."""
    settings.validate_runtime()
    clock = _utcnow
    settings.var_dir.mkdir(parents=True, exist_ok=True)
    app.state.resources = ResourceRepo.load(DATA_DIR / "resources")
    app.state.rules = RulesRepo.load(DATA_DIR / "rules")
    langpacks_dir = DATA_DIR / "langpacks"
    base = BasePack.load(langpacks_dir / "en.json")
    languages = LanguageTable.load(DATA_DIR / "languages.yaml", langpacks_dir)
    app.state.packs = base
    app.state.languages = languages
    pack_cache = PackCache(
        settings.var_dir / "langpacks",
        langpacks_dir=langpacks_dir,
        base=base,
        languages=languages,
        ttl_days=settings.langpack_cache_ttl_days,
        clock=clock,
    )
    pack_cache.prune()
    app.state.pack_cache = pack_cache
    fixtures = FixtureStore.load(DATA_DIR / "fixtures")
    app.state.fixtures = fixtures
    provider, keypool = build_provider(settings, fixtures, clock)
    app.state.provider = provider
    app.state.keypool = keypool
    app.state.ai = AIService(provider, keypool, settings)
    app.state.ratelimiter = RateLimiter(settings)
    app.state.feedback_store = FeedbackStore(settings.var_dir / "feedback_counts.sqlite")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings if settings is not None else Settings()
    configure_logging(resolved.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _build_state(app, resolved)
        log_event(route="startup", provider=resolved.provider, data_use_tier=resolved.data_use_tier)
        for index in resolved.unbilled_slot_indexes:  # D-01: name every unbilled slot at boot
            log_event(route="startup.unbilled_slot", slot_index=index)
        with serving():  # requests (user content) from here on: stdlib records lose their args
            yield
        keypool: KeyPool | None = getattr(app.state, "keypool", None)
        if keypool is not None:
            keypool.persist()

    app = FastAPI(
        title="ProxyHealth AI API",
        version=__version__,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = resolved
    install_handlers(app)
    install_middlewares(app, resolved)
    for router in ALL_ROUTERS:
        app.include_router(router)
    app.openapi = lambda: openapi_schema(app)  # type: ignore[method-assign]
    return app


def openapi_schema(app: FastAPI) -> dict[str, Any]:
    """FastAPI's schema minus the automatic 422 ``HTTPValidationError`` (we answer 400 instead)."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title, version=app.version, openapi_version=app.openapi_version,
        description=app.description, routes=app.routes,
    )  # fmt: skip
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            responses = operation.get("responses", {})
            auto = responses.get("422", {})
            content = auto.get("content", {}).get("application/json", {})
            ref = content.get("schema", {}).get("$ref", "")
            if ref.endswith("/HTTPValidationError"):
                del responses["422"]
    schemas = schema.get("components", {}).get("schemas", {})
    for name in _AUTO_422_SCHEMAS:
        schemas.pop(name, None)
    app.openapi_schema = schema
    return schema


def openapi_json(app: FastAPI) -> str:
    """Deterministic text of ``openapi.json`` (scripts/export_openapi.py and the snapshot test)."""
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


app = create_app()
