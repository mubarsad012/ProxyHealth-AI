"""Pipeline helpers for ``AI_PROVIDER=openai_compat`` runtime limits (LOCAL_AI.md §5;
free-ai-providers §4.6; AI_PROMPTS §9.4, §11.9).

A local model needs minutes per paper (≈ 34 s to read a page, then ≈ 19 tokens/s), so three
pipeline steps designed for Gemini's much shorter calls are adjusted here.
Gemini and the mock never reach these paths, so their behaviour and fixtures are unchanged:

* ``check_fallback_budget`` — the D-06 two-call fallback (transcribe, then explain), and the
  §11.8 injection re-run (a second ``analyze_single``, or ``explain``, with the hit blocks
  masked), only start on a loopback endpoint when enough of the request's deadline is left for
  them to finish; otherwise the reader gets an honest "too slow" error at once instead of a
  doomed minute.
* ``same_language_pages`` — when the paper is already in the reader's language, the lines the
  model copied (or skipped, on a stub) become the transcript's own lines; any passage the model
  translated (a bilingual page) is kept.
* ``memoised`` — a phrasing rewrite (§11.9) is asked once per distinct sentence per request.

Nothing here logs content; the one log line is content-free.
"""

import re
from collections.abc import Sequence
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
# must also start before the deadline. With less than this left the fallback cannot finish — nor
# can the injection re-run, a whole second ``analyze_single`` (or an ``explain`` over the text).
OPENAI_COMPAT_FALLBACK_MIN_S = 120

# ``same_language_pages`` lines the model's page text up with the transcript, line by line. A
# stretch of model lines counts as copied from the page when it adds no words of its own beyond
# copy slips (a re-typed digit, a dropped mask): no run of more than ``COPY_SLIP_WORDS`` words the
# page does not have there, and fewer than 1 in ``COPY_SLIP_SHARE`` of its words. Anything else
# is the model's own text — the translated passage of a bilingual page, or a paper whose
# language it mislabelled — and is kept as written. Measured on the 2026-10-22 sweep: the
# re-typed copies add at most 1 word in a row; a translated line adds whole runs.
COPY_SLIP_WORDS = 2
COPY_SLIP_SHARE = 4
_WORD_RE = re.compile(r"\w+")

MemoKey = tuple[str, str, str]


def _base(tag: str) -> str:
    return tag.split("-")[0].lower()


FALLBACK_SKIPPED_ROUTE = "analysis.mode_fallback_skipped"
INJECTION_RERUN_SKIPPED_ROUTE = "analysis.injection_rerun_skipped"


def check_fallback_budget(
    ai: AIService,
    deadline_at: datetime,
    *,
    request_id: str,
    reason: str,
    route: str = FALLBACK_SKIPPED_ROUTE,
) -> None:
    """Raise ``502 model_output_invalid`` (``err.ai_too_slow``) instead of starting a second
    reading — the two-call fallback, or the injection re-run (``route`` =
    ``INJECTION_RERUN_SKIPPED_ROUTE``) — on a loopback ``openai_compat`` endpoint with less than
    ``OPENAI_COMPAT_FALLBACK_MIN_S`` of the request's deadline left. ``reason`` is a fixed code
    string (the ``SchemaFallbackNeeded`` text — ``incomplete``, ``unparsed``, … — or
    ``injection_rerun``)."""
    settings = ai.settings
    if ai.provider.name is not Provider.openai_compat or not settings.openai_compat_is_loopback:
        return
    if ai.remaining_s(deadline_at) >= OPENAI_COMPAT_FALLBACK_MIN_S:
        return
    log_event(
        request_id=request_id, route=route, error_code="fallback_budget",
        provider=ai.provider.name,
    )  # fmt: skip
    raise ApiError(
        ErrorCode.model_output_invalid, 502, "The AI could not finish reading this paper in time.",
        user_message_key=AI_TOO_SLOW_KEY, details={"reason": reason[:40]},
    )  # fmt: skip


def _words(lines: Sequence[str]) -> list[str]:
    return [w for line in lines for w in _WORD_RE.findall(line.lower())]


def _copied(page_lines: Sequence[str], model_lines: Sequence[str]) -> bool:
    """True when ``model_lines`` add no words of their own to ``page_lines`` beyond copy slips
    (see ``COPY_SLIP_WORDS``): a re-typed copy, a merged or split copy, or a fragment of it."""
    page, model = _words(page_lines), _words(model_lines)
    matcher = SequenceMatcher(None, page, model, autojunk=False)
    own = [j2 - j1 for tag, _, _, j1, j2 in matcher.get_opcodes() if tag in ("replace", "insert")]
    return not own or (max(own) <= COPY_SLIP_WORDS and sum(own) * COPY_SLIP_SHARE < len(model))


def _merge(page_lines: list[str], model_lines: list[str]) -> tuple[list[str], bool, bool]:
    """The model's lines with each stretch it copied from the page swapped for the transcript's
    lines. Returns ``(lines, wrote_own_text, copied_any)``. Page lines the model left out are not
    brought back here: the caller restores the whole page only when the model wrote no text of
    its own (a copy, a stub or nothing)."""
    keys = [" ".join(_words([line])) for line in page_lines]
    model_keys = [" ".join(_words([line])) for line in model_lines]
    spans: list[tuple[int, int, int, int]] = []
    matcher = SequenceMatcher(None, keys, model_keys, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "delete":
            continue
        if tag == "replace" and i2 - i1 == j2 - j1:  # same line count: judge line by line
            spans.extend((i1 + k, i1 + k + 1, j1 + k, j1 + k + 1) for k in range(i2 - i1))
        else:
            spans.append((i1, i2, j1, j2))
    merged: list[str] = []
    own = copied = False
    for i1, i2, j1, j2 in spans:
        if _copied(page_lines[i1:i2], model_lines[j1:j2]):
            merged.extend(page_lines[i1:i2])
            copied = copied or i2 > i1
        else:
            merged.extend(model_lines[j1:j2])
            own = True
    return merged, own, copied


def _lines(text: str) -> list[str]:
    return [line for line in text.split("\n") if line.strip()]


def same_language_pages(
    settings: Settings, out: AnalysisModelOut, paper: Transcript, *, detected: str, target: str
) -> AnalysisModelOut:
    """``openai_compat`` only, when the detected language is the target language. For each page
    with text, the model's page text is compared with the page's transcript (its blocks' text, in
    block order, masks applied):

    * nothing written, a stub (a fragment such as the sample banner) or a copy of the page → the
      transcript itself;
    * the model's own text throughout → kept as written (a paper whose language it mislabelled);
    * both — a bilingual page whose other-language passage the model translated → the model's
      lines, with every stretch it copied swapped for the transcript's lines, so the translated
      passage survives.

    The contact scrub, printed-date forms and ``translation_partial`` then run on the result as
    on any translation. Other providers, other languages and blank pages are returned as is."""
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
        merged, own, copied = _merge(_lines(text), [ln for p in written for ln in _lines(p.text)])
        if not own:
            pages.append(TranslatedPage(page=page.page, text=text))
        elif not copied:
            pages.extend(written)
        else:
            pages.append(TranslatedPage(page=page.page, text="\n".join(merged)))
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
