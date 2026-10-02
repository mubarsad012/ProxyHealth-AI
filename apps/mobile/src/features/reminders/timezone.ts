// Reminders follow the device's local 09:00 (PRODUCT_SPEC §10.2 "Time zone: Device local;
// recomputed on timezone change events at app start"). A scheduled notification is an absolute
// instant, so after the phone moves to another time zone a "9:00" reminder would ring at another
// hour (or on another day). At app start (and when the app comes back to the front) the zone is
// compared with the one stored when reminders were last checked; when it changed, every future
// 7/3/1-day reminder is moved to 09:00 in the new zone and its notification re-scheduled.
//   • The slot (7, 3 or 1 days before) is read on the wall clock of the OLD zone (its stored UTC
//     offset; a DST error of an hour cannot move a 09:00 time to another day).
//   • A reminder is never lost: when 09:00 in the new zone has already passed, the old (still
//     future) time is kept; the 1-minute "soon" reminder and past rows are left alone.
//   • Web is unaffected: nothing is scheduled there and downloaded .ics files carry their own times.
// Only the zone name and UTC offset are stored (kv), never anything about a paper.

import { getCalendars } from 'expo-localization';

import type { Reminder, StoredDocument } from '@/storage/index';

import { docFor, moveReminder } from './manage';
import { localTime, parseLocalDay, REMINDER_OFFSETS_DAYS, type ReminderOffset } from './schedule';
import { eventDateOf, type RemindersDeps } from './service';

const DAY_MS = 86_400_000;

/** kv key (the `ph:` prefix makes "Delete everything" remove it with the rest). */
export const ZONE_KEY = 'ph:reminders:time_zone';

export interface ZoneStamp {
  /** IANA name ("America/New_York"), or null when the platform does not say. */
  zone: string | null;
  /** Minutes EAST of UTC at the time of the stamp (−240 for New York in summer). */
  offsetMinutes: number;
}

export interface ZoneStore {
  get(): Promise<ZoneStamp | null>;
  set(stamp: ZoneStamp): Promise<void>;
}

/** The device's current zone: expo-localization (SDK 57 `getCalendars()[0].timeZone`), else Intl. */
export function deviceZone(now: Date = new Date()): ZoneStamp {
  let zone: string | null = null;
  try {
    zone = getCalendars()[0]?.timeZone ?? null;
  } catch {
    zone = null;
  }
  if (!zone) {
    try {
      zone = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
    } catch {
      zone = null;
    }
  }
  return { zone, offsetMinutes: -now.getTimezoneOffset() };
}

export function isZoneStamp(value: unknown): value is ZoneStamp {
  if (!value || typeof value !== 'object') return false;
  const v = value as Record<string, unknown>;
  return (v.zone === null || typeof v.zone === 'string') && typeof v.offsetMinutes === 'number' && Number.isFinite(v.offsetMinutes);
}

/** Same named zone → no change (DST is already in every scheduled instant); else compare offsets. */
export function zoneChanged(prev: ZoneStamp, current: ZoneStamp): boolean {
  if (prev.zone && current.zone) return prev.zone !== current.zone;
  return prev.offsetMinutes !== current.offsetMinutes;
}

/** Which 7/3/1-day slot a stored fire time was for, read in the zone it was scheduled in. */
export function slotOfFireTime(fireAtIso: string, eventIso: string, prevOffsetMinutes: number): ReminderOffset | null {
  const fire = Date.parse(fireAtIso);
  const day = parseLocalDay(eventIso);
  if (Number.isNaN(fire) || !day) return null;
  const wall = new Date(fire + prevOffsetMinutes * 60_000);
  const wallDay = Date.UTC(wall.getUTCFullYear(), wall.getUTCMonth(), wall.getUTCDate());
  const eventDay = Date.UTC(day.y, day.m - 1, day.d);
  const before = Math.round((eventDay - wallDay) / DAY_MS);
  return (REMINDER_OFFSETS_DAYS as readonly number[]).includes(before) ? (before as ReminderOffset) : null;
}

/** The new fire time after a zone change (09:00 local in the new zone), or null to keep it. */
export function retimedFireAt(r: Pick<Reminder, 'fireAt'>, eventIso: string | null, prevOffsetMinutes: number, now: Date): Date | null {
  if (!eventIso) return null;
  const old = Date.parse(r.fireAt);
  if (Number.isNaN(old) || old <= now.getTime()) return null;
  const slot = slotOfFireTime(r.fireAt, eventIso, prevOffsetMinutes);
  const day = parseLocalDay(eventIso);
  if (slot === null || !day) return null;
  const at = localTime(day, slot);
  if (at.getTime() === old) return null;
  // Never lose a reminder: 09:00 already passed in the new zone → keep the old future time.
  if (at.getTime() <= now.getTime()) return null;
  return at;
}

/**
 * App start / back to the front (native): when the zone changed since the last check, move every
 * future reminder to 09:00 in the new zone. Resolves the number of reminders moved. The stamp is
 * written after the move, so a crash half-way repeats the (idempotent) move on the next start.
 */
export async function retimeForZoneChange(deps: RemindersDeps, store: ZoneStore, current: ZoneStamp): Promise<number> {
  if (deps.isWeb) return 0;
  const prev = await store.get();
  if (!prev || !zoneChanged(prev, current)) {
    if (!prev || prev.zone !== current.zone || prev.offsetMinutes !== current.offsetMinutes) await store.set(current);
    return 0;
  }
  const granted = (await deps.notifications.getPermission()) === 'granted';
  const now = deps.now();
  const cache = new Map<string, StoredDocument | null>();
  let moved = 0;
  for (const r of await deps.reminders.list()) {
    const doc = await docFor(deps, cache, r.documentId);
    const at = retimedFireAt(r, eventDateOf(r, doc), prev.offsetMinutes, now);
    if (!at) continue;
    await moveReminder(deps, r, doc, at, granted);
    moved += 1;
  }
  await store.set(current);
  if (moved > 0) deps.onChange?.();
  return moved;
}
