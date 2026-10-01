// S7 details found in the Phase 2B audit:
//  - words as printed (quotes, `value_verbatim`, `term_as_written`, S8 blocks) carry the paper's
//    language (`detected_language`) for screen readers, not the UI pack's (WCAG 3.1.2, COMPLIANCE §15);
//  - the scam card ends "Report it:" and is followed by the vetted `scam_report` contacts (J-F step 4);
//  - `phrasing_lint_unavailable` shows the "some safety checks" chip only for Tier 3 packs
//    (PRODUCT_SPEC §5.6), while `emergency_lexicon_unavailable` always shows.

import { render, within } from '@testing-library/react-native';
import { Platform } from 'react-native';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { AnalysisResult } from '@/api/types';
import { LRI, PDI } from '@/design/components/Bidi';
import { AppProviders } from '@/design/components/Providers';
import { bundledPackFor, EN_PACK, t, useI18n } from '@/i18n/store';

import medicaidPrs from '../../../assets/fixtures/medicaid_address_confirmation.result.prs.json';
import ntaAr from '../../../assets/fixtures/nta_hearing_date.result.ar.json';
import scamEn from '../../../assets/fixtures/scam_gift_card_letter.result.en.json';
import { paperLang, paperLangProps } from './cards/shared';
import { warningChipKeys } from './disclaimers';
import { ResultView } from './ResultView';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
jest.mock('@/lib/network', () => ({ useOnline: () => ({ online: false, known: true }), isOnline: async () => false }));

type Json = { type?: string; props?: Record<string, unknown>; children?: unknown };

function offlineClient(): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return new Proxy({ baseUrl: 'http://127.0.0.1:8031', fixturePageUrl: () => '' } as unknown as ApiClient, {
    get: (target, prop) => (prop in target ? target[prop as keyof ApiClient] : fail),
  });
}

function asResult(raw: unknown): AnalysisResult {
  return JSON.parse(JSON.stringify(raw)) as AnalysisResult;
}

/**
 * The screen-reader language of every leaf string containing `needle`: the nearest
 * `accessibilityLanguage` on the leaf's host element or any ancestor (null = the app language).
 */
function leafLanguages(
  node: unknown,
  needle: string,
  inherited: string | null = null,
  out: (string | null)[] = [],
  exact = false,
): (string | null)[] {
  if (!node || typeof node !== 'object') return out;
  if (Array.isArray(node)) {
    for (const n of node) leafLanguages(n, needle, inherited, out, exact);
    return out;
  }
  const n = node as Json;
  const own = typeof n.props?.accessibilityLanguage === 'string' ? (n.props.accessibilityLanguage as string) : inherited;
  const kids = Array.isArray(n.children) ? n.children : [];
  if (kids.some((k) => typeof k === 'string' && (exact ? k === needle : k.includes(needle)))) out.push(own);
  for (const k of kids) if (typeof k === 'object') leafLanguages(k, needle, own, out, exact);
  return out;
}

async function renderResult(a: AnalysisResult) {
  return render(
    <AppProviders client={offlineClient()} staticMetrics>
      <ResultView analysis={a} pages={[]} handlers={{ onOpenSource: jest.fn() }} />
    </AppProviders>,
  );
}

afterEach(() => useI18n.getState().setPack(EN_PACK));

