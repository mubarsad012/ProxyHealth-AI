"""Phase 2B — ``POST /v1/analyze`` hardening through the real pipeline (ScriptedProvider).

Each test pins one audited finding: prose dates checked against the paper, unverified dates in
the banner, the display date preference, agency anti-fraud boilerplate, every model-authored
field through the contact filter, code-only notario flags, and the translated clerk card.
"""

from __future__ import annotations

import functools
from typing import Any

import httpx
from fastapi import FastAPI

from proxyhealth_api.ai.provider import Task
from proxyhealth_api.analysis import clerk, prose_dates
from proxyhealth_api.analysis.i18n import english_translator
from proxyhealth_api.contracts.analysis import GlossaryTerm
from proxyhealth_api.contracts.enums import (
    DocumentCategory,
    DocumentType,
    PlanStepKind,
    RedFlagKind,
    SenderKind,
)
from proxyhealth_api.contracts.model_out import AnalysisModelOut, PlanStepOut, RedFlagOut
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


# --- Local-model sweep (qwen3.5:4b, 2026-10): prose shape faults mended in code -----------------


async def test_failing_definitions_and_steps_are_dropped_not_rewritten(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """§11.9: "The paper says …" on a definition or a suggested step would put words in the
    paper's mouth ("The paper says a judge made a decision that you must leave the country")."""
    out = out_of(NTA)
    out.glossary.append(GlossaryTerm(
        term_as_written="order of removal",
        explanation="a decision by the judge that you must leave the country.",
    ))  # fmt: skip
    kept = GlossaryTerm(term_as_written="Notice to Appear", explanation="A paper from a court.")
    out.glossary.append(kept)
    for i, text in enumerate([
        "Find out if you can get a fee waiver so you do not have to pay for the hearing.",
        "If the paper says it is a sample, do not pay or go to court.",
    ]):  # fmt: skip
        out.plan_steps.append(PlanStepOut(
            id=f"s{9 + i}", text=text, kind=PlanStepKind.ask, resource_tags=[], span_ids=[],
            demand_id=None,
        ))  # fmt: skip
    provider = install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body(NTA))
    assert "order of removal" not in {g.term_as_written for g in res.glossary}
    assert kept in res.glossary
    assert not {"s9", "s10"} & {s.id for s in res.plan_steps}
    assert Task.phrasing_rewrite not in provider.tasks()
    assert res.verification.phrasing_rewrites == 3


