"""Vetted resources: resource matching (API_CONTRACT §3.8) and browsing (§3.9)."""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from proxyhealth_api.contracts.common import LanguageTag
from proxyhealth_api.contracts.enums import (
    Cost,
    DisclaimerKind,
    DocumentCategory,
    DocumentType,
    GeoScope,
    LinkHealth,
    OrgType,
    ResourceTag,
    ScamRisk,
    StatusNoteKey,
    VerificationMethod,
)

# API_CONTRACT §3.8 — E.164 or a bare N11 / short code (211, 311, 911, 988, 711).
PHONE_PATTERN = r"^(\+[1-9]\d{6,14}|211|311|911|988|711)$"
PhoneNumber = Annotated[str, StringConstraints(pattern=PHONE_PATTERN)]

# ``ResourceMatchRequest.institutions_as_written`` caps (Phase 2C; ``resources.matcher`` applies the
# same bounds for direct callers).
MAX_INSTITUTIONS = 10
MAX_INSTITUTION_CHARS = 200


class Serves(BaseModel):
    """API_CONTRACT §3.8 — service area of a resource."""

    scope: GeoScope
    states: list[str]
    counties: list[str]
    cities: list[str]
    zip3: list[str]


class Resource(BaseModel):
    """API_CONTRACT §3.8 — one vetted resource; also the schema of ``data/resources/*.yaml``."""

    id: str
    name: str
    name_note: str | None
    org_type: OrgType
    what_it_does: dict[str, str]
    url: str
    alt_urls: list[str]
    phone: PhoneNumber | None
    tty: PhoneNumber | None
    text_line: str | None
    hours: str | None
    languages: list[str]
    cost: Cost
    serves: Serves
    tags: list[ResourceTag]
    status_note_key: StatusNoteKey | None
    eligibility_plain: dict[str, str]
    prepare_checklist_keys: list[str]
    verified_on: date
    verification_method: VerificationMethod
    link_health: LinkHealth
    warnings: list[str]
    priority: int = Field(ge=0, le=100)
    never_show_with_tags: list[ResourceTag]

    @field_validator("what_it_does")
    @classmethod
    def _english_required(cls, value: dict[str, str]) -> dict[str, str]:
        if "en" not in value:
            raise ValueError("what_it_does must contain the 'en' entry")
        return value


class ChecklistItem(BaseModel):
    """API_CONTRACT §3.8 — one "bring this" item; ``key`` renders as ``prepare.<key>``."""

    key: str
    text_en: str


class ResourceMatch(BaseModel):
    """API_CONTRACT §3.8 — one scored match; ``score`` orders only and is never displayed."""

    resource: Resource
    score: float
    why_keys: list[str]
    why: list[str]
    eligibility_note_key: StatusNoteKey | None
    checklist: list[ChecklistItem]


class ResourceMatchRequest(BaseModel):
    """API_CONTRACT §3.8 — tags × location × language for the deterministic matcher."""

    model_config = ConfigDict(extra="forbid")

    tags: list[ResourceTag] = Field(min_length=1, max_length=12)
    document_type: DocumentType | None = None
    category: DocumentCategory | None = None
    state: str | None = None
    county: str | None = None
    zip3: str | None = None
    language: LanguageTag
    # Phase 2C caps: ≤ 10 names of ≤ 200 chars (``matcher.MAX_INSTITUTION_CHARS``; the analysis
    # pipeline emits ≤ 120-char names, so a client echoing ``entities`` always fits).
    institutions_as_written: list[
        Annotated[str, StringConstraints(max_length=MAX_INSTITUTION_CHARS)]
    ] = Field(default_factory=list, max_length=MAX_INSTITUTIONS)
    scam_risk: ScamRisk = ScamRisk.none
    emergency: bool = False
    limit: int = Field(default=8, ge=1, le=12)


class ResourceMatchResponse(BaseModel):
    """API_CONTRACT §3.8 — scored results plus ordered national fallbacks."""

    results: list[ResourceMatch]
    national_fallbacks: list[Resource]
    notes_keys: list[str]
    disclaimer_kind: DisclaimerKind
    resource_db_version: str


class ResourceList(BaseModel):
    """API_CONTRACT §3.9 — browse/search page of resources."""

    items: list[Resource]
    total: int
    resource_db_version: str