describe('words as printed carry the paper language (Arabic UI, English NTA)', () => {
  beforeEach(() => {
    const pack = bundledPackFor('ar');
    if (!pack) throw new Error('ar pack not bundled');
    useI18n.getState().setPack(pack);
  });

  it('quotes, values and crops say lang=en; the explanation text stays ar', async () => {
    const a = asResult(ntaAr);
    expect(a.detected_language).toBe('en');
    const { toJSON, getByTestId } = await renderResult(a);
    const tree = toJSON();
    const d = a.demands[0];
    // The quote (quote-only fallback: no page image in this test), wherever it is shown.
    const quoteLangs = leafLanguages(tree, d.source_quote);
    expect(quoteLangs.length).toBeGreaterThan(0);
    expect(quoteLangs.every((l) => l === 'en')).toBe(true);
    // The value as printed in its demand row (the same date inside an Arabic sentence stays ar).
    const valueLangs = leafLanguages(getByTestId(`demand-${d.id}`), `${LRI}${d.value_verbatim}${PDI}`, null, [], true);
    expect(valueLangs).toEqual(['en']);
    // The term as printed in the glossary.
    expect(a.glossary.length).toBeGreaterThan(0);
    for (const g of a.glossary) {
      const langs = leafLanguages(getByTestId('card-glossary'), `${LRI}${g.term_as_written}${PDI}`, null, [], true);
      expect(langs).toEqual(['en']);
    }
    // The crop control is labelled with the quote → the same language.
    expect(getByTestId(`fact-${d.id}-crop`).props.accessibilityLanguage).toBe('en');
    // The target-language sentence keeps the UI language.
    const explained = leafLanguages(tree, d.text);
    expect(explained.length).toBeGreaterThan(0);
    expect(explained.every((l) => l === 'ar')).toBe(true);
  });

  it('web: the paper language goes on `lang` while the layout direction is kept', () => {
    const os = Platform.OS;
    Object.defineProperty(Platform, 'OS', { value: 'web', configurable: true });
    try {
      expect(paperLangProps('en', 'rtl')).toEqual({ accessibilityLanguage: 'en', lang: 'en', dir: 'rtl' });
    } finally {
      Object.defineProperty(Platform, 'OS', { value: os, configurable: true });
    }
    expect(paperLang('und')).toBeUndefined();
    expect(paperLang('')).toBeUndefined();
    expect(paperLangProps(null, 'ltr')).toEqual({});
  });
});

describe('scam card → where to report it', () => {
  it('"Report it:" is followed by DHS OIG / FTC from the vetted DB (bundled subset offline)', async () => {
    const a = asResult(scamEn);
    expect(a.scam_risk).toBe('likely');
    const { findByTestId, getByTestId } = await renderResult(a);
    const card = getByTestId('card-scam');
    expect(within(card).getByText(/Report it:/)).toBeTruthy();
    expect(await within(card).findByTestId('scam-report-resources')).toBeTruthy();
    expect(await findByTestId('resource-dhs_oig')).toBeTruthy();
    expect(within(card).getByText(t('scam.gift_card'))).toBeTruthy();
  });

  it('no reporting contacts on a paper with no scam risk', async () => {
    const a = asResult(scamEn);
    a.scam_risk = 'none';
    const { queryByTestId } = await renderResult(a);
    expect(queryByTestId('card-scam')).toBeNull();
    expect(queryByTestId('scam-report-resources')).toBeNull();
  });
});

describe('"Some safety checks are not available" chip (Tier 3 only)', () => {
  it('pure mapping: phrasing chip only for Tier 3; emergency-lexicon chip always', () => {
    expect(warningChipKeys(['phrasing_lint_unavailable'], { packTier: 2 })).toEqual([]);
    expect(warningChipKeys(['phrasing_lint_unavailable'], { packTier: 1 })).toEqual([]);
    expect(warningChipKeys(['phrasing_lint_unavailable'], { packTier: 3 })).toEqual(['warning.checks_unavailable']);
    expect(warningChipKeys(['emergency_lexicon_unavailable'], { packTier: 1 })).toEqual(['warning.checks_unavailable']);
    expect(warningChipKeys(['phrasing_lint_unavailable'])).toEqual(['warning.checks_unavailable']);
  });

  it('bundled Dari (Tier 2) result: no chip', async () => {
    const pack = bundledPackFor('prs');
    if (!pack) throw new Error('prs pack not bundled');
    useI18n.getState().setPack(pack);
    const a = asResult(medicaidPrs);
    expect(a.warnings).toContain('phrasing_lint_unavailable');
    const { queryByText } = await renderResult(a);
    expect(queryByText(t('warning.checks_unavailable'))).toBeNull();
  });

  it('a Tier 3 language (not in the seed) keeps the chip', async () => {
    const a = asResult(medicaidPrs);
    a.target_language = 'x-tier3-test';
    const { getByText } = await renderResult(a);
    expect(getByText(t('warning.checks_unavailable'))).toBeTruthy();
  });
});
