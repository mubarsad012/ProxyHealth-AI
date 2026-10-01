// Urgency copy helpers (PRODUCT_SPEC §5.5). The level and headline key are computed server-side
// (`analysis/urgency.py`, D-12); the client renders them and decides which CTAs exist. The one
// exception is time passing: a real paper reopened days later (from the vault) re-counts its
// driving date against the device clock (`liveUrgency`), so a hearing that has passed says "This
// date may have passed" instead of a frozen "In 5 days". Sample papers are never re-counted
// (PRODUCT_SPEC §12.3: their dates are pinned to `DEMO_AS_OF`).

import type { AnalysisResult, Demand, DocumentCategory, DocumentType, Urgency, UrgencyLevel } from '@/api/types';
import { urgency as urgencyTokens } from '@/design/tokens';
import { urgencyDaysLine, urgencyHeadlineKey } from '@/design/components/UrgencyBanner';
import { interpolate } from '@/i18n/store';
import type { TFunction } from '@/i18n/useT';
import { daysUntil } from '@/lib/dates';

import { isSampleResult } from './disclaimers';

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

// ---- Re-counting a stored result's driving date (mirror of `analysis/urgency.py`, TAXONOMY §5) ----

const LEVEL_RANK: Record<UrgencyLevel, number> = { info: 0, medium: 1, high: 2, critical: 3, emergency: 4 };
const KEY_DATE_PASSED = 'urgency.critical.date_passed';
const KEY_ESTIMATED = 'urgency.medium.estimated';

/** TAXONOMY §5.2 per-type critical sets (`urgency.py` `CRITICAL_SET`): ≤ 7 days → critical. */
const CRITICAL_SET: Partial<Record<DocumentType, readonly string[]>> = {
  uscis_biometrics: ['appointment'],
  uscis_interview: ['appointment'],
  asylum_fee_notice: ['payment_due'],
  ice_checkin: ['appointment'],
  nta: ['hearing_date'],
  hearing_notice: ['hearing_date'],
  traffic_court: ['hearing_date'],
  eviction_summons: ['hearing_date'],
};
const PAST_CRITICAL_CATEGORIES: readonly DocumentCategory[] = ['immigration', 'court'];
const PAST_CRITICAL_TYPES: readonly DocumentType[] = ['eviction_summons'];
const PAST_HIGH_ROLES: readonly string[] = ['response_due', 'payment_due', 'appointment', 'hearing_date'];

function maxLevel(a: UrgencyLevel, b: UrgencyLevel): UrgencyLevel {
  return LEVEL_RANK[a] >= LEVEL_RANK[b] ? a : b;
}

function thresholdLevel(days: number, criticalAllowed: boolean): UrgencyLevel {
  if (days <= 7 && criticalAllowed) return 'critical';
  if (days <= 14) return 'high';
  if (days <= 30) return 'medium';
  return 'info';
}

function futureHeadline(level: UrgencyLevel, days: number): string {
  if (level === 'critical') return days === 0 ? 'urgency.critical.date_today' : 'urgency.critical.date_soon';
  if (level === 'high') return 'urgency.high.date_soon';
  if (level === 'medium') return 'urgency.medium.date_soon';
  return 'urgency.info.date_later';
}

function pastLevel(role: string | null, category: DocumentCategory, type: DocumentType): UrgencyLevel {
  if (PAST_CRITICAL_CATEGORIES.includes(category) || PAST_CRITICAL_TYPES.includes(type)) return 'critical';
  return role && PAST_HIGH_ROLES.includes(role) ? 'high' : 'medium';
}

/**
 * The urgency to show for `a` today. Unchanged for samples, emergencies, results without a driving
 * date, and when the device's day count matches the server's. Otherwise the days line is re-counted
 * from `nearest_date_iso`; a date that is now past switches to the `date_passed` headline (and the
 * "Verify this date" CTA) at the server's past-date level, and a nearer date can raise the level by
 * the same thresholds. An estimated date is never raised above `medium` (D-12), and the level
 * never drops below what the server said (so a type floor stays).
 */
export function liveUrgency(a: AnalysisResult, now: Date = new Date()): Urgency {
  const u = a.urgency;
  if (u.level === 'emergency' || isSampleResult(a) || !u.nearest_date_iso) return u;
  const days = daysUntil(u.nearest_date_iso, now);
  if (days === null || days === u.days_until) return u;
  const driving = a.demands.find((d) => d.id === u.driving_demand_id) ?? null;
  const role = driving?.role ?? null;
  const estimated = driving?.date?.kind === 'estimated' || u.headline_key === KEY_ESTIMATED;
  const past = days < 0;
  let level: UrgencyLevel;
  let headline: string;
  if (past) {
    level = pastLevel(role, a.category, a.document_type);
    headline = KEY_DATE_PASSED;
  } else {
    const criticalAllowed = !estimated && Boolean(role && CRITICAL_SET[a.document_type]?.includes(role));
    level = thresholdLevel(days, criticalAllowed);
    headline = estimated ? KEY_ESTIMATED : futureHeadline(level, days);
  }
  if (estimated && LEVEL_RANK[level] > LEVEL_RANK.medium) level = 'medium';
  level = maxLevel(level, u.level);
  return { ...u, level, headline_key: headline, days_until: days, past_date: past };
}

/** `a` with `liveUrgency` applied (the same object when nothing changed). */
export function withLiveUrgency<T extends AnalysisResult | null>(a: T, now: Date = new Date()): T {
  if (!a) return a;
  const live = liveUrgency(a, now);
  return (live === a.urgency ? a : { ...a, urgency: live }) as T;
}
