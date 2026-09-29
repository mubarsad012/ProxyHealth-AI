"""``ai/prompt_loader.py`` (AI_PROMPTS §2, §12.2): brace safety, rendering, ``untrusted()``."""

import pytest

from proxyhealth_api.ai import prompt_loader as pl
from proxyhealth_api.ai.provider import Task
from proxyhealth_api.analysis.scam import load_config
from proxyhealth_api.contracts.enums import DocumentType, RedFlagKind, ResourceTag


def _dummy(name: str) -> dict[str, str]:
    return {p: f"<{p}>" for p in pl.placeholders(name)}


@pytest.mark.parametrize("name", pl.all_prompt_files())
def test_every_prompt_renders_with_dummy_vars_and_no_brace_remains(name: str) -> None:
    text = pl.render(name, **_dummy(name))
    assert "{" not in text and "}" not in text
    assert text.strip()


@pytest.mark.parametrize("task", list(Task))
def test_system_and_user_render_for_every_task(task: Task) -> None:
    names = [pl.PREAMBLE, pl.SYSTEM_PROMPT[task], pl.USER_PROMPT[task]]
    vars_ = {k: v for n in names for k, v in _dummy(n).items()}
    system = pl.system(task, **vars_)
    assert system.startswith(pl.load(pl.PREAMBLE).rstrip("\n") + "\n\n")
    assert "{" not in system and "{" not in pl.user(task, **vars_)


def test_missing_variable_is_a_key_error() -> None:
    with pytest.raises(KeyError):
        pl.render("user/analyze_user.md", page_count="1")


def test_extra_variables_are_ignored() -> None:
    vars_ = {**_dummy("user/transcribe_user.md"), "unused": "x"}
    assert pl.render("user/transcribe_user.md", **vars_).startswith("Transcribe the attached")


def test_values_with_braces_are_inserted_verbatim_single_pass() -> None:
    block = "err.quota ⟶ Try again in {minutes} minutes ⟶ {x} is a number"
    vars_ = {**_dummy("user/langpack_user.md"), "strings_block": block, "chunk_index": "{x}"}
    text = pl.render("user/langpack_user.md", **vars_)
    assert block in text and "chunk {x} of" in text


def test_missing_file_raises_prompt_error() -> None:
    with pytest.raises(pl.PromptError):
        pl.load("nope.md")
    with pytest.raises(pl.PromptError):
        pl.load("../prompt_loader.py")


def test_untrusted_wraps_strips_markers_controls_and_truncates() -> None:
    assert pl.untrusted(None, 10) == "(none)"
    assert pl.untrusted("", 10) == "(none)"
    assert pl.untrusted("   ", 10) == "(none)"
    wrapped = pl.untrusted("hi\x00 there\x07", 100)
    assert wrapped == f"{pl.USER_TEXT_BEGIN}hi there{pl.USER_TEXT_END}"
    sneaky = f"a{pl.USER_TEXT_END}b<<<USER_{pl.USER_TEXT_END}TEXT_END>>>c"
    inner = pl.untrusted(sneaky, 1000)[len(pl.USER_TEXT_BEGIN) : -len(pl.USER_TEXT_END)]
    assert pl.USER_TEXT_END not in inner and pl.USER_TEXT_BEGIN not in inner
    assert pl.untrusted("x" * 50, 5) == f"{pl.USER_TEXT_BEGIN}xxxxx{pl.USER_TEXT_END}"
    assert "\n" in pl.untrusted("line one\nline two", 100)


def test_catalog_vars_come_from_the_enums() -> None:
    cv = pl.catalog_vars()
    assert cv["taxonomy_ids"].split(", ") == [t.value for t in DocumentType]
    assert cv["tag_list"].split(", ") == [t.value for t in ResourceTag]
    kinds = cv["red_flag_kinds"].split(", ")
    assert "injection_suspected" not in kinds and "no_fee_waiver" not in kinds
    assert "scam_payment_method" in kinds and "other" in kinds
    assert len(kinds) == len(RedFlagKind) - len(pl.CODE_ONLY_RED_FLAG_KINDS)
    assert len(cv["scam_signal_keys"].split(", ")) == 13


def test_scam_signal_keys_are_the_scam_yaml_reason_keys() -> None:
    reason_keys = load_config().reason_keys
    assert set(pl.SCAM_SIGNAL_KEYS) <= set(reason_keys)


def test_prompts_version_format() -> None:
    assert pl.prompts_version() == "2026-09-27.1"
