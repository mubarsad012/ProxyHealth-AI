"""WP2 — ``analysis/contacts_filter.py`` (D-10; AI_PROMPTS §11.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from proxyhealth_api.analysis import contacts_filter as cf
from proxyhealth_api.analysis.i18n import MappingTranslator
from proxyhealth_api.contracts.enums import WarningCode
from tests.unit._fixtures_wp2 import en_t

PAPER = (
    "Fairfax County Department of Family Services\n"
    "Questions? Call (703) 555-0142 or visit www.fairfaxcounty.gov/familyservices.\n"
    "Email benefits@fairfaxcounty.gov. Office: 12011 Government Center Pkwy, Suite 232.\n"
    "Immigration Court, Arlington, VA. 1901 S. Bell Street, Suite 200.\n"
    "Dial 211 for local help."
)
DB_NAMES = {"Legal Aid Justice Center", "CASA", "ImmigrationLawHelp.org"}
MARK = "[contact removed — see Get help nearby]"
ORG = "a group or office (see Get help nearby)"


@pytest.fixture()
def scrubber() -> cf.ContactScrubber:
    return cf.make_scrubber(PAPER, DB_NAMES, en_t())


def test_markers_come_from_the_pack(scrubber: cf.ContactScrubber) -> None:
    assert scrubber.marker == MARK
    assert scrubber.org_marker == ORG
    spanish = MappingTranslator(
        {cf.MARKER_KEY: "[contacto eliminado]", cf.ORG_MARKER_KEY: "una org"}
    )
    assert cf.make_scrubber(PAPER, DB_NAMES, spanish).marker == "[contacto eliminado]"


@pytest.mark.parametrize(
    "text",
    [
        "Call 703-555-0142 to ask.",
        "Call 1 (703) 555 0142 to ask.",
        "Call +1.703.555.0142 to ask.",
        "See fairfaxcounty.gov/familyservices for the form.",
        "Visit https://www.fairfaxcounty.gov/familyservices today.",
        "Write to benefits@fairfaxcounty.gov with questions.",
        "Go to 1901 S. Bell Street, Suite 200.",
        "You can dial 211 for local help.",
    ],
)
def test_contacts_printed_on_the_paper_are_kept(scrubber: cf.ContactScrubber, text: str) -> None:
    assert scrubber.scrub(text) == text
    assert scrubber.total == 0 and scrubber.warnings() == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Call 703-555-0199 to ask.", f"Call {MARK} to ask."),
        ("Call 1-800-375-5283 or 800 375 5283 now.", f"Call {MARK} now."),
        ("Call +93 20 123 4567 for your family.", f"Call {MARK} for your family."),
        ("Report it at ReportFraud.ftc.gov.", f"Report it at {MARK}."),
        ("Visit uscis.gov/scams today.", f"Visit {MARK} today."),
        ("See www.fairfaxcounty.gov/other-page.", f"See {MARK}."),
        ("Email help@immigrationhelp.com now.", f"Email {MARK} now."),
        ("Go to 42 Main Street tomorrow.", f"Go to {MARK} tomorrow."),
        ("Call 911 if you feel sick.", f"Call {MARK} if you feel sick."),
        ("Text 988 any time.", f"Text {MARK} any time."),
        ("Llame al 911 si es urgente.", f"Llame al {MARK} si es urgente."),
    ],
)
def test_invented_contacts_are_replaced(
    scrubber: cf.ContactScrubber, text: str, expected: str
) -> None:
    assert scrubber.scrub(text) == expected
    assert scrubber.contacts_stripped >= 1
    assert scrubber.warnings() == [WarningCode.contacts_stripped]


@pytest.mark.parametrize(
    "text",
    [
        "The paper says 10/14/2026 at 9:00 AM.",
        "Your receipt number is IOE0912345678.",
        "The fee is $1,250.00 for 911 days of coverage.",
        "Answer 3 questions for the court.",
        "Take 2 pills and see Dr Lee.",
        "Case 2026-123 is open.",
        "Your A-Number is A123456789.",
        "Section 8 office",
    ],
)
def test_non_contacts_are_left_alone(scrubber: cf.ContactScrubber, text: str) -> None:
    assert scrubber.scrub(text) == text
    assert scrubber.total == 0


def test_organisations_not_on_paper_or_in_db_are_replaced(scrubber: cf.ContactScrubber) -> None:
    assert scrubber.scrub("Ask Northern Virginia Immigrant Services Center.") == f"Ask {ORG}."
    assert scrubber.scrub("Kaiser Permanente Hospital sent this.") == (
        "A group or office (see Get help nearby) sent this."
    )
    assert scrubber.orgs_replaced == 2
    assert scrubber.total == 2 and scrubber.warnings() == [WarningCode.contacts_stripped]


def test_a_leading_article_is_absorbed_into_the_org_marker(scrubber: cf.ContactScrubber) -> None:
    assert scrubber.scrub("Ask the Fake Immigrant Justice Center.") == f"Ask {ORG}."
    assert scrubber.scrub("Visit the Springfield Refugee Services Center.") == f"Visit {ORG}."
    assert scrubber.scrub("The Fake Immigrant Justice Center can help.") == (
        "A group or office (see Get help nearby) can help."
    )
    assert scrubber.orgs_replaced == 3


def test_new_contacts_only_reports_additions() -> None:
    original = "Call Cover Virginia at 1-855-242-8282 or visit coverva.org."
    assert cf.new_contacts("Call (855) 242-8282 or go to www.coverva.org.", original) == []
    added = cf.new_contacts("Call 703-555-0199.", original)
    assert [c.text for c in added] == ["703-555-0199"]


@pytest.mark.parametrize(
    "text",
    [
        "Ask the Legal Aid Justice Center for help.",  # in the DB
        "Casa Inc can help.",  # DB name + corporate suffix
        "The Fairfax County Department of Family Services sent this.",  # on the paper
        "Go to the Arlington Immigration Court.",  # one printed stretch, reordered
        "Talk to the Social Security Office.",  # generic institution words only
        "Your Doctor's Office can explain.",
        "The Department of Social Services can help.",
    ],
)
def test_known_or_generic_organisations_are_kept(scrubber: cf.ContactScrubber, text: str) -> None:
    assert scrubber.scrub(text) == text
    assert scrubber.orgs_replaced == 0


def test_scrub_all_and_none(scrubber: cf.ContactScrubber) -> None:
    assert scrubber.scrub(None) is None
    out = scrubber.scrub_all(["Call 703-555-0199.", "Nothing here."])
    assert out == [f"Call {MARK}.", "Nothing here."]
    assert scrubber.total == 1


def test_extra_texts_extend_the_allow_list() -> None:
    s = cf.make_scrubber("", set(), en_t(), extra_texts=["Help desk: 1-877-555-0100"])
    assert s.scrub("Call 1-877-555-0100.") == "Call 1-877-555-0100."
    assert s.scrub("Call 1-877-555-0101.") == f"Call {MARK}."


def test_eastern_digits_are_normalised() -> None:
    s = cf.make_scrubber("Call ٧٠٣-٥٥٥-٠١٤٢", set(), en_t())
    assert cf.normalize_phone("٧٠٣-٥٥٥-٠١٤٢") == "7035550142"
    assert s.allow.phones == frozenset({"7035550142"})


def test_find_contacts_kinds() -> None:
    kinds = [c.kind for c in cf.find_contacts("Call 703-555-0199 or mail a@b.org, see x.gov")]
    assert kinds == ["phone", "email", "url"]
    assert cf.has_contact("see example.com") and not cf.has_contact("see the example")
    assert cf.normalize_url("HTTPS://WWW.USCIS.gov/AddressChange/.") == "uscis.gov/addresschange"


def test_repo_names_seam(tmp_path: Path) -> None:
    """``ResourceRepo.names()`` returns raw names; ``AllowList`` normalises them itself."""
    allow = cf.AllowList.build("", ["  The Legal Aid Justice Center (LAJC) "])
    assert allow.allows_org("Legal Aid Justice Center LAJC")


@pytest.mark.parametrize(
    "verb", ["Try", "Reach", "Apply to", "Email", "Use", "Get help from", "Seek", "Choose"]
)
def test_a_leading_verb_is_not_swallowed_into_the_org(
    scrubber: cf.ContactScrubber, verb: str
) -> None:
    assert scrubber.scrub(f"{verb} Acme Legal Services LLC.") == f"{verb} {ORG}."


def test_a_marker_that_starts_a_sentence_is_capitalised(scrubber: cf.ContactScrubber) -> None:
    capital = "A group or office (see Get help nearby)"
    assert scrubber.scrub("Acme Legal Services LLC can help.") == f"{capital} can help."
    assert scrubber.scrub("Call us. Acme Legal Services LLC can help.") == (
        f"Call us. {capital} can help."
    )
    assert scrubber.scrub("Line one\nAcme Legal Services LLC helps.") == (
        f"Line one\n{capital} helps."
    )
    assert scrubber.scrub("Or ask Acme Legal Services LLC.") == f"Or ask {ORG}."


def test_printed_specific_words_plus_generic_words_are_not_a_printed_name() -> None:
    """D-10 / AI_PROMPTS §11.3: "Fairfax" and "County" are printed, but the name "Fairfax County
    Legal Aid Society" is neither on the paper nor in ``ResourceRepo.names()``."""
    from proxyhealth_api.resources.loader import ResourceRepo
    from proxyhealth_api.settings import DATA_DIR

    paper = "Arlington Immigration Court\n…\nFairfax County Department of Family Services"
    names = ResourceRepo.load(DATA_DIR / "resources").names()
    s = cf.make_scrubber(paper, names, en_t())
    assert s.scrub("Ask Fairfax County Legal Aid Society about it.") == f"Ask {ORG} about it."
    capital = ORG[0].upper() + ORG[1:]
    assert s.scrub("Fairfax Family Services Center can help.") == f"{capital} can help."
    assert s.orgs_replaced == 2
    for kept in (
        "Ask Fairfax County Department of Family Services.",  # printed as is
        "Go to the Arlington Immigration Court.",  # printed as is
        "Ask the Legal Aid Justice Center.",  # in the DB
    ):
        assert s.scrub(kept) == kept


