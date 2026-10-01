"""Privacy sentences stay literally true (D-02, COMPLIANCE_PRIVACY §17; FTC Act §5).

Parses the fenced ``yaml`` block of ``docs/COMPLIANCE_PRIVACY.md`` §17 and asserts:

(a) every ``approved_keys`` entry exists in ``en.json`` and its English string equals the copy
    fixed in the docs byte for byte — ``PRODUCT_SPEC.md`` Appendix A, COMPLIANCE_PRIVACY §4
    (``key``: "copy"), §12 ("copy" (``key``)) or §17.1 (reviewed copy that Appendix A lacks);
(b) no ``en.json`` string contains a ``forbidden_phrases`` entry (case-insensitive). The check is
    negation-aware (CL-012): an occurrence directly preceded by "not", "never" or "no" is the
    honest disclaimer itself — "Keep on this device (not encrypted by the app)" — not a claim;
(c) every ``en.json`` key whose value contains a ``claim_markers`` entry is an approved key, so a
    new privacy sentence cannot ship unreviewed.

It also applies (b) to the public privacy policy (``apps/mobile/public/privacy/index.html``) and to
the store copy blocks in ``docs/STORE_LISTING.md``, and checks that the policy reuses the in-app
notice sentences verbatim and prints the current ``CONSENT_VERSION`` (COMPLIANCE_PRIVACY §16).

Finally it backs "Our server does not keep your papers or photos" with a static check: every file
write, temp file, rename, mkdir or SQLite connection in ``apps/api/proxyhealth_api`` must be a
reviewed site (BUILD_PLAN §7 row 11).
"""

import ast
import html
import json
import re
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml

from proxyhealth_api.settings import DATA_DIR, Settings

REPO = Path(__file__).resolve().parents[4]
COMPLIANCE = REPO / "docs" / "COMPLIANCE_PRIVACY.md"
PRODUCT_SPEC = REPO / "docs" / "PRODUCT_SPEC.md"
STORE_LISTING = REPO / "docs" / "STORE_LISTING.md"
PRIVACY_PAGE = REPO / "apps" / "mobile" / "public" / "privacy" / "index.html"
EN_JSON = DATA_DIR / "langpacks" / "en.json"

_NEGATION_BEFORE = re.compile(r"(?:\bnot|\bnever|\bno)[\s(\"'“‘]*$", re.IGNORECASE)

# Sentences the privacy policy must reuse verbatim (COMPLIANCE_PRIVACY §16, items 3–13).
POLICY_REUSES = (
    "privacy.notice.sent",
    "privacy.notice.what_we_keep",
    "privacy.notice.settings_sent",
    "privacy.notice.no_status",
    "privacy.notice.install_id",
    "privacy.notice.device",
    "privacy.notice.device_web",
    "privacy.notice.hide_parts",
    "privacy.notice.delete",
    "privacy.notice.feedback",
    "privacy.notice.no_ads",
    "consent.line2.paid",
    "consent.line2.demo",
    "vault.privacy_native",
    "vault.privacy_web",
)


def _section(text: str, start: str, end: str) -> str:
    i = text.index(start)
    j = text.index(end, i + len(start))
    return text[i:j]


@cache
def claims() -> dict[str, Any]:
    text = COMPLIANCE.read_text("utf-8")
    sec17 = text[text.index("## 17.") :]
    m = re.search(r"```yaml\n(.*?)```", sec17, re.S)
    assert m, "COMPLIANCE_PRIVACY §17 has no fenced yaml block"
    data = yaml.safe_load(m.group(1))["privacy_claims"]
    assert isinstance(data, dict)
    return data


@cache
def en_strings() -> dict[str, str]:
    data = json.loads(EN_JSON.read_text("utf-8"))
    return {k: v for k, v in data.items() if isinstance(v, str)}


def _appendix_a_copy(text: str) -> dict[str, list[str]]:
    """``| `a` / `b` | A / B |`` rows expand to one entry per key when the counts agree."""
    out: dict[str, list[str]] = {}
    appendix = text[text.index("## Appendix A") :]
    for line in appendix.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        keys = re.findall(r"`([^`]+)`", cells[0])
        if len(keys) == 1:
            out.setdefault(keys[0], []).append(cells[1])
            continue
        values = cells[1].split(" / ")
        if len(values) == len(keys):
            for key, value in zip(keys, values, strict=True):
                out.setdefault(key, []).append(value)
    return out


