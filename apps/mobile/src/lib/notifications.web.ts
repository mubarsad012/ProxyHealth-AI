// Web: browsers get no scheduled notifications (expo-notifications has no web implementation —
// docs.expo.dev/versions/v57.0.0/sdk/notifications/). Reminders are offered as an .ics file
// instead (PRODUCT_SPEC §10.2 "Web"): `offerIcs` builds a Blob and clicks an `<a download>`, so
// call it synchronously inside the button's click handler (no await before it).

import type { IcsOfferResult, NotificationsApi } from '@/lib/notifications';

export const REMINDER_CHANNEL_ID = 'dates' as const;

export const notifications: NotificationsApi = {
  supported: false,
  getPermission: () => Promise.resolve('unavailable'),
  requestPermission: () => Promise.resolve('unavailable'),
  ensureChannel: () => Promise.resolve(),
  schedule: () => Promise.resolve(null),
  cancel: () => Promise.resolve(),
  scheduledIds: () => Promise.resolve([]),
  addTapListener: () => () => undefined,
  openSettings: () => Promise.resolve(),
};

export function offerIcs(fileName: string, ics: string): Promise<IcsOfferResult> {
  try {
    if (typeof document === 'undefined' || typeof Blob === 'undefined' || typeof URL === 'undefined') {
      return Promise.resolve('unavailable');
    }
    const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' });
    const href = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = href;
    a.download = fileName;
    a.rel = 'noopener';
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    // Give the browser a moment to start the download before the object URL goes away.
    setTimeout(() => URL.revokeObjectURL(href), 10_000);
    return Promise.resolve('downloaded');
  } catch {
    return Promise.resolve('unavailable');
  }
}
