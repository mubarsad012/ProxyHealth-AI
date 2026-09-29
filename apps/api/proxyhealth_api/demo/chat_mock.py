"""Keyword-routed chat answers for the ``MockProvider`` (BUILD_PLAN §5.8 table; D-29).

The mock never reads a fixture for chat: it answers from the request's ``AnalysisContext`` only,
so every answer is grounded on quotes the client already has. Routing (first match wins):

1. eligibility / outcome / filing-advice words → ``refusal_kind`` + ``refer_to_professional`` by
   ``category`` (checked first: a question like "will I win by the date?" must never be answered);
2. scam words → ground on the paper's red flags (before dates: "pay with gift cards by Friday?");
3. date / deadline / pay words → quote the first verified ``deadline`` / ``appointment`` demand;
4. otherwise → ``not_in_document=true`` grounded on the summary's span ids.

Word lists cover ``en``, ``es``, ``prs`` and ``ar``; other languages match through the English and
Spanish lists and get English answer templates (a real model call would translate).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from proxyhealth_api.contracts.analysis import Demand
from proxyhealth_api.contracts.chat import AnalysisContext
from proxyhealth_api.contracts.enums import DemandKind, DocumentCategory, ReferTo, RefusalKind
from proxyhealth_api.contracts.model_out import ChatModelOut

WORDS: dict[str, dict[str, tuple[str, ...]]] = {
    "eligibility": {
        "en": ("qualify", "eligible", "eligibility", "am i allowed", "entitled"),
        "es": ("califico", "calificar", "elegible", "tengo derecho"),
        "prs": ("واجد شرایط", "حق دارم", "مستحق"),
        "ar": ("مؤهل", "أستحق", "يحق لي"),
    },
    "outcome": {
        "en": ("will i win", "will i lose", "deported", "approved", "denied", "what will happen",
               "chance"),
        "es": ("voy a ganar", "voy a perder", "deportado", "aprobado", "negado", "qué va a pasar"),
        "prs": ("برنده", "بازنده", "اخراج", "قبول می‌شود", "رد می‌شود", "چه خواهد شد"),
        "ar": ("سأربح", "سأخسر", "ترحيل", "ستتم الموافقة", "سيُرفض", "ماذا سيحدث"),
    },  # fmt: skip
    "filing_advice": {
        "en": ("should i file", "should i appeal", "should i sign", "should i plead",
               "should i apply", "which form", "what form"),
        "es": ("debo firmar", "debo apelar", "qué formulario", "cuál formulario"),
        "prs": ("کدام فورم", "درخواست بدهم", "امضا کنم"),
        "ar": ("أي نموذج", "هل أوقع", "هل أستأنف"),
    },
    "date": {
        "en": ("when", "date", "deadline", "due", "by what day", "how long", "appointment",
               "hearing", "time", "pay", "miss"),
        "es": ("cuándo", "cuando", "fecha", "plazo", "vence", "cita", "audiencia", "hora", "pagar"),
        "prs": ("چه وقت", "کی", "تاریخ", "مهلت", "ملاقات", "جلسه", "ساعت", "پرداخت"),
        "ar": ("متى", "تاريخ", "موعد", "مهلة", "جلسة", "الساعة", "أدفع"),
    },  # fmt: skip
    "scam": {
        "en": ("scam", "fake", "fraud", "real letter", "is this real", "gift card", "legit"),
        "es": ("estafa", "fraude", "falso", "falsa", "es real", "tarjeta de regalo"),
        "prs": ("کلاهبرداری", "تقلب", "جعلی", "واقعی است"),
        "ar": ("احتيال", "نصب", "مزيف", "مزورة", "حقيقية"),
    },
}

_TEMPLATES: dict[str, dict[str, str]] = {
    "quote": {
        "en": "The paper says: “{quote}”",
        "es": "El papel dice: “{quote}”",
        "prs": "در کاغذ نوشته شده: «{quote}»",
        "ar": "تقول الورقة: «{quote}»",
    },
    "flag": {
        "en": "Here is what the paper says: “{quote}”. Check with the real office before you pay.",
        "es": "Esto dice el papel: “{quote}”. Consulte con la oficina real antes de pagar.",
        "prs": "کاغذ این را می‌گوید: «{quote}». پیش از پرداخت با اداره واقعی تماس بگیرید.",
        "ar": "هذا ما تقوله الورقة: «{quote}». تحقق مع الجهة الحقيقية قبل أن تدفع.",
    },
    "refusal": {
        "en": "I cannot answer that from the paper. A person who knows your case can help.",
        "es": "No puedo responder eso con el papel. Una persona que conozca su caso puede ayudar.",
        "prs": "از روی کاغذ نمی‌توانم به این جواب بدهم. کسی که قضیه شما را می‌داند کمک می‌کند.",
        "ar": "لا أستطيع الإجابة عن ذلك من الورقة. يمكن لشخص يعرف حالتك أن يساعدك.",
    },
    "not_in_document": {
        "en": "The paper does not say. It is about: {title}",
        "es": "El papel no lo dice. Trata sobre: {title}",
        "prs": "کاغذ این را نمی‌گوید. درباره این است: {title}",
        "ar": "الورقة لا تذكر ذلك. هي عن: {title}",
    },
}
_SUGGESTED: dict[str, list[str]] = {
    "en": ["What is the date on this paper?", "Who sent this paper?"],
    "es": ["¿Qué fecha tiene este papel?", "¿Quién envió este papel?"],
    "prs": ["تاریخ این کاغذ چیست؟", "این کاغذ را چه کسی فرستاده؟"],
    "ar": ["ما التاريخ على هذه الورقة؟", "من أرسل هذه الورقة؟"],
}

REFER_BY_CATEGORY: dict[DocumentCategory, ReferTo] = {
    DocumentCategory.immigration: ReferTo.lawyer_or_accredited_rep,
    DocumentCategory.court: ReferTo.lawyer_or_accredited_rep,
    DocumentCategory.civic: ReferTo.lawyer_or_accredited_rep,
    DocumentCategory.employment: ReferTo.lawyer_or_accredited_rep,
    DocumentCategory.medical: ReferTo.clinician,
    DocumentCategory.housing: ReferTo.housing_counselor,
    DocumentCategory.benefits: ReferTo.benefits_office,
    DocumentCategory.school: ReferTo.sender,
    DocumentCategory.tax: ReferTo.sender,
    DocumentCategory.other: ReferTo.sender,
}
_DATE_KINDS = (DemandKind.deadline, DemandKind.appointment, DemandKind.relative_deadline)
_ROUTES = ("eligibility", "outcome", "filing_advice", "scam", "date")


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _lang(tag: str) -> str:
    base = tag.split("-")[0].lower()
    return base if base in _SUGGESTED else "en"


def _matches(words: tuple[str, ...], question: str) -> bool:
    for w in words:
        if re.search(r"[a-z]", w):  # Latin words: whole-word match
            if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", question):
                return True
        elif w in question:
            return True
    return False


def route(question: str, tag: str) -> str | None:
    """The first route whose words (target language + en + es) appear in ``question``."""
    q = _norm(question)
    langs = dict.fromkeys((_lang(tag), "en", "es"))
    for name in _ROUTES:
        if any(_matches(WORDS[name].get(lang, ()), q) for lang in langs):
            return name
    return None


@dataclass
class _Answer:
    answer: str
    span_ids: list[str]
    not_in_document: bool = False
    refusal: RefusalKind = RefusalKind.none
    refer: ReferTo = ReferTo.none
    tags: tuple[str, ...] = ()


def _t(name: str, lang: str, **values: str) -> str:
    return _TEMPLATES[name].get(lang, _TEMPLATES[name]["en"]).format(**values)[:600]


def _first_dated(ctx: AnalysisContext) -> Demand | None:
    for d in ctx.demands:
        if d.verified and d.kind in _DATE_KINDS:
            return d
    return None


def chat_answer(ctx: AnalysisContext | None, question: str, target_language: str) -> ChatModelOut:
    lang = _lang(target_language)
    name = route(question, target_language)
    summary_ids = list(ctx.summary.span_ids) if ctx else []
    title = ctx.summary.title if ctx else ""
    ans = _Answer(_t("not_in_document", lang, title=title), summary_ids, not_in_document=True)
    if name in ("eligibility", "outcome", "filing_advice"):
        category = ctx.category if ctx else DocumentCategory.other
        ans = _Answer(
            _t("refusal", lang), [], refusal=RefusalKind(name), refer=REFER_BY_CATEGORY[category]
        )
    elif name == "date" and ctx is not None:
        demand = _first_dated(ctx)
        if demand is not None:
            ans = _Answer(_t("quote", lang, quote=demand.source_quote), list(demand.span_ids))
    elif name == "scam" and ctx is not None:
        flag = next((r for r in ctx.red_flags if r.span_ids and r.source_quote), None)
        if flag is not None and flag.source_quote:
            ans = _Answer(
                _t("flag", lang, quote=flag.source_quote), list(flag.span_ids),
                tags=("scam_report",),
            )  # fmt: skip
    return ChatModelOut(
        answer=ans.answer,
        grounded_span_ids=ans.span_ids,
        not_in_document=ans.not_in_document,
        refusal_kind=ans.refusal,
        refer_to_professional=ans.refer,
        distress_acknowledged=False,
        suggested_questions=list(_SUGGESTED[lang]),
        resource_tags=list(ans.tags),
    )


__all__ = ["REFER_BY_CATEGORY", "WORDS", "chat_answer", "route"]
