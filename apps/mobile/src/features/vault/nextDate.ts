// Home "next date" card model (PRODUCT_SPEC S3): pure, so the 30-day window is unit-tested.

import { daysUntil, parseLocalDay } from '@/features/reminders/schedule';
import { ownDateOf } from '@/features/reminders/service';
import type { DocumentRow, Reminder } from '@/storage/index';

export const NEXT_DATE_WINDOW_DAYS = 30;

export interface NextDate {
  documentId: string;
  title: string;
  dateIso: string;
}

/** Pure: the soonest saved date within 30 days — a saved paper's next stated date, or one of the
 *  user's own reminder dates. `documentId` is '' for an own date. */
export function pickNextDate(rows: DocumentRow[], reminders: Reminder[], now: Date): NextDate | null {
  const candidates: NextDate[] = [];
  const inWindow = (iso: string | null) => {
    const day = parseLocalDay(iso);
    if (!day) return false;
    const until = daysUntil(day, now);
    return until >= 0 && until <= NEXT_DATE_WINDOW_DAYS;
  };
  for (const r of rows) {
    if (r.nextDateIso && inWindow(r.nextDateIso)) {
      candidates.push({ documentId: r.id, title: r.title, dateIso: r.nextDateIso.slice(0, 10) });
    }
  }
  for (const r of reminders) {
    const own = ownDateOf(r);
    if (r.enabled && own && inWindow(own)) candidates.push({ documentId: '', title: r.label, dateIso: own });
  }
  candidates.sort((a, b) => (a.dateIso < b.dateIso ? -1 : a.dateIso > b.dateIso ? 1 : 0));
  return candidates[0] ?? null;
}
