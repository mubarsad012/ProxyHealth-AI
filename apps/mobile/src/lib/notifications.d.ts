// Type declaration for the platform-resolved notifications module (same pattern as
// `storage/vault.d.ts`): Metro picks `notifications.native.ts` (expo-notifications, share sheet for
// .ics) on iOS/Android and `notifications.web.ts` (no scheduling, `<a download>` for .ics) on web;
// TypeScript resolves `@/lib/notifications` to this file. Both implementations export exactly
// these names. expo-notifications has no web implementation (docs.expo.dev/versions/v57.0.0/sdk/notifications/).

export type NotificationPermission = 'granted' | 'denied' | 'undetermined' | 'unavailable';

export interface ScheduleRequest {
  fireAt: Date;
  /** Already-translated title (the app name). */
  title: string;
  /** Already-translated body: generic unless the user opted into lock-screen detail. */
  body: string;
  /** In-app route opened when the notification is tapped, e.g. `/reminders?doc=<id>`. */
  url: string;
}

export interface NotificationsApi {
  /** True where local notifications can be scheduled (native only). */
  readonly supported: boolean;
  getPermission(): Promise<NotificationPermission>;
  /** Shows the system prompt (native). Callers show the explanation card first. */
  requestPermission(): Promise<NotificationPermission>;
  /** Android channel `dates` with the translated name "Dates to remember"; no-op elsewhere. */
  ensureChannel(name: string): Promise<void>;
  /** Returns the OS notification id, or null when scheduling is impossible. */
  schedule(req: ScheduleRequest): Promise<string | null>;
  cancel(id: string): Promise<void>;
  /** Ids of every notification the OS still has scheduled. */
  scheduledIds(): Promise<string[]>;
  /** Calls `onUrl` with the reminder route when a notification is tapped (incl. cold start). */
  addTapListener(onUrl: (url: string) => void): () => void;
  /** Opens the system settings page for this app (native). */
  openSettings(): Promise<void>;
}

export declare const REMINDER_CHANNEL_ID: 'dates';

export declare const notifications: NotificationsApi;

export type IcsOfferResult = 'downloaded' | 'shared' | 'unavailable';

/** Web: download the file through `<a download>` (call inside the click handler). Native: write
 *  it to the cache directory and open the share sheet ("Add to calendar"). */
export declare function offerIcs(fileName: string, ics: string): Promise<IcsOfferResult>;
