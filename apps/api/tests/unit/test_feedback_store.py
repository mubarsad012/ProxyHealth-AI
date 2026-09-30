"""``feedback/store.py`` — counts only (D-31; API_CONTRACT §3.12; BUILD_PLAN §5.8 step 6)."""

import re
import sqlite3
from pathlib import Path

from proxyhealth_api.contracts.feedback import FeedbackRequest
from proxyhealth_api.feedback.store import (
    CROCKFORD,
    KEY_COLUMNS,
    OTHER,
    FeedbackStore,
    counter_key,
    ulid,
)

ID_RE = re.compile(r"^fb_[0-9A-HJKMNP-TV-Z]{26}$")


def request(**overrides: object) -> FeedbackRequest:
    values: dict[str, object] = {
        "kind": "unclear", "surface": "demands", "language_tag": "prs",
        "document_category": "benefits", "document_type": "medicaid_renewal", "card_id": "d2",
        "resource_id": None, "app_version": "1.0.0", "platform": "android",
        "model_id": "gemini-3.8-flash",
    }  # fmt: skip
    values.update(overrides)
    return FeedbackRequest.model_validate(values)


def unchecked(**overrides: object) -> FeedbackRequest:
    """A request whose identifier fields skip the contract patterns (CL-026).

    The contract now refuses free text with 400, but the store must not rely on that: it is the
    privacy boundary (CL-052), so these tests hand it values the contract would never let through.
    """
    return request().model_copy(update=overrides)


def test_schema_has_only_the_counter_key_and_count(tmp_path: Path) -> None:
    store = FeedbackStore(tmp_path / "var" / "feedback_counts.sqlite")
    store.record(request())
    assert store.columns() == [*KEY_COLUMNS, "count"]
    assert set(KEY_COLUMNS) == {
        "kind", "surface", "language_tag", "document_type", "resource_id", "app_version",
        "model_id",
    }  # fmt: skip
    with sqlite3.connect(tmp_path / "var" / "feedback_counts.sqlite") as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert tables == ["feedback_counts"]


def test_two_posts_increment_once_each(tmp_path: Path) -> None:
    store = FeedbackStore(tmp_path / "counts.sqlite")
    store.record(request())
    store.record(request(card_id="d9", platform="web"))  # card_id / platform are not stored
    store.record(request(kind="clear"))
    rows = store.counts()
    assert ("unclear", "demands", "prs", "medicaid_renewal", "", "1.0.0", "gemini-3.8-flash",
            "2") in rows  # fmt: skip
    assert ("clear", "demands", "prs", "medicaid_renewal", "", "1.0.0", "gemini-3.8-flash",
            "1") in rows  # fmt: skip
    assert len(rows) == 2


def test_nothing_but_enums_reaches_disk(tmp_path: Path) -> None:
    path = tmp_path / "counts.sqlite"
    FeedbackStore(path).record(request(card_id="summary", platform="ios"))
    raw = path.read_bytes()
    for absent in (b"summary", b"ios", b"benefits"):
        assert absent not in raw


def test_ids_are_prefixed_ulids_and_unique(tmp_path: Path) -> None:
    store = FeedbackStore(tmp_path / "counts.sqlite")
    ids = {store.record(request()) for _ in range(20)}
    assert len(ids) == 20 and all(ID_RE.match(i) for i in ids)


def test_ulid_encodes_time_then_randomness() -> None:
    value = ulid(now_ns=lambda: 1_700_000_000_000 * 1_000_000, random_bytes=lambda n: b"\x00" * n)
    assert len(value) == 26 and set(value) <= set(CROCKFORD)
    later = ulid(now_ns=lambda: 1_700_000_000_001 * 1_000_000, random_bytes=lambda n: b"\x00" * n)
    assert later > value and value.endswith("0" * 16)


def test_counts_empty_before_first_record(tmp_path: Path) -> None:
    assert FeedbackStore(tmp_path / "missing.sqlite").counts() == []


