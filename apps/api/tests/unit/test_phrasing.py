"""WP2 — ``analysis/phrasing.py`` + ``data/safety/phrasing.yaml`` (D-17; TAXONOMY §8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from proxyhealth_api.analysis import phrasing as ph
from proxyhealth_api.analysis.i18n import MappingTranslator
from proxyhealth_api.contracts.enums import (
    DocumentCategory,
    DocumentType,
    PlanStepKind,
    ReferTo,
    RefusalKind,
    ScamRisk,
    WarningCode,
)
from proxyhealth_api.demo.fixtures import FixtureStore
from proxyhealth_api.settings import DATA_DIR
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
    """TAXONOMY §8.1/§8.6: the target language is linted only when its section is reviewed;
    an unlisted or unreviewed language lints English only and warns."""
    es = await ph.enforce(
        "Usted califica para ayuda.", t=en_t(), category=C.benefits, language="es"
    )
    assert es.replacements == 0 and es.warnings == [WarningCode.phrasing_lint_unavailable]
    so = await ph.enforce("You qualify.", t=en_t(), category=C.benefits, language="so")
    assert so.warnings == [WarningCode.phrasing_lint_unavailable] and so.replacements == 1
    assert ph.load_config().reviewed_by["es"] is None
    assert ph.lint_languages("es-MX") == (["en"], True)
    assert ph.lint_languages("en") == (["en"], False)
    reviewed = _reviewed_config("es")
    assert ph.lint_languages("es-MX", reviewed) == (["en", "es"], False)
    es_reviewed = await ph.enforce(
        "Usted califica para ayuda.", t=en_t(), category=C.benefits, language="es", cfg=reviewed
    )
    assert es_reviewed.replacements == 1 and es_reviewed.warnings == []


def _reviewed_config(*tags: str) -> ph.PhrasingConfig:
    data = yaml.safe_load(ph.PHRASING_YAML.read_text(encoding="utf-8"))
    for tag in tags:
        data["languages"][tag]["reviewed_by"] = "test reviewer"
    return ph.parse_config(data)


def test_spanish_attribution_exempts_reported_sentences() -> None:
    """§8.3 in Spanish: "Su arrendador, …, dice que usted debe pagar" reports the paper."""
    cfg = _reviewed_config("es")
    reported = (
        "Su arrendador, Oak Hollow Property Management LLC, dice que usted debe $1,450.00 de "
        "renta y que debe pagar antes del 8 de octubre de 2026 o mudarse."
    )
    assert ph.is_attributed(reported, cfg, ["en", "es"])
    assert not ph.is_attributed(reported, cfg)  # the English regex alone does not cover it
    assert ph.lint_text(reported, category=C.housing, language="es", cfg=cfg) == []
    assert ph.lint_text("La carta dice que debe firmar.", language="es", cfg=cfg) == []
    assert ph.lint_text("Usted debe pagar la renta.", language="es", cfg=cfg) == [
        ("Usted debe pagar la renta.", ["advice_verb"])
    ]


def _fixture_fields(out: dict[str, Any], lang: str) -> list[tuple[str, str]]:
    """(language, text) for every model-authored field TAXONOMY §8.1 lints."""
    fields = [(lang, out.get("summary_title")), (lang, out.get("summary_body"))]
    fields += [("en", out.get("summary_body_en")), ("en", out.get("clerk_need_en"))]
    for d in out.get("demands") or []:
        fields += [(lang, d.get("text")), (lang, d.get("ambiguity_note"))]
    fields += [(lang, s.get("text")) for s in out.get("plan_steps") or []]
    fields += [(lang, g.get("explanation")) for g in out.get("glossary") or []]
    fields += [(lang, r.get("text")) for r in out.get("red_flags") or []]
    fields += [(lang, q) for q in out.get("questions_to_ask") or []]
    return [(tag, text) for tag, text in fields if isinstance(text, str) and text]


FIXTURE_OUTPUTS = sorted((DATA_DIR / "fixtures").glob("*/out.*.json"))


@pytest.mark.parametrize("path", FIXTURE_OUTPUTS, ids=lambda p: f"{p.parent.name}-{p.name}")
def test_every_fixture_output_lints_clean(path: Path) -> None:
    """Every recorded golden's model-authored fields pass the lint — as shipped (unreviewed
    target languages lint English only) and with every language section switched on."""
    lang = path.name.split(".")[1]
    out = json.loads(path.read_text(encoding="utf-8"))
    category = C(out["category"]) if out.get("category") else None
    all_reviewed = _reviewed_config(*ph.load_config().languages)
    for tag, text in _fixture_fields(out, lang):
        for cfg in (ph.load_config(), all_reviewed):
            assert ph.lint_text(text, category=category, language=tag, cfg=cfg) == [], (tag, text)


def test_fixture_outputs_exist() -> None:
    assert len(FIXTURE_OUTPUTS) >= 18


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


# --- Phase 2B: regex defects (negated duty, contractions, adverbs, two-word analytes) ------------


@pytest.mark.parametrize(
    ("sentence", "category", "family"),
    [
        ("You don't need to go to court.", C.court, "negated_duty"),
        ("You do not need to go to the hearing.", C.immigration, "negated_duty"),
        ("You do not need to attend.", C.immigration, "negated_duty"),
        ("You need not appear.", C.court, "negated_duty"),
        ("There is no need to answer this letter.", C.court, "negated_duty"),
        ("You're eligible for financial assistance.", C.medical, "eligibility"),
        ("You’re eligible for financial assistance.", C.medical, "eligibility"),
        ("You're not eligible.", C.benefits, "eligibility"),
        ("You probably qualify for charity care.", C.medical, "eligibility"),
        ("You will probably be approved.", C.immigration, "outcome"),
        ("Your blood sugar is too high.", C.medical, "medical_interpret"),
        ("Your cholesterol is 260, which is high.", C.medical, "medical_interpret"),
        ("Your A1C of 9.1 is above normal.", C.medical, "medical_interpret"),
        ("A glucose of 250 means diabetes.", C.medical, "medical_interpret"),
        ("You can stop taking this medicine when you feel better.", C.medical, "medical_interpret"),
    ],
)
def test_phase_2b_phrasings_are_caught(
    sentence: str, category: DocumentCategory, family: str
) -> None:
    assert family in ph.lint_sentence(sentence, category=category), sentence


@pytest.mark.parametrize(
    ("sentence", "category"),
    [
        ("Your balance is $250.", C.medical),
        ("Your total bill is high.", C.medical),
        ("Your amount due of 250.00 is shown at the top.", C.medical),
        ("Your appointment is on Monday.", C.medical),
        ("The letter says you do not need to bring anything else.", C.benefits),
        ("Bring this letter to your hearing.", C.court),
    ],
)
def test_phase_2b_neighbours_still_pass(sentence: str, category: DocumentCategory) -> None:
    assert ph.lint_sentence(sentence, category=category) == [], sentence


async def test_chat_minimisation_about_a_hearing_is_hedged() -> None:
    res = await ph.enforce(
        "You don't need to go to the hearing if your lawyer goes for you.", t=en_t(),
        category=C.court, language="en",
    )  # fmt: skip
    assert "don't need to go" not in res.text and res.hedged == 1


# --- Phase 2B: DOJ-accredited representatives are for immigration papers only -------------------


def test_professional_words_follow_the_paper_not_just_the_category() -> None:
    dt = DocumentType
    assert "DOJ-accredited" in ph.professional_for(C.court, document_type=dt.nta)
    assert "DOJ-accredited" in ph.professional_for(C.immigration)
    for category, doc in ((C.court, dt.traffic_court), (C.civic, dt.jury_summons),
                          (C.employment, dt.pay_stub), (C.employment, dt.w2_1099)):  # fmt: skip
        assert "DOJ" not in ph.professional_for(category, document_type=doc), doc


def test_a_step_naming_a_tax_professional_gets_no_lawyer_referral() -> None:
    step = "A free tax-help site or a tax professional can explain the boxes with you."
    assert ph.names_professional(step)
    assert ph.ensure_professional(step, C.employment, en_t()) == step


# --- Local-model sweep (qwen3.5:4b, 2026-10): plan-step fit, referrals, skip_duty ---------------

DOJ_STEP = (
    "Before October 28, 2026, talk to a licensed lawyer or a DOJ-accredited representative "
    "about the bill."
)


def _es_t() -> MappingTranslator:
    pack = json.loads((DATA_DIR / "langpacks" / "es.json").read_text(encoding="utf-8"))
    return MappingTranslator(pack["strings"])


@pytest.mark.parametrize(
    ("category", "doc", "refer"),
    [
        (C.medical, DocumentType.medical_bill, "clinician"),
        (C.housing, DocumentType.pay_or_quit, "housing_counselor"),
        (C.benefits, DocumentType.medicaid_renewal, "benefits_office"),
        (C.tax, DocumentType.irs_notice, "sender"),
        (C.school, DocumentType.immunization_notice, "sender"),
        (C.employment, DocumentType.w2_1099, "lawyer_or_accredited_rep"),
    ],
)
def test_a_doj_step_on_a_paper_without_one_becomes_the_category_referral(
    category: DocumentCategory, doc: DocumentType, refer: str
) -> None:
    """§8.4: "a DOJ-accredited representative" only where analyze.md Step 4 asks for one."""
    t = en_t()
    text, replaced = ph.fit_professional_step(
        DOJ_STEP, category=category, document_type=doc, demand_id=None, t=t
    )
    assert (text, replaced) == (t(f"chat.refer.{refer}"), True)
    assert "October 28" not in text  # fixed copy only: the model's sentence is gone


@pytest.mark.parametrize(
    ("category", "doc"),
    [
        (C.court, DocumentType.nta),
        (C.civic, DocumentType.jury_summons),
        (C.immigration, DocumentType.uscis_rfe),
        (C.immigration, DocumentType.other_notice),  # the scam letter "from immigration"
        (C.court, DocumentType.traffic_court),  # analyze.md Step 4 lists court papers
    ],
)
def test_a_doj_step_on_an_immigration_court_or_civic_paper_is_kept(
    category: DocumentCategory, doc: DocumentType
) -> None:
    step = "Talk to a licensed lawyer or a DOJ-accredited representative before the hearing."
    out = ph.fit_professional_step(
        step, category=category, document_type=doc, demand_id="d1", t=en_t()
    )
    assert out == (step, False)
    assert ph.accredited_rep_fits(category, doc)


def test_spanish_accredited_rep_step_gets_the_spanish_referral() -> None:
    es = _es_t()
    step = "Hable con un abogado o un representante acreditado por el DOJ sobre su renovación."
    text, replaced = ph.fit_professional_step(
        step, category=C.benefits, document_type=DocumentType.medicaid_renewal, demand_id=None,
        t=es, language="es",
    )  # fmt: skip
    assert replaced and text == es("chat.refer.benefits_office")
    assert ph.names_accredited_rep("Pida ayuda a un representante acreditado.", language="es")
    assert not ph.names_accredited_rep("Pida ayuda a un representante del hospital.", language="es")


def test_the_copied_before_that_date_opener_is_removed_only_without_a_demand() -> None:
    step = "Before that date, talk to a licensed lawyer or a DOJ-accredited representative."
    kw: dict[str, Any] = {
        "category": C.civic, "document_type": DocumentType.jury_summons, "t": en_t(),
    }  # fmt: skip
    assert ph.fit_professional_step(step, demand_id=None, **kw) == (
        "Talk to a licensed lawyer or a DOJ-accredited representative.", False
    )
    assert ph.fit_professional_step(step, demand_id="d1", **kw) == (step, False)
    spanish = "Antes de esa fecha, hable con un abogado con licencia."
    assert ph.fit_professional_step(spanish, demand_id=None, **kw)[0] == (
        "Hable con un abogado con licencia."
    )
    # no date is ever put in its place, and a bare opener is left alone
    bare = "Before that date,"
    assert ph.fit_professional_step(bare, demand_id=None, **kw)[0] == bare


def _fixture_steps() -> list[tuple[str, str, dict[str, Any], dict[str, Any]]]:
    rows: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []
    for path in FIXTURE_OUTPUTS:
        out = json.loads(path.read_text(encoding="utf-8"))
        if not out.get("category"):
            continue
        lang = path.name.split(".")[1]
        for s in out.get("plan_steps") or []:
            rows.append((f"{path.parent.name}-{lang}-{s['id']}", lang, s, out))
    return rows


FIXTURE_STEPS = _fixture_steps()


@pytest.mark.parametrize(
    ("lang", "step", "out"), [r[1:] for r in FIXTURE_STEPS], ids=[r[0] for r in FIXTURE_STEPS]
)
def test_every_fixture_plan_step_fits_unchanged(
    lang: str, step: dict[str, Any], out: dict[str, Any]
) -> None:
    """The curated steps (every language) keep their wording, and each professional step
    already names someone in its own language, so no second referral is appended (§8.4)."""
    category, doc = C(out["category"]), DocumentType(out["document_type"])
    t = _es_t() if lang == "es" else en_t()
    fitted = ph.fit_professional_step(
        step["text"], category=category, document_type=doc, demand_id=step.get("demand_id"),
        t=t, language=lang,
    )  # fmt: skip
    assert fitted == (step["text"], False)
    if step["kind"] == "professional":
        assert ph.names_professional(step["text"], language=lang), step["text"]
        assert ph.ensure_professional(step["text"], category, t, language=lang) == step["text"]


def test_fixture_steps_cover_every_demo_language() -> None:
    langs = {r[1] for r in FIXTURE_STEPS if r[2]["kind"] == "professional"}
    assert {"en", "es", "ar", "prs"} <= langs


def test_a_step_naming_nobody_still_gets_the_referral_in_any_language() -> None:
    es = _es_t()
    bare = "Obtenga ayuda con este papel."
    assert not ph.names_professional(bare, language="es")
    added = ph.ensure_professional(bare, C.benefits, es, language="es")
    assert added == f"{bare} {es('chat.refer.benefits_office')}"
    # an Arabic word joined to its preposition still names a lawyer ("لمحامٍ")
    assert ph.names_professional("يمكن لمحامٍ أن يساعدك.", language="ar")
    assert not ph.names_professional("يمكن لمحامٍ أن يساعدك.")  # the English list only
    # English behaviour is unchanged
    assert ph.names_professional("Ask a counselor.") and not ph.names_professional("Get help.")


def test_a_step_that_already_is_the_referral_gets_no_second_one() -> None:
    t = en_t()
    referral = t("chat.refer.sender")
    assert ph.ensure_professional(referral, C.tax, t) == referral


def test_language_sections_without_families_never_lint() -> None:
    """ar/prs/ps carry professional words only: they stay "unavailable" even when reviewed."""
    assert ph.lint_languages("ar") == (["en"], True)
    assert ph.lint_languages("prs", _reviewed_config("prs")) == (["en"], True)
    assert ph.load_config().languages["prs"] == ()


@pytest.mark.asyncio
async def test_a_repeated_referral_sentence_is_added_once() -> None:
    """The rewrite template's referral is not repeated within one field (irs_cp_notice)."""

    async def template(sentence: str, professional: str) -> str | None:
        who = professional[0].upper() + professional[1:]
        said = sentence[0].lower() + sentence[1:]
        return f"The paper says {said} {who} can tell you what it means for you."

    out = await ph.enforce(
        "You owe $312.45. You must pay by October 26, 2026.", t=en_t(), category=C.tax,
        rewrite=template,
    )  # fmt: skip
    referral = "The IRS or a free tax helper can tell you what it means for you."
    assert out.text.count(referral) == 1 and out.rewritten == 2
    assert out.text == (
        f"The paper says you owe $312.45. {referral} The paper says you must pay by October 26, "
        "2026."
    )
    hedged = await ph.enforce(
        "You must pay the fee. You must sign the form.", t=en_t(), category=C.housing
    )
    assert hedged.text == en_t()("chat.refusal.filing_advice") and hedged.replacements == 2


