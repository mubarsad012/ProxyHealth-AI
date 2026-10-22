"""Check the configured AI provider end to end on SAMPLE papers (free-ai-providers §4.10).

Runs sample fixtures (default ``medicaid_address_confirmation``) through the real analysis
pipeline (``run_analysis``) with the provider configured in ``apps/api/.env`` — typically
``AI_PROVIDER=openai_compat`` against a local Ollama/LM Studio — and prints, per paper: whether
the output passed schema validation (and in which analysis mode), verified and rejected facts,
latency, and which structured-output mode the endpoint accepted (``json_schema``,
``json_object`` or ``prompt``; ``+repair`` when the one repair retry was needed). On a loopback
``openai_compat`` endpoint it also fits this machine's speed (page read in seconds, then tokens
per second) and warns when a runaway reply would hit ``OPENAI_COMPAT_TIMEOUT_S`` before
``OPENAI_COMPAT_MAX_OUTPUT_TOKENS`` (LOCAL_AI.md §5), naming a cap that fits.

    apps/api/.venv/bin/python apps/api/scripts/provider_check.py [--fixture ID ...] [--lang TAG]
        [--image PATH] [--json]

``--image PATH`` reads one of YOUR OWN photos (JPEG/PNG/PDF) — allowed only on the ``local`` and
``attested`` tiers, where real papers may reach the model. It is read into memory only.

Content-free by construction: prints ids, counts, statuses, token counts and latencies, never
model text, never a key, never the base URL. Nothing is written to disk: the key pool lives in a
temporary directory that is deleted on exit. Exit 0 when every paper passed, 1 when one failed,
2 on bad arguments (unknown fixture, ``--image`` on a samples-only tier, unreadable file).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from proxyhealth_api.ai.failover import AIService  # noqa: E402
from proxyhealth_api.ai.provider import AIProvider, StructuredResult  # noqa: E402
from proxyhealth_api.analysis.pipeline import PipelineDeps, run_analysis  # noqa: E402
from proxyhealth_api.analysis.uploads import sniff_mime  # noqa: E402
from proxyhealth_api.contracts.analysis import AnalyzeRequest  # noqa: E402
from proxyhealth_api.contracts.common import PageInput  # noqa: E402
from proxyhealth_api.contracts.enums import DataUseTier  # noqa: E402
from proxyhealth_api.demo.fixtures import FixtureStore  # noqa: E402
from proxyhealth_api.errors import ApiError  # noqa: E402
from proxyhealth_api.main import build_provider  # noqa: E402
from proxyhealth_api.resources.loader import ResourceRepo  # noqa: E402
from proxyhealth_api.resources.rules_repo import RulesRepo  # noqa: E402
from proxyhealth_api.settings import DATA_DIR, Settings  # noqa: E402

DEFAULT_FIXTURE = "medicaid_address_confirmation"
RESOURCES = ResourceRepo.load(DATA_DIR / "resources")
RULES = RulesRepo.load(DATA_DIR / "rules")
REAL_PAPER_TIERS = frozenset({DataUseTier.local, DataUseTier.attested})
# Ollama's default context is 4k tokens below 24 GiB of memory (§3.3): a prompt this close to it
# was probably cut short.
OLLAMA_DEFAULT_CONTEXT = 4096
CONTEXT_WARN_FROM = 3900
# LOCAL_AI.md §5: latency ≈ page read + output tokens / decode speed, fitted on the page-reading
# calls. With one call the page read is taken as DEFAULT_PAGE_READ_S (≈ 34 s measured on an M4).
SPEED_TASKS = frozenset({"analyze_single", "transcribe"})
DEFAULT_PAGE_READ_S = 35.0
TIMEOUT_SLACK_S = 10  # the cap must be reached at least this long before the timeout
CAP_MARGIN_S = 30  # the suggested cap ends this long before the timeout


@dataclass
class Call:
    """One provider call, content-free."""

    task: str
    json_mode: str | None
    repaired: bool
    parsed: bool
    incomplete: bool
    blocked: bool
    input_tokens: int
    output_tokens: int
    latency_ms: int


@dataclass
class PaperRun:
    paper: str
    ok: bool = False
    error: str | None = None
    schema_valid: bool = False
    analysis_mode: str | None = None
    verified_facts: int = 0
    rejected_facts: int = 0
    latency_ms: int = 0
    calls: list[Call] = field(default_factory=list)


class Recorder:
    """Wraps the provider and keeps content-free facts about every call."""

    def __init__(self, inner: AIProvider) -> None:
        self.inner = inner
        self.name = inner.name
        self.calls: list[Call] = []

    async def generate_structured(self, **kwargs: Any) -> StructuredResult:
        t0 = time.perf_counter()
        res = await self.inner.generate_structured(**kwargs)
        mode = getattr(self.inner, "last_json_mode", None)
        self.calls.append(
            Call(
                task=str(getattr(kwargs.get("task"), "value", kwargs.get("task"))),
                json_mode=mode if isinstance(mode, str) else None,
                repaired=bool(getattr(self.inner, "last_repaired", False)),
                parsed=res.parsed is not None, incomplete=res.incomplete,
                blocked=res.blocked_reason is not None,
                input_tokens=res.usage.input_tokens, output_tokens=res.usage.output_tokens,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )  # fmt: skip
        )
        return res


class NotAPaper(ValueError):
    """The file's magic bytes match no accepted page type."""


