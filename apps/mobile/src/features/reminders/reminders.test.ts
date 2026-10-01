// WP6 lane 6A tests (BUILD_PLAN §5.7 step 3, Appendix B): reminder fire-time math with a FIXED
// `now`, generic notification bodies unless opted in, `.ics` with one VEVENT per reminder and a
// generic SUMMARY unless opted in; plus the service's native/web paths with fakes, S14 grouping,
// the Home next-date window and the opt-in save document builder.

import type { AnalysisResult, Demand } from '@/api/types';
import { pickNextDate } from '@/features/vault/nextDate';
import { buildStoredDocument, maskIdText } from '@/features/vault/documents';
import { buildIcs, countEvents, escapeText, foldLine, formatFloating } from '@/lib/ics';
import type { NotificationPermission, NotificationsApi, ScheduleRequest } from '@/lib/notifications';
import type { DocumentRow, Reminder, StoredDocument } from '@/storage/index';
import type { CapturedPage } from '@/store/session';

import { formatClock, formatDay, formatFireTime, gregorianLocale, toWesternDigits } from './format';
import { groupReminders, OWN_GROUP_KEY } from './groups';
import { rescheduleMissing, setReminderEnabled } from './manage';
import { computeFireTimes, nextStatedDate, notificationText, reminderEligibility, toIsoDay } from './schedule';
import { createRemindersService, eventDateOf, ownDateOf, type RemindersDeps, validateOwnDate } from './service';

// Fixed clock: Wednesday 30 September 2026, 10:00 device-local time.
const NOW = new Date(2026, 8, 30, 10, 0, 0, 0);

const EN: Record<string, string> = {
  'app.name': 'ProxyHealth AI',
  'notif.generic_body': 'You have a date coming up.',
  'notif.today_body': 'You have a date today.',
  'notif.detail_body': '{document_title}: {demand_text} on {date}',
  'notif.channel_name': 'Dates to remember',
  'vault.title_fallback': '{type} · {date}',
  'vault.category.benefits': 'Benefits',
  'vault.title_scam_check': 'Scam check',
};
const t = (key: string, vars?: Record<string, string | number>) =>
  (EN[key] ?? key).replace(/\{(\w+)\}/g, (_m, name: string) => String(vars?.[name] ?? `{${name}}`));

function demand(
  over: Partial<Demand> & { iso?: string | null; dateKind?: 'stated' | 'estimated' | 'unresolved' } = {},
): Demand {
  const { iso = '2026-10-14', dateKind: kind = 'stated', ...rest } = over;
  return {
    ambiguity_note: null,
    amount: null,
    confidence: 'high',
    date: {
      anchor_demand_id: null,
      anchor_quote: null,
      formula: null,
      kind,
      localized_line: null,
      rule_id: null,
      rule_source_url: null,
      rule_verification: null,
      time_text: null,
      value_iso: iso,
    },
    documents: [],
    id: 'd1',
    kind: 'deadline',
    page: 1,
    reminder_eligible: true,
    role: null,
    source_quote: 'by October 14, 2026',
    span_ids: ['p1s1'],
    text: 'Confirm your address',
    value_verbatim: 'October 14, 2026',
    verification_note: 'exact',
    verified: true,
    ...rest,
  } as Demand;
}

function analysis(demands: Demand[] = [demand()], over: Partial<AnalysisResult> = {}): AnalysisResult {
  return {
    analysis_id: 'an_1',
    category: 'benefits',
    document_type: 'medicaid_renewal',
    demands,
    unverified: [],
    summary: { title: 'Medicaid letter', body: '', body_en: '', span_ids: [] },
    quality: { legibility: 'good', pages_received: 1, pages_unreadable: [], readable: true, reason: null },
    model_meta: { demo: true },
    page_thumbnails: [{ page: 1, data_base64: 'AAAA', mime_type: 'image/jpeg', width: 10, height: 10 }],
    sender_as_written: 'State Medicaid Office',
    is_likely_scam: false,
    ...over,
  } as unknown as AnalysisResult;
}

