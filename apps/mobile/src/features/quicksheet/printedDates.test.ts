// Phase 2C: the quick sheet's "Dates" lines carry the date exactly as PRINTED (`value_verbatim`).
// The server's `localized_line` (e.g. Persian digits) may be added after it, never substituted (D-26).

import type { AnalysisResult } from '@/api/types';
import { BASE_STRINGS, translate } from '@/i18n/store';

import { buildQuickSheetText, dateLines } from './build';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

const medicaidPrs = require('../../../assets/fixtures/medicaid_address_confirmation.result.prs.json') as AnalysisResult;
const medicaidEn = require('../../../assets/fixtures/medicaid_address_confirmation.result.en.json') as AnalysisResult;

const t = (key: string, vars?: Record<string, string | number>) => translate(BASE_STRINGS, key, vars);
const clone = (a: AnalysisResult): AnalysisResult => JSON.parse(JSON.stringify(a));

describe('quick sheet printed dates (D-26)', () => {
  it('Dari: the printed date stays, the Persian-digit line is only added', () => {
    const lines = dateLines(clone(medicaidPrs), t);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toContain('October 14, 2026');
    expect(lines[0]).toContain('(۲۰۲۶-۱۰-۱۴)');
    // The printed date comes first; the localized line never replaces it.
    expect(lines[0].indexOf('October 14, 2026')).toBeLessThan(lines[0].indexOf('۲۰۲۶-۱۰-۱۴'));
  });

  it('a localized line that differs from the demand text never becomes the label', () => {
    const a = clone(medicaidEn);
    a.demands[0] = { ...a.demands[0], text: 'Send the form back.', date: { ...a.demands[0].date!, localized_line: '14/10/2026' } };
    const [line] = dateLines(a, t);
    expect(line).toBe('October 14, 2026 (14/10/2026) — Send the form back.');
  });

  it('no printed value → no date label (a localized line alone is not shown)', () => {
    const a = clone(medicaidEn);
    a.demands[0] = { ...a.demands[0], value_verbatim: '', date: { ...a.demands[0].date!, localized_line: '۲۰۲۶-۱۰-۱۴' } };
    expect(dateLines(a, t)).toEqual([]);
  });

  it('estimated dates keep the estimate prefix in front of the printed words', () => {
    const a = clone(medicaidEn);
    a.demands[0] = {
      ...a.demands[0],
      text: 'Answer the letter.',
      value_verbatim: 'within 30 days',
      date: { ...a.demands[0].date!, kind: 'estimated', localized_line: null },
    };
    const [line] = dateLines(a, t);
    expect(line.startsWith(`${BASE_STRINGS['demand.estimate_prefix']} within 30 days`)).toBe(true);
  });

  it('the built sheet (and the PDF request built from it) carries the printed date', () => {
    const sheet = buildQuickSheetText(clone(medicaidPrs), [], t, { today: '2026-10-01' });
    const dates = sheet.sections[sheet.sectionKinds!.indexOf('dates')];
    expect(dates.lines.join(' ')).toContain('October 14, 2026');
  });
});
