"""Text-only quick-sheet PDF: ``POST /v1/quicksheet/pdf`` (API_CONTRACT §3.11)."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from proxyhealth_api.contracts.common import LanguageTag
from proxyhealth_api.contracts.enums import Direction


class QuickSheetSection(BaseModel):
    """API_CONTRACT §3.11 — one card of the sheet (heading in both languages, ≤ 40 lines)."""

    model_config = ConfigDict(extra="forbid")

    heading: str
    heading_en: str
    lines: list[str] = Field(max_length=40)


class QuickSheetResource(BaseModel):
    """API_CONTRACT §3.11 — a resource line; the server re-validates it against the DB."""

    model_config = ConfigDict(extra="forbid")

    name: str
    phone: str | None = None
    url: str | None = None


class QuickSheetRequest(BaseModel):
    """API_CONTRACT §3.11 — everything the PDF renders; nothing is stored."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=120)
    language_tag: LanguageTag
    direction: Direction
    font_hint: str | None = None
    sections: list[QuickSheetSection] = Field(max_length=8)
    resources: list[QuickSheetResource] = Field(max_length=8)
    footer: str
    generated_on: date
