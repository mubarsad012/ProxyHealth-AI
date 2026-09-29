"""Base English pack and the ``languages.yaml`` table (BUILD_PLAN §4.1; ARCHITECTURE §2.1)."""

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path

import yaml
from pydantic import BaseModel

from proxyhealth_api.contracts.config import LanguageInfo
from proxyhealth_api.contracts.enums import DigitSystem, Direction, PackTier


def pack_etag(language_tag: str, pack_version: str, strings: Mapping[str, str]) -> str:
    """Strong ETag of a pack's content: sha256 of the canonical JSON of tag, base hash, strings."""
    canonical = json.dumps(
        {"language_tag": language_tag, "pack_version": pack_version, "strings": dict(strings)},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
        """Sorted keys in batches of ``size`` (D-25: 60-key language-pack chunks)."""
        if size < 1:
            raise ValueError("chunk size must be >= 1")
        keys = sorted(self.strings)
        return [keys[i : i + size] for i in range(0, len(keys), size)]

    def context(self, key: str) -> str:
        return self.contexts.get(key, "")


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

    def info(
        self, entry: LanguageEntry, *, machine_translated: bool | None = None
    ) -> LanguageInfo:
        """``machine_translated`` comes from the bundled pack file when the caller knows it."""
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
            machine_translated=(
                machine_translated if machine_translated is not None else entry.tag != "en"
            ),
            tts_tag=entry.tts_tag,
            tts_fallback_tag=entry.tts_fallback_tag,
        )

    def infos(
        self, machine_translated: Callable[[str], bool | None] | None = None
    ) -> list[LanguageInfo]:
        lookup = machine_translated or (lambda _tag: None)
        return [self.info(e, machine_translated=lookup(e.tag)) for e in self.entries.values()]

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
