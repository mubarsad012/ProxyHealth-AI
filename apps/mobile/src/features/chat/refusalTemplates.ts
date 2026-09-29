// Fixed refusal / referral templates and starter questions (PRODUCT_SPEC S9, D-17). The model never
// writes these sentences; the client renders them from pack keys.

import type { AnalysisResult, ReferTo, RefusalKind } from '@/api/types';
import type { TFunction } from '@/i18n/useT';

export function refusalKey(kind: RefusalKind): string | null {
  return kind === 'none' ? null : `chat.refusal.${kind}`;
}

export function referKey(to: ReferTo): string | null {
  return to === 'none' ? null : `chat.refer.${to}`;
}

/** Referrals that point at "Get help nearby" get the `btn.get_help` action. */
export function referShowsHelp(to: ReferTo): boolean {
  return to === 'lawyer_or_accredited_rep' || to === 'housing_counselor';
}

/** Initial chips: `questions_to_ask` plus two fixed starters chosen from the paper's demands. */
export function starterQuestions(a: AnalysisResult, t: TFunction, max = 5): string[] {
  const kinds = new Set(a.demands.map((d) => d.kind));
  const starters: string[] = [];
  if (kinds.has('deadline') || kinds.has('relative_deadline') || kinds.has('appointment')) starters.push(t('chat.starter.miss_date'));
  if (kinds.has('amount')) starters.push(t('chat.starter.pay_now'));
  if (kinds.has('document_requested')) starters.push(t('chat.starter.bring'));
  for (const fallback of [t('chat.starter.miss_date'), t('chat.starter.bring')]) {
    if (starters.length >= 2) break;
    if (!starters.includes(fallback)) starters.push(fallback);
  }
  const out: string[] = [];
  for (const q of [...a.questions_to_ask, ...starters.slice(0, 2)]) {
    if (q && !out.includes(q)) out.push(q);
  }
  return out.slice(0, max);
}
