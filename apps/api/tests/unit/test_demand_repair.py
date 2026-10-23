"""``analysis/demand_repair.py`` — deterministic citation repair before §11.2 (D-09 unchanged).

The shapes come from a qwen3.5:4b sweep over the synthetic sample papers: block ids written as
the quote, quotes cited to the wrong block (or to ids beyond the last block), and a sentence cut
at the 120-character ``value_verbatim`` cap. Every repair is checked against the page by the
unchanged ``verify_span``; the adversarial tests below show an unprinted value never verifies.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from proxyhealth_api.ai.failover import AIService
from proxyhealth_api.ai.provider import StructuredResult
from proxyhealth_api.analysis import deadline_rules as dr
from proxyhealth_api.analysis import demand_repair as rep
from proxyhealth_api.analysis import scam as sc
from proxyhealth_api.analysis import verify as v
from proxyhealth_api.analysis.pipeline import run_analysis
from proxyhealth_api.analysis.transcript import Transcript, assemble_transcript
from proxyhealth_api.contracts.analysis import AnalysisResult, AnalyzeRequest, Demand
from proxyhealth_api.contracts.common import TextBlock
from proxyhealth_api.contracts.enums import (
    Confidence,
    DateKind,
    DemandKind,
    DocumentType,
    RedFlagKind,
    ScamRisk,
)
from proxyhealth_api.contracts.model_out import AnalysisModelOut, DemandOut, ExplainOut, RedFlagOut
from proxyhealth_api.settings import DATA_DIR
from tests.golden._fixtures_wp7 import STORE, CountingMock, build_deps, fixture
from tests.unit._fixtures_wp2 import block, demand_out, en_t

# --- papers as the small model transcribed them (coarse blocks) ---------------------------------

RETURN_FORM = (
    "Please complete the Juror Qualification Questionnaire and return it by October 23, 2026."
)
REPORT = "Report date: November 16, 2026 at 8:00 AM, Jury Assembly Room, Sample County Courthouse."
CALL_JURY = "To ask for a new date or an excuse, call the Jury Office at (703) 555-0181."
CONFIRM = "Please confirm or update your address by October 14, 2026."
ORDERED = (
    "YOU ARE ORDERED to appear before an immigration judge at 100 Sample Plaza, Suite 200, "
    "Fairfax, VA 22030 on October 7, 2026 at 8:30 AM."
)
IRS_BOX = (
    "Amount due: $312.45 Pay by: October 26, 2026 If you pay after this date, interest and "
    "penalties may increase the amount you owe. If you already paid or you disagree, call us at "
    "(800) 555-0110."
)
NOTICE = (
    "Aviso para desocupar: el inquilino debe avisar por escrito 60 días antes de terminar el "
    "contrato."
)
LEASE = (
    "Plazo: del 1 de diciembre de 2026 al 30 de noviembre de 2027. Renta mensual: $1,650.00, que "
    f"se paga el día 1 de cada mes. {NOTICE} Teléfono de la oficina: (703) 555-0190"
)
FOOTER = "SAMPLE — synthetic document made for demonstration. Not a real letter."


def _t(*blocks: TextBlock, pages: int = 1) -> Transcript:
    return assemble_transcript(list(blocks), pages_received=pages)


def jury() -> Transcript:
    return _t(
        block("p1b1", "Circuit Court of Sample County, Virginia\nDate: September 25, 2026"),
        block("p1b2", f"SUMMONS FOR JURY SERVICE\nYou are hereby summoned.\n{RETURN_FORM}"),
        block("p1b3", REPORT),
        block("p1b4", f"Answer every question truthfully.\n{CALL_JURY}"),
        block("p1b5", FOOTER),
    )


def medicaid() -> Transcript:
    return _t(
        block("p1b1", "Virginia Department of Medical Assistance Services"),
        block("p1b2", "Date: September 10, 2026"),
        block("p1b3", f"IMPORTANT: Please confirm your address\n{CONFIRM}"),
    )


def id_quoted(
    demand_id: str, sentence: str, span: str, *, kind: DemandKind = DemandKind.deadline, **kw: Any
) -> DemandOut:
    """The sweep's commonest shape: the block id as the quote, the sentence as the value."""
    return demand_out(
        demand_id, kind=kind, value_verbatim=sentence, source_quote=span, span_ids=[span], **kw
    )


def checked(d: DemandOut, t: Transcript) -> tuple[rep.Repair, Any]:
    fixed = rep.repair_demand(d, t)
    return fixed, v.demand_from_out(fixed.demand, t)


def dates_of(demands: list[DemandOut], t: Transcript, doc: DocumentType) -> list[Any]:
    out = rep.repair_demands(demands, t).verify(t)
    ctx = dr.DeadlineContext(document_type=doc, rules=[], today=date(2026, 10, 2), t=en_t())
    return dr.apply_deadline_rules(out.verified, out.sources, ctx, t)


# --- R0 ------------------------------------------------------------------------------------------


