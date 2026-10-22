// Reminder service (PRODUCT_SPEC §10, ARCHITECTURE §3.1 "Reminders") with injected dependencies so
// the platform rules are unit-tested with fakes and a fixed clock:
//   native → explanation card first, then the system prompt; granted → one local notification per
//            fire time (9:00 local, 7/3/1 days before) with the generic body unless the user opted
//            into lock-screen detail; denied → the in-app list still gets the rows ('denied');
//   web    → no scheduling: the .ics file (one VEVENT per reminder) is offered FIRST, synchronously
//            inside the click handler, then the rows are stored for the in-app list ('ics').
// Every reminder row stores only the demand label, the fire time and ids (D-22).
// Sample papers (PRODUCT_SPEC §12.3): eligibility and fire times run as of the samples' fixed day
// (`features/demo/asOf.ts`, the server's DEMO_AS_OF), the result gets the sample note
// (`demo.as_of_note`) through `notify`, and only fire times still ahead of the real clock become
// OS notifications. "Remind me" never fails silently: a real paper whose date has passed resolves
// 'past' and shows `reminders.date_passed`.

import type { AnalysisResult, Demand } from '@/api/types';
import { DEMO_AS_OF_NOTE, isSampleAnalysis, sampleNow } from '@/features/demo/asOf';
import { buildIcs, type IcsEvent, icsFileName } from '@/lib/ics';
import type { IcsOfferResult, NotificationPermission, NotificationsApi } from '@/lib/notifications';
import type { Reminder, StoredDocument, Vault } from '@/storage/index';

import {
  computeFireTimes,
  type FireSlot,
  notificationText,
  parseLocalDay,
  reminderEligibility,
  reminderUrl,
  toIsoDay,
  type Translate,
} from './schedule';

/** 'past' (a widening): the date is before today (a sample: before its as-of day); the service
 *  has already shown `reminders.date_passed` through `notify`. */
export type ScheduleOutcome = 'scheduled' | 'ics' | 'denied' | 'not_eligible' | 'past';

export const OWN_PREFIX = 'own:';
export const OWN_TITLE_MAX = 60;
export const OWN_NOTE_MAX = 100;
const LABEL_MAX = 140;

export interface RemindersDeps {
  reminders: Vault['reminders'];
  getDocument(id: string): Promise<StoredDocument | null>;
  notifications: NotificationsApi;
  offerIcs(fileName: string, ics: string): Promise<IcsOfferResult>;
  isWeb: boolean;
  t: Translate;
  now(): Date;
  /** Settings → "Show details on the lock screen" (default off). */
  lockScreenDetail(): boolean;
  /** Shows `reminders.permission_explain`; resolves true when the user wants the system prompt. */
  explainPermission(): Promise<boolean>;
  /** Called after any change so lists re-read the vault. */
  onChange?(): void;
  /** Shows one short, already-translated line the calling screen does not show itself (the date
   *  has passed; the sample note). */
  notify?(message: string): void;
}

export interface OwnDateInput {
  title: string;
  dateIso: string;
  note?: string;
}

/** Own dates have no document: `documentId` is '' and `demandId` is `own:<YYYY-MM-DD>:<rand>`. */
export function isOwnReminder(r: Pick<Reminder, 'demandId'>): boolean {
  return r.demandId.startsWith(OWN_PREFIX);
}

export function ownDateOf(r: Pick<Reminder, 'demandId'>): string | null {
  if (!isOwnReminder(r)) return null;
  const iso = r.demandId.slice(OWN_PREFIX.length, OWN_PREFIX.length + 10);
  return parseLocalDay(iso) ? iso : null;
}

/** Finds the demand a reminder belongs to in a stored analysis (demands, then unverified). */
export function findDemand(analysis: AnalysisResult | null | undefined, demandId: string): Demand | null {
  if (!analysis) return null;
  return (
    analysis.demands?.find((d) => d.id === demandId) ?? analysis.unverified?.find((d) => d.id === demandId) ?? null
  );
}

/** The date the reminder is about (not its fire time): own date, or the demand's `value_iso`. */
export function eventDateOf(r: Reminder, doc: StoredDocument | null): string | null {
  const own = ownDateOf(r);
  if (own) return own;
  const iso = findDemand(doc?.analysis, r.demandId)?.date?.value_iso ?? null;
  return iso ? iso.slice(0, 10) : null;
}

function clip(text: string, max: number): string {
  const trimmed = text.trim();
  return trimmed.length > max ? `${trimmed.slice(0, max - 1)}…` : trimmed;
}

