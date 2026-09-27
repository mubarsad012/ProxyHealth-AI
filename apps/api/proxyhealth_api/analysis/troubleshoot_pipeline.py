"""``run_troubleshoot`` (BUILD_PLAN §4.1). WP0: one call, neutral ``TroubleshootModelOut`` map."""

import time

from proxyhealth_api.ai.provider import Part, Task
from proxyhealth_api.analysis.pipeline import (
    PipelineDeps,
    decode_pages,
    hints_for,
    model_meta,
    parsed_as,
    red_flag,
    resource_tags,
)
from proxyhealth_api.contracts.analysis import Safety
from proxyhealth_api.contracts.enums import DisclaimerKind, Provider, ScamRisk, WarningCode
from proxyhealth_api.contracts.model_out import TroubleshootModelOut
from proxyhealth_api.contracts.troubleshoot import TroubleshootRequest, TroubleshootResult


async def run_troubleshoot(req: TroubleshootRequest, deps: PipelineDeps) -> TroubleshootResult:
    media, _ = decode_pages([req.screenshot], deps.settings)
    parts = [Part.of_text(req.user_goal or ""), *media]
    started = time.perf_counter()
    outcome = await deps.ai.generate(
        task=Task.troubleshoot, parts=parts, system="", schema=TroubleshootModelOut,
        pages=1, is_pdf=False, request_id=deps.request_id,
        hints=hints_for(
            demo_sample_id=req.demo_sample_id, target_language=req.target_language,
            mode=req.mode.value,
        ),
    )  # fmt: skip
    latency_ms = int((time.perf_counter() - started) * 1000)
    out = parsed_as(outcome, TroubleshootModelOut)
    demo = bool(req.demo_sample_id) or deps.ai.provider.name is Provider.mock
    warnings: list[WarningCode] = list(outcome.warnings)
    if demo:
        warnings.append(WarningCode.demo_sample)
    return TroubleshootResult(
        request_id=deps.request_id,
        screen_summary=out.screen_summary,
        error_text_quoted=out.error_text_quoted,
        error_meaning=out.error_meaning,
        steps=list(out.steps),
        cautions=list(out.cautions),
        asks_for_credentials_or_payment=out.asks_for_credentials_or_payment,
        is_likely_scam=out.is_likely_scam,
        scam_risk=ScamRisk.likely if out.is_likely_scam else ScamRisk.none,
        scam_reasons=list(out.scam_signals),
        needs_human_help=out.needs_human_help,
        red_flags=[red_flag(r) for r in out.red_flags],
        resource_tags=resource_tags(out.resource_tags),
        screen_text=list(out.screen_text),
        confidence=out.confidence,
        safety=Safety(
            emergency=False, emergency_kinds=[],
            credential_or_payment_request=out.asks_for_credentials_or_payment,
        ),  # fmt: skip
        disclaimer_kind=DisclaimerKind.general_information,
        warnings=warnings,
        model_meta=model_meta(outcome, deps, demo=demo, latency_ms=latency_ms),
    )
