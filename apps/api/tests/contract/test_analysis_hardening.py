"""Phase 2B — ``POST /v1/analyze`` hardening through the real pipeline (ScriptedProvider).

Each test pins one audited finding: prose dates checked against the paper, unverified dates in
the banner, the display date preference, agency anti-fraud boilerplate, every model-authored
field through the contact filter, code-only notario flags, and the translated clerk card.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import FastAPI

from proxyhealth_api.ai.provider import Task
from proxyhealth_api.analysis import prose_dates
from proxyhealth_api.contracts.analysis import GlossaryTerm
from proxyhealth_api.contracts.enums import (
    DocumentCategory,
    DocumentType,
    PlanStepKind,
    SenderKind,
)
from proxyhealth_api.contracts.model_out import AnalysisModelOut, PlanStepOut
from proxyhealth_api.settings import Settings
from tests.contract.test_analyze import STORE, analyze, demo_body, install, medicaid_out, result_of

NTA = "nta_hearing_date"
RFE = "uscis_rfe_87d"


def out_of(fid: str, lang: str = "en") -> AnalysisModelOut:
    out = STORE.get(fid).analysis_out(lang)  # type: ignore[union-attr]
    assert out is not None
    return out.model_copy(deep=True)


async def test_invented_dates_in_prose_never_reach_the_reader(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """D-11 / invariant #5: the summary, the demand sentence and the steps may only name the
    paper's dates (the verified value, a printed date, or today)."""
    out = out_of(NTA)
    out.demands[0].text = "Go to the immigration court on October 17, 2026 at 8:30 AM."
    out.summary_body = out.summary_body_en = (
        "This paper starts a case in immigration court. You must appear before a judge on "
        "October 17, 2026. You then have until November 30, 2026 to file your application."
    )
    out.plan_steps.append(
        PlanStepOut(
            id="s9", text="You have 30 days, until November 6, 2026, to send your answer.",
            kind=PlanStepKind.mail, resource_tags=[], span_ids=[], demand_id=None,
        )  # fmt: skip
    )
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body(NTA))
    shown = " ".join(
        [res.summary.body, res.summary.body_en, *(d.text for d in res.demands),
         *(s.text for s in res.plan_steps)]
    )  # fmt: skip
    for invented in ("October 17", "November 30", "November 6"):
        assert invented not in shown, invented
    assert res.demands[0].text == "Go to the immigration court on October 7, 2026 at 8:30 AM."
    assert res.demands[0].value_verbatim == "October 7, 2026" and res.demands[0].verified
    assert res.summary.body.startswith("This paper starts a case in immigration court.")
    assert res.verification.facts_rejected >= 4
    assert res.verification.facts_rejected <= res.verification.facts_checked
    step = next(s for s in res.plan_steps if s.id == "s9")
    assert prose_dates.SEE_PAPER_KEY in step.text or "date on the paper" in step.text


async def test_every_quote_failing_never_says_nothing_to_do(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """D-12: unverified dates may raise urgency up to medium; the RFE banner must not read
    "Nothing to do right now" while the summary states a deadline."""
    out = out_of(RFE)
    for d in out.demands:
        d.source_quote = "Response due 10/13/2026"  # not on the page (a skewed photo)
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body(RFE))
    assert res.demands == [] and len(res.unverified) == len(out.demands)
    assert res.urgency.headline_key == "urgency.medium.unverified_date"
    assert res.urgency.level == "medium" and res.urgency.verify_resource_id == "uscis_contact"


