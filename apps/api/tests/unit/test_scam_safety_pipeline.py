"""Scam and emergency safety end to end (integration review G1, issues 5, 11-14, 16-18).

Each test is one reviewer reproduction: a crafted small-model reading goes through
``run_analysis`` as a real upload (``openai_compat``, local tier — never a sample) or as a sample
paper (``demo_sample_id``). The fake provider answers every task itself (``tag`` when a test gives
one; rewrite and clerk translation are unavailable, so the fixed fallbacks apply): no network, no
model. Synthetic strings only. Rules held: DOCUMENT_TAXONOMY §6.4 (on a possible or likely scam
nothing sends the reader to the paper's own contact), D-14 (no emergency false negative on a real
upload; a sample's junk tag adds no crisis card), D-13 (scam status from code evidence)."""

from __future__ import annotations

import base64
import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import BaseModel

from proxyhealth_api.ai.failover import AIService
from proxyhealth_api.ai.mock import MockProvider
from proxyhealth_api.ai.provider import StructuredResult, Task, Usage
from proxyhealth_api.analysis.pipeline import PipelineDeps, run_analysis
from proxyhealth_api.contracts.analysis import AnalysisResult, AnalyzeRequest
from proxyhealth_api.contracts.common import TextBlock
from proxyhealth_api.contracts.enums import (
    Confidence,
    DemandKind,
    DocumentCategory,
    DocumentType,
    PlanStepKind,
    Provider,
    RedFlagKind,
    ResourceTag,
    ScamRisk,
    SenderKind,
)
from proxyhealth_api.contracts.model_out import (
    AnalysisModelOut,
    DemandOut,
    PlanStepOut,
    RedFlagOut,
    TaggingModelOut,
)
from proxyhealth_api.demo.fixtures import FixtureStore
from proxyhealth_api.resources.loader import ResourceRepo
from proxyhealth_api.resources.rules_repo import RulesRepo
from proxyhealth_api.settings import DATA_DIR
from tests.conftest import make_settings
from tests.unit._fixtures_wp2 import en_t

STORE = FixtureStore.load(DATA_DIR / "fixtures")
RESOURCES = ResourceRepo.load(DATA_DIR / "resources")
RULES = RulesRepo.load(DATA_DIR / "rules")
SCAM = "scam_gift_card_letter"
MEDICAID = "medicaid_address_confirmation"
SCAMMER = "(202) 555-0147"
DT, DC, SK, RT = DocumentType, DocumentCategory, SenderKind, ResourceTag


def _page() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (1200, 1600), "white").save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


PAGE = _page()


class Fake(MockProvider):
    """Answers ``analyze_single`` with ``analysis`` and ``tag`` with ``tag`` (else nothing)."""

    def __init__(self, settings: Any, analysis: AnalysisModelOut,
                 tag: TaggingModelOut | None = None) -> None:  # fmt: skip
        super().__init__(STORE, settings)
        self.name = Provider.openai_compat
        self.reading, self.tag = analysis, tag
        self.tasks: list[Task] = []

    async def generate_structured(self, **kwargs: Any) -> StructuredResult:
        task = kwargs["task"]
        self.tasks.append(task)
        answer: BaseModel | None = {Task.analyze_single: self.reading, Task.tag: self.tag}.get(task)
        if answer is None:
            return StructuredResult(None, None, "fake", Usage(), finish_reason="stop")
        return StructuredResult(answer, None, "fake", Usage(1, 1), finish_reason="stop")