def image_request(path: Path, lang: str) -> AnalyzeRequest:
    """One page from the user's own file, read into memory only."""
    data = path.read_bytes()
    mime = sniff_mime(data)
    if mime is None:
        raise NotAPaper("not a JPEG, PNG, WebP, HEIC or PDF file")
    page = PageInput.model_validate(
        {"mime_type": mime, "data_base64": base64.b64encode(data).decode("ascii")}
    )
    return AnalyzeRequest(pages=[page], target_language=lang, client_platform="web")


async def run_paper(
    settings: Settings, store: FixtureStore, paper: str, req: AnalyzeRequest
) -> PaperRun:
    run = PaperRun(paper)
    inner, keypool = build_provider(settings, store, lambda: datetime.now(UTC))
    recorder = Recorder(inner)
    deps = PipelineDeps(
        settings=settings, ai=AIService(recorder, keypool, settings),
        resources=RESOURCES, rules=RULES, fixtures=store, request_id=f"check-{paper}",
        data_use_tier=settings.data_use_tier, clock=lambda: datetime.now(UTC),
    )  # fmt: skip
    started = time.perf_counter()
    try:
        result = await run_analysis(req, deps)
    except ApiError as exc:
        run.error = f"{exc.status} {exc.code.value}"
    else:
        run.ok = run.schema_valid = True
        run.analysis_mode = result.model_meta.analysis_mode.value
        run.verified_facts = len(result.demands)
        run.rejected_facts = len(result.unverified)
    finally:
        run.latency_ms = int((time.perf_counter() - started) * 1000)
        run.calls = recorder.calls
        close = getattr(inner, "aclose", None)
        if close is not None:
            await close()
    return run


def context_warning(settings: Settings, runs: Sequence[PaperRun]) -> str | None:
    if settings.ai_provider != "openai_compat" or not settings.openai_compat_is_loopback:
        return None
    low, high = CONTEXT_WARN_FROM, OLLAMA_DEFAULT_CONTEXT
    near = [c for r in runs for c in r.calls if low <= c.input_tokens <= high]
    if not near:
        return None
    return (
        f"{len(near)} call(s) used {CONTEXT_WARN_FROM}-{OLLAMA_DEFAULT_CONTEXT} prompt tokens: "
        "Ollama's default 4k context probably cut the prompt. Set OLLAMA_CONTEXT_LENGTH=16384 "
        "(free-ai-providers §3.3) and restart Ollama."
    )


@dataclass(frozen=True)
class Speed:
    """This machine's measured speed: ``latency_s ≈ page_read_s + tokens * s_per_token``."""

    page_read_s: float
    s_per_token: float
    calls: int

    def report(self) -> dict[str, float | int]:
        return {
            "page_read_s": round(self.page_read_s, 1),
            "decode_tok_s": round(1 / self.s_per_token, 1),
            "calls": self.calls,
        }


def measure_speed(runs: Sequence[PaperRun]) -> Speed | None:
    """Least-squares fit over the repair-free page-reading calls; ``None`` when nothing usable
    was measured."""
    points = [
        (float(c.output_tokens), c.latency_ms / 1000)
        for r in runs for c in r.calls
        if c.task in SPEED_TASKS and c.output_tokens > 0 and not c.repaired
    ]  # fmt: skip
    if not points:
        return None
    xs = [x for x, _ in points]
    if len(set(xs)) >= 2:
        mx, my = sum(xs) / len(xs), sum(y for _, y in points) / len(points)
        slope = sum((x - mx) * (y - my) for x, y in points) / sum((x - mx) ** 2 for x in xs)
        intercept = my - slope * mx
    else:
        intercept = DEFAULT_PAGE_READ_S
        slope = sum((y - intercept) / x for x, y in points) / len(points)
    if slope <= 0:
        return None
    return Speed(max(intercept, 0.0), slope, len(points))


