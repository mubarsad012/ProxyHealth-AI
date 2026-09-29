// Native local notifications for date reminders (PRODUCT_SPEC §10.2, ARCHITECTURE §3.1).
// Verified against https://docs.expo.dev/versions/v57.0.0/sdk/notifications/ and the installed
// expo-notifications 57.0.20 types: getPermissionsAsync / requestPermissionsAsync,
// setNotificationChannelAsync(id, { name, importance }), scheduleNotificationAsync({ content,
// trigger: { type: SchedulableTriggerInputTypes.DATE, date, channelId } }),
// cancelScheduledNotificationAsync, getAllScheduledNotificationsAsync, setNotificationHandler,
// addNotificationResponseReceivedListener, getLastNotificationResponseAsync. The module is loaded
// lazily (like storage/vault.native.ts) so importing this file at app start registers nothing.
// Notification text is always supplied by the caller: generic unless the user opted into detail.
// The .ics "Add to calendar" path uses expo-file-system (File in Paths.cache) + expo-sharing.

import { Linking } from 'react-native';

import type { IcsOfferResult, NotificationPermission, NotificationsApi, ScheduleRequest } from '@/lib/notifications';

type NotificationsModule = typeof import('expo-notifications');

export const REMINDER_CHANNEL_ID = 'dates' as const;

function load(): NotificationsModule | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('expo-notifications') as NotificationsModule;
  } catch {
    return null;
  }
}

let handlerSet = false;

/** Show reminders while the app is open too (banner + list, no sound, no badge). */
function ensureHandler(N: NotificationsModule): void {
  if (handlerSet) return;
  handlerSet = true;
  try {
    N.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowBanner: true,
        shouldShowList: true,
        shouldPlaySound: false,
        shouldSetBadge: false,
      }),
    });
  } catch {
    handlerSet = false;
  }
}

function toPermission(res: { granted?: boolean; status?: string } | null | undefined): NotificationPermission {
  if (!res) return 'unavailable';
  if (res.granted) return 'granted';
  if (res.status === 'denied') return 'denied';
  return 'undetermined';
}

function urlFrom(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null;
  const url = (data as Record<string, unknown>).url;
  return typeof url === 'string' && url.startsWith('/') ? url : null;
}

export const notifications: NotificationsApi = {
  supported: true,
  async getPermission() {
    const N = load();
    if (!N) return 'unavailable';
    try {
      return toPermission(await N.getPermissionsAsync());
    } catch {
      return 'unavailable';
    }
  },
  async requestPermission() {
    const N = load();
    if (!N) return 'unavailable';
    try {
      return toPermission(await N.requestPermissionsAsync());
    } catch {
      return 'unavailable';
    }
  },
  async ensureChannel(name) {
    const N = load();
    if (!N) return;
    try {
      await N.setNotificationChannelAsync(REMINDER_CHANNEL_ID, {
        name,
        importance: N.AndroidImportance.DEFAULT,
      });
    } catch {
      // iOS has no channels; Android may refuse while the app is backgrounded.
    }
  },
  async schedule(req: ScheduleRequest) {
    const N = load();
    if (!N) return null;
    ensureHandler(N);
    try {
      return await N.scheduleNotificationAsync({
        content: { title: req.title, body: req.body, data: { url: req.url } },
        trigger: { type: N.SchedulableTriggerInputTypes.DATE, date: req.fireAt, channelId: REMINDER_CHANNEL_ID },
      });
    } catch {
      return null;
    }
  },
  async cancel(id) {
    try {
      await load()?.cancelScheduledNotificationAsync(id);
    } catch {
      // already fired or never scheduled
    }
  },
  async scheduledIds() {
    const N = load();
    if (!N) return [];
    try {
      const all = await N.getAllScheduledNotificationsAsync();
      return all.map((n) => n.identifier);
    } catch {
      return [];
    }
  },
  addTapListener(onUrl) {
    const N = load();
    if (!N) return () => undefined;
    ensureHandler(N);
    let active = true;
    void N.getLastNotificationResponseAsync()
      .then((last) => {
        const url = urlFrom(last?.notification.request.content.data);
        if (active && url) {
          onUrl(url);
          void N.clearLastNotificationResponseAsync().catch(() => undefined);
        }
      })
      .catch(() => undefined);
    let sub: { remove(): void } | null = null;
    try {
      sub = N.addNotificationResponseReceivedListener((response) => {
        const url = urlFrom(response.notification.request.content.data);
        if (url) onUrl(url);
      });
    } catch {
      sub = null;
    }
    return () => {
      active = false;
      sub?.remove();
    };
  },
  async openSettings() {
    try {
      await Linking.openSettings();
    } catch {
      // nothing else we can do; the in-app list still works
    }
  },
};

/** Native "Add to calendar": write the .ics to the cache directory and open the share sheet. */
export async function offerIcs(fileName: string, ics: string): Promise<IcsOfferResult> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const Sharing = require('expo-sharing') as typeof import('expo-sharing');
    if (!(await Sharing.isAvailableAsync())) return 'unavailable';
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { File, Paths } = require('expo-file-system') as typeof import('expo-file-system');
    const file = new File(Paths.cache, fileName);
    if (file.exists) file.delete();
    file.create({ overwrite: true });
    file.write(ics);
    await Sharing.shareAsync(file.uri, { mimeType: 'text/calendar', UTI: 'public.calendar-event' });
    return 'shared';
  } catch {
    return 'unavailable';
  }
}
