// Estimated dates written out for reading (PRODUCT_SPEC S7 item 8, D-11, D-12, CL-080(d)). An
// `estimated` DateInfo has no printed date: the server computed `value_iso` from a printed phrase
// plus a cited rule (`deadline_rules.py`) and writes it out in `localized_line`
// (`deadline_rules.estimate_text`: like the printed anchor — "November 13, 2026", "11/13/2026" —
// English month and Western digits in every language, AI_PROMPTS §5.0 rule 7). The demand row
// leads with "About {date} (estimate)" using that line; a pack with its own digits gets the extra
// digit line from `value_iso` (`i18n/digits.localizedDateLine`), as a stated date does. A stored
// paper read before the server wrote estimates out still carries a bare ISO day there and in the
// urgency banner's `{date}`; both are then written the server's default way (`estimateDateText`).
// Nothing here computes a date, and a printed (stated) date is never touched.

import { useMemo } from 'react';

import type { DateInfo, DigitSystem, Urgency } from '@/api/types';
import { type DateOrder, localizedDateLine } from '@/i18n/digits';
import type { TFunction } from '@/i18n/useT';
import { estimateDateText, isIsoDayText } from '@/lib/dates';

/** "About {date} (estimate)" (keys-2c-mobilescan.json). */
export const ESTIMATE_ABOUT_KEY = 'demand.estimate_about';

/** The readable estimate: the server's `localized_line`, or `value_iso` written out the server's
 *  default way when that line is missing or still a bare ISO day. Null when not an estimate. */
export function estimateReadable(date: DateInfo | null | undefined): string | null {
  if (!date || date.kind !== 'estimated') return null;
  const line = date.localized_line?.trim();
  if (line && !isIsoDayText(line)) return line;
  return estimateDateText(date.value_iso);
}

/** The demand-row line for an estimated date, or null when the date is not an estimate. */
export function estimatedDateLine(date: DateInfo | null | undefined, t: TFunction): string | null {
  const readable = estimateReadable(date);
  return readable ? t(ESTIMATE_ABOUT_KEY, { date: readable }) : null;
}

/** The pack-digit line under the estimate (`۱۳/۱۱/۲۰۲۶`); null for Western-digit packs. */
export function estimatedDigitsLine(date: DateInfo | null | undefined, digitSystem: DigitSystem, order: DateOrder = 'auto'): string | null {
  if (!date || date.kind !== 'estimated') return null;
  return localizedDateLine(date.value_iso, digitSystem, order);
}

/** The one headline whose `{date}` is an estimate (`urgency.py`); every other `{date}` is printed. */
export const ESTIMATED_HEADLINE_KEY = 'urgency.medium.estimated';

/** `u` with an estimated headline's raw ISO `{date}` (a stored paper from before the server wrote
 *  estimates out) written the server's way; the same object otherwise — a printed date, even one
 *  printed as `2026-10-17`, is never rewritten. */
export function localizeUrgencyDate(u: Urgency): Urgency {
  if (u.headline_key !== ESTIMATED_HEADLINE_KEY) return u;
  const params = u.headline_params ?? {};
  const raw = params.date;
  if (typeof raw !== 'string' || !isIsoDayText(raw)) return u;
  const readable = estimateDateText(typeof params.date_iso === 'string' ? params.date_iso : raw);
  if (!readable) return u;
  return { ...u, headline_params: { ...params, date: readable } };
}

export function useLocalizedUrgency(u: Urgency): Urgency {
  return useMemo(() => localizeUrgencyDate(u), [u]);
}
