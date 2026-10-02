// Notification tap → `/reminders?doc=<analysis_id>` (PRODUCT_SPEC §10.2 "Tap"), plus the once-per-
// session start sync: follow a device time-zone change (`timezone.ts`, §10.2 "Time zone"), then
// re-schedule reminders the OS lost. The zone is checked again whenever the app comes back to the
// front (a trip usually happens while the app sleeps). Native only; a no-op on web. Mounted by Home
// (the first tab), and safe to mount again elsewhere (e.g. the root layout) because every step is
// idempotent and the runs are serialised.

import { type Href, router } from 'expo-router';
import { useEffect } from 'react';
import { AppState } from 'react-native';

import { notifications } from '@/lib/notifications';
import { isWeb } from '@/lib/platform';
import type { Vault } from '@/storage/index';
import { useVault } from '@/storage/StorageProvider';

import { retimeRemindersForZone, syncRemindersAtStart } from './useReminders';

let rescheduledThisSession = false;
let queue: Promise<unknown> = Promise.resolve();

/** Run reminder maintenance one at a time (two overlapping runs could re-arm a row twice). */
function serial<T>(job: () => Promise<T>): Promise<T> {
  const next = queue.then(job, job);
  queue = next.catch(() => undefined);
  return next;
}

export function startReminderSync(vault: Vault): Promise<unknown> {
  return serial(() => syncRemindersAtStart(vault));
}

export function useReminderTapRouting(): void {
  const vault = useVault();
  useEffect(() => {
    if (isWeb) return undefined;
    if (!rescheduledThisSession) {
      rescheduledThisSession = true;
      void startReminderSync(vault);
    }
    const appState = AppState.addEventListener('change', (state) => {
      if (state === 'active') void serial(() => retimeRemindersForZone(vault));
    });
    const removeTap = notifications.addTapListener((url) => {
      try {
        router.push(url as Href);
      } catch {
        // navigation not ready yet; the list is one tap away on the My papers tab
      }
    });
    return () => {
      appState.remove();
      removeTap();
    };
  }, [vault]);
}
