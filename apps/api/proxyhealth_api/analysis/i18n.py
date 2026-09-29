"""Translator seam for server-composed strings (WP2 lane 2A; BUILD_PLAN §4.1 ``t_server``).

Every validator that emits a user-facing line (fixed notices, scam chips, the contact marker,
urgency red flags, phrasing hedges) takes a ``Translator`` instead of a ``PackCache`` so the
modules stay pure and testable. The pipeline (lane 2B) builds one from ``packs.t_server``::

    t = translator_from(lambda key, **vars: t_server(tag, key, packs, base, **vars))

Tests use ``english_translator()``, which reads ``data/langpacks/en.json`` once.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from proxyhealth_api.settings import DATA_DIR

EN_JSON_PATH = DATA_DIR / "langpacks" / "en.json"


class Translator(Protocol):
    """``t(key, **vars) -> str``: target-language string with English fallback, never raising."""

    def __call__(self, key: str, /, **vars: str) -> str: ...


class _SafeVars(dict[str, str]):
    """``format_map`` helper that leaves unknown placeholders visible instead of raising."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class MappingTranslator:
    """A ``Translator`` over a flat ``{key: text}`` mapping (English pack or a test dict)."""

    def __init__(self, strings: Mapping[str, str]) -> None:
        self._strings = strings

    def __call__(self, key: str, /, **vars: str) -> str:
        text = self._strings.get(key) or key
        return text.format_map(_SafeVars(vars))


@lru_cache(maxsize=4)
def _load_strings(path: Path) -> Mapping[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a flat JSON object")
    return {str(k): str(v) for k, v in data.items()}


def english_translator(path: Path = EN_JSON_PATH) -> Translator:
    """``Translator`` over the base English pack (cached read of ``en.json``)."""
    return MappingTranslator(_load_strings(path))


def translator_from(fn: Callable[..., str]) -> Translator:
    """Wrap any ``fn(key, **vars) -> str`` (e.g. a bound ``t_server``) as a ``Translator``."""

    def _t(key: str, /, **vars: str) -> str:
        return fn(key, **vars)

    return _t


__all__ = [
    "EN_JSON_PATH",
    "MappingTranslator",
    "Translator",
    "english_translator",
    "translator_from",
]
