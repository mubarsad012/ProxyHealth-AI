"""End-to-end smoke test against a running API in mock mode (BUILD_PLAN §5.9 step 2).

Standard library only (``urllib``), so it runs against any deployment with nothing installed:

    apps/api/.venv/bin/python apps/api/scripts/smoke.py --base-url http://127.0.0.1:8000

``scripts/smoke.sh`` (``make smoke``) boots the API with ``AI_PROVIDER=mock`` on a free port, runs
this script, and always stops the server. Checks, in order: ``/health``, ``/v1/config``, the ``en``
language pack (ETag + 304), the demo list (18 samples) and one page PNG, ``/v1/analyze`` with
``demo_sample_id`` for every document sample in every ``available_target_language``,
``/v1/troubleshoot`` for the screenshot sample **with its PNG bytes**, grounded chat (a date
question) and a refusal (an outcome question), ``/v1/resources/match``, ``/v1/rules`` (12 rules),
``/v1/quicksheet/pdf`` (LTR and RTL, ``%PDF-`` magic bytes) and ``/v1/feedback``.

Every JSON answer is scanned for ``[contact removed`` (D-10: the mock never trips the contact
filter), and every ``Demand`` must carry ``source_quote``/``span_ids``/``page``/``confidence``/
``verified`` (D-09). Urgency is compared with BUILD_PLAN Appendix D only when it cannot drift with
the calendar: a sample with no date must be ``info``, and a dated sample is checked only when its
``days_until`` is counted from the sample's pinned ``today`` (``manifest.yaml``); otherwise the
script prints a note and skips that assertion. Exit status: 0 = all checks passed, 1 = a failure.
"""

import argparse
import base64
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "data" / "fixtures"
CONTACT_REMOVED = "[contact removed"
ADAPTING = "Adapting system environment to your language..."
CONFIDENCE = {"high", "medium", "low"}
URGENCY = {"emergency", "critical", "high", "medium", "info"}

# BUILD_PLAN Appendix D — urgency levels per sample (None = no urgency assertion in the table).
APPENDIX_D_URGENCY: dict[str, set[str] | None] = {
    "medicaid_address_confirmation": {"high"},
    "uscis_i797c_receipt_i765": {"info"},
    "uscis_rfe_87d": {"high", "critical"},
    "nta_hearing_date": {"critical", "high"},
    "inova_final_notice": {"medium"},
    "insurance_denial_180d": {"medium"},
    "prescription_label": {"info"},
    "school_immunization_notice": {"medium"},
    "va_pay_or_quit_14d": {"high"},
    "snap_interview_notice": {"high"},
    "irs_cp_notice": {"medium"},
    "jury_summons": {"medium"},
    "scam_gift_card_letter": None,
    "blurry_unreadable_page": None,
    "spanish_lease": {"info"},
    "w2_form": {"info"},
    "traffic_court_notice": {"high", "critical"},
}

Json = Any


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Json:
        return json.loads(self.body.decode("utf-8"))


