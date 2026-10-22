"""Pipeline helpers for ``AI_PROVIDER=openai_compat`` runtime limits (LOCAL_AI.md §5;
free-ai-providers §4.6; AI_PROMPTS §9.4, §11.9).

A local model needs minutes per paper (≈ 34 s to read a page, then ≈ 19 tokens/s), so three
pipeline steps designed for Gemini's much shorter calls are adjusted here.
Gemini and the mock never reach these paths, so their behaviour and fixtures are unchanged:

* ``check_fallback_budget`` — the D-06 two-call fallback (transcribe, then explain) only starts
  on a loopback endpoint when enough of the request's deadline is left for it to finish;
  otherwise the reader gets an honest "too slow" error at once instead of a doomed minute.
* ``same_language_pages`` — when the paper is already in the reader's language, its
  "translation" is the transcript itself, copied in code instead of re-typed by the model.
* ``memoised`` — a phrasing rewrite (§11.9) is asked once per distinct sentence per request.

Nothing here logs content; the one log line is content-free.
"""

from datetime import datetime
from difflib import SequenceMatcher

from proxyhealth_api.ai.failover import AIService
from proxyhealth_api.ai.slow_errors import AI_TOO_SLOW_KEY
from proxyhealth_api.analysis.phrasing import Rewriter
from proxyhealth_api.analysis.transcript import Transcript
from proxyhealth_api.contracts.common import TranslatedPage
from proxyhealth_api.contracts.enums import ErrorCode, Provider
from proxyhealth_api.contracts.model_out import AnalysisModelOut
from proxyhealth_api.errors import ApiError
from proxyhealth_api.logging_ import log_event
from proxyhealth_api.settings import Settings

# One loopback transcribe (≈ 34 s page read + ≈ 500–1,000 tokens) is ≈ 65 s; the explain call
# must also start before the deadline. With less than this left the fallback cannot finish.
OPENAI_COMPAT_FALLBACK_MIN_S = 120

# ``same_language_pages``: a page text the model wrote is kept (not replaced by the transcript)
# only when it is a real rewrite of the page — at least half its length and sharing less than
# this share of its words in order — i.e. the model translated a paper whose language it
# mislabelled. A copy of the page (≈ 0.9) or a one-line stub (the sample banner) is replaced.
KEEP_REWRITE_MAX_SIMILARITY = 0.5

MemoKey = tuple[str, str, str]


def _base(tag: str) -> str:
    return tag.split("-")[0].lower()


def check_fallback_budget(
    ai: AIService, deadline_at: datetime, *, request_id: str, reason: str
) -> None:
    """Raise ``502 model_output_invalid`` (``err.ai_too_slow``) instead of starting the two-call
    fallback on a loopback ``openai_compat`` endpoint with less than
    ``OPENAI_COMPAT_FALLBACK_MIN_S`` of the request's deadline left. ``reason`` is the
    ``SchemaFallbackNeeded`` text (fixed by the code: ``incomplete``, ``unparsed``, …)."""
    settings = ai.settings
    if ai.provider.name is not Provider.openai_compat or not settings.openai_compat_is_loopback:
        return
    if ai.remaining_s(deadline_at) >= OPENAI_COMPAT_FALLBACK_MIN_S:
        return
    log_event(
        request_id=request_id, route="analysis.mode_fallback_skipped",
        error_code="fallback_budget", provider=ai.provider.name,
    )  # fmt: skip
    raise ApiError(
        ErrorCode.model_output_invalid, 502, "The AI could not finish reading this paper in time.",
        user_message_key=AI_TOO_SLOW_KEY, details={"reason": reason[:40]},
    )  # fmt: skip


def _words(text: str) -> list[str]:
    return text.lower().split()


def _is_real_rewrite(model_text: str, page_text: str) -> bool:
    if len(model_text.strip()) * 2 < len(page_text.strip()):
        return False  # nothing, or a stub such as the first line only
    ratio = SequenceMatcher(None, _words(model_text), _words(page_text), autojunk=False).ratio()
    return ratio < KEEP_REWRITE_MAX_SIMILARITY


def same_language_pages(
    settings: Settings, out: AnalysisModelOut, paper: Transcript, *, detected: str, target: str
) -> AnalysisModelOut:
    """``openai_compat`` only: when the detected language is the target language, each page with
    text gets the page's own transcript (its blocks' text, in block order, masks applied) as its
    "translation" — unless the model wrote a real rewrite of that page (``_is_real_rewrite``).
    The contact scrub, printed-date forms and ``translation_partial`` then run on the result as
    on any translation. Other providers, other languages and blank papers are returned as is."""
    if settings.ai_provider != "openai_compat" or _base(detected) != _base(target):
        return out
    by_page: dict[int, list[TranslatedPage]] = {}
    for item in out.translated_pages:
        by_page.setdefault(item.page, []).append(item)
    pages: list[TranslatedPage] = []
    for page in paper.pages:
        written = by_page.pop(page.page, [])
        if not page.blocks:
            pages.extend(written)
            continue
        text = "\n".join(b.text for b in page.blocks)
        model_text = "\n".join(p.text for p in written)
        if written and _is_real_rewrite(model_text, text):
            pages.extend(written)
        else:
            pages.append(TranslatedPage(page=page.page, text=text))
    pages.extend(p for rest in by_page.values() for p in rest)  # pages the paper does not have
    return out.model_copy(update={"translated_pages": pages})


def memoised(rewrite: Rewriter, memo: dict[MemoKey, str | None], *, language: str) -> Rewriter:
    """``rewrite`` asked once per (base language, sentence, professional) for one request: the
    English target's ``summary_body`` and ``summary_body_en`` (and a demand that repeats them)
    share one call. A hit spends no budget; a failed rewrite (``None``) is remembered too, so it
    is not retried. ``phrasing.enforce`` still lints every returned candidate."""
    base = _base(language)

    async def cached(sentence: str, professional: str) -> str | None:
        key = (base, sentence.strip(), professional)
        if key in memo:
            return memo[key]
        result = await rewrite(sentence, professional)
        memo[key] = result
        return result

    return cached
