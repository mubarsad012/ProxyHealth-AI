"""Bundled packs translate the visible UI strings, not only the old ones (D-25; 2026-10-22).

The Dari build showed English on screens a sample-mode user reaches (the "no voice" line under a
result, the "I think this is a…" chips, the hide-parts box controls, Help search, read-later
lines) because those keys were only ``fallback_keys`` in every bundled pack. They are translated
now. The keys a bundled pack still leaves in English on purpose are the reviewed privacy sentences
that make a sending claim (COMPLIANCE_PRIVACY §17 ``approved_keys``, e.g. ``banner.demo_sample``)
and ``consent.*``. ``home.tile_sample_sub`` (the Home sample tile, §17.1: "makes no sending
claim") is translated: judges in Dari saw it in English on Home.
"""

import re

import pytest
import yaml

from proxyhealth_api.contracts.langpack import LanguagePack
from proxyhealth_api.packs.base import BasePack
from proxyhealth_api.settings import DATA_DIR

from .test_privacy_claims import COMPLIANCE

LANGPACKS = DATA_DIR / "langpacks"
REQUIRED_BUNDLED = ("es", "prs", "ar", "ps")

# Visible UI keys that were English fallbacks in the bundled packs until 2026-10-22
# (``clerk.generic_need`` only in ps).
TRANSLATED_UI_KEYS = (
    "capture.torch",
    "chat.unavailable_unpaid",
    "clerk.generic_need",
    "demand.estimate_about",
    "help.always",
    "help.any_language",
    "help.search_empty",
    "prepare.bring_school_records",
    "reminders.lockscreen_explain.web",
    "review.hint.hearing_notice",
    "review.hint.medicaid_renewal",
    "review.hint.medical_bill",
    "review.hint.not_sure",
    "review.hint.pay_or_quit",
    "review.hint.school_enrollment",
    "review.hint.snap_notice",
    "review.hint.uscis_receipt",
    "review.hint.utility_shutoff",
    "review.mask_bigger",
    "review.mask_box",
    "review.mask_move_left",
    "review.mask_move_right",
    "review.mask_resize_handle",
    "review.mask_smaller",
    "review.output_language",
    "review.output_language_title",
    "review.page_image",
    "review.preparing_page",
    "review.read_later_needs_keep_pages",
    "review.read_later_saved",
    "review.read_later_unavailable",
    "review.waiting_for_internet",
    "tts.fallback_offer_english",
    "tts.no_voice",
    "urgency.medium.unverified_date",
    "vault.delete_confirm.web",
    "verify.date_see_paper",
    "wipe.body.web",
)


def approved_privacy_keys() -> set[str]:
    text = COMPLIANCE.read_text("utf-8")
    m = re.search(r"```yaml\n(.*?)```", text[text.index("## 17.") :], re.S)
    assert m, "COMPLIANCE_PRIVACY §17 has no fenced yaml block"
    return set(yaml.safe_load(m.group(1))["privacy_claims"]["approved_keys"])


def load(tag: str) -> LanguagePack:
    return LanguagePack.model_validate_json((LANGPACKS / f"{tag}.json").read_bytes())


def test_translated_list_has_no_privacy_or_consent_key() -> None:
    privacy = approved_privacy_keys() & set(TRANSLATED_UI_KEYS)
    consent = [k for k in TRANSLATED_UI_KEYS if k.startswith("consent.")]
    assert not privacy and not consent, (sorted(privacy), consent)


@pytest.mark.parametrize("tag", REQUIRED_BUNDLED)
def test_visible_ui_keys_are_translated(tag: str) -> None:
    base = BasePack.load(LANGPACKS / "en.json")
    pack = load(tag)
    still_english = [
        k
        for k in TRANSLATED_UI_KEYS
        if k in pack.fallback_keys or pack.strings[k] == base.strings[k]
    ]
    assert not still_english, still_english


@pytest.mark.parametrize("tag", REQUIRED_BUNDLED)
def test_fallback_keys_are_exactly_english(tag: str) -> None:
    # A key left in English (privacy sentences, consent, new en.json keys) shows the English
    # copy byte for byte — never a half-edited translation that QA no longer looks at.
    base = BasePack.load(LANGPACKS / "en.json")
    pack = load(tag)
    drifted = [k for k in pack.fallback_keys if pack.strings[k] != base.strings[k]]
    assert not drifted, drifted


@pytest.mark.parametrize("tag", REQUIRED_BUNDLED)
def test_home_sample_tile_subtitle_is_translated(tag: str) -> None:
    # The Home sample tile is the first thing a sample-mode judge reads under "Try a sample paper".
    base = BasePack.load(LANGPACKS / "en.json")
    pack = load(tag)
    key = "home.tile_sample_sub"
    assert key not in pack.fallback_keys
    assert pack.strings[key] != base.strings[key]