def speed_warning(settings: Settings, speed: Speed | None) -> str | None:
    """Loopback ``openai_compat`` only: the output cap must be reached before the timeout, so a
    runaway reply ends as ``incomplete`` (→ the two-call fallback), not as a 503 that a retry at
    temperature 0 repeats. Numbers and setting names only."""
    if settings.ai_provider != "openai_compat" or not settings.openai_compat_is_loopback:
        return None
    if speed is None:
        return None
    cap, timeout = settings.openai_compat_output_cap, settings.openai_compat_timeout
    if speed.page_read_s + cap * speed.s_per_token <= timeout - TIMEOUT_SLACK_S:
        return None
    safe = int((timeout - speed.page_read_s - CAP_MARGIN_S) / speed.s_per_token)
    return (
        f"a runaway reply would hit OPENAI_COMPAT_TIMEOUT_S={timeout} before "
        f"OPENAI_COMPAT_MAX_OUTPUT_TOKENS={cap} at this speed; set "
        f"OPENAI_COMPAT_MAX_OUTPUT_TOKENS={max(safe, 256)} or lower, or raise "
        "OPENAI_COMPAT_TIMEOUT_S and FAILOVER_DEADLINE_S (LOCAL_AI.md §5)."
    )


def header(settings: Settings) -> dict[str, Any]:
    head: dict[str, Any] = {
        "provider": settings.provider.value,
        "data_use_tier": settings.data_use_tier.value,
        "model_pro": settings.active_model_pro,
        "model_fast": settings.active_model_fast,
    }
    if settings.ai_provider == "openai_compat":
        head |= {
            "host": settings.openai_compat_host,
            "json_mode_setting": settings.openai_compat_json_mode,
            "reasoning": settings.openai_compat_reasoning,
            "timeout_s": settings.openai_compat_timeout,
            "max_output_tokens": settings.openai_compat_output_cap,
            "max_images": settings.openai_compat_image_cap,
        }
    return head


def print_text(
    head: dict[str, Any], runs: Sequence[PaperRun], warnings: Sequence[str],
    speed: Speed | None = None,
) -> None:  # fmt: skip
    print(" ".join(f"{k}={v}" for k, v in head.items()))
    for r in runs:
        status = "ok" if r.ok else f"FAILED ({r.error})"
        print(
            f"{r.paper}: {status} schema_valid={'yes' if r.schema_valid else 'no'} "
            f"mode={r.analysis_mode or '-'} verified={r.verified_facts} "
            f"rejected={r.rejected_facts} latency={r.latency_ms}ms"
        )
        for c in r.calls:
            mode = (c.json_mode or "-") + ("+repair" if c.repaired else "")
            state = "blocked" if c.blocked else "valid" if c.parsed else "invalid"
            print(
                f"  {c.task:<18} json={mode:<20} {state:<8} incomplete={c.incomplete} "
                f"tok={c.input_tokens}/{c.output_tokens} {c.latency_ms}ms"
            )
    if speed is not None:
        print(
            f"speed: page read ~{speed.page_read_s:.0f} s, then ~{1 / speed.s_per_token:.1f} "
            f"tokens/s ({speed.calls} call(s))"
        )
    for warning in warnings:
        print(f"WARNING: {warning}")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--fixture", action="append", default=[], help="sample fixture id")
    ap.add_argument("--image", type=Path, help="your own paper (local/attested tiers only)")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    store = FixtureStore.load(DATA_DIR / "fixtures")
    ids = args.fixture or ([] if args.image else [DEFAULT_FIXTURE])
    unknown = [f for f in ids if (fx := store.get(f)) is None or fx.kind != "document"]
    if unknown:
        print(f"provider_check: unknown document fixture(s): {unknown}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(var_dir=Path(tmp))  # the key pool's file dies with the temp dir
        papers: list[tuple[str, AnalyzeRequest]] = [
            (f, AnalyzeRequest(pages=[], target_language=args.lang, client_platform="web",
                               demo_sample_id=f))
            for f in ids
        ]  # fmt: skip
        if args.image is not None:
            if settings.data_use_tier not in REAL_PAPER_TIERS:
                print(
                    "provider_check: --image needs OPENAI_COMPAT_DATA_TIER=local or attested "
                    f"(this server runs tier {settings.data_use_tier.value}); use sample papers.",
                    file=sys.stderr,
                )
                return 2
            try:
                papers.append(("image", image_request(args.image, args.lang)))
            except OSError:
                why = "the file could not be read"
            except NotAPaper as exc:
                why = str(exc)
            except ValidationError:  # never printed: its text could carry the file's bytes
                why = "the page was refused"
            else:
                why = ""
            if why:
                print(f"provider_check: cannot use --image: {why}", file=sys.stderr)
                return 2
        runs = [asyncio.run(run_paper(settings, store, name, req)) for name, req in papers]
        head = header(settings)
        warning = context_warning(settings, runs)
        speed = measure_speed(runs) if settings.ai_provider == "openai_compat" else None
        slow = speed_warning(settings, speed)
    if args.json:
        report = {
            **head, "papers": [asdict(r) for r in runs], "warning": warning,
            "speed": speed.report() if speed else None, "speed_warning": slow,
        }  # fmt: skip
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(head, runs, [w for w in (warning, slow) if w], speed)
    return 0 if all(r.ok for r in runs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