@pytest.mark.parametrize(
    "sentence",
    [
        "If the paper says it is a sample, do not pay or go to court.",
        "Don't go to the hearing.",
        "Never appear at your SNAP interview.",
        "Do not come to the appointment.",
        "Skip the interview.",
        "The paper says do not attend the hearing.",  # attribution does not exempt it
    ],
)
def test_skip_duty_catches_telling_the_reader_to_skip(sentence: str) -> None:
    assert "skip_duty" in ph.lint_sentence(sentence, category=C.other), sentence
    assert ph.hedge_key(["skip_duty"]) == "chat.refusal.filing_advice"


@pytest.mark.parametrize(
    "sentence",
    [
        "Do not pay and do not call the number on this letter.",  # the scam fixture's step
        "Your permission to drive may be stopped if you do not show up for court.",
        "If you cannot make the hearing, ask the court about rescheduling it.",
        "Do not miss your hearing.",
        "Go to the hearing on October 7, 2026 at 8:30 AM.",
    ],
)
def test_skip_duty_leaves_consequences_and_scam_warnings_alone(sentence: str) -> None:
    assert "skip_duty" not in ph.lint_sentence(sentence, category=C.court), sentence


def test_optional_prose_is_dropped_on_a_hit_never_rewritten() -> None:
    """§11.9: a definition or a non-professional step that fails the lint loses the failing
    sentence (all of it when nothing else is left); only a dramatizing clause is deleted in place
    (the rest of the step is still useful)."""
    removal = "a decision by the judge that you must leave the country."
    assert ph.optional_prose(removal, category=C.court) is None
    waiver = "Find out if you can get a fee waiver so you do not have to pay for the hearing."
    assert ph.optional_prose(waiver, category=C.court) is None
    assert ph.optional_prose("Balance due. You owe $312.45.", category=C.tax) == "Balance due."
    clean = "Extra charges added when taxes are not paid on time."
    assert ph.optional_prose(clean, category=C.tax) == clean
    assert ph.optional_prose("Bring your ID! Arrive early.", category=C.court) == (
        "Bring your ID. Arrive early."
    )
    assert ph.optional_prose("URGENT!", category=C.court) is None


