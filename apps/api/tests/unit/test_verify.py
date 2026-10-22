"""WP2 — ``analysis/verify.py`` (D-09; AI_PROMPTS §11.2): every fact is a quotation."""

from __future__ import annotations

from proxyhealth_api.analysis import verify as v
from proxyhealth_api.analysis.transcript import Transcript, assemble_transcript
from proxyhealth_api.contracts.analysis import AmountInfo
from proxyhealth_api.contracts.common import TextBlock
from proxyhealth_api.contracts.enums import Confidence, DemandKind, RedFlagKind
from tests.unit._fixtures_wp2 import block, demand_out, red_flag_out

LINE = "Please return the signed form to our office by October 14, 2026."


def _t(*blocks: TextBlock) -> Transcript:
    return assemble_transcript(list(blocks), pages_received=1)


def test_exact_substring_passes() -> None:
    t = _t(block("p1b1", LINE))
    check = v.verify_span(t, ["p1b1"], "by October 14, 2026", value_verbatim="October 14, 2026")
    assert check.verified and check.note == v.NOTE_EXACT == "exact"
    assert check.confidence is Confidence.medium
    assert check.span_ids == ["p1b1"] and check.page == 1


def test_nfkc_folds_fullwidth_digits_and_ligatures() -> None:
    t = _t(block("p1b1", "Pay by １０/１４/２０２６ at the ﬁnance office"))
    check = v.verify_span(t, ["p1b1"], "Pay by 10/14/2026 at the finance office")
    assert check.verified


def test_dash_and_quote_unification() -> None:
    t = _t(block("p1b1", "Hearing: 9:00 AM – “Courtroom 3” — Arlington"))
    check = v.verify_span(t, ["p1b1"], 'Hearing: 9:00 AM - "Courtroom 3" - Arlington')
    assert check.verified
    assert v.normalize("a‑b ‘c’") == "a-b 'c'"


def test_ocr_confusion_map_applies_to_matching_copy_only() -> None:
    t = _t(block("p1b1", "Respond by 0ctober l4, 2O26"))
    check = v.verify_span(t, ["p1b1"], "Respond by October 14, 2026")
    assert check.verified
    # the normaliser used for display keeps the letters; only match_key maps them
    assert v.normalize("0ctober") == "0ctober"
    assert v.match_key("SOlI") == v.match_key("5011")


def test_whitespace_is_collapsed() -> None:
    t = _t(block("p1b1", "Return   this\nform  by\tOctober 14"))
    assert v.verify_span(t, ["p1b1"], "Return this form by October 14").verified


def test_fuzzy_fallback_at_or_above_threshold() -> None:
    t = _t(block("p1b1", LINE))
    quote = "Please return the signed form to our ofice by October 14, 2026."
    check = v.verify_span(t, ["p1b1"], quote)
    assert check.verified
    assert check.note is not None and check.note.startswith("fuzzy match ")
    assert check.ratio is not None and check.ratio >= v.FUZZY_THRESHOLD


def test_below_threshold_is_not_found() -> None:
    t = _t(block("p1b1", LINE))
    check = v.verify_span(t, ["p1b1"], "You must pay $500 to the court tomorrow morning.")
    assert not check.verified
    assert check.note == v.NOTE_NOT_FOUND
    assert check.confidence is Confidence.low


def test_value_must_sit_in_quote_with_every_digit_run() -> None:
    t = _t(block("p1b1", LINE))
    bad_value = v.verify_span(t, ["p1b1"], "by October 14, 2026", value_verbatim="October 15, 2026")
    assert not bad_value.verified and bad_value.note == v.NOTE_VALUE_NOT_IN_QUOTE
    assert v.check_value("$1,250.00", "Amount due: $1,250.00") is None
    assert v.check_value("$1,250.00", "Amount due: $1,260.00") == v.NOTE_VALUE_NOT_IN_QUOTE
    assert v.digit_runs("Pay ٣٠ days, ۱۴ Oct") == ["30", "14"]


def test_value_check_is_strict_with_no_fuzzy_fallback() -> None:
    quote = "Return the form by October 15, 2026."
    assert v.check_value("October 1, 2026", quote) == v.NOTE_VALUE_NOT_IN_QUOTE
    assert v.check_value("October 15, 2026", quote) is None
    assert v.check_value("$95", "You owe $950 today.") == v.NOTE_VALUE_NOT_IN_QUOTE
    assert v.check_value("$95", "You owe $95 today.") is None
    assert v.check_value("Oct", "by October 15") == v.NOTE_VALUE_NOT_IN_QUOTE
    assert v.check_value("$95", "You owe $95.00 today.") is None
    # scripts without spaces between words still match
    assert v.check_value("2026年10月14日", "请于2026年10月14日前返回") is None


