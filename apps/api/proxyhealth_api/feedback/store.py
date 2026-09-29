"""Content-free feedback counters (API_CONTRACT §3.12; D-31; BUILD_PLAN §4.1/§5.8 step 6).

``var/feedback_counts.sqlite`` holds one table: the API_CONTRACT §3.12 counter key
``(kind, surface, language_tag, document_type, resource_id, app_version, model_id)`` plus
``count``. Nothing else from the request is stored — not ``card_id``, not ``platform``, no time
stamp, no install id, no text of any kind — so a row can never be tied to a person or a paper.
The response id is a fresh ULID (26-char Crockford base32, ``time.time_ns()`` + 80 random bits)
prefixed ``fb_``; it is not stored either.

``kind``/``surface``/``document_type`` are enum values and ``language_tag`` is pattern-checked by
``FeedbackRequest``. The contract leaves ``resource_id``, ``app_version`` and ``model_id`` as free
``str`` (CL line to WP0 filed), so ``counter_key`` re-validates them here and replaces anything
that is not a short identifier with ``OTHER``: a resource id must look like a vetted-DB id (and be
a known one when the caller passes ``known_resource``), an app version must be semver-like, a model
id must be a configured/mock model or a lowercase model-style slug. Absent values are stored as
``''`` so the primary key stays unique in SQLite. Free text therefore never reaches the file.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
import threading
import time
from collections.abc import Callable, Collection
from pathlib import Path

from proxyhealth_api.contracts.feedback import FeedbackRequest

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ID_PREFIX = "fb_"
# Stored in place of a value that fails its identifier check (never the value itself).
OTHER = "other"
MOCK_MODEL_ID = "mock"
RESOURCE_ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")
APP_VERSION_RE = re.compile(r"^\d{1,6}\.\d{1,6}\.\d{1,6}([-+][0-9A-Za-z.]{1,20})?$", re.ASCII)
MODEL_ID_RE = re.compile(r"^[a-z0-9.-]{1,64}$")
KEY_COLUMNS: tuple[str, ...] = (
    "kind",
    "surface",
    "language_tag",
    "document_type",
    "resource_id",
    "app_version",
    "model_id",
)
_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS feedback_counts ("
    + ", ".join(f"{c} TEXT NOT NULL" for c in KEY_COLUMNS)
    + ", count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY ("
    + ", ".join(KEY_COLUMNS)
    + "))"
)
_UPSERT = (
    f"INSERT INTO feedback_counts ({', '.join(KEY_COLUMNS)}, count) "
    f"VALUES ({', '.join('?' for _ in KEY_COLUMNS)}, 1) "
    f"ON CONFLICT({', '.join(KEY_COLUMNS)}) DO UPDATE SET count = count + 1"
)


def ulid(
    now_ns: Callable[[], int] = time.time_ns,
    random_bytes: Callable[[int], bytes] = secrets.token_bytes,
) -> str:
    """26-char Crockford-base32 ULID: 48-bit millisecond time + 80 random bits."""
    millis = now_ns() // 1_000_000
    value = ((millis & ((1 << 48) - 1)) << 80) | int.from_bytes(random_bytes(10), "big")
    chars = []
    for _ in range(26):
        chars.append(CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def _resource_id(value: str | None, known: Callable[[str], bool] | None) -> str:
    if not value:
        return ""
    if not RESOURCE_ID_RE.fullmatch(value) or (known is not None and not known(value)):
        return OTHER
    return value


def _app_version(value: str) -> str:
    return value if APP_VERSION_RE.fullmatch(value) else OTHER


def _model_id(value: str | None, known: Collection[str]) -> str:
    if not value:
        return ""
    if value == MOCK_MODEL_ID or value in known or MODEL_ID_RE.fullmatch(value):
        return value
    return OTHER


def counter_key(
    req: FeedbackRequest,
    *,
    known_resource: Callable[[str], bool] | None = None,
    known_models: Collection[str] = (),
) -> tuple[str, ...]:
    """The API_CONTRACT §3.12 counter tuple — the only data that is ever persisted.

    ``known_resource`` (e.g. ``lambda rid: repo.get(rid) is not None``) narrows ``resource_id``
    to vetted-DB ids; ``known_models`` are the configured ``MODEL_PRO``/``MODEL_FAST`` ids.
    """
    return (
        req.kind.value,
        req.surface.value,
        req.language_tag,
        req.document_type.value if req.document_type else "",
        _resource_id(req.resource_id, known_resource),
        _app_version(req.app_version),
        _model_id(req.model_id, known_models),
    )


class FeedbackStore:
    """Thread-safe SQLite counter table; one short-lived connection per call."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._ready = False

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5)
        if not self._ready:
            conn.execute(_SCHEMA)
            conn.commit()
            self._ready = True
        return conn

    def record(
        self,
        req: FeedbackRequest,
        *,
        known_resource: Callable[[str], bool] | None = None,
        known_models: Collection[str] = (),
    ) -> str:
        """Increment the counter for ``req``'s key and return a fresh ``fb_<ULID>`` id."""
        key = counter_key(req, known_resource=known_resource, known_models=known_models)
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(_UPSERT, key)
                conn.commit()
            finally:
                conn.close()
        return ID_PREFIX + ulid()

    def counts(self) -> list[tuple[str, ...]]:
        """Every row as ``(*KEY_COLUMNS, str(count))``, sorted (tests and ops only)."""
        if not self.path.is_file():
            return []
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    f"SELECT {', '.join(KEY_COLUMNS)}, count FROM feedback_counts "
                    f"ORDER BY {', '.join(KEY_COLUMNS)}"
                ).fetchall()
            finally:
                conn.close()
        return [tuple(str(v) for v in row) for row in rows]

    def columns(self) -> list[str]:
        """Column names of the counter table (the privacy test asserts this exact list)."""
        with self._lock:
            conn = self._connect()
            try:
                info = conn.execute("PRAGMA table_info(feedback_counts)").fetchall()
            finally:
                conn.close()
        return [str(row[1]) for row in info]


__all__ = [
    "CROCKFORD",
    "ID_PREFIX",
    "KEY_COLUMNS",
    "OTHER",
    "FeedbackStore",
    "counter_key",
    "ulid",
]
