"""Deadline rules table: ``GET /v1/rules`` (API_CONTRACT §3.10)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from proxyhealth_api.contracts.enums import DocumentType, RuleVerification


class DeadlineRule(BaseModel):
    """API_CONTRACT §3.10 — one sourced relative-deadline rule (the ``rules.yaml`` shape)."""

    id: str
    label_en: str
    applies_to_doc_types: list[DocumentType]
    pattern: str
    days: int
    count_basis: Literal["calendar", "business"]
    anchor_role: str
    receipt_based: bool
    mail_days: int
    source_url: str
    source_verified_on: date
    verification: RuleVerification
    valid_until: date | None
    notes_en: str | None


class RulesResponse(BaseModel):
    """API_CONTRACT §3.10 — the whole rules table with its version."""

    rules_version: str
    rules: list[DeadlineRule]
