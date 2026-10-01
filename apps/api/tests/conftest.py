"""Shared fixtures (BUILD_PLAN §4.1, permanent). WP-specific fixtures live in the WP's modules."""

import base64
import io
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from proxyhealth_api.main import create_app
from proxyhealth_api.settings import DATA_DIR, KeySlotConfig, Settings

FROZEN_NOW = datetime(2026, 9, 24, 14, 0, 0, tzinfo=UTC)


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "ai_provider": "mock",
        "var_dir": tmp_path / "var",
        "mock_latency_min_ms": 0,
        "mock_latency_max_ms": 0,
        "install_hash_secret": "test",
        "consent_version": "2026-10-01",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def frozen_now() -> Callable[[], datetime]:
    return lambda: FROZEN_NOW


@pytest.fixture
def consent_headers() -> dict[str, str]:
    return {"X-Consent-Version": "2026-10-01"}


@pytest.fixture
def fixture_png() -> Callable[[str], bytes]:
    def _read(fixture_id: str) -> bytes:
        path = DATA_DIR / "fixtures" / fixture_id / "page-1.png"
        if not path.is_file():
            pytest.skip(f"fixture image missing: {path}")
        return path.read_bytes()

    return _read


@pytest.fixture
def tiny_png_base64() -> str:
    """A 16×16 white PNG as standard base64 (any page works for the hour-one mock)."""
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.fixture
def gemini_settings(tmp_path: Path) -> Callable[[list[dict[str, object]]], Settings]:
    """Factory for keypool tests: takes a list of ``{"key", "project", "billing"}`` dicts."""

    def _make(slots: list[dict[str, object]]) -> Settings:
        return make_settings(
            tmp_path,
            ai_provider="gemini",
            gemini_keys=[KeySlotConfig.model_validate(s) for s in slots],
        )

    return _make
