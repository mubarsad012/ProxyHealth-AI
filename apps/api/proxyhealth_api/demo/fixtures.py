"""``FixtureStore`` (BUILD_PLAN §4.1). WP0: one inline fixture, no ``data/fixtures/`` needed.

The page PNG is generated with Pillow at first use and kept in memory only (never on disk).
"""

import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from proxyhealth_api.contracts.analysis import GlossaryTerm
from proxyhealth_api.contracts.common import TextBlock, TranslatedPage
from proxyhealth_api.contracts.demo import DemoFixture
from proxyhealth_api.contracts.enums import (
    Confidence,
    DemandKind,
    DocumentCategory,
    DocumentType,
    Legibility,
    PlanStepKind,
    SenderKind,
)
from proxyhealth_api.contracts.model_out import (
    AnalysisModelOut,
    DemandOut,
    PlanStepOut,
    TroubleshootModelOut,
)

INLINE_FIXTURE_ID = "medicaid_address_confirmation"

_LINES: list[tuple[str, str]] = [
    ("b1", "Virginia Department of Medical Assistance Services"),
    ("b2", "Cover Virginia - Medicaid and FAMIS"),
    ("b3", "Date: September 10, 2026"),
    ("b4", "IMPORTANT: Please confirm your address"),
    ("b5", "We need your correct mailing address so you do not miss letters about your "
           "Medicaid coverage."),
    ("b6", "Please confirm or update your address within 30 days of the date of this letter."),
    ("b7", "You can confirm your address online, by phone using the number on your Medicaid "
           "card, or by mailing the enclosed form."),
    ("b8", "If we do not hear from you, we may not be able to send you your renewal packet."),
    ("b9", "Case number: ******1234"),
    ("b10", "SAMPLE - This is a synthetic document for demonstration only."),
]  # fmt: skip


def _blocks() -> list[TextBlock]:
    out: list[TextBlock] = []
    for i, (bid, text) in enumerate(_LINES):
        y0 = 0.08 + i * 0.07
        out.append(
            TextBlock(
                id=bid, page=1, text=text, bbox=[0.08, y0, 0.92, y0 + 0.05],
                is_handwriting=False, is_unclear=False,
            )
        )  # fmt: skip
    return out


def _transcript() -> str:
    return "\n".join(text for _, text in _LINES)


def medicaid_address_confirmation_out() -> AnalysisModelOut:
    """English ``AnalysisModelOut`` for the inline fixture (validator-clean by construction)."""
    return AnalysisModelOut(
        document_type=DocumentType.medicaid_renewal,
        category=DocumentCategory.benefits,
        document_type_confidence=Confidence.high,
        sender_as_written="Virginia Department of Medical Assistance Services",
        sender_kind=SenderKind.state_agency,
        detected_language="en",
        translated_pages=[TranslatedPage(page=1, text=_transcript())],
        summary_title="Medicaid asks you to confirm your address",
        summary_body=(
            "This letter is from Virginia Medicaid. It asks you to confirm your mailing "
            "address within 30 days. If you do not, you may miss your renewal papers."
        ),
        summary_body_en=(
            "This letter is from Virginia Medicaid. It asks you to confirm your mailing "
            "address within 30 days. If you do not, you may miss your renewal papers."
        ),
        summary_span_ids=["b1", "b6", "b8"],
        demands=[
            DemandOut(
                id="d1", kind=DemandKind.relative_deadline,
                text="Confirm or update your address within 30 days of the letter date.",
                value_verbatim="within 30 days",
                source_quote=(
                    "Please confirm or update your address within 30 days of the date of this "
                    "letter."
                ),
                span_ids=["b6"], page=1, date_text=None, time_text=None,
                relative_rule_text="within 30 days of the date of this letter",
                anchor_span_id="b3", amount_text=None, currency=None, documents=[], role=None,
                confidence=Confidence.high, ambiguity_note=None,
            ),
            DemandOut(
                id="d2", kind=DemandKind.action,
                text="Confirm your address online, by phone, or by mailing the enclosed form.",
                value_verbatim="confirm or update your address",
                source_quote=(
                    "You can confirm your address online, by phone using the number on your "
                    "Medicaid card, or by mailing the enclosed form."
                ),
                span_ids=["b7"], page=1, date_text=None, time_text=None, relative_rule_text=None,
                anchor_span_id=None, amount_text=None, currency=None,
                documents=["the enclosed form"], role=None, confidence=Confidence.high,
                ambiguity_note=None,
            ),
        ],  # fmt: skip
        plan_steps=[
            PlanStepOut(
                id="p1",
                text="Check the address printed on the letter. If it is right, confirm it.",
                kind=PlanStepKind.verify, resource_tags=["medicaid_renewal"], span_ids=["b5"],
                demand_id="d2",
            ),
            PlanStepOut(
                id="p2", text="Go online, call, or mail the enclosed form to confirm your address.",
                kind=PlanStepKind.submit_online, resource_tags=["change_of_address"],
                span_ids=["b7"], demand_id="d2",
            ),
            PlanStepOut(
                id="p3", text="If you need help, ask a benefits office or call 211.",
                kind=PlanStepKind.ask, resource_tags=["benefits_navigation"], span_ids=["b8"],
                demand_id=None,
            ),
        ],  # fmt: skip
        glossary=[
            GlossaryTerm(
                term_as_written="Medicaid",
                explanation="Free or low-cost health coverage from the state.",
            ),
            GlossaryTerm(
                term_as_written="renewal packet",
                explanation="The forms the state sends each year to keep your coverage.",
            ),
            GlossaryTerm(
                term_as_written="FAMIS",
                explanation="Virginia's health coverage program for children.",
            ),
        ],
        red_flags=[],
        questions_to_ask=[
            "Is the address you have for me correct?",
            "What happens if I miss the 30 days?",
            "Can I confirm my address by phone?",
        ],
        clerk_need_en=(
            "I received a letter asking me to confirm my address for Medicaid. "
            "I want to confirm or update my address."
        ),
        emergency_terms_found=[],
        is_likely_scam=False,
        scam_signals=[],
        resource_tags=["medicaid_renewal", "change_of_address"],
        institutions_as_written=[
            "Virginia Department of Medical Assistance Services", "Cover Virginia",
        ],  # fmt: skip
        form_numbers=[],
        geo_state="VA",
        geo_county=None,
        geo_city=None,
        geo_zip=None,
        legibility=Legibility.good,
        readable_reason=None,
        blocks=_blocks(),
    )