def test_noop_when_already_verified() -> None:
    t = jury()
    d = demand_out(
        "d1", value_verbatim="October 23, 2026", source_quote=RETURN_FORM, span_ids=["p1b2"],
        date_text="October 23, 2026", role="response_due",
    )  # fmt: skip
    fixed = rep.repair_demand(d, t)
    assert fixed.demand is d and fixed.codes == () and fixed.original_span_ids == ["p1b2"]
    out = rep.repair_demands([d], t).verify(t)
    assert out.verified[0].verification_note == "exact"
    assert out.verified[0].confidence is Confidence.high


def test_fixture_goldens_are_never_touched() -> None:
    """Every demand of every curated ``out.*.json`` is returned as the same object (R0), and the
    printed-in-the-quote gates on ``amount_text`` / ``time_text`` change none of them."""
    count = 0
    for path in sorted((DATA_DIR / "fixtures").glob("*/out.*.json")):
        data = json.loads(path.read_text("utf-8"))
        if not data.get("demands") or not data.get("blocks"):
            continue
        blocks = [TextBlock.model_validate(b) for b in data["blocks"]]
        t = _t(*blocks, pages=max(b.page for b in blocks))
        for raw in data["demands"]:
            d = DemandOut.model_validate(raw)
            where = (path.parent.name, path.name, d.id)
            fixed = rep.repair_demand(d, t)
            assert fixed.demand is d and fixed.codes == (), where
            assert v.demand_from_out(d, t).amount == v.parse_amount(d.amount_text, d.currency)
            assert not d.time_text or v.check_value(d.time_text, d.source_quote) is None, where
            count += 1
    assert count >= 100


# --- cost: a demand the repair leaves alone is searched once ------------------------------------


