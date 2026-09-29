"""WP2 — ``analysis/emergency.py`` + ``data/safety/emergency.yaml`` (D-14; COMPLIANCE §7)."""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from proxyhealth_api.analysis import emergency as em
from proxyhealth_api.contracts.enums import WarningCode

BUNDLED = (
    "en", "es", "zh-Hans", "zh-Hant", "vi", "tl", "ar", "ht", "pt-BR", "ru", "uk", "ko", "fr",
    "prs", "ps", "fa", "ur", "hi", "pa", "bn", "so", "sw", "am", "my", "ne", "rw",
)  # fmt: skip
NEUTRAL: dict[str, str] = {
    "en": "Please bring this letter to your appointment on Monday.",
    "es": "Por favor traiga esta carta a su cita del lunes.",
    "zh-Hans": "请在星期一带这封信来参加预约。",
    "zh-Hant": "請在星期一帶這封信來參加預約。",
    "vi": "Vui lòng mang thư này đến cuộc hẹn vào thứ Hai.",
    "tl": "Pakidala ang sulat na ito sa iyong appointment sa Lunes.",
    "ar": "يرجى إحضار هذه الرسالة إلى موعدك يوم الاثنين.",
    "ht": "Tanpri pote lèt sa a nan randevou ou lendi.",
    "pt-BR": "Por favor, traga esta carta para sua consulta na segunda-feira.",
    "ru": "Пожалуйста, принесите это письмо на приём в понедельник.",
    "uk": "Будь ласка, принесіть цей лист на прийом у понеділок.",
    "ko": "월요일 예약 시 이 편지를 가져오세요.",
    "fr": "Veuillez apporter cette lettre à votre rendez-vous lundi.",
    "prs": "لطفاً این نامه را روز دوشنبه با خود بیاورید.",
    "ps": "مهرباني وکړئ دا لیک د دوشنبې په ورځ راوړئ.",
    "fa": "لطفاً این نامه را روز دوشنبه همراه خود بیاورید.",
    "ur": "براہ کرم پیر کے دن یہ خط ساتھ لائیں۔",
    "hi": "कृपया सोमवार को यह पत्र साथ लाएं। विषय: आपकी नियुक्ति।",
    "pa": "ਕਿਰਪਾ ਕਰਕੇ ਸੋਮਵਾਰ ਨੂੰ ਇਹ ਚਿੱਠੀ ਨਾਲ ਲਿਆਓ।",
    "bn": "অনুগ্রহ করে সোমবার এই চিঠিটি সঙ্গে আনুন। বিষয়: আপনার সাক্ষাৎ।",
    "so": "Fadlan keen warqaddan ballantaada Isniinta.",
    "sw": "Tafadhali leta barua hii kwenye miadi yako Jumatatu.",
    "am": "እባክዎ ይህን ደብዳቤ ሰኞ ወደ ቀጠሮዎ ይዘው ይምጡ።",
    "my": "တနင်္လာနေ့ ချိန်းဆိုမှုသို့ ဤစာကို ယူလာပါ။",
    "ne": "कृपया सोमबार यो पत्र साथमा ल्याउनुहोस्। विषय: भेट।",
    "rw": "Mwibuke kuzana iyi baruwa ku wa mbere.",
}


def _raw() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(em.EMERGENCY_YAML.read_text(encoding="utf-8"))
    return data


RAW = _raw()


def test_schema_every_bundled_language_every_kind() -> None:
    assert tuple(RAW["kinds"]) == em.KINDS
    assert set(RAW["languages"]) == set(BUNDLED)
    for tag in BUNDLED:
        lang = RAW["languages"][tag]
        assert "reviewed_by" in lang and lang["reviewed_by"] is None, tag
        assert "reviewed_on" in lang
        assert set(lang["terms"]) == set(em.KINDS), tag
        assert all(lang["terms"][k] for k in em.KINDS), tag
    lex = em.load_lexicon()
    assert set(lex.languages) == set(BUNDLED)
    assert lex.fallback_languages == ("en", "es")


@pytest.mark.parametrize("tag", BUNDLED)
@pytest.mark.parametrize("kind", em.KINDS)
def test_one_positive_per_kind_per_language(tag: str, kind: str) -> None:
    term = str(RAW["languages"][tag]["terms"][kind][0]).rstrip("*")
    text = f"{NEUTRAL[tag]} {term} 12"
    assert kind in em.scan_text(text, [tag]), (tag, kind, term)


@pytest.mark.parametrize("tag", BUNDLED)
def test_one_negative_per_language(tag: str) -> None:
    assert em.scan_text(NEUTRAL[tag], [tag]) == []


@pytest.mark.parametrize(
    "text",
    [
        "Your chest x-ray is scheduled for Monday.",
        "Take one tablet daily with food.",
        "For questions call Poison Control at the number on the label.",
        "Poison Help: 1-800-222-1222.",
        "Keep this letter for your records.",
        "List any allergies on the form.",
        "Report fraud, waste and abuse to Medicare.",
        "Bring your insurance card and a photo ID.",
        "The hearing is at the court on Friday.",
    ],
)
def test_english_negatives(text: str) -> None:
    assert em.scan_text(text, ["en", "es"]) == []


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Go to the ER if you have chest pain or trouble breathing.", "chest_pain"),
        ("My son overdosed last night", "overdose"),
        ("my child swallowed poison", "poison"),
        ("I want to kill myself", "self_harm"),
        ("signs of a stroke: face drooping", "stroke"),
        ("bleeding won't stop", "bleeding"),
        ("She had an allergic reaction", "allergic"),
        ("My husband beats me", "violence"),
    ],
)
def test_english_positives(text: str, kind: str) -> None:
    assert kind in em.scan_text(text, ["en"])