class FakeNotifications implements NotificationsApi {
  readonly supported = true;
  permission: NotificationPermission = 'granted';
  afterRequest: NotificationPermission = 'granted';
  scheduled: (ScheduleRequest & { id: string })[] = [];
  cancelled: string[] = [];
  requested = 0;
  getPermission = async () => this.permission;
  requestPermission = async () => {
    this.requested += 1;
    this.permission = this.afterRequest;
    return this.permission;
  };
  ensureChannel = async () => undefined;
  private next = 0;
  schedule = async (req: ScheduleRequest) => {
    this.next += 1;
    const id = `n${this.next}`;
    this.scheduled.push({ ...req, id });
    return id;
  };
  cancel = async (id: string) => {
    this.cancelled.push(id);
    this.scheduled = this.scheduled.filter((s) => s.id !== id);
  };
  scheduledIds = async () => this.scheduled.map((s) => s.id);
  addTapListener = () => () => undefined;
  openSettings = async () => undefined;
}

function fakeDeps(over: Partial<RemindersDeps> = {}) {
  const rows: Reminder[] = [];
  const log: string[] = [];
  const offered: { name: string; ics: string }[] = [];
  const notifications = new FakeNotifications();
  let n = 0;
  const deps: RemindersDeps = {
    reminders: {
      list: async () => [...rows],
      add: async (r) => {
        log.push('add');
        const row = { ...r, id: `r${++n}` };
        rows.push(row);
        return row;
      },
      remove: async (id) => {
        const i = rows.findIndex((r) => r.id === id);
        if (i >= 0) rows.splice(i, 1);
      },
      setEnabled: async (id, on) => {
        const r = rows.find((x) => x.id === id);
        if (r) r.enabled = on;
      },
    },
    getDocument: async () => null,
    notifications,
    offerIcs: async (name, ics) => {
      log.push('offer');
      offered.push({ name, ics });
      return 'downloaded';
    },
    isWeb: false,
    t,
    now: () => NOW,
    lockScreenDetail: () => false,
    explainPermission: async () => true,
    ...over,
  };
  return { deps, rows, log, offered, notifications };
}

describe('fire-time math (fixed now = 2026-09-30 10:00 local)', () => {
  it('schedules 7, 3 and 1 days before at 09:00 local time', () => {
    const slots = computeFireTimes('2026-10-14', NOW);
    expect(slots.map((s) => s.offsetDays)).toEqual([7, 3, 1]);
    expect(slots.map((s) => toIsoDay(s.fireAt))).toEqual(['2026-10-07', '2026-10-11', '2026-10-13']);
    for (const s of slots) {
      expect(s.fireAt.getHours()).toBe(9);
      expect(s.fireAt.getMinutes()).toBe(0);
      expect(s.today).toBe(false);
    }
  });

  it('skips fire times that already passed', () => {
    expect(computeFireTimes('2026-10-05', NOW).map((s) => s.offsetDays)).toEqual([3, 1]);
    const early = new Date(2026, 8, 30, 8, 0);
    expect(computeFireTimes('2026-10-01', early).map((s) => [s.offsetDays, toIsoDay(s.fireAt)])).toEqual([[1, '2026-09-30']]);
  });

  it('fires once in 1 minute when every standard time passed; "today" only for today', () => {
    const tomorrow = computeFireTimes('2026-10-01', NOW);
    expect(tomorrow).toHaveLength(1);
    expect(tomorrow[0].offsetDays).toBe(0);
    expect(tomorrow[0].fireAt.getTime() - NOW.getTime()).toBe(60_000);
    expect(tomorrow[0].today).toBe(false);
    const today = computeFireTimes('2026-09-30', NOW);
    expect(today).toHaveLength(1);
    expect(today[0].today).toBe(true);
  });

  it('never schedules a date before today or an impossible date', () => {
    expect(computeFireTimes('2026-09-29', NOW)).toEqual([]);
    expect(computeFireTimes('2026-02-30', NOW)).toEqual([]);
    expect(computeFireTimes('soon', NOW)).toEqual([]);
  });

  it('eligibility follows §10.1', () => {
    expect(reminderEligibility(demand(), NOW)).toBe('ok');
    expect(reminderEligibility(demand({ dateKind: 'estimated' }), NOW)).toBe('estimate');
    expect(reminderEligibility(demand({ verified: false }), NOW)).toBe('unverified');
    expect(reminderEligibility(demand({ reminder_eligible: false }), NOW)).toBe('unverified');
    expect(reminderEligibility(demand({ iso: '2026-09-01' }), NOW)).toBe('past');
    expect(reminderEligibility(demand({ iso: null }), NOW)).toBe('no_date');
  });

  it('next stated date ignores estimates, unverified and past dates', () => {
    const a = analysis([
      demand({ id: 'a', iso: '2026-11-01' }),
      demand({ id: 'b', iso: '2026-10-20', dateKind: 'estimated' }),
      demand({ id: 'c', iso: '2026-10-10', verified: false }),
      demand({ id: 'd', iso: '2026-09-01' }),
    ]);
    expect(nextStatedDate(a, NOW)).toBe('2026-11-01');
  });
});

