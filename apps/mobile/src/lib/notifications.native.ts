// Native local notifications for date reminders (PRODUCT_SPEC §10.2, ARCHITECTURE §3.1).
// Verified against https://docs.expo.dev/versions/v57.0.0/sdk/notifications/ and the installed
// expo-notifications 57.0.20 types: getPermissionsAsync / requestPermissionsAsync,
// setNotificationChannelAsync(id, { name, importance }), scheduleNotificationAsync({ content,
// trigger: { type: SchedulableTriggerInputTypes.DATE, date, channelId } }),
// cancelScheduledNotificationAsync, getAllScheduledNotificationsAsync, setNotificationHandler,
// addNotificationResponseReceivedListener, getLastNotificationResponseAsync. The module is loaded
// lazily (like storage/vault.native.ts) so importing this file at app start registers nothing.
// Notification text is always supplied by the caller: generic unless the user opted into detail.
// The .ics "Add to calendar" path uses expo-file-system (File in Paths.cache/ics-share) +
// expo-sharing; the file is deleted once the share sheet closes and on "Delete everything".

import { Linking, Platform } from 'react-native';

import type { IcsOfferResult, NotificationPermission, NotificationsApi, ScheduleRequest } from '@/lib/notifications';
import { registerWipeHook } from '@/storage/wipe';

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
    try {
      // Cold start: the tap that launched the app.
      void N.getLastNotificationResponseAsync()
        .then((last) => {
          const url = urlFrom(last?.notification.request.content.data);
          if (active && url) {
            onUrl(url);
            void Promise.resolve(N.clearLastNotificationResponseAsync()).catch(() => undefined);
          }
        })
        .catch(() => undefined);
    } catch {
      // module present but not functional (Expo Go / tests); live taps below still work
    }
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
      if (typeof sub?.remove === 'function') sub.remove();
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

type FileSystemModule = typeof import('expo-file-system');

function loadFileSystem(): FileSystemModule | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('expo-file-system') as FileSystemModule;
  } catch {
    return null;
  }
}

/** The shared .ics lives in its own cache folder so it can be removed as a whole. */
const ICS_DIR = 'ics-share';
/** iOS resolves `shareAsync` when the sheet closes (the target already copied the file). Android
 *  resolves as soon as the chooser closes, while the chosen app may still be reading the file, so
 *  the delete waits a minute there. */
const DELETE_AFTER_SHARE_MS = Platform.OS === 'android' ? 60_000 : 0;
/** Bumped per share so a delayed delete never removes a newer share's file. */
let shareGeneration = 0;

/** Remove every .ics this app wrote for the share sheet (it can hold paper titles when detail is on). */
export function deleteSharedIcs(): void {
  const fs = loadFileSystem();
  if (!fs) return;
  try {
    const dir = new fs.Directory(fs.Paths.cache, ICS_DIR);
    if (dir.exists) dir.delete();
  } catch {
    // nothing left to remove, or the OS already cleared the cache
  }
}

// "Delete everything" (PRODUCT_SPEC §9.3) also removes a leftover shared .ics — e.g. one from a
// session that ended while the share sheet was open.
registerWipeHook(deleteSharedIcs);

/** Native "Add to calendar": write the .ics to the cache, open the share sheet, then delete it. */
export async function offerIcs(fileName: string, ics: string): Promise<IcsOfferResult> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const Sharing = require('expo-sharing') as typeof import('expo-sharing');
    if (!(await Sharing.isAvailableAsync())) return 'unavailable';
    const fs = loadFileSystem();
    if (!fs) return 'unavailable';
    deleteSharedIcs();
    const generation = ++shareGeneration;
    const cleanUp = () => {
      if (generation === shareGeneration) deleteSharedIcs();
    };
    const dir = new fs.Directory(fs.Paths.cache, ICS_DIR);
    dir.create({ intermediates: true, idempotent: true });
    const file = new fs.File(dir, fileName);
    file.create({ overwrite: true });
    file.write(ics);
    try {
      await Sharing.shareAsync(file.uri, { mimeType: 'text/calendar', UTI: 'public.calendar-event' });
    } finally {
      if (DELETE_AFTER_SHARE_MS > 0) setTimeout(cleanUp, DELETE_AFTER_SHARE_MS);
      else cleanUp();
    }
    return 'shared';
  } catch {
    return 'unavailable';
  }
}
