"""The repo-root ``render.yaml`` (DEPLOYMENT §1.7) stays deployable, consistent and secret-free.

* The API's environment, with a fake ``GEMINI_KEYS`` and stand-ins for Render's generated values,
  boots ``ENV=production`` on the paid tier; every variable is a ``Settings`` field
  (``extra="forbid"`` turns a typo into a failure).
* Secrets are never values in the file, and nothing key-shaped appears in it.
* The URLs agree: ``CORS_ORIGINS`` / ``PRIVACY_POLICY_URL`` name the web service, and
  ``EXPO_PUBLIC_API_URL`` and the CSP ``connect-src`` name the API service.
* The static site sends exactly the DEPLOYMENT §2.2 headers.
* Every Expo Router screen in ``apps/mobile/src/app`` has a rewrite to the file the static export
  writes for it (DEPLOYMENT §2.3: dynamic routes keep their brackets, ``result/[id].html``), most
  specific first, and no rule is left over from a removed screen.
"""

import re
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from proxyhealth_api.contracts.enums import DataUseTier, Provider
from proxyhealth_api.settings import Settings

REPO = Path(__file__).resolve().parents[4]
BLUEPRINT = REPO / "render.yaml"
DEPLOYMENT = REPO / "docs" / "DEPLOYMENT.md"
APP_DIR = REPO / "apps" / "mobile" / "src" / "app"
PRIVACY_PAGE = REPO / "apps" / "mobile" / "public" / "privacy" / "index.html"

FAKE_KEYS = '[{"key":"AIzaFAKEFAKEFAKE","project":"proxyhealth-cac","billing":true}]'
# Read from os.environ by settings.dotenv_disabled(), not a Settings field.
NOT_SETTINGS = frozenset({"PROXYHEALTH_NO_DOTENV"})
KEY_SHAPES = re.compile(
    r"AIza[0-9A-Za-z_\-]{20,}|AQ\.[0-9A-Za-z_\-]{20,}|github_pat_|gh[pousr]_[0-9A-Za-z]{20,}"
    r"|sk-[0-9A-Za-z]{20,}"
)
DYNAMIC_SEGMENT = re.compile(r"^\[[A-Za-z0-9_]+\]$")
# Rules with no screen of their own: the public policy (public/privacy/index.html) and papers/
# (also a directory, papers/member/…).
EXTRA_RULES = {"/privacy": "/privacy/index.html", "/papers/": "/papers.html"}


@cache
def blueprint() -> dict[str, Any]:
    data = yaml.safe_load(BLUEPRINT.read_text("utf-8"))
    assert isinstance(data, dict)
    return data


def service(runtime: str) -> dict[str, Any]:
    matches = [s for s in blueprint()["services"] if s.get("runtime") == runtime]
    assert len(matches) == 1, f"expected one {runtime} service"
    found: dict[str, Any] = matches[0]
    return found