def test_optional_prose_keeps_the_clean_sentences_of_a_step() -> None:
    """Only the failing sentence goes: the step that tells the reader to go to the hearing stays."""
    hearing = "Go to your hearing on November 16, 2026."
    assert ph.optional_prose(f"{hearing} You must pay the fee first.", category=C.immigration) == (
        hearing
    )
    for step in (
        f"{hearing} Do not go to court without this notice and your ID.",
        "Bring this notice. Do not come to the interview without your passport.",
    ):
        assert ph.optional_prose(step, category=C.immigration) == step
    assert ph.optional_prose(
        "You must pay the fee. You must sign the form.", category=C.housing
    ) is None


def test_title_connectors_are_english_plus_the_title_language() -> None:
    assert {"and", "asking", "you", "on"} <= ph.title_connectors("en")
    assert "true" not in ph.title_connectors("en")
    es = ph.title_connectors("es-MX")
    assert {"and", "y", "de"} <= es and "و" not in es
    assert "از" in ph.title_connectors("prs")


def test_every_yaml_word_list_entry_is_a_string() -> None:
    """A bare ``on`` is YAML for ``true``: word lists must be quoted, and parsing says so."""
    data = yaml.safe_load(ph.PHRASING_YAML.read_text(encoding="utf-8"))
    for tag, section in data["languages"].items():
        for key in ("professional_words", "title_connectors"):
            assert all(isinstance(w, str) for w in section.get(key) or []), (tag, key)
    assert all(isinstance(w, str) for w in data["professional_words"])
    data["languages"]["en"]["title_connectors"].append(True)
    with pytest.raises(ValueError, match="en.title_connectors"):
        ph.parse_config(data)


