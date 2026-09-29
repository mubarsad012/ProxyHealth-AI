// Result cards (BUILD_PLAN §5.6 step 4 / Acceptance): renders the synced RFE and Medicaid golden
// results (`assets/fixtures/*.result.{en,prs}.json`, written by sync_to_mobile.py) in LTR and RTL
// and at font scale 2. Asserts: every fact row shows quote + crop (or full-page / quote fallback)
// + confidence chip; an unverified demand never appears in the demands card and never gets a
// reminder button; the emergency card renders first when `safety.emergency`.

import { render, within } from '@testing-library/react-native';
import { PixelRatio } from 'react-native';

import type { AnalysisResult, Demand } from '@/api/types';
import { LRI, PDI } from '@/design/components/Bidi';
import { bundledPackFor, EN_PACK, t, useI18n } from '@/i18n/store';

import medicaidEn from '../../../assets/fixtures/medicaid_address_confirmation.result.en.json';
import medicaidPrs from '../../../assets/fixtures/medicaid_address_confirmation.result.prs.json';
import rfeEn from '../../../assets/fixtures/uscis_rfe_87d.result.en.json';
import rfePrs from '../../../assets/fixtures/uscis_rfe_87d.result.prs.json';
import { ResultView } from './ResultView';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

type Json = { [k: string]: unknown };

function asResult(raw: unknown): AnalysisResult {
  return JSON.parse(JSON.stringify(raw)) as AnalysisResult;
}

/** Adds a verified reminder-eligible date, an unverified item (wrongly flagged eligible, to prove
 *  the UI still refuses it) and an emergency trigger to a golden result. */
function withExtras(base: AnalysisResult): AnalysisResult {
  const a = asResult(base);
  const first = a.demands[0];
  a.demands[0] = {
    ...first,
    reminder_eligible: true,
    verified: true,
    date: {
      kind: 'stated',
      value_iso: '2026-10-14',
      time_text: null,
      formula: null,
      anchor_quote: null,
      anchor_demand_id: null,
      rule_id: null,
      rule_source_url: null,
      rule_verification: null,
      localized_line: null,
    },
  };
  const unverified: Demand = {
    ...first,
    id: 'u1',
    text: 'Pay a fee',
    value_verbatim: '$500',
    source_quote: 'Pay $500 today',
    verified: false,
    reminder_eligible: true,
    verification_note: 'not found on page',
    confidence: 'low',
  };
  a.unverified = [unverified];
  a.safety = { emergency: true, emergency_kinds: ['chest_pain'], credential_or_payment_request: false };
  return a;
}

function testIds(node: unknown, out: string[] = []): string[] {
  if (!node) return out;
  if (Array.isArray(node)) {
    for (const n of node) testIds(n, out);
    return out;
  }
  const n = node as Json;
  const props = (n.props ?? {}) as Json;
  if (typeof props.testID === 'string') out.push(props.testID);
  if (n.children) testIds(n.children, out);
  return out;
}

function textNodes(node: unknown, out: Json[] = []): Json[] {
  if (!node) return out;
  if (Array.isArray(node)) {
    for (const n of node) textNodes(n, out);
    return out;
  }
  const n = node as Json;
  if (n.type === 'Text') out.push(n);
  if (n.children) textNodes(n.children, out);
  return out;
}

const handlers = {
  onOpenSource: jest.fn(),
  onRescan: jest.fn(),
  onRemind: jest.fn(),
  onFindHelp: jest.fn(),
  onAsk: jest.fn(),
  onCall: jest.fn(),
};

async function renderResult(a: AnalysisResult) {
  return render(<ResultView analysis={a} pages={[]} handlers={handlers} />);
}

const CASES: [string, unknown, 'en' | 'prs'][] = [
  ['medicaid en', medicaidEn, 'en'],
  ['rfe en', rfeEn, 'en'],
  ['medicaid prs', medicaidPrs, 'prs'],
  ['rfe prs', rfePrs, 'prs'],
];

afterEach(() => {
  useI18n.getState().setPack(EN_PACK);
  jest.restoreAllMocks();
});

