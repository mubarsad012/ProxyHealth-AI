"""Deterministic resource matcher (RESOURCE_DB §5 geography, §6 algorithm; API_CONTRACT §3.8).

Pure functions: no randomness, no model calls, no I/O; ``today`` is injected. Identical input →
identical output (the golden tests depend on it). ``score`` orders results only and is never
shown to the user.

Interpretations recorded here because the spec examples and rules disagree in places:

* Crisis-forced entries (``emergency=true``) are the *dedicated* crisis services — entries whose
  tags all lie in {crisis, poison, domestic_violence, trafficking} (the four D-14 lines; RESOURCE_DB
  §12.1). Multi-purpose entries that merely carry one of those tags (211, DV legal nonprofits)
  rank normally, so the bill/letter resources still follow the hotlines (RESOURCE_DB §6.11-E).
  Crisis-forced entries are exempt from the ≤ 2 per ``org_type`` cap (RESOURCE_DB §6.7);
  scam-forced entries are ordered first but **stay capped** (RESOURCE_DB §6.11-D, §12.2: "the cap
  allows only two government scam pages").
* Inside a forced block the order is the one the worked examples list, not raw score:
  crisis lines follow the D-14 emergency card (``well_known_ids.emergency_card``: 988, poison,
  DV), then priority; scam entries go by priority, then score, so ``dhs_oig`` leads
  (RESOURCE_DB §6.11-D/E and the §10 test "scam_risk=likely puts dhs_oig first"). Non-forced
  entries sort by score desc, priority desc, id asc (§6.6.3).
* ``notes.resource_text_english_only`` follows the §6.10 rule (and §7.1: v1 YAML is English
  only), so a non-English request gets it even where a §6.11 example omits it.
* ``notes.no_local_results`` means no *eligible* non-national candidate existed for the user's
  state — not merely that ``limit`` cut the local ones (RESOURCE_DB §6.10 wording, §6.11-B intent).
* ``why.serves_your_county`` is used when the user's county matched; a zip3-only match renders
  ``why.serves_your_area`` even if a (non-matching) county was supplied.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher

from proxyhealth_api.contracts.enums import (
    DisclaimerKind,
    GeoScope,
    LinkHealth,
    ResourceTag,
    ScamRisk,
    StatusNoteKey,
    VerificationMethod,
)
from proxyhealth_api.contracts.resources import (
    Resource,
    ResourceMatch,
    ResourceMatchRequest,
    ResourceMatchResponse,
)
from proxyhealth_api.resources import checklist
from proxyhealth_api.resources.loader import (
    STALE_WARN_DAYS,
    Meta,
    ResourceRepo,
    county_display,
    normalize_county,
    normalize_org_name,
)

# RESOURCE_DB §3.1 tag groups used by ``national_fallbacks`` (§6.9).
IMMIGRATION_GROUP: frozenset[ResourceTag] = frozenset(
    {
        ResourceTag.immigration_legal_help, ResourceTag.removal_proceedings, ResourceTag.asylum,
        ResourceTag.daca_tps, ResourceTag.work_permit, ResourceTag.green_card,
        ResourceTag.naturalization, ResourceTag.change_of_address, ResourceTag.fee_waiver,
        ResourceTag.afghan_specific, ResourceTag.refugee_services, ResourceTag.court_notice,
    }
)  # fmt: skip
HEALTH_GROUP: frozenset[ResourceTag] = frozenset(
    {
        ResourceTag.medical_bill, ResourceTag.charity_care, ResourceTag.insurance_denial,
        ResourceTag.medicare_appeal, ResourceTag.medicaid_renewal, ResourceTag.prescription_help,
        ResourceTag.primary_care_uninsured, ResourceTag.lab_results, ResourceTag.vaccine_records,
    }
)  # fmt: skip
CRISIS_TAGS: frozenset[ResourceTag] = frozenset(
    {ResourceTag.crisis, ResourceTag.poison, ResourceTag.domestic_violence, ResourceTag.trafficking}
)

GEO_NATIONAL = 0.5
GEO_STATE = 0.7
GEO_LOCALITY_UNKNOWN = 0.9
GEO_LOCAL = 1.0
LANG_EXACT = 1.0
LANG_FAMILY = 0.9
LANG_OTHER = 0.8
INSTITUTION_BONUS = 0.5
PIN_BONUS = 0.5
DOC_BOOST = 0.5
PENALTY_LSC = 0.2
PENALTY_MANUAL_VERIFY = 0.2
PENALTY_LINK_SOFT = 0.1
PENALTY_LINK_UNVERIFIED = 0.3
PENALTY_STALE = 0.3
FUZZY_RATIO = 0.85
MAX_PER_ORG_TYPE = 2
MAX_WHY_KEYS = 4

FORCED_NONE = 0
FORCED_SCAM = 1
FORCED_CRISIS = 2

_SOFT_LINKS = frozenset({LinkHealth.unknown_403, LinkHealth.js_rendered})


@dataclass
class Scored:
    """One candidate with its score components (kept for tests and ``why`` rendering)."""

    resource: Resource
    score: float
    forced: int
    tag_score: float
    geo: float
    geo_key: str
    language: float
    institution: str | None
    pinned: bool
    boosted: bool
    penalties: float
    shared: list[ResourceTag] = field(default_factory=list)
    county: str | None = None


@dataclass(frozen=True)
class _Location:
    state: str | None
    county: str | None  # canonical comparison form
    zip3: str | None

    @property
    def locality_known(self) -> bool:
        return self.county is not None or self.zip3 is not None


def _location(req: ResourceMatchRequest) -> _Location:
    state = req.state.strip().upper() if req.state and req.state.strip() else None
    county = normalize_county(req.county) if req.county and req.county.strip() else None
    zip3 = req.zip3.strip() if req.zip3 and req.zip3.strip() else None
    return _Location(state=state, county=county or None, zip3=zip3)


def geo_credit(res: Resource, loc: _Location) -> tuple[float, str, str | None] | None:
    """RESOURCE_DB §5 table → ``(geo, why_key, matched_county)`` or ``None`` when excluded."""
    s = res.serves
    if s.scope == GeoScope.national:
        return GEO_NATIONAL, "why.anywhere_in_us", None
    if loc.state is None or loc.state not in s.states:
        return None
    if s.scope == GeoScope.state:
        return GEO_STATE, "why.serves_your_state", None
    if not loc.locality_known:
        return GEO_LOCALITY_UNKNOWN, "why.check_service_area", None
    if loc.county is not None:
        for canonical in s.counties:
            if normalize_county(canonical) == loc.county:
                return GEO_LOCAL, "why.serves_your_county", canonical
    if loc.zip3 is not None and loc.zip3 in s.zip3:
        return GEO_LOCAL, "why.serves_your_area", None
    return None


def language_credit(req_language: str, languages: list[str], meta: Meta) -> float:
    """1.0 exact / interpreters, 0.9 same primary subtag or ``language_families`` pair, else 0.8."""
    if req_language in languages or "interpreters_200+" in languages:
        return LANG_EXACT
    primary = req_language.split("-")[0]
    for lang in languages:
        if lang == "interpreters_200+":
            continue
        if lang.split("-")[0] == primary:
            return LANG_FAMILY
        if meta.same_family(req_language, lang) or meta.same_family(primary, lang):
            return LANG_FAMILY
    return LANG_OTHER


def institution_match(institutions: list[str], res: Resource) -> str | None:
    """RESOURCE_DB §6.3 fuzzy institution match; returns the institution as written."""
    candidates = [normalize_org_name(t) for t in (res.name, res.name_note or "") if t]
    candidates = [c for c in candidates if c]
    for written in institutions:
        a = normalize_org_name(written)
        if len(a) < 3:
            continue
        for b in candidates:
            if a in b or b in a or SequenceMatcher(None, a, b).ratio() >= FUZZY_RATIO:
                return written
    return None


def tag_score(
    req_tags: list[ResourceTag], res_tags: list[ResourceTag]
) -> tuple[float, list[ResourceTag]]:
    """``2·Jaccard + 1`` if the primary (first) request tag is carried; shared in request order."""
    r = set(req_tags)
    s = set(res_tags)
    shared = [t for t in req_tags if t in s]
    if not shared:
        return 0.0, []
    jaccard = len(r & s) / len(r | s)
    return 2.0 * jaccard + (1.0 if req_tags[0] in s else 0.0), shared


def penalties(res: Resource, today: date) -> float:
    total = 0.0
    if res.status_note_key == StatusNoteKey.lsc_restricted:
        total += PENALTY_LSC
    if (
        res.status_note_key == StatusNoteKey.manual_verify
        or res.verification_method == VerificationMethod.manual_verify
    ):
        total += PENALTY_MANUAL_VERIFY
    if res.link_health in _SOFT_LINKS:
        total += PENALTY_LINK_SOFT
    elif res.link_health == LinkHealth.unverified:
        total += PENALTY_LINK_UNVERIFIED
    if (today - res.verified_on).days > STALE_WARN_DAYS:
        total += PENALTY_STALE
    return total


def is_dedicated_crisis(res: Resource) -> bool:
    """True for the D-14 crisis lines: every tag is in the crisis group (988, DV, poison, …)."""
    return bool(res.tags) and set(res.tags) <= CRISIS_TAGS


def _forced_rank(req: ResourceMatchRequest, res: Resource) -> int:
    tags = set(res.tags)
    if req.emergency and is_dedicated_crisis(res):
        return FORCED_CRISIS
    if req.scam_risk == ScamRisk.likely and ResourceTag.scam_report in tags:
        return FORCED_SCAM
    return FORCED_NONE


def score_candidates(
    req: ResourceMatchRequest, repo: ResourceRepo, *, today: date
) -> tuple[list[Scored], bool]:
    """RESOURCE_DB §6.1–§6.5: every eligible candidate, scored; plus "a local candidate exists"."""
    meta = repo.meta
    loc = _location(req)
    req_tags = list(dict.fromkeys(req.tags))
    pins = set(meta.doc_type_pins.get(req.document_type, ())) if req.document_type else set()
    boost_tags = meta.urgent_doc_boost.get(req.document_type) if req.document_type else None
    scored: list[Scored] = []
    local_candidate = False
    for res in repo.active():
        forced = _forced_rank(req, res)
        t_score, shared = tag_score(req_tags, res.tags)
        pinned = res.id in pins
        if not shared and not pinned and forced == FORCED_NONE:
            continue
        if set(res.never_show_with_tags) & set(req_tags):
            continue
        geo = geo_credit(res, loc)
        if geo is None:
            continue
        geo_value, geo_key, county = geo
        if res.serves.scope != GeoScope.national:
            local_candidate = True
        language = language_credit(req.language, res.languages, meta)
        institution = institution_match(req.institutions_as_written, res)
        boosted = bool(boost_tags) and bool(set(res.tags) & set(boost_tags or ()))
        penalty = penalties(res, today)
        total = (
            t_score
            + geo_value
            + language
            + (INSTITUTION_BONUS if institution else 0.0)
            + res.priority / 100
            + (PIN_BONUS if pinned else 0.0)
            + (DOC_BOOST if boosted else 0.0)
            - penalty
        )
        scored.append(
            Scored(
                resource=res,
                score=round(total, 6),
                forced=forced,
                tag_score=t_score,
                geo=geo_value,
                geo_key=geo_key,
                language=language,
                institution=institution,
                pinned=pinned,
                boosted=boosted,
                penalties=penalty,
                shared=shared,
                county=county,
            )
        )
    card = repo.well_known_ids("emergency_card")
    scored.sort(key=lambda c: order_key(c, card))
    return scored, local_candidate


def order_key(cand: Scored, emergency_card: list[str]) -> tuple[int, int, float, float, str]:
    """RESOURCE_DB §6.6: crisis block → scam block → everything else (see module docstring)."""
    res = cand.resource
    if cand.forced == FORCED_CRISIS:
        slot = emergency_card.index(res.id) if res.id in emergency_card else len(emergency_card)
        return (-cand.forced, slot, -res.priority, -cand.score, res.id)
    if cand.forced == FORCED_SCAM:
        return (-cand.forced, 0, -res.priority, -cand.score, res.id)
    return (-cand.forced, 0, -cand.score, -res.priority, res.id)


def apply_diversity_cap(scored: list[Scored], limit: int) -> list[Scored]:
    """RESOURCE_DB §6.7: ≤ 2 per ``org_type`` (crisis-forced exempt), stop at ``limit``."""
    counts: dict[str, int] = {}
    kept: list[Scored] = []
    for cand in scored:
        org = cand.resource.org_type.value
        if cand.forced != FORCED_CRISIS and counts.get(org, 0) >= MAX_PER_ORG_TYPE:
            continue
        counts[org] = counts.get(org, 0) + 1
        kept.append(cand)
        if len(kept) >= limit:
            break
    return kept


def why_keys_for(cand: Scored, req_tags: list[ResourceTag]) -> list[str]:
    """RESOURCE_DB §6.8 order, forced key first, at most ``MAX_WHY_KEYS``."""
    keys: list[str] = []
    if cand.forced == FORCED_CRISIS:
        keys.append("why.crisis_line")
    elif cand.forced == FORCED_SCAM:
        keys.append("why.report_scam")
    if cand.pinned:
        keys.append("why.for_this_paper")
    if cand.institution:
        keys.append("why.institution_match")
    if cand.shared:
        primary = req_tags[0]
        tag = primary if primary in cand.shared else cand.shared[0]
        keys.append(f"why.for_{tag.value}")
    keys.append(cand.geo_key)
    if cand.language >= LANG_EXACT:
        keys.append("why.speaks_your_language")
    return keys[:MAX_WHY_KEYS]


def render_why(
    key: str, cand: Scored, loc_state: str | None, meta: Meta, strings: Mapping[str, str]
) -> str:
    template = strings.get(key) or meta.strings().get(key) or key
    text = template
    if "{institution}" in text:
        text = text.replace("{institution}", cand.institution or "")
    if "{county}" in text:
        text = text.replace("{county}", county_display(cand.county) if cand.county else "")
    if "{state}" in text:
        text = text.replace("{state}", meta.state_names.get(loc_state or "", loc_state or ""))
    return text.strip()


def national_fallbacks(
    req: ResourceMatchRequest, repo: ResourceRepo, result_ids: set[str]
) -> list[Resource]:
    """RESOURCE_DB §6.9 ordered, de-duplicated against ``results`` and itself."""
    req_tags = set(req.tags)
    wanted: list[str] = list(repo.well_known_ids("fallback_always"))
    if req_tags & IMMIGRATION_GROUP:
        wanted += repo.well_known_ids("fallback_immigration")
    if req_tags & HEALTH_GROUP:
        wanted += repo.well_known_ids("fallback_health")
    if req.scam_risk != ScamRisk.none:
        wanted += repo.well_known_ids("fallback_scam")
    if req.emergency:
        wanted += repo.well_known_ids("fallback_emergency")[:1]
    out: list[Resource] = []
    seen: set[str] = set(result_ids)
    for rid in wanted:
        if rid in seen:
            continue
        res = repo.get(rid)
        if res is None or repo.is_stale_excluded(rid):  # §8.3.5: > 365 d → not matched
            continue
        seen.add(rid)
        out.append(res)
    return out


def notes_keys_for(
    req: ResourceMatchRequest,
    loc: _Location,
    eligible: list[Scored],
    results: list[Scored],
    local_candidate: bool,
) -> list[str]:
    """RESOURCE_DB §6.10 in its listed order; ``notes.verify_before_going`` always last."""
    keys: list[str] = []
    if loc.state is None:
        keys.append("notes.set_region_for_local_help")
    else:
        if not loc.locality_known and any(c.geo == GEO_LOCALITY_UNKNOWN for c in eligible):
            keys.append("notes.county_unknown")
        if not local_candidate:
            keys.append("notes.no_local_results")
    if any(c.resource.status_note_key == StatusNoteKey.lsc_restricted for c in results):
        keys.append("notes.lsc_restricted_explained")
    if req.language != "en" and any(req.language not in c.resource.what_it_does for c in results):
        keys.append("notes.resource_text_english_only")
    keys.append("notes.verify_before_going")
    return keys


def match(
    req: ResourceMatchRequest,
    repo: ResourceRepo,
    *,
    en_strings: Mapping[str, str] | None = None,
    today: date | None = None,
) -> ResourceMatchResponse:
    """BUILD_PLAN §4.1 signature. ``en_strings`` (the base pack) overrides ``_meta.yaml`` copy."""
    today = today or date.today()
    strings: Mapping[str, str] = en_strings if en_strings is not None else {}
    meta = repo.meta
    loc = _location(req)
    req_tags = list(dict.fromkeys(req.tags))
    eligible, local_candidate = score_candidates(req, repo, today=today)
    kept = apply_diversity_cap(eligible, req.limit)
    prepare = repo.prepare_map()
    results: list[ResourceMatch] = []
    for cand in kept:
        keys = why_keys_for(cand, req_tags)
        results.append(
            ResourceMatch(
                resource=cand.resource,
                score=round(cand.score, 2),
                why_keys=keys,
                why=[render_why(k, cand, loc.state, meta, strings) for k in keys],
                eligibility_note_key=cand.resource.status_note_key,
                checklist=checklist.build(
                    cand.resource,
                    req.document_type,
                    checklist_text=meta.checklist,
                    prepare=prepare,
                ),
            )
        )
    result_ids = {c.resource.id for c in kept}
    return ResourceMatchResponse(
        results=results,
        national_fallbacks=national_fallbacks(req, repo, result_ids),
        notes_keys=notes_keys_for(req, loc, eligible, kept, local_candidate),
        disclaimer_kind=DisclaimerKind.general_information,
        resource_db_version=repo.version,
    )


__all__ = [
    "CRISIS_TAGS",
    "HEALTH_GROUP",
    "IMMIGRATION_GROUP",
    "Scored",
    "apply_diversity_cap",
    "geo_credit",
    "institution_match",
    "is_dedicated_crisis",
    "language_credit",
    "match",
    "national_fallbacks",
    "order_key",
    "penalties",
    "score_candidates",
    "tag_score",
    "why_keys_for",
]
