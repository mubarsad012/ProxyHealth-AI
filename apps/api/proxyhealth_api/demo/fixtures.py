"""``FixtureStore`` (BUILD_PLAN §4.1; ARCHITECTURE §2 ``demo/``; D-29).

Loads ``data/fixtures/<id>/manifest.yaml`` for every sample paper at boot. Everything else — page
PNGs, ``transcript.txt``, ``out.<lang>.json`` — is read from disk on first use and cached in
memory. Fixture files are committed, synthetic and watermarked SAMPLE; nothing user-supplied is
ever read or written here (ARCHITECTURE §7).

``out(lang)`` returns the recorded model output with the ``_meta`` object removed (AI_PROMPTS
§10.2); ``match_dhash`` compares an uploaded page against the precomputed page hashes of the
fixtures of one ``kind`` and returns the nearest one within ``max_hamming`` (ties → manifest
order), so a photographed printed SAMPLE sheet resolves to its fixture in zero-key mode.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ValidationError

from proxyhealth_api.contracts.demo import DemoFixture
from proxyhealth_api.contracts.model_out import AnalysisModelOut, TroubleshootModelOut
from proxyhealth_api.demo.phash import HashError, dhash, hamming, hex_to_hash

FixtureKind = Literal["document", "screenshot"]
FixtureOut = AnalysisModelOut | TroubleshootModelOut

# The fixture everything falls back to when a caller needs "some" sample (hour-one behaviour).
DEFAULT_FIXTURE_ID = "medicaid_address_confirmation"


class FixtureError(Exception):
    """A fixture folder is malformed (bad manifest, unreadable output). Boot fails loudly."""


@dataclass
class Fixture:
    """One sample paper or screenshot on disk."""

    manifest: DemoFixture
    dir: Path
    dhash: int
    page_dhashes: list[int]
    today: date
    expected: dict[str, Any] = field(default_factory=dict)
    recorded_on: str | None = None
    _pngs: dict[int, bytes] = field(default_factory=dict, repr=False)
    _outs: dict[str, FixtureOut | None] = field(default_factory=dict, repr=False)
    _metas: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)
    _transcript: str | None = field(default=None, repr=False)

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def kind(self) -> FixtureKind:
        return self.manifest.kind

    @property
    def languages(self) -> list[str]:
        return list(self.manifest.available_target_languages)

    def page_png(self, n: int) -> bytes:
        """PNG bytes of page ``n`` (1-based); ``KeyError`` for a page that does not exist."""
        if not 1 <= n <= self.manifest.pages:
            raise KeyError(n)
        cached = self._pngs.get(n)
        if cached is None:
            path = self.dir / f"page-{n}.png"
            if not path.is_file():
                raise KeyError(n)
            cached = path.read_bytes()
            self._pngs[n] = cached
        return cached

    @property
    def transcript(self) -> str:
        if self._transcript is None:
            path = self.dir / "transcript.txt"
            self._transcript = path.read_text("utf-8") if path.is_file() else ""
        return self._transcript

    def _load(self, lang: str) -> None:
        path = self.dir / f"out.{lang}.json"
        if not path.is_file():
            self._outs[lang] = None
            return
        try:
            raw: dict[str, Any] = json.loads(path.read_text("utf-8"))
        except ValueError as exc:
            raise FixtureError(f"{path}: not valid JSON ({exc})") from exc
        meta = raw.pop("_meta", None)
        self._metas[lang] = dict(meta) if isinstance(meta, dict) else {}
        schema: type[BaseModel] = (
            TroubleshootModelOut if self.kind == "screenshot" else AnalysisModelOut
        )
        try:
            parsed = schema.model_validate(raw)
        except ValidationError as exc:
            raise FixtureError(f"{path}: {exc.error_count()} validation error(s)") from exc
        assert isinstance(parsed, AnalysisModelOut | TroubleshootModelOut)
        self._outs[lang] = parsed

    def out(self, lang: str) -> FixtureOut | None:
        """The recorded output for exactly ``lang`` (``None`` when not recorded).

        Only the manifest's ``available_target_languages`` are ever loaded or cached, so an
        arbitrary (pattern-valid) request tag cannot grow the per-fixture cache.
        """
        if lang not in self.manifest.available_target_languages:
            return None
        if lang not in self._outs:
            self._load(lang)
        return self._outs.get(lang)

    def analysis_out(self, lang: str) -> AnalysisModelOut | None:
        out = self.out(lang)
        return out if isinstance(out, AnalysisModelOut) else None

    def troubleshoot_out(self, lang: str) -> TroubleshootModelOut | None:
        out = self.out(lang)
        return out if isinstance(out, TroubleshootModelOut) else None

    def meta(self, lang: str) -> dict[str, Any]:
        """The ``_meta`` object of ``out.<lang>.json`` (empty when absent)."""
        self.out(lang)
        return dict(self._metas.get(lang, {}))

    def distance(self, value: int) -> int:
        """Smallest Hamming distance between ``value`` and any page of this fixture."""
        return min(hamming(value, h) for h in (self.page_dhashes or [self.dhash]))


def _manifest(path: Path) -> Fixture:
    try:
        raw = yaml.safe_load(path.read_text("utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise FixtureError(f"{path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise FixtureError(f"{path}: manifest must be a mapping")
    try:
        manifest = DemoFixture.model_validate(
            {k: raw[k] for k in DemoFixture.model_fields if k in raw}
        )
        page_hashes = [hex_to_hash(str(h)) for h in raw.get("page_dhashes") or [raw["dhash"]]]
        today = date.fromisoformat(str(raw["today"]))
        main_hash = hex_to_hash(str(raw["dhash"]))
    except (KeyError, ValueError, ValidationError) as exc:
        raise FixtureError(f"{path}: {exc}") from exc
    if manifest.id != path.parent.name:
        raise FixtureError(f"{path}: id {manifest.id!r} does not match its folder")
    expected = raw.get("expected") or {}
    return Fixture(
        manifest=manifest,
        dir=path.parent,
        dhash=main_hash,
        page_dhashes=page_hashes,
        today=today,
        expected=dict(expected) if isinstance(expected, dict) else {},
        recorded_on=str(raw["recorded_on"]) if raw.get("recorded_on") else None,
    )


class FixtureStore:
    """All sample papers, in id order (the sample picker's order)."""

    def __init__(self, fixtures: list[Fixture]) -> None:
        self._by_id = {f.manifest.id: f for f in fixtures}

    @classmethod
    def load(cls, dir: Path) -> FixtureStore:  # noqa: A002 - name fixed by BUILD_PLAN §4.1
        """Read every ``dir/*/manifest.yaml``; a missing directory gives an empty store."""
        if not dir.is_dir():
            return cls([])
        return cls([_manifest(p) for p in sorted(dir.glob("*/manifest.yaml"))])

    def __len__(self) -> int:
        return len(self._by_id)

    def ids(self) -> list[str]:
        return list(self._by_id)

    def all(self) -> list[Fixture]:
        return list(self._by_id.values())

    def list(self) -> list[DemoFixture]:
        return [f.manifest for f in self._by_id.values()]

    def get(self, id: str) -> Fixture | None:  # noqa: A002 - name fixed by BUILD_PLAN §4.1
        return self._by_id.get(id)

    def default(self) -> Fixture | None:
        return self._by_id.get(DEFAULT_FIXTURE_ID) or next(iter(self._by_id.values()), None)

    def match_dhash(
        self, png_or_jpeg: bytes, max_hamming: int, *, kind: FixtureKind | None = "document"
    ) -> Fixture | None:
        """Nearest fixture of ``kind`` (any kind when ``None``) within ``max_hamming`` bits."""
        try:
            value = dhash(png_or_jpeg)
        except HashError:
            return None
        best: Fixture | None = None
        best_distance = max_hamming + 1
        for fixture in self._by_id.values():
            if kind is not None and fixture.kind != kind:
                continue
            d = fixture.distance(value)
            if d < best_distance:
                best, best_distance = fixture, d
        return best


__all__ = [
    "DEFAULT_FIXTURE_ID",
    "Fixture",
    "FixtureError",
    "FixtureKind",
    "FixtureOut",
    "FixtureStore",
]
