"""``ai/prompts/**`` == the ``text prompt:`` blocks of ``docs/AI_PROMPTS.md`` §5 (§13 there)."""

import re
from pathlib import Path

import pytest

from proxyhealth_api.ai import prompt_loader as pl

REPO = Path(__file__).resolve().parents[4]
DOC = REPO / "docs" / "AI_PROMPTS.md"
BLOCK_RE = re.compile(r"^```text prompt:(\S+)\n(.*?)^```$", re.M | re.S)
EXPECTED = {
    "preamble.md", "analyze.md", "transcribe.md", "explain.md", "troubleshoot.md", "chat.md",
    "langpack.md", "tag.md", "phrasing_rewrite.md", "user/analyze_user.md",
    "user/transcribe_user.md", "user/explain_user.md", "user/troubleshoot_user.md",
    "user/chat_user.md", "user/langpack_user.md", "user/tag_user.md",
    "user/phrasing_rewrite_user.md", "user/resolve_language_user.md",
    "compat_analyze.md", "user/sample_note.md",
}  # fmt: skip

pytestmark = pytest.mark.skipif(not DOC.is_file(), reason="docs/ not present in this checkout")


def _doc() -> str:
    return DOC.read_text(encoding="utf-8").replace("\r\n", "\n")


def _blocks() -> dict[str, str]:
    found: dict[str, str] = {}
    for name, body in BLOCK_RE.findall(_doc()):
        assert name not in found, f"duplicate prompt block {name}"
        found[name] = body
    return found


def _table_placeholders() -> set[str]:
    section = _doc().split("## 2. Prompt loader", 1)[1].split("\n## 3.", 1)[0]
    names: set[str] = set()
    for row in re.findall(r"^\| (.+?) \|", section, re.M):
        names.update(re.findall(r"`\{([a-z_]+)\}`", row))
    return names


def _strip(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).rstrip()


def test_block_names_are_exactly_the_prompt_files() -> None:
    assert set(_blocks()) == EXPECTED
    assert set(pl.all_prompt_files()) == EXPECTED


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_prompt_file_matches_doc_block(name: str) -> None:
    block = _blocks()[name]
    text = (pl.PROMPTS_DIR / name).read_text(encoding="utf-8")
    assert _strip(text) == _strip(block), f"ai/prompts/{name} differs from AI_PROMPTS §5"
    assert text.endswith("\n") and not text.endswith("\n\n"), "file must end with one newline"


def test_version_matches_doc() -> None:
    section = _doc().split("## 13. Prompt versioning", 1)[1].split("\n## 14.", 1)[0]
    current = re.search(r"Current: \*\*`prompts_version = ([0-9.-]+)`\*\*", section)
    assert current is not None, "AI_PROMPTS §13 must state the current prompts_version"
    raw = pl.VERSION_FILE.read_text(encoding="utf-8")
    assert raw == f"prompts_version = {current.group(1)}\n"
    assert pl.prompts_version() == current.group(1)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_placeholder_is_in_the_section_2_table(name: str) -> None:
    table = _table_placeholders()
    block = _blocks()[name]
    used = set(pl.PLACEHOLDER.findall(block))
    assert used <= table, f"{name}: placeholders not in AI_PROMPTS §2 table: {used - table}"
    leftover = pl.PLACEHOLDER.sub("", block)
    assert "{" not in leftover and "}" not in leftover, f"{name}: stray brace"
