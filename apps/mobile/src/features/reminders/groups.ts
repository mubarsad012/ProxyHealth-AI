// S14 list model (PRODUCT_SPEC §10.3): reminders sorted by fire time, grouped by paper (own dates
// in one "My own dates" group), then by the date on that paper. Pure (unit-tested).

import type { Reminder, StoredDocument } from '@/storage/index';

import { eventDateOf, findDemand, isOwnReminder } from './service';

export const OWN_GROUP_KEY = 'own';

export interface DateItem {
  key: string;
  documentId: string;
  demandId: string;
  /** Demand text (or the user's own title + note). */
  text: string;
  /** Printed value, shown verbatim in <Bidi>. */
  verbatim: string | null;
  localizedLine: string | null;
  /** ISO day the reminders are about. */
  eventDate: string | null;
  reminders: Reminder[];
}

export interface PaperGroup {
  key: string;
  documentId: string;
  /** Paper title; '' for the own-dates group (the screen shows `reminders.own_group`). */
  title: string;
  memberId: string | null;
  items: DateItem[];
}

const byFire = (a: Reminder, b: Reminder) => (a.fireAt < b.fireAt ? -1 : a.fireAt > b.fireAt ? 1 : 0);

export function groupReminders(
  reminders: Reminder[],
  docs: Map<string, StoredDocument | null>,
  focusDocumentId?: string | null,
): PaperGroup[] {
  const groups = new Map<string, PaperGroup>();
  for (const r of [...reminders].sort(byFire)) {
    const own = isOwnReminder(r) || !r.documentId;
    const gKey = own ? OWN_GROUP_KEY : r.documentId;
    const doc = own ? null : (docs.get(r.documentId) ?? null);
    let group = groups.get(gKey);
    if (!group) {
      group = {
        key: gKey,
        documentId: own ? '' : r.documentId,
        title: own ? '' : (doc?.title ?? doc?.analysis?.summary?.title ?? r.label),
        memberId: doc?.memberId ?? null,
        items: [],
      };
      groups.set(gKey, group);
    }
    const iKey = `${gKey}|${r.demandId}`;
    let item = group.items.find((i) => i.key === iKey);
    if (!item) {
      const demand = findDemand(doc?.analysis, r.demandId);
      item = {
        key: iKey,
        documentId: group.documentId,
        demandId: r.demandId,
        text: demand?.text ?? r.label,
        verbatim: demand?.value_verbatim ?? null,
        localizedLine: demand?.date?.localized_line ?? null,
        eventDate: eventDateOf(r, doc),
        reminders: [],
      };
      group.items.push(item);
    }
    item.reminders.push(r);
  }
  const list = [...groups.values()];
  const first = (g: PaperGroup) => g.items[0]?.reminders[0]?.fireAt ?? '';
  list.sort((a, b) => {
    if (focusDocumentId) {
      if (a.documentId === focusDocumentId && b.documentId !== focusDocumentId) return -1;
      if (b.documentId === focusDocumentId && a.documentId !== focusDocumentId) return 1;
    }
    if (a.key === OWN_GROUP_KEY && b.key !== OWN_GROUP_KEY) return 1;
    if (b.key === OWN_GROUP_KEY && a.key !== OWN_GROUP_KEY) return -1;
    return first(a) < first(b) ? -1 : first(a) > first(b) ? 1 : 0;
  });
  return list;
}

export function allReminders(groups: PaperGroup[]): Reminder[] {
  return groups.flatMap((g) => g.items.flatMap((i) => i.reminders));
}

export function groupReminderList(group: PaperGroup): Reminder[] {
  return group.items.flatMap((i) => i.reminders);
}
