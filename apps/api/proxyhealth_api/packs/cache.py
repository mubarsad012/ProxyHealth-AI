"""Language-pack cache (BUILD_PLAN §4.1; ARCHITECTURE §2.1 "Language-pack cache"; D-25).

* **Bundled** packs are read from ``data/langpacks/<tag>.json`` (the flat ``en.json`` base, or a
  full ``LanguagePack`` dump for every other tag) and *rebased* on the current base pack: keys
  the file lacks (``en.json`` grew after the pack was authored) are filled with English and
  listed in ``fallback_keys``; keys the base no longer has are dropped; ``pack_version`` and
  ``etag`` are recomputed, so a bundled pack always matches ``/v1/config.base_pack_version``.
* **Generated** packs live in an in-memory LRU (256) backed by
  ``var/langpacks/<tag>--<pack_version>.json`` (atomic writes). They hold UI strings only — never
  user content — which is why ``var/langpacks/`` is one of the three allowed server paths.
  Files older than ``LANGPACK_CACHE_TTL_DAYS`` are ignored and pruned.
* ``single_flight(tag)`` returns one ``asyncio.Lock`` per tag so concurrent POSTs generate once.
"""

import asyncio
import json
import os
import re
import tempfile
import weakref
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from proxyhealth_api.contracts.common import LANGUAGE_TAG_PATTERN
from proxyhealth_api.contracts.enums import Confidence, DigitSystem, Direction, PackSource, PackTier
from proxyhealth_api.contracts.langpack import LanguagePack
from proxyhealth_api.packs.base import BasePack, LanguageTable, pack_etag
from proxyhealth_api.settings import DATA_DIR

Clock = Callable[[], datetime]

_TAG_RE = re.compile(LANGUAGE_TAG_PATTERN)
_VERSION_RE = re.compile(r"^[0-9a-f]{64}$")
LRU_SIZE = 256
# A generated pack thinner than this is served to its client but never cached (AI_PROMPTS §7.8).
MIN_CACHE_COVERAGE = 0.9


def is_valid_tag(tag: str) -> bool:
    return bool(_TAG_RE.match(tag))


