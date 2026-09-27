"""The committed ``openapi.json`` must equal the in-memory schema byte for byte (API_CONTRACT §5).
"""

import json
import re
from pathlib import Path

from proxyhealth_api.main import create_app, openapi_json
from proxyhealth_api.settings import Settings

SNAPSHOT = Path(__file__).resolve().parents[2] / "openapi.json"
REGENERATE = "run: apps/api/.venv/bin/python apps/api/scripts/export_openapi.py"

CONTRACT_PATHS = {
    "/health", "/v1/config", "/v1/language-packs/{tag}", "/v1/language-packs", "/v1/analyze",
    "/v1/troubleshoot", "/v1/chat", "/v1/resources/match", "/v1/resources", "/v1/resources/{id}",
    "/v1/rules", "/v1/quicksheet/pdf", "/v1/feedback", "/v1/demo/fixtures",
    "/v1/demo/fixtures/{id}/pages/{n}", "/v1/admin/keys",
}  # fmt: skip


def _current() -> str:
    return openapi_json(create_app(Settings(_env_file=None)))


def test_snapshot_is_current() -> None:
    assert SNAPSHOT.is_file(), f"openapi.json missing; {REGENERATE}"
    stale = f"openapi.json is stale; {REGENERATE}"
    assert SNAPSHOT.read_text(encoding="utf-8") == _current(), stale


def test_every_contract_path_is_present() -> None:
    schema = json.loads(_current())
    assert set(schema["paths"]) == CONTRACT_PATHS


def test_error_response_on_every_4xx_5xx() -> None:
    schema = json.loads(_current())
    for path, item in schema["paths"].items():
        for method, op in item.items():
            for status, resp in op["responses"].items():
                if status[0] in "45":
                    ref = resp["content"]["application/json"]["schema"]["$ref"]
                    assert ref.endswith("/ErrorResponse"), f"{method.upper()} {path} {status}"


def test_property_names_are_snake_case() -> None:
    schema = json.loads(_current())
    bad = [
        f"{name}.{prop}"
        for name, model in schema["components"]["schemas"].items()
        for prop in model.get("properties", {})
        if not re.fullmatch(r"[a-z][a-z0-9_]*", prop)
    ]
    assert not bad, bad
    assert not {"HTTPValidationError", "ValidationError"} & set(schema["components"]["schemas"])