# --- Scam papers: no referral back to the paper's own contact (TAXONOMY §6.4) ------------------

SENDER_REFERRALS = ("chat.refer.sender", "chat.refer.benefits_office")


@pytest.mark.parametrize("risk", [ScamRisk.possible, ScamRisk.likely])
@pytest.mark.parametrize("category", list(C))
def test_no_category_refers_a_scam_reader_to_the_sender(
    category: DocumentCategory, risk: ScamRisk
) -> None:
    assert ph.refer_to_for(category, scam_risk=risk) not in (
        ReferTo.sender, ReferTo.benefits_office
    )
    assert "sent this paper" not in ph.professional_for(category, scam_risk=risk)


def test_without_a_scam_score_the_referrals_are_unchanged() -> None:
    assert ph.refer_to_for(C.tax) is ReferTo.sender
    assert ph.refer_to_for(C.benefits, scam_risk=ScamRisk.none) is ReferTo.benefits_office
    assert ph.professional_for(C.benefits) == "the office that sent this paper"
    assert ph.refer_to_for(C.medical, scam_risk=ScamRisk.likely) is ReferTo.clinician


@pytest.mark.parametrize("risk", [ScamRisk.possible, ScamRisk.likely])
@pytest.mark.parametrize("category", [C.tax, C.other, C.school, C.benefits])
def test_a_doj_step_on_a_scam_paper_never_points_to_the_sender(
    category: DocumentCategory, risk: ScamRisk
) -> None:
    """irs_cp_notice replay (scam likely, tax): the swap gave "Ask the sender. Their contact is on
    the paper." — the scammer. The lawyer referral (Get help) takes its place."""
    t = en_t()
    step = "Talk to a licensed lawyer or a DOJ-accredited representative before you pay anyone."
    text, replaced = ph.fit_professional_step(
        step, category=category, document_type=None, demand_id=None, t=t, scam_risk=risk
    )
    assert replaced and text == t("chat.refer.lawyer_or_accredited_rep")
    assert all(t(k) not in text for k in SENDER_REFERRALS)
    bare = ph.ensure_professional("Get help before you do anything.", category, t, scam_risk=risk)
    assert bare.endswith(t("chat.refer.lawyer_or_accredited_rep"))
    assert all(t(k) not in bare for k in SENDER_REFERRALS)