describe('notification text', () => {
  it('is generic unless the user opted into detail', () => {
    const detail = { documentTitle: 'Medicaid letter', demandText: 'Confirm your address', date: 'October 14, 2026' };
    expect(notificationText(t, { today: false }, { optIn: false, ...detail })).toEqual({
      title: 'ProxyHealth AI',
      body: 'You have a date coming up.',
    });
    expect(notificationText(t, { today: true }, { optIn: false, ...detail }).body).toBe('You have a date today.');
    expect(notificationText(t, { today: false }, { optIn: true, ...detail }).body).toBe(
      'Medicaid letter: Confirm your address on October 14, 2026',
    );
  });
});

describe('.ics builder', () => {
  const events = computeFireTimes('2026-10-14', NOW).map((s, i) => ({
    uid: `r${i}`,
    start: s.fireAt,
    summary: 'You have a date coming up.',
    alarmText: 'You have a date coming up.',
  }));

  it('writes one VEVENT per reminder with floating 09:00 DTSTART and CRLF lines', () => {
    const ics = buildIcs(events, { now: NOW });
    expect(countEvents(ics)).toBe(3);
    expect(ics.startsWith('BEGIN:VCALENDAR\r\nVERSION:2.0\r\n')).toBe(true);
    expect(ics.endsWith('END:VCALENDAR\r\n')).toBe(true);
    expect(ics).toContain('DTSTART:20261007T090000\r\n');
    expect(ics).toContain('DTSTART:20261013T090000\r\n');
    expect(ics).not.toMatch(/DTSTART:[0-9T]+Z/);
    expect(ics).not.toMatch(/TZID/);
    expect(ics.split('\r\n').filter((l) => l.startsWith('SUMMARY:'))).toEqual([
      'SUMMARY:You have a date coming up.',
      'SUMMARY:You have a date coming up.',
      'SUMMARY:You have a date coming up.',
    ]);
    expect(formatFloating(events[0].start)).toBe('20261007T090000');
  });

  it('escapes TEXT and folds long lines at 75 octets', () => {
    expect(escapeText('a,b;c\\d\ne')).toBe('a\\,b\\;c\\\\d\\ne');
    const long = `SUMMARY:${'وثيقة '.repeat(30)}`;
    const folded = foldLine(long).split('\r\n');
    expect(folded.length).toBeGreaterThan(1);
    for (const line of folded) expect(new TextEncoder().encode(line).length).toBeLessThanOrEqual(75);
    expect(folded.slice(1).every((l) => l.startsWith(' '))).toBe(true);
  });
});

