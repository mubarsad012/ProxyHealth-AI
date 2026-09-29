"""Link-health checker for the vetted resource DB (RESOURCE_DB §9; weekly CI + on demand).

usage: check_links.py [--write] [--freshness] [--only <id>] [--json report.json]

* Loads the repo exactly like the server, so a broken YAML fails here first.
* GETs every ``url`` / ``alt_urls`` item with a browser User-Agent, ``Accept-Language: en-US``,
  20 s timeout and ≤ 5 redirects **within the same registrable domain**; an off-site redirect is
  reported as ``redirected_offsite`` for human review (not followed, never written).
* ``--write`` rewrites only the ``link_health:`` value inside the entry's ``- {id: …`` block
  (never ``verified_on``/``phone``); ``transient`` results are never written.
* ``--freshness`` exits 1 when a non-broken entry (including one already past 365 days) is older
  than 120 days (``manual_verify``: 90).

Never run by the unit tests (network). Nothing user-related is read or written.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from proxyhealth_api.contracts.enums import LinkHealth, VerificationMethod  # noqa: E402
from proxyhealth_api.contracts.resources import Resource  # noqa: E402
from proxyhealth_api.resources.loader import ResourceRepo  # noqa: E402

RESOURCES_DIR = API_ROOT / "data" / "resources"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)
TIMEOUT_S = 20.0
MAX_REDIRECTS = 5
MIN_TEXT_CHARS = 500
FRESH_DAYS = 120
FRESH_DAYS_MANUAL = 90
JS_MARKERS = ("<noscript", 'id="root"', "ng-app")
CHALLENGE_MARKERS = ("cf-chl", "_Incapsula_", "Just a moment")
WRITABLE = {"ok", "js_rendered", "unknown_403", "unverified", "broken"}
TAG_RE = re.compile(r"<(script|style)\b.*?</\1>|<[^>]+>", re.S | re.I)


@dataclass
class Finding:
    resource_id: str
    url: str
    # ok · js_rendered · unknown_403 · unverified · broken · transient · redirected_offsite
    status: str
    detail: str = ""
    drift: list[str] = field(default_factory=list)


def registrable_domain(url: str) -> str:
    """Last two host labels (``www.uscis.gov`` → ``uscis.gov``); enough for .gov/.org."""
    host = (urlsplit(url).hostname or "").lower()
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def visible_text(html: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", html)).strip()


def classify(status_code: int, body: str) -> str:
    """RESOURCE_DB §9 step 3 → proposed ``link_health`` (or ``transient``)."""
    if any(marker in body for marker in CHALLENGE_MARKERS):
        return "unverified"
    if status_code in (401, 403):
        return "unknown_403"
    if status_code in (404, 410):
        return "broken"
    if status_code >= 500:
        return "transient"
    if 200 <= status_code < 300:
        text = visible_text(body)
        if len(text) >= MIN_TEXT_CHARS:
            return "ok"
        if any(marker in body for marker in JS_MARKERS):
            return "js_rendered"
        return "ok" if text else "js_rendered"
    return "transient"


def digits_only(text: str) -> str:
    return re.sub(r"\D", "", text)


def content_drift(expect: list[str], text: str) -> list[str]:
    """``x_meta.expect_text`` phrases missing from the page (digits compared bare)."""
    missing: list[str] = []
    flat_digits = digits_only(text)
    lowered = text.casefold()
    for phrase in expect:
        if digits_only(phrase) and len(digits_only(phrase)) >= 3:
            if digits_only(phrase) not in flat_digits:
                missing.append(phrase)
        elif phrase.casefold() not in lowered:
            missing.append(phrase)
    return missing


def fetch(client: httpx.Client, resource_id: str, url: str, expect: list[str]) -> Finding:
    """GET with same-domain redirects only (followed manually so off-site hops are reported)."""
    current = url
    home = registrable_domain(url)
    try:
        for _hop in range(MAX_REDIRECTS + 1):
            response = client.get(current)
            if response.is_redirect:
                target = urljoin(current, response.headers.get("location", ""))
                if registrable_domain(target) != home:
                    return Finding(resource_id, url, "redirected_offsite", target)
                current = target
                continue
            body = response.text
            status = classify(response.status_code, body)
            finding = Finding(resource_id, url, status, f"HTTP {response.status_code}")
            if status == "ok" and expect:
                finding.drift = content_drift(expect, visible_text(body))
            return finding
        return Finding(resource_id, url, "transient", "too many redirects")
    except httpx.ConnectError as exc:
        return Finding(resource_id, url, "broken", f"connect: {type(exc).__name__}")
    except httpx.TimeoutException:
        return Finding(resource_id, url, "transient", "timeout")
    except httpx.HTTPError as exc:
        return Finding(resource_id, url, "transient", type(exc).__name__)


def stale(repo: ResourceRepo, today: date) -> list[Resource]:
    """RESOURCE_DB §9 step 6 over every non-broken entry — ``repo.all()``, not ``active()``,
    which already hides entries older than 365 days (the stalest ones must be flagged too)."""
    out: list[Resource] = []
    for res in repo.all():
        limit = (
            FRESH_DAYS_MANUAL
            if res.verification_method == VerificationMethod.manual_verify
            else FRESH_DAYS
        )
        if (today - res.verified_on).days > limit:
            out.append(res)
    return out


def entry_file(resource_id: str) -> Path | None:
    pattern = re.compile(rf'^- \{{?\s*id:\s*"?{re.escape(resource_id)}"?\s*[,\n]', re.M)
    for path in sorted(RESOURCES_DIR.rglob("*.yaml")):
        if not path.name.startswith("_") and pattern.search(path.read_text(encoding="utf-8")):
            return path
    return None


def write_link_health(resource_id: str, value: str) -> bool:
    """Regex-replace the single ``link_health:`` inside the entry block (RESOURCE_DB §9 step 5)."""
    path = entry_file(resource_id)
    if path is None:
        return False
    text = path.read_text(encoding="utf-8")
    start_re = re.compile(rf'^- \{{?\s*id:\s*"?{re.escape(resource_id)}"?\s*[,\n]', re.M)
    start = start_re.search(text)
    if start is None:
        return False
    nxt = re.compile(r"^- ", re.M).search(text, start.end())
    end = nxt.start() if nxt else len(text)
    block = text[start.start() : end]
    new_block, n = re.subn(r"(link_health:\s*)([a-z_0-9]+)", rf"\g<1>{value}", block, count=1)
    if n != 1 or new_block == block:
        return False
    path.write_text(text[: start.start()] + new_block + text[end:], encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--write", action="store_true", help="update link_health in the YAML")
    parser.add_argument("--freshness", action="store_true", help="fail on stale verified_on")
    parser.add_argument("--only", metavar="ID", help="check a single resource id")
    parser.add_argument("--json", metavar="REPORT", type=Path, help="write a JSON report")
    args = parser.parse_args(argv)

    today = date.today()
    repo = ResourceRepo.load(RESOURCES_DIR, today=today)
    if args.freshness:
        old = stale(repo, today)
        for res in old:
            print(f"stale  {res.id:32s} verified_on={res.verified_on}")
        print(f"{len(old)} stale of {len(repo.all())} non-broken entries")
        return 1 if old else 0

    resources = [r for r in repo.loaded() if args.only in (None, r.id)]
    if args.only and not resources:
        print(f"unknown id {args.only!r}", file=sys.stderr)
        return 2
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-US"}
    findings: list[Finding] = []
    with httpx.Client(headers=headers, timeout=TIMEOUT_S, follow_redirects=False) as client:
        for res in resources:
            x_meta = repo.x_meta(res.id) or {}
            expect = [str(t) for t in x_meta.get("expect_text", [])]
            for index, url in enumerate((res.url, *res.alt_urls)):
                finding = fetch(client, res.id, url, expect if index == 0 else [])
                findings.append(finding)
                drift = f" drift={finding.drift}" if finding.drift else ""
                print(f"{finding.status:18s} {res.id:32s} {url}  {finding.detail}{drift}")
            primary = next(f for f in findings if f.resource_id == res.id)
            if args.write and primary.status in WRITABLE and primary.status != res.link_health:
                if write_link_health(res.id, primary.status):
                    print(f"  wrote link_health: {primary.status} for {res.id}")

    report: dict[str, int] = {"checked": len(findings)}
    for status in (*(h.value for h in LinkHealth), "transient", "redirected_offsite"):
        report[status] = sum(1 for f in findings if f.status == status)
    report["content_drift"] = sum(1 for f in findings if f.drift)
    report["stale"] = len(stale(repo, today))
    print(json.dumps(report, sort_keys=True))
    if args.json:
        detail = [f.__dict__ for f in findings]
        args.json.write_text(json.dumps({**report, "findings": detail}, indent=2), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
