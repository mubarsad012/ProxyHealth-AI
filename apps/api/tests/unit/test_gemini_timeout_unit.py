"""The SDK's ``HttpOptions.timeout`` unit (D-05; AI_PROMPTS §9.1). WP1 lane 1B.

``gemini.py`` converts ``UPSTREAM_TIMEOUT_S`` to **milliseconds** because the installed
google-genai documents ``HttpOptions.timeout`` that way. If a future SDK changes the unit this
test (and the import-time check in ``gemini.py``) must fail loudly instead of silently timing out
90 000× too early or too late.
"""

import re

from google.genai import types

from proxyhealth_api.ai import gemini
from proxyhealth_api.settings import Settings


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"ai_provider": "mock"}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_sdk_documents_timeout_in_milliseconds() -> None:
    doc = types.HttpOptions.model_fields["timeout"].description or ""
    assert re.search(r"millisecond", doc, re.I), (
        "google-genai changed the unit of HttpOptions.timeout; update gemini.py: " + repr(doc)
    )
    assert gemini.HTTP_TIMEOUT_DOC == doc


def test_http_options_timeout_is_upstream_timeout_s_times_1000() -> None:
    opts = gemini.build_http_options(_settings(upstream_timeout_s=90))
    assert opts.timeout == 90_000
    assert gemini.build_http_options(_settings(upstream_timeout_s=7)).timeout == 7_000


def test_retry_options_per_d05() -> None:
    opts = gemini.build_http_options(_settings())
    retry = opts.retry_options
    assert retry is not None
    assert retry.attempts == 2
    assert retry.initial_delay == 1.0
    assert retry.max_delay == 4.0
    assert retry.http_status_codes == [408, 500, 502, 503, 504]


def test_sdk_never_retries_429_itself() -> None:
    # The key pool owns 429 (D-07): an SDK-level retry would hide rotation and Retry-After.
    opts = gemini.build_http_options(_settings())
    assert opts.retry_options is not None
    assert 429 not in (opts.retry_options.http_status_codes or [])
    assert 429 not in gemini.RETRY_STATUS_CODES


def test_sdk_enum_names_used_by_gemini_py_still_exist() -> None:
    # AI_PROMPTS §9 names verified against the installed SDK; keep them verified.
    for name in ("MINIMAL", "LOW", "MEDIUM", "HIGH"):
        assert name in types.ThinkingLevel.__members__
    for name in ("MEDIA_RESOLUTION_MEDIUM", "MEDIA_RESOLUTION_HIGH"):
        assert name in types.MediaResolution.__members__
    for name in gemini.BLOCK_FINISH | {"STOP", "MAX_TOKENS"}:
        assert name in types.FinishReason.__members__
    for name in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "OTHER"):
        assert name in types.BlockedReason.__members__
    fields = types.GenerateContentConfig.model_fields
    for name in (
        "system_instruction",
        "response_mime_type",
        "response_schema",
        "thinking_config",
        "media_resolution",
        "max_output_tokens",
    ):
        assert name in fields
    assert {"include_thoughts", "thinking_level"} <= set(types.ThinkingConfig.model_fields)