def test_a_printed_name_may_be_reordered_only_within_one_stretch() -> None:
    allow = cf.AllowList.build("Immigration Court, Arlington, VA\nFairfax County Office")
    assert allow.allows_org("Arlington Immigration Court")  # one printed stretch, reordered
    assert not allow.allows_org("Fairfax Immigration Court")  # scattered words
    assert not allow.allows_org("Arlington County Legal Aid Society")


@pytest.fixture(scope="module")
def db_names() -> set[str]:
    from proxyhealth_api.resources.loader import ResourceRepo
    from proxyhealth_api.settings import DATA_DIR

    return ResourceRepo.load(DATA_DIR / "resources").names()


LANDLORD = "Notice from your landlord. Rent is due."
CAPITAL_ORG = ORG[0].upper() + ORG[1:]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Cut at the last institution word and accepted as part of a DB name.
        (
            "Contact the U.S. Department of Immigration Payments for help.",
            f"Contact {ORG} for help.",
        ),
        # Suffix-first "X of Y" names.
        ("Contact the Department of Immigration Payments for help.", f"Contact {ORG} for help."),
        ("Department of Immigration Payments can help.", f"{CAPITAL_ORG} can help."),
        # The words after the last institution word are checked too.
        ("Pay the Federal Immigration Agency Office of Fast Visas.", f"Pay {ORG}."),
        ("Ask the Legal Aid Justice Center and Fake Visas.", f"Ask {ORG}."),
        ("Go to the Housing Rights Association of Northern Virginia.", f"Go to {ORG}."),
    ],
)
def test_invented_org_names_are_replaced_whole(
    db_names: set[str], text: str, expected: str
) -> None:
    """D-10 / AI_PROMPTS §11.3: an org name passes only as a whole DB name or a printed name."""
    s = cf.make_scrubber(LANDLORD, db_names, en_t())
    assert s.scrub(text) == expected
    assert s.orgs_replaced == 1