@cache
def fixed_copy() -> dict[str, list[str]]:
    """Every English string the docs fix for a key (several sources may repeat a key)."""
    out = _appendix_a_copy(PRODUCT_SPEC.read_text("utf-8"))
    comp = COMPLIANCE.read_text("utf-8")
    inline = re.compile(r"`([a-z0-9_]+(?:\.[a-z0-9_]+)+)`(?:\s*\([^)]*\))?:\s*\"([^\"]+)\"")
    for start, end in (("## 4. Consent", "## 5. Fixed"), ("## 17.", "## 18.")):
        for m in inline.finditer(_section(comp, start, end)):
            out.setdefault(m.group(1), []).append(m.group(2))
    perm = re.compile(r"\"([^\"]+)\"\s*\(`(perm\.[a-z_]+)`\)")
    for m in perm.finditer(_section(comp, "## 12. Permission", "### 12.1")):
        out.setdefault(m.group(2), []).append(m.group(1))
    return out


def forbidden_hits(text: str, phrases: list[str]) -> list[str]:
    """Forbidden phrases in ``text``, ignoring occurrences negated by the word right before."""
    hits: list[str] = []
    low = text.lower()
    for phrase in phrases:
        start = 0
        needle = phrase.lower()
        while (i := low.find(needle, start)) != -1:
            if not _NEGATION_BEFORE.search(text[:i]):
                hits.append(phrase)
                break
            start = i + len(needle)
    return hits


def page_text(raw_html: str) -> str:
    no_code = re.sub(r"<(script|style)\b.*?</\1>", " ", raw_html, flags=re.S)
    no_tags = re.sub(r"<[^>]+>", " ", no_code)
    return re.sub(r"\s+", " ", html.unescape(no_tags))


# --- the seed itself ---------------------------------------------------------------------------


def test_seed_parses() -> None:
    c = claims()
    for field in ("approved_keys", "claim_markers", "forbidden_phrases"):
        assert isinstance(c[field], list) and c[field], field
    assert len(set(c["approved_keys"])) == len(c["approved_keys"]), "duplicate approved key"


def test_negation_awareness() -> None:
    phrases = ["encrypted by the app", "backed up"]
    assert forbidden_hits("Keep on this device (not encrypted by the app)", phrases) == []
    assert forbidden_hits("The app does NOT encrypted by the app", phrases) == []
    assert forbidden_hits("Your papers are encrypted by the app.", phrases) == [
        "encrypted by the app"
    ]
    assert forbidden_hits("Papers are backed up. Also not backed up.", phrases) == ["backed up"]
    assert forbidden_hits("It is nothing backed up", phrases) == ["backed up"]


# --- rules a–c -----------------------------------------------------------------------------------


def test_a_approved_keys_exist_and_match_fixed_copy() -> None:
    strings = en_strings()
    copy = fixed_copy()
    problems: list[str] = []
    for key in claims()["approved_keys"]:
        if key not in strings:
            problems.append(f"{key}: missing from en.json")
        elif key not in copy:
            problems.append(f"{key}: no fixed copy (PRODUCT_SPEC App. A, COMPLIANCE §4/§12/§17.1)")
        elif strings[key] not in copy[key]:
            problems.append(f"{key}: en.json {strings[key]!r} != docs {copy[key]!r}")
    assert not problems, "\n".join(problems)


def test_b_no_forbidden_phrase_in_en_json() -> None:
    phrases = claims()["forbidden_phrases"]
    bad = {k: hits for k, v in en_strings().items() if (hits := forbidden_hits(v, phrases))}
    assert not bad, bad


def test_c_every_claim_sentence_is_approved() -> None:
    approved = set(claims()["approved_keys"])
    markers = [m.lower() for m in claims()["claim_markers"]]
    unreviewed = {
        k: v
        for k, v in en_strings().items()
        if k not in approved and any(m in v.lower() for m in markers)
    }
    assert not unreviewed, (
        "privacy-style sentences outside COMPLIANCE_PRIVACY §17 approved_keys (review them "
        f"against the implementation, then approve or reword): {unreviewed}"
    )


# --- the public privacy policy and the store copy (COMPLIANCE_PRIVACY §16, §5.4) -------------


@pytest.fixture(scope="module")
def policy() -> str:
    assert PRIVACY_PAGE.is_file(), f"{PRIVACY_PAGE} is missing (WP8)"
    return PRIVACY_PAGE.read_text("utf-8")


def test_policy_is_plain_html_with_lang_and_dir(policy: str) -> None:
    assert re.search(r"<html[^>]*\blang=\"en\"[^>]*\bdir=\"ltr\"", policy)
    assert "<script" not in policy.lower(), "the policy must read without JavaScript"
    assert "<h1" in policy and "<h2" in policy


def test_policy_has_no_forbidden_phrase(policy: str) -> None:
    assert forbidden_hits(page_text(policy), claims()["forbidden_phrases"]) == []


def test_policy_reuses_notice_sentences_verbatim(policy: str) -> None:
    text = page_text(policy)
    strings = en_strings()
    missing = [k for k in POLICY_REUSES if strings[k] not in text]
    assert not missing, f"privacy policy lacks the verbatim sentences of {missing}"


