// Client date helpers (ARCHITECTURE §3 `lib/dates.ts`, D-11/D-12/D-26). Deadlines and urgency are
// computed ONLY on the server (`analysis/deadline_rules.py`, `analysis/urgency.py`); this file does
// display math on dates the server already resolved: days-until for a stated ISO date and the
// optional localized-digit line. It never parses, rewrites or reformats a printed (verbatim) date.

import type { DateInfo, DigitSystem } from '@/api/types';
import { type DateOrder, localizedDateLine } from '@/i18n/digits';

const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})/;

/** Local-midnight Date for an ISO calendar day, or null. */
export function isoDay(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const m = ISO_DAY.exec(iso);
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Whole calendar days from `now` (local) to the ISO day; negative when past; null when unknown. */
export function daysUntil(iso: string | null | undefined, now: Date = new Date()): number | null {
  const target = isoDay(iso);
  if (!target) return null;
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

/**
 * The additional localized line under a verbatim date (D-26): the server's `localized_line` when it
 * sent one, else a digit-localized day/month/year built from `value_iso` for packs with their own
 * digits. Western-digit packs get null (the verbatim value is already readable).
 */
export function extraDateLine(
  date: DateInfo | null | undefined,
  digitSystem: DigitSystem,
  order: DateOrder = 'auto',
): string | null {
  if (!date) return null;
  if (date.localized_line) return date.localized_line;
  if (date.kind !== 'stated') return null;
  return localizedDateLine(date.value_iso, digitSystem, order);
}

/** ISO timestamp → `YYYY-MM-DD` (vault titles, reminders); never used on printed dates. */
export function isoDateOnly(iso: string): string {
  return ISO_DAY.exec(iso)?.[0] ?? iso.slice(0, 10);
}
