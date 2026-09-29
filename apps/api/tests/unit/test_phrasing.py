"""WP2 — ``analysis/phrasing.py`` + ``data/safety/phrasing.yaml`` (D-17; TAXONOMY §8)."""

from __future__ import annotations

import pytest

from proxyhealth_api.analysis import phrasing as ph
from proxyhealth_api.contracts.enums import DocumentCategory, ReferTo, RefusalKind, WarningCode
from tests.unit._fixtures_wp2 import en_t

C = DocumentCategory

FORBIDDEN = [
    ("The notice itself does not require you to leave; a court hearing would have to happen "
     "first in Virginia.", C.housing),
    ("You qualify for financial assistance because your income is under 400% FPL.", C.medical),
    ("Your potassium is high, which can be dangerous.", C.medical),
    ("You should appeal within 180 days.", C.medical),
    ("You are not eligible for Medicaid.", C.benefits),
    ("You will be approved.", C.immigration),
    ("You don't have to pay this bill.", C.medical),
    ("This means you owe $200.", C.tax),
    ("Your results are normal.", C.medical),
    ("You have diabetes.", C.medical),
    ("You must sign the lease.", C.housing),
    ("Don't worry about this letter.", C.other),
    ("You can work while your case is pending.", C.immigration),
    ("The landlord cannot evict you.", C.housing),
    ("This is wage theft.", C.employment),
    ("Your child needs special education.", C.school),
    ("Your benefits will stop.", C.benefits),
    ("You may be deported if you miss this.", C.court),
]  # fmt: skip

ALLOWED = [
    ("In Virginia, a landlord generally needs a court order before an eviction can happen. "
     "Confirm with the legal helpline today.", C.housing),
    ("The paper says financial assistance is for households under 400% of the poverty level. "
     "The hospital's financial assistance office can tell you if that includes you.", C.medical),
    ("The paper lists potassium as H (high) next to the normal range. Ask your doctor or nurse "
     "what this means for you.", C.medical),
    ("The paper says an internal appeal can be asked for within 180 days of the notice. A "
     "benefits counselor or your plan can advise you.", C.medical),
    ("Talk to a licensed lawyer or a DOJ-accredited representative before October 14, 2026.",
     C.immigration),
    ("Ask your doctor, nurse or pharmacist what this means for you.", C.medical),
    ("A housing lawyer or counselor can advise you.", C.housing),
    ("The office that sent this paper can tell you what happens next.", C.benefits),
    ("The letter says you must pay $45.10 by October 14, 2026.", C.medical),
    ("It says you should bring your passport.", C.immigration),
    ("Your balance is high.", C.medical),
    ("Bring this letter to your appointment.", C.medical),
    ("The paper says X. A licensed lawyer or a DOJ-accredited representative can tell you what "
     "it means for you.", C.immigration),
]  # fmt: skip


@pytest.mark.parametrize(("sentence", "category"), FORBIDDEN)
def test_forbidden_phrasings_are_caught(sentence: str, category: DocumentCategory) -> None:
    assert ph.lint_text(sentence, category=category), sentence


@pytest.mark.parametrize(("sentence", "category"), ALLOWED)
def test_allowed_phrasings_pass(sentence: str, category: DocumentCategory) -> None:
    assert ph.lint_text(sentence, category=category) == [], sentence


def test_attribution_skips_advice_but_not_eligibility() -> None:
    assert ph.is_attributed("The notice says you must reply.")
    assert ph.lint_text("The notice says you must pay the fee.", category=C.housing) == []
    assert ph.lint_text("The paper says you qualify.", category=C.benefits)


def test_domains_limit_families() -> None:
    assert ph.lint_text("You have a strong case.", category=C.court)  # outcome: all domains
    assert ph.lint_text("You can stay in the country.", category=C.medical) == []
    assert ph.lint_text("You can stay in the country.", category=C.immigration)
    # medical rules also fire outside medical papers when a medicine or test is named
    assert ph.lint_text("Your test results are normal.", category=C.school)


def test_contact_like_only_reports_contacts_a_rewrite_adds() -> None:
    # a sentence is never failed for a contact the scrubber already vetted
    assert ph.lint_sentence("Call 703-555-0199 to appeal.") == []
    fams = ph.lint_sentence("Call 703-555-0199 to appeal.", original="Call the office to appeal.")
    assert "contact_like" in fams
    kept = ph.lint_sentence("The paper says to call 703-555-0199.", original="Call 703-555-0199.")
    assert kept == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sentence",
    [
        "Call Cover Virginia at 1-855-242-8282 to renew.",
        "You can return the form online at coverva.org.",
        "Mail it to 600 East Broad Street, Richmond.",
        "Phone for questions about this bill, from your paper: (703) 555-0142.",
    ],
)
async def test_contacts_printed_on_the_paper_are_not_hedged(sentence: str) -> None:
    out = await ph.enforce(sentence, t=en_t(), category=C.benefits)
    assert out.text == sentence and out.replacements == 0


