"""Sample papers: ``GET /v1/demo/fixtures`` (API_CONTRACT §3.13)."""

from typing import Literal

from pydantic import BaseModel

from proxyhealth_api.contracts.common import LanguageTag
from proxyhealth_api.contracts.enums import DocumentCategory, DocumentType


class DemoFixture(BaseModel):
    """API_CONTRACT §3.13 — one synthetic, watermarked sample paper or screenshot."""

    id: str
    title_key: str
    title_en: str
    document_type: DocumentType
    category: DocumentCategory
    language_of_document: LanguageTag
    pages: int
    available_target_languages: list[LanguageTag]
    thumbnail_url: str
    kind: Literal["document", "screenshot"]
