"""Golden evaluation (D-16; AI_PROMPTS §12.4, §12.6, §12.9).

Runs every document fixture through ``run_analysis`` (and the screenshot through
``run_troubleshoot``) with the configured provider — the mock by default, Gemini with
``--provider gemini`` and billed keys — and reports per fixture: fact precision/recall against
the fixture's recorded ``out.en.json`` demands (match on ``kind`` + digit-normalised
``value_verbatim``), invented contacts in the *raw* model prose (before the scrubber), the quote
verification rate, schema failures, analysis mode and latency. ``--readability`` applies the
en.json heuristic (average sentence ≤ 12 words; no word > 3 syllables outside the allow-list) to
every golden's ``summary_body_en``, ``clerk_need_en`` and English plan steps.

    apps/api/.venv/bin/python apps/api/scripts/eval_golden.py [--provider mock|gemini]
        [--fixture ID ...] [--lang TAG] [--readability] [--baseline FILE] [--write]
        [--allow-stale] [--json]

Gates (exit 1): any invented contact; quote verification < 0.95; any schema failure; with
``--baseline``, precision down > 0.02 or recall down > 0.05 on any fixture; readability > 5 %
offending sentences. Exit 2: bad arguments, or ``--provider gemini`` without keys, or live goldens
from another prompt date without ``--allow-stale``. Content-free: prints and writes ids, counts
and ratios only (``--write`` → ``var/eval/<date>.json``); never model text.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from datetime import time as dtime
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from pydantic import BaseModel  # noqa: E402

from proxyhealth_api.ai import prompt_loader  # noqa: E402
from proxyhealth_api.ai.failover import AIService  # noqa: E402
from proxyhealth_api.ai.provider import AIProvider, StructuredResult, Task  # noqa: E402
from proxyhealth_api.analysis.contacts_filter import AllowList, find_contacts  # noqa: E402
from proxyhealth_api.analysis.pipeline import PipelineDeps, run_analysis  # noqa: E402
from proxyhealth_api.analysis.verify import digit_runs, normalize  # noqa: E402
from proxyhealth_api.contracts.analysis import AnalyzeRequest  # noqa: E402
from proxyhealth_api.contracts.model_out import AnalysisModelOut, ExplainOut  # noqa: E402
from proxyhealth_api.demo.fixtures import Fixture, FixtureStore  # noqa: E402
from proxyhealth_api.errors import ApiError  # noqa: E402
from proxyhealth_api.main import build_provider  # noqa: E402
from proxyhealth_api.resources.loader import ResourceRepo  # noqa: E402
from proxyhealth_api.resources.rules_repo import RulesRepo  # noqa: E402
from proxyhealth_api.settings import DATA_DIR, Settings  # noqa: E402

VERIFY_GATE = 0.95
PRECISION_DROP = 0.02
RECALL_DROP = 0.05
READABILITY_GATE = 0.05
MAX_WORDS = 12
MAX_SYLLABLES = 3
ALLOWLIST = API_ROOT / "tests" / "unit" / "readability_allowlist.txt"
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
_VOWELS_RE = re.compile(r"[aeiouy]+")


class Capturing:
    """Wraps the provider to keep the raw analysis output (for the invented-contact count)."""

    def __init__(self, inner: AIProvider) -> None:
        self.inner = inner
        self.name = inner.name
        self.raw: list[BaseModel] = []

    async def generate_structured(self, **kwargs: Any) -> StructuredResult:
        res = await self.inner.generate_structured(**kwargs)
        if kwargs.get("task") in (Task.analyze_single, Task.explain) and res.parsed is not None:
            self.raw.append(res.parsed)
        return res


@dataclass
class Row:
    fixture: str
    lang: str
    ok: bool = True
    error: str | None = None
    mode: str | None = None
    precision: float = 0.0
    recall: float = 0.0
    verify_rate: float = 1.0
    invented_contacts: int = 0
    contacts_stripped: int = 0
    phrasing_rewrites: int = 0
    latency_ms: int = 0


def fact_key(kind: str, value: str) -> tuple[str, str]:
    digits = "".join(digit_runs(value))
    return kind, digits or normalize(value).casefold()


def prose_of(out: BaseModel) -> list[str]:
    """Every model-authored string of an analysis output (quotes and blocks excluded)."""
    if not isinstance(out, AnalysisModelOut | ExplainOut):
        return []
    texts = [out.summary_title, out.summary_body, out.summary_body_en, out.clerk_need_en]
    texts += [d.text for d in out.demands] + [p.text for p in out.plan_steps]
    texts += [g.explanation for g in out.glossary] + [f.text for f in out.red_flags]
    return texts + list(out.questions_to_ask)


def invented_contacts(raw: Sequence[BaseModel], transcript: str) -> int:
    allow = AllowList.build(transcript)
    return sum(
        1
        for out in raw
        for text in prose_of(out)
        for match in find_contacts(text, include_orgs=False)
        if not allow.allows(match)
    )


async def evaluate(fx: Fixture, lang: str, settings: Settings, store: FixtureStore) -> Row:
    row = Row(fx.id, lang)
    inner, keypool = build_provider(settings, store, lambda: datetime.now(UTC))
    provider = Capturing(inner)
    moment = datetime.combine(fx.today, dtime(14, 0), tzinfo=UTC)
    deps = PipelineDeps(
        settings=settings, ai=AIService(provider, keypool, settings), resources=RESOURCES,
        rules=RULES, fixtures=store, request_id=f"eval-{fx.id}",
        data_use_tier=settings.data_use_tier, clock=lambda: moment,
    )  # fmt: skip
    req = AnalyzeRequest(
        pages=[], target_language=lang, client_platform="web", demo_sample_id=fx.id,
        state=str(fx.expected.get("state")) if fx.expected.get("state") else None,
    )  # fmt: skip
    started = time.perf_counter()
    try:
        result = await run_analysis(req, deps)
    except ApiError as exc:
        row.ok, row.error = False, exc.code.value
        return row
    row.latency_ms = int((time.perf_counter() - started) * 1000)
    row.mode = result.model_meta.analysis_mode.value
    golden = fx.analysis_out("en")
    golden_demands = golden.demands if golden else []
    expected = {fact_key(d.kind.value, d.value_verbatim) for d in golden_demands}
    got = {fact_key(d.kind.value, d.value_verbatim) for d in result.demands}
    row.precision = len(got & expected) / len(got) if got else float(not expected)
    row.recall = len(got & expected) / len(expected) if expected else 1.0
    checked = len(result.demands) + len(result.unverified)
    row.verify_rate = len(result.demands) / checked if checked else 1.0
    row.invented_contacts = invented_contacts(provider.raw, fx.transcript)
    row.contacts_stripped = result.verification.contacts_stripped
    row.phrasing_rewrites = result.verification.phrasing_rewrites
    return row


def syllables(word: str) -> int:
    w = word.lower().strip("'-")
    count = len(_VOWELS_RE.findall(w))
    if w.endswith("e") and not w.endswith(("le", "ee")) and count > 1:
        count -= 1
    return max(count, 1)


def readability(store: FixtureStore, allow: set[str]) -> tuple[int, int]:
    """(offending sentences, sentences) over every golden's English prose."""
    bad = total = 0
    for fx in store.all():
        out = fx.analysis_out("en")
        if out is None:
            continue
        for text in [out.summary_body_en, out.clerk_need_en, *(p.text for p in out.plan_steps)]:
            for sentence in (s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()):
                words = _WORD_RE.findall(sentence)
                long_words = [
                    w for w in words if w.lower() not in allow and syllables(w) > MAX_SYLLABLES
                ]
                total += 1
                bad += int(len(words) > MAX_WORDS or bool(long_words))
    return bad, total