@pytest.mark.parametrize(
    "text",
    [
        "Ask the Legal Aid Justice Center and Just Neighbors.",  # two whole DB names
        "Ask the Tahirih Justice Center.",
        "Ask the International Rescue Committee.",  # DB "International Rescue Committee (IRC)"
        "Contact the HHS Office for Civil Rights.",  # DB "HHS Office for Civil Rights: …"
        "Ask the Virginia Poverty Law Center.",  # parenthesised DB name
        "The Department of Health and Human Services can help.",  # generic words only
        "Ask the Clinic for Dari interpreters.",  # a language is not part of a name
        "Call the Immigration Court for Monday's hearing.",
        "Go to the Department of Labor. Then Call Them.",
    ],
)
def test_whole_db_names_and_generic_names_are_kept(db_names: set[str], text: str) -> None:
    s = cf.make_scrubber(LANDLORD, db_names, en_t())
    assert s.scrub(text) == text
    assert s.orgs_replaced == 0


def test_a_db_name_never_passes_by_a_part_of_it(db_names: set[str]) -> None:
    allow = cf.AllowList.build(LANDLORD, db_names)
    assert allow.allows_org("U.S. Department of Labor Wage and Hour Division")
    assert not allow.allows_org("U.S. Department of Immigration Payments")
    assert not allow.allows_org("Tahirih Justice")  # part of "Tahirih Justice Center"