def _count_searches(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Count the fuzzy sliding-window searches (``verify._best_window``)."""
    calls = {"n": 0}
    real = v._best_window

    def counted(needle: str, haystack: str) -> tuple[float, int]:
        calls["n"] += 1
        return real(needle, haystack)

    monkeypatch.setattr(v, "_best_window", counted)
    return calls


UNPRINTED = "Please mail the enclosed card back to the clerk before October 23, 2026."
FUZZY = RETURN_FORM.replace("Questionnaire", "Questionaire")


@pytest.mark.parametrize(("quote", "verified"), [(UNPRINTED, False), (FUZZY, True)])
def test_unrepaired_demand_is_searched_once(
    monkeypatch: pytest.MonkeyPatch, quote: str, verified: bool
) -> None:
    """The R0 check is handed on to ``verify_demands``: a quote that fails (and cannot be
    repaired) or verifies fuzzily costs one page search, as it did before the repair."""
    t = jury()
    d = demand_out(
        "d1", value_verbatim="October 23, 2026", source_quote=quote, span_ids=["p1b2", "p1b3"],
        date_text="October 23, 2026", role="response_due",
    )  # fmt: skip
    calls = _count_searches(monkeypatch)
    v.verify_demands([d], t)
    assert calls["n"] == 1
    calls["n"] = 0
    out = rep.repair_demands([d], t).verify(t)
    assert calls["n"] == 1 and len(out.verified) == int(verified)


def _dump(demands: list[Demand]) -> list[dict[str, Any]]:
    return [d.model_dump() for d in demands]


def _same(a: v.VerifiedDemands, b: v.VerifiedDemands) -> bool:
    dump = _dump
    return (
        dump(a.verified) == dump(b.verified) and dump(a.unverified) == dump(b.unverified)
        and (a.facts_checked, a.facts_rejected, a.page_edge_crop, a.sources)
        == (b.facts_checked, b.facts_rejected, b.page_edge_crop, b.sources)
    )  # fmt: skip


def test_handed_on_check_equals_fresh_verification() -> None:
    """For every demand the repair leaves alone (all fixture goldens, and failing shapes it cannot
    fix), the reused R0 check gives exactly what ``verify_demands`` computes from scratch."""
    papers: list[tuple[Transcript, list[DemandOut]]] = []
    for path in sorted((DATA_DIR / "fixtures").glob("*/out.*.json")):
        data = json.loads(path.read_text("utf-8"))
        if data.get("demands") and data.get("blocks"):
            blocks = [TextBlock.model_validate(b) for b in data["blocks"]]
            t = _t(*blocks, pages=max(b.page for b in blocks))
            papers.append((t, [DemandOut.model_validate(raw) for raw in data["demands"]]))
    failing = [
        demand_out("d1", value_verbatim="October 23, 2026", source_quote=UNPRINTED,
                   span_ids=["p1b2"], date_text="October 23, 2026", role="response_due"),
        id_quoted("d2", "Pay $999.00 to the clerk by October 23, 2026.", "p1b2"),
        demand_out("d1", value_verbatim="(703) 555-0181", source_quote=CALL_JURY.replace("1", "7"),
                   span_ids=["p1b4"], kind=DemandKind.contact),
    ]  # fmt: skip
    papers.append((jury(), failing))
    for t, demands in papers:
        repaired = rep.repair_demands(demands, t)
        assert all(not r.codes for r in repaired.repairs)
        assert _same(repaired.verify(t), v.verify_demands(demands, t))
    assert sum(len(ds) for _, ds in papers) >= 100


# --- R1 + R2 -------------------------------------------------------------------------------------


def test_block_id_quote_uses_value_as_quote() -> None:
    """jury_summons d1: ``source_quote="p1b2"``, the printed sentence as the value."""
    t = jury()
    d = id_quoted(
        "d1", RETURN_FORM, "p1b2", kind=DemandKind.document_requested,
        documents=["Juror Qualification Questionnaire"], date_text="October 23, 2026",
        role="response_due",
    )  # fmt: skip
    fixed, demand = checked(d, t)
    assert fixed.codes == (rep.R1_ID_QUOTE, rep.R2_NARROWED)
    assert demand.verified and demand.verification_note == v.NOTE_EXACT
    assert demand.source_quote == RETURN_FORM and demand.span_ids == ["p1b2"]
    assert demand.value_verbatim == "Juror Qualification Questionnaire"
    assert demand.confidence is Confidence.medium, "a repaired fact is never 'high'"
    out = rep.repair_demands([d], t).verify(t)
    assert out.verified[0].verification_note == "exact (repaired: R1, R2)"
    assert out.facts_rejected == 0


def test_block_id_quote_narrows_to_date_text() -> None:
    """medicaid_address_confirmation d1: the value becomes the printed date, which resolves."""
    t = medicaid()
    d = id_quoted("d1", CONFIRM, "p1b3", date_text="October 14, 2026", role="response_due")
    fixed, demand = checked(d, t)
    assert demand.verified and demand.value_verbatim == "October 14, 2026"
    assert demand.source_quote == CONFIRM
    (dated,) = dates_of([d], t, DocumentType.medicaid_renewal)
    assert dated.date is not None and dated.date.kind is DateKind.stated
    assert dated.date.value_iso == "2026-10-14" and dated.reminder_eligible


def test_contact_value_narrowed_to_single_printed_phone() -> None:
    t = jury()
    fixed, demand = checked(id_quoted("d3", CALL_JURY, "p1b4", kind=DemandKind.contact), t)
    assert demand.verified and demand.value_verbatim == "(703) 555-0181"
    assert demand.source_quote == CALL_JURY


def test_two_dates_without_date_text_keeps_sentence_value() -> None:
    moved = "Your hearing moved from October 7, 2026 to November 4, 2026."
    t = _t(block("p1b1", moved))
    d = id_quoted("d1", moved, "p1b1", kind=DemandKind.appointment, role="hearing_date")
    fixed, demand = checked(d, t)
    assert demand.verified and demand.value_verbatim == moved
    assert fixed.codes == (rep.R1_ID_QUOTE,)
    (dated,) = dates_of([d], t, DocumentType.hearing_notice)
    assert dated.date is not None and dated.date.kind is DateKind.unresolved


def test_unprinted_sentence_with_id_quote_stays_rejected() -> None:
    t = jury()
    d = id_quoted(
        "d1", "Pay $999.00 by November 2, 2026.", "p1b2", date_text="November 2, 2026",
        amount_text="$999.00",
    )  # fmt: skip
    fixed, demand = checked(d, t)
    assert fixed.demand is d and fixed.codes == ()
    assert not demand.verified and demand.verification_note == v.NOTE_NOT_FOUND


def test_unprinted_date_text_is_never_the_value() -> None:
    """A ``date_text`` the quote does not hold is skipped; the printed date is used instead."""
    t = medicaid()
    d = id_quoted("d1", CONFIRM, "p1b3", date_text="November 2, 2026", role="response_due")
    fixed, demand = checked(d, t)
    assert demand.verified and demand.value_verbatim == "October 14, 2026"
    (dated,) = dates_of([d], t, DocumentType.medicaid_renewal)
    assert dated.date is not None and dated.date.value_iso == "2026-10-14"


def _digit_bumps(text: str) -> list[str]:
    return [
        text[: m.start()] + str((int(m.group()) + 1) % 10) + text[m.end() :]
        for m in re.finditer(r"\d", text)
    ]


BUMPED = [
    *((s, "p1b2", DemandKind.document_requested) for s in _digit_bumps(RETURN_FORM)),
    *((s, "p1b3", DemandKind.appointment) for s in _digit_bumps(REPORT)),
    *((s, "p1b4", DemandKind.contact) for s in _digit_bumps(CALL_JURY)),
]


@pytest.mark.parametrize(("value", "span", "kind"), BUMPED)
def test_bumped_digit_in_value_stays_rejected(value: str, span: str, kind: DemandKind) -> None:
    """One changed digit anywhere in the model's sentence: never verified, never repaired."""
    t = jury()
    for quote in (span, ""):
        d = demand_out(
            "d1", kind=kind, value_verbatim=value, source_quote=quote, span_ids=[span],
            date_text="October 23, 2026", time_text="8:00 AM",
        )  # fmt: skip
        fixed, demand = checked(d, t)
        assert fixed.demand is d and not demand.verified, value


@pytest.mark.parametrize("field", ["date_text", "amount_text", "relative_rule_text"])
def test_bumped_typed_field_is_never_the_value(field: str) -> None:
    t = _t(block("p1b1", "You may prepay $156.00 by October 9, 2026 instead of coming to court."))
    sentence = "You may prepay $156.00 by October 9, 2026 instead of coming to court."
    kinds = {
        "date_text": DemandKind.deadline, "amount_text": DemandKind.amount,
        "relative_rule_text": DemandKind.relative_deadline,
    }  # fmt: skip
    for bumped in _digit_bumps({"date_text": "October 9, 2026", "amount_text": "$156.00",
                                "relative_rule_text": "by October 9, 2026"}[field]):  # fmt: skip
        d = id_quoted("d1", sentence, "p1b1", kind=kinds[field], **{field: bumped})
        fixed, demand = checked(d, t)
        assert demand.verified, bumped
        assert v.check_value(bumped, demand.value_verbatim) is not None, bumped
        assert v.contains_token(v.match_key(demand.value_verbatim), v.match_key(sentence))


def test_failed_repair_is_all_or_nothing() -> None:
    """R1 applies, R2 narrows, but the sentence is not on the cited page: nothing changes."""
    t = jury()
    d = id_quoted(
        "d1", "Please return the questionnaire by October 23, 2026.", "p1b2",
        date_text="October 23, 2026", confidence=Confidence.high,
    )  # fmt: skip
    fixed, demand = checked(d, t)
    assert fixed.demand is d and fixed.codes == ()
    assert demand.source_quote == "p1b2" and demand.value_verbatim == d.value_verbatim
    assert demand.verification_note == v.demand_from_out(d, t).verification_note
    out = rep.repair_demands([d], t).verify(t)
    assert out.facts_rejected == 1 and out.unverified[0].verification_note == v.NOTE_NOT_FOUND


def test_masks_apply_before_repair() -> None:
    """The page's SSN is masked (§11.1): the model's unmasked copy still matches, and the
    repaired quote never carries the full number."""
    line = "Confirm the number we have on file, 123-45-6789, by October 14, 2026."
    t = _t(block("p1b1", line))
    assert "***-**-6789" in t.blocks[0].text
    d = id_quoted("d1", line, "p1b1", kind=DemandKind.action, role="response_due")
    fixed, demand = checked(d, t)
    assert demand.verified
    assert "123-45" not in fixed.demand.source_quote + fixed.demand.value_verbatim
    assert "***-**-6789" in demand.source_quote


def test_id_tags_with_flags_are_id_only() -> None:
    assert rep.quote_ids("[p1b3|unclear]") == ["p1b3"]
    assert rep.quote_ids("p1b2, p1b3") == ["p1b2", "p1b3"]
    assert rep.quote_ids(" [P1B2] and p1b3; ") == ["p1b2", "p1b3"]
    assert rep.quote_ids("") == [] and rep.quote_ids("   ") == []
    assert rep.quote_ids("See p1b2") is None
    assert rep.quote_ids("Pay by October 9, 2026") is None
    assert rep.quote_ids(" " * 5000 + "x") is None  # linear: no catastrophic backtracking
    t = jury()
    d = id_quoted("d2", REPORT, "p1b3", kind=DemandKind.appointment, date_text="November 16, 2026")
    d = d.model_copy(update={"source_quote": "[p1b3|unclear]", "span_ids": []})
    fixed, demand = checked(d, t)
    assert demand.verified and demand.span_ids == ["p1b3"]
    assert demand.value_verbatim == "November 16, 2026"


def test_value_that_is_itself_an_id_is_not_used() -> None:
    t = jury()
    d = demand_out("d1", value_verbatim="p1b2", source_quote="p1b2", span_ids=["p1b2"])
    assert rep.repair_demand(d, t).demand is d


# --- R4 re-anchoring -----------------------------------------------------------------------------


def irs() -> Transcript:
    return _t(
        block("p1b1", "Department of the Treasury Internal Revenue Service"),
        block("p1b2", "Notice CP14 Tax year 2025 Notice date: September 21, 2026"),
        block("p1b3", "Balance due on your 2025 tax return"),
        block("p1b4", "Our records show you have unpaid taxes for the tax year 2025."),
        block("p1b5", IRS_BOX),
        block("p1b6", "Keep this notice for your records."),
        block("p1b7", FOOTER),
    )


def test_wrong_block_reanchors_to_exact_block() -> None:
    """irs_cp_notice: three exact quotes cited to p1b2, p1b3 and p1b6 all live in p1b5."""
    t = irs()
    demands = [
        demand_out("d1", kind=DemandKind.amount, value_verbatim="$312.45",
                   source_quote="Amount due: $312.45", span_ids=["p1b2"], amount_text="$312.45"),
        demand_out("d2", value_verbatim="October 26, 2026", source_quote="Pay by: October 26, 2026",
                   span_ids=["p1b3"], date_text="October 26, 2026"),
        demand_out("d3", kind=DemandKind.contact, value_verbatim="(800) 555-0110",
                   source_quote="call us at (800) 555-0110", span_ids=["p1b6"]),
    ]  # fmt: skip
    for d in demands:
        fixed, demand = checked(d, t)
        assert fixed.codes == (rep.R4_REANCHORED,) and fixed.original_span_ids == d.span_ids
        assert demand.verified and demand.verification_note == v.NOTE_EXACT
        assert demand.span_ids == ["p1b5"] and demand.page == 1
        assert demand.source_quote == d.source_quote and demand.value_verbatim == d.value_verbatim


def lease() -> Transcript:
    return _t(
        block("p1b1", "Propiedades Los Robles LLC Arlington, Virginia"),
        block("p1b2", "CONTRATO DE ARRENDAMIENTO RESIDENCIAL"),
        block("p1b3", LEASE),
        block("p1b4", FOOTER),
    )


def test_unknown_ids_reanchor_on_same_page() -> None:
    """spanish_lease d4: four blocks transcribed, ``p1b6`` cited, the phone printed in p1b3."""
    t = lease()
    d = id_quoted("d4", "(703) 555-0190", "p1b6", kind=DemandKind.contact)
    fixed, demand = checked(d, t)
    assert demand.verified and demand.span_ids == ["p1b3"]
    assert rep.R4_REANCHORED in fixed.codes and demand.value_verbatim == "(703) 555-0190"


def test_context_expansion_uses_printed_sentence() -> None:
    """R5 (spanish_lease d3): the quote grows from the bare value to its printed sentence."""
    t = lease()
    d = id_quoted("d3", "60 días antes de terminar el contrato.", "p1b5", role="other")
    fixed, demand = checked(d, t)
    assert fixed.codes == (rep.R1_ID_QUOTE, rep.R4_REANCHORED, rep.R5_SENTENCE)
    assert demand.verified and demand.source_quote == NOTICE
    assert demand.value_verbatim == "60 días antes de terminar el contrato."


def test_sentence_with_form_blanks_is_not_the_quote() -> None:
    """R5 skips a line with signature blanks (it is form furniture, not a sentence): the printed
    value stays the quote."""
    line = "Teléfono de la oficina: (703) 555-0190 Firma del inquilino: _______________"
    t = _t(block("p1b1", "CONTRATO DE ARRENDAMIENTO"), block("p1b2", line))
    fixed, demand = checked(id_quoted("d1", "(703) 555-0190", "p1b2", kind=DemandKind.contact), t)
    assert demand.verified and demand.source_quote == "(703) 555-0190"
    assert fixed.codes == (rep.R1_ID_QUOTE,)


def test_reanchor_never_crosses_pages() -> None:
    t = _t(
        block("p1b1", "Page one heading"),
        block("p1b2", "Nothing else here."),
        block("p2b1", "Please pay by October 28, 2026.", page=2),
        pages=2,
    )
    cited_p1 = demand_out(
        "d1", value_verbatim="October 28, 2026", source_quote="Please pay by October 28, 2026.",
        span_ids=["p1b2"], page=2,
    )  # fmt: skip
    fixed, demand = checked(cited_p1, t)
    assert fixed.demand is cited_p1 and not demand.verified
    assert demand.verification_note == v.NOTE_NOT_FOUND
    # Every cited id unknown: the model's own page is searched, and only that page.
    unknown_p1 = cited_p1.model_copy(update={"span_ids": ["p1b9"], "page": 1})
    assert rep.repair_demand(unknown_p1, t).demand is unknown_p1
    unknown_p2 = cited_p1.model_copy(update={"span_ids": ["p2b9"], "page": 2})
    fixed2, demand2 = checked(unknown_p2, t)
    assert demand2.verified and demand2.span_ids == ["p2b1"] and demand2.page == 2
    bad_page = cited_p1.model_copy(update={"span_ids": ["p9b1"], "page": 9})
    assert rep.repair_demand(bad_page, t).demand is bad_page


def test_reanchor_requires_exact() -> None:
    """A quote that only fuzzily matches another block (≥ 0.92) stays rejected."""
    t = _t(
        block("p1b1", "Heading"), block("p1b2", "Please pay the full amount by October 28, 2026.")
    )
    d = demand_out(
        "d1", value_verbatim="October 28, 2026",
        source_quote="Please pay the ful amount by October 28, 2026.", span_ids=["p1b1"],
    )  # fmt: skip
    assert v.verify_span(t, ["p1b2"], d.source_quote).verified, "fuzzy in the right block"
    fixed, demand = checked(d, t)
    assert fixed.demand is d and not demand.verified


def test_reanchor_value_must_still_be_on_page() -> None:
    t = irs()
    d = demand_out(
        "d1", kind=DemandKind.amount, value_verbatim="$312.46",
        source_quote="Amount due: $312.45", span_ids=["p1b2"],
    )  # fmt: skip
    fixed, demand = checked(d, t)
    assert fixed.demand is d and not demand.verified


def test_reanchor_prefers_single_block_then_nearest() -> None:
    line = "Bring this letter to your appointment."
    t = _t(
        block("p1b1", "Bring this"),
        block("p1b2", "letter to your appointment."),
        block("p1b3", line),
        block("p1b4", "Office hours: 9 to 5."),
        block("p1b5", "Questions? Ask at the front desk."),
        block("p1b6", line),
    )
    d = demand_out(
        "d1", kind=DemandKind.action, value_verbatim=line, source_quote=line, span_ids=["p1b5"]
    )
    fixed, demand = checked(d, t)
    assert demand.verified and demand.span_ids == ["p1b6"], "single block, nearest to p1b5"
    first = d.model_copy(update={"span_ids": ["p1b9"]})
    fixed, demand = checked(first, t)
    assert demand.span_ids == ["p1b3"], "no known id: the earliest single block"


def test_reanchor_spans_adjacent_blocks() -> None:
    t = _t(
        block("p1b1", "Heading"),
        block("p1b2", "Please return the signed form"),
        block("p1b3", "by October 14, 2026."),
        block("p1b4", "Thank you."),
    )
    d = demand_out(
        "d1", value_verbatim="October 14, 2026",
        source_quote="Please return the signed form by October 14, 2026.", span_ids=["p1b4"],
    )  # fmt: skip
    fixed, demand = checked(d, t)
    assert demand.verified and demand.span_ids == ["p1b2", "p1b3"]


# --- R3 a value cut at its cap -------------------------------------------------------------------


def nta() -> Transcript:
    return _t(
        block("p1b1", "NOTICE TO APPEAR"),
        block("p1b4", f"{ORDERED}\nYou may be represented in this proceeding."),
        block("p1b5", "Failure to appear: an order of removal may be entered in your absence."),
    )


def test_truncated_value_completes_to_printed_sentence() -> None:
    """nta_hearing_date d1: the value stops at 120 characters, inside "2026"."""
    cut = ORDERED[: rep.VALUE_CAP]
    assert cut.endswith("October 7, 20")
    t = nta()
    d = id_quoted(
        "d1", cut, "p1b4", kind=DemandKind.appointment, date_text="October 7, 2026",
        time_text="8:30 AM", role="hearing_date",
    )  # fmt: skip
    assert not v.demand_from_out(d, t).verified
    fixed, demand = checked(d, t)
    assert fixed.codes == (rep.R1_ID_QUOTE, rep.R2_NARROWED, rep.R3_COMPLETED)
    assert demand.verified and demand.source_quote == ORDERED
    assert demand.value_verbatim == "October 7, 2026"
    (dated,) = dates_of([d], t, DocumentType.nta)
    assert dated.date is not None and dated.date.value_iso == "2026-10-07"
    assert dated.date.time_text == "8:30 AM"


def test_value_cut_inside_a_word_completes_too() -> None:
    """A value cut inside a *word* is a substring of the page but not on it as printed (the D-09
    token test), so R3 still completes it to the printed sentence."""
    sentence = (
        "Bring your passport, your work permit card and every letter you received from the "
        "agency to your interview at the Fairfax office on October 7, 2026."
    )
    cut = sentence[: rep.VALUE_CAP]
    assert cut[-1].isalpha() and sentence[rep.VALUE_CAP].isalpha()
    assert v.find_quote(cut, sentence).found  # an exact substring of the block
    t = _t(block("p1b1", "USCIS"), block("p1b2", sentence))
    d = id_quoted(
        "d1", cut, "p1b2", kind=DemandKind.appointment, date_text="October 7, 2026",
        role="appointment",
    )  # fmt: skip
    fixed, demand = checked(d, t)
    assert fixed.codes == (rep.R1_ID_QUOTE, rep.R2_NARROWED, rep.R3_COMPLETED)
    assert demand.verified and demand.source_quote == sentence
    assert demand.value_verbatim == "October 7, 2026"


def test_truncated_prefix_not_on_page_stays_rejected() -> None:
    other = ORDERED.replace("immigration judge", "administrative judge")[: rep.VALUE_CAP]
    t = nta()
    d = id_quoted("d1", other, "p1b4", kind=DemandKind.appointment, date_text="October 7, 2026")
    assert rep.repair_demand(d, t).demand is d


def test_truncated_prefix_in_two_sentences_stays_rejected() -> None:
    second = ORDERED.replace("8:30 AM", "1:00 PM")
    t = _t(block("p1b4", f"{ORDERED}\n{second}"))
    d = id_quoted(
        "d1", ORDERED[: rep.VALUE_CAP], "p1b4", kind=DemandKind.appointment,
        date_text="October 7, 2026",
    )  # fmt: skip
    assert rep.repair_demand(d, t).demand is d


def test_prefix_shorter_than_40_chars_is_not_completed() -> None:
    long_link = "https://www.example.gov/" + "a" * 120
    t = _t(block("p1b1", f"See {long_link} for details."))
    cut = f"See {long_link}"[: rep.VALUE_CAP]
    assert len(rep.whole_word_prefix(cut)) < rep.MIN_PREFIX_CHARS
    d = id_quoted("d1", cut, "p1b1", kind=DemandKind.action)
    assert rep.repair_demand(d, t).demand is d


def test_value_under_cap_is_never_completed() -> None:
    t = nta()
    short = ORDERED[: rep.VALUE_CAP - 1]  # "…on October 7, 2": not at the cap, so not "cut"
    d = id_quoted("d1", short, "p1b4", kind=DemandKind.appointment, date_text="October 7, 2026")
    assert rep.repair_demand(d, t).demand is d


# --- the pipeline: demands repaired, red flags never (RD-7) --------------------------------------

JURY = "jury_summons"


class CitingMock(CountingMock):
    """The fixture mock, with every demand written the sweep's way (block id as the quote, the
    printed sentence as the value) and, optionally, a payment red flag cited to the wrong block."""

    def __init__(self, settings: Any, *, bad_flag: bool = False) -> None:
        super().__init__(STORE, settings)
        self.bad_flag = bad_flag

    def _rewrite(self, out: BaseModel) -> BaseModel:
        data = out.model_dump()
        for d in data["demands"]:
            d["value_verbatim"], d["source_quote"] = d["source_quote"], d["span_ids"][0]
        if self.bad_flag:
            data["red_flags"] = [*data["red_flags"], {
                "kind": "scam_payment_method", "text": "Asks for a fine.",
                "source_quote": "Failure to return the questionnaire may result in a fine.",
                "span_ids": ["p1b3"], "page": 1,
            }]  # fmt: skip
        return type(out).model_validate(data)

    async def generate_structured(self, **kwargs: Any) -> StructuredResult:
        res = await super().generate_structured(**kwargs)
        if isinstance(res.parsed, AnalysisModelOut | ExplainOut):
            res = StructuredResult(
                self._rewrite(res.parsed), res.raw_text, res.model_id, res.usage,
                res.blocked_reason, res.finish_reason, res.incomplete,
            )  # fmt: skip
        return res


async def _analyze(tmp_path: Path, *, bad_flag: bool = False) -> AnalysisResult:
    deps, _ = build_deps(fixture(JURY), tmp_path)
    deps.ai = AIService(CitingMock(deps.settings, bad_flag=bad_flag), None, deps.settings)
    req = AnalyzeRequest(pages=[], target_language="en", client_platform="web", demo_sample_id=JURY)
    result = await run_analysis(req, deps)
    return AnalysisResult.model_validate(result.model_dump())


def _golden() -> dict[str, Any]:
    path = DATA_DIR / "fixtures" / JURY / "out.en.json"
    data: dict[str, Any] = json.loads(path.read_text("utf-8"))
    return data


async def test_pipeline_repairs_block_id_quotes(tmp_path: Path) -> None:
    result = await _analyze(tmp_path)
    golden = _golden()
    assert result.verification.facts_rejected == 0 and result.unverified == []
    assert [d.value_verbatim for d in result.demands] == [
        d["value_verbatim"] for d in golden["demands"]
    ]
    assert [d.source_quote for d in result.demands] == [
        d["source_quote"] for d in golden["demands"]
    ]
    assert all(d.verification_note == "exact (repaired: R1, R2)" for d in result.demands)
    dated = {d.id: d.date.value_iso for d in result.demands if d.date and d.date.value_iso}
    assert dated == {"d1": "2026-10-23", "d2": "2026-11-16"}
    assert result.urgency.nearest_date_iso == "2026-10-23"


async def test_red_flags_are_not_repaired(tmp_path: Path) -> None:
    """A payment flag whose printed quote sits in another block stays dropped: red flags get R1
    only (an id-only quote), never R4's re-anchoring."""
    result = await _analyze(tmp_path, bad_flag=True)
    assert RedFlagKind.scam_payment_method not in {f.kind for f in result.red_flags}
    assert result.verification.facts_rejected == 1, "the flag, and no demand"
    assert result.scam_risk is ScamRisk.none
    assert all(d.verified for d in result.demands)


# --- red flags: R1 only (integration review, issue 14) -------------------------------------------
# A small model's scam flag citing "p1b2" was rejected, so in a language without scam regexes (vi)
# a gift-card scam scored none. The repaired flag quotes the exact printed text of the one block it
# cites — and never a block holding the SAMPLE footer (every block-id flag of the sweep did). Only
# ``scam_payment_method`` flags: their signal passes the payment screens; impersonation and the
# other kinds do not, so a junk block-id flag on an agency header stays rejected.

GIFT_VI = (
    "Bạn phải trả 500 đô la ngay hôm nay bằng thẻ quà tặng Google Play, nếu không bạn sẽ bị "
    "trục xuất."
)


def scam_paper() -> Transcript:
    return _t(
        block("p1b1", "Sở Di trú Hoa Kỳ"),
        block("p1b2", GIFT_VI),
        block("p1b3", "USCIS will never ask you to pay with gift cards."),
        block("p1b4", f"Pay with Google Play gift cards today.\n{FOOTER}"),
        block("p1b5", FOOTER),
        block("p1b6", "Not a real letter."),
        block("p1b7", "Gọi ngay (202) 555-0147", unclear=True),
    )


def id_flag(quote: str, span_ids: list[str], kind: RedFlagKind = RedFlagKind.scam_payment_method,
            text: str = "Asks for gift cards.") -> RedFlagOut:  # fmt: skip
    return RedFlagOut(kind=kind, text=text, source_quote=quote, span_ids=span_ids, page=1)


@pytest.mark.parametrize(
    ("quote", "span_ids"), [("p1b2", ["p1b2"]), ("[p1b2]", ["p1b2"]), ("p1b2", []),
                            ("[p1b2|unclear]", ["p1b2"])],
)  # fmt: skip
def test_flag_r1_quotes_the_one_cited_block(quote: str, span_ids: list[str]) -> None:
    t = scam_paper()
    f = id_flag(quote, span_ids)
    fixed = rep.repair_red_flag(f, t)
    assert (fixed.source_quote, fixed.span_ids, fixed.page) == (GIFT_VI, ["p1b2"], 1)
    assert (fixed.kind, fixed.text) == (f.kind, f.text), "kind and text stay the model's"
    checked = v.verify_red_flags([fixed], t)
    assert [x.source_quote for x in checked.flags] == [GIFT_VI] and checked.facts_rejected == 0
    assert v.verify_red_flags([f], t).facts_rejected == 1, "unrepaired, it was rejected"


@pytest.mark.parametrize(
    ("quote", "span_ids", "kind"),
    [
        ("p1b5", ["p1b5"], RedFlagKind.scam_payment_method),  # the SAMPLE footer
        ("p1b5", ["p1b5"], RedFlagKind.impersonation),
        ("p1b4", ["p1b4"], RedFlagKind.scam_payment_method),  # a block holding the footer too
        ("p1b6", ["p1b6"], RedFlagKind.impersonation),  # a piece of the footer
        ("p1b7", ["p1b7"], RedFlagKind.scam_payment_method),  # an unclear block
        ("p1b2 p1b3", ["p1b2", "p1b3"], RedFlagKind.scam_payment_method),  # two blocks
        ("p1b2", ["p1b3"], RedFlagKind.scam_payment_method),  # quote and span disagree
        ("p1b2", ["p1b2", "p9b9"], RedFlagKind.scam_payment_method),  # an unknown span too
        ("p9b9", ["p9b9"], RedFlagKind.scam_payment_method),  # no such block
        ("p1b2", ["p1b2"], RedFlagKind.contradiction),  # not a scam kind
        ("p1b2", ["p1b2"], RedFlagKind.other),
        # Scam kinds without the payment screens: a junk block-id impersonation flag on a genuine
        # agency header would score the real paper possible (G1 review).
        ("p1b1", ["p1b1"], RedFlagKind.impersonation),
        ("p1b2", ["p1b2"], RedFlagKind.urgency_pressure),
        ("p1b2", ["p1b2"], RedFlagKind.notario),
        ("p1b2", ["p1b2"], RedFlagKind.fee_for_free_form),
        ("p1b2", ["p1b2"], RedFlagKind.guaranteed_result),
        ("see p1b2", ["p1b2"], RedFlagKind.scam_payment_method),  # words of its own
        ("", ["p1b2"], RedFlagKind.scam_payment_method),
    ],
)
def test_flag_r1_never_repairs_anything_else(
    quote: str, span_ids: list[str], kind: RedFlagKind
) -> None:
    t = scam_paper()
    f = id_flag(quote, span_ids, kind)
    assert rep.repair_red_flag(f, t) is f
    assert v.verify_red_flags([f], t).flags == []


def test_flag_r1_leaves_the_sentinel_and_quoted_flags_alone() -> None:
    t = scam_paper()
    sentinel = id_flag("p1b2", ["p1b2"], RedFlagKind.other, v.MULTIPLE_DOCUMENTS_SENTINEL)
    quoted = id_flag(GIFT_VI, ["p1b2"])
    assert rep.repair_red_flags([sentinel, quoted], t) == [sentinel, quoted]


def test_a_repaired_anti_fraud_block_still_neither_shows_nor_scores() -> None:
    """The screens run on the repaired quote exactly as on a typed one."""
    fixed = rep.repair_red_flag(id_flag("p1b3", ["p1b3"]), scam_paper())
    assert fixed.source_quote == "USCIS will never ask you to pay with gift cards."
    assert sc.is_anti_fraud_quote(fixed.source_quote)
    assert not sc.payment_flag_has_evidence(fixed.source_quote)