def test_a_step_naming_the_doj_as_an_agency_is_not_a_representative() -> None:
    t = en_t()
    warning = "Do not pay. The DOJ and the IRS never ask for gift cards."
    assert not ph.names_accredited_rep(warning)
    assert ph.fit_professional_step(
        warning, category=C.tax, document_type=None, demand_id=None, t=t,
        scam_risk=ScamRisk.likely,
    ) == (warning, False)  # fmt: skip
    for named in (
        "a DOJ-accredited representative", "a DOJ accredited rep",
        "a representative accredited by the DOJ", "un representante acreditado por el DOJ",
    ):
        assert ph.names_accredited_rep(named, language="es"), named


@pytest.mark.asyncio
async def test_the_rewrite_template_never_names_the_sender_on_a_scam() -> None:
    asked: list[str] = []

    async def rewrite(sentence: str, professional: str) -> str | None:
        asked.append(professional)
        return None

    for risk in (ScamRisk.none, ScamRisk.possible):
        await ph.enforce(
            "You must pay the fee.", t=en_t(), category=C.benefits, rewrite=rewrite,
            scam_risk=risk,
        )  # fmt: skip
    assert asked == ["the office that sent this paper", "a licensed lawyer"]


# --- skip_duty: qualifiers and printed conditions ----------------------------------------------