def test_wrong_value_is_not_verified_and_gets_no_date() -> None:
    t = _t(block("p1b1", "Return the form by October 15, 2026."))
    wrong = demand_out(
        "d1", value_verbatim="October 1, 2026", source_quote="Return the form by October 15, 2026.",
        span_ids=["p1b1"], date_text="October 1, 2026",
    )  # fmt: skip
    out = v.verify_demands([wrong], t)
    assert out.verified == [] and len(out.unverified) == 1
    assert out.unverified[0].verification_note == v.NOTE_VALUE_NOT_IN_QUOTE
    assert out.unverified[0].reminder_eligible is False


def test_contains_token_boundaries() -> None:
    assert v.contains_token("14", "on 14 oct")
    assert not v.contains_token("14", "on 145 oct")
    assert v.contains_token("14", "on 145 or 14")
    assert v.contains_token("", "anything")


def test_unknown_block_ids_fail() -> None:
    t = _t(block("p1b1", LINE))
    check = v.verify_span(t, ["p9b9"], "by October 14, 2026")
    assert not check.verified and check.note == v.NOTE_UNKNOWN_BLOCK and check.span_ids == []


def test_empty_quote_fails() -> None:
    assert v.find_quote("   ", LINE).note == v.NOTE_EMPTY_QUOTE


def test_edge_crop_forces_low_confidence() -> None:
    edge = block("p1b1", LINE, bbox=[0.0, 0.5, 0.6, 0.55])
    t = _t(edge)
    check = v.verify_span(t, ["p1b1"], "by October 14, 2026", model_confidence=Confidence.high)
    assert check.verified and check.edge_crop and check.confidence is Confidence.low
    assert v.is_edge_block(block("x", "y", bbox=[0.2, 0.2, 0.98, 0.3]))
    assert not v.is_edge_block(block("x", "y", bbox=[0.1, 0.1, 0.9, 0.9]))


def test_unclear_or_handwriting_forces_low_confidence() -> None:
    t = _t(block("p1b1", LINE, unclear=True), block("p1b2", "Signed: J. Doe", handwriting=True))
    assert v.verify_span(t, ["p1b1"], "October 14, 2026").confidence is Confidence.low
    assert v.verify_span(t, ["p1b2"], "J. Doe").confidence is Confidence.low


def test_quote_may_span_several_blocks() -> None:
    t = _t(block("p1b1", "Please return the form"), block("p1b2", "by October 14, 2026."))
    assert v.verify_span(t, ["p1b1", "p1b2"], "return the form by October 14, 2026").verified


def test_verify_demands_splits_and_renames_duplicates() -> None:
    t = _t(block("p1b1", LINE), block("p1b2", "Amount due: $45.10", bbox=[0.1, 0.97, 0.5, 0.99]))
    good = demand_out(
        "d1", value_verbatim="October 14, 2026", source_quote="by October 14, 2026",
        span_ids=["p1b1"], date_text="October 14, 2026",
    )  # fmt: skip
    dup = demand_out(
        "d1", value_verbatim="$45.10", source_quote="Amount due: $45.10", span_ids=["p1b2"],
        amount_text="$45.10", currency="USD",
    )  # fmt: skip
    bad = demand_out(
        "d3", value_verbatim="November 1", source_quote="by November 1", span_ids=["p1b1"]
    )
    out = v.verify_demands([good, dup, bad], t)
    assert [d.id for d in out.verified] == ["d1", "d1_2"]
    assert [d.id for d in out.unverified] == ["d3"]
    assert out.unverified[0].verified is False
    assert out.unverified[0].confidence is Confidence.low
    assert out.unverified[0].verification_note == v.NOTE_NOT_FOUND
    assert out.facts_checked == 3 and out.facts_rejected == 1
    assert out.page_edge_crop is True
    assert out.sources["d1_2"] is dup and out.sources["d3"] is bad
    assert out.verified[1].amount is not None and out.verified[1].amount.amount_minor == 4510
    assert all(d.date is None and d.reminder_eligible is False for d in out.verified)


