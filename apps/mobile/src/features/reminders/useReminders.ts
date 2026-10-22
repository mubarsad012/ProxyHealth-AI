// `useReminders()` seam (BUILD_PLAN §4.2) wired to the real vault, notifications and settings.
// The permission explanation card (`reminders.permission_explain`) is a native Alert — it only
// ever shows on iOS/Android, because web never asks for notification permission.

import { useMemo } from 'react';
import { Alert } from 'react-native';

import type { AnalysisResult, Demand } from '@/api/types';
import { bumpVault } from '@/features/vault/store';
import { t as translate } from '@/i18n/store';
import type { IcsEvent } from '@/lib/ics';
import { type IcsOfferResult, notifications, offerIcs } from '@/lib/notifications';
import { isWeb } from '@/lib/platform';
import type { Reminder, Vault } from '@/storage/index';
import { kv } from '@/storage/kv';
import { useVault } from '@/storage/StorageProvider';
import { useSettings } from '@/store/settings';

import { icsEvents, offerEvents, rescheduleMissing, setReminderEnabled } from './manage';
import { showNotice } from './notice';
import { createRemindersService, type OwnDateInput, type RemindersDeps, type ScheduleOutcome } from './service';
import { deviceZone, isZoneStamp, retimeForZoneChange, ZONE_KEY, type ZoneStore } from './timezone';

export type { ScheduleOutcome } from './service';

export interface RemindersApi {
  /** 7/3/1-day 9 am reminders on native; `.ics` on web; generic bodies unless opted in. */
  scheduleForDemand(analysis: AnalysisResult, demand: Demand, documentId?: string): Promise<ScheduleOutcome>;
  list(): Promise<Reminder[]>;
  remove(id: string): Promise<void>;
  /** S14 additions (widening; the three members above are the fixed seam). */
  addOwnDate(input: OwnDateInput): Promise<ScheduleOutcome>;
  setEnabled(reminder: Reminder, on: boolean): Promise<void>;
  /** Offer an .ics for these reminders (web download / native share sheet). */
  offerIcsFor(reminders: Reminder[]): Promise<IcsOfferResult>;
  /** Prepare calendar events ahead of time so the web download runs inside the click handler. */
  icsEventsFor(reminders: Reminder[]): Promise<IcsEvent[]>;
  offerPrepared(events: IcsEvent[]): Promise<IcsOfferResult>;
}

function explainPermission(): Promise<boolean> {
  return new Promise((resolve) => {
    try {
      Alert.alert(
        translate('btn.remind_me'),
        translate('reminders.permission_explain'),
        [
          { text: translate('btn.cancel'), style: 'cancel', onPress: () => resolve(false) },
          { text: translate('btn.continue'), onPress: () => resolve(true) },
        ],
        { cancelable: true, onDismiss: () => resolve(false) },
      );
    } catch {
      resolve(true);
    }
  });
}

export function remindersDeps(vault: Vault): RemindersDeps {
  return {
    reminders: vault.reminders,
    getDocument: (id) => (id ? vault.documents.get(id) : Promise.resolve(null)),
    notifications,
    offerIcs,
    isWeb,
    t: translate,
    now: () => new Date(),
    lockScreenDetail: () => useSettings.getState().lockScreenDetail,
    explainPermission,
    onChange: bumpVault,
    notify: (message) =>
      showNotice(message, { isWeb, title: translate('app.name'), close: translate('btn.close') }),
  };
}

export function remindersApi(deps: RemindersDeps): RemindersApi {
  const service = createRemindersService(deps);
  return {
    scheduleForDemand: service.scheduleForDemand,
    list: () => deps.reminders.list(),
    remove: async (id) => {
      await deps.reminders.remove(id);
      deps.onChange?.();
    },
    addOwnDate: service.addOwnDate,
    setEnabled: (r, on) => setReminderEnabled(deps, r, on),
    offerIcsFor: async (reminders) => offerEvents(deps, await icsEvents(deps, reminders)),
    icsEventsFor: (reminders) => icsEvents(deps, reminders),
    offerPrepared: (events) => offerEvents(deps, events),
  };
}

export function useReminders(): RemindersApi {
  const vault = useVault();
  return useMemo(() => remindersApi(remindersDeps(vault)), [vault]);
}

/** App start (native): put back notifications the OS lost. Safe to call more than once. */
export function rescheduleLostReminders(vault: Vault): Promise<number> {
  return rescheduleMissing(remindersDeps(vault)).catch(() => 0);
}

/** The zone reminders were last checked in (kv; only a zone name and a UTC offset). */
export const zoneStore: ZoneStore = {
  get: async () => {
    const value = await kv.getJSON<unknown>(ZONE_KEY);
    return isZoneStamp(value) ? value : null;
  },
  set: (stamp) => kv.setJSON(ZONE_KEY, stamp),
};

/** Native: move reminders to 09:00 in the device's current zone if it changed (§10.2). */
export function retimeRemindersForZone(vault: Vault): Promise<number> {
  return retimeForZoneChange(remindersDeps(vault), zoneStore, deviceZone()).catch(() => 0);
}

/** App start (native): first follow a time-zone change, then put back what the OS lost. */
export async function syncRemindersAtStart(vault: Vault): Promise<{ retimed: number; rescheduled: number }> {
  const retimed = await retimeRemindersForZone(vault);
  const rescheduled = await rescheduleLostReminders(vault);
  return { retimed, rescheduled };
}
