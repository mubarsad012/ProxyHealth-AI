"""WP2 — ``analysis/clerk.py`` + ``data/rules/clerk_needs.yaml`` (D-18; PRODUCT_SPEC §8)."""

from __future__ import annotations

import pytest

from proxyhealth_api.analysis import clerk as ck
from proxyhealth_api.analysis.contacts_filter import has_contact, make_scrubber
from proxyhealth_api.analysis.phrasing import lint_sentence
from proxyhealth_api.contracts.enums import DocumentType, SenderKind, WarningCode
from proxyhealth_api.resources.rules_repo import RulesRepo, load_clerk_needs
from proxyhealth_api.settings import DATA_DIR
from tests.unit._fixtures_wp2 import en_t

DT = DocumentType
SK = SenderKind
RULES_DIR = DATA_DIR / "rules"


@pytest.fixture(scope="module")
def rules() -> RulesRepo:
    return RulesRepo.load(RULES_DIR)


def test_every_document_type_has_a_clean_need_line(rules: RulesRepo) -> None:
    needs, version = load_clerk_needs(RULES_DIR / "clerk_needs.yaml")
    assert version != "0" and set(needs) == set(DocumentType)
    t = en_t()
    for doc in DocumentType:
        line = ck.template_need_line(rules, doc, t)
        assert line and len(line) <= ck.MAX_NEED_CHARS, doc
        assert not has_contact(line), doc
        assert lint_sentence(line) == [], (doc, line)
    assert ck.template_need_line(rules, DT.unknown, t) == t("clerk.generic_need")
    assert set(ck.PLAIN_DOCUMENT) == set(DocumentType)


@pytest.mark.asyncio
async def test_card_from_the_model_need_line(rules: RulesRepo) -> None:
    out = await ck.build_clerk_message(
        language_name_en="Dari", document_type=DT.medicaid_renewal,
        sender_as_written="Virginia Department of Medical Assistance Services",
        sender_kind=SK.state_agency,
        clerk_need_en="returning the address form before October 14, 2026.",
        template_line=ck.template_need_line(rules, DT.medicaid_renewal, en_t()),
        target_language="en",
    )  # fmt: skip
    msg = out.message
    assert msg.english == (
        "Hello. I speak Dari. I am here about: a Medicaid letter from Virginia Department of "
        "Medical Assistance Services. I need help with: returning the address form before "
        "October 14, 2026. Please speak slowly or write it down. Thank you."
    )
    assert msg.need_line_source == "ai" and msg.translated == msg.english
    assert msg.appended_line_keys == ["clerk.interpreter_hhs"] and out.warnings == []


@pytest.mark.parametrize(
    "need",
    [
        "calling 703-555-0199 about my case",  # contact not on the paper
        "you qualify for this program",  # phrasing lint
        "",
        None,
    ],
)
@pytest.mark.asyncio
async def test_bad_need_lines_fall_back_to_the_template(rules: RulesRepo, need: str | None) -> None:
    template = ck.template_need_line(rules, DT.snap_notice, en_t())
    out = await ck.build_clerk_message(
        language_name_en="Spanish", document_type=DT.snap_notice, sender_as_written=None,
        sender_kind=SK.state_agency, clerk_need_en=need, template_line=template,
        target_language="en", scrubber=make_scrubber("SNAP interview", set(), en_t()),
    )  # fmt: skip
    assert out.message.need_line_source == "template"
    assert f"I need help with: {template.rstrip('.')}." in out.message.english
    assert "I am here about: a SNAP notice." in out.message.english


def test_hedged_and_long_need_lines() -> None:
    assert ck.choose_need_line("fine words", "template", hedged=True) == ("template", "template")
    long = "word " * 60
    line, source = ck.choose_need_line(long, "template")
    assert source == "ai" and len(line) <= 200 and not line.endswith(" ")
    assert ck.cut_at_word("x" * 250) == ""
    assert ck.choose_need_line("x" * 250, "template") == ("template", "template")


@pytest.mark.parametrize(
    ("doc", "sender", "hhs_resource", "expected"),
    [
        (DT.medicaid_renewal, SK.state_agency, False, True),
        (DT.medical_bill, SK.hospital_or_clinic, False, True),
        (DT.prescription_label, SK.pharmacy, False, True),
        (DT.eob, SK.insurer, False, True),
        (DT.snap_notice, SK.state_agency, True, True),
        (DT.snap_notice, SK.state_agency, False, False),
        (DT.pay_or_quit, SK.landlord, True, False),
        (DT.eviction_summons, SK.court, True, False),
        (DT.report_card, SK.school, True, False),
        (DT.nta, SK.court, False, False),
    ],
)
def test_interpreter_line_only_for_hhs_settings(
    doc: DocumentType, sender: SenderKind, hhs_resource: bool, expected: bool
) -> None:
    got = ck.wants_interpreter_line(doc, sender, first_resource_hhs_funded=hhs_resource)
    assert got is expected


