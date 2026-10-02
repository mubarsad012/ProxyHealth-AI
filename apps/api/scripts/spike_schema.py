"""Day-0 structured-output spike (D-06; AI_PROMPTS §9.4; BUILD_PLAN §5.2 steps 3 and 7).

Sends every model-output schema to the live Gemini API through the real ``AIService`` +
``KeyPool`` + ``GeminiProvider`` stack — or, with ``--provider openai_compat``, to the
OpenAI-compatible endpoint from ``OPENAI_COMPAT_*`` (free-ai-providers §4.4, §4.10: run this
against every fixture before trusting a local model) — and reports, per fixture, which analysis
mode worked:
``single`` (``AnalysisModelOut`` in one call) or ``two_call`` (``TranscriptOut`` then
``ExplainOut``). Pin the printed recommendation in ``.env.example`` (``ANALYSIS_MODE``).

    apps/api/.venv/bin/python apps/api/scripts/spike_schema.py [--fixture ID ...] [--no-tasks]
                                [--provider gemini|openai_compat] [--json]

Exit codes: 0 every probe passed, 1 at least one probe failed, 2 ``GEMINI_KEYS`` is empty (Gemini),
the ``OPENAI_COMPAT_*`` configuration is refused, or an argument is wrong. The fixtures are
synthetic, so any data-use tier may run it (D-01). ``--provider`` defaults to ``openai_compat``
when ``AI_PROVIDER=openai_compat``, else ``gemini``.

Content-free by construction: it prints ids, statuses, HTTP codes, token counts and latencies —
never model output, never a key — and writes nothing except the key pool's own
``var/keypool.json``. The prompts below are short schema-acceptance instructions, not WP2's
product prompts (``ai/prompts/**``): this spike measures whether a schema is *accepted* and fits
``max_output_tokens``; answer quality is the golden eval's job (D-16).
"""

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from proxyhealth_api.ai.failover import (  # noqa: E402
    AIService,
    SchemaFallbackNeeded,
    is_schema_rejection,
    message_of,
    status_of,
)
from proxyhealth_api.ai.gemini import GeminiProvider  # noqa: E402
from proxyhealth_api.ai.keypool import KeyPool  # noqa: E402
from proxyhealth_api.ai.openai_compat import (  # noqa: E402
    OpenAICompatProvider,
    build_openai_compat_stack,
)
from proxyhealth_api.ai.provider import AIProvider, Part, StructuredResult, Task  # noqa: E402
from proxyhealth_api.contracts.enums import Legibility, ModelTier, ThinkingLevel  # noqa: E402
from proxyhealth_api.contracts.model_out import (  # noqa: E402
    AnalysisModelOut,
    ChatModelOut,
    ExplainOut,
    LanguagePackModelOut,
    LanguageResolveOut,
    RewriteOut,
    TaggingModelOut,
    TranscriptOut,
    TroubleshootModelOut,
)
from proxyhealth_api.errors import ApiError  # noqa: E402
from proxyhealth_api.settings import DATA_DIR, Settings  # noqa: E402

FIXTURES_DIR = DATA_DIR / "fixtures"
NO_KEYS_MESSAGE = (
    "spike_schema: GEMINI_KEYS is empty. This spike calls the live Gemini API; set GEMINI_KEYS "
    "in apps/api/.env (billed projects, D-01) and re-run. Nothing was sent."
)

SYSTEM = (
    "You are a careful document reader running a structured-output acceptance test. Return only "
    "JSON that matches the response schema. Copy printed text exactly; never invent phone "
    "numbers, web addresses, dates, names or amounts. Use plain words a 12-year-old can read."
)

# Text-only probes for the tasks that do not need a page (AI_PROMPTS §3 schemas).
TEXT_PROBES: dict[Task, tuple[type[BaseModel], str]] = {
    Task.chat: (
        ChatModelOut,
        "Paper blocks: [b1] Please confirm your address by October 14. "
        "Question: When do I need to answer? Target language: en.",
    ),
    Task.langpack_chunk: (
        LanguagePackModelOut,
        "Translate these UI strings into Spanish (es); keep every key unchanged.\n"
        "btn.retry = Try again\nbtn.save = Save to read later",
    ),
    Task.clerk_translate: (
        LanguagePackModelOut,
        "Translate this one line into Spanish (es); key clerk.need:\n"
        "clerk.need = I need help understanding this letter.",
    ),
    Task.resolve_language: (
        LanguageResolveOut,
        "Which language does the user mean: 'Dari (Afghanistan)'? Give its BCP-47 tag.",
    ),
    Task.tag: (
        TaggingModelOut,
        "Pick resource tags for: a Medicaid renewal letter asking to confirm a home address.",
    ),
    Task.phrasing_rewrite: (
        RewriteOut,
        "Rewrite as information, not advice, in one sentence: 'You must call them today.'",
    ),
}
ANALYZE_USER = (
    "Transcribe every text block on the attached page(s) with ids b1, b2, ... and page numbers, "
    "then explain what the paper asks for, in plain English (target language: en)."
)
TRANSCRIBE_USER = (
    "Transcribe every text block on the attached page(s) with ids b1, b2, ... and page numbers. "
    "Do not explain anything."
)
EXPLAIN_USER = (
    "The transcript of a paper follows, one block per line as [id] text. Explain what the paper "
    "asks for in plain English (target language: en), citing block ids.\n\n{transcript}"
)
TROUBLESHOOT_USER = (
    "The attached screenshot shows a screen someone is stuck on. Explain what it says and the "
    "next steps (target language: en)."
)