def test_verify_red_flags_drops_unverified_and_keeps_sentinel() -> None:
    t = _t(block("p1b1", "Pay with Google Play gift cards today"))
    ok = red_flag_out(
        "scam_payment_method", "Asks for gift cards.", source_quote="Google Play gift cards",
        span_ids=["p1b1"],
    )  # fmt: skip
    missing = red_flag_out(
        "impersonation", "Pretends to be USCIS.", source_quote="Officer Smith", span_ids=["p1b1"]
    )
    no_quote = red_flag_out("notario", "Mentions a notario.", source_quote=None, span_ids=[])
    sentinel = red_flag_out("other", v.MULTIPLE_DOCUMENTS_SENTINEL, source_quote=None, span_ids=[])
    out = v.verify_red_flags([ok, missing, no_quote, sentinel], t)
    kinds = [f.kind for f in out.flags]
    assert kinds == [RedFlagKind.scam_payment_method, RedFlagKind.other]
    assert out.flags[0].severity.value == "high" and out.flags[0].verified
    assert out.flags[1].text == v.MULTIPLE_DOCUMENTS_SENTINEL
    assert out.facts_checked == 3 and out.facts_rejected == 2


def test_parse_amount() -> None:
    assert v.parse_amount("$1,234.50", "usd") == AmountInfo(amount_minor=123450, currency="USD")
    assert v.parse_amount("45", None) == AmountInfo(amount_minor=4500, currency="USD")
    assert v.parse_amount("$1234.50", "USD") == AmountInfo(amount_minor=123450, currency="USD")
    assert v.parse_amount("$12345", "USD") == AmountInfo(amount_minor=1234500, currency="USD")
    assert v.parse_amount("$100000", "USD") == AmountInfo(amount_minor=10000000, currency="USD")
    assert v.parse_amount("$1500.00", "USD") == AmountInfo(amount_minor=150000, currency="USD")
    assert v.parse_amount("$1,000,000", "USD") == AmountInfo(amount_minor=100000000, currency="USD")
    assert v.parse_amount("no number", "USD") is None
    assert v.parse_amount(None, "USD") is None


def test_amount_text_not_in_quote_is_not_parsed() -> None:
    """D-09: a figure the paper does not print never becomes ``Demand.amount`` (the va_pay_or_quit
    mutation: ``amount_text`` "$2,450.00" against a printed "$1,450.00")."""
    rent = "You owe rent of $1,450.00 for September 2026."
    t = _t(block("p1b1", rent))
    invented = demand_out(
        "d1", kind=DemandKind.amount, value_verbatim="$1,450.00", source_quote=rent,
        span_ids=["p1b1"], amount_text="$2,450.00", currency="USD",
    )  # fmt: skip
    out = v.demand_from_out(invented, t)
    assert out.verified and out.amount == AmountInfo(amount_minor=145000, currency="USD")
    # Another kind has no printed value to fall back on: no amount at all.
    action = invented.model_copy(update={"kind": DemandKind.action, "value_verbatim": rent})
    assert v.demand_from_out(action, t).amount is None
    # A value with more than one number is not guessed from either.
    sentence = invented.model_copy(update={"value_verbatim": rent})
    assert v.demand_from_out(sentence, t).amount is None
    # Printed in the quote: parsed as before.
    printed = invented.model_copy(update={"amount_text": "$1,450.00"})
    assert v.demand_from_out(printed, t).amount == AmountInfo(amount_minor=145000, currency="USD")


def test_summary_span_ids_drop_unknown() -> None:
    t = _t(block("p1b1", LINE))
    assert v.verify_summary_span_ids(["p1b1", "nope", "p1b1"], t) == ["p1b1"]


def test_quotes_and_values_get_the_transcript_masks() -> None:
    t = _t(block("p1b1", "SSN: 123-45-6789. Reply by October 14, 2026."))
    assert "123-45" not in t.blocks[0].text
    d = demand_out(
        "d1", value_verbatim="123-45-6789", source_quote="SSN: 123-45-6789.", span_ids=["p1b1"]
    )
    flag = red_flag_out(
        "other", "Shows a full SSN.", source_quote="SSN: 123-45-6789", span_ids=["p1b1"]
    )
    out = v.verify_demands([d], t)
    [demand] = out.verified
    assert demand.source_quote == "SSN: ***-**-6789." and demand.value_verbatim == "***-**-6789"
    flags = v.verify_red_flags([flag], t)
    assert flags.flags[0].source_quote == "SSN: ***-**-6789"
    hidden = assemble_transcript(
        [block("p1b1", "Receipt IOE0912345678")], pages_received=1, hide_id_numbers=True
    )
    assert hidden.mask("IOE0912345678") == "IOE••••••5678"


# --- round 2: a fuzzy match never carries changed digits (D-09) --------------------------------

SEND = "Send it by October 15, 2026."