def gate_failures(rows: Sequence[Row], baseline: Mapping[str, Mapping[str, Any]]) -> list[str]:
    fails: list[str] = []
    for r in rows:
        key = f"{r.fixture}:{r.lang}"
        if not r.ok:
            fails.append(f"{key} schema/model failure {r.error}")
            continue
        if r.invented_contacts:
            fails.append(f"{key} invented contacts {r.invented_contacts}")
        if r.verify_rate < VERIFY_GATE:
            fails.append(f"{key} quote verification {r.verify_rate:.2f} < {VERIFY_GATE}")
        base = baseline.get(key)
        if base and r.precision < float(base.get("precision", 0)) - PRECISION_DROP:
            fails.append(f"{key} precision {r.precision:.2f} (baseline {base['precision']:.2f})")
        if base and r.recall < float(base.get("recall", 0)) - RECALL_DROP:
            fails.append(f"{key} recall {r.recall:.2f} (baseline {base['recall']:.2f})")
    return fails


def stale(store: FixtureStore, ids: Sequence[str]) -> list[str]:
    current = prompt_loader.prompts_version().split(".")[0]
    out = []
    for fid in ids:
        fx = store.get(fid)
        version = str(fx.meta("en").get("prompts_version", "")) if fx else ""
        if version.split(".")[0] != current:
            out.append(fid)
    return out