@pytest.mark.asyncio
async def test_rewrite_that_adds_a_contact_is_rejected() -> None:
    async def adds_phone(sentence: str, professional: str) -> str | None:
        return "The paper lists the help you can ask about at 703-555-0199."

    async def keeps_phone(sentence: str, professional: str) -> str | None:
        return "The paper says to call 1-855-242-8282 about this."

    out = await ph.enforce("You qualify for help.", t=en_t(), category=C.benefits,
                           rewrite=adds_phone)  # fmt: skip
    assert ph.lint_sentence("The paper lists the help you can ask about at 703-555-0199.") == []
    assert out.hedged == 1 and "703-555-0199" not in out.text
    keep = await ph.enforce(
        "You should apply by phone at 1-855-242-8282.", t=en_t(), category=C.benefits,
        rewrite=keeps_phone,
    )  # fmt: skip
    assert keep.rewritten == 1 and "1-855-242-8282" in keep.text


@pytest.mark.asyncio
async def test_rewrite_once_then_hedge() -> None:
    calls: list[tuple[str, str]] = []

    async def mock_rewrite(sentence: str, professional: str) -> str | None:
        calls.append((sentence, professional))
        return "The paper says " + sentence[0].lower() + sentence[1:]

    out = await ph.enforce(
        "You should appeal within 180 days. You qualify for help. Bring the letter.",
        t=en_t(), category=C.medical, rewrite=mock_rewrite,
    )  # fmt: skip
    assert calls[0][1] == "your doctor, nurse or pharmacist" and len(calls) == 2
    assert out.text == (
        "The paper says you should appeal within 180 days. "
        "I cannot say whether you qualify. The paper says what it says; a professional can tell "
        "you what it means for you. Bring the letter."
    )
    assert out.replacements == 2 and out.rewritten == 1 and out.hedged == 1
    assert out.families == ["advice_verb", "eligibility"] and out.warnings == []


@pytest.mark.asyncio
async def test_rewrite_with_a_contact_is_rejected() -> None:
    async def bad(sentence: str, professional: str) -> str | None:
        return "The paper says call 703-555-0199."

    out = await ph.enforce("You must pay the fee.", t=en_t(), category=C.housing, rewrite=bad)
    assert out.text == en_t()("chat.refusal.filing_advice") and out.hedged == 1


@pytest.mark.asyncio
async def test_no_rewriter_uses_the_hedge_directly() -> None:
    out = await ph.enforce("Your results are normal.", t=en_t(), category=C.medical)
    assert out.text == en_t()("chat.refusal.medical_interpretation")
    assert out.replacements == 1


@pytest.mark.asyncio
async def test_dramatize_clause_is_deleted() -> None:
    out = await ph.enforce("Read this now! It is a catastrophe, but help exists.", t=en_t())
    assert out.text == "Read this now. But help exists."
    only = await ph.enforce("URGENT!", t=en_t())
    assert only.text == "" and only.replacements == 1


@pytest.mark.asyncio
async def test_languages_and_unavailable_warning() -> None:
    es = await ph.enforce(
        "Usted califica para ayuda.", t=en_t(), category=C.benefits, language="es"
    )
    assert es.replacements == 1 and es.warnings == []
    so = await ph.enforce("You qualify.", t=en_t(), category=C.benefits, language="so")
    assert so.warnings == [WarningCode.phrasing_lint_unavailable] and so.replacements == 1
    assert ph.lint_languages("es-MX") == (["en", "es"], False)
    assert ph.lint_languages("en") == (["en"], False)


def test_professional_and_referral_words() -> None:
    lawyer = "a licensed lawyer or a DOJ-accredited representative"
    assert ph.professional_for(C.immigration) == lawyer
    assert ph.professional_for(C.tax) == "the IRS or a free tax helper"
    assert ph.professional_for(None) == "a professional"
    assert ph.refer_to_for(C.housing) is ReferTo.housing_counselor
    assert ph.refer_to_for(C.school) is ReferTo.sender
    assert ph.refusal_kind_for(["eligibility"]) is RefusalKind.eligibility
    assert ph.refusal_kind_for(["dramatize"]) is RefusalKind.none


def test_professional_steps_name_someone() -> None:
    t = en_t()
    named = "Talk to a lawyer before the hearing."
    assert ph.ensure_professional(named, C.court, t) == named
    bare = ph.ensure_professional("Get help with this paper", C.medical, t)
    assert bare == "Get help with this paper. " + t("chat.refer.clinician")


def test_sentence_splitting() -> None:
    assert ph.split_sentences("One. Two! Three? 四。五") == ["One.", "Two!", "Three?", "四。五"]
    assert ph.split_sentences("  ") == []


@pytest.mark.parametrize(
    ("sentence", "category"),
    [
        ("You have an appointment on October 3, 2026.", C.medical),
        ("Call the pharmacy if you have questions.", C.medical),
        ("You have 30 days to pay this bill.", C.medical),
        ("Bring your test results if you have them.", C.benefits),
        (
            "Ask the pharmacist or the prescriber if you have questions about more medicine.",
            C.medical,
        ),
        ("The paper says you have an appointment on October 3.", C.medical),
        ("Bring all the papers you have.", C.medical),
        ("You may have to pay a fee.", C.medical),
    ],
)
def test_medical_interpret_ignores_ordinary_you_have(sentence: str, category: C) -> None:
    assert "medical_interpret" not in ph.lint_sentence(sentence, category=category)


@pytest.mark.parametrize(
    "sentence",
    [
        "You have diabetes.",
        "You might have an infection.",
        "You have high blood pressure.",
        "You are pregnant.",
        "You are suffering from anemia.",
    ],
)
def test_medical_interpret_still_catches_diagnoses(sentence: str) -> None:
    assert "medical_interpret" in ph.lint_sentence(sentence, category=C.medical)