describe('reminders service (native)', () => {
  it('asks after the explanation card, schedules 3 generic notifications and stores 3 rows', async () => {
    const { deps, rows, notifications } = fakeDeps();
    notifications.permission = 'undetermined';
    const explain = jest.fn(async () => true);
    const service = createRemindersService({ ...deps, explainPermission: explain });
    await expect(service.scheduleForDemand(analysis(), demand(), 'an_1')).resolves.toBe('scheduled');
    expect(explain).toHaveBeenCalledTimes(1);
    expect(notifications.requested).toBe(1);
    expect(notifications.scheduled).toHaveLength(3);
    for (const s of notifications.scheduled) {
      expect(s.body).toBe('You have a date coming up.');
      expect(s.title).toBe('ProxyHealth AI');
      expect(s.url).toBe('/reminders?doc=an_1');
      expect(s.body).not.toContain('Medicaid');
    }
    expect(rows.map((r) => r.notificationId)).toEqual(['n1', 'n2', 'n3']);
    expect(rows.every((r) => r.documentId === 'an_1' && r.demandId === 'd1' && !r.detailOptIn)).toBe(true);
    expect(rows.map((r) => r.fireAt)).toEqual(computeFireTimes('2026-10-14', NOW).map((s) => s.fireAt.toISOString()));
  });

  it('uses the detail body only when the user opted in', async () => {
    const { deps, notifications, rows } = fakeDeps({ lockScreenDetail: () => true });
    await createRemindersService(deps).scheduleForDemand(analysis(), demand());
    expect(notifications.scheduled[0].body).toBe('Medicaid letter: Confirm your address on October 14, 2026');
    expect(rows[0].detailOptIn).toBe(true);
  });

  it('denied → keeps the in-app list without scheduling', async () => {
    const { deps, rows, notifications } = fakeDeps();
    notifications.permission = 'denied';
    await expect(createRemindersService(deps).scheduleForDemand(analysis(), demand())).resolves.toBe('denied');
    expect(notifications.scheduled).toHaveLength(0);
    expect(rows).toHaveLength(3);
    expect(rows.every((r) => r.notificationId === null)).toBe(true);
  });

  it('declining the explanation never shows the system prompt', async () => {
    const { deps, notifications } = fakeDeps({ explainPermission: async () => false });
    notifications.permission = 'undetermined';
    await expect(createRemindersService(deps).scheduleForDemand(analysis(), demand())).resolves.toBe('denied');
    expect(notifications.requested).toBe(0);
  });

  it('refuses estimated, unverified and past dates and stores nothing', async () => {
    const { deps, rows } = fakeDeps();
    const service = createRemindersService(deps);
    await expect(service.scheduleForDemand(analysis(), demand({ dateKind: 'estimated' }))).resolves.toBe('not_eligible');
    await expect(service.scheduleForDemand(analysis(), demand({ verified: false }))).resolves.toBe('not_eligible');
    await expect(service.scheduleForDemand(analysis(), demand({ iso: '2026-09-01' }))).resolves.toBe('not_eligible');
    expect(rows).toHaveLength(0);
  });

  it('scheduling the same date again replaces its reminders', async () => {
    const { deps, rows } = fakeDeps();
    const service = createRemindersService(deps);
    await service.scheduleForDemand(analysis(), demand());
    await service.scheduleForDemand(analysis(), demand());
    expect(rows).toHaveLength(3);
  });
});

describe('reminders service (web)', () => {
  it('offers the .ics first (inside the tap), one VEVENT per reminder, generic SUMMARY', async () => {
    const { deps, rows, log, offered, notifications } = fakeDeps({ isWeb: true });
    await expect(createRemindersService(deps).scheduleForDemand(analysis(), demand())).resolves.toBe('ics');
    expect(log[0]).toBe('offer');
    expect(offered).toHaveLength(1);
    expect(offered[0].name).toMatch(/\.ics$/);
    expect(countEvents(offered[0].ics)).toBe(3);
    const summaries = offered[0].ics.split('\r\n').filter((l) => l.startsWith('SUMMARY:'));
    expect(summaries.every((l) => l === 'SUMMARY:You have a date coming up.')).toBe(true);
    expect(offered[0].ics).not.toContain('Medicaid');
    expect(offered[0].ics).not.toMatch(/^DESCRIPTION:(?!You have a date)/m);
    expect(notifications.scheduled).toHaveLength(0);
    expect(rows).toHaveLength(3);
  });

  it('puts the detail in SUMMARY only when opted in', async () => {
    const { deps, offered } = fakeDeps({ isWeb: true, lockScreenDetail: () => true });
    await createRemindersService(deps).scheduleForDemand(analysis(), demand());
    expect(offered[0].ics).toContain('SUMMARY:Medicaid letter: Confirm your address on October 14\\, 2026');
    // The alarm text stays generic even with detail on.
    expect(offered[0].ics.split('\r\n').filter((l) => l.startsWith('DESCRIPTION:'))).toEqual([
      'DESCRIPTION:You have a date coming up.',
      'DESCRIPTION:You have a date coming up.',
      'DESCRIPTION:You have a date coming up.',
    ]);
  });
});

