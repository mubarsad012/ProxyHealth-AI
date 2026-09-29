// Reminder schedule math (PRODUCT_SPEC §10.1–§10.2). Pure functions with an injected `now`, so the
// fire-time rules are unit-tested with a fixed clock (reminders.test.ts):
//   • eligible only when `reminder_eligible && verified && date.kind === "stated" && value_iso`;
//   • fires 7, 3 and 1 day(s) before the date at 09:00 LOCAL device time, each skipped if past;
//   • when every standard fire time has passed but the date is today or later, ONE reminder fires
//     in 1 minute (`notif.today_body` when the date is today, the generic body otherwise);
//   • dates before today cannot be scheduled.
// Dates are calendar days in the device's time zone; `YYYY-MM-DD` is never parsed as UTC.

import type { AnalysisResult, Demand } from '@/api/types';

export const REMINDER_OFFSETS_DAYS = [7, 3, 1] as const;
export const REMINDER_HOUR = 9;
export const SOON_DELAY_MS = 60_000;
const DAY_MS = 24 * 60 * 60 * 1000;

export type ReminderOffset = (typeof REMINDER_OFFSETS_DAYS)[number] | 0;

export interface FireSlot {
  fireAt: Date;
  /** Days before the date (7/3/1), or 0 for the "fires in 1 minute" reminder. */
  offsetDays: ReminderOffset;
  /** True when the date itself is today (body `notif.today_body`). */
  today: boolean;
}

export type Eligibility = 'ok' | 'no_date' | 'estimate' | 'unverified' | 'past';

const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})/;

export interface LocalDay {
  y: number;
  m: number;
  d: number;
}

/** `YYYY-MM-DD…` → calendar day, or null. Rejects impossible dates (2026-02-30). */
export function parseLocalDay(iso: string | null | undefined): LocalDay | null {
  if (!iso) return null;
  const match = ISO_DAY.exec(iso);
  if (!match) return null;
  const y = Number(match[1]);
  const m = Number(match[2]);
  const d = Number(match[3]);
  const probe = new Date(y, m - 1, d);
  if (probe.getFullYear() !== y || probe.getMonth() !== m - 1 || probe.getDate() !== d) return null;
  return { y, m, d };
}

/** Local wall-clock time on `day` minus `daysBefore`, at `hour`:00 (DST-safe via Date overflow). */
export function localTime(day: LocalDay, daysBefore: number, hour: number = REMINDER_HOUR): Date {
  return new Date(day.y, day.m - 1, day.d - daysBefore, hour, 0, 0, 0);
}

export function startOfLocalDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0);
}

/** Whole calendar days from today to `day` (0 = today, negative = past). */
export function daysUntil(day: LocalDay, now: Date): number {
  const target = new Date(day.y, day.m - 1, day.d, 12, 0, 0, 0);
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / DAY_MS);
}

/** `YYYY-MM-DD` for a local Date. */
export function toIsoDay(d: Date): string {
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

/** Fire times for a date; empty when the date is before today or not a real date. */
export function computeFireTimes(valueIso: string, now: Date): FireSlot[] {
  const day = parseLocalDay(valueIso);
  if (!day) return [];
  const until = daysUntil(day, now);
  if (until < 0) return [];
  const slots: FireSlot[] = [];
  for (const offset of REMINDER_OFFSETS_DAYS) {
    const at = localTime(day, offset);
    if (at.getTime() > now.getTime()) slots.push({ fireAt: at, offsetDays: offset, today: false });
  }
  if (slots.length === 0) {
    slots.push({ fireAt: new Date(now.getTime() + SOON_DELAY_MS), offsetDays: 0, today: until === 0 });
  }
  return slots;
}

/** Why a demand can or cannot get "Remind me" (§10.1). */
export function reminderEligibility(demand: Demand, now: Date): Eligibility {
  const date = demand.date;
  if (!date || !date.value_iso) return 'no_date';
  if (date.kind !== 'stated') return 'estimate';
  if (!demand.verified || !demand.reminder_eligible) return 'unverified';
  const day = parseLocalDay(date.value_iso);
  if (!day) return 'no_date';
  if (daysUntil(day, now) < 0) return 'past';
  return 'ok';
}

/** Earliest verified, stated date on the paper that is today or later (`DocumentRow.nextDateIso`). */
export function nextStatedDate(analysis: AnalysisResult | null | undefined, now: Date): string | null {
  if (!analysis) return null;
  let best: string | null = null;
  for (const d of analysis.demands ?? []) {
    const iso = d.date?.value_iso;
    if (!iso || d.date?.kind !== 'stated' || !d.verified) continue;
    const day = parseLocalDay(iso);
    if (!day || daysUntil(day, now) < 0) continue;
    const key = iso.slice(0, 10);
    if (best === null || key < best) best = key;
  }
  return best;
}

export interface NotificationText {
  title: string;
  body: string;
}

export type Translate = (key: string, vars?: Record<string, string | number>) => string;

/** Title = app name; body generic unless the user opted into detail (`notif.detail_body`). */
export function notificationText(
  t: Translate,
  slot: Pick<FireSlot, 'today'>,
  detail: { optIn: boolean; documentTitle?: string | null; demandText?: string | null; date?: string | null },
): NotificationText {
  const title = t('app.name');
  if (detail.optIn && detail.documentTitle && detail.demandText && detail.date) {
    return {
      title,
      body: t('notif.detail_body', {
        document_title: detail.documentTitle,
        demand_text: detail.demandText,
        date: detail.date,
      }),
    };
  }
  return { title, body: t(slot.today ? 'notif.today_body' : 'notif.generic_body') };
}

/** The route a reminder notification opens (`/reminders?doc=<analysis_id>`). */
export function reminderUrl(documentId: string | null | undefined): string {
  return documentId ? `/reminders?doc=${encodeURIComponent(documentId)}` : '/reminders';
}
