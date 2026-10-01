"""WP2 — ``analysis/scam.py`` + ``data/safety/scam.yaml`` (D-13; DOCUMENT_TAXONOMY §6)."""

from __future__ import annotations

import json

import pytest

from proxyhealth_api.analysis import scam as sc
from proxyhealth_api.analysis.transcript import assemble_transcript
from proxyhealth_api.contracts.analysis import RedFlag
from proxyhealth_api.contracts.enums import (
    DocumentType,
    RedFlagKind,
    ScamRisk,
    SenderKind,
    Severity,
)
from proxyhealth_api.settings import DATA_DIR
from tests.unit._fixtures_wp2 import block, en_t

DT = DocumentType
SK = SenderKind


def segs(*lines: str) -> list[sc.Segment]:
    return [sc.Segment(f"p1b{i}", 1, line) for i, line in enumerate(lines, 1)]


def model_flag(kind: RedFlagKind, quote: str) -> RedFlag:
    return RedFlag(
        kind=kind, text="model text", source_quote=quote, span_ids=["p1b1"], page=1,
        severity=Severity.medium, fixed_copy_key=None, verified=True,
    )  # fmt: skip


GIFT_CARD_LETTER = segs(
    "U.S. Citizenship and Immigration Services — Final Warning",
    "To avoid deportation you must pay a fee of $500 immediately.",
    "Pay with Google Play gift cards. Confirm at www.uscis-payments.com (USCIS office).",
)


def test_config_loads_and_every_reason_key_exists() -> None:
    cfg = sc.load_config()
    en = json.loads((DATA_DIR / "langpacks" / "en.json").read_text(encoding="utf-8"))
    assert cfg.reason_keys <= set(en)
    assert "scam.card.likely" in en and "scam.card.possible" in en
    assert cfg.possible == 2 and cfg.likely == 4
    assert cfg.reviewed_by == {"en": None, "es": None, "ar": None, "prs": None, "ps": None}
    thirteen = {
        "scam.gift_card", "scam.wire_transfer", "scam.payment_app", "scam.crypto",
        "scam.arrest_threat", "scam.deportation_threat", "scam.guaranteed", "scam.notario",
        "scam.non_gov_domain", "scam.expedite_fee", "scam.fee_for_free_form",
        "scam.urgency_pressure", "scam.impersonation",
    }  # fmt: skip
    assert thirteen <= cfg.reason_keys


def test_gift_card_letter_is_likely_with_reasons_and_flags() -> None:
    """§6.2 worked check: gift card (3) + deportation threat (2) + non-.gov domain (3) = 8."""
    out = sc.score_scam(
        GIFT_CARD_LETTER, document_type=DT.other_notice, sender_kind=SK.federal_agency,
        sender_as_written="U.S. Citizenship and Immigration Services", t=en_t(),
    )  # fmt: skip
    assert out.scam_risk is ScamRisk.likely and out.is_likely_scam
    assert out.score >= 8
    top = ["scam.gift_card", "scam.non_gov_domain", "scam.deportation_threat"]
    assert out.scam_reasons[:3] == top
    kinds = {f.kind for f in out.red_flags}
    assert {RedFlagKind.scam_payment_method, RedFlagKind.impersonation} <= kinds
    gift = next(f for f in out.red_flags if f.kind is RedFlagKind.scam_payment_method)
    assert gift.text == "Asks for gift cards" and gift.severity is Severity.high
    assert gift.span_ids == ["p1b3"] and gift.page == 1 and gift.fixed_copy_key is None
    assert gift.source_quote and "gift cards" in gift.source_quote and gift.verified


def test_spanish_patterns() -> None:
    out = sc.score_scam(
        segs("Pague con tarjetas de regalo hoy.", "Evite la deportación: pague la cuota ahora."),
        document_type=DT.other_notice, sender_kind=SK.unknown,
    )  # fmt: skip
    assert out.scam_risk is ScamRisk.likely
    assert "scam.gift_card" in out.scam_reasons


def test_sms_with_arrest_threat() -> None:
    out = sc.score_scam(
        segs("SSA: a warrant for your arrest will be issued today unless you pay with a "
             "prepaid card. Call now."),
        document_type=DT.other_notice, sender_kind=SK.unknown,
    )  # fmt: skip
    assert out.scam_risk is ScamRisk.likely
    assert out.scam_reasons[0] == "scam.gift_card"
    assert "scam.arrest_threat" in out.scam_reasons


