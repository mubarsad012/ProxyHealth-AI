"""Base English pack and the ``languages.yaml`` table (BUILD_PLAN §4.1; ARCHITECTURE §2.1)."""

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel

from proxyhealth_api.contracts.config import LanguageInfo
from proxyhealth_api.contracts.enums import DigitSystem, Direction, PackTier


class BasePack:
    """``data/langpacks/en.json``: flat ``{key: english}``; ``version`` = sha256 of the bytes."""

    def __init__(self, strings: dict[str, str], version: str, contexts: dict[str, str]) -> None:
        self.strings = strings
        self.version = version
        self.contexts = contexts

    @classmethod
    def load(cls, path: Path) -> "BasePack":
        raw = path.read_bytes()
        data = json.loads(raw)
        if not isinstance(data, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in data.items()
        ):
            raise ValueError(f"{path} must be a flat JSON object of strings")
        strings: dict[str, str] = dict(data)
        contexts: dict[str, str] = {}
        ctx_path = path.parent / "_contexts.json"
        if ctx_path.is_file():
            loaded = json.loads(ctx_path.read_text(encoding="utf-8"))
            contexts = {str(k): str(v) for k, v in loaded.items() if k in strings}
        return cls(strings, hashlib.sha256(raw).hexdigest(), contexts)

    def chunks(self, size: int = 60) -> list[list[str]]:
        keys = sorted(self.strings)
        return [keys[i : i + size] for i in range(0, len(keys), size)]


class LanguageEntry(BaseModel):
    """One row of ``data/languages.yaml`` (BUILD_PLAN Appendix E)."""

    tag: str
    name_native: str
    name_en: str
    direction: Direction
    script: str | None = None
    digit_system: DigitSystem
    font_hint: str | None = None
    tier: PackTier
    tts_tag: str | None = None
    tts_fallback_tag: str | None = None


class LanguageTable:
    def __init__(self, entries: list[LanguageEntry], langpacks_dir: Path) -> None:
        self.entries: dict[str, LanguageEntry] = {e.tag: e for e in entries}
        self.langpacks_dir = langpacks_dir

    @classmethod
    def load(cls, path: Path, langpacks_dir: Path) -> "LanguageTable":
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        entries = [LanguageEntry(tag=str(tag), **row) for tag, row in raw.items()]
        return cls(entries, langpacks_dir)

    def get(self, tag: str) -> LanguageEntry | None:
        return self.entries.get(tag)

    def is_bundled(self, tag: str) -> bool:
        return (self.langpacks_dir / f"{tag}.json").is_file()

    def info(self, entry: LanguageEntry) -> LanguageInfo:
        return LanguageInfo(
            tag=entry.tag,
            name_native=entry.name_native,
            name_en=entry.name_en,
            direction=entry.direction,
            script=entry.script,
            digit_system=entry.digit_system,
            font_hint=entry.font_hint,
            tier=entry.tier,
            bundled=self.is_bundled(entry.tag),
            machine_translated=entry.tag != "en",
            tts_tag=entry.tts_tag,
            tts_fallback_tag=entry.tts_fallback_tag,
        )

    def infos(self) -> list[LanguageInfo]:
        return [self.info(e) for e in self.entries.values()]

    def resolve(self, query: str) -> str | None:
        """Case-insensitive match on tag, English name or native name; ``None`` if unknown."""
        q = query.strip().casefold()
        if not q:
            return None
        for tag, e in self.entries.items():
            if q in {tag.casefold(), e.name_en.casefold(), e.name_native.casefold()}:
                return tag
        for tag, e in self.entries.items():
            if q == e.name_en.split(" (")[0].casefold():
                return tag
        return None