Status = Literal[
    "ok", "schema_rejected", "incomplete", "unparsed", "blocked", "quota", "upstream", "error",
    "skipped",
]  # fmt: skip


@dataclass
class Probe:
    """One ``AIService.generate`` call, content-free."""

    task: str
    status: Status
    http: int | None = None
    detail: str = ""
    model: str = ""
    quality: str = ""
    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0
    latency_ms: int = 0


@dataclass
class FixtureRun:
    fixture_id: str
    kind: str
    pages: int
    mode: str  # single | two_call | failed | skipped
    probes: list[Probe] = field(default_factory=list)


@dataclass
class SpikeReport:
    model_pro: str
    model_fast: str
    tasks: list[Probe] = field(default_factory=list)
    fixtures: list[FixtureRun] = field(default_factory=list)


@dataclass(frozen=True)
class SpikeFixture:
    id: str
    kind: str  # document | screenshot
    pages: list[bytes]


class UpstreamRecorder:
    """Wraps a provider and remembers, content-free, whether the last upstream error was a
    schema rejection (``failover`` maps a non-``analyze_single`` schema 400 to a plain 400)."""

    def __init__(self, inner: AIProvider) -> None:
        self.inner = inner
        self.name = inner.name
        self.last_schema_rejection = False

    async def generate_structured(
        self,
        *,
        task: Task,
        tier: ModelTier,
        parts: Sequence[Part],
        system: str,
        schema: type[BaseModel],
        thinking: ThinkingLevel | None,
        media_resolution: Literal["high", "medium"] | None,
        max_output_tokens: int,
        request_id: str,
        slot_index: int | None = None,
        hints: Mapping[str, str] | None = None,
    ) -> StructuredResult:
        try:
            return await self.inner.generate_structured(
                task=task, tier=tier, parts=parts, system=system, schema=schema,
                thinking=thinking, media_resolution=media_resolution,
                max_output_tokens=max_output_tokens, request_id=request_id,
                slot_index=slot_index, hints=hints,
            )  # fmt: skip
        except Exception as exc:
            self.last_schema_rejection = status_of(exc) == 400 and is_schema_rejection(
                message_of(exc)
            )
            raise


# ------------------------------------------------------------------------------ probes


def _classify(exc: ApiError, recorder: UpstreamRecorder) -> tuple[Status, str]:
    details = exc.details or {}
    if exc.status == 400 and recorder.last_schema_rejection:
        return "schema_rejected", "upstream 400 names the schema"
    if exc.status == 422:
        return "blocked", str(details.get("block_reason", ""))
    if exc.status == 502:
        return ("incomplete" if details.get("incomplete") else "unparsed"), exc.code.value
    if exc.status == 429:
        return "quota", f"retry_after={exc.retry_after}"
    if exc.status == 503:
        return "upstream", exc.code.value
    return "error", exc.code.value


async def probe(
    service: AIService,
    recorder: UpstreamRecorder,
    task: Task,
    schema: type[BaseModel],
    parts: Sequence[Part],
    *,
    pages: int = 1,
    is_pdf: bool = False,
) -> tuple[Probe, BaseModel | None]:
    """One call through the real failover stack; returns a content-free ``Probe``."""
    recorder.last_schema_rejection = False
    t0 = time.monotonic()
    request_id = f"spike-{task.value}-{int(time.time() * 1000)}"

    def elapsed() -> int:
        return int((time.monotonic() - t0) * 1000)

    try:
        out = await service.generate(
            task=task, parts=parts, system=SYSTEM, schema=schema, pages=pages, is_pdf=is_pdf,
            request_id=request_id,
        )  # fmt: skip
    except SchemaFallbackNeeded as exc:
        reason = str(exc)
        status: Status = (
            "incomplete" if reason == "incomplete"
            else "unparsed" if reason == "unparsed"
            else "schema_rejected"
        )  # fmt: skip
        http = 400 if status == "schema_rejected" else 200
        return Probe(task.value, status, http=http, detail=reason, latency_ms=elapsed()), None
    except ApiError as exc:
        status, detail = _classify(exc, recorder)
        return Probe(task.value, status, http=exc.status, detail=detail, latency_ms=elapsed()), None
    res = out.result
    return (
        Probe(
            task.value, "ok", http=200, model=res.model_id, quality=out.quality.value,
            attempts=out.attempts, input_tokens=res.usage.input_tokens,
            output_tokens=res.usage.output_tokens, thought_tokens=res.usage.thought_tokens,
            latency_ms=elapsed(),
        ),  # fmt: skip
        res.parsed,
    )