def test_utility_prepaid_card_threat_is_likely() -> None:
    out = sc.score_scam(
        segs("Pay within 1 hour by prepaid card or your service is cut."),
        document_type=DT.utility_shutoff, sender_kind=SK.utility, sender_as_written="Power Co",
    )  # fmt: skip
    assert out.score == 4 and out.scam_risk is ScamRisk.likely


@pytest.mark.parametrize(
    ("lines", "doc", "sender"),
    [
        (("FINAL NOTICE. Your balance of $210.00 is past due.",
          "Pay online at inova.org or call the billing office."), DT.medical_bill,
         SK.hospital_or_clinic),
        (("Pay online at irs.gov or mail a check to the Internal Revenue Service.",),
         DT.irs_notice, SK.federal_agency),
        (("Filing fee: $550 payable to U.S. Department of Homeland Security.",
          "You may request premium processing with Form I-907 for a fee."),
         DT.uscis_receipt, SK.federal_agency),
        (("If you fail to appear, a warrant may be issued for your arrest.",),
         DT.traffic_court, SK.court),
        (("You may be ordered removed in your absence if you do not appear.",),
         DT.nta, SK.court),
        (("Employee Social Security Number: ___  List A documents",), DT.i9, SK.employer),
        (("Sworn before me, notary public, State of Virginia. Seal.",), DT.lease, SK.landlord),
        (("Wire transfers accepted. Accepted forms of payment: card, check, wire transfer.",),
         DT.medical_bill, SK.hospital_or_clinic),
        (("Social Security Administration. Visit www.ssa.gov/myaccount.",),
         DT.ssa_letter, SK.federal_agency),
        (("Kaiser Permanente patient portal: kp.org. Questions about Medicare?",),
         DT.eob, SK.insurer),
    ],
)  # fmt: skip
def test_false_positive_guards(
    lines: tuple[str, ...], doc: DocumentType, sender: SenderKind
) -> None:
    out = sc.score_scam(segs(*lines), document_type=doc, sender_kind=sender, sender_as_written="X")
    assert out.scam_risk is ScamRisk.none, (out.score, out.fired)
    assert out.red_flags == []


def test_inova_model_urgency_flag_alone_is_none() -> None:
    flag = model_flag(RedFlagKind.urgency_pressure, "FINAL NOTICE")
    out = sc.score_scam(
        segs("FINAL NOTICE"), document_type=DT.medical_bill, sender_kind=SK.hospital_or_clinic,
        sender_as_written="Inova", model_flags=[flag],
    )  # fmt: skip
    assert out.scam_risk is ScamRisk.none and out.score == 1


def test_landlord_zelle_is_possible() -> None:
    out = sc.score_scam(
        segs("You can pay rent by Zelle to John Smith."), document_type=DT.lease,
        sender_kind=SK.landlord, sender_as_written="John Smith", t=en_t(),
    )  # fmt: skip
    assert out.scam_risk is ScamRisk.possible and out.scam_reasons == ["scam.payment_app"]
    assert out.red_flags[0].severity is Severity.medium


def test_model_flag_and_regex_count_once() -> None:
    lines = segs("Pay with Google Play gift cards.")
    flag = model_flag(RedFlagKind.scam_payment_method, "Google Play gift cards")
    both = sc.score_scam(lines, document_type=DT.other_notice, model_flags=[flag])
    regex_only = sc.score_scam(lines, document_type=DT.other_notice)
    assert both.score == regex_only.score == 3
    assert both.hits["gift_card"].from_model and both.hits["gift_card"].from_regex
    # a model-backed signal keeps its own (linted) flag; code adds none for it
    assert all(f.kind is not RedFlagKind.scam_payment_method for f in both.red_flags)


def test_unverified_model_flags_do_not_count() -> None:
    flag = model_flag(RedFlagKind.impersonation, "Department of Immigration")
    flag = flag.model_copy(update={"verified": False})
    out = sc.score_scam(segs("hello"), document_type=DT.other_notice, model_flags=[flag])
    assert out.score == 0


def test_model_payment_flag_without_known_method() -> None:
    flag = model_flag(RedFlagKind.scam_payment_method, "send cash in an envelope")
    out = sc.score_scam(
        segs("send cash in an envelope"), document_type=DT.other_notice,
        sender_kind=SK.federal_agency, model_flags=[flag],
    )  # fmt: skip
    assert out.scam_risk is ScamRisk.likely and out.likely_rule == "payment_and_agency_sender"
    assert out.scam_reasons == []  # no fixed chip for an unknown method