describe('own dates, toggles and reschedule', () => {
  it('validates title, note and date', () => {
    expect(validateOwnDate({ title: 'Clinic', dateIso: '2026-10-20' }, NOW)).toBe('ok');
    expect(validateOwnDate({ title: ' ', dateIso: '2026-10-20' }, NOW)).toBe('title');
    expect(validateOwnDate({ title: 'x'.repeat(61), dateIso: '2026-10-20' }, NOW)).toBe('title');
    expect(validateOwnDate({ title: 'Clinic', dateIso: '2026-09-01' }, NOW)).toBe('date');
  });

  it('stores own dates without a document and recovers their date', async () => {
    const { deps, rows } = fakeDeps();
    await expect(createRemindersService(deps).addOwnDate({ title: 'Clinic', dateIso: '2026-10-20', note: 'Bring card' })).resolves.toBe(
      'scheduled',
    );
    expect(rows).toHaveLength(3);
    expect(rows[0].documentId).toBe('');
    expect(rows[0].label).toBe('Clinic — Bring card');
    expect(ownDateOf(rows[0])).toBe('2026-10-20');
    expect(eventDateOf(rows[0], null)).toBe('2026-10-20');
  });

  it('turning a reminder off cancels its notification; on re-arms it', async () => {
    const { deps, rows, notifications } = fakeDeps();
    await createRemindersService(deps).scheduleForDemand(analysis(), demand());
    const first = rows[0];
    await setReminderEnabled(deps, first, false);
    expect(notifications.cancelled).toEqual(['n1']);
    expect(rows[0].enabled).toBe(false);
    await setReminderEnabled(deps, { ...rows[0] }, true);
    expect(rows.find((r) => r.fireAt === first.fireAt)?.notificationId).toBe('n4');
    expect(rows).toHaveLength(3);
  });

  it('re-schedules enabled future reminders the OS lost', async () => {
    const { deps, rows, notifications } = fakeDeps();
    await createRemindersService(deps).scheduleForDemand(analysis(), demand());
    notifications.scheduled = [];
    await expect(rescheduleMissing(deps)).resolves.toBe(3);
    expect(notifications.scheduled.map((s) => s.body)).toEqual(Array(3).fill('You have a date coming up.'));
    expect(rows.every((r) => r.notificationId !== null)).toBe(true);
    await expect(rescheduleMissing(deps)).resolves.toBe(0);
  });
});

