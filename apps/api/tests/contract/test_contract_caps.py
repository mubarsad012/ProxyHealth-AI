"""Phase 2C contract caps: ``AnalysisContext`` (= ``chat_pipeline.bounded_context``) and
``ResourceMatchRequest.institutions_as_written`` (= ``resources.matcher`` bounds)."""

from typing import Any

import pytest
from pydantic import ValidationError

from proxyhealth_api.analysis import chat_pipeline
from proxyhealth_api.contracts import chat as chat_contract
from proxyhealth_api.contracts import resources as resources_contract
from proxyhealth_api.contracts.chat import AnalysisContext
from proxyhealth_api.contracts.common import PageText, TextBlock
from proxyhealth_api.contracts.resources import ResourceMatchRequest
from proxyhealth_api.main import create_app
from proxyhealth_api.resources import matcher
from proxyhealth_api.settings import Settings


def test_context_caps_equal_what_the_chat_pipeline_reads() -> None:
    assert chat_contract.MAX_CONTEXT_PAGES == chat_pipeline.MAX_CONTEXT_PAGES
    assert chat_contract.MAX_BLOCKS_PER_PAGE == chat_pipeline.MAX_BLOCKS_PER_PAGE
    assert chat_contract.MAX_BLOCK_CHARS == chat_pipeline.MAX_BLOCK_CHARS
    assert chat_contract.MAX_CONTEXT_ITEMS == chat_pipeline.MAX_CONTEXT_ITEMS


def test_institution_caps_equal_the_matcher_bounds() -> None:
    assert resources_contract.MAX_INSTITUTIONS == matcher.MAX_INSTITUTIONS
    assert resources_contract.MAX_INSTITUTION_CHARS == matcher.MAX_INSTITUTION_CHARS


def block(n: int, text: str = "Please reply.") -> TextBlock:
    return TextBlock(id=f"b{n}", page=1, text=text, bbox=None, is_handwriting=False,
                     is_unclear=False)  # fmt: skip


def context(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "analysis_id": "a1", "category": "benefits", "document_type": "other_notice",
        "detected_language": "en", "sender_as_written": None,
        "summary": {"title": "t", "body": "b", "body_en": "b", "span_ids": []},
        "demands": [], "unverified": [], "plan_steps": [], "red_flags": [], "glossary": [],
        "original_text": [],
        "urgency": {"level": "info", "headline_key": "urgency.info.headline",
                    "headline_params": {}, "driving_demand_id": None, "nearest_date_iso": None,
                    "days_until": None, "past_date": False, "floor_applied": False,
                    "verify_resource_id": None},
    }  # fmt: skip
    base.update(overrides)
    return base


def pages(count: int, blocks: int = 1, text: str = "Please reply.") -> list[dict[str, Any]]:
    return [
        PageText(page=n, width=None, height=None,
                 blocks=[block(i, text) for i in range(blocks)]).model_dump(mode="json")
        for n in range(1, count + 1)
    ]  # fmt: skip


@pytest.fixture
def valid_context() -> dict[str, Any]:
    AnalysisContext.model_validate(context())  # the minimal shape is itself valid
    return context()


def test_context_at_the_caps_is_accepted(valid_context: dict[str, Any]) -> None:
    ctx = {**valid_context, "original_text": pages(60, blocks=2, text="x" * 4000)}
    assert len(AnalysisContext.model_validate(ctx).original_text) == 60
    one_full_page = {**valid_context, "original_text": pages(1, blocks=400)}
    assert len(AnalysisContext.model_validate(one_full_page).original_text[0].blocks) == 400


@pytest.mark.parametrize(
    ("field", "value", "loc"),
    [
        ("original_text", pages(61), ("original_text",)),
        ("original_text", pages(1, blocks=401), ("original_text",)),
        ("original_text", pages(1, text="x" * 4001), ("original_text",)),
        ("glossary", [{"term_as_written": "t", "explanation": "e"}] * 61, ("glossary",)),
    ],
)
def test_context_over_a_cap_is_refused(
    valid_context: dict[str, Any], field: str, value: Any, loc: tuple[str, ...]
) -> None:
    with pytest.raises(ValidationError) as info:
        AnalysisContext.model_validate({**valid_context, field: value})
    assert any(err["loc"][: len(loc)] == loc for err in info.value.errors())


def test_institutions_are_capped_per_item_and_per_list() -> None:
    base: dict[str, Any] = {"tags": ["immigration_legal_help"], "language": "en"}
    ok = ResourceMatchRequest.model_validate({**base, "institutions_as_written": ["x" * 200] * 10})
    assert len(ok.institutions_as_written) == 10
    with pytest.raises(ValidationError):
        ResourceMatchRequest.model_validate({**base, "institutions_as_written": ["x" * 201]})
    with pytest.raises(ValidationError):
        ResourceMatchRequest.model_validate({**base, "institutions_as_written": ["Inova"] * 11})


def test_caps_are_in_the_openapi_contract() -> None:
    schemas = create_app(Settings(_env_file=None)).openapi()["components"]["schemas"]
    ctx = schemas["AnalysisContext"]["properties"]
    for name in ("original_text", "demands", "unverified", "plan_steps", "red_flags", "glossary"):
        assert ctx[name]["maxItems"] == 60, name
    inst = schemas["ResourceMatchRequest"]["properties"]["institutions_as_written"]
    assert inst["maxItems"] == 10 and inst["items"]["maxLength"] == 200
