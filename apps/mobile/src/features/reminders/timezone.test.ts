// Phase 2C — reminders follow a device time-zone change (PRODUCT_SPEC §10.2 "Time zone"): checked
// at app start (native), every future 7/3/1-day reminder moves to 09:00 in the new zone and its
// notification is re-scheduled; web is untouched. Times are built relative to the jest process
// zone, so the test passes in any TZ.

import type { NotificationsApi, ScheduleRequest } from '@/lib/notifications';
import type { Reminder, StoredDocument } from '@/storage/index';

import type { RemindersDeps } from './service';
import {
  retimedFireAt,
  retimeForZoneChange,
  slotOfFireTime,
  zoneChanged,
  type ZoneStamp,
  type ZoneStore,
} from './timezone';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

// Fixed clock: 1 October 2026, 10:00 device-local time. The paper's date: 14 October 2026.
const NOW = new Date(2026, 9, 1, 10, 0, 0, 0);
const EVENT = '2026-10-14';
const offsetAt = (d: Date) => -d.getTimezoneOffset();
const HOUR = 3_600_000;

/** The instant that showed 09:00 on `day` in a zone `shiftHours` east of the current one. */
function nineAmInOtherZone(y: number, m: number, d: number, shiftHours: number): Date {
  return new Date(new Date(y, m - 1, d, 9, 0, 0, 0).getTime() - shiftHours * HOUR);
}
const localNine = (y: number, m: number, d: number) => new Date(y, m - 1, d, 9, 0, 0, 0);

const t = (key: string) => key;

class FakeNotifications implements NotificationsApi {
  readonly supported = true;
  permission: 'granted' | 'denied' = 'granted';
  scheduled: (ScheduleRequest & { id: string })[] = [];
  cancelled: string[] = [];
  private next = 100;
  getPermission = async () => this.permission;
  requestPermission = async () => this.permission;
  ensureChannel = async () => undefined;
  schedule = async (req: ScheduleRequest) => {
    const id = `n${++this.next}`;
    this.scheduled.push({ ...req, id });
    return id;
  };
  cancel = async (id: string) => {
    this.cancelled.push(id);
  };
  scheduledIds = async () => this.scheduled.map((s) => s.id);
  addTapListener = () => () => undefined;
  openSettings = async () => undefined;
}

function setup(rows: Reminder[], over: Partial<RemindersDeps> = {}) {
  const notifications = new FakeNotifications();
  let n = 0;
  const onChange = jest.fn();
  const doc = {
    id: 'an_1',
    title: 'Medicaid letter',
    analysis: { summary: { title: 'Medicaid letter' }, demands: [{ id: 'd1', text: 'Confirm your address', value_verbatim: 'October 14, 2026', date: { value_iso: EVENT } }], unverified: [] },
  } as unknown as StoredDocument;
  const deps: RemindersDeps = {
    reminders: {
      list: async () => [...rows],
      add: async (r) => {
        const row = { ...r, id: `new${++n}` };
        rows.push(row);
        return row;
      },
      remove: async (id) => {
        const i = rows.findIndex((r) => r.id === id);
        if (i >= 0) rows.splice(i, 1);
      },
      setEnabled: async () => undefined,
    },
    getDocument: async (id) => (id === 'an_1' ? doc : null),
    notifications,
    offerIcs: async () => 'downloaded',
    isWeb: false,
    t,
    now: () => NOW,
    lockScreenDetail: () => false,
    explainPermission: async () => true,
    onChange,
    ...over,
  };
  let stamp: ZoneStamp | null = null;
  const store: ZoneStore = {
    get: async () => stamp,
    set: async (s) => {
      stamp = s;
    },
  };
  return { deps, rows, notifications, store, setStamp: (s: ZoneStamp | null) => (stamp = s), getStamp: () => stamp, onChange };
}

function row(id: string, fireAt: Date, over: Partial<Reminder> = {}): Reminder {
  return { id, documentId: 'an_1', demandId: 'd1', fireAt: fireAt.toISOString(), notificationId: `old-${id}`, detailOptIn: false, enabled: true, label: 'Confirm your address', ...over };
}

describe('zoneChanged', () => {
  it('compares zone names when both are known (DST alone is not a change)', () => {
    expect(zoneChanged({ zone: 'America/New_York', offsetMinutes: -240 }, { zone: 'America/New_York', offsetMinutes: -300 })).toBe(false);
    expect(zoneChanged({ zone: 'America/New_York', offsetMinutes: -240 }, { zone: 'Asia/Kabul', offsetMinutes: 270 })).toBe(true);
  });
  it('falls back to the UTC offset when a name is missing', () => {
    expect(zoneChanged({ zone: null, offsetMinutes: -240 }, { zone: 'America/New_York', offsetMinutes: -240 })).toBe(false);
    expect(zoneChanged({ zone: null, offsetMinutes: -240 }, { zone: null, offsetMinutes: 60 })).toBe(true);
  });
});

