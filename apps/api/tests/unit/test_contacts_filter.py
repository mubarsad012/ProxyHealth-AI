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
ORG = "an organization (see Get help nearby)"


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
        "An organization (see Get help nearby) sent this."
    )
    assert scrubber.orgs_replaced == 2
    assert scrubber.total == 2 and scrubber.warnings() == [WarningCode.contacts_stripped]


def test_a_leading_article_is_absorbed_into_the_org_marker(scrubber: cf.ContactScrubber) -> None:
    assert scrubber.scrub("Ask the Fake Immigrant Justice Center.") == f"Ask {ORG}."
    assert scrubber.scrub("Visit the Springfield Refugee Services Center.") == f"Visit {ORG}."
    assert scrubber.scrub("The Fake Immigrant Justice Center can help.") == (
        "An organization (see Get help nearby) can help."
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
        "Go to the Arlington Immigration Court.",  # every specific word printed
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
    capital = "An organization (see Get help nearby)"
    assert scrubber.scrub("Acme Legal Services LLC can help.") == f"{capital} can help."
    assert scrubber.scrub("Call us. Acme Legal Services LLC can help.") == (
        f"Call us. {capital} can help."
    )
    assert scrubber.scrub("Line one\nAcme Legal Services LLC helps.") == (
        f"Line one\n{capital} helps."
    )
    assert scrubber.scrub("Or ask Acme Legal Services LLC.") == f"Or ask {ORG}."