def render_transcript(transcript: TranscriptOut) -> str:
    return "\n".join(f"[{b.id}] {b.text}" for b in transcript.blocks)


async def run_fixture(
    service: AIService, recorder: UpstreamRecorder, fx: SpikeFixture, *, mode: str = "auto"
) -> FixtureRun:
    """AI_PROMPTS §9.4 in miniature: single-call, then two-call on ``SchemaFallbackNeeded``."""
    pages = [Part.of_bytes(png, "image/png") for png in fx.pages]
    run = FixtureRun(fx.id, fx.kind, len(fx.pages), mode="failed")
    n = len(fx.pages)
    if fx.kind == "screenshot":
        p, _ = await probe(
            service, recorder, Task.troubleshoot, TroubleshootModelOut,
            [Part.of_text(TROUBLESHOOT_USER), *pages[:1]],
        )  # fmt: skip
        run.probes.append(p)
        run.mode = "single" if p.status == "ok" else "failed"
        return run
    if mode in ("auto", "single"):
        p, _ = await probe(
            service, recorder, Task.analyze_single, AnalysisModelOut,
            [Part.of_text(ANALYZE_USER), *pages], pages=n,
        )  # fmt: skip
        run.probes.append(p)
        if p.status == "ok":
            run.mode = "single"
            return run
        if mode == "single" or p.status not in ("schema_rejected", "incomplete", "unparsed"):
            return run
    t, parsed = await probe(
        service, recorder, Task.transcribe, TranscriptOut,
        [Part.of_text(TRANSCRIBE_USER), *pages], pages=n,
    )  # fmt: skip
    run.probes.append(t)
    if t.status != "ok" or not isinstance(parsed, TranscriptOut):
        return run
    if parsed.legibility is Legibility.poor:
        run.mode = "two_call"  # unreadable: the pipeline stops after call one (§9.4)
        return run
    user = EXPLAIN_USER.format(transcript=render_transcript(parsed))
    e, _ = await probe(
        service, recorder, Task.explain, ExplainOut, [Part.of_text(user)], pages=n
    )
    run.probes.append(e)
    run.mode = "two_call" if e.status == "ok" else "failed"
    return run


async def run_spike(
    service: AIService,
    recorder: UpstreamRecorder,
    settings: Settings,
    fixtures: Sequence[SpikeFixture],
    *,
    probe_tasks: bool = True,
    mode: str = "auto",
) -> SpikeReport:
    report = SpikeReport(model_pro=settings.active_model_pro, model_fast=settings.active_model_fast)
    if probe_tasks:
        for task, (schema, text) in TEXT_PROBES.items():
            p, _ = await probe(service, recorder, task, schema, [Part.of_text(text)])
            report.tasks.append(p)
        if not any(f.kind == "screenshot" for f in fixtures):
            report.tasks.append(
                Probe(Task.troubleshoot.value, "skipped", detail="no screenshot fixture on disk")
            )
    for fx in fixtures:
        report.fixtures.append(await run_fixture(service, recorder, fx, mode=mode))
    return report


# ------------------------------------------------------------------ fixtures + report


def load_fixtures(root: Path = FIXTURES_DIR, ids: Sequence[str] = ()) -> list[SpikeFixture]:
    """``data/fixtures/<id>/manifest.yaml`` + ``page-<n>.png`` (synthetic papers only)."""
    found: list[SpikeFixture] = []
    if not root.is_dir():
        return found
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")):
        if ids and d.name not in ids:
            continue
        manifest = d / "manifest.yaml"
        if not manifest.is_file():
            continue
        meta = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        count = int(meta.get("pages", 1)) if isinstance(meta, dict) else 1
        kind = str(meta.get("kind", "document")) if isinstance(meta, dict) else "document"
        pngs = [d / f"page-{i}.png" for i in range(1, count + 1)]
        if not all(p.is_file() for p in pngs):
            continue
        found.append(SpikeFixture(d.name, kind, [p.read_bytes() for p in pngs]))
    return found


