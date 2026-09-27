"""Every router module; ``main.create_app`` includes ``ALL_ROUTERS`` in this order."""

from fastapi import APIRouter

from proxyhealth_api.routers import (
    admin,
    analyze,
    chat,
    config,
    demo,
    feedback,
    health,
    langpacks,
    quicksheet,
    resources,
    rules,
    troubleshoot,
)

ALL_ROUTERS: list[APIRouter] = [
    health.router,
    config.router,
    langpacks.router,
    analyze.router,
    troubleshoot.router,
    chat.router,
    resources.router,
    rules.router,
    quicksheet.router,
    feedback.router,
    demo.router,
    admin.router,
]

__all__ = ["ALL_ROUTERS"]