def test_free_text_in_identifier_fields_never_reaches_disk(tmp_path: Path) -> None:
    # The contract patterns (CL-026) are only a coarse filter; the store itself must refuse
    # anything that is not a short identifier (D-31; CL-052; ARCHITECTURE §7).
    path = tmp_path / "counts.sqlite"
    store = FeedbackStore(path)
    store.record(
        unchecked(
            language_tag="en",
            app_version="My landlord John Smith at 12 Oak St says pay by Friday",
            platform="web",
            resource_id="A-123456789 my case number",
            model_id="x" * 5000,
        )
    )
    store.record(unchecked(resource_id="Maria Lopez", app_version="1.0", model_id="Maria Lopez"))
    # Lowercase hyphenated slugs pass the contract pattern but are not model ids; with or without
    # the configured models passed in, they are counted as OTHER.
    store.record(request(model_id="maria-lopez-12-oak-st"))
    store.record(
        unchecked(model_id="maria-lopez-12-oak-st-a123456789", app_version="x"),
        known_models=("gemini-3.8-pro", "gemini-3.8-flash"),
    )
    store.record(unchecked(model_id="gemini-3-maria-lopez", app_version="y"))
    raw = path.read_bytes()
    for absent in (b"John Smith", b"Oak St", b"A-123456789", b"case number", b"x" * 65,
                   b"Maria", b"Lopez", b"maria", b"lopez", b"oak-st", b"a123456789"):  # fmt: skip
        assert absent not in raw
    rows = store.counts()
    assert ("unclear", "demands", "en", "medicaid_renewal", OTHER, OTHER, OTHER, "1") in rows
    assert ("unclear", "demands", "prs", "medicaid_renewal", "", "1.0.0", OTHER, "1") in rows
    assert all(row[4] in ("", OTHER) and row[6] == OTHER for row in rows)
    assert sum(int(row[7]) for row in rows) == 5


def test_identifier_fields_keep_real_ids_only() -> None:
    known = {"dhs_oig", "ftc_reportfraud"}.__contains__
    models = ("gemini-3.8-flash", "gemini-3.5-flash-lite")
    ok = counter_key(
        request(resource_id="dhs_oig", app_version="1.2.3-beta.1", model_id="mock"),
        known_resource=known, known_models=models,
    )  # fmt: skip
    assert ok[4:] == ("dhs_oig", "1.2.3-beta.1", "mock")
    unknown = counter_key(
        unchecked(resource_id="john_smith", app_version="1.0.0+build.7", model_id="Gemini Pro!"),
        known_resource=known, known_models=models,
    )  # fmt: skip
    assert unknown[4:] == (OTHER, "1.0.0+build.7", OTHER)
    for slug in ("maria-lopez-12-oak-st", "gemini-3-maria-lopez", "custom-model-1"):
        assert counter_key(request(model_id=slug), known_models=models)[6] == OTHER
    for model in ("gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3-pro-preview-06-05"):
        assert counter_key(request(model_id=model))[6] == model  # shape-valid, not configured
    assert counter_key(request(model_id=None, resource_id=None))[4:] == ("", "1.0.0", "")


def test_app_surface_is_counted_as_its_own_enum_value(tmp_path: Path) -> None:
    # S18 "Report a problem" and Settings → About post surface "app" (CL-028(b)), so they no
    # longer inflate the summary counts; the stored value is the enum value, nothing more.
    store = FeedbackStore(tmp_path / "counts.sqlite")
    store.record(request(surface="app", document_category=None, document_type=None, card_id=None,
                         model_id=None))  # fmt: skip
    store.record(request(surface="summary"))
    rows = store.counts()
    assert ("unclear", "app", "prs", "", "", "1.0.0", "", "1") in rows
    assert ("unclear", "summary", "prs", "medicaid_renewal", "", "1.0.0", "gemini-3.8-flash",
            "1") in rows  # fmt: skip
    assert len(rows) == 2


def test_store_narrows_values_the_contract_patterns_accept() -> None:
    # Values that satisfy the coarse CL-026 patterns but are not vetted ids still become OTHER.
    known = {"dhs_oig"}.__contains__
    models = ("gemini-3.8-flash", "gemini-3.5-flash-lite")
    key = counter_key(
        request(resource_id="maria_lopez_12_oak_st", model_id="maria.lopez-12.oak-st",
                app_version="999999999.0.0"),
        known_resource=known, known_models=models,
    )  # fmt: skip
    assert key[4:] == (OTHER, OTHER, OTHER)
