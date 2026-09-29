"""Resource DB loader / validator and ``ResourceRepo`` (RESOURCE_DB §8; BUILD_PLAN §4.1).

Loads ``data/resources/**/*.yaml`` (excluding ``_*.yaml``) into ``Resource`` models at boot.
Invalid data raises ``ResourceLoadError`` whose message starts with ``<path>:<line>:`` so the
boot refusal names the offending entry. Freshness problems are warnings (never a boot failure).
"""

from __future__ import annotations

import builtins
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from proxyhealth_api.contracts.enums import (
    DocumentType,
    GeoScope,
    LinkHealth,
    OrgType,
    ResourceTag,
    StatusNoteKey,
    VerificationMethod,
)
from proxyhealth_api.contracts.resources import PHONE_PATTERN, Resource
from proxyhealth_api.resources.checklist import PrepareLoadError, load_prepare

logger = logging.getLogger("proxyhealth.resources")

STALE_WARN_DAYS = 120
STALE_EXCLUDE_DAYS = 365
MIN_VERIFIED_ON = date(2026, 1, 1)
MAX_TAGS = 8
TEXT_MAX = 300

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,39}$")
PHONE_RE = re.compile(PHONE_PATTERN)
LANGUAGE_RE = re.compile(r"^(interpreters_200\+|[a-z]{2,3}(-[A-Za-z0-9]{2,8})*)$")
URL_RE = re.compile(r"^https://[^\s]+$")
ZIP3_RE = re.compile(r"^\d{3}$")
CHECKLIST_KEY_RE = re.compile(r"^[a-z0-9_]+$")
PHONE_LIKE_RE = re.compile(r"\d{3}[\s.\-]?\d{3,4}[\s.\-]?\d{3,4}")
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+(?:\s+|$)")

# RESOURCE_DB §2.2: the DB is user-facing copy and follows D-17. These are the load-bearing
# forbidden phrasings (data/safety/phrasing.yaml is WP2's file and may not exist at boot).
FORBIDDEN_PHRASES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\byou (do |don't |do not )?qualif(y|ies)\b", re.IGNORECASE),
    re.compile(
        r"\byou (are|aren't|are not|'re) (eligible|not eligible|ineligible|entitled)\b", re.I
    ),
    re.compile(
        r"\byou (should|must|need to|have to|ought to) "
        r"(file|appeal|apply|pay|sign|send|submit|plead|accept|refuse|leave|move)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\byou (will|won't|will not) (win|lose|be approved|be denied|be deported)\b", re.I),
)

STATES: frozenset[str] = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ "
    "NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC PR GU VI AS MP".split()
)
HHS_FUNDED_ORG_TYPES: frozenset[OrgType] = frozenset({OrgType.fqhc, OrgType.hospital_program})

# Optional fields the seed may omit (RESOURCE_DB §2.1 "Defaults").
_DEFAULTS: dict[str, Any] = {
    "name_note": None,
    "alt_urls": [],
    "phone": None,
    "tty": None,
    "text_line": None,
    "hours": None,
    "status_note_key": None,
    "prepare_checklist_keys": [],
    "warnings": [],
    "never_show_with_tags": [],
}
_SERVES_DEFAULTS: dict[str, list[str]] = {"states": [], "counties": [], "cities": [], "zip3": []}
_RESOURCE_FIELDS = frozenset(Resource.model_fields)


class ResourceLoadError(Exception):
    """Boot refusal: the message names ``path:line`` of the offending entry (or the meta file)."""


def _die(path: Path, line: int | None, msg: str) -> ResourceLoadError:
    where = f"{path}:{line}" if line is not None else str(path)
    return ResourceLoadError(f"{where}: {msg}")


def normalize_county(value: str) -> str:
    """Canonical comparison form: NFKC, casefold, straight apostrophe, no trailing ' county'."""
    s = unicodedata.normalize("NFKC", value).replace("’", "'").casefold().strip()
    s = re.sub(r"\s+", " ", s)
    if s.endswith(" county"):
        s = s[: -len(" county")]
    return s


