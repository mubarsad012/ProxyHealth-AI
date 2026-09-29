// Notification tap → `/reminders?doc=<analysis_id>` (PRODUCT_SPEC §10.2 "Tap"), plus the once-per-
// session reschedule of reminders the OS lost. Native only; a no-op on web. Mounted by Home (the
// first tab), and safe to mount again elsewhere (e.g. the root layout) because both steps are
// idempotent.

import { type Href, router } from 'expo-router';
import { useEffect } from 'react';

import { notifications } from '@/lib/notifications';
import { isWeb } from '@/lib/platform';
import { useVault } from '@/storage/StorageProvider';

import { rescheduleLostReminders } from './useReminders';

let rescheduledThisSession = false;

export function useReminderTapRouting(): void {
  const vault = useVault();
  useEffect(() => {
    if (isWeb) return undefined;
    if (!rescheduledThisSession) {
      rescheduledThisSession = true;
      void rescheduleLostReminders(vault);
    }
    return notifications.addTapListener((url) => {
      try {
        router.push(url as Href);
      } catch {
        // navigation not ready yet; the list is one tap away on the My papers tab
      }
    });
  }, [vault]);
}