async def analyze(
    tmp_path: Path,
    out: AnalysisModelOut,
    *,
    sample: str | None = None,
    tag: TaggingModelOut | None = None,
) -> tuple[AnalysisResult, list[Task]]:
    settings = make_settings(
        tmp_path, ai_provider="openai_compat", openai_compat_data_tier="local",
        openai_compat_model_label="Qwen", openai_compat_base_url="http://127.0.0.1:9/v1",
    )  # fmt: skip
    provider = Fake(settings, out, tag)
    deps = PipelineDeps(
        settings=settings, ai=AIService(provider, None, settings), resources=RESOURCES,
        rules=RULES, fixtures=STORE, request_id="g1-test", data_use_tier=settings.data_use_tier,
        clock=lambda: datetime(2026, 10, 22, 15, 0, tzinfo=UTC),
    )  # fmt: skip
    if sample:
        req = AnalyzeRequest(pages=[], target_language="en", client_platform="web",
                             demo_sample_id=sample, state="VA")  # fmt: skip
    else:
        req = AnalyzeRequest(pages=[{"mime_type": "image/png", "data_base64": PAGE}],
                             target_language="en", client_platform="web", state="VA")  # fmt: skip
    result = await run_analysis(req, deps)
    return AnalysisResult.model_validate(result.model_dump()), provider.tasks


def fixture_out(fid: str = SCAM) -> AnalysisModelOut:
    fx = STORE.get(fid)
    assert fx is not None
    out = fx.analysis_out("en")
    assert out is not None
    return out.model_copy(deep=True)


def blocks(*texts: str) -> list[TextBlock]:
    n = len(texts)
    return [
        TextBlock(id=f"p1b{i}", page=1, text=text,
                  bbox=[0.08, 0.05 + 0.8 * (i - 1) / n, 0.9, 0.08 + 0.8 * (i - 1) / n],
                  is_handwriting=False, is_unclear=False)  # fmt: skip
        for i, text in enumerate(texts, 1)
    ]


def variant(texts: list[str], *, dtype: DocumentType = DT.other_notice,
            category: DocumentCategory = DC.other, sender: SenderKind = SK.unknown,
            lang: str = "en", flags: list[RedFlagOut] | None = None, likely: bool = False,
            signals: list[str] | None = None, tags: list[str] | None = None,
            forms: list[str] | None = None, confidence: Confidence = Confidence.medium,
            ) -> AnalysisModelOut:  # fmt: skip
    """A one-page reading of ``texts`` on the Medicaid fixture's frame (no demands, one step)."""
    return fixture_out(MEDICAID).model_copy(update={
        "blocks": blocks(*texts), "document_type": dtype, "document_type_confidence": confidence,
        "category": category, "sender_kind": sender, "sender_as_written": texts[0],
        "red_flags": flags or [], "demands": [], "scam_signals": signals or [],
        "is_likely_scam": likely, "detected_language": lang, "resource_tags": tags or [],
        "emergency_terms_found": [], "summary_span_ids": [], "institutions_as_written": [],
        "form_numbers": forms or [], "translated_pages": [], "glossary": [],
        "questions_to_ask": [], "summary_title": "A letter", "summary_body": "A letter.",
        "summary_body_en": "A letter.",
        "plan_steps": [PlanStepOut(id="s1", text="Keep this paper.", kind=PlanStepKind.gather,
                                   resource_tags=[], span_ids=[], demand_id=None)],
    })  # fmt: skip


def payment_flag(quote: str, span: str = "p1b2") -> RedFlagOut:
    return RedFlagOut(kind=RedFlagKind.scam_payment_method, text="Asks for gift cards.",
                      source_quote=quote, span_ids=[span], page=1)  # fmt: skip


def preview(result: AnalysisResult) -> list[str]:
    return [p.resource.id for p in result.resource_preview]


def step(sid: str, text: str, kind: PlanStepKind, span: str = "p1b8") -> PlanStepOut:
    return PlanStepOut(id=sid, text=text, kind=kind, resource_tags=[], span_ids=[span],
                       demand_id=None)  # fmt: skip


# --- issue 12: a scam's printed phone never becomes the "Verify this date" target ----------------