def test_secrecy_raises_urgency_weight() -> None:
    plain = sc.score_scam(segs("Call now."), document_type=DT.other_notice)
    secret = sc.score_scam(segs("Call now. Do not tell anyone."), document_type=DT.other_notice)
    assert plain.score == 1 and secret.score == 2


def test_troubleshoot_credential_request_and_lines() -> None:
    lines = sc.segments_from_lines(["Enter your SSN and bank PIN to unlock your benefits"])
    assert lines[0].id == "s1" and lines[0].page is None
    out = sc.score_scam(
        lines, document_type=None, credential_request=True, sender_kind=SK.unknown, t=en_t()
    )
    assert out.hits["id_or_payment_data_request"].weight == 2
    assert out.scam_risk is ScamRisk.possible
    assert all(f.span_ids == [] for f in out.red_flags)


def test_no_sender_with_money_scores() -> None:
    out = sc.score_scam(segs("Send $300 now."), document_type=DT.other_notice)
    assert "no_sender" not in out.hits  # no demands passed
    assert out.score == 0


def test_resource_hosts_are_not_fake_agencies() -> None:
    lines = segs("USCIS partners: see immigrationlawhelp.org for free help.")
    assert sc.score_scam(lines, document_type=DT.other_notice).hits.get("non_gov_domain")
    out = sc.score_scam(
        lines, document_type=DT.other_notice, resource_hosts=["https://www.immigrationlawhelp.org/"]
    )
    assert "non_gov_domain" not in out.hits


def test_reasons_are_capped_and_ordered() -> None:
    out = sc.score_scam(
        segs("Bitcoin, Western Union, gift cards, Zelle. Guaranteed green card approval.",
             "Expedite your case for a fee of $300. Notario público. Act now.",
             "To avoid deportation pay immediately. Department of Immigration."),
        document_type=DT.other_notice,
    )  # fmt: skip
    assert len(out.scam_reasons) == sc.MAX_REASONS
    assert out.scam_reasons[:3] == ["scam.gift_card", "scam.wire_transfer", "scam.crypto"]


def test_retype_only_agency_papers() -> None:
    assert sc.retype_for_scam(DT.uscis_rfe, ScamRisk.likely) is DT.other_notice
    assert sc.retype_for_scam(DT.nta, ScamRisk.likely) is DT.nta
    assert sc.retype_for_scam(DT.uscis_rfe, ScamRisk.possible) is DT.uscis_rfe


def test_score_transcript_and_hosts() -> None:
    t = assemble_transcript([block("p1b1", "Pay with iTunes gift cards")], pages_received=1)
    assert sc.score_transcript(t, document_type=DT.other_notice).hits["gift_card"].segment
    assert sc.host_of("HTTPS://www.USCIS.gov/x") == "uscis.gov"
    assert sc.host_of("agent@uscis-help.com") == "uscis-help.com"
    assert sc.is_gov_host("uscis.gov", (".gov",)) and not sc.is_gov_host("uscis-gov.com", (".gov",))


@pytest.mark.parametrize(
    "line",
    [
        "Pay the $500 fee with gift cards today or you will be deported.",
        "Pay the $500 fee today or you will be deported.",
        "Pague hoy o será deportado.",
    ],
)
def test_pay_or_be_deported_fires_the_deportation_threat(line: str) -> None:
    out = sc.score_scam(segs(line), document_type=DT.other_notice, sender_kind=SK.unknown)
    assert "scam.deportation_threat" in out.scam_reasons
    assert out.scam_risk is not ScamRisk.none


def test_pay_or_be_deported_keeps_the_court_notice_guard() -> None:
    line = "Pay the $500 fee today or you will be deported."
    out = sc.score_scam(segs(line), document_type=DT.nta, sender_kind=SK.court)
    assert "scam.deportation_threat" not in out.scam_reasons


# --- Phase 2B: agency anti-fraud boilerplate, .gov payment portals, ar/prs/ps, notaría -----------

BOILERPLATE = [
    (SK.federal_agency, DT.uscis_rfe,
     "Avoid scams: USCIS will never ask you to pay by Western Union, MoneyGram, PayPal, "
     "or gift cards."),
    (SK.federal_agency, DT.ssa_letter,
     "Social Security will never ask you to pay with gift cards, wire transfers, "
     "cryptocurrency, or cash."),
    (SK.federal_agency, DT.irs_notice,
     "The IRS will never demand immediate payment using gift cards, prepaid debit cards or "
     "wire transfers."),
    (SK.state_agency, DT.medicaid_renewal,
     "Nunca le pediremos pagos con tarjetas de regalo ni por Zelle."),
    (SK.federal_agency, DT.uscis_receipt,
     "Scammers may ask you to pay with gift cards. If someone asks for a wire transfer, hang up."),
]  # fmt: skip