async def test_date_preference_never_moves_a_printed_court_date(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """A Dari reader who picks day-month-year still gets 10/07/2026 = October 7 on an NTA."""
    out = out_of(NTA)
    for b in out.blocks:
        b.text = b.text.replace("October 7, 2026", "10/07/2026")
    for d in out.demands:
        d.source_quote = d.source_quote.replace("October 7, 2026", "10/07/2026")
    out.demands[0].value_verbatim = out.demands[0].date_text = "10/07/2026"
    install(app, settings, analyze_single=lambda kw: out)
    prefs: dict[str, Any] = {"tone": "plain", "calendar_notes": [], "date_format": "dmy"}
    res = await analyze(client, demo_body(NTA, preferences=prefs))
    d1 = next(d for d in res.demands if d.id == "d1")
    assert d1.date is not None and d1.date.value_iso == "2026-10-07"
    assert res.urgency.nearest_date_iso == "2026-10-07"


async def test_agency_anti_fraud_line_keeps_a_real_rfe_an_rfe(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    out = out_of(RFE)
    last = out.blocks[-1]
    line = "Avoid scams: USCIS will never ask you to pay by Western Union, MoneyGram, PayPal, or gift cards."  # noqa: E501
    out.blocks.append(last.model_copy(update={"id": "p1b16", "text": line}))
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body(RFE))
    assert res.document_type == DocumentType.uscis_rfe and res.scam_risk == "none"
    assert res.urgency.verify_resource_id == "uscis_contact"
    assert not any(f.kind.value.startswith("scam") for f in res.red_flags)


async def test_every_model_authored_field_passes_the_contact_filter(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """D-10 / invariant #4: translation, sender line, documents, notes and glossary terms too."""
    out = medicaid_out()
    out.translated_pages[0].text += (
        " For help call 1-866-555-0123 or go to www.medicaid-renew-now.com."
    )
    out.demands[0].documents = [
        "Proof of address: call 1-888-555-0199 or visit www.fast-medicaid-help.com"
    ]
    out.demands[0].ambiguity_note = "Call (202) 555-0147 to confirm."
    out.sender_as_written = "Virginia Medicaid Helpline 1-877-555-0100 www.va-medicaid-fast.com"
    out.glossary.append(GlossaryTerm(term_as_written="www.renewhelp.net", explanation="A site."))
    out.questions_to_ask = ["You qualify for this, right?"]
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body())
    dump = res.model_dump_json()
    for invented in ("555-0123", "medicaid-renew-now", "555-0199", "fast-medicaid-help",
                     "555-0147", "555-0100", "va-medicaid-fast", "renewhelp"):  # fmt: skip
        assert invented not in dump, invented
    assert res.sender_as_written is None and "Medicaid" in res.clerk_message.english
    assert res.demands[0].documents and "Proof of address" in res.demands[0].documents[0]
    assert all("You qualify" not in q for q in res.questions_to_ask)
    assert res.verification.contacts_stripped >= 5


async def test_code_only_notario_gets_the_fixed_card(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """D-20: the scam scorer's notario regex alone brings "A notario is not a lawyer"."""
    out = out_of("scam_gift_card_letter")
    texts = [
        "Maria Lopez, Notario Publico",
        "We prepare your immigration papers quickly.",
        "Call our office for an appointment.",
    ]
    out.blocks = [b.model_copy(update={"text": x}) for b, x in zip(out.blocks, texts, strict=False)]
    out.red_flags, out.demands, out.glossary = [], [], []
    out.sender_as_written, out.sender_kind = "Maria Lopez", SenderKind.unknown
    out.document_type, out.category = DocumentType.other_notice, DocumentCategory.immigration
    out.translated_pages[0].text = "\n".join(texts)
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body("scam_gift_card_letter"))
    assert "scam.notario" in res.scam_reasons
    keys = {f.fixed_copy_key for f in res.red_flags}
    assert "fixed.notario_not_a_lawyer" in keys


async def test_failed_clerk_translation_uses_the_dari_generic_card(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """CL-055(c): a prs reader gets the pack's Dari card around the English need line."""
    provider = install(app, settings, clerk_translate=lambda kw: result_of(None))
    res = await analyze(client, demo_body(target_language="prs"))
    assert Task.clerk_translate in provider.tasks()
    assert res.clerk_message.translated.startswith("سلام. من به")
    assert res.clerk_message.english.startswith("Hello. I speak")
    assert "translation_partial" in res.warnings