def render_sample_png(lines: list[str], width: int = 600, height: int = 800) -> bytes:
    """Synthetic page watermarked SAMPLE, built in memory with Pillow."""
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    body = ImageFont.load_default(size=14)
    big = ImageFont.load_default(size=96)
    draw.text((width // 2, height // 2), "SAMPLE", fill=(215, 215, 215), font=big, anchor="mm")
    y = 60
    for line in lines:
        draw.text((48, y), line[:70], fill="black", font=body)
        if len(line) > 70:
            y += 18
            draw.text((48, y), line[70:140], fill="black", font=body)
        y += 40
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


@dataclass
class Fixture:
    manifest: DemoFixture
    transcript: str
    outs: dict[str, AnalysisModelOut | TroubleshootModelOut]
    dhash: int = 0
    _png: bytes | None = field(default=None, repr=False)

    def page_png(self, n: int) -> bytes:
        if n != 1:
            raise KeyError(n)
        if self._png is None:
            self._png = render_sample_png(self.transcript.splitlines())
        return self._png

    def out(self, lang: str) -> AnalysisModelOut | TroubleshootModelOut | None:
        return self.outs.get(lang)


def _inline_fixture() -> Fixture:
    manifest = DemoFixture(
        id=INLINE_FIXTURE_ID,
        title_key="fixture.medicaid_address_confirmation",
        title_en="Medicaid letter asking to confirm your address",
        document_type=DocumentType.medicaid_renewal,
        category=DocumentCategory.benefits,
        language_of_document="en",
        pages=1,
        available_target_languages=["en"],
        thumbnail_url=f"/v1/demo/fixtures/{INLINE_FIXTURE_ID}/pages/1",
        kind="document",
    )
    return Fixture(
        manifest=manifest,
        transcript=_transcript(),
        outs={"en": medicaid_address_confirmation_out()},
    )


class FixtureStore:
    def __init__(self, fixtures: list[Fixture]) -> None:
        self._by_id = {f.manifest.id: f for f in fixtures}

    @classmethod
    def load(cls, dir: Path) -> "FixtureStore":  # noqa: A002 - name fixed by BUILD_PLAN §4.1
        """WP7 reads ``dir/*/manifest.yaml``; WP0 serves the inline fixture only."""
        return cls([_inline_fixture()])

    def list(self) -> list[DemoFixture]:
        return [f.manifest for f in self._by_id.values()]

    def get(self, id: str) -> Fixture | None:  # noqa: A002 - name fixed by BUILD_PLAN §4.1
        return self._by_id.get(id)

    def default(self) -> Fixture:
        return self._by_id[INLINE_FIXTURE_ID]

    def match_dhash(self, png_or_jpeg: bytes, max_hamming: int) -> Fixture | None:
        return None