async def test_a_scams_printed_phone_is_never_the_verify_target(tmp_path: Path) -> None:
    """review/scam_contact.py: a small model's block-id contact and pay-by demands on the scam
    letter verify after repair (R1, R2); the re-typed other_notice has no agency line, so an empty
    verify target made the client dial the first printed phone — the scammer's."""
    out = fixture_out()
    out.blocks[6].text = (
        "Pay by October 25, 2026 with Google Play gift cards or you will be deported."
    )
    common: dict[str, Any] = {
        "time_text": None, "relative_rule_text": None, "anchor_span_id": None,
        "amount_text": None, "currency": None, "documents": [], "confidence": Confidence.high,
        "ambiguity_note": None, "page": 1,
    }
    out.demands += [
        DemandOut(id="d2", kind=DemandKind.contact, text="Call the officer.",
                  value_verbatim=out.blocks[7].text[:120], source_quote="p1b8",
                  span_ids=["p1b8"], date_text=None, role="contact", **common),
        DemandOut(id="d3", kind=DemandKind.deadline, text="Pay by October 25, 2026.",
                  value_verbatim=out.blocks[6].text, source_quote="p1b7", span_ids=["p1b7"],
                  date_text="October 25, 2026", role="payment_due", **common),
    ]  # fmt: skip
    result, _ = await analyze(tmp_path, out)
    assert result.scam_risk is ScamRisk.likely and result.document_type is DT.other_notice
    contact = [d for d in result.demands if d.kind is DemandKind.contact]
    assert contact and contact[0].verified and "555-0147" in contact[0].value_verbatim
    assert result.urgency.driving_demand_id == "d3"
    assert result.urgency.verify_resource_id == "dhs_oig", "the scam card's line, never the paper's"
    assert all("555-0147" not in s.text for s in result.plan_steps)


# --- issue 13 (D-14): a real upload keeps the model's crisis/poison tag; a sample's junk does not -

HT_SCHOOL = [
    "Lekòl Elemantè Riverside", "Avi pou paran yo",
    "Pitit ou a te di yon pwofesè li vle touye tèt li. Tanpri rele nou jodi a.",
]  # fmt: skip


async def test_a_real_uploads_crisis_tag_brings_the_emergency_card(tmp_path: Path) -> None:
    """review/e2e4.py: a Haitian Creole school letter no lexicon covers, model tag crisis."""
    out = variant(HT_SCHOOL, category=DC.school, sender=SK.school, lang="ht", tags=["crisis"])
    result, _ = await analyze(tmp_path, out)
    assert result.safety.emergency and result.urgency.level.value == "emergency"
    assert result.resource_tags[0] is RT.crisis and "988" in preview(result)


async def test_a_samples_junk_crisis_tag_adds_no_crisis_card(tmp_path: Path) -> None:
    out = variant(["Riverside Elementary", "Picture day is Friday."], category=DC.school,
                  sender=SK.school, tags=["crisis", "poison"])  # fmt: skip
    result, _ = await analyze(tmp_path, out, sample=MEDICAID)
    assert not result.safety.emergency
    assert not {RT.crisis, RT.poison} & set(result.resource_tags)
    assert "988" not in preview(result)


async def test_a_real_uploads_poison_tag_stays_without_an_emergency(tmp_path: Path) -> None:
    """review/e2e2.py: a Tagalog label ("tumawag agad sa Poison Control"), model tag poison."""
    out = variant(["Klinika", "Kung nakalunok ang bata ng gamot na ito, tumawag agad sa Poison "
                   "Control."], dtype=DT.prescription_label, category=DC.medical,
                  sender=SK.pharmacy, lang="tl", tags=["poison"],
                  confidence=Confidence.high)  # fmt: skip
    result, _ = await analyze(tmp_path, out)
    assert not result.safety.emergency
    assert RT.poison in result.resource_tags and "poison" in preview(result)


# --- issue 14: the model's scam signal survives where code evidence is missing ------------------

VI_GIFT = ("Bạn phải trả 500 đô la ngay hôm nay bằng thẻ quà tặng Google Play, nếu không bạn sẽ "
           "bị trục xuất.")  # fmt: skip


