// Urgency copy helpers (PRODUCT_SPEC §5.5). The level and headline key are computed server-side
// (`analysis/urgency.py`, D-12); the client only renders them and decides which CTAs exist.

import type { AnalysisResult, Demand, Urgency } from '@/api/types';
import { urgency as urgencyTokens } from '@/design/tokens';
import { urgencyDaysLine, urgencyHeadlineKey } from '@/design/components/UrgencyBanner';
import { interpolate } from '@/i18n/store';
import type { TFunction } from '@/i18n/useT';

/** Plain sentence for read-aloud / quick copies: word + headline + days line. */
export function urgencySpeech(u: Urgency, t: TFunction): string {
  const parts = [t(urgencyTokens[u.level].wordKey), interpolate(t(urgencyHeadlineKey(u)), u.headline_params ?? {})];
  const days = urgencyDaysLine(u);
  if (days) parts.push(t(days.key, { days: days.days }));
  if (u.floor_applied) parts.push(t('urgency.floor_note'));
  return parts.join('. ');
}

/** The demand that drives the banner, only if it is verified (never an unverified one). */
export function drivingDemand(a: AnalysisResult): Demand | null {
  const id = a.urgency.driving_demand_id;
  if (!id) return null;
  const d = a.demands.find((x) => x.id === id);
  return d && d.verified ? d : null;
}

/** A `contact` demand whose number is printed on the page (verified) → `tel:` href, else null. */
export function printedPhoneHref(d: Demand): string | null {
  if (d.kind !== 'contact' || !d.verified) return null;
  const digits = d.value_verbatim.replace(/[^\d+]/g, '');
  if (digits.replace(/\D/g, '').length < 7) return null;
  if (!d.source_quote.includes(d.value_verbatim)) return null;
  return `tel:${digits}`;
}

export function firstPrintedPhone(a: AnalysisResult): string | null {
  for (const d of a.demands) {
    const href = printedPhoneHref(d);
    if (href) return href;
  }
  return null;
}