def test_a_replacement_leaves_no_dangling_tail() -> None:
    s = cf.make_scrubber(LANDLORD, [], en_t())
    assert s.scrub("Contact the U.S. Department of Labor.") == (
        "Contact the U.S. Department of Labor."  # generic words only: kept whole
    )
    assert s.scrub("Ask the Housing Rights Association of Northern Virginia today.") == (
        f"Ask {ORG} today."
    )
    assert s.scrub("Acme Legal Services Inc. can help.") == f"{CAPITAL_ORG} can help."


def test_us_initialism_is_one_generic_word(db_names: set[str]) -> None:
    court = cf.make_scrubber("Immigration Court, 1901 S. Bell Street, Arlington.", db_names, en_t())
    for kept in ("Ask the U.S. Immigration Court.", "Ask the US Immigration Court."):
        assert court.scrub(kept) == kept
    uscis = cf.make_scrubber(
        "U.S. Citizenship and Immigration Services. Receipt Notice.", db_names, en_t()
    )
    printed = "The U.S. Citizenship and Immigration Services Office can help."
    assert uscis.scrub(printed) == printed  # a trailing generic word the paper does not print
    assert court.orgs_replaced == 0 and uscis.orgs_replaced == 0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Go to scamsite.xyz to pay.", f"Go to {MARK} to pay."),
        ("Go to bit.ly/abc123 to pay.", f"Go to {MARK} to pay."),
        ("Go to irs.co to pay.", f"Go to {MARK} to pay."),  # the paper prints irs.com
        ("See county.gov.", f"See {MARK}."),  # the paper prints fairfaxcounty.gov
        ("See fairfaxcounty.gov/family.", f"See {MARK}."),  # not a whole path segment
        ("Email elp@fairfaxcounty.gov.", f"Email {MARK}."),
        ("See irs.com.", "See irs.com."),
        ("See fairfaxcounty.gov/familyservices/forms today.", f"See {MARK} today."),
        ("See www.fairfaxcounty.gov.", "See www.fairfaxcounty.gov."),
        ("Upload form.pdf today.", "Upload form.pdf today."),  # a file name, not a domain
        ("Pay it today.Please call.", "Pay it today.Please call."),  # a missing space
    ],
)
def test_domains_are_compared_on_label_boundaries(text: str, expected: str) -> None:
    paper = "Visit irs.com or www.fairfaxcounty.gov/familyservices. Email help@fairfaxcounty.gov."
    s = cf.make_scrubber(paper, [], en_t())
    assert s.scrub(text) == expected


