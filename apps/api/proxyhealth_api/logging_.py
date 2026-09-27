"""Structured JSON logger with an allow-list of fields (ARCHITECTURE §2.1, §7).

Any key outside ``ALLOWED_FIELDS`` is dropped (``check_fields`` raises for tests). Bodies,
document text, keys and user-typed strings never reach a log line.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from enum import Enum
from typing import Any

ALLOWED_FIELDS: frozenset[str] = frozenset(
    {
        "ts", "request_id", "route", "status", "error_code", "provider", "model", "tier",
        "slot_index", "quality", "analysis_mode", "latency_ms", "input_tokens", "output_tokens",
        "thought_tokens", "page_count", "total_bytes", "document_type", "category",
        "urgency_level", "scam_risk", "contacts_stripped", "phrasing_rewrites", "facts_total",
        "facts_unverified", "injection_suspected", "target_language", "detected_language",
        "install_id_hash", "client_platform", "data_use_tier",
    }
)  # fmt: skip

_LOGGER_NAME = "proxyhealth"
_logger = logging.getLogger(_LOGGER_NAME)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        return msg if msg.startswith("{") else json.dumps({"ts": _now(), "route": msg})


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def configure_logging(level: str = "info") -> None:
    """Install the JSON handler once and silence uvicorn's access log (bodies/paths with ids)."""
    if not _logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        _logger.addHandler(handler)
    _logger.propagate = False
    _logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logging.getLogger("uvicorn.access").disabled = True


def check_fields(fields: dict[str, Any]) -> None:
    """Raise on any key outside the allow-list (used by ``test_logging_allowlist``)."""
    unknown = sorted(set(fields) - ALLOWED_FIELDS)
    if unknown:
        raise ValueError(f"log fields not in allow-list: {unknown}")


def _scalar(value: Any) -> str | int | float | bool | None:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def log_event(**fields: Any) -> None:
    """Emit one JSON line containing only allow-listed keys."""
    kept = {k: _scalar(v) for k, v in fields.items() if k in ALLOWED_FIELDS}
    kept.setdefault("ts", _now())
    _logger.info(json.dumps(kept, ensure_ascii=False, sort_keys=True))
