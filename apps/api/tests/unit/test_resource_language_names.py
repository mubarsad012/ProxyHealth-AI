"""Every language a resource says it speaks has a readable name in the app (POLISH item 4).

The mobile "Speaks: …" line shows ``languageInfoFor(tag).name_native``. Tags in
``data/languages.yaml`` come from the synced seed; resource-only tags (zh, hmn, km, …) come from
``apps/mobile/src/i18n/languageNames.ts`` and are never added to the language grid.
"""

from __future__ import annotations

import logging
import re

import yaml

from proxyhealth_api.resources.loader import ResourceRepo
from proxyhealth_api.settings import DATA_DIR

NAMES_TS = DATA_DIR.parents[1] / "mobile" / "src" / "i18n" / "languageNames.ts"
NOT_A_LANGUAGE = {"interpreters_200+"}  # rendered as the "interpreters" line instead
ENTRY_RE = re.compile(r"^\s+([a-z]{2,3}(?:-[A-Za-z0-9]+)?): \{ name_native: '([^']+)', "
                      r"name_en: '([^']+)' \},$", re.M)  # fmt: skip


def extra_names() -> dict[str, tuple[str, str]]:
    return {m[1]: (m[2], m[3]) for m in ENTRY_RE.finditer(NAMES_TS.read_text(encoding="utf-8"))}


def test_every_resource_language_has_a_name() -> None:
    logging.getLogger("proxyhealth").setLevel(logging.ERROR)
    repo = ResourceRepo.load(DATA_DIR / "resources")
    seed = yaml.safe_load((DATA_DIR / "languages.yaml").read_text(encoding="utf-8"))
    spoken = {tag for entry in repo.all() for tag in entry.languages} - NOT_A_LANGUAGE
    missing = sorted(spoken - set(seed) - set(extra_names()))
    assert not missing, f"add native/English names to {NAMES_TS.name}: {missing}"


def test_extra_names_are_not_pack_languages() -> None:
    seed = yaml.safe_load((DATA_DIR / "languages.yaml").read_text(encoding="utf-8"))
    names = extra_names()
    assert {"zh", "hmn", "km"} <= set(names)
    assert names["zh"] == ("中文", "Chinese") and names["hmn"] == ("Hmoob", "Hmong")
    assert names["km"] == ("ខ្មែរ", "Khmer")
    # A tag with a seed row belongs to the seed (and the grid); never both.
    assert not set(names) & set(seed)
    assert all(native != tag for tag, (native, _) in names.items())