async def test_a_block_id_payment_flag_is_repaired_on_a_real_upload(tmp_path: Path) -> None:
    """review/vi_id.py: Vietnamese has no scam regexes; the flag's quote was "p1b2"."""
    for quote in (VI_GIFT, "p1b2", "[p1b2]"):
        out = variant(["Sở Di trú Hoa Kỳ", VI_GIFT], category=DC.immigration, lang="vi",
                      flags=[payment_flag(quote)])  # fmt: skip
        result, _ = await analyze(tmp_path, out)
        assert result.scam_risk is ScamRisk.likely, quote
        shown = [f for f in result.red_flags if f.kind is RedFlagKind.scam_payment_method]
        assert [f.source_quote for f in shown] == [VI_GIFT], quote
        assert result.resource_tags[0] is RT.scam_report


async def test_a_block_id_flag_on_the_sample_footer_stays_rejected(tmp_path: Path) -> None:
    footer = "SAMPLE — synthetic document made for demonstration. Not a real letter."
    out = variant(["Sở Di trú Hoa Kỳ", footer], category=DC.immigration, lang="vi",
                  flags=[payment_flag("p1b2")])  # fmt: skip
    for sample in (None, MEDICAID):
        result, _ = await analyze(tmp_path, out, sample=sample)
        assert result.scam_risk is ScamRisk.none and result.red_flags == [], sample
        assert result.verification.facts_rejected >= 1


DARI = ("هرگز این نامه را به کسی نشان ندهید و امروز ۳۰۰ دالر را با کارت های گوگل پلی پرداخت کنید، "
        "وگرنه برق شما قطع می‌شود.")  # fmt: skip


async def test_a_dari_never_word_is_no_anti_fraud_line(tmp_path: Path) -> None:
    """review/prs_neg.py: "Never show this letter to anyone and pay … with Google Play cards" read
    as anti-fraud boilerplate silenced the regex and dropped the model's flag and scam_report tag
    (previews: fairfax_csp/liheap/211, aila/eoir_roster/ayuda)."""
    cases = [(["شرکت برق دومینیون", "اخطار نهایی", DARI], SK.utility, DT.utility_shutoff,
              DC.housing, ScamRisk.possible),
             (["اداره مهاجرت ایالات متحده", "اخطار نهایی", DARI], SK.federal_agency,
              DT.other_notice, DC.immigration, ScamRisk.likely)]  # fmt: skip
    for texts, sender, dtype, category, risk in cases:
        out = variant(texts, dtype=dtype, category=category, sender=sender, lang="prs",
                      flags=[payment_flag(DARI, "p1b3")], likely=True,
                      tags=["scam_report"])  # fmt: skip
        result, _ = await analyze(tmp_path, out)
        assert result.scam_risk is risk and "scam.gift_card" in result.scam_reasons, sender
        assert "dhs_oig" in preview(result), (sender, preview(result))


async def test_the_models_own_scam_verdict_keeps_its_scam_report_tag(tmp_path: Path) -> None:
    """Option 3 of the issue: no code evidence at all (the flag quotes words the paper does not
    print), but the model called the paper a scam: on a real upload its tag stands; on a sample —
    where the SAMPLE footer made a small model call every paper fake — it does not."""
    out = variant(["Sở Di trú Hoa Kỳ", VI_GIFT], category=DC.immigration, lang="vi",
                  flags=[payment_flag("Trả bằng thẻ quà tặng")], likely=True,
                  signals=["scam.gift_card"], tags=["scam_report"])  # fmt: skip
    real, _ = await analyze(tmp_path, out)
    assert real.scam_risk is ScamRisk.none and RT.scam_report in real.resource_tags
    sample, _ = await analyze(tmp_path, out, sample=MEDICAID)
    assert RT.scam_report not in sample.resource_tags


# --- issues 16 and 18: plan steps on the scam letter --------------------------------------------