def test_policy_prints_current_consent_version(policy: str) -> None:
    version = Settings(_env_file=None).consent_version
    assert f"consent version {version}" in page_text(policy)


def test_store_listing_copy_has_no_forbidden_phrase() -> None:
    assert STORE_LISTING.is_file(), f"{STORE_LISTING} is missing (WP8)"
    blocks = re.findall(r"```text\n(.*?)```", STORE_LISTING.read_text("utf-8"), re.S)
    assert blocks, "STORE_LISTING.md keeps store copy in ```text blocks"
    bad = [b[:60] for b in blocks if forbidden_hits(b, claims()["forbidden_phrases"])]
    assert not bad, bad


def test_store_listing_code_fences_are_balanced() -> None:
    """An unclosed fence turns the rest of the file into code and hides it from the scan above."""
    text = STORE_LISTING.read_text("utf-8")
    fences = re.findall(r"^```", text, re.M)
    assert len(fences) % 2 == 0, f"STORE_LISTING.md has {len(fences)} line-start ``` fences"
    openers = len(re.findall(r"^```text$", text, re.M))
    blocks = re.findall(r"^```text\n(.*?)^```$", text, re.S | re.M)
    assert len(blocks) == openers, "every ```text block must be closed before the next fence"


# Native sends mask rectangles and the server blacks them out; web burns them in on the device
# (features/analysis/buildRequest.ts). The policy must say both, in the approved consent words.
MASK_SENTENCES = ("consent.line4.masks", "consent.line4.masks_web")


def test_policy_states_where_masks_are_applied(policy: str) -> None:
    text = page_text(policy)
    strings = en_strings()
    missing = [k for k in MASK_SENTENCES if strings[k] not in text]
    assert not missing, f"privacy policy lacks the verbatim sentences of {missing}"


# --- "Our server does not keep your papers" — where server code may write (BUILD_PLAN §7 row 11) --

SERVER_CODE = REPO / "apps" / "api" / "proxyhealth_api"

# Calls that create, change or move something on disk. ``open``/``fdopen`` count only with a write
# mode (or a mode the scan cannot read); ``shutil`` counts whole. ``Path.replace`` cannot be told
# apart from ``str.replace``, so server code moves files with ``os.replace`` (which is scanned).
_WRITE_METHODS = frozenset(
    {"write_text", "write_bytes", "mkdir", "touch", "save", "rename", "symlink_to", "hardlink_to"}
)
_WRITE_MODULE_CALLS: dict[str, frozenset[str] | None] = {
    "os": frozenset(
        {"replace", "rename", "renames", "makedirs", "mkdir", "fdopen", "open", "link", "symlink"}
    ),
    "tempfile": frozenset(
        {
            "mkstemp",
            "mkdtemp",
            "NamedTemporaryFile",
            "TemporaryFile",
            "SpooledTemporaryFile",
            "TemporaryDirectory",
        }
    ),
    "sqlite3": frozenset({"connect"}),
    "shutil": None,
}

# Every place the server writes, and why it never holds a user's paper. (module, function, call).
REVIEWED_WRITE_SITES: dict[tuple[str, str, str], str] = {
    ("main.py", "_build_state", "mkdir"): "creates settings.var_dir itself",
    ("ai/keypool.py", "KeyPool.persist", "mkdir"): "var_dir/keypool.json: slot state, no user data",
    ("ai/keypool.py", "KeyPool.persist", "write_text"): "var_dir/keypool.json (temp file first)",
    ("ai/keypool.py", "KeyPool.persist", "os.replace"): "var_dir/keypool.json (atomic swap)",
    ("packs/cache.py", "PackCache.put", "mkdir"): "var_dir/langpacks/: generated UI strings",
    ("packs/cache.py", "PackCache.put", "tempfile.mkstemp"): "var_dir/langpacks/ temp file",
    ("packs/cache.py", "PackCache.put", "os.fdopen"): "var_dir/langpacks/ temp file",
    ("packs/cache.py", "PackCache.put", "os.replace"): "var_dir/langpacks/<tag>.json (atomic)",
    ("feedback/store.py", "FeedbackStore._connect", "mkdir"): "var_dir: feedback counters",
    ("feedback/store.py", "FeedbackStore._connect", "sqlite3.connect"): (
        "var_dir/feedback_counts.sqlite: counters keyed by enums, never text (D-31)"
    ),
    ("ai/recording.py", "RecordingProvider.write", "write_text"): (
        "dev-only recording provider (ENV=development, AI_PROVIDER=gemini, RECORD_FIXTURES=1): "
        "data/fixtures/<id>/out.*.json, and only when every media part is that fixture's own page"
    ),
    ("analysis/redaction.py", "_encode", "save"): "Pillow into an io.BytesIO buffer (memory)",
    ("analysis/pdf_pages.py", "rasterize", "save"): "Pillow into an io.BytesIO buffer (memory)",
    ("quicksheet/render.py", "_Sheet.finish", "save"): "reportlab canvas on an io.BytesIO (memory)",
}


