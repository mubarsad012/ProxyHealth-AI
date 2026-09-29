// Chat request pieces (API_CONTRACT §3.7, PRODUCT_SPEC S9). The server is stateless: the client
// re-sends the analysis context (original_text ≤ 60 000 chars; oldest pages dropped first) and the
// last ≤ 8 messages (each ≤ 1000 chars). History stays on the device only.

import type { AnalysisContext, AnalysisResult, ChatMessage, ChatRequest, PageText } from '@/api/types';

export const MAX_CONTEXT_CHARS = 60_000;
export const DEFAULT_MAX_HISTORY = 8;
export const DEFAULT_MAX_QUESTION = 1000;

function pageChars(p: PageText): number {
  return p.blocks.reduce((n, b) => n + b.text.length, 0);
}

/** Keep the transcript under `max` chars: drop the oldest pages first, then trim blocks. */
export function compactOriginalText(pages: readonly PageText[], max: number = MAX_CONTEXT_CHARS): PageText[] {
  const out = pages.slice();
  let total = out.reduce((n, p) => n + pageChars(p), 0);
  while (total > max && out.length > 1) {
    total -= pageChars(out[0]);
    out.shift();
  }
  if (total <= max || !out.length) return out;
  const only = out[0];
  const blocks = [];
  let used = 0;
  for (const b of only.blocks) {
    if (used + b.text.length > max) break;
    used += b.text.length;
    blocks.push(b);
  }
  return [{ ...only, blocks }];
}

export function analysisContext(a: AnalysisResult, maxChars: number = MAX_CONTEXT_CHARS): AnalysisContext {
  return {
    analysis_id: a.analysis_id,
    category: a.category,
    document_type: a.document_type,
    detected_language: a.detected_language,
    sender_as_written: a.sender_as_written,
    summary: a.summary,
    demands: a.demands,
    unverified: a.unverified,
    plan_steps: a.plan_steps,
    red_flags: a.red_flags,
    glossary: a.glossary,
    original_text: compactOriginalText(a.original_text, maxChars),
    urgency: a.urgency,
  };
}

/** The last `max` turns, each capped at 1000 chars (history cap: oldest dropped silently). */
export function historyForRequest(messages: readonly ChatMessage[], max: number = DEFAULT_MAX_HISTORY): ChatMessage[] {
  return messages.slice(-max).map((m) => ({ role: m.role, text: m.text.slice(0, DEFAULT_MAX_QUESTION) }));
}

export function buildChatRequest(opts: {
  analysis: AnalysisResult;
  history: readonly ChatMessage[];
  question: string;
  targetLanguage: string;
  demoSampleId: string | null;
  maxHistory?: number;
  maxQuestion?: number;
}): ChatRequest {
  return {
    analysis: analysisContext(opts.analysis),
    messages: historyForRequest(opts.history, opts.maxHistory ?? DEFAULT_MAX_HISTORY),
    question: opts.question.trim().slice(0, opts.maxQuestion ?? DEFAULT_MAX_QUESTION),
    target_language: opts.targetLanguage,
    demo_sample_id: opts.demoSampleId,
  };
}