function randomToken(): string {
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

export function validateOwnDate(input: OwnDateInput, now: Date): 'ok' | 'title' | 'date' {
  const title = input.title.trim();
  if (title.length === 0 || title.length > OWN_TITLE_MAX) return 'title';
  if ((input.note ?? '').length > OWN_NOTE_MAX) return 'title';
  if (computeFireTimes(input.dateIso, now).length === 0) return 'date';
  return 'ok';
}

interface Plan {
  documentId: string;
  demandId: string;
  label: string;
  slots: FireSlot[];
  detail: { documentTitle: string | null; demandText: string | null; date: string | null };
}

export function createRemindersService(deps: RemindersDeps) {
  const { t } = deps;

  function events(plan: Plan, detailOptIn: boolean): IcsEvent[] {
    return plan.slots.map((slot) => {
      const generic = notificationText(t, slot, { optIn: false });
      const shown = notificationText(t, slot, { optIn: detailOptIn, ...plan.detail });
      return {
        uid: `${plan.documentId || 'own'}-${plan.demandId}-${slot.offsetDays}-${slot.fireAt.getTime()}`,
        start: slot.fireAt,
        summary: shown.body,
        alarmText: generic.body,
      };
    });
  }

  async function removeExisting(documentId: string, demandId: string): Promise<void> {
    const all = await deps.reminders.list();
    for (const r of all) {
      if (r.documentId === documentId && r.demandId === demandId) await deps.reminders.remove(r.id);
    }
  }

  async function permission(): Promise<NotificationPermission> {
    let perm = await deps.notifications.getPermission();
    if (perm === 'undetermined') {
      const go = await deps.explainPermission();
      perm = go ? await deps.notifications.requestPermission() : 'undetermined';
    }
    return perm;
  }

  async function store(plan: Plan): Promise<ScheduleOutcome> {
    const detailOptIn = deps.lockScreenDetail();
    if (deps.isWeb) {
      // First statement that has an effect: the download must stay inside the click gesture.
      void deps.offerIcs(icsFileName(), buildIcs(events(plan, detailOptIn), { now: deps.now() }));
      await removeExisting(plan.documentId, plan.demandId);
      for (const slot of plan.slots) {
        await deps.reminders.add({
          documentId: plan.documentId,
          demandId: plan.demandId,
          fireAt: slot.fireAt.toISOString(),
          notificationId: null,
          detailOptIn,
          enabled: true,
          label: plan.label,
        });
      }
      deps.onChange?.();
      return 'ics';
    }
    const perm = await permission();
    const granted = perm === 'granted';
    if (granted) await deps.notifications.ensureChannel(t('notif.channel_name'));
    await removeExisting(plan.documentId, plan.demandId);
    // A sample's fire times are counted from its as-of day, so they can be behind the real clock:
    // those stay in the list only (the OS would fire them at once or refuse them).
    const realNow = deps.now().getTime();
    for (const slot of plan.slots) {
      const text = notificationText(t, slot, { optIn: detailOptIn, ...plan.detail });
      const notificationId = granted && slot.fireAt.getTime() > realNow
        ? await deps.notifications.schedule({
            fireAt: slot.fireAt,
            title: text.title,
            body: text.body,
            url: reminderUrl(plan.documentId),
          })
        : null;
      await deps.reminders.add({
        documentId: plan.documentId,
        demandId: plan.demandId,
        fireAt: slot.fireAt.toISOString(),
        notificationId,
        detailOptIn,
        enabled: true,
        label: plan.label,
      });
    }
    deps.onChange?.();
    return granted ? 'scheduled' : 'denied';
  }

  function notify(key: string): void {
    try {
      deps.notify?.(t(key));
    } catch {
      // best-effort: the outcome still reaches the caller
    }
  }

  function scheduleForDemand(analysis: AnalysisResult, demand: Demand, documentId?: string): Promise<ScheduleOutcome> {
    // Everything up to `store` runs synchronously: on web the .ics download must stay in the tap.
    const sample = isSampleAnalysis(analysis);
    const now = sample ? sampleNow(deps.now()) : deps.now();
    const eligibility = reminderEligibility(demand, now);
    if (eligibility === 'past') {
      notify('reminders.date_passed');
      return Promise.resolve('past');
    }
    if (eligibility !== 'ok' || !demand.date?.value_iso) return Promise.resolve('not_eligible');
    const slots = computeFireTimes(demand.date.value_iso, now);
    if (slots.length === 0) return Promise.resolve('not_eligible');
    const plan: Plan = {
      documentId: documentId ?? analysis.analysis_id,
      demandId: demand.id,
      label: clip(demand.text, LABEL_MAX),
      slots,
      detail: {
        documentTitle: analysis.summary?.title ?? null,
        demandText: demand.text,
        date: demand.value_verbatim || demand.date.value_iso,
      },
    };
    const stored = store(plan);
    if (!sample) return stored;
    return stored.then((outcome) => {
      notify(DEMO_AS_OF_NOTE);
      return outcome;
    });
  }

  function addOwnDate(input: OwnDateInput): Promise<ScheduleOutcome> {
    const now = deps.now();
    if (validateOwnDate(input, now) !== 'ok') return Promise.resolve('not_eligible');
    const day = input.dateIso.slice(0, 10);
    const note = (input.note ?? '').trim();
    const title = input.title.trim();
    const plan: Plan = {
      documentId: '',
      demandId: `${OWN_PREFIX}${day}:${randomToken()}`,
      label: note ? `${title} — ${note}` : title,
      slots: computeFireTimes(day, now),
      detail: { documentTitle: title, demandText: note || title, date: day },
    };
    return store(plan);
  }

  return { scheduleForDemand, addOwnDate, removeExisting, permission, events };
}

export type RemindersService = ReturnType<typeof createRemindersService>;

export { toIsoDay };