# --- Phase 2B: head-first and Arabic-script names, dash look-alikes, 00 and vanity numbers -------


@pytest.mark.parametrize(
    "text",
    [
        "Llame al Centro Legal de Inmigración Hispano para recibir ayuda.",
        "Visite la Clínica Legal Latina en Fairfax.",
        "Busque ayuda en Servicios Legales Comunitarios.",
        "با انجمن کمک حقوقی افغان‌ها تماس بگیرید.",
        "اتصل بمركز المساعدة القانونية العربي.",
        "Ask the Northern Virginia Immigrant Justice Project.",
    ],
)
def test_invented_organisations_in_any_word_order_or_script_are_replaced(
    scrubber: cf.ContactScrubber, text: str
) -> None:
    assert ORG in scrubber.scrub(text), text


@pytest.mark.parametrize(
    "text",
    [
        "Call 703–555–0199 today.",  # en dashes
        "Call 703‑555‑0199 today.",  # U+2011 non-breaking hyphens
        "Call ٧٠٣–٥٥٥–٠١٩٩ today.",  # Eastern digits, en dashes
        "Call 00 44 20 7946 0958",
        "Call 1-800-FIX-BILL for help.",
    ],
)
def test_phone_spellings_the_old_patterns_missed(scrubber: cf.ContactScrubber, text: str) -> None:
    assert MARK in scrubber.scrub(text), text


@pytest.mark.parametrize(
    "text",
    [
        "Llame a la Oficina del Seguro Social.",
        "Escriba a los Servicios de Ciudadanía e Inmigración de los Estados Unidos.",
        "Llame a la Oficina del Jurado si tiene preguntas.",
        "El Departamento de Servicios Familiares del Condado de Fairfax le escribió.",
        "اداره خدمات تابعیت و مهاجرت ایالات متحده به شما نامه فرستاده است.",
        "این نامه از دفتر تأمین اجتماعی است.",
        "Contact the City Council.",
        "Call (703) 555‑0142 with questions.",  # printed number, non-breaking hyphen
        "Room 204 NEW WING",
    ],
)
def test_translated_agency_names_and_printed_contacts_are_kept(
    scrubber: cf.ContactScrubber, text: str
) -> None:
    assert scrubber.scrub(text) == text


def test_spanish_contraction_is_absorbed_before_the_marker(scrubber: cf.ContactScrubber) -> None:
    out = scrubber.scrub("Llame al Centro Legal de Inmigración Hispano hoy.")
    assert out == f"Llame a {ORG} hoy."


def test_scrub_kinds_checks_only_phone_web_and_email(scrubber: cf.ContactScrubber) -> None:
    """A translation keeps a translated name but never an unprinted number or site."""
    text = "Legal Aid Fairfax Help Center can help. Call 1-866-555-0123 or www.renew-now.com."
    out = scrubber.scrub_kinds(text, cf.CONTACT_KINDS)
    assert "Help Center" in out and "555-0123" not in out and "renew-now" not in out
    assert scrubber.contacts_stripped >= 1


# --- Phase 2C: a Spanish phrase run into a printed name with "de" is not an invented org


def test_spanish_phrase_before_a_printed_name_is_kept() -> None:
    paper = "U.S. Citizenship and Immigration Services\nRequest for Evidence"
    s = cf.make_scrubber(paper, set(), en_t())
    text = (
        "Vengo por: una Solicitud de Evidencia de USCIS de U.S. Citizenship and Immigration "
        "Services."
    )
    assert s.scrub(text) == text and s.total == 0


def test_spanish_phrase_before_an_unprinted_name_is_still_replaced() -> None:
    s = cf.make_scrubber("U.S. Citizenship and Immigration Services", set(), en_t())
    out = s.scrub("Pida ayuda a la Solicitud de Fairfax Immigrant Legal Services hoy.")
    assert "Fairfax Immigrant Legal Services" not in out and s.total == 1
