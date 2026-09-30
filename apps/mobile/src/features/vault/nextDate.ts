// Home "next date" card model (PRODUCT_SPEC S3): pure, so the 30-day window is unit-tested.
// The card appears "when a saved reminder is within 30 days": only reminders that are switched on
// count, and the card shows the date the reminder is about (own date, or the demand's `value_iso`),
// not the paper's earliest date and not the fire time.

import { daysUntil, parseLocalDay } from '@/features/reminders/schedule';
import { eventDateOf, isOwnReminder } from '@/features/reminders/service';
import type { DocumentRow, Reminder, StoredDocument } from '@/storage/index';

export const NEXT_DATE_WINDOW_DAYS = 30;

export interface NextDate {
  documentId: string;
  title: string;
  dateIso: string;
}

/** Documents behind the switched-on paper reminders (the only ones `pickNextDate` needs). */
export function reminderDocumentIds(reminders: Reminder[]): string[] {
  const ids = new Set<string>();
  for (const r of reminders) if (r.enabled && !isOwnReminder(r) && r.documentId) ids.add(r.documentId);
  return [...ids];
}

/** Pure: the soonest date within 30 days that has a switched-on reminder. `documentId` is '' for
 *  the user's own date. `docs` holds the stored papers named by `reminderDocumentIds`. */
export function pickNextDate(
  rows: DocumentRow[],
  reminders: Reminder[],
  docs: ReadonlyMap<string, StoredDocument | null>,
  now: Date,
): NextDate | null {
  const candidates: NextDate[] = [];
  const inWindow = (iso: string | null) => {
    const day = parseLocalDay(iso);
    if (!day) return false;
    const until = daysUntil(day, now);
    return until >= 0 && until <= NEXT_DATE_WINDOW_DAYS;
  };
  for (const r of reminders) {
    if (!r.enabled) continue;
    const own = isOwnReminder(r);
    const doc = own ? null : (docs.get(r.documentId) ?? null);
    const date = eventDateOf(r, doc);
    if (!date || !inWindow(date)) continue;
    if (own) {
      candidates.push({ documentId: '', title: r.label, dateIso: date });
      continue;
    }
    const row = rows.find((d) => d.id === r.documentId);
    // A reminder whose paper is gone is not shown (deleting a paper removes its reminders).
    if (!row && !doc) continue;
    candidates.push({ documentId: r.documentId, title: row?.title ?? doc?.title ?? r.label, dateIso: date });
  }
  candidates.sort((a, b) => (a.dateIso < b.dateIso ? -1 : a.dateIso > b.dateIso ? 1 : 0));
  return candidates[0] ?? null;
}
