"""``packs/cache.py``: bundled rebasing, disk + LRU cache, TTL, prune, single-flight, t_server."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from proxyhealth_api.contracts.enums import Confidence, DigitSystem, Direction, PackSource, PackTier
from proxyhealth_api.contracts.langpack import LanguagePack
from proxyhealth_api.packs.base import BasePack, LanguageTable, pack_etag
from proxyhealth_api.packs.cache import PackCache, is_valid_tag, t_server
from proxyhealth_api.settings import DATA_DIR

NOW = datetime(2026, 9, 24, 14, 0, tzinfo=UTC)
BASE_STRINGS = {"app.name": "ProxyHealth AI", "home.hi": "Hello {name}", "btn.ok": "OK"}


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def write_base(dir_: Path) -> BasePack:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / "en.json").write_text(json.dumps(BASE_STRINGS), encoding="utf-8")
    return BasePack.load(dir_ / "en.json")


def make_pack(base: BasePack, tag: str = "x-test", when: datetime = NOW) -> LanguagePack:
    strings = {k: f"[{tag}] {v}" for k, v in base.strings.items()}
    return LanguagePack(
        language_tag=tag, language_name_native=tag, language_name_en=tag,
        direction=Direction.ltr, script=None, digit_system=DigitSystem.western, font_hint=None,
        tier=PackTier.tier_3, source=PackSource.generated, pack_version=base.version,
        etag=pack_etag(tag, base.version, strings), strings=strings, fallback_keys=[],
        coverage=1.0, machine_translated=True, reviewed_by=None, confidence=Confidence.low,
        generated_at=when,
    )  # fmt: skip


@pytest.fixture
def base(tmp_path: Path) -> BasePack:
    return write_base(tmp_path / "langpacks")


def cache_for(
    tmp_path: Path, base: BasePack, clock: Clock | None = None, *, ttl_days: int = 180,
    lru_size: int = 256,
) -> PackCache:
    return PackCache(
        tmp_path / "var" / "langpacks", langpacks_dir=tmp_path / "langpacks", base=base,
        clock=clock or Clock(NOW), ttl_days=ttl_days, lru_size=lru_size,
    )  # fmt: skip


def test_base_pack_version_is_sha256_of_bytes(base: BasePack, tmp_path: Path) -> None:
    raw = (tmp_path / "langpacks" / "en.json").read_bytes()
    assert base.version == hashlib.sha256(raw).hexdigest()
    assert base.chunks(2) == [["app.name", "btn.ok"], ["home.hi"]]
    real = BasePack.load(DATA_DIR / "langpacks" / "en.json")
    assert all(len(c) <= 60 for c in real.chunks()) and sum(map(len, real.chunks())) == len(
        real.strings
    )


def test_put_get_roundtrip_on_disk(tmp_path: Path, base: BasePack) -> None:
    cache = cache_for(tmp_path, base)
    pack = make_pack(base)
    cache.put(pack)
    path = tmp_path / "var" / "langpacks" / f"x-test--{base.version}.json"
    assert path.is_file()
    assert not list(path.parent.glob(".tmp-*"))  # atomic write leaves no temp files
    fresh = cache_for(tmp_path, base)  # a new process: memory is empty, disk serves
    got = fresh.get("x-test", base.version)
    assert got is not None and got.source == "cache" and got.etag == pack.etag
    assert fresh.get("x-test", "0" * 64) is None


def test_lru_evicts_oldest_from_memory_only(tmp_path: Path, base: BasePack) -> None:
    cache = cache_for(tmp_path, base, lru_size=2)
    for tag in ("x-a", "x-b", "x-c"):
        cache.put(make_pack(base, tag))
    assert len(cache._memory) == 2 and ("x-a", base.version) not in cache._memory
    assert cache.get("x-a", base.version) is not None  # reloaded from disk


def test_ttl_expiry_and_prune(tmp_path: Path, base: BasePack) -> None:
    clock = Clock(NOW)
    cache = cache_for(tmp_path, base, clock, ttl_days=180)
    cache.put(make_pack(base, "x-old", when=NOW - timedelta(days=181)))
    cache.put(make_pack(base, "x-new", when=NOW - timedelta(days=10)))
    assert cache.get("x-old", base.version) is None
    assert cache.get("x-new", base.version) is not None
    clock.now = NOW + timedelta(days=200)
    assert cache_for(tmp_path, base, clock).prune() == 1  # x-new is now stale too
    assert not list((tmp_path / "var" / "langpacks").glob("*--*.json"))


def test_corrupt_cache_file_is_dropped(tmp_path: Path, base: BasePack) -> None:
    cache = cache_for(tmp_path, base)
    path = cache.path_for("x-bad", base.version)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert cache.get("x-bad", base.version) is None and not path.exists()


def test_paths_reject_traversal(tmp_path: Path, base: BasePack) -> None:
    cache = cache_for(tmp_path, base)
    for tag in ("../etc", "a/b", "x-", ""):
        assert not is_valid_tag(tag)
        with pytest.raises(ValueError):
            cache.path_for(tag, base.version)
    with pytest.raises(ValueError):
        cache.path_for("es", "../../x")
    assert cache.get("../etc", base.version) is None and cache.bundled("../en") is None


async def test_single_flight_lock_per_tag(tmp_path: Path, base: BasePack) -> None:
    cache = cache_for(tmp_path, base)
    assert cache.single_flight("es") is cache.single_flight("es")
    assert cache.single_flight("es") is not cache.single_flight("ar")


def test_bundled_flat_en(tmp_path: Path, base: BasePack) -> None:
    pack = cache_for(tmp_path, base).bundled("en")
    assert pack is not None and pack.source == "bundled" and pack.machine_translated is False
    assert pack.strings == BASE_STRINGS and pack.fallback_keys == [] and pack.coverage == 1.0
    assert pack.etag == pack_etag("en", base.version, BASE_STRINGS)


def test_bundled_full_pack_is_rebased_on_current_base(tmp_path: Path, base: BasePack) -> None:
    old = make_pack(base, "es").model_copy(
        update={
            "pack_version": "f" * 64,
            "strings": {"app.name": "ProxyHealth AI", "btn.ok": "Aceptar", "gone.key": "x"},
            "source": PackSource.bundled,
        }
    )
    (tmp_path / "langpacks" / "es.json").write_text(old.model_dump_json(), encoding="utf-8")
    languages = LanguageTable.load(DATA_DIR / "languages.yaml", tmp_path / "langpacks")
    cache = PackCache(
        tmp_path / "var", langpacks_dir=tmp_path / "langpacks", base=base, languages=languages
    )
    pack = cache.bundled("es")
    assert pack is not None
    assert pack.pack_version == base.version  # always matches /v1/config.base_pack_version
    assert pack.strings == {
        "app.name": "ProxyHealth AI", "home.hi": "Hello {name}", "btn.ok": "Aceptar",
    }  # fmt: skip
    assert pack.fallback_keys == ["home.hi"] and pack.coverage == pytest.approx(2 / 3, abs=1e-3)
    assert pack.language_name_native == "Español"  # languages.yaml wins over the file
    assert pack.etag == pack_etag("es", base.version, pack.strings)
    assert cache.machine_translated("es") is True and cache.machine_translated("zz") is None
    assert cache.lookup("es") is pack


def test_t_server_translates_with_english_fallback(tmp_path: Path, base: BasePack) -> None:
    es = make_pack(base, "es").model_copy(
        update={"strings": {"home.hi": "Hola {name}"}, "source": PackSource.bundled}
    )
    (tmp_path / "langpacks" / "es.json").write_text(es.model_dump_json(), encoding="utf-8")
    cache = cache_for(tmp_path, base)
    assert t_server("es", "home.hi", cache, base, name="Ana") == "Hola Ana"
    assert t_server("es", "btn.ok", cache, base) == "OK"  # missing → English
    assert t_server("zz", "home.hi", cache, base, name="Ana") == "Hello Ana"
    assert t_server("es", "home.hi", cache, base) == "Hola {name}"  # missing var left as-is
    assert t_server("es", "no.such.key", cache, base) == "no.such.key"
