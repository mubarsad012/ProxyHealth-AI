"""Write ``apps/api/openapi.json`` deterministically from ``create_app()`` (API_CONTRACT §5)."""

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from proxyhealth_api.main import create_app, openapi_json  # noqa: E402
from proxyhealth_api.settings import Settings  # noqa: E402


def main() -> int:
    target = API_ROOT / "openapi.json"
    text = openapi_json(create_app(Settings(_env_file=None)))
    if target.is_file() and target.read_text(encoding="utf-8") == text:
        print(f"unchanged {target}")
        return 0
    target.write_text(text, encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
