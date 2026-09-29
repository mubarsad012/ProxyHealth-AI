"""Structured JSON logger with an allow-list of fields (ARCHITECTURE §2.1 "Logging", §7; D-08).

Only the keys in ``ALLOWED_FIELDS`` ever reach a log line. Outside tests an unknown key is
dropped; while pytest is running (or after ``set_strict(True)``) ``log_event`` raises, so a
stray ``quote=`` or ``filename=`` anywhere in the server fails the suite
(``tests/unit/test_logging_allowlist.py``). Values are scalars only; strings are truncated so
no line can smuggle content. uvicorn's access log is disabled (paths carry ids).

Two more paths could carry content and are closed here (ARCHITECTURE §7 item 1):

* a plain stdlib record from any ``proxyhealth.*`` logger (``logger.warning("... %s", x)``) is
  printed as ``{"ts", "route"}``. While any app is serving requests (``serving()``, entered by the
  lifespan after startup) it holds only the code-authored template: numeric arguments are
  interpolated, any other argument (a path, a quote, model prose) is not, and the result is cut
  to ``MAX_STRING_LEN``. Before the first request can arrive (boot: resource/rules warnings name
  a YAML path) the full message is kept, cut to ``BOOT_MESSAGE_LEN``. Tracebacks never print;
* uvicorn's access and trace loggers drop every record (``DropAllFilter`` survives uvicorn's own
  ``dictConfig``, which resets ``disabled``);
* uvicorn's own error loggers get ``ContentFreeFilter``, which drops ``exc_info`` /
  ``stack_info`` so a traceback or an exception message (pydantic's ``input_value='…'``, a
  ``ValueError`` quoting the paper) never reaches stderr. The app itself never lets an unexpected
  exception escape to uvicorn (``middleware.UnhandledErrorMiddleware``); the filter is the backstop.
"""

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
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

# Longest string value a log line may carry (ids, hashes and route templates fit easily).
MAX_STRING_LEN = 120
# Longest boot-time stdlib message (no request, hence no user content, exists yet).
BOOT_MESSAGE_LEN = 1000

_LOGGER_NAME = "proxyhealth"
_logger = logging.getLogger(_LOGGER_NAME)
_strict: bool | None = None
_serving = 0  # apps past startup (a request, and so user content, may be in flight)

Scalar = str | int | float | bool | None


class LogFieldError(ValueError):
    """A log call used a key outside ``ALLOWED_FIELDS`` (raised only in strict mode)."""


# ``extra=`` marker set only by ``log_event``: its JSON line is printed verbatim.
_EVENT_ATTR = "proxyhealth_event"

# uvicorn's loggers that may carry a traceback, and those that print paths/scopes per request.
_UVICORN_ERROR_LOGGERS = ("uvicorn", "uvicorn.error")
_UVICORN_SILENT_LOGGERS = ("uvicorn.access", "uvicorn.asgi")


@contextmanager
def serving() -> Iterator[None]:
    """Mark an app as serving: stdlib records then lose their non-numeric arguments."""
    global _serving
    _serving += 1
    try:
        yield
    finally:
        _serving -= 1


def safe_message(record: logging.LogRecord) -> str:
    """A stdlib record's text without its non-numeric arguments, cut to ``MAX_STRING_LEN``."""
    if not _serving:
        try:
            return record.getMessage()[:BOOT_MESSAGE_LEN]
        except (TypeError, ValueError):
            pass
    template = record.msg if isinstance(record.msg, str) else type(record.msg).__name__
    args = record.args
    if isinstance(args, tuple) and args and all(isinstance(a, int | float) for a in args):
        try:
            template = template % args
        except (TypeError, ValueError):
            pass
    return template[:MAX_STRING_LEN]


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if getattr(record, _EVENT_ATTR, False) and isinstance(record.msg, str):
            return record.msg
        return json.dumps({"ts": _now(), "route": safe_message(record)}, ensure_ascii=False)


class ContentFreeFilter(logging.Filter):
    """Strip tracebacks and exception text from a record; the message template stays."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


class DropAllFilter(logging.Filter):
    """Drop every record (uvicorn's access/trace logs carry raw paths and request scopes)."""

    def filter(self, record: logging.LogRecord) -> bool:
        return False


def _add_filter_once(logger: logging.Logger, kind: type[logging.Filter]) -> None:
    if not any(isinstance(f, kind) for f in logger.filters):
        logger.addFilter(kind())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def configure_logging(level: str = "info") -> None:
    """Install the JSON handler once, silence uvicorn's access/trace logs (paths carry ids,
    trace prints scopes) and keep tracebacks out of uvicorn's error log."""
    if not _logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        _logger.addHandler(handler)
    _logger.propagate = False
    _logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    for name in _UVICORN_SILENT_LOGGERS:
        logging.getLogger(name).disabled = True
        _add_filter_once(logging.getLogger(name), DropAllFilter)
    for name in _UVICORN_ERROR_LOGGERS:
        _add_filter_once(logging.getLogger(name), ContentFreeFilter)


def set_strict(enabled: bool | None) -> None:
    """Force strict mode on/off; ``None`` restores auto-detection (strict while pytest runs)."""
    global _strict
    _strict = enabled


def is_strict() -> bool:
    if _strict is not None:
        return _strict
    return "pytest" in sys.modules


def check_fields(fields: dict[str, Any]) -> None:
    """Raise ``LogFieldError`` on any key outside the allow-list."""
    unknown = sorted(set(fields) - ALLOWED_FIELDS)
    if unknown:
        raise LogFieldError(f"log fields not in allow-list: {unknown}")


def _scalar(value: Any) -> Scalar:
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        return value
    text = value if isinstance(value, str) else str(value)
    return text[:MAX_STRING_LEN]


def log_event(**fields: Any) -> None:
    """Emit one JSON line containing only allow-listed keys (drops or raises on others)."""
    if is_strict():
        check_fields(fields)
    kept = {k: _scalar(v) for k, v in fields.items() if k in ALLOWED_FIELDS}
    kept.setdefault("ts", _now())
    _logger.info(json.dumps(kept, ensure_ascii=False, sort_keys=True), extra={_EVENT_ATTR: True})