async def test_plan_steps_name_the_professional_that_fits_the_paper(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """§8.4: no DOJ-accredited representative on a hospital bill; no copied "Before that date,"."""
    t = english_translator()
    bill = out_of("inova_final_notice")
    bill.plan_steps[-1].text = (
        "Before October 28, 2026, talk to a licensed lawyer or a DOJ-accredited representative "
        "about the bill."
    )
    install(app, settings, analyze_single=lambda kw: bill)
    res = await analyze(client, demo_body("inova_final_notice"))
    assert res.plan_steps[-1].text == t("chat.refer.clinician")
    assert "DOJ" not in " ".join(s.text for s in res.plan_steps)

    jury = out_of("jury_summons")
    jury.plan_steps[-1].text = "Before that date, talk to a licensed lawyer about jury duty."
    install(app, settings, analyze_single=lambda kw: jury)
    res = await analyze(client, demo_body("jury_summons"))
    assert res.plan_steps[-1].text == "Talk to a licensed lawyer about jury duty."


async def test_a_cut_title_and_its_continued_body_are_mended(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    out = out_of("jury_summons")
    court = "This is a summons from the Circuit Court of Sample County, Virginia"
    out.summary_title = f"{court}, asking you"
    out.summary_body = "to appear for jury service and to return a questionnaire."
    out.summary_body_en = out.summary_title
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body("jury_summons"))
    assert res.summary.title == f"{court}…"
    assert res.summary.body == res.summary.body_en == (
        f"{out.summary_title} to appear for jury service and to return a questionnaire."
    )


def _recorded(out: AnalysisModelOut, kw: dict[str, Any]) -> AnalysisModelOut:
    return out


async def test_an_english_reader_gets_one_english_body(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """For an English target ``body`` and ``body_en`` are the same text (AI_PROMPTS §4)."""
    base = out_of(NTA)
    title, body = base.summary_title, base.summary_body
    cases = [
        (body, title, body),  # body_en only repeats the title
        (body, f"{title}. {body}", body),  # body_en opens with the title
        ("Este papel es de la corte de inmigración y le pide ir a una audiencia.", body, body),
    ]
    for model_body, model_body_en, shown in cases:
        out = base.model_copy(update={"summary_body": model_body,
                                      "summary_body_en": model_body_en}, deep=True)  # fmt: skip
        install(app, settings, analyze_single=functools.partial(_recorded, out))
        res = await analyze(client, demo_body(NTA))
        assert res.summary.body == res.summary.body_en == shown, (model_body, model_body_en)


async def test_an_unreadable_papers_summary_gets_the_same_repairs(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    fid = "blurry_unreadable_page"
    out = out_of(fid)
    body = f"{out.summary_body} SSN 123-45-6789."
    out.summary_body, out.summary_body_en = body, f"{out.summary_title}. {out.summary_body}"
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body(fid))
    assert not res.quality.readable
    assert res.summary.body == res.summary.body_en == body.replace("123-45-6789", "***-**-6789")


async def test_a_non_english_readers_bodies_are_left_as_written(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    out = out_of(NTA, "es")
    english = out_of(NTA).summary_body_en
    out.summary_body_en = f"{out.summary_title}. {english}"
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body(NTA, target_language="es"))
    assert res.summary.body_en == out.summary_body_en and res.summary.body == out.summary_body


async def test_hide_id_numbers_reaches_model_prose(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    """D-19: the masks reach steps, the clerk line, the translation and the summary too."""
    fid = "uscis_i797c_receipt_i765"
    out = out_of(fid)
    out.plan_steps[0].text = "Write down the receipt number IOE0912345678 and A 123-456-789."
    out.clerk_need_en = "keeping the receipt notice IOE0912345678 for A 123-456-789"
    out.translated_pages[0].text += "\nA-Number: A 123-456-789"
    out.summary_body_en = out.summary_body = f"{out.summary_body} Your receipt is IOE0912345678."
    out.glossary.append(GlossaryTerm(term_as_written="IOE0912345678", explanation="A number."))
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body(fid, hide_id_numbers=True))
    dump = res.model_dump_json()
    assert "0912345678" not in dump and "123-456-789" not in dump
    assert "IOE••••••5678" in res.plan_steps[0].text and "A•••••6789" in res.plan_steps[0].text
    assert "IOE••••••5678" in res.clerk_message.english
    assert res.clerk_message.need_line_source == "ai"
    assert "A•••••6789" in res.translated_text[0].text
    assert "IOE••••••5678" in res.summary.body and "IOE••••••5678" in res.summary.body_en

    shown = await analyze(client, demo_body(fid))  # receipt numbers stay visible when off
    assert "IOE0912345678" in shown.plan_steps[0].text


async def test_ssns_in_model_prose_are_always_masked(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    out = medicaid_out()
    out.translated_pages[0].text += "\nSSN 123-45-6789"
    out.summary_body = out.summary_body_en = f"{out.summary_body} Your SSN is 123-45-6789."
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body())
    assert "123-45-6789" not in res.model_dump_json()
    assert "***-**-6789" in res.translated_text[0].text and "***-**-6789" in res.summary.body


async def test_the_clerk_line_drops_the_copied_prefix_and_the_prompts_example(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    out = out_of(RFE)
    out.clerk_need_en = "I need help with: sending the papers before October 13, 2026"
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body(RFE))
    assert "I need help with: sending the papers before October 13, 2026." in (
        res.clerk_message.english
    )
    assert res.clerk_message.english.count("I need help with") == 1

    out.clerk_need_en = f"I need help with: {clerk.PROMPT_EXAMPLE_NEED}"  # October 14: unprinted
    res = await analyze(client, demo_body(RFE))
    assert res.clerk_message.need_line_source == "template"
    assert "October 14" not in res.clerk_message.english


async def test_missing_pages_and_repeated_flags_are_settled_in_code(
    app: FastAPI, client: httpx.AsyncClient, settings: Settings
) -> None:
    out = out_of(RFE)
    quoted = out.blocks[0]
    out.red_flags = [
        RedFlagOut(kind=RedFlagKind.missing_pages, text="Pages may be missing.",
                   source_quote=quoted.text.splitlines()[0], span_ids=[quoted.id], page=1),
        *[RedFlagOut(kind=RedFlagKind.contradiction, text="Two dates disagree.",
                     source_quote=quoted.text.splitlines()[0], span_ids=[quoted.id], page=1)
          for _ in range(2)],
    ]  # fmt: skip
    install(app, settings, analyze_single=lambda kw: out)
    res = await analyze(client, demo_body(RFE))
    kinds = [f.kind for f in res.red_flags]
    assert RedFlagKind.missing_pages not in kinds and kinds.count(RedFlagKind.contradiction) == 1
