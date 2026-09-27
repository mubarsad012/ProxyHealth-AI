"""``run_chat`` (BUILD_PLAN §4.1). WP0: one fast call, neutral ``ChatModelOut`` mapping."""

import json
import time

from proxyhealth_api.ai.provider import Part, Task
from proxyhealth_api.analysis.pipeline import (
    PipelineDeps,
    disclaimer_for,
    hints_for,
    model_meta,
    parsed_as,
    resource_tags,
)
from proxyhealth_api.contracts.analysis import Safety
from proxyhealth_api.contracts.chat import ChatAnswer, ChatRequest, Quote
from proxyhealth_api.contracts.enums import Provider, WarningCode
from proxyhealth_api.contracts.model_out import ChatModelOut


def _quotes(req: ChatRequest, span_ids: list[str]) -> list[Quote]:
    blocks = {b.id: b for page in req.analysis.original_text for b in page.blocks}
    return [
        Quote(span_id=sid, text=blocks[sid].text, page=blocks[sid].page)
        for sid in span_ids
        if sid in blocks
    ]


async def run_chat(req: ChatRequest, deps: PipelineDeps) -> ChatAnswer:
    history = [m.model_dump() for m in req.messages]
    parts = [
        Part.of_text(req.analysis.model_dump_json()),
        Part.of_text(json.dumps(history, ensure_ascii=False)),
        Part.of_text(req.question),
    ]
    started = time.perf_counter()
    outcome = await deps.ai.generate(
        task=Task.chat, parts=parts, system="", schema=ChatModelOut,
        pages=1, is_pdf=False, request_id=deps.request_id,
        hints=hints_for(
            demo_sample_id=req.demo_sample_id, target_language=req.target_language,
            question=req.question,
        ),
    )  # fmt: skip
    latency_ms = int((time.perf_counter() - started) * 1000)
    out = parsed_as(outcome, ChatModelOut)
    demo = bool(req.demo_sample_id) or deps.ai.provider.name is Provider.mock
    warnings: list[WarningCode] = list(outcome.warnings)
    if demo:
        warnings.append(WarningCode.demo_sample)
    grounded = _quotes(req, out.grounded_span_ids)
    return ChatAnswer(
        request_id=deps.request_id,
        answer=out.answer,
        grounded_span_ids=[q.span_id for q in grounded],
        grounded_quotes=grounded,
        not_in_document=out.not_in_document,
        refusal_kind=out.refusal_kind,
        refer_to_professional=out.refer_to_professional,
        distress_acknowledged=out.distress_acknowledged,
        suggested_questions=list(out.suggested_questions),
        resource_tags=resource_tags(out.resource_tags),
        safety=Safety(emergency=False, emergency_kinds=[], credential_or_payment_request=False),
        disclaimer_kind=disclaimer_for(req.analysis.category),
        warnings=warnings,
        model_meta=model_meta(outcome, deps, demo=demo, latency_ms=latency_ms),
    )
