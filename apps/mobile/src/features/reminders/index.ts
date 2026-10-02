// Reminders feature (WP6 lane 6A; BUILD_PLAN §4.2 seam, PRODUCT_SPEC §10 / S14).
// Fixed seam: `useReminders(): { scheduleForDemand, list, remove }` and `ScheduleOutcome`.
// Additions (widenings only): S14 screen, own dates, toggles, .ics helpers, pure schedule math,
// notification-tap routing and the app-start reschedule.

export { RemindersScreen } from './RemindersScreen';
export { useReminderTapRouting } from './useReminderTapRouting';
export {
  rescheduleLostReminders,
  remindersApi,
  remindersDeps,
  retimeRemindersForZone,
  syncRemindersAtStart,
  useReminders,
  zoneStore,
  type RemindersApi,
  type ScheduleOutcome,
} from './useReminders';
export { startReminderSync } from './useReminderTapRouting';
export {
  deviceZone,
  retimedFireAt,
  retimeForZoneChange,
  slotOfFireTime,
  zoneChanged,
  ZONE_KEY,
  type ZoneStamp,
  type ZoneStore,
} from './timezone';
export {
  computeFireTimes,
  daysUntil,
  nextStatedDate,
  notificationText,
  parseLocalDay,
  REMINDER_HOUR,
  REMINDER_OFFSETS_DAYS,
  reminderEligibility,
  reminderUrl,
  toIsoDay,
  type Eligibility,
  type FireSlot,
} from './schedule';
export {
  createRemindersService,
  eventDateOf,
  findDemand,
  isOwnReminder,
  ownDateOf,
  validateOwnDate,
  OWN_NOTE_MAX,
  OWN_TITLE_MAX,
  type OwnDateInput,
  type RemindersDeps,
} from './service';
export { icsEvents, moveReminder, rescheduleMissing, setReminderEnabled } from './manage';