SKIP_FAMILIES = {"skip_duty", "skip_duty_conditional"}


@pytest.mark.parametrize(
    "sentence",
    [
        "Do not go to court without your ID.",
        "Do not go to the court hearing without this notice.",
        "Do not come to the interview without your passport.",
        "Never go to court late.",
        "The court says do not come to court if you have a fever; call the clerk.",
        "The letter says do not come to the appointment if you are sick.",
    ],
)
def test_skip_duty_spares_qualifiers_and_attributed_conditions(sentence: str) -> None:
    assert not SKIP_FAMILIES & set(ph.lint_sentence(sentence, category=C.civic)), sentence


@pytest.mark.parametrize(
    "sentence",
    [
        "Do not go to the hearing if you are sick.",
        "Don't come to court unless the clerk calls you.",
    ],
)
def test_an_unattributed_condition_to_skip_is_still_caught(sentence: str) -> None:
    assert "skip_duty_conditional" in ph.lint_sentence(sentence, category=C.civic), sentence
    assert ph.hedge_key(["skip_duty_conditional"]) == "chat.refusal.filing_advice"


# --- integration review, issue 16: no plan step sends a scam's reader to the paper's contact -----
# scam_gift_card_letter with small-model steps: "The office that sent this paper can tell you more.
# Call Officer Daniel Sample at (202) 555-0147." (professional) and "Check whether the letter is
# real by calling (202) 555-0147." (verify) both survived on a likely scam.