describe.each(CASES)('ResultView renders the %s golden', (_name, raw, lang) => {
  beforeEach(() => {
    if (lang === 'prs') {
      const pack = bundledPackFor('prs');
      if (!pack) throw new Error('prs pack not bundled');
      useI18n.getState().setPack(pack);
    }
  });

  it('shows quote + crop + confidence for every fact row', async () => {
    const a = asResult(raw);
    const { getByTestId, toJSON } = await renderResult(a);
    expect(getByTestId('card-what-is-this')).toBeTruthy();
    expect(getByTestId('card-asking-for')).toBeTruthy();
    for (const d of a.demands) {
      const row = within(getByTestId(`fact-${d.id}`));
      expect(row.getByTestId(`fact-${d.id}-crop`)).toBeTruthy();
      expect(row.getByText(t(`confidence.${d.confidence}`))).toBeTruthy();
      // The quote is shown as text (quote-only fallback when no page image is available).
      expect(row.getByText(d.source_quote, { exact: false })).toBeTruthy();
      // The value as printed is LTR-isolated (native Bidi path) and never localized.
      expect(within(getByTestId(`demand-${d.id}`)).getByText(`${LRI}${d.value_verbatim}${PDI}`)).toBeTruthy();
    }
    const ids = testIds(toJSON());
    expect(ids.indexOf('card-what-is-this')).toBeLessThan(ids.indexOf('card-asking-for'));
  });

  it('renders the emergency card first and refuses reminders for unverified items', async () => {
    const a = withExtras(asResult(raw));
    const { getByTestId, queryByTestId, toJSON } = await renderResult(a);
    const ids = testIds(toJSON());
    expect(ids[0]).toBe('result-view');
    expect(ids[1]).toBe('emergency-card');
    expect(ids.indexOf('emergency-card')).toBeLessThan(ids.indexOf('card-what-is-this'));
    expect(getByTestId('remind-d1')).toBeTruthy();
    expect(getByTestId('unverified-u1')).toBeTruthy();
    expect(queryByTestId('remind-u1')).toBeNull();
    expect(queryByTestId('demand-u1')).toBeNull();
    expect(within(getByTestId('card-asking-for')).queryByText('Pay a fee')).toBeNull();
  });
});

describe('ResultView direction', () => {
  it('mirrors rows in RTL and keeps them LTR in English', async () => {
    const pack = bundledPackFor('prs');
    if (!pack) throw new Error('prs pack not bundled');
    useI18n.getState().setPack(pack);
    const rtl = await renderResult(asResult(medicaidPrs));
    expect(JSON.stringify(rtl.toJSON())).toContain('"flexDirection":"row-reverse"');
    await rtl.unmount();
    useI18n.getState().setPack(EN_PACK);
    const ltr = await renderResult(asResult(medicaidEn));
    expect(JSON.stringify(ltr.toJSON())).not.toContain('"flexDirection":"row-reverse"');
  });
});

describe('ResultView at font scale 2 (200 %)', () => {
  it.each(CASES)('%s: renders every card with no truncated or fixed-height text', async (_n, raw, lang) => {
    jest.spyOn(PixelRatio, 'getFontScale').mockReturnValue(2);
    if (lang === 'prs') {
      const pack = bundledPackFor('prs');
      if (pack) useI18n.getState().setPack(pack);
    }
    const a = withExtras(asResult(raw));
    const { getByTestId, toJSON } = await renderResult(a);
    expect(getByTestId('card-plan')).toBeTruthy();
    expect(getByTestId('result-footer')).toBeTruthy();
    expect(getByTestId('emergency-card')).toBeTruthy();
    const texts = textNodes(toJSON());
    expect(texts.length).toBeGreaterThan(10);
    for (const n of texts) {
      const props = (n.props ?? {}) as Json;
      expect(props.numberOfLines ?? 0).toBe(0);
      expect(props.allowFontScaling).not.toBe(false);
      const flat = [props.style].flat(Infinity as 1) as (Json | null | undefined)[];
      expect(flat.some((st) => st && typeof st === 'object' && 'height' in st)).toBe(false);
    }
  });
});