describe('S14 grouping and the Home next-date card', () => {
  const doc = { id: 'an_1', title: 'Medicaid letter', memberId: 'me', analysis: analysis() } as unknown as StoredDocument;
  const rem = (id: string, fireAt: string, over: Partial<Reminder> = {}): Reminder => ({
    id,
    documentId: 'an_1',
    demandId: 'd1',
    fireAt,
    notificationId: null,
    detailOptIn: false,
    enabled: true,
    label: 'Confirm your address',
    ...over,
  });

  it('groups by paper then date, own dates last, the focused paper first', () => {
    const list = [
      rem('a', '2026-10-13T13:00:00.000Z'),
      rem('b', '2026-10-07T13:00:00.000Z'),
      rem('c', '2026-10-02T13:00:00.000Z', { documentId: '', demandId: 'own:2026-10-03:x', label: 'Clinic' }),
    ];
    const groups = groupReminders(list, new Map([['an_1', doc]]));
    expect(groups.map((g) => g.key)).toEqual(['an_1', OWN_GROUP_KEY]);
    expect(groups[0].title).toBe('Medicaid letter');
    expect(groups[0].items[0].reminders.map((r) => r.id)).toEqual(['b', 'a']);
    expect(groups[0].items[0].verbatim).toBe('October 14, 2026');
    expect(groups[0].items[0].eventDate).toBe('2026-10-14');
    expect(groups[1].items[0].eventDate).toBe('2026-10-03');
  });

  it('Home card: the soonest switched-on reminder date within 30 days (S3)', () => {
    const row = (id: string, next: string | null): DocumentRow => ({
      id,
      memberId: 'me',
      title: id === 'an_1' ? 'Medicaid letter' : id,
      category: 'benefits',
      documentType: 'medicaid_renewal',
      createdAt: '2026-09-01T00:00:00.000Z',
      nextDateIso: next,
      pageCount: 1,
    });
    const docs = new Map([['an_1', doc]]);
    // A saved paper with a date but no reminder does not show the card.
    expect(pickNextDate([row('an_1', '2026-10-14'), row('none', null)], [], docs, NOW)).toBeNull();
    // A reminder that is switched off does not count either.
    const off = rem('x', '2026-10-13T13:00:00.000Z', { enabled: false });
    expect(pickNextDate([row('an_1', '2026-10-14')], [off], docs, NOW)).toBeNull();
    // The card shows the date the reminder is about, not the fire time.
    expect(pickNextDate([row('an_1', '2026-10-14')], [rem('a', '2026-10-07T13:00:00.000Z')], docs, NOW)).toEqual({
      documentId: 'an_1',
      title: 'Medicaid letter',
      dateIso: '2026-10-14',
    });
    // Own dates compete on the same terms; more than 30 days away is ignored.
    const own = rem('o', '2026-10-01T13:00:00.000Z', { documentId: '', demandId: 'own:2026-10-02:z', label: 'Clinic' });
    const far = rem('f', '2026-11-29T13:00:00.000Z', { documentId: '', demandId: 'own:2026-11-30:y', label: 'Far' });
    expect(pickNextDate([row('an_1', '2026-10-14')], [rem('a', '2026-10-07T13:00:00.000Z'), own], docs, NOW)?.title).toBe(
      'Clinic',
    );
    expect(pickNextDate([], [far], docs, NOW)).toBeNull();
  });
});

describe('date wording: Gregorian calendar, Western digits (D-26)', () => {
  // prs/ps/fa default to the Solar Hijri calendar ("15 Mizan 1405") and th to the Buddhist one
  // ("2569"): a court date must read as the paper prints it — October 7, 2026.
  it.each(['prs', 'ps', 'fa', 'ar', 'ur', 'th', 'my', 'es', 'en'])('%s: formatDay keeps 2026, day 7 and Western digits', (tag) => {
    const text = formatDay('2026-10-07', tag);
    expect(text).toContain('2026');
    expect(text).toMatch(/\b7\b/);
    expect(text).not.toMatch(/1405|2569/);
    expect(text).not.toMatch(/[\u0660-\u0669\u06f0-\u06f9\u1040-\u1049]/);
  });

  it('English and Dari read as the Gregorian date', () => {
    expect(formatDay('2026-10-07', 'en')).toBe('Wednesday, October 7, 2026');
    const prs = formatDay('2026-10-07', 'prs');
    expect(prs).not.toContain('میزان'); // Solar Hijri month "Mizan"
    expect(prs).toContain('اکتوبر'); // October
    const fire = formatFireTime(new Date(2026, 9, 4, 9, 0).toISOString(), 'prs');
    expect(fire).toContain('2026');
    expect(fire).toContain('9:00');
    expect(fire).not.toMatch(/[\u06f0-\u06f9]/);
    expect(formatClock(new Date(2026, 9, 4, 9, 5).toISOString(), 'ps')).toMatch(/9:05/);
  });

  it('helpers: locale extension, digit mapping, numeric fallback', () => {
    expect(gregorianLocale('prs')).toBe('prs-u-ca-gregory-nu-latn');
    expect(gregorianLocale('en-u-ca-gregory')).toBe('en-u-ca-gregory');
    expect(toWesternDigits('۱۴۰۵ ٢٠٢٦ ၂၀၂၆ 12')).toBe('1405 2026 2026 12');
    expect(formatDay('not a date', 'prs')).toBe('not a date');
    expect(formatDay('2026-10-07', '###')).toBe('2026-10-07');
  });
});