OFFICE_STEP = "The office that sent this paper can tell you more."
CALL_SCAMMER = f"{OFFICE_STEP} Call Officer Daniel Sample at (202) 555-0147."


@pytest.mark.parametrize("risk", [ScamRisk.possible, ScamRisk.likely])
@pytest.mark.parametrize(
    "text",
    [
        CALL_SCAMMER,
        "Check whether the letter is real by calling (202) 555-0147.",
        "Confirm the payment at www.uscis-payments.com before Friday.",
        "Write to enforcement.office@example.com to ask for more time.",
        "Bring the cash to 1200 Main Street, Suite 4, Fairfax, VA 22030.",
    ],
)
def test_a_scam_step_pointing_at_a_printed_contact_goes(text: str, risk: ScamRisk) -> None:
    t = en_t()
    referral = t("chat.refer.lawyer_or_accredited_rep")
    for kind in PlanStepKind:
        got = ph.scam_safe_step(text, kind, category=C.immigration, t=t, scam_risk=risk)
        assert got == (referral if kind is PlanStepKind.professional else None), (kind, got)
    kept = ph.scam_safe_step(text, PlanStepKind.verify, category=C.immigration, t=t,
                             scam_risk=ScamRisk.none)  # fmt: skip
    assert kept == text, "a real paper keeps its contacts"


@pytest.mark.parametrize(
    "text",
    [
        "Do not pay. Check with the real agency through Get help.",
        "Check your case status at www.uscis.gov/casestatus or e-mail help@uscis.gov.",
        "Keep the letter and the envelope.",
    ],
)
def test_a_scam_step_without_a_paper_contact_stays(text: str) -> None:
    for kind in (PlanStepKind.verify, PlanStepKind.professional, PlanStepKind.gather):
        assert ph.scam_safe_step(text, kind, category=C.immigration, t=en_t(),
                                 scam_risk=ScamRisk.likely) == text  # fmt: skip


