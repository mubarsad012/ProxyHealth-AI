// Estimated dates (PRODUCT_SPEC S7 item 8, D-11/D-12, CL-080(d)): the demand row says "About {date}
// (estimate)" with the server's written-out `localized_line` ("November 13, 2026", English month and
// Western digits in every language), plus the pack-digit line for packs with their own digits. A
// stored paper from before the server wrote estimates out (bare ISO day in `localized_line` and in
// the banner's `{date}`) gets the server's default spelling. A printed (stated) date is never
// rewritten. The new copy key comes from keys-2c-mobilescan.json, so the test packs below carry it
// until the COPY merge.

import { render } from '@testing-library/react-native';

import type { AnalysisResult, DateInfo, Urgency } from '@/api/types';
import { bundledPackFor, EN_PACK, t, useI18n } from '@/i18n/store';
import { estimateDateText, isIsoDayText } from '@/lib/dates';

import fixture from '../../../assets/fixtures/insurance_denial_180d.result.en.json';
import { DemandRow } from './cards/DemandsCard';
import {
  ESTIMATE_ABOUT_KEY,
  estimatedDateLine,
  estimatedDigitsLine,
  estimateReadable,
  localizeUrgencyDate,
} from './estimatedDate';
import { ResultView } from './ResultView';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

const base = (): AnalysisResult => JSON.parse(JSON.stringify(fixture)) as AnalysisResult;
type DemandT = AnalysisResult['demands'][number];

/** "About {date} (estimate)" with the date's LTR isolate (and the RTL pack's outer isolate) allowed. */
function aboutLine(date: string): RegExp {
  const iso = '[\\u2066-\\u2069]*';
  const esc = date.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');
  return new RegExp(`^${iso}About ${iso}${esc}${iso} \\(estimate\\)${iso}$`);
}

function estimated(a: AnalysisResult): DemandT {
  const d = a.demands.find((x) => x.date?.kind === 'estimated');
  if (!d) throw new Error('fixture has no estimated date');
  return d;
}

beforeEach(() => {
  useI18n.getState().setPack({ ...EN_PACK, strings: { ...EN_PACK.strings, [ESTIMATE_ABOUT_KEY]: 'About {date} (estimate)' } });
});

afterAll(() => useI18n.getState().setPack(EN_PACK));

describe('server-style estimate text', () => {
  it('writes an ISO day like deadline_rules.estimate_text does by default', () => {
    expect(estimateDateText('2026-10-17')).toBe('October 17, 2026');
    expect(estimateDateText('2026-11-03T00:00:00Z')).toBe('November 3, 2026');
    expect(estimateDateText('October 17')).toBeNull();
    expect(estimateDateText(null)).toBeNull();
  });

  it('recognises a bare ISO day in any digits (an old server line)', () => {
    expect(isIsoDayText('2026-10-17')).toBe(true);
    expect(isIsoDayText('۲۰۲۶-۱۰-۱۷')).toBe(true);
    expect(isIsoDayText('٢٠٢٦-١٠-١٧')).toBe(true);
    expect(isIsoDayText('October 17, 2026')).toBe(false);
    expect(isIsoDayText('11/13/2026')).toBe(false);
    expect(isIsoDayText(null)).toBe(false);
  });
});

describe('estimate lines', () => {
  it('uses the server line; falls back only for a missing or bare-ISO line; never for a stated date', () => {
    const date = estimated(base()).date as DateInfo;
    expect(estimateReadable({ ...date, localized_line: 'November 13, 2026' })).toBe('November 13, 2026');
    expect(estimateReadable({ ...date, localized_line: '11/13/2026' })).toBe('11/13/2026');
    expect(estimateReadable({ ...date, value_iso: '2026-10-17', localized_line: null })).toBe('October 17, 2026');
    expect(estimateReadable({ ...date, value_iso: '2026-10-17', localized_line: '۲۰۲۶-۱۰-۱۷' })).toBe('October 17, 2026');
    expect(estimatedDateLine({ ...date, localized_line: 'November 13, 2026' }, t)).toBe('About November 13, 2026 (estimate)');
    expect(estimatedDateLine({ ...date, kind: 'stated' }, t)).toBeNull();
  });

  it('adds the pack-digit line only for packs with their own digits', () => {
    const date = { ...(estimated(base()).date as DateInfo), value_iso: '2026-11-13' };
    expect(estimatedDigitsLine(date, 'persian')).toBe('۱۳/۱۱/۲۰۲۶');
    expect(estimatedDigitsLine(date, 'persian', 'mdy')).toBe('۱۱/۱۳/۲۰۲۶');
    expect(estimatedDigitsLine(date, 'western')).toBeNull();
    expect(estimatedDigitsLine({ ...date, kind: 'stated' }, 'persian')).toBeNull();
  });

  it('the banner {date} of an old estimate is written out; a printed date is left as printed', () => {
    const est: Urgency = { ...base().urgency, headline_key: 'urgency.medium.estimated', headline_params: { date: '2026-10-17', date_iso: '2026-10-17' } };
    expect(localizeUrgencyDate(est).headline_params).toEqual({ date: 'October 17, 2026', date_iso: '2026-10-17' });
    // The current server already sends the written-out line: unchanged.
    const now: Urgency = { ...est, headline_params: { date: 'October 17, 2026', date_iso: '2026-10-17' } };
    expect(localizeUrgencyDate(now)).toBe(now);
    // A date printed as an ISO day on the paper is printed text (D-26): never rewritten.
    const printed: Urgency = { ...est, headline_key: 'urgency.medium.date_soon', headline_params: { date: '2026-10-07', date_iso: '2026-10-07' } };
    expect(localizeUrgencyDate(printed)).toBe(printed);
  });

  it('S7 renders the demand row line and the banner without raw ISO', async () => {
    const a = base();
    const d = estimated(a);
    const iso = (d.date as DateInfo).value_iso as string;
    const readable = estimateReadable(d.date) as string;
    const view = await render(<ResultView analysis={a} pages={[]} handlers={{}} />);
    expect(view.getByTestId(`estimate-${d.id}`)).toHaveTextContent(aboutLine(readable));
    expect(view.queryByTestId(`estimate-digits-${d.id}`)).toBeNull();
    // Two places: the banner headline and the demand row.
    expect(view.getAllByText(readable, { exact: false }).length).toBeGreaterThanOrEqual(2);
    expect(view.queryByText(iso, { exact: false })).toBeNull();
  });

  it('a Dari pack keeps the estimate as the server wrote it and adds Dari digits', async () => {
    const prs = bundledPackFor('prs');
    if (!prs) return;
    useI18n.getState().setPack({ ...prs, strings: { ...prs.strings, [ESTIMATE_ABOUT_KEY]: 'About {date} (estimate)' } });
    const a = base();
    const d = estimated(a);
    const readable = estimateReadable(d.date) as string;
    const view = await render(<DemandRow analysis={a} pages={[]} handlers={{}} demand={d} />);
    expect(view.getByTestId(`estimate-${d.id}`)).toHaveTextContent(aboutLine(readable));
    expect(view.getByTestId(`estimate-digits-${d.id}`)).toHaveTextContent(/^[۰-۹]{1,2}\/[۰-۹]{1,2}\/۲۰۲۶$/);
  });
});
