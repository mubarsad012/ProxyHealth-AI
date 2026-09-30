// POLISH items 1 and 5 on the result screen. (1) A sample result shows the server's `days_until`
// (computed as of DEMO_AS_OF, apps/api/proxyhealth_api/demo/as_of.py) — never a device-clock
// recomputation — plus the one fixed line `demo.as_of_note`; a real result shows no such line.
// (5) In an RTL pack, server text whose strong characters are all LTR (a pseudo-translated
// sentence, the English body) is FSI-isolated; Dari text is left alone.

import { render } from '@testing-library/react-native';

import type { AnalysisResult, LanguagePack } from '@/api/types';
import { FSI, PDI } from '@/i18n/bidi';
import { bundledPackFor, EN_PACK, fromLanguagePack, t, useI18n } from '@/i18n/store';

import medicaidEn from '../../../assets/fixtures/medicaid_address_confirmation.result.en.json';
import medicaidPrs from '../../../assets/fixtures/medicaid_address_confirmation.result.prs.json';
import { DEMO_AS_OF_NOTE_KEY, sampleAsOfNoteKey } from './disclaimers';
import { ResultView } from './ResultView';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

const handlers = { onOpenSource: jest.fn(), onRescan: jest.fn(), onAsk: jest.fn() };

function asResult(raw: unknown): AnalysisResult {
  return JSON.parse(JSON.stringify(raw)) as AnalysisResult;
}

/** An RTL pseudo pack like the mock serves for a Tier 3 language: "⟦rhg⟧ " + English. */
function pseudoRtlPack() {
  const strings = Object.fromEntries(Object.entries(EN_PACK.strings).map(([k, v]) => [k, `⟦rhg⟧ ${v}`]));
  const pack: LanguagePack = {
    language_tag: 'rhg',
    language_name_native: 'Rohingya',
    language_name_en: 'Rohingya',
    direction: 'rtl',
    script: 'Rohg',
    digit_system: 'western',
    font_hint: null,
    tier: 3,
    source: 'generated',
    pack_version: 'test',
    etag: 'test',
    strings,
    fallback_keys: [],
    coverage: 1,
    machine_translated: true,
    reviewed_by: null,
    confidence: 'low',
    generated_at: '2026-09-29T00:00:00Z',
    tts_tag: null,
    tts_fallback_tag: 'my-MM',
  } as LanguagePack;
  return fromLanguagePack(pack, 'generated');
}

const ONLY_DATE = [
  'setTimeout', 'setInterval', 'setImmediate', 'clearTimeout', 'clearInterval', 'clearImmediate', 'nextTick',
  'queueMicrotask', 'requestAnimationFrame', 'cancelAnimationFrame', 'requestIdleCallback', 'cancelIdleCallback',
  'hrtime', 'performance',
] as const;

afterEach(() => {
  jest.useRealTimers();
  useI18n.getState().setPack(EN_PACK);
});

describe('sample dates are pinned (item 1)', () => {
  it('a sample with dates gets the note; a real result does not', () => {
    const sample = asResult(medicaidEn);
    expect(sample.model_meta.demo).toBe(true);
    expect(sampleAsOfNoteKey(sample)).toBe(DEMO_AS_OF_NOTE_KEY);
    const real = asResult(medicaidEn);
    real.model_meta = { ...real.model_meta, demo: false };
    real.warnings = real.warnings.filter((w) => w !== 'demo_sample');
    expect(sampleAsOfNoteKey(real)).toBeNull();
    const undated = asResult(medicaidEn);
    undated.urgency = { ...undated.urgency, nearest_date_iso: null, days_until: null };
    undated.demands = undated.demands.map((d) => ({ ...d, date: null }));
    expect(sampleAsOfNoteKey(undated)).toBeNull();
  });

  it('shows the server days_until and the note even when the device clock is months later', async () => {
    jest.useFakeTimers({ now: new Date(2027, 2, 1, 12), doNotFake: [...ONLY_DATE] });
    const a = asResult(medicaidEn);
    expect(a.urgency.days_until).toBe(12);
    const { getByTestId, getByText } = await render(<ResultView analysis={a} pages={[]} handlers={handlers} />);
    expect(getByText(t('urgency.days_until', { days: 12 }))).toBeTruthy();
    expect(getByTestId('demo-as-of-note')).toHaveTextContent(t('demo.as_of_note'));
    expect(t('demo.as_of_note')).toBe('Sample dates are shown as if today were October 2, 2026.');
  });
});

describe('RTL isolation of server text (item 5)', () => {
  it('Dari text in the prs pack is not isolated', async () => {
    useI18n.getState().setPack(bundledPackFor('prs')!);
    const a = asResult(medicaidPrs);
    const { getByText, queryByText } = await render(<ResultView analysis={a} pages={[]} handlers={handlers} />);
    expect(getByText(a.summary.title)).toBeTruthy();
    expect(queryByText(`${FSI}${a.summary.title}${PDI}`)).toBeNull();
    expect(getByText(t('demo.as_of_note'))).toBeTruthy(); // Dari copy: mixed with digits, not wrapped
  });

  it('a pseudo-translated (all-LTR) summary in an RTL pack is FSI-isolated', async () => {
    useI18n.getState().setPack(pseudoRtlPack());
    const a = asResult(medicaidEn);
    a.summary = { ...a.summary, title: `⟦rhg⟧ ${a.summary.title}` };
    const { getByText } = await render(<ResultView analysis={a} pages={[]} handlers={handlers} />);
    expect(getByText(`${FSI}${a.summary.title}${PDI}`)).toBeTruthy();
    // Pack strings too: "⟦rhg⟧ Need help now?" keeps its question mark at the end.
    expect(t('demo.as_of_note')).toBe(`${FSI}⟦rhg⟧ Sample dates are shown as if today were October 2, 2026.${PDI}`);
    expect(getByText(t('demo.as_of_note'))).toBeTruthy();
  });
});