@pytest.mark.parametrize("risk", [ScamRisk.possible, ScamRisk.likely])
def test_office_alone_is_no_professional_on_a_scam_paper(risk: ScamRisk) -> None:
    t = en_t()
    assert ph.names_professional(OFFICE_STEP) and not ph.names_professional(OFFICE_STEP,
                                                                            scam_risk=risk)
    referral = t("chat.refer.lawyer_or_accredited_rep")
    assert ph.ensure_professional(OFFICE_STEP, C.immigration, t, scam_risk=risk) == referral
    assert ph.ensure_professional(OFFICE_STEP, C.tax, t, scam_risk=risk) == referral
    assert not ph.names_professional("La oficina que envió esta carta le puede decir más.",
                                     language="es", scam_risk=risk)  # fmt: skip
    named = "A licensed lawyer or the real USCIS office can tell you more."
    assert ph.names_professional(named, scam_risk=risk)
    assert ph.ensure_professional(named, C.immigration, t, scam_risk=risk) == named
    # Without a scam score the office still counts, as before.
    assert ph.ensure_professional(OFFICE_STEP, C.benefits, t) == OFFICE_STEP


# A step may send the reader to the scammer without writing the contact out: "Call the number on
# the letter" goes like "(202) 555-0147" — but the warning itself ("Do not call the number on this
# letter", the fixture's own step) and "Report the website on the letter" stay.

POINTERS = [
    "Call the number on the letter to check if it is real.",
    "Check whether the letter is real by calling the phone number on this paper.",
    "Ask the office that sent this paper whether it is real.",
    "If you are not sure, call the number on the letter.",
    "Do not pay; instead, call the number on the letter.",
    "Do not pay and call the number on the letter.",
    "Call the sender back today.",
    "Llame al número de la carta para confirmar.",
    "Pregunte a la oficina que le envió esta carta.",
]
WARNINGS = [
    "Do not pay and do not call the number on this letter. Check with the real agency through "
    "Get help.",
    "Never call the number on this letter.",
    "Don't use the website on the letter.",
    "Report the website on the letter to the FTC.",
    "Call USCIS using the number on its official website, not the number on the letter.",
    "Ask USCIS whether this is a real letter before you pay.",
    "Write down the case number from the letter.",
    "No pague y no llame al número de esta carta. Consulte con la agencia real por medio de "
    "Obtener ayuda.",
]


@pytest.mark.parametrize("text", POINTERS)
def test_a_scam_step_pointing_at_the_papers_contact_in_words_goes(text: str) -> None:
    assert ph.refers_to_paper_contact(text) and ph.points_at_paper_contact(text)
    t = en_t()
    for risk in (ScamRisk.possible, ScamRisk.likely):
        assert ph.scam_safe_step(text, PlanStepKind.verify, category=C.immigration, t=t,
                                 scam_risk=risk) is None  # fmt: skip
        referral = ph.scam_safe_step(text, PlanStepKind.professional, category=C.tax, t=t,
                                     scam_risk=risk)  # fmt: skip
        assert referral == t("chat.refer.lawyer_or_accredited_rep")
    assert ph.scam_safe_step(text, PlanStepKind.verify, category=C.immigration, t=t,
                             scam_risk=ScamRisk.none) == text  # fmt: skip


@pytest.mark.parametrize("text", WARNINGS)
def test_a_scam_warning_about_the_papers_contact_stays(text: str) -> None:
    assert not ph.refers_to_paper_contact(text), text
    assert ph.scam_safe_step(text, PlanStepKind.verify, category=C.immigration, t=en_t(),
                             scam_risk=ScamRisk.likely) == text  # fmt: skip


def test_the_scam_fixture_steps_survive_the_pointer_check() -> None:
    """scam_gift_card_letter in every language: its steps warn about the number and stay."""
    fx = FixtureStore.load(DATA_DIR / "fixtures").get("scam_gift_card_letter")
    assert fx is not None
    for lang in fx.languages:
        out = fx.analysis_out(lang)
        assert out is not None
        for step in out.plan_steps:
            assert not ph.points_at_paper_contact(step.text), (lang, step.text)