def env_vars(svc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {spec["key"]: spec for spec in svc["envVars"]}


def origin(svc: dict[str, Any]) -> str:
    return f"https://{svc['name']}.onrender.com"


def test_service_names_and_api_build() -> None:
    api, web = service("docker"), service("static")
    assert (api["name"], web["name"]) == ("proxyhealth-ai-api", "proxyhealth-ai")
    assert api["type"] == web["type"] == "web"
    assert api["plan"] == "free"
    assert api["healthCheckPath"] == "/health"
    dockerfile = REPO / api["dockerfilePath"]
    assert dockerfile.is_file() and (REPO / api["dockerContext"]).is_dir()
    assert dockerfile.parent == (REPO / api["dockerContext"]).resolve()
    assert "--port ${PORT}" in dockerfile.read_text("utf-8")  # Render injects PORT


def test_api_environment_boots_in_production(tmp_path: Path) -> None:
    values: dict[str, str] = {}
    for key, spec in env_vars(service("docker")).items():
        if key in NOT_SETTINGS:
            continue
        if "value" in spec:
            values[key.lower()] = str(spec["value"])
        elif spec.get("generateValue"):
            values[key.lower()] = "generated-by-render"
    values["gemini_keys"] = FAKE_KEYS  # sync: false — typed into Render's form
    values["var_dir"] = str(tmp_path / "var")
    settings = Settings(_env_file=None, **values)  # type: ignore[arg-type]
    settings.validate_runtime()
    web = origin(service("static"))
    assert settings.env == "production"
    assert settings.provider is Provider.gemini
    assert settings.data_use_tier is DataUseTier.paid
    assert settings.real_documents_allowed and not settings.allow_unpaid_real_documents
    assert not settings.allow_unpaid_keys
    assert settings.trusted_proxy_hops == 1
    assert settings.cors_origin_list == [web]
    assert settings.privacy_policy_url == f"{web}/privacy"
    assert settings.log_level == "info"


def test_secrets_are_never_values() -> None:
    api = env_vars(service("docker"))
    assert api["GEMINI_KEYS"] == {"key": "GEMINI_KEYS", "sync": False}
    for key in ("INSTALL_HASH_SECRET", "ADMIN_TOKEN"):
        assert api[key] == {"key": key, "generateValue": True}
    for svc in blueprint()["services"]:
        for spec in svc.get("envVars", []):
            if re.search(r"KEY|SECRET|TOKEN|PASSWORD", spec["key"]):
                assert "value" not in spec, f"{spec['key']} must not carry a value"
    match = KEY_SHAPES.search(BLUEPRINT.read_text("utf-8"))
    assert match is None, f"key-shaped text in render.yaml at char {match.start() if match else 0}"


def test_web_build_points_at_the_api() -> None:
    web = service("static")
    env = env_vars(web)
    assert env["EXPO_PUBLIC_API_URL"]["value"] == origin(service("docker"))
    assert env["EXPO_PUBLIC_APP_ENV"]["value"] == "production"
    assert web["staticPublishPath"] == "./apps/mobile/dist"
    build = web["buildCommand"]
    for part in (
        "npm ci --legacy-peer-deps",
        "expo export --platform web --clear",
        "dist/privacy/index.html",
        "web-host-rules.py apps/mobile/dist --write --check",
    ):
        assert part in build, part
    assert PRIVACY_PAGE.is_file()


def deployment_headers(api_origin: str) -> dict[tuple[str, str], str]:
    """The ``_headers`` block of DEPLOYMENT §2.2 as {(path, name): value}."""
    section = DEPLOYMENT.read_text("utf-8").split("### 2.2", 1)[1]
    block = section.split("```text", 1)[1].split("```", 1)[0]
    headers: dict[tuple[str, str], str] = {}
    path = ""
    for line in block.splitlines():
        if not line.strip():
            continue
        if not line.startswith(" "):
            path = line.strip()
            continue
        name, _, value = line.strip().partition(": ")
        headers[(path, name)] = value.replace("https://<prod-api>", api_origin)
    return headers


def test_web_headers_match_deployment_section_2_2() -> None:
    web = service("static")
    sent = {(h["path"], h["name"]): h["value"] for h in web["headers"]}
    expected = deployment_headers(origin(service("docker")))
    assert len(expected) >= 10
    assert sent == expected


def screens() -> dict[str, str]:
    """{rewrite source: exported file} for every screen, as the SDK 57 static export names them."""
    pages: dict[str, str] = {}
    for file in sorted(APP_DIR.rglob("*.tsx")):
        rel = file.relative_to(APP_DIR).with_suffix("")
        if rel.name.startswith(("_", "+")) or rel.name.endswith(".test"):
            continue
        parts = [p for p in rel.parts if not (p.startswith("(") and p.endswith(")"))]
        if parts and parts[-1] == "index":
            parts = parts[:-1]
        if not parts:
            continue  # "/" is index.html, served without a rule
        source = "/" + "/".join("*" if DYNAMIC_SEGMENT.match(p) else p for p in parts)
        pages[source] = "/" + "/".join(parts) + ".html"
    return pages


def test_every_screen_has_a_rewrite_most_specific_first() -> None:
    routes = service("static")["routes"]
    assert all(r["type"] == "rewrite" for r in routes)
    rules = {r["source"]: r["destination"] for r in routes}
    assert len(rules) == len(routes), "duplicate rewrite sources"
    pages = screens()
    assert "/result/*" in pages and "/result/*/chat" in pages  # the walk found the dynamic routes
    for source, destination in pages.items():
        assert rules.get(source) == destination, f"render.yaml lacks {source} -> {destination}"
    for source, destination in EXTRA_RULES.items():
        assert rules.get(source) == destination
    stale = set(rules) - set(pages) - set(EXTRA_RULES)
    assert not stale, f"rewrites without a screen: {sorted(stale)}"
    order = [r["source"] for r in routes]
    for i, source in enumerate(order):
        if source.endswith("/*"):
            shadowed = [s for s in order[i + 1 :] if s.startswith(source[:-1])]
            assert not shadowed, f"{source} comes before the more specific {shadowed}"
