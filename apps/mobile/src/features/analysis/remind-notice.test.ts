jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

import { remindNotice } from './ResultScreen';

const t = (k: string) => k;
const demand = { value_verbatim: 'October 14, 2026', date: { kind: 'stated' } } as never;

describe('remindNotice', () => {
  it('shows a visible line when the date has already passed (never silent)', () => {
    expect(remindNotice('past', demand, t)).toBe('reminders.date_passed');
  });
  it('keeps the existing outcomes', () => {
    expect(remindNotice('scheduled', demand, t)).toBe('reminders.added');
    expect(remindNotice('ics', demand, t)).toBe('reminders.web_explain');
    expect(remindNotice('denied', demand, t)).toBe('reminders.permission_denied');
  });
});