def county_display(canonical: str) -> str:
    """RESOURCE_DB §4.2: append ' County' unless the name ends in 'City' or is the District."""
    if canonical.endswith("City") or canonical == "District of Columbia":
        return canonical
    return f"{canonical} County"


_ORG_STOPWORDS = ("health system", "hospital", "the", "inc")


def normalize_org_name(value: str) -> str:
    """RESOURCE_DB §6.3 institution normalisation (also used for ``org_names()``)."""
    s = unicodedata.normalize("NFKC", value).casefold()
    s = re.sub(r"[^\w\s]", " ", s)
    for word in _ORG_STOPWORDS:
        s = re.sub(rf"\b{re.escape(word)}\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _apply_defaults(raw: dict[str, Any]) -> dict[str, Any]:
    """Fill omitted optional fields (RESOURCE_DB §2.1) so compact seed entries validate."""
    out = dict(raw)
    for key, default in _DEFAULTS.items():
        if key not in out or out[key] is None and isinstance(default, list):
            out[key] = list(default) if isinstance(default, list) else default
    serves = out.get("serves")
    if isinstance(serves, dict):
        merged = dict(serves)
        for key, default in _SERVES_DEFAULTS.items():
            if merged.get(key) is None:
                merged[key] = list(default)
        out["serves"] = merged
    return out


@dataclass(frozen=True)
class Meta:
    """``data/resources/_meta.yaml`` (RESOURCE_DB §4, §8.5)."""

    resource_db_version: str
    fallback_only_tags: frozenset[ResourceTag]
    language_families: tuple[frozenset[str], ...]
    state_names: dict[str, str]
    checklist: dict[str, str]
    why: dict[str, str]
    notes: dict[str, str]
    warning_keys: frozenset[str]
    doc_type_pins: dict[DocumentType, tuple[str, ...]]
    urgent_doc_boost: dict[DocumentType, frozenset[ResourceTag]]
    well_known_ids: dict[str, str | list[str]]

    def strings(self) -> dict[str, str]:
        """Every English template the matcher renders (``why.*`` + ``notes.*``)."""
        return {**self.why, **self.notes}

    def same_family(self, a: str, b: str) -> bool:
        return any(a in fam and b in fam for fam in self.language_families)


_META_SECTIONS = (
    "resource_db_version", "fallback_only_tags", "language_families", "state_names", "checklist",
    "why", "notes", "warning_keys", "doc_type_pins", "urgent_doc_boost", "well_known_ids",
)  # fmt: skip


def load_meta(path: Path) -> Meta:
    """Parse and validate ``_meta.yaml``; any missing section or bad value refuses boot."""
    if not path.is_file():
        raise _die(path, None, "missing _meta.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise _die(path, 1, "_meta.yaml must be a mapping")
    for section in _META_SECTIONS:
        if section not in data:
            raise _die(path, 1, f"_meta.yaml is missing the '{section}' section")
    try:
        fallback_only = frozenset(ResourceTag(t) for t in data["fallback_only_tags"])
        pins = {
            DocumentType(k): tuple(str(v) for v in (ids or []))
            for k, ids in data["doc_type_pins"].items()
        }
        boosts = {
            DocumentType(k): frozenset(ResourceTag(t) for t in tags)
            for k, tags in data["urgent_doc_boost"].items()
        }
    except ValueError as exc:
        raise _die(path, 1, f"_meta.yaml enum value: {exc}") from exc
    checklist = {str(k): str(v) for k, v in data["checklist"].items()}
    for key in checklist:
        if not CHECKLIST_KEY_RE.match(key):
            raise _die(path, 1, f"checklist key {key!r} is not ^[a-z0-9_]+$")
    why = {str(k): str(v) for k, v in data["why"].items()}
    missing_why = [t.value for t in ResourceTag if f"why.for_{t.value}" not in why]
    if missing_why:
        raise _die(path, 1, f"why templates missing for tags: {missing_why}")
    well_known: dict[str, str | list[str]] = {}
    for k, v in data["well_known_ids"].items():
        well_known[str(k)] = [str(x) for x in v] if isinstance(v, list) else str(v)
    return Meta(
        resource_db_version=str(data["resource_db_version"]),
        fallback_only_tags=fallback_only,
        language_families=tuple(
            frozenset(str(x) for x in fam) for fam in data["language_families"]
        ),
        state_names={str(k): str(v) for k, v in data["state_names"].items()},
        checklist=checklist,
        why=why,
        notes={str(k): str(v) for k, v in data["notes"].items()},
        warning_keys=frozenset(str(k) for k in data["warning_keys"]),
        doc_type_pins=pins,
        urgent_doc_boost=boosts,
        well_known_ids=well_known,
    )


def _entry_lines(text: str) -> list[int]:
    """1-based start line of every top-level sequence item (for ``path:line`` messages)."""
    node = yaml.compose(text)
    if node is None or not isinstance(node, yaml.SequenceNode):
        return []
    return [child.start_mark.line + 1 for child in node.value]


def _sentence_stats(text: str) -> float:
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if not sentences:
        return 0.0
    return sum(len(s.split()) for s in sentences) / len(sentences)


def _check_text(field_name: str, value: dict[str, str], path: Path, line: int) -> list[str]:
    """RESOURCE_DB §8.2 item 10; returns readability warnings (never fatal)."""
    en = value.get("en")
    if not isinstance(en, str) or not 1 <= len(en) <= TEXT_MAX:
        raise _die(path, line, f"{field_name}.en must be 1–{TEXT_MAX} characters")
    for pattern in FORBIDDEN_PHRASES:
        if pattern.search(en):
            raise _die(
                path, line, f"{field_name}.en contains forbidden phrasing {pattern.pattern!r}"
            )
    if _sentence_stats(en) > 20:
        return [f"{path}:{line}: {field_name}.en averages > 20 words per sentence"]
    return []


def _check_serves(res: Resource, path: Path, line: int) -> None:
    s = res.serves
    for st in s.states:
        if st not in STATES:
            raise _die(path, line, f"serves.states has unknown state {st!r}")
    for county in s.counties:
        if county.casefold().endswith(" county") or "’" in county:
            raise _die(path, line, f"serves.counties {county!r} must be canonical (no ' County')")
    for z in s.zip3:
        if not ZIP3_RE.match(z):
            raise _die(path, line, f"serves.zip3 {z!r} is not three digits")
    if s.scope == GeoScope.national:
        if s.states or s.counties or s.cities or s.zip3:
            raise _die(path, line, "serves.scope national must have empty lists")
    elif s.scope == GeoScope.state:
        if not s.states or s.counties or s.cities or s.zip3:
            raise _die(path, line, "serves.scope state needs states only")
    elif s.scope == GeoScope.county:
        if not s.states or not s.counties:
            raise _die(path, line, "serves.scope county needs states and counties")
    elif s.scope == GeoScope.city and (not s.states or not s.cities or not (s.counties or s.zip3)):
        raise _die(path, line, "serves.scope city needs states, cities and counties or zip3")


def _check_entry(
    res: Resource, raw_warnings: list[str], x_meta: Any, meta: Meta, path: Path, line: int,
    today: date,
) -> list[str]:  # fmt: skip
    """RESOURCE_DB §8.2 per-entry checks beyond the Pydantic types. Returns boot warnings."""
    warnings: list[str] = []
    if not ID_RE.match(res.id):
        raise _die(path, line, f"id {res.id!r} does not match ^[a-z0-9][a-z0-9_]{{1,39}}$")
    for url in (res.url, *res.alt_urls):
        if not URL_RE.match(url) or "#" in url or "utm_" in url:
            raise _die(path, line, f"url {url!r} must be https, without #fragment or utm_ params")
    if res.url in res.alt_urls:
        raise _die(path, line, "url must not repeat in alt_urls")
    for number in (res.phone, res.tty):
        if number is not None and not PHONE_RE.match(number):
            raise _die(path, line, f"phone/tty {number!r} is not E.164 or an N11 code")
    if res.text_line is not None and len(res.text_line) > 60:
        raise _die(path, line, "text_line longer than 60 characters")
    for tag in res.languages:
        if not LANGUAGE_RE.match(tag):
            raise _die(path, line, f"languages entry {tag!r} is not a BCP-47 tag")
    _check_serves(res, path, line)
    if len(res.tags) > MAX_TAGS:
        raise _die(path, line, f"more than {MAX_TAGS} tags")
    if not res.tags and not any(res.id in ids for ids in meta.doc_type_pins.values()):
        raise _die(path, line, "tags may be empty only for ids listed in doc_type_pins")
    if set(res.never_show_with_tags) & set(res.tags):
        raise _die(path, line, "never_show_with_tags overlaps tags")
    unknown_keys = [k for k in res.prepare_checklist_keys if k not in meta.checklist]
    if unknown_keys:
        raise _die(path, line, f"unknown prepare_checklist_keys {unknown_keys}")
    unknown_warn = [w for w in raw_warnings if w not in meta.warning_keys]
    if unknown_warn:
        raise _die(path, line, f"unknown warnings {unknown_warn} (use unprefixed registry keys)")
    warnings += _check_text("what_it_does", res.what_it_does, path, line)
    if "en" not in res.eligibility_plain:
        raise _die(path, line, "eligibility_plain must contain the 'en' entry")
    warnings += _check_text("eligibility_plain", res.eligibility_plain, path, line)
    if not MIN_VERIFIED_ON <= res.verified_on <= today:
        raise _die(
            path, line, f"verified_on {res.verified_on} must be in [{MIN_VERIFIED_ON}, today]"
        )
    if res.verification_method == VerificationMethod.manual_verify:
        if res.status_note_key != StatusNoteKey.manual_verify:
            raise _die(
                path, line, "verification_method manual_verify needs status_note_key manual_verify"
            )
    elif res.status_note_key == StatusNoteKey.manual_verify and res.phone is not None:
        raise _die(
            path, line, "status_note_key manual_verify without manual verification needs phone null"
        )
    if x_meta is not None:
        if not isinstance(x_meta, dict):
            raise _die(path, line, "x_meta must be a mapping")
        if not isinstance(x_meta.get("source"), str) or not x_meta["source"].strip():
            raise _die(path, line, "x_meta.source must be a non-empty string")
        expect = x_meta.get("expect_text", [])
        if not isinstance(expect, list) or not all(isinstance(t, str) for t in expect):
            raise _die(path, line, "x_meta.expect_text must be a list of strings")
    if res.link_health == LinkHealth.broken:
        warnings.append(f"{path}:{line}: {res.id} is broken (loaded inactive)")
    return warnings


LoadedEntry = tuple[Resource, dict[str, Any] | None, int]


def _load_file(path: Path, meta: Meta, today: date) -> tuple[list[LoadedEntry], list[str]]:
    """One resource file → ``(resource, x_meta, line)`` triples plus boot warnings."""
    text = path.read_text(encoding="utf-8")
    try:
        doc = yaml.safe_load(text)
        lines = _entry_lines(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 1 if mark is not None else 1
        raise _die(path, line, f"YAML syntax error: {exc}") from exc
    if not isinstance(doc, list):
        raise _die(path, 1, "resource file must be a YAML list of entries")
    loaded: list[LoadedEntry] = []
    warnings: list[str] = []
    for index, raw in enumerate(doc):
        line = lines[index] if index < len(lines) else 1
        if not isinstance(raw, dict):
            raise _die(path, line, "entry must be a mapping")
        entry = dict(raw)
        x_meta = entry.pop("x_meta", None)
        unknown = sorted(set(entry) - _RESOURCE_FIELDS)
        if unknown:
            raise _die(path, line, f"unknown fields {unknown}")
        entry = _apply_defaults(entry)
        raw_warnings = [str(w) for w in entry.get("warnings") or []]
        entry["warnings"] = [f"warn.{w}" for w in raw_warnings]
        try:
            res = Resource.model_validate(entry)
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first["loc"])
            raise _die(path, line, f"{loc}: {first['msg']}") from exc
        warnings += _check_entry(res, raw_warnings, x_meta, meta, path, line, today)
        loaded.append((res, x_meta, line))
    return loaded, warnings


def _cross_checks(
    resources: dict[str, Resource], browsable: set[str], active: set[str], meta: Meta,
    meta_path: Path,
) -> list[str]:
    """RESOURCE_DB §8.3; returns warnings, raises on hard failures.

    Coverage and reference checks run against *browsable* (non-broken) entries, so an entry
    ageing past 365 days never refuses boot (§8.1: freshness problems are warnings). When a tag
    or a ``_meta.yaml`` reference is carried only by stale-excluded entries, boot logs a warning
    and the matcher simply has no candidate for it until the entry is re-verified (§8.3.5).
    """
    warnings: list[str] = []
    covered: set[ResourceTag] = set()
    covered_active: set[ResourceTag] = set()
    for rid in browsable:
        covered.update(resources[rid].tags)
        if rid in active:
            covered_active.update(resources[rid].tags)
    stale_tags: list[str] = []
    for tag in ResourceTag:
        if tag not in covered:
            if tag in meta.fallback_only_tags:
                warnings.append(f"tag {tag.value} has no active entry (fallback-only tag)")
            else:
                raise _die(meta_path, None, f"tag {tag.value} has no active resource entry")
        elif tag not in covered_active:
            stale_tags.append(tag.value)
    if stale_tags:
        warnings.append(
            f"tags carried only by entries verified > 365 days ago (no match candidates until "
            f"re-verified): {stale_tags}"
        )
    referenced: list[tuple[str, str]] = []
    for doc_type, ids in meta.doc_type_pins.items():
        referenced += [(f"doc_type_pins.{doc_type.value}", rid) for rid in ids]
    for name, value in meta.well_known_ids.items():
        wk_ids = value if isinstance(value, list) else [value]
        referenced += [(f"well_known_ids.{name}", rid) for rid in wk_ids]
    stale_refs: dict[str, None] = {}
    for section, rid in referenced:
        if rid not in resources:
            raise _die(meta_path, None, f"{section} references unknown resource id {rid!r}")
        if rid not in browsable:
            raise _die(meta_path, None, f"{section} references inactive resource id {rid!r}")
        if rid not in active:
            stale_refs[rid] = None
    if stale_refs:
        warnings.append(
            f"_meta.yaml pins/well_known_ids reference entries verified > 365 days ago "
            f"(excluded from matching): {list(stale_refs)}"
        )
    return warnings


I18N_DIR = "i18n"
_I18N_FIELDS = ("what_it_does", "eligibility_plain")
I18N_TEXT_MAX = 600  # 300 English characters × the 1.8 length ratio of RESOURCE_DB §7.1 (+ slack)


def _merge_i18n(i18n_dir: Path, entries: list[LoadedEntry]) -> list[LoadedEntry]:
    """RESOURCE_DB §7.1: merge ``i18n/<tag>.yaml`` sidecars into ``what_it_does`` /
    ``eligibility_plain``. No sidecar directory (v1) → entries unchanged. English is never
    overwritten; an unknown id, tag or field refuses boot with ``path:line``."""
    if not i18n_dir.is_dir():
        return entries
    by_id = {res.id: i for i, (res, _x, _l) in enumerate(entries)}
    out = list(entries)
    for path in sorted(i18n_dir.glob("*.yaml")):
        tag = path.stem
        if tag == "en" or not LANGUAGE_RE.match(tag):
            raise _die(path, 1, f"sidecar name {tag!r} is not a non-English BCP-47 tag")
        text = path.read_text(encoding="utf-8")
        try:
            data = yaml.safe_load(text)
            node = yaml.compose(text)
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            raise _die(path, mark.line + 1 if mark else 1, f"YAML syntax error: {exc}") from exc
        if data is None:
            continue
        if not isinstance(data, dict):
            raise _die(path, 1, "sidecar must map resource ids to translated fields")
        lines: dict[str, int] = {}
        if isinstance(node, yaml.MappingNode):
            lines = {str(k.value): k.start_mark.line + 1 for k, _v in node.value}
        for rid, fields in data.items():
            line = lines.get(str(rid), 1)
            if str(rid) not in by_id:
                raise _die(path, line, f"unknown resource id {rid!r}")
            if not isinstance(fields, dict) or set(fields) - set(_I18N_FIELDS):
                raise _die(path, line, f"only {list(_I18N_FIELDS)} may be translated")
            index = by_id[str(rid)]
            res, x_meta, entry_line = out[index]
            update: dict[str, dict[str, str]] = {}
            for name, value in fields.items():
                if not isinstance(value, str) or not 1 <= len(value) <= I18N_TEXT_MAX:
                    raise _die(path, line, f"{rid}.{name} must be 1–{I18N_TEXT_MAX} characters")
                update[name] = {**getattr(res, name), tag: value}
            out[index] = (res.model_copy(update=update), x_meta, entry_line)
    return out


def _load_prepare(path: Path, meta: Meta) -> dict[DocumentType, list[str]]:
    """``data/rules/prepare.yaml`` (RESOURCE_DB §4.8); keys must exist in ``meta.checklist``."""
    if not path.is_file():
        logger.warning("prepare.yaml missing at %s; checklists use resource keys only", path)
        return {}
    try:
        return load_prepare(path, allowed_keys=meta.checklist)
    except PrepareLoadError as exc:
        raise ResourceLoadError(str(exc)) from exc


class ResourceRepo:
    """Read-only view of the loaded DB (RESOURCE_DB §8.4; BUILD_PLAN §4.1).

    ``all()`` = every browsable entry (``link_health != broken``); ``active()`` = the matcher's
    candidates (browsable and ``verified_on`` within 365 days of ``today``); ``count()`` = every
    entry that validated, including inactive ones (``/health.resources_loaded``).
    """

    def __init__(
        self,
        entries: list[LoadedEntry],
        meta: Meta,
        *,
        prepare: dict[DocumentType, list[str]] | None = None,
        today: date | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        today = today or date.today()
        self._meta = meta
        self._prepare: dict[DocumentType, list[str]] = dict(prepare or {})
        self._warnings: list[str] = list(warnings or [])
        self._loaded = len(entries)
        self._by_id: dict[str, Resource] = {}
        self._x_meta: dict[str, dict[str, Any]] = {}
        self._broken: set[str] = set()
        self._stale_excluded: set[str] = set()
        self._stale_warn: set[str] = set()
        for res, x_meta, _line in entries:
            self._by_id[res.id] = res
            if x_meta is not None:
                self._x_meta[res.id] = x_meta
            if res.link_health == LinkHealth.broken:
                self._broken.add(res.id)
            age = (today - res.verified_on).days
            if age > STALE_EXCLUDE_DAYS:
                self._stale_excluded.add(res.id)
                self._warnings.append(f"{res.id}: verified_on {res.verified_on} is > 365 days old")
            elif age > STALE_WARN_DAYS:
                self._stale_warn.add(res.id)
                self._warnings.append(f"{res.id}: verified_on {res.verified_on} is > 120 days old")
        names: set[str] = set()
        phones: dict[str, str] = {}
        for res in self._by_id.values():
            if res.id in self._broken:
                continue
            for text in (res.name, res.name_note, *self._x_meta.get(res.id, {}).get("aliases", [])):
                if isinstance(text, str) and normalize_org_name(text):
                    names.add(normalize_org_name(text))
            for number in (res.phone, res.tty):
                if number is not None:
                    phones.setdefault(number, res.id)
        self._org_names: frozenset[str] = frozenset(names)
        self._phone_index: dict[str, str] = phones

    @classmethod
    def load(
        cls, dir: Path, *, today: date | None = None, prepare_path: Path | None = None
    ) -> ResourceRepo:  # noqa: A002 - name fixed by BUILD_PLAN §4.1
        """RESOURCE_DB §8.1 boot sequence; raises ``ResourceLoadError`` (``path:line: …``)."""
        today = today or date.today()
        try:
            meta_path = dir / "_meta.yaml"
            meta = load_meta(meta_path)
            entries: list[LoadedEntry] = []
            warnings: list[str] = []
            seen: dict[str, str] = {}
            files = sorted(
                p
                for p in dir.rglob("*.yaml")
                if not p.name.startswith("_") and I18N_DIR not in p.relative_to(dir).parts
            )
            per_file: dict[str, int] = {}
            for path in files:
                loaded, file_warnings = _load_file(path, meta, today)
                warnings += file_warnings
                for res, x_meta, line in loaded:
                    if res.id in seen:
                        raise _die(path, line, f"duplicate id {res.id!r} (also in {seen[res.id]})")
                    seen[res.id] = f"{path}:{line}"
                    entries.append((res, x_meta, line))
                per_file[str(path.relative_to(dir))] = len(loaded)
            entries = _merge_i18n(dir / I18N_DIR, entries)
            resources = {res.id: res for res, _x, _l in entries}
            browsable = {
                res.id for res, _x, _l in entries if res.link_health != LinkHealth.broken
            }
            active = {
                rid
                for rid in browsable
                if (today - resources[rid].verified_on).days <= STALE_EXCLUDE_DAYS
            }
            warnings += _cross_checks(resources, browsable, active, meta, meta_path)
            if prepare_path is None:
                prepare_path = dir.parent / "rules" / "prepare.yaml"
            prepare = _load_prepare(prepare_path, meta)
            repo = cls(entries, meta, prepare=prepare, today=today, warnings=warnings)
            if not repo.org_names():
                raise _die(meta_path, None, "org_names() is empty")
            phone_like = sorted(n for n in repo.org_names() if PHONE_LIKE_RE.search(n))
            if phone_like:
                raise _die(meta_path, None, f"org_names() contains phone-like digits: {phone_like}")
        except ResourceLoadError as exc:
            logger.error("resource DB refused: %s", exc)
            raise
        for warning in repo.warnings:
            logger.warning("resource DB: %s", warning)
        logger.info(
            "resources_loaded=%d active=%d stale=%d files=%s version=%s",
            repo.count(), len(repo.active()), len(repo._stale_warn) + len(repo._stale_excluded),
            per_file, repo.version,
        )  # fmt: skip
        return repo

    # ---- BUILD_PLAN §4.1 surface -------------------------------------------------------------

    def all(self) -> builtins.list[Resource]:
        """Browsable entries (everything except ``broken``), in file order."""
        return [r for r in self._by_id.values() if r.id not in self._broken]

    def get(self, id: str) -> Resource | None:  # noqa: A002 - name fixed by BUILD_PLAN §4.1
        res = self._by_id.get(id)
        if res is None or res.id in self._broken:
            return None
        return res

    def names(self) -> set[str]:
        """Raw organization names (``name`` + ``name_note``) of browsable entries."""
        out: set[str] = set()
        for res in self.all():
            out.add(res.name)
            if res.name_note:
                out.add(res.name_note)
        return out

    @property
    def version(self) -> str:
        return self._meta.resource_db_version

    # ---- RESOURCE_DB §8.4 surface ------------------------------------------------------------

    @property
    def meta(self) -> Meta:
        return self._meta

    @property
    def warnings(self) -> builtins.list[str]:
        """Boot warnings (freshness, readability, broken entries) — never fatal."""
        return list(self._warnings)

    def active(self) -> builtins.list[Resource]:
        """Matcher candidates: browsable and verified within the last 365 days."""
        return [r for r in self.all() if r.id not in self._stale_excluded]

    def count(self) -> int:
        """Every entry that validated, inactive ones included (``/health.resources_loaded``)."""
        return self._loaded

    def loaded(self) -> builtins.list[Resource]:
        """Every validated entry including ``broken`` ones (``scripts/check_links.py`` only)."""
        return list(self._by_id.values())

    def stale_ids(self) -> frozenset[str]:
        """Entries older than 120 days (warned) or 365 days (excluded from matching)."""
        return frozenset(self._stale_warn | self._stale_excluded)

    def is_stale_excluded(self, id: str) -> bool:  # noqa: A002
        return id in self._stale_excluded

    def org_names(self) -> frozenset[str]:
        """Normalized ``name`` / ``name_note`` / ``x_meta.aliases`` (D-10 contacts allow-list)."""
        return self._org_names

    def phone_index(self) -> dict[str, str]:
        """E.164 / N11 number → resource id (quick-sheet re-validation, RESOURCE_DB §7)."""
        return dict(self._phone_index)

    def is_hhs_funded(self, id: str) -> bool:  # noqa: A002
        """D-18 / RESOURCE_DB §3.3 derivation: note ``hhs_funded_health`` or FQHC/hospital."""
        res = self.get(id)
        if res is None:
            return False
        return res.status_note_key == StatusNoteKey.hhs_funded_health or (
            res.org_type in HHS_FUNDED_ORG_TYPES
        )

    def well_known(self, name: str) -> str | builtins.list[str]:
        """``_meta.yaml.well_known_ids[name]`` (boot asserts the ids exist and are not broken)."""
        value = self._meta.well_known_ids[name]
        return list(value) if isinstance(value, list) else value

    def well_known_ids(self, name: str) -> builtins.list[str]:
        value = self.well_known(name)
        return list(value) if isinstance(value, list) else [value]

    def prepare_map(self) -> dict[DocumentType, builtins.list[str]]:
        """``prepare.yaml`` as loaded (document type → checklist keys)."""
        return {k: list(v) for k, v in self._prepare.items()}

    def prepare_items(self, doc_type: DocumentType) -> builtins.list[str]:
        return list(self._prepare.get(doc_type, []))

    def x_meta(self, id: str) -> dict[str, Any] | None:  # noqa: A002
        """The YAML-only ``x_meta`` block (``scripts/check_links.py`` reads ``expect_text``)."""
        block = self._x_meta.get(id)
        return dict(block) if block is not None else None

    def list(
        self,
        *,
        tag: ResourceTag | None = None,
        state: str | None = None,
        language: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[builtins.list[Resource], int]:
        """RESOURCE_DB §7 ``GET /v1/resources`` filters; ``total`` counts before paging."""
        items = self.all()
        if tag is not None:
            items = [r for r in items if tag in r.tags]
        if state:
            st = state.strip().upper()
            items = [
                r for r in items if r.serves.scope == GeoScope.national or st in r.serves.states
            ]
        if language:
            lang = language.strip()
            items = [r for r in items if lang in r.languages or "interpreters_200+" in r.languages]
        if q:
            needle = q.casefold().strip()
            items = [
                r
                for r in items
                if needle in r.name.casefold()
                or needle in r.id.casefold()
                or (r.name_note is not None and needle in r.name_note.casefold())
            ]
        items.sort(key=lambda r: (-r.priority, r.name.casefold(), r.id))
        total = len(items)
        return items[offset : offset + limit], total


__all__ = [
    "Meta",
    "ResourceLoadError",
    "ResourceRepo",
    "county_display",
    "load_meta",
    "normalize_county",
    "normalize_org_name",
]