@dataclass
class Smoke:
    base: str
    timeout: float = 60.0
    verbose: bool = True
    consent_version: str = ""
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    passed: int = 0

    # --- plumbing ------------------------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        body: Json | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        data = None if body is None else json.dumps(body).encode("utf-8")
        hdrs = {"Accept": "application/json", **(headers or {})}
        if data is not None:
            hdrs["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return Response(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read())
        except urllib.error.HTTPError as e:
            return Response(e.code, {k.lower(): v for k, v in e.headers.items()}, e.read())

    def check(self, ok: bool, label: str, detail: str = "") -> bool:
        if ok:
            self.passed += 1
            if self.verbose:
                print(f"  ok    {label}")
        else:
            self.failures.append(f"{label}{': ' + detail if detail else ''}")
            print(f"  FAIL  {label}{': ' + detail if detail else ''}")
        return ok

    def note(self, text: str) -> None:
        self.notes.append(text)
        print(f"  note  {text}")

    def json_ok(self, r: Response, label: str, *, scan: bool = True) -> Json | None:
        if not self.check(r.status == 200, label, f"HTTP {r.status} {r.body[:300]!r}"):
            return None
        try:
            data = r.json()
        except ValueError as e:
            self.check(False, label, f"invalid JSON: {e}")
            return None
        if scan:
            self.no_contact_removed(data, label)
        return data

    def no_contact_removed(self, data: Json, label: str) -> None:
        hits = [s for s in iter_strings(data) if CONTACT_REMOVED in s]
        self.check(not hits, f"{label}: no '{CONTACT_REMOVED}'", f"{hits[:2]}")

    # --- checks --------------------------------------------------------------------------------

    def health_and_config(self) -> None:
        print("status")
        r = self.request("GET", "/health")
        health = self.json_ok(r, "GET /health")
        if health is not None:
            self.check(health.get("status") == "ok", "health.status == ok", str(health))
            self.check(health.get("provider") == "mock", "health.provider == mock", str(health))
            self.check(health.get("data_use_tier") == "demo", "health tier == demo", str(health))
            self.check(health.get("keys_configured") == 0, "health.keys_configured == 0")
            for h in ("x-request-id", "x-contract-version", "x-data-use-tier"):
                self.check(bool(r.headers.get(h)), f"/health header {h}")
        cfg = self.json_ok(self.request("GET", "/v1/config"), "GET /v1/config")
        if cfg is not None:
            self.consent_version = str(cfg.get("consent_version", ""))
            self.check(cfg.get("data_use_tier") == "demo", "config.data_use_tier == demo")
            self.check(bool(self.consent_version), "config.consent_version set")
            tags = {lang.get("tag") for lang in cfg.get("languages", [])}
            self.check({"en", "es", "prs", "ar"} <= tags, "config.languages has en/es/prs/ar")
            self.check(
                str(cfg.get("privacy_policy_url", "")).startswith("http"),
                "config.privacy_policy_url is a URL",
            )

    def language_pack(self) -> None:
        print("language pack")
        r = self.request("GET", "/v1/language-packs/en")
        # The pack itself holds the UI copy for the marker, so it is not scanned for it.
        pack = self.json_ok(r, "GET /v1/language-packs/en", scan=False)
        if pack is None:
            return
        strings = pack.get("strings", {})
        self.check(strings.get("langpack.adapting") == ADAPTING, "en pack has langpack.adapting")
        etag = r.headers.get("etag", "")
        self.check(bool(etag), "en pack ETag")
        if etag:
            again = self.request("GET", "/v1/language-packs/en", headers={"If-None-Match": etag})
            self.check(again.status == 304, "If-None-Match → 304", f"HTTP {again.status}")

    def demo_list(self) -> list[Json]:
        print("demo samples")
        fixtures = self.json_ok(self.request("GET", "/v1/demo/fixtures"), "GET /v1/demo/fixtures")
        if not isinstance(fixtures, list):
            return []
        self.check(len(fixtures) == 18, "18 samples listed", f"got {len(fixtures)}")
        kinds = [f.get("kind") for f in fixtures]
        self.check(kinds.count("screenshot") == 1, "exactly one screenshot sample")
        png = self.request("GET", str(fixtures[0].get("thumbnail_url", "")))
        self.check(
            png.status == 200 and png.body.startswith(b"\x89PNG"),
            f"sample page PNG ({fixtures[0].get('id')})",
            f"HTTP {png.status} {png.headers.get('content-type')}",
        )
        return list(fixtures)

    def analyze_all(self, fixtures: list[Json]) -> dict[tuple[str, str], Json]:
        print("analyze (every document sample × every recorded language)")
        results: dict[tuple[str, str], Json] = {}
        for fx in fixtures:
            if fx.get("kind") != "document":
                continue
            for lang in fx.get("available_target_languages", []):
                result = self.analyze(fx, lang)
                if result is not None:
                    results[(fx["id"], lang)] = result
        return results

    def analyze(self, fx: Json, lang: str) -> Json | None:
        fid = fx["id"]
        label = f"analyze {fid} [{lang}]"
        body = {"pages": [], "target_language": lang, "client_platform": "web",
                "demo_sample_id": fid}  # fmt: skip
        headers = {"X-Consent-Version": self.consent_version} if self.consent_version else {}
        result = self.json_ok(self.request("POST", "/v1/analyze", body, headers), label)
        if result is None:
            return None
        problems: list[str] = []
        if result.get("document_type") != fx.get("document_type"):
            problems.append(f"document_type {result.get('document_type')} != {fx['document_type']}")
        if result.get("target_language") != lang:
            problems.append(f"target_language {result.get('target_language')}")
        meta = result.get("model_meta") or {}
        if meta.get("demo") is not True or meta.get("provider") != "mock":
            problems.append(f"model_meta {meta}")
        if "demo_sample" not in result.get("warnings", []):
            problems.append("warnings lacks demo_sample")
        for bucket, verified in (("demands", True), ("unverified", False)):
            for d in result.get(bucket, []):
                problems.extend(demand_problems(d, bucket, verified))
        level = (result.get("urgency") or {}).get("level")
        if level not in URGENCY:
            problems.append(f"urgency.level {level!r}")
        self.check(not problems, f"{label}: contract shape, D-09 fields", "; ".join(problems))
        self.urgency_vs_appendix_d(fid, lang, result)
        return result

    def urgency_vs_appendix_d(self, fid: str, lang: str, result: Json) -> None:
        expected = APPENDIX_D_URGENCY.get(fid)
        if expected is None:
            return
        urgency = result.get("urgency") or {}
        level, nearest, days = urgency.get("level"), urgency.get("nearest_date_iso"), urgency.get(
            "days_until"
        )
        label = f"urgency {fid} [{lang}] in Appendix D {sorted(expected)}"
        if nearest is None:
            if expected == {"info"}:
                self.check(level == "info", label, f"got {level}")
            elif lang == "en":
                self.note(f"{fid}: no dated demand in the result; urgency {level} not asserted")
            return
        pinned = pinned_today(fid)
        if pinned is None:
            if lang == "en":
                self.note(f"{fid}: no fixtures dir or manifest 'today'; urgency not asserted")
            return
        if days == (date.fromisoformat(nearest) - pinned).days:
            self.check(level in expected, label, f"got {level} (days_until {days})")
        elif lang == "en":
            self.note(
                f"{fid}: urgency counted from the real calendar (days_until {days}, pinned sample "
                f"day {pinned}); sample dates not pinned yet (POLISH) — got {level}, not asserted"
            )

    def stable_goldens(self, results: dict[tuple[str, str], Json]) -> None:
        """Appendix D assertions that do not depend on the calendar."""
        print("date-independent Appendix D checks")
        scam = results.get(("scam_gift_card_letter", "en"))
        if scam is not None:
            self.check(scam.get("scam_risk") == "likely", "scam sample: scam_risk likely")
            tags = scam.get("resource_tags") or []
            self.check(bool(tags) and tags[0] == "scam_report", "scam sample: scam_report first")
        blurry = results.get(("blurry_unreadable_page", "en"))
        if blurry is not None:
            readable = (blurry.get("quality") or {}).get("readable")
            self.check(readable is False, "blurry sample: quality.readable false")
        lease = results.get(("spanish_lease", "en"))
        if lease is not None:
            self.check(lease.get("detected_language") == "es", "Spanish lease: detected es")
        medicaid = results.get(("medicaid_address_confirmation", "en"))
        if medicaid is not None:
            self.check(len(medicaid.get("demands", [])) == 2, "Medicaid sample: 2 demands")

    def troubleshoot(self, fixtures: list[Json]) -> None:
        print("troubleshoot (screenshot sample with its PNG bytes)")
        shots = [f for f in fixtures if f.get("kind") == "screenshot"]
        if not self.check(bool(shots), "a screenshot sample exists"):
            return
        fx = shots[0]
        png = self.request("GET", f"/v1/demo/fixtures/{fx['id']}/pages/1")
        if not self.check(png.body.startswith(b"\x89PNG"), f"{fx['id']} page PNG"):
            return
        shot = {"mime_type": "image/png", "data_base64": base64.b64encode(png.body).decode()}
        headers = {"X-Consent-Version": self.consent_version} if self.consent_version else {}
        for lang in fx.get("available_target_languages", ["en"]):
            body = {"screenshot": shot, "target_language": lang, "client_platform": "web",
                    "mode": "portal", "demo_sample_id": fx["id"]}  # fmt: skip
            label = f"troubleshoot {fx['id']} [{lang}]"
            res = self.json_ok(self.request("POST", "/v1/troubleshoot", body, headers), label)
            if res is None:
                continue
            self.check(bool(res.get("steps")), f"{label}: has steps")
            self.check((res.get("safety") or {}).get("emergency") is False, f"{label}: no alarm")
            if lang == "en":
                text = " ".join(iter_strings(res))
                for word in ("Choose File", "Upload"):
                    self.check(word in text, f"{label}: names '{word}' as written")

    def chat(self, results: dict[tuple[str, str], Json]) -> None:
        print("chat (grounded date answer, outcome refusal)")
        headers = {"X-Consent-Version": self.consent_version} if self.consent_version else {}
        medicaid = results.get(("medicaid_address_confirmation", "en"))
        if medicaid is not None:
            body = chat_body(medicaid, "When is it due?", "medicaid_address_confirmation")
            ans = self.json_ok(self.request("POST", "/v1/chat", body, headers), "chat date")
            if ans is not None:
                spans = {s for d in medicaid.get("demands", []) for s in d.get("span_ids", [])}
                grounded = set(ans.get("grounded_span_ids") or [])
                self.check(ans.get("not_in_document") is False, "chat date: found in the paper")
                self.check(bool(grounded) and grounded <= spans, "chat date: quotes a demand span")
                self.check(ans.get("refusal_kind") == "none", "chat date: no refusal")
        nta = results.get(("nta_hearing_date", "en"))
        if nta is not None:
            body = chat_body(nta, "Will I be deported?", "nta_hearing_date")
            ans = self.json_ok(self.request("POST", "/v1/chat", body, headers), "chat outcome")
            if ans is not None:
                self.check(ans.get("refusal_kind") == "outcome", "chat outcome: refusal_kind")
                self.check(ans.get("refer_to_professional") != "none", "chat outcome: referral")

    def resources(self, results: dict[tuple[str, str], Json]) -> list[Json]:
        print("resources")
        medicaid = results.get(("medicaid_address_confirmation", "en")) or {}
        body = {
            "tags": (medicaid.get("resource_tags") or ["benefits_help"])[:12],
            "document_type": medicaid.get("document_type"),
            "category": medicaid.get("category"),
            "state": "VA",
            "language": "en",
            "institutions_as_written": [medicaid["sender_as_written"]]
            if medicaid.get("sender_as_written") else [],
        }  # fmt: skip
        res = self.json_ok(self.request("POST", "/v1/resources/match", body), "resources/match")
        matches: list[Json] = []
        if res is not None:
            matches = list(res.get("results", []))
            self.check(bool(matches) or bool(res.get("national_fallbacks")), "match returns help")
            dated = all(m.get("resource", {}).get("verified_on") for m in matches)
            self.check(dated, "every match has verified_on")
            self.check(all("checklist" in m for m in matches), "every match has a checklist")
        scam = {"tags": ["scam_report"], "language": "en", "scam_risk": "likely"}
        res = self.json_ok(self.request("POST", "/v1/resources/match", scam), "match scam")
        if res is not None and res.get("results"):
            first = res["results"][0].get("resource", {})
            self.check("scam_report" in first.get("tags", []), "scam match: scam_report first")
        rules = self.json_ok(self.request("GET", "/v1/rules"), "GET /v1/rules")
        if rules is not None:
            items = rules.get("rules", [])
            self.check(len(items) == 12, "12 deadline rules", f"got {len(items)}")
            self.check(all(r.get("source_url") for r in items), "every rule has source_url")
        return matches

    def quicksheet(self, matches: list[Json]) -> None:
        print("quick sheet PDF")
        res_lines = [
            {k: m["resource"].get(k) for k in ("name", "phone", "url")} for m in matches[:2]
        ]
        for tag, direction, heading in (("en", "ltr", "What is this?"),
                                        ("prs", "rtl", "این چیست؟")):  # fmt: skip
            body = {
                "title": "Sample paper",
                "language_tag": tag,
                "direction": direction,
                "sections": [{"heading": heading, "heading_en": "What is this?",
                              "lines": ["A sample letter.", "October 14, 2026"]}],
                "resources": res_lines,
                "footer": "Made with a computer from your paper. It can be wrong.",
                "generated_on": date.today().isoformat(),
            }  # fmt: skip
            r = self.request("POST", "/v1/quicksheet/pdf", body)
            self.check(
                r.status == 200 and r.body.startswith(b"%PDF-"),
                f"quicksheet PDF [{tag}, {direction}] magic bytes",
                f"HTTP {r.status} {r.body[:120]!r}",
            )
            self.check("pdf" in r.headers.get("content-type", ""), f"quicksheet [{tag}] PDF type")

    def feedback(self) -> None:
        print("feedback")
        body = {"kind": "clear", "surface": "summary", "language_tag": "en",
                "document_type": "medicaid_renewal", "card_id": "summary",
                "app_version": "1.0.0", "platform": "web"}  # fmt: skip
        res = self.json_ok(self.request("POST", "/v1/feedback", body), "POST /v1/feedback")
        if res is not None:
            self.check(res.get("received") is True, "feedback received")


# --- helpers ------------------------------------------------------------------------------------


def iter_strings(data: Json) -> list[str]:
    out: list[str] = []
    stack = [data]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return out


def demand_problems(d: Json, bucket: str, verified: bool) -> list[str]:
    did = d.get("id", "?")
    out: list[str] = []
    if not isinstance(d.get("source_quote"), str) or (verified and not d["source_quote"].strip()):
        out.append(f"{bucket}.{did}.source_quote")
    if not isinstance(d.get("span_ids"), list) or (verified and not d["span_ids"]):
        out.append(f"{bucket}.{did}.span_ids")
    if not isinstance(d.get("page"), int) or d["page"] < 1:
        out.append(f"{bucket}.{did}.page")
    if d.get("confidence") not in CONFIDENCE:
        out.append(f"{bucket}.{did}.confidence")
    if d.get("verified") is not verified:
        out.append(f"{bucket}.{did}.verified must be {verified}")
    return out


def chat_body(analysis: Json, question: str, sample_id: str) -> Json:
    keys = ("analysis_id", "category", "document_type", "detected_language", "sender_as_written",
            "summary", "demands", "unverified", "plan_steps", "red_flags", "glossary",
            "original_text", "urgency")  # fmt: skip
    return {"analysis": {k: analysis.get(k) for k in keys}, "messages": [], "question": question,
            "target_language": "en", "demo_sample_id": sample_id}  # fmt: skip


def pinned_today(fid: str) -> date | None:
    """The sample's pinned ``today`` from its manifest (plain regex: no YAML parser in stdlib)."""
    manifest = FIXTURES_DIR / fid / "manifest.yaml"
    if not manifest.is_file():
        return None
    m = re.search(r"^today:\s*['\"]?(\d{4}-\d{2}-\d{2})", manifest.read_text("utf-8"), re.M)
    return date.fromisoformat(m.group(1)) if m else None


def wait_for_health(base: str, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base + "/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.3)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--wait", type=float, default=0.0, help="seconds to wait for /health")
    parser.add_argument("--quiet", action="store_true", help="print only failures and notes")
    args = parser.parse_args(argv)
    base = args.base_url.rstrip("/")
    if args.wait and not wait_for_health(base, args.wait):
        print(f"smoke: {base}/health did not answer within {args.wait:.0f} s", file=sys.stderr)
        return 1
    started = time.monotonic()
    s = Smoke(base=base, verbose=not args.quiet)
    s.health_and_config()
    s.language_pack()
    fixtures = s.demo_list()
    results = s.analyze_all(fixtures)
    s.stable_goldens(results)
    s.troubleshoot(fixtures)
    s.chat(results)
    matches = s.resources(results)
    s.quicksheet(matches)
    s.feedback()
    took = time.monotonic() - started
    print(f"\nsmoke: {s.passed} checks passed, {len(s.failures)} failed, "
          f"{len(s.notes)} notes in {took:.1f} s against {base}")  # fmt: skip
    if s.failures:
        print("FAILED:\n  " + "\n  ".join(s.failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
