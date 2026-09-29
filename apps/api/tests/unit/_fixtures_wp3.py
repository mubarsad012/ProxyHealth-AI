"""WP3 test helpers (BUILD_PLAN §4.1: ``tests/<dir>/_fixtures_<wp>.py``, imported explicitly)."""

from __future__ import annotations

import shutil
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from proxyhealth_api.contracts.resources import Resource
from proxyhealth_api.resources.loader import (
    LoadedEntry,
    Meta,
    ResourceRepo,
    _apply_defaults,
    load_meta,
)
from proxyhealth_api.settings import DATA_DIR

RESOURCES_DIR: Path = DATA_DIR / "resources"
RULES_DIR: Path = DATA_DIR / "rules"
SEED_TODAY = date(2026, 9, 27)  # RESOURCE_DB §6.11 "today"


@lru_cache(maxsize=1)
def real_repo() -> ResourceRepo:
    """The seed loaded once per test session (``today`` pinned to the seed date)."""
    return ResourceRepo.load(RESOURCES_DIR, today=SEED_TODAY)


@lru_cache(maxsize=1)
def real_meta() -> Meta:
    return load_meta(RESOURCES_DIR / "_meta.yaml")


MINIMAL_ENTRY: dict[str, Any] = {
    "id": "test_org",
    "name": "Test Organization",
    "org_type": "nonprofit",
    "what_it_does": {"en": "Helps people read letters."},
    "url": "https://example.org/help",
    "languages": ["en"],
    "cost": "free",
    "serves": {"scope": "national"},
    "tags": ["benefits_navigation"],
    "eligibility_plain": {"en": "Anyone."},
    "verified_on": "2026-09-20",
    "verification_method": "fetched",
    "link_health": "ok",
    "priority": 50,
}


def make_resource(**overrides: Any) -> Resource:
    """A valid ``Resource`` from the compact seed form plus overrides (defaults applied)."""
    raw = {**MINIMAL_ENTRY, **overrides}
    raw = _apply_defaults(raw)
    raw["warnings"] = [f"warn.{w}" if not w.startswith("warn.") else w for w in raw["warnings"]]
    return Resource.model_validate(raw)


def make_repo(resources: list[Resource], *, today: date = SEED_TODAY) -> ResourceRepo:
    """Hand-built repo over the real ``_meta.yaml`` (no cross-checks; for matcher unit tests)."""
    entries: list[LoadedEntry] = [(r, None, i + 1) for i, r in enumerate(resources)]
    return ResourceRepo(entries, real_meta(), prepare=real_repo().prepare_map(), today=today)


def copy_seed(tmp_path: Path) -> Path:
    """Copy ``data/resources`` into ``tmp_path/resources`` so a test can add a bad file."""
    target = tmp_path / "resources"
    shutil.copytree(RESOURCES_DIR, target)
    return target


def write_entries(path: Path, entries: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(entries, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


# API_CONTRACT §3.11 example, verbatim.
DARI_EXAMPLE: dict[str, Any] = {
    "title": "نامه مدیکید ویرجینیا — برگه سریع",
    "language_tag": "prs",
    "direction": "rtl",
    "font_hint": "NotoNaskhArabic",
    "sections": [
        {
            "heading": "این چیست؟",
            "heading_en": "What is this?",
            "lines": ["این نامه از مدیکید ویرجینیا است. بیمه شما قطع نشده است."],
        },
        {
            "heading": "چه می‌خواهد؟",
            "heading_en": "What is it asking for?",
            "lines": ["تا October 14, 2026 جواب بدهید.", "یک بل برق، آب یا گاز بفرستید."],
        },
        {
            "heading": "قدم‌های شما",
            "heading_en": "Your steps",
            "lines": ["۱. بل را پیدا کنید", "۲. فورم را پست کنید"],
        },
    ],
    "resources": [{"name": "211", "phone": "211", "url": "https://www.211.org/"}],
    "footer": (
        "ساخته شده با هوش مصنوعی از کاغذ شما. می‌تواند اشتباه باشد. "
        "تاریخ‌ها را با فرستنده تأیید کنید."
    ),
    "generated_on": "2026-09-24",
}

ENGLISH_EXAMPLE: dict[str, Any] = {
    "title": "Virginia Medicaid letter — quick sheet",
    "language_tag": "en",
    "direction": "ltr",
    "font_hint": "NotoSans",
    "sections": [
        {"heading": "What is this?", "heading_en": "What is this?", "lines": ["A letter."]},
        {"heading": "Dates", "heading_en": "Dates", "lines": ["Answer by October 14, 2026."]},
    ],
    "resources": [
        {"name": "211", "phone": "211", "url": "https://www.211.org/"},
        {"name": "211", "phone": "+15555550100", "url": "https://www.211.org/"},
        {"name": "Totally Real Legal Help", "phone": "+15555550199", "url": None},
    ],
    "footer": "Made with a computer from your paper. It can be wrong.",
    "generated_on": "2026-09-24",
}


__all__ = [
    "DARI_EXAMPLE",
    "ENGLISH_EXAMPLE",
    "MINIMAL_ENTRY",
    "RESOURCES_DIR",
    "RULES_DIR",
    "SEED_TODAY",
    "copy_seed",
    "make_repo",
    "make_resource",
    "real_meta",
    "real_repo",
    "write_entries",
]