def test_fuzzy_quote_with_a_changed_day_does_not_verify() -> None:
    t = _t(block("p1b1", SEND))
    check = v.verify_span(
        t, ["p1b1"], "Send it by October 16, 2026.", value_verbatim="October 16, 2026"
    )
    assert not check.verified and check.note == v.NOTE_DIGITS_DIFFER
    assert check.confidence is Confidence.low
    assert v.find_quote("Send it by October 16, 2026.", SEND).found is False


def test_fuzzy_quote_with_a_changed_year_does_not_verify() -> None:
    t = _t(block("p1b1", SEND))
    check = v.verify_span(
        t, ["p1b1"], "Send it by October 15, 2027.", value_verbatim="October 15, 2027"
    )
    assert not check.verified and check.note == v.NOTE_DIGITS_DIFFER


def test_fuzzy_quote_with_a_changed_amount_does_not_verify() -> None:
    t = _t(block("p1b1", "You owe $950 today for the filing fee."))
    fuzzy = v.verify_span(
        t, ["p1b1"], "You owe $95 today for the filing fee.", value_verbatim="$95"
    )
    assert not fuzzy.verified and fuzzy.note == v.NOTE_DIGITS_DIFFER
    # a quote that stops inside the printed number is not "exact" either
    cut = v.verify_span(t, ["p1b1"], "You owe $95", value_verbatim="$95")
    assert not cut.verified and cut.note == v.NOTE_DIGITS_DIFFER
    assert v.verify_span(t, ["p1b1"], "You owe $950", value_verbatim="$950").verified


def test_value_must_be_on_the_page_not_only_in_the_quote() -> None:
    t = _t(block("p1b1", SEND))
    # the quote verifies fuzzily (a letter typo) but the value itself is not printed
    check = v.verify_span(
        t, ["p1b1"], "Sent it by October 15, 2026.", value_verbatim="Sent it by October 15"
    )
    assert not check.verified and check.note == v.NOTE_VALUE_NOT_ON_PAGE
    ok = v.verify_span(t, ["p1b1"], "Sent it by October 15, 2026.", value_verbatim="October 15")
    assert ok.verified and ok.note is not None and ok.note.startswith("fuzzy match ")


def test_letter_noise_still_matches_fuzzily() -> None:
    t = _t(block("p1b1", SEND))
    assert v.verify_span(t, ["p1b1"], "Send it by Octobr 15, 2026.").verified
    long_line = "Please return the signed form to our office by October 14, 2026. Thank you 12"
    quote = "Please return the signed form to our ofice by October 14, 2026"
    assert v.find_quote(quote, long_line).found


def test_changed_hearing_date_is_unverified_end_to_end() -> None:
    t = _t(block("p1b1", "Your hearing is on October 30, 2026 at 8:30 AM."))
    wrong = demand_out(
        "d1", value_verbatim="October 1, 2026",
        source_quote="Your hearing is on October 1, 2026 at 8:30 AM.", span_ids=["p1b1"],
        date_text="October 1, 2026",
    )  # fmt: skip
    out = v.verify_demands([wrong], t)
    assert out.verified == [] and len(out.unverified) == 1
    [demand] = out.unverified
    assert demand.verified is False and demand.verification_note == v.NOTE_DIGITS_DIFFER
    assert demand.date is None and demand.reminder_eligible is False


def test_match_key_folds_case_before_the_ocr_map() -> None:
    assert v.find_quote("FILING DEADLINE", "Filing deadline").note == v.NOTE_EXACT
    assert v.find_quote("filing", "FILING").found
    assert v.match_key("BOSIL") == v.match_key("bosil") == v.match_key("80511")
    assert v.match_key("Straße") == v.match_key("STRASSE")


def test_fuzzy_window_off_the_coarse_grid_is_found() -> None:
    """D-09 / BUILD_PLAN §5.3: a quote whose best sliding-window ratio is ≥ 0.92 verifies at
    every offset, not only where the window lands on the coarse ``n // 8`` grid."""
    target = (
        "Please bring your identification documents and proof of address to the interview office"
    )
    quote = (
        target.replace("identification", "identifcaton")
        .replace("address", "adres")
        .replace("interview", "intervew")
    )
    for offset in (1, 2, 11, 12, 21, 22, 31, 32):
        corpus = "x" * offset + " " + target + " " + "y" * 50
        check = v.find_quote(quote, corpus)
        assert check.found, (offset, check)
        assert check.ratio is not None and check.ratio >= v.FUZZY_THRESHOLD
    assert v.fuzzy_ratio(quote, "x " + target + " " + "y" * 50) > 0.93