describe('opt-in save document', () => {
  const pages: CapturedPage[] = [
    { id: 'p1', uri: 'file:///p1.jpg', base64: 'QUJD', mimeType: 'image/jpeg', rotation: 0, masks: [], source: 'camera' },
  ];

  it('never stores a page whose "Hide parts" boxes are not burned into its pixels (D-19)', () => {
    const box = { x0: 0.1, y0: 0.1, x1: 0.5, y1: 0.2 };
    const masked: CapturedPage[] = [
      { ...pages[0], id: 'm1', base64: '/9j/UNMASKED_ORIGINAL_BYTES_WITH_SSN', masks: [box] },
      { ...pages[0], id: 'm2', base64: 'UExBSU4=', masks: [] },
    ];
    // Native (masks travel as `masks[]`; the session page is the original photo): page 1 is dropped.
    const native = buildStoredDocument({ analysis: analysis(), pages: masked, memberId: 'me', keepPages: true, hideIds: false, now: NOW, t });
    expect(native.pages.map((p) => p.base64Jpeg)).toEqual(['UExBSU4=']);
    expect(JSON.stringify(native)).not.toContain('UNMASKED_ORIGINAL_BYTES_WITH_SSN');
    // Web display pages from `preparePages` have the boxes burned in: they may be kept.
    const web = buildStoredDocument({
      analysis: analysis(),
      pages: masked,
      memberId: 'me',
      keepPages: true,
      hideIds: false,
      now: NOW,
      t,
      masksBurnedIn: true,
    });
    expect(web.pages.map((p) => p.page)).toEqual([1, 2]);
    // A paper whose only page is masked keeps no images at all (the row says so).
    const only = buildStoredDocument({ analysis: analysis(), pages: [masked[0]], memberId: 'me', keepPages: true, hideIds: false, now: NOW, t });
    expect(only.pages).toEqual([]);
    expect(only.doc.keepPages).toBe(false);
  });

  it('keeps page images only when the setting is on', () => {
    const on = buildStoredDocument({ analysis: analysis(), pages, memberId: 'me', keepPages: true, hideIds: false, now: NOW, t });
    expect(on.doc.id).toBe('an_1');
    expect(on.doc.title).toBe('Medicaid letter');
    expect(on.doc.nextDateIso).toBe('2026-10-14');
    expect(on.pages).toEqual([{ page: 1, base64Jpeg: 'QUJD', thumbBase64: 'AAAA' }]);
    expect(on.doc.keepPages).toBe(true);
    const off = buildStoredDocument({ analysis: analysis(), pages, memberId: 'me', keepPages: false, hideIds: false, now: NOW, t });
    expect(off.pages).toEqual([]);
    expect(off.doc.keepPages).toBe(false);
    expect(off.doc.analysis.page_thumbnails).toBeNull();
  });

  it('"Hide ID numbers" masks A-numbers and receipt numbers and keeps no images', () => {
    expect(maskIdText('A-number A123456789 and receipt IOE0912345678')).toBe(
      'A-number A-•••-•••-789 and receipt IOE•••••••678',
    );
    const a = analysis([demand({ text: 'Bring A 123 456 789', source_quote: 'A-123-456-789' })]);
    const out = buildStoredDocument({ analysis: a, pages, memberId: 'me', keepPages: true, hideIds: true, now: NOW, t });
    expect(out.pages).toEqual([]);
    expect(out.doc.analysis.demands[0].text).toBe('Bring A-•••-•••-789');
    expect(out.doc.analysis.demands[0].source_quote).toBe('A-•••-•••-789');
    expect(out.doc.analysis.demands[0].id).toBe('d1');
  });

  it('"Save to read later" needs an id and stores no analysis', () => {
    const later = buildStoredDocument({
      analysis: null,
      pages,
      memberId: 'me',
      keepPages: true,
      hideIds: false,
      now: NOW,
      t,
      documentId: 'doc_1',
    });
    expect(later.doc.analysis).toBeNull();
    expect(later.doc.title).toBe('{type} · 2026-09-30'.replace('{type}', t('vault.category.other')));
    expect(later.doc.nextDateIso).toBeNull();
  });
});