def _writes_with_mode(call: ast.Call, position: int, *, keyword_only: bool = False) -> bool:
    mode: ast.expr | None = None
    if len(call.args) > position:
        mode = call.args[position]
    for kw in call.keywords:
        if kw.arg == "mode":
            mode = kw.value
    if mode is None:
        return False
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return any(ch in mode.value for ch in "wax+")
    return not keyword_only  # a mode the scan cannot read counts as a write


class _WriteScanner(ast.NodeVisitor):
    def __init__(self, module: str) -> None:
        self.module = module
        self.scope: list[str] = []
        self.sites: dict[tuple[str, str, str], int] = {}

    def _enter(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _enter

    def visit_Call(self, node: ast.Call) -> None:
        name = self._write_name(node)
        if name is not None:
            key = (self.module, ".".join(self.scope) or "<module>", name)
            self.sites.setdefault(key, node.lineno)
        self.generic_visit(node)

    @staticmethod
    def _write_name(node: ast.Call) -> str | None:
        func = node.func
        if isinstance(func, ast.Name):
            return "open" if func.id == "open" and _writes_with_mode(node, 1) else None
        if not isinstance(func, ast.Attribute):
            return None
        if isinstance(func.value, ast.Name) and func.value.id in _WRITE_MODULE_CALLS:
            allowed = _WRITE_MODULE_CALLS[func.value.id]
            if allowed is not None and func.attr not in allowed:
                return None
            if func.attr == "fdopen" and not _writes_with_mode(node, 1):
                return None
            return f"{func.value.id}.{func.attr}"
        if func.attr in _WRITE_METHODS:
            return func.attr
        if func.attr == "open" and _writes_with_mode(node, 0, keyword_only=True):
            return "open"  # Path.open("w"); Image.open(buffer) is a read
        if func.attr == "open" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                return "open" if any(ch in first.value for ch in "wax+") else None
        return None


def server_write_sites(root: Path = SERVER_CODE) -> dict[tuple[str, str, str], int]:
    sites: dict[tuple[str, str, str], int] = {}
    for path in sorted(root.rglob("*.py")):
        scanner = _WriteScanner(path.relative_to(root).as_posix())
        scanner.visit(ast.parse(path.read_text("utf-8"), filename=str(path)))
        sites.update(scanner.sites)
    return sites


def test_write_scanner_sees_every_kind_of_write(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(
        "import os, shutil, sqlite3, tempfile\n"
        "from pathlib import Path\n"
        "def f(p: Path, mode: str) -> None:\n"
        "    open(p, 'w'); open(p, mode); open(p)\n"
        "    p.write_text('x'); p.write_bytes(b''); p.mkdir(); p.touch(); p.open('ab')\n"
        "    os.replace('a', 'b'); os.fdopen(3, 'wb'); os.fdopen(3, 'rb'); shutil.copy('a', 'b')\n"
        "    sqlite3.connect(':memory:'); tempfile.mkstemp()\n"
        "    'a'.replace('a', 'b'); p.read_text(); Image.open(buf)\n",
        "utf-8",
    )
    names = sorted(name for (_, fn, name) in server_write_sites(tmp_path) if fn == "f")
    assert names == sorted(
        ["open", "write_text", "write_bytes", "mkdir", "touch", "os.replace", "os.fdopen",
         "shutil.copy", "sqlite3.connect", "tempfile.mkstemp"]
    )  # fmt: skip


def test_server_writes_only_at_reviewed_sites() -> None:
    """The proof for "Our server does not keep your papers or photos" and the privacy policy's "It
    writes no copy of your paper to disk": server code writes only where a reviewer said why.

    A new file write, temp file, rename, mkdir or SQLite connection in ``proxyhealth_api`` fails
    here until it is added to ``REVIEWED_WRITE_SITES`` with a reason; a stale entry fails too.
    """
    found = server_write_sites()
    unreviewed = {f"{m}:{line} {fn}() {name}" for (m, fn, name), line in found.items()
                  if (m, fn, name) not in REVIEWED_WRITE_SITES}  # fmt: skip
    assert not unreviewed, (
        "server code writes to disk at a site nobody reviewed — keep user content in memory, or "
        f"add the site to REVIEWED_WRITE_SITES with the reason it never holds a paper: {unreviewed}"
    )
    stale = sorted(set(REVIEWED_WRITE_SITES) - set(found))
    assert not stale, f"REVIEWED_WRITE_SITES lists sites that no longer exist: {stale}"
