"""WP1 test helpers (imported explicitly; never a second conftest.py — BUILD_PLAN §4.1)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI

from proxyhealth_api.main import create_app
from proxyhealth_api.settings import KeySlotConfig, Settings
from tests.conftest import make_settings

# Fake key strings: long enough to have a distinct last-4, never sent anywhere (no network).
FAKE_KEYS = (
    "AIzaFAKE-slot-zero-0000Qx7A",
    "AIzaFAKE-slot-one-1111Bb2C",
    "AIzaFAKE-slot-two-2222Zz9D",
)


def slots(*billing: bool) -> list[KeySlotConfig]:
    """One ``KeySlotConfig`` per flag, each from a distinct project."""
    return [
        KeySlotConfig.model_validate(
            {"key": FAKE_KEYS[i], "project": f"proxyhealth-test-{i}", "billing": flag}
        )
        for i, flag in enumerate(billing)
    ]


def gemini(tmp_path: Path, *billing: bool, **overrides: object) -> Settings:
    return make_settings(tmp_path, ai_provider="gemini", gemini_keys=slots(*billing), **overrides)


@asynccontextmanager
async def running(
    settings: Settings, *, raise_app_exceptions: bool = True
) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient]]:
    """``create_app(settings)`` with its lifespan running and an ASGI client bound to it."""
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield app, client


def demo_body(sample: str = "medicaid_address_confirmation") -> dict[str, object]:
    return {
        "pages": [],
        "target_language": "en",
        "client_platform": "web",
        "demo_sample_id": sample,
    }


def page_body(png_b64: str) -> dict[str, object]:
    return {
        "pages": [{"mime_type": "image/png", "data_base64": png_b64}],
        "target_language": "en",
        "client_platform": "web",
    }
