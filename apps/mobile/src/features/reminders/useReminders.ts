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
import { useVault } from '@/storage/StorageProvider';
import { useSettings } from '@/store/settings';

import { icsEvents, offerEvents, rescheduleMissing, setReminderEnabled } from './manage';
import { createRemindersService, type OwnDateInput, type RemindersDeps, type ScheduleOutcome } from './service';

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