@pytest.mark.parametrize(("sender", "doc", "line"), BOILERPLATE)
def test_agency_anti_fraud_boilerplate_is_not_a_scam(
    sender: SenderKind, doc: DocumentType, line: str
) -> None:
    out = sc.score_scam(segs("Official notice", line), document_type=doc, sender_kind=sender,
                        sender_as_written="Agency")  # fmt: skip
    assert out.scam_risk is ScamRisk.none and out.fired == [], out.fired
    assert sc.retype_for_scam(doc, out.scam_risk) is doc, "a real RFE keeps its type and CTA"


@pytest.mark.parametrize(
    "line",
    [
        "We do not accept cash or checks, pay with gift cards only.",
        "If you do not pay with iTunes gift cards within 24 hours you will be arrested.",
        "We never ask twice. Send Google Play gift cards today.",
    ],
)
def test_a_real_demand_near_a_negation_still_scores(line: str) -> None:
    out = sc.score_scam(segs(line), document_type=DT.other_notice, sender_kind=SK.federal_agency)
    assert out.scam_risk is ScamRisk.likely and "gift_card" in out.fired


def test_gov_payment_portal_is_not_a_payment_app_scam() -> None:
    court = sc.score_scam(
        segs("You may prepay the fine online with a credit card or PayPal at vacourts.gov."),
        document_type=DT.traffic_court, sender_kind=SK.court, sender_as_written="Circuit Court",
    )  # fmt: skip
    county = sc.score_scam(
        segs("Pay your tax online with PayPal or Venmo at samplecountyva.gov/pay."),
        document_type=DT.other_notice, sender_kind=SK.local_agency, sender_as_written="County",
    )  # fmt: skip
    assert court.scam_risk is ScamRisk.none and county.scam_risk is ScamRisk.none
    zelle = sc.score_scam(
        segs("Send the fee by Zelle to 703-555-0199. More at uscis.gov."),
        document_type=DT.other_notice, sender_kind=SK.federal_agency,
    )  # fmt: skip
    assert zelle.scam_risk is ScamRisk.likely, "a recipient next to the .gov link is no portal"


def test_model_flag_quoting_anti_fraud_boilerplate_is_ignored() -> None:
    quote = "USCIS will never ask you to pay by Western Union, MoneyGram, PayPal, or gift cards."
    assert sc.is_anti_fraud_quote(quote)
    assert not sc.is_anti_fraud_quote("You must pay today with Google Play gift cards")
    assert not sc.is_anti_fraud_quote(None)
    out = sc.score_scam(
        segs(quote), document_type=DT.uscis_rfe, sender_kind=SK.federal_agency,
        model_flags=[model_flag(RedFlagKind.scam_payment_method, quote)],
    )  # fmt: skip
    assert out.scam_risk is ScamRisk.none


@pytest.mark.parametrize(
    "lines",
    [
        [
            "دائرة الهجرة الأمريكية",
            "يجب عليك دفع 900 دولار عبر ويسترن يونيون خلال 24 ساعة لتجنب الترحيل.",
        ],
        [
            "اداره مهاجرت امریکا",
            "برای جلوگیری از اخراج، ۵۰۰ دالر کارت هدیه گوگل پلی بخرید و کد آن را بفرستید.",
        ],
    ],
)
def test_arabic_and_dari_payment_demands_score(lines: list[str]) -> None:
    for sender in (SK.unknown, SK.federal_agency):
        out = sc.score_scam(segs(*lines), document_type=None, sender_kind=sender)
        assert out.scam_risk is ScamRisk.likely, (sender, out.fired)


def test_neutral_arabic_script_letters_do_not_score() -> None:
    lines = [
        "يرجى إحضار هذه الرسالة إلى موعدك يوم الاثنين.",
        "لطفاً این نامه را روز دوشنبه با خود بیاورید.",
    ]
    out = sc.score_scam(segs(*lines), document_type=DT.other_notice, sender_kind=SK.unknown)
    assert out.scam_risk is ScamRisk.none


def test_notaria_publica_is_a_notario() -> None:
    out = sc.score_scam(
        segs("Notaría Pública Hispana — Le arreglamos sus papeles de inmigración."),
        document_type=DT.other_notice, sender_kind=SK.unknown,
    )  # fmt: skip
    assert "notario" in out.fired
