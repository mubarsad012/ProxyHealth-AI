// Client date helpers (ARCHITECTURE §3 `lib/dates.ts`, D-11/D-12/D-26). Deadlines are computed
// ONLY on the server (`analysis/deadline_rules.py`) and urgency there too (`analysis/urgency.py`);
// the one client exception is re-counting days for a stored paper with the server's own rule
// (`features/analysis/urgencyCopy.liveUrgency`). This file does display math on dates the server
// already resolved: days-until for an ISO date, the optional localized-digit line, and
// `estimateDateText` — an estimate's `value_iso` written the way the server writes estimates
// ("November 13, 2026"), only for a stored estimate whose server line is still a bare ISO day. It
// never parses, rewrites or reformats a printed (verbatim) date.

import type { DateInfo, DigitSystem } from '@/api/types';
import { DIGIT_SETS, type DateOrder, localizedDateLine } from '@/i18n/digits';

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

const EN_MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
] as const;

const ISO_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Pack digits (`DIGIT_SETS`) → ASCII, for shape checks only. */
function asciiDigits(text: string): string {
  let out = text;
  for (const set of Object.values(DIGIT_SETS)) {
    if (!set || set === '0123456789') continue;
    out = out.replace(new RegExp(`[${set}]`, 'g'), (ch) => String(set.indexOf(ch)));
  }
  return out;
}

/** True for a bare ISO day in any digits (`2026-11-13`, `۲۰۲۶-۱۱-۱۳`): a server line from before
 *  estimates were written out (stored papers read before Phase 2C). */
export function isIsoDayText(text: string | null | undefined): boolean {
  return Boolean(text) && ISO_ONLY.test(asciiDigits(String(text).trim()));
}

/**
 * An ISO day written the way the server writes an estimate when the printed anchor gives no other
 * pattern (`deadline_rules.estimate_text`): "November 13, 2026" — English month and Western digits
 * in every language (AI_PROMPTS §5.0 rule 7). Only for an estimate whose stored line predates that.
 * Null for a non-ISO input.
 */
export function estimateDateText(iso: string | null | undefined): string | null {
  const m = iso ? ISO_DAY.exec(iso) : null;
  if (!m) return null;
  const month = EN_MONTHS[Number(m[2]) - 1];
  const day = Number(m[3]);
  return month && day >= 1 && day <= 31 ? `${month} ${day}, ${m[1]}` : null;
}