async def test_no_scam_step_sends_the_reader_to_the_papers_contact(tmp_path: Path) -> None:
    """review/scam_steps.py: "The office that sent this paper can tell you more. Call Officer
    Daniel Sample at (202) 555-0147." (professional) and "Check whether the letter is real by
    calling (202) 555-0147." (verify) both survived on a likely scam; on the in-app demo "Ask
    USCIS whether this is a real letter before you pay." was dropped as the footer's claim."""
    out = fixture_out()
    out.plan_steps = [
        step("s1", f"The office that sent this paper can tell you more. Call Officer Daniel "
                   f"Sample at {SCAMMER}.", PlanStepKind.professional),
        step("s2", f"Check whether the letter is real by calling {SCAMMER}.", PlanStepKind.verify),
        step("s3", "Ask USCIS whether this is a real letter before you pay.", PlanStepKind.verify,
             "p1b1"),
        step("s4", "Call the number on the letter to ask whether it is real.",
             PlanStepKind.verify),
        step("s5", "If the paper says it is a sample, do not pay.", PlanStepKind.verify, "p1b1"),
    ]  # fmt: skip
    out.questions_to_ask = ["Who signed this letter?", "Why must I pay with gift cards?"]
    referral = en_t()("chat.refer.lawyer_or_accredited_rep")
    for sample in (None, SCAM):
        result, _ = await analyze(tmp_path, out.model_copy(deep=True), sample=sample)
        assert result.scam_risk is ScamRisk.likely
        texts = {s.id: s.text for s in result.plan_steps}
        assert all("555-0147" not in x and "number on the letter" not in x
                   for x in texts.values()), texts  # fmt: skip
        assert texts["s1"] == referral, texts
        assert texts["s3"] == "Ask USCIS whether this is a real letter before you pay.", sample
        assert "s5" not in texts or sample is None, "the footer's own claim goes on a sample"
        assert result.questions_to_ask == [], "no questions for the scammer (§6.4)"


async def test_a_real_papers_steps_keep_their_printed_contact(tmp_path: Path) -> None:
    out = fixture_out("va_pay_or_quit_14d")
    out.plan_steps.append(step("s9", "Call the leasing office at (703) 555-0175 with questions.",
                               PlanStepKind.call, "p1b10"))  # fmt: skip
    result, _ = await analyze(tmp_path, out)
    assert result.scam_risk is ScamRisk.none
    assert any("(703) 555-0175" in s.text for s in result.plan_steps)


# --- issue 17: a fake form label never upgrades a possible scam to the agency type --------------


async def test_a_fake_i797c_label_on_a_possible_scam_stays_other_notice(tmp_path: Path) -> None:
    """review/e2e3.py i797c_possible: the agency's fixed card and type pins pushed the
    scam-report help out of the preview."""
    texts = [
        "Form I-797C, Notice of Action", "Receipt Notice",
        "U.S. Citizenship and Immigration Services",
        "Your I-765 case is on hold. Check status at www.uscis-case-help.example.com",
    ]  # fmt: skip
    out = variant(texts, category=DC.immigration, sender=SK.federal_agency, likely=True,
                  signals=["impersonation", "non_gov_domain"], tags=["scam_report"],
                  forms=["I-797C", "I-765"])  # fmt: skip
    result, _ = await analyze(tmp_path, out)
    assert result.scam_risk is ScamRisk.possible
    assert result.document_type is DT.other_notice and result.category is DC.immigration
    assert "fixed.uscis_receipt_i765" not in {f.fixed_copy_key for f in result.red_flags}
    assert result.urgency.verify_resource_id is None
    assert "dhs_oig" in preview(result)


# --- issue 5: a model list the gates empty still gets the one tag call --------------------------