def is_pseudo(pack: LanguagePack) -> bool:
    """A mock pseudo-localized pack (``⟦tag⟧ English``, AI_PROMPTS §7.10); never cached."""
    marker = f"⟦{pack.language_tag}⟧"
    return any(value.startswith(marker) for value in pack.strings.values())


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
        ttl_days: int = 180,
        lru_size: int = LRU_SIZE,
        clock: Clock | None = None,
    ) -> None:
        self.var_dir = var_dir
        self.langpacks_dir = langpacks_dir or DATA_DIR / "langpacks"
        self.base = base if base is not None else BasePack.load(self.langpacks_dir / "en.json")
        self.languages = languages
        self.ttl = timedelta(days=ttl_days)
        self.lru_size = lru_size
        self._clock: Clock = clock or (lambda: datetime.now(UTC))
        self._memory: OrderedDict[tuple[str, str], LanguagePack] = OrderedDict()
        # Only hits are memoised: a miss is one stat() and random tags must not grow memory.
        self._bundled: dict[str, LanguagePack] = {}
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()

    # ------------------------------------------------------------------ generated packs

    def path_for(self, tag: str, pack_version: str) -> Path:
        if not is_valid_tag(tag) or not _VERSION_RE.match(pack_version):
            raise ValueError("invalid language tag or pack version for a cache path")
        return self.var_dir / f"{tag}--{pack_version}.json"

    def _fresh(self, pack: LanguagePack) -> bool:
        generated = pack.generated_at
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=UTC)
        return self._clock() - generated <= self.ttl

    def _remember(self, pack: LanguagePack) -> None:
        key = (pack.language_tag, pack.pack_version)
        self._memory[key] = pack
        self._memory.move_to_end(key)
        while len(self._memory) > self.lru_size:
            self._memory.popitem(last=False)

    def get(self, tag: str, pack_version: str) -> LanguagePack | None:
        """A generated pack from memory or ``var/langpacks`` (``source="cache"``), else ``None``."""
        key = (tag, pack_version)
        pack = self._memory.get(key)
        if pack is not None:
            if self._fresh(pack):
                self._memory.move_to_end(key)
                return pack
            del self._memory[key]
        try:
            path = self.path_for(tag, pack_version)
        except ValueError:
            return None
        if not path.is_file():
            return None
        try:
            loaded = LanguagePack.model_validate_json(path.read_bytes())
        except ValueError:
            path.unlink(missing_ok=True)  # corrupt cache file: regenerate
            return None
        if not self._fresh(loaded) or loaded.language_tag != tag or is_pseudo(loaded):
            path.unlink(missing_ok=True)  # stale, misfiled, or a mock pack from an older build
            return None
        pack = loaded.model_copy(update={"source": PackSource.cache})
        self._remember(pack)
        return pack

    def put(self, pack: LanguagePack) -> None:
        """Remember a generated pack and write it atomically to ``var/langpacks``."""
        path = self.path_for(pack.language_tag, pack.pack_version)
        self._remember(pack.model_copy(update={"source": PackSource.cache}))
        path.parent.mkdir(parents=True, exist_ok=True)
        data = pack.model_dump_json(indent=None).encode("utf-8")
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def prune(self) -> int:
        """Delete stale, unreadable or pseudo generated packs; returns how many were removed."""
        if not self.var_dir.is_dir():
            return 0
        removed = 0
        for path in self.var_dir.glob("*--*.json"):
            try:
                pack = LanguagePack.model_validate_json(path.read_bytes())
                stale = not self._fresh(pack) or is_pseudo(pack)
            except ValueError:
                stale = True
            if stale:
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    def single_flight(self, tag: str) -> asyncio.Lock:
        """One lock per tag while anyone holds or awaits it (weakly kept, so it never leaks)."""
        lock = self._locks.get(tag)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[tag] = lock
        return lock

    def lookup(self, tag: str) -> LanguagePack | None:
        """Bundled first, then a cached generated pack for the current base version."""
        return self.bundled(tag) or self.get(tag, self.base.version)

    # ------------------------------------------------------------------ bundled packs

    def bundled(self, tag: str) -> LanguagePack | None:
        """The pack shipped as ``data/langpacks/<tag>.json``, rebased on the current base."""
        cached = self._bundled.get(tag)
        if cached is not None:
            return cached
        if not is_valid_tag(tag):
            return None
        path = self.langpacks_dir / f"{tag}.json"
        if not path.is_file():
            return None
        pack = self._load_bundled(tag, path)
        self._bundled[tag] = pack
        return pack

    def machine_translated(self, tag: str) -> bool | None:
        """``machine_translated`` as the bundled pack file states it (``None`` if not bundled)."""
        pack = self.bundled(tag)
        return None if pack is None else pack.machine_translated

    def _load_bundled(self, tag: str, path: Path) -> LanguagePack:
        data = json.loads(path.read_bytes())
        if not isinstance(data, dict):
            raise ValueError(f"{path} must be a JSON object")
        if "strings" in data and "language_tag" in data:
            meta = LanguagePack.model_validate(data)
            if meta.language_tag != tag:
                raise ValueError(f"{path} declares language_tag {meta.language_tag!r}")
            file_strings = meta.strings
        else:
            meta = None
            file_strings = {str(k): str(v) for k, v in data.items()}
        base = self.base.strings
        declared_fallback = set(meta.fallback_keys) if meta else set()
        strings: dict[str, str] = {}
        fallback: list[str] = []
        for key, english in base.items():
            value = file_strings.get(key)
            if value is None or key in declared_fallback:
                fallback.append(key)
                strings[key] = value if value is not None else english
            else:
                strings[key] = value
        version = self.base.version
        generated_at = (
            meta.generated_at if meta else datetime.fromtimestamp(path.stat().st_mtime, UTC)
        )
        return LanguagePack(
            **self._descriptor(tag, meta),
            source=PackSource.bundled,
            pack_version=version,
            etag=pack_etag(tag, version, strings),
            strings=strings,
            fallback_keys=sorted(fallback),
            coverage=round(1 - len(fallback) / max(len(strings), 1), 4),
            machine_translated=meta.machine_translated if meta else tag != "en",
            reviewed_by=meta.reviewed_by if meta else None,
            confidence=meta.confidence if meta else Confidence.high,
            generated_at=generated_at,
        )

    def _descriptor(self, tag: str, meta: LanguagePack | None) -> dict[str, Any]:
        """Name/direction/script/digits/font/tier/TTS: ``languages.yaml`` wins over the file."""
        entry = self.languages.get(tag) if self.languages else None
        if entry is not None:
            return {
                "language_tag": tag,
                "language_name_native": entry.name_native,
                "language_name_en": entry.name_en,
                "direction": entry.direction,
                "script": entry.script,
                "digit_system": entry.digit_system,
                "font_hint": entry.font_hint,
                "tier": entry.tier,
                "tts_tag": entry.tts_tag,
                "tts_fallback_tag": entry.tts_fallback_tag,
            }
        if meta is not None:
            return {
                "language_tag": tag,
                "language_name_native": meta.language_name_native,
                "language_name_en": meta.language_name_en,
                "direction": meta.direction,
                "script": meta.script,
                "digit_system": meta.digit_system,
                "font_hint": meta.font_hint,
                "tier": meta.tier,
                "tts_tag": meta.tts_tag,
                "tts_fallback_tag": meta.tts_fallback_tag,
            }
        return {
            "language_tag": tag,
            "language_name_native": tag,
            "language_name_en": tag,
            "direction": Direction.ltr,
            "script": None,
            "digit_system": DigitSystem.western,
            "font_hint": None,
            "tier": PackTier.tier_1,
            "tts_tag": None,
            "tts_fallback_tag": None,
        }


def t_server(tag: str, key: str, packs: PackCache, base: BasePack, **vars: str) -> str:
    """Target-language string with English fallback (clerk template, fixed notices, markers).

    Unknown ``{placeholders}`` are left as written, so a missing variable never raises.
    """
    pack = packs.lookup(tag) if is_valid_tag(tag) else None
    text = (pack.strings.get(key) if pack else None) or base.strings.get(key) or key
    return text.format_map(_SafeVars(vars))