RESOURCES = ResourceRepo.load(DATA_DIR / "resources")
RULES = RulesRepo.load(DATA_DIR / "rules")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--provider", choices=("mock", "gemini"), default=None)
    ap.add_argument("--fixture", action="append", default=[])
    ap.add_argument("--lang", default="en")
    ap.add_argument("--readability", action="store_true")
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--allow-stale", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    store = FixtureStore.load(DATA_DIR / "fixtures")
    docs = [fx for fx in store.all() if fx.kind == "document"]
    ids = args.fixture or [fx.id for fx in docs]
    unknown = [fid for fid in ids if store.get(fid) is None]
    if unknown:
        print(f"unknown fixture(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    env = Settings()
    provider = args.provider or ("mock" if env.ai_provider == "mock" else "gemini")
    with tempfile.TemporaryDirectory() as tmp:
        overrides: dict[str, Any] = {"ai_provider": provider}
        if provider == "mock":
            overrides |= {"var_dir": Path(tmp), "mock_latency_min_ms": 0,
                          "mock_latency_max_ms": 0}  # fmt: skip
        settings = env.model_copy(update=overrides)
        if provider == "gemini":
            if not settings.gemini_keys:
                print("GEMINI_KEYS is empty; live evaluation needs billed keys.", file=sys.stderr)
                return 2
            old = stale(store, ids)
            if old and not args.allow_stale:
                print(f"goldens from another prompt date: {old} (--allow-stale)", file=sys.stderr)
                return 2
        rows = [
            asyncio.run(evaluate(fx, args.lang, settings, store))
            for fx in (store.get(fid) for fid in ids)
            if fx is not None and fx.kind == "document" and args.lang in fx.languages
        ]
    baseline: dict[str, dict[str, Any]] = {}
    if args.baseline:
        data = json.loads(args.baseline.read_text(encoding="utf-8"))
        baseline = {f"{r['fixture']}:{r['lang']}": r for r in data.get("rows", [])}
    fails = gate_failures(rows, baseline)
    report: dict[str, Any] = {
        "provider": provider,
        "prompts_version": prompt_loader.prompts_version(),
        "rows": [asdict(r) for r in rows],
    }
    if args.readability:
        allow = set()
        if ALLOWLIST.is_file():
            allow = {w.strip().lower() for w in ALLOWLIST.read_text("utf-8").split() if w.strip()}
        bad, total = readability(store, allow)
        share = bad / total if total else 0.0
        report["readability"] = {"offending": bad, "sentences": total, "share": round(share, 3)}
        if share > READABILITY_GATE:
            fails.append(f"readability {share:.1%} offending sentences > {READABILITY_GATE:.0%}")
    report["failures"] = fails
    if args.write:
        out_dir = settings.var_dir / "eval"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{datetime.now(UTC).date().isoformat()}.json"
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{'fixture':32} {'lang':5} {'mode':9} {'P':>5} {'R':>5} {'ver':>5} "
              f"{'inv':>4} {'strip':>5} {'rew':>4} {'ms':>6}")  # fmt: skip
        for r in rows:
            mode = r.mode or r.error or "-"
            print(
                f"{r.fixture:32} {r.lang:5} {mode:9} {r.precision:5.2f} {r.recall:5.2f} "
                f"{r.verify_rate:5.2f} {r.invented_contacts:4d} {r.contacts_stripped:5d} "
                f"{r.phrasing_rewrites:4d} {r.latency_ms:6d}"
            )
        if "readability" in report:
            print(f"readability: {report['readability']}")
        for f in fails:
            print(f"GATE: {f}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