async def test_a_sensitive_only_model_list_still_gets_the_tag_call(tmp_path: Path) -> None:
    """review/e2e.py 'tagging': model tags ['scam_report'] on a collections letter with no scam
    evidence skipped the tag call and ended with no tags at all."""
    texts = ["Sample Collections LLC", "Your account 4455 is past due. Please call us."]
    tag = TaggingModelOut(tags=["benefits_navigation"], geo_state=None, geo_county=None,
                          geo_city=None, geo_zip=None, institutions_as_written=[],
                          emergency=False)  # fmt: skip
    for model in (["scam_report"], []):
        out = variant(texts, confidence=Confidence.high, tags=model)
        result, tasks = await analyze(tmp_path, out, sample=MEDICAID, tag=tag)
        assert Task.tag in tasks, model
        assert result.resource_tags == [RT.benefits_navigation], model


# --- issue 11: a payment flag naming no method on a paper scored none ---------------------------


async def test_a_methodless_payment_flag_on_a_real_bill_neither_shows_nor_tags(
    tmp_path: Path,
) -> None:
    """replay va_pay_or_quit_14d: the model's own negation ("It does not ask for gift cards")
    quoting the landlord's payment line was shown first with a danger icon and backed a
    scam_report tag."""
    out = fixture_out("va_pay_or_quit_14d")
    out.red_flags.append(RedFlagOut(
        kind=RedFlagKind.scam_payment_method,
        text="This paper says to pay at the leasing office or call a phone number. It does not "
             "ask for gift cards, wire transfers, or crypto.",
        source_quote="Pay at the leasing office or call (703) 555-0175 with questions.",
        span_ids=["p1b10"], page=1,
    ))  # fmt: skip
    out.resource_tags = ["scam_report", *out.resource_tags]
    result, _ = await analyze(tmp_path, out)
    assert result.scam_risk is ScamRisk.none
    assert RedFlagKind.scam_payment_method not in {f.kind for f in result.red_flags}
    assert RT.scam_report not in result.resource_tags
    assert result.verification.facts_rejected >= 1


# --- G1 review: false scam evidence on genuine papers -------------------------------------------

RFE = [
    "U.S. Citizenship and Immigration Services", "Request for Evidence", "Form I-485",
    "Submit the evidence listed below by January 12, 2027.",
    "Mail your response to the address on this notice: USCIS, P.O. Box 660867, Dallas, TX 75266.",
    "Call the USCIS Contact Center at 800-375-5283 with questions.",
]  # fmt: skip


def rfe_out(flags: list[RedFlagOut]) -> AnalysisModelOut:
    out = variant(RFE, dtype=DT.uscis_rfe, category=DC.immigration, sender=SK.federal_agency,
                  flags=flags, tags=["immigration_legal_help"], forms=["I-485"],
                  confidence=Confidence.high)  # fmt: skip
    due = DemandOut(
        id="d1", kind=DemandKind.deadline, text="Send the evidence.", value_verbatim="January 12, "
        "2027", source_quote=RFE[3], span_ids=["p1b4"], page=1, date_text="January 12, 2027",
        time_text=None, relative_rule_text=None, anchor_span_id=None, amount_text=None,
        currency=None, documents=[], role="response_due", confidence=Confidence.high,
        ambiguity_note=None,
    )  # fmt: skip
    return out.model_copy(update={
        "demands": [due], "questions_to_ask": ["What evidence do I need?"],
        "plan_steps": [
            step("s1", "Mail your response to USCIS, P.O. Box 660867, Dallas, TX 75266 before "
                       "January 12, 2027.", PlanStepKind.mail, "p1b5"),
            step("s2", "Call the USCIS Contact Center at 800-375-5283 if you have questions.",
                 PlanStepKind.call, "p1b6"),
            step("s3", "Ask the office that sent this paper what evidence they need.",
                 PlanStepKind.verify, "p1b4"),
        ],
    })  # fmt: skip


