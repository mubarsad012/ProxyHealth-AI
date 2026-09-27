"""``PackCache`` (BUILD_PLAN §4.1). WP0: in-memory only; ``bundled`` reads ``data/langpacks``."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from proxyhealth_api.contracts.enums import Confidence, DigitSystem, Direction, PackSource, PackTier
from proxyhealth_api.contracts.langpack import LanguagePack
from proxyhealth_api.packs.base import BasePack, LanguageTable
from proxyhealth_api.settings import DATA_DIR


class _SafeVars(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class PackCache:
    def __init__(
        self,
        var_dir: Path,
        *,
        langpacks_dir: Path | None = None,
        base: BasePack | None = None,
        languages: LanguageTable | None = None,
    ) -> None:
        self.var_dir = var_dir
        self.langpacks_dir = langpacks_dir or DATA_DIR / "langpacks"
        self.base = base
        self.languages = languages
        self._memory: dict[tuple[str, str], LanguagePack] = {}
        self._bundled: dict[str, LanguagePack] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, tag: str, pack_version: str) -> LanguagePack | None:
        return self._memory.get((tag, pack_version))

    def put(self, pack: LanguagePack) -> None:
        self._memory[(pack.language_tag, pack.pack_version)] = pack

    def single_flight(self, tag: str) -> asyncio.Lock:
        return self._locks.setdefault(tag, asyncio.Lock())

    def bundled(self, tag: str) -> LanguagePack | None:
        """A pack shipped in ``data/langpacks/<tag>.json`` (full pack JSON or the flat base)."""
        if tag in self._bundled:
            return self._bundled[tag]
        if tag.startswith("_"):
            return None
        path = self.langpacks_dir / f"{tag}.json"
        if not path.is_file():
            return None
        raw = path.read_bytes()
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        pack = (
            LanguagePack.model_validate(data)
            if "strings" in data and "language_tag" in data
            else self._from_flat(tag, data, raw, path)
        )
        self._bundled[tag] = pack
        return pack

    def _from_flat(self, tag: str, data: dict[str, Any], raw: bytes, path: Path) -> LanguagePack:
        strings = {str(k): str(v) for k, v in data.items()}
        entry = self.languages.get(tag) if self.languages else None
        return LanguagePack(
            language_tag=tag,
            language_name_native=entry.name_native if entry else tag,
            language_name_en=entry.name_en if entry else tag,
            direction=entry.direction if entry else Direction.ltr,
            script=entry.script if entry else None,
            digit_system=entry.digit_system if entry else DigitSystem.western,
            font_hint=entry.font_hint if entry else None,
            tier=entry.tier if entry else PackTier.tier_1,
            source=PackSource.bundled,
            pack_version=self.base.version if self.base else hashlib.sha256(raw).hexdigest(),
            etag=hashlib.sha256(raw).hexdigest(),
            strings=strings,
            fallback_keys=[],
            coverage=1.0,
            machine_translated=tag != "en",
            reviewed_by=None,
            confidence=Confidence.high,
            generated_at=datetime.fromtimestamp(path.stat().st_mtime, UTC),
            tts_tag=entry.tts_tag if entry else None,
            tts_fallback_tag=entry.tts_fallback_tag if entry else None,
        )


def t_server(tag: str, key: str, packs: PackCache, base: BasePack, **vars: str) -> str:
    """Target-language string with English fallback (used for server-composed lines)."""
    pack = packs.bundled(tag) or packs.get(tag, base.version)
    text = (pack.strings.get(key) if pack else None) or base.strings.get(key) or key
    return text.format_map(_SafeVars(vars))