def recommendation(report: SpikeReport) -> tuple[str, bool]:
    """The ``.env.example`` line to pin and whether every probe passed."""
    docs = [r for r in report.fixtures if r.kind != "screenshot"]
    failed_tasks = [p for p in report.tasks if p.status not in ("ok", "skipped")]
    failed = [r for r in report.fixtures if r.mode == "failed"] or failed_tasks
    stamp = datetime.now(UTC).date().isoformat()
    single = sum(r.mode == "single" for r in docs)
    two = sum(r.mode == "two_call" for r in docs)
    head = f"# spike_schema {stamp} {report.model_pro}: single {single}/{len(docs)}, "
    head += f"two_call {two}/{len(docs)}"
    if failed or not docs:
        why = f"{len(failed)} probe(s) failed" if failed else "no document fixtures"
        return f"{head} -> no recommendation ({why}); keep ANALYSIS_MODE=auto", False
    mode = "two_call" if two else "auto"
    return f"{head} -> ANALYSIS_MODE={mode}", True


def _row(p: Probe) -> str:
    return (
        f"  {p.task:<18} {p.status:<16} http={p.http!s:<4} model={p.model or '-':<24} "
        f"q={p.quality or '-':<8} tok={p.input_tokens}/{p.output_tokens}/{p.thought_tokens} "
        f"{p.latency_ms}ms {p.detail}"
    )


def print_report(report: SpikeReport, *, as_json: bool) -> None:
    line, _ = recommendation(report)
    if as_json:
        print(json.dumps({**asdict(report), "recommendation": line}, indent=2, sort_keys=True))
        return
    print(f"models: pro={report.model_pro} fast={report.model_fast}")
    if report.tasks:
        print("schemas (text-only tasks):")
        for p in report.tasks:
            print(_row(p))
    for r in report.fixtures:
        print(f"fixture {r.fixture_id} ({r.kind}, {r.pages} page(s)): mode={r.mode}")
        for p in r.probes:
            print(_row(p))
    print(line)


# ------------------------------------------------------------------------------ main


def load_settings() -> Settings:
    env = API_ROOT / ".env"
    return Settings(_env_file=env if env.is_file() else None)


def build_service(settings: Settings) -> tuple[AIService, UpstreamRecorder]:
    if settings.ai_provider == "openai_compat":
        compat, keypool = build_openai_compat_stack(settings)
        recorder = UpstreamRecorder(compat)
        return AIService(recorder, keypool, settings), recorder
    recorder = UpstreamRecorder(GeminiProvider(list(settings.gemini_keys), settings))
    gemini_pool = KeyPool.from_settings(settings, lambda: datetime.now(UTC))
    return AIService(recorder, gemini_pool, settings), recorder


def compat_settings(settings: Settings) -> Settings | None:
    """``settings`` as ``AI_PROVIDER=openai_compat``, re-validated so its boot rules run."""
    if settings.ai_provider == "openai_compat":
        return settings
    data = settings.model_dump(exclude_unset=True) | {"ai_provider": "openai_compat"}
    try:
        return Settings(_env_file=None, **data)
    except ValueError as exc:
        print(f"spike_schema: OPENAI_COMPAT_* configuration refused: {exc}", file=sys.stderr)
        return None


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--fixture", action="append", default=[], help="only this fixture id")
    ap.add_argument("--no-tasks", action="store_true", help="skip the text-only schema probes")
    ap.add_argument("--mode", choices=["auto", "single", "two_call"], default="auto")
    ap.add_argument("--provider", choices=["gemini", "openai_compat"], default=None)
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    return ap.parse_args(argv)


def main(argv: Sequence[str] | None = None, *, settings: Settings | None = None) -> int:
    try:
        args = parse_args(argv)
    except SystemExit as exc:  # argparse error / --help
        return 0 if exc.code == 0 else 2
    settings = settings or load_settings()
    provider = args.provider or (
        "openai_compat" if settings.ai_provider == "openai_compat" else "gemini"
    )
    if provider == "openai_compat":
        compat = compat_settings(settings)
        if compat is None:
            return 2
        settings = compat
    elif not settings.gemini_keys:
        print(NO_KEYS_MESSAGE, file=sys.stderr)
        return 2
    fixtures = load_fixtures(ids=args.fixture)
    if args.fixture and len(fixtures) != len(set(args.fixture)):
        missing = sorted(set(args.fixture) - {f.id for f in fixtures})
        print(f"spike_schema: unknown or incomplete fixture(s): {missing}", file=sys.stderr)
        return 2
    service, recorder = build_service(settings)

    async def spike() -> SpikeReport:
        try:
            return await run_spike(
                service, recorder, settings, fixtures, probe_tasks=not args.no_tasks,
                mode=args.mode,
            )  # fmt: skip
        finally:
            if isinstance(recorder.inner, OpenAICompatProvider):
                await recorder.inner.aclose()

    report = asyncio.run(spike())
    print_report(report, as_json=args.json)
    return 0 if recommendation(report)[1] else 1


if __name__ == "__main__":
    raise SystemExit(main())
