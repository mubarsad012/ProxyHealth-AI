// Reminder list management (PRODUCT_SPEC S14 / §10.2): per-reminder on/off, .ics for one group or
// all, and "rescheduled from the table on app start if the OS lost them". Same injected deps as
// service.ts. The vault has no "update notification id" call, so re-arming a reminder adds the
// new row first and then removes the old one (whose notification is already cancelled).

import { buildIcs, type IcsEvent, icsFileName } from '@/lib/ics';
import type { IcsOfferResult } from '@/lib/notifications';
import type { Reminder, StoredDocument } from '@/storage/index';

import { notificationText, reminderUrl, toIsoDay } from './schedule';
import { eventDateOf, findDemand, type RemindersDeps } from './service';

/** True when the reminder's date is today (body `notif.today_body`). */
function isToday(r: Reminder, doc: StoredDocument | null, now: Date): boolean {
  const iso = eventDateOf(r, doc);
  return iso !== null && iso.slice(0, 10) === toIsoDay(now);
}

async function docFor(deps: RemindersDeps, cache: Map<string, StoredDocument | null>, id: string) {
  if (!id) return null;
  if (!cache.has(id)) cache.set(id, await deps.getDocument(id).catch(() => null));
  return cache.get(id) ?? null;
}

function textFor(deps: RemindersDeps, r: Reminder, doc: StoredDocument | null, now: Date) {
  const demand = findDemand(doc?.analysis, r.demandId);
  const date = eventDateOf(r, doc);
  return notificationText(deps.t, { today: isToday(r, doc, now) }, {
    optIn: r.detailOptIn,
    documentTitle: doc?.analysis?.summary?.title ?? doc?.title ?? (r.documentId ? null : r.label),
    demandText: demand?.text ?? r.label,
    date: demand?.value_verbatim || date,
  });
}

async function rearm(deps: RemindersDeps, r: Reminder, doc: StoredDocument | null): Promise<void> {
  const now = deps.now();
  const text = textFor(deps, r, doc, now);
  const notificationId = await deps.notifications.schedule({
    fireAt: new Date(r.fireAt),
    title: text.title,
    body: text.body,
    url: reminderUrl(r.documentId),
  });
  const { id: _old, ...rest } = r;
  await deps.reminders.add({ ...rest, notificationId, enabled: true });
  await deps.reminders.remove(r.id);
}

/** Toggle one reminder. Off cancels its notification; on re-schedules it (native, future only). */
export async function setReminderEnabled(deps: RemindersDeps, r: Reminder, on: boolean): Promise<void> {
  if (!on) {
    if (r.notificationId) await deps.notifications.cancel(r.notificationId);
    await deps.reminders.setEnabled(r.id, false);
    deps.onChange?.();
    return;
  }
  const future = Date.parse(r.fireAt) > deps.now().getTime();
  if (!deps.isWeb && future && (await deps.notifications.getPermission()) === 'granted') {
    await rearm(deps, r, await deps.getDocument(r.documentId).catch(() => null));
  } else {
    await deps.reminders.setEnabled(r.id, true);
  }
  deps.onChange?.();
}

/** Calendar events for the given reminders: enabled, still in the future, one VEVENT each. */
export async function icsEvents(deps: RemindersDeps, reminders: Reminder[]): Promise<IcsEvent[]> {
  const now = deps.now();
  const cache = new Map<string, StoredDocument | null>();
  const out: IcsEvent[] = [];
  for (const r of reminders) {
    if (!r.enabled || Date.parse(r.fireAt) <= now.getTime()) continue;
    const doc = await docFor(deps, cache, r.documentId);
    const shown = textFor(deps, r, doc, now);
    const generic = notificationText(deps.t, { today: isToday(r, doc, now) }, { optIn: false });
    out.push({ uid: r.id, start: new Date(r.fireAt), summary: shown.body, alarmText: generic.body });
  }
  return out;
}

/** Build the .ics text synchronously from prepared events (keeps the web download in the gesture). */
export function offerEvents(deps: RemindersDeps, events: IcsEvent[]): Promise<IcsOfferResult> {
  if (events.length === 0) return Promise.resolve('unavailable');
  return deps.offerIcs(icsFileName(), buildIcs(events, { now: deps.now() }));
}

/** App start (native): re-schedule enabled future reminders the OS no longer has. */
export async function rescheduleMissing(deps: RemindersDeps): Promise<number> {
  if (deps.isWeb) return 0;
  if ((await deps.notifications.getPermission()) !== 'granted') return 0;
  const scheduled = new Set(await deps.notifications.scheduledIds());
  const now = deps.now().getTime();
  const cache = new Map<string, StoredDocument | null>();
  let count = 0;
  for (const r of await deps.reminders.list()) {
    if (!r.enabled || Date.parse(r.fireAt) <= now) continue;
    if (r.notificationId && scheduled.has(r.notificationId)) continue;
    await rearm(deps, r, await docFor(deps, cache, r.documentId));
    count += 1;
  }
  if (count > 0) deps.onChange?.();
  return count;
}