describe('re-timing math', () => {
  it('reads the slot on the old wall clock and moves it to 09:00 in the new zone', () => {
    for (const shift of [-10, -5, 3, 9, 13]) {
      const old = nineAmInOtherZone(2026, 10, 11, shift); // the 3-day reminder, scheduled elsewhere
      const prevOffset = offsetAt(localNine(2026, 10, 11)) + shift * 60;
      expect(slotOfFireTime(old.toISOString(), EVENT, prevOffset)).toBe(3);
      expect(retimedFireAt({ fireAt: old.toISOString() }, EVENT, prevOffset, NOW)?.getTime()).toBe(localNine(2026, 10, 11).getTime());
    }
  });

  it('leaves a reminder alone when nothing moves, it is past, or it is the 1-minute "soon" one', () => {
    const nine = localNine(2026, 10, 7);
    expect(retimedFireAt({ fireAt: nine.toISOString() }, EVENT, offsetAt(nine), NOW)).toBeNull();
    const past = new Date(NOW.getTime() - HOUR);
    expect(retimedFireAt({ fireAt: past.toISOString() }, '2026-10-02', offsetAt(past) + 300, NOW)).toBeNull();
    const soon = new Date(NOW.getTime() + 60_000);
    expect(retimedFireAt({ fireAt: soon.toISOString() }, '2026-10-01', offsetAt(soon) + 300, NOW)).toBeNull();
    expect(retimedFireAt({ fireAt: nine.toISOString() }, null, 0, NOW)).toBeNull();
  });

  it('never loses a reminder: if 09:00 already passed in the new zone, the old future time stays', () => {
    // The 1-day reminder for 2 October, scheduled 9 hours to the west: it fires at 18:00 today
    // here, but 09:00 today (the moved time) is already past at 10:00.
    const old = nineAmInOtherZone(2026, 10, 1, -9);
    const prevOffset = offsetAt(localNine(2026, 10, 1)) - 9 * 60;
    expect(old.getTime()).toBeGreaterThan(NOW.getTime());
    expect(retimedFireAt({ fireAt: old.toISOString() }, '2026-10-02', prevOffset, NOW)).toBeNull();
  });
});

describe('retimeForZoneChange', () => {
  const kabul: ZoneStamp = { zone: 'Asia/Kabul', offsetMinutes: offsetAt(NOW) + 300 };
  const here: ZoneStamp = { zone: 'Test/Here', offsetMinutes: offsetAt(NOW) };

  it('first run only stamps the zone', async () => {
    const s = setup([row('a', nineAmInOtherZone(2026, 10, 7, 5))]);
    expect(await retimeForZoneChange(s.deps, s.store, here)).toBe(0);
    expect(s.getStamp()).toEqual(here);
    expect(s.notifications.cancelled).toEqual([]);
  });

  it('after a zone change: cancels, re-schedules at 09:00 local, keeps toggles, stamps the new zone', async () => {
    const own = row('own', nineAmInOtherZone(2026, 10, 17, 5), { documentId: '', demandId: 'own:2026-10-20:abc', label: 'Lease' });
    const off = row('off', nineAmInOtherZone(2026, 10, 13, 5), { enabled: false, notificationId: null });
    const s = setup([row('a', nineAmInOtherZone(2026, 10, 7, 5)), row('b', nineAmInOtherZone(2026, 10, 11, 5)), own, off]);
    s.setStamp(kabul);
    expect(await retimeForZoneChange(s.deps, s.store, here)).toBe(4);
    const byDay = (d: Date) => s.rows.find((r) => r.fireAt === d.toISOString());
    expect(byDay(localNine(2026, 10, 7))).toMatchObject({ enabled: true, documentId: 'an_1', demandId: 'd1' });
    expect(byDay(localNine(2026, 10, 11))).toMatchObject({ enabled: true });
    expect(byDay(localNine(2026, 10, 17))).toMatchObject({ demandId: 'own:2026-10-20:abc', label: 'Lease' });
    expect(byDay(localNine(2026, 10, 13))).toMatchObject({ enabled: false, notificationId: null });
    expect(s.rows).toHaveLength(4);
    expect(s.notifications.cancelled.sort()).toEqual(['old-a', 'old-b', 'old-own']);
    expect(s.notifications.scheduled.map((x) => x.fireAt.getTime()).sort()).toEqual(
      [localNine(2026, 10, 7), localNine(2026, 10, 11), localNine(2026, 10, 17)].map((d) => d.getTime()).sort(),
    );
    // Generic body unless opted in; the tap opens the reminders list for the paper.
    expect(s.notifications.scheduled.every((x) => x.body === 'notif.generic_body')).toBe(true);
    expect(s.getStamp()).toEqual(here);
    expect(s.onChange).toHaveBeenCalled();
    // Idempotent: a second run moves nothing.
    expect(await retimeForZoneChange(s.deps, s.store, here)).toBe(0);
  });

  it('permission denied: rows still move (the in-app list stays right), nothing is scheduled', async () => {
    const s = setup([row('a', nineAmInOtherZone(2026, 10, 7, 5))]);
    s.notifications.permission = 'denied';
    s.setStamp(kabul);
    expect(await retimeForZoneChange(s.deps, s.store, here)).toBe(1);
    expect(s.rows[0]).toMatchObject({ fireAt: localNine(2026, 10, 7).toISOString(), notificationId: null });
    expect(s.notifications.scheduled).toEqual([]);
  });

  it('web is unaffected (nothing scheduled there; .ics files keep their own times)', async () => {
    const original = nineAmInOtherZone(2026, 10, 7, 5).toISOString();
    const s = setup([row('a', new Date(original))], { isWeb: true });
    s.setStamp(kabul);
    expect(await retimeForZoneChange(s.deps, s.store, here)).toBe(0);
    expect(s.rows[0].fireAt).toBe(original);
    expect(s.getStamp()).toEqual(kabul);
  });
});