async def test_a_block_id_impersonation_flag_on_a_genuine_rfe_is_no_scam(tmp_path: Path) -> None:
    """g1adv/legit2.py: red-flag R1 repaired a junk impersonation flag citing the USCIS header
    ("p1b1"); the genuine RFE scored possible and lost every plan step and its question. Only
    payment flags are repaired now; the others stay rejected, as before the repair."""
    for kind, span in ((RedFlagKind.impersonation, "p1b1"),
                       (RedFlagKind.urgency_pressure, "p1b4"),
                       (RedFlagKind.notario, "p1b3")):  # fmt: skip
        flag = RedFlagOut(kind=kind, text="Looks fake.", source_quote=span, span_ids=[span], page=1)
        result, _ = await analyze(tmp_path, rfe_out([flag]))
        assert result.scam_risk is ScamRisk.none and result.red_flags == [], kind
        assert result.document_type is DT.uscis_rfe and result.verification.facts_rejected >= 1
        assert [s.id for s in result.plan_steps] == ["s1", "s2", "s3"], kind
        assert result.questions_to_ask == ["What evidence do I need?"]
        assert result.urgency.verify_resource_id == "uscis_contact"


SNAP = [
    "Fairfax County Department of Family Services", "SNAP Interview Notice",
    "Your phone interview is on November 3, 2026 at 10:00 AM.",
    "We will call you at the number on file.",
]  # fmt: skip
SCAM_HELP = {"dhs_oig", "uscis_scams", "ftc_immigrant_scams", "ftc_reportfraud", "ssa_scams",
             "irs_scams"}  # fmt: skip


async def test_a_bare_model_scam_verdict_does_not_take_over_a_genuine_papers_help(
    tmp_path: Path,
) -> None:
    """g1adv/legit.py L6: the small model called a genuine SNAP notice a scam (is_likely_scam,
    signals ['urgency_pressure'], no red flag) and listed scam_report first; the preview became
    dhs_oig/uscis_scams/ftc_immigrant_scams. A verdict alone is no evidence (D-13); with a scam
    flag of its own (here unverifiable) the tag stays, behind the type's own help."""
    bare = variant(SNAP, dtype=DT.snap_notice, category=DC.benefits, sender=SK.local_agency,
                   likely=True, signals=["urgency_pressure"],
                   tags=["scam_report", "benefits_navigation"],
                   confidence=Confidence.high)  # fmt: skip
    result, _ = await analyze(tmp_path, bare)
    assert result.scam_risk is ScamRisk.none and RT.scam_report not in result.resource_tags
    assert not SCAM_HELP & set(preview(result)), preview(result)
    flagged = bare.model_copy(update={"red_flags": [RedFlagOut(
        kind=RedFlagKind.impersonation, text="Pretends to be the county.",
        source_quote="Department of Social Services fraud unit", span_ids=["p1b1"], page=1,
    )]})  # fmt: skip
    result, _ = await analyze(tmp_path, flagged)
    assert result.scam_risk is ScamRisk.none and result.resource_tags[-1] is RT.scam_report
    assert result.resource_tags[0] is not RT.scam_report
    assert preview(result) and preview(result)[0] not in SCAM_HELP, preview(result)


async def test_a_genuine_dari_receipt_saying_never_pay_by_gift_card_is_no_scam(
    tmp_path: Path,
) -> None:
    """g1adv/legit.py L1: "هرگز با کارت تحفه یا حواله پول پرداخت نکنید" ("never pay by gift card or
    money transfer") on a genuine USCIS receipt scored likely and re-typed it to other_notice once
    the bare "never" cue was gone."""
    texts = ["اداره خدمات شهروندی و مهاجرت ایالات متحده", "رسید درخواست I-765",
             "ما درخواست شما را دریافت کردیم.", "هرگز با کارت تحفه یا حواله پول پرداخت نکنید."]
    out = variant(texts, dtype=DT.uscis_receipt, category=DC.immigration,
                  sender=SK.federal_agency, lang="prs", tags=["immigration_legal_help"],
                  confidence=Confidence.high)  # fmt: skip
    result, _ = await analyze(tmp_path, out)
    assert result.scam_risk is ScamRisk.none and result.document_type is DT.uscis_receipt
    assert RT.scam_report not in result.resource_tags