@pytest.mark.asyncio
async def test_translation_and_its_fallback() -> None:
    async def mock_translate(english: str) -> str | None:
        return "⟦prs⟧ " + english

    async def failing(english: str) -> str | None:
        raise RuntimeError("quota")

    kwargs = dict(
        language_name_en="Dari", document_type=DT.lease, sender_as_written="Oak Apartments",
        sender_kind=SK.landlord, clerk_need_en="the rent amount", template_line="a lease",
        target_language="prs",
    )  # fmt: skip
    ok = await ck.build_clerk_message(translate=mock_translate, **kwargs)  # type: ignore[arg-type]
    assert ok.message.translated.startswith("⟦prs⟧ Hello. I speak Dari.")
    assert ok.warnings == [] and ok.message.appended_line_keys == []
    bad = await ck.build_clerk_message(translate=failing, **kwargs)  # type: ignore[arg-type]
    assert bad.message.translated == bad.message.english
    assert bad.warnings == [WarningCode.translation_partial]
    none = await ck.build_clerk_message(**kwargs)  # type: ignore[arg-type]
    assert none.warnings == [WarningCode.translation_partial]


@pytest.mark.asyncio
async def test_failed_translation_uses_the_packs_fixed_card() -> None:
    """AI_PROMPTS §5.5.4: the pack's ``clerk.*`` pieces joined with the English need line."""
    from proxyhealth_api.analysis.i18n import MappingTranslator

    async def failing(english: str) -> str | None:
        return None

    dari = MappingTranslator({ck.GENERIC_CARD_KEY: "⟦prs⟧ {language}: {need}."})
    kwargs = dict(
        language_name_en="Dari", document_type=DT.lease, sender_as_written="Oak Apartments",
        sender_kind=SK.landlord, clerk_need_en="the rent amount", template_line="a lease",
        target_language="prs",
    )  # fmt: skip
    for translate in (failing, None):
        out = await ck.build_clerk_message(translate=translate, t=dari, **kwargs)  # type: ignore[arg-type]
        assert out.message.translated == "⟦prs⟧ Dari: the rent amount."
        assert out.message.english.startswith("Hello. I speak Dari. I am here about: a lease")
        assert out.warnings == [WarningCode.translation_partial]
    english = await ck.build_clerk_message(t=dari, **{**kwargs, "target_language": "en"})  # type: ignore[arg-type]
    assert english.message.translated == english.message.english and english.warnings == []


def test_document_phrase_and_generic_card() -> None:
    assert ck.document_phrase(DT.nta, None) == "a Notice to Appear"
    assert ck.document_phrase(DT.lease, "  Oak   Apartments ") == "a lease from Oak Apartments"
    assert ck.generic_card("Somali", "an appointment.") == (
        "Hello. I speak Somali. I need help with: an appointment. Please speak slowly or write "
        "it down. Thank you."
    )


@pytest.mark.asyncio
async def test_invented_sender_never_reaches_either_card(rules: RulesRepo) -> None:
    """D-10: ``sender_as_written`` is model output; an org/phone not on the paper is left out."""
    paper = "Virginia Medicaid. Send a copy of a bill by October 14, 2026."

    async def echo(english: str) -> str | None:
        return english

    out = await ck.build_clerk_message(
        language_name_en="Dari", document_type=DT.medicaid_renewal,
        sender_as_written="Acme Immigration Help Center 703-555-0199",
        sender_kind=SK.state_agency, clerk_need_en=None,
        template_line=ck.template_need_line(rules, DT.medicaid_renewal, en_t()),
        target_language="prs", scrubber=make_scrubber(paper, set(), en_t()), translate=echo,
    )  # fmt: skip
    msg = out.message
    assert "I am here about: a Medicaid letter. I need help with:" in msg.english
    for card in (msg.english, msg.translated):
        assert "Acme" not in card and "703-555-0199" not in card and not has_contact(card)
    assert msg.translated == msg.english


def test_checked_sender_keeps_a_sender_printed_on_the_paper() -> None:
    paper = "Virginia Department of Medical Assistance Services. Call 1-855-242-8282."
    scrubber = make_scrubber(paper, set(), en_t())
    name = "Virginia Department of Medical Assistance Services"
    assert ck.checked_sender(f"  {name} ", scrubber) == name
    assert ck.checked_sender("Acme Legal Services LLC", scrubber) is None
    assert ck.checked_sender(f"{name} 703-555-0199", scrubber) is None
    assert ck.checked_sender("Oak Apartments", None) == "Oak Apartments"
    assert ck.checked_sender("   ", scrubber) is None


def test_clerk_checks_do_not_count_text_they_drop() -> None:
    """Sender / need-line checks only decide what the card shows; text they drop is not shown,
    so it must not inflate ``verification.contacts_stripped``."""
    scrubber = make_scrubber("Fairfax County Department of Family Services", set(), en_t())
    assert ck.checked_sender("Acme Legal Services LLC", scrubber) is None
    need = "Call 703-555-0199 about my letter"
    assert ck.choose_need_line(need, "template", scrubber=scrubber) == ("template", "template")
    assert scrubber.total == 0 and scrubber.warnings() == []