def test_kinds_are_deduplicated_in_fixed_order() -> None:
    text = "trouble breathing, chest pain, chest pain again"
    assert em.scan_text(text, ["en"]) == ["chest_pain", "breathing"]


def test_substring_and_zwnj_matching() -> None:
    assert em.scan_text("他说他想自杀了", ["zh-Hans"]) == ["self_harm"]
    joined = "نمی‌توانم نفس بکشم"
    spaced = "نمی توانم نفس بکشم"
    assert em.scan_text(joined, ["fa"]) == em.scan_text(spaced, ["fa"]) == ["breathing"]


def test_detected_target_and_fallback_languages() -> None:
    tags, unavailable = em.languages_to_scan("es-MX", "prs")
    assert tags == ["es", "prs", "en"] and unavailable is False
    tags, unavailable = em.languages_to_scan("x-wakhi", "rhg")
    assert tags == ["en", "es"] and unavailable is True
    assert em.load_lexicon().resolve("zh-TW") == "zh-Hant"
    assert em.load_lexicon().resolve("pt") == "pt-BR"
    assert em.has_lexicon("ar") and not em.has_lexicon("rhg")


def test_detect_emergency_on_a_transcript() -> None:
    out = em.detect_emergency(
        ["Discharge instructions", "Call 911 for chest pain or severe bleeding."],
        detected_language="en", target_language="ar",
    )  # fmt: skip
    assert out.safety.emergency is True
    assert out.safety.emergency_kinds == ["chest_pain", "bleeding"]
    assert out.safety.credential_or_payment_request is False
    assert out.warnings == [] and out.model_only is False


def test_detect_emergency_in_target_language_chat() -> None:
    out = em.detect_emergency(
        ["¿Qué dice esta carta?", "mi hijo no puede respirar"],
        detected_language="en", target_language="es",
    )  # fmt: skip
    assert out.safety.emergency_kinds == ["breathing"]


def test_unavailable_language_warns_but_still_scans_fallbacks() -> None:
    out = em.detect_emergency(
        ["sobredosis"], detected_language="rhg", target_language="rhg"
    )
    assert out.safety.emergency and out.safety.emergency_kinds == ["overdose"]
    assert out.warnings == [WarningCode.emergency_lexicon_unavailable]


def test_model_hints_alone_trigger() -> None:
    out = em.detect_emergency(
        ["nothing here"], detected_language="en", target_language="en",
        model_terms=["heart attack"],
    )  # fmt: skip
    assert out.safety.emergency and out.safety.emergency_kinds == ["chest_pain"]
    assert out.model_only is True
    flag = em.detect_emergency([], detected_language="en", target_language="en", model_flag=True)
    assert flag.safety.emergency and flag.safety.emergency_kinds == []


def test_no_emergency() -> None:
    out = em.detect_emergency(
        [NEUTRAL["en"]], detected_language="en", target_language="es",
        credential_or_payment_request=True,
    )  # fmt: skip
    assert out.safety.emergency is False and out.safety.emergency_kinds == []
    assert out.safety.credential_or_payment_request is True


# --- round 2: common phrasings (D-14: false negatives are not acceptable) ---------------------


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("My husband hits me every night", "violence"),
        ("he keeps hitting me", "violence"),
        ("my chest hurts a lot", "chest_pain"),
        ("My chest is hurting since this morning", "chest_pain"),
        ("I am bleeding a lot", "bleeding"),
        ("I can't stop bleeding", "bleeding"),
        ("Me quiero matar", "self_harm"),
        ("quiero matarme", "self_harm"),
        ("me duele el pecho", "chest_pain"),
    ],
)
def test_round2_common_phrasings(text: str, kind: str) -> None:
    out = em.detect_emergency([text], detected_language="en", target_language="en")
    assert out.safety.emergency is True and kind in out.safety.emergency_kinds, text


def test_typed_question_about_poison_control_is_an_emergency() -> None:
    question = "My son swallowed something, should I call poison control?"
    out = em.detect_emergency(
        [], user_texts=[question], detected_language="en", target_language="en"
    )
    assert out.safety.emergency is True and out.safety.emergency_kinds == ["poison"]
    # the same words typed by the user keep "poison control" (exclude is for printed text only)
    typed = em.scan_text("should I call poison control?", ["en"], apply_exclude=False)
    assert typed == ["poison"]
    assert em.scan_text("should I call poison control?", ["en"]) == []


def test_medicine_label_boilerplate_is_still_not_an_emergency() -> None:
    label = "If swallowed, get medical help or contact a Poison Control Center right away."
    out = em.detect_emergency([label], detected_language="en", target_language="es")
    assert out.safety.emergency is False
