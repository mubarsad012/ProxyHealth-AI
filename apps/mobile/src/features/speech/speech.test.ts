// Read-aloud honesty (D-26) and the fixed-copy helpers around the result (D-17): the fallback line
// names the missing language and the voice actually used, and is absent when the pack's own voice
// exists; hear-it mode reads the emergency card first and never reads unverified items as facts;
// banners come from enums only; the web blur hint is a Laplacian-variance threshold.

import type { AnalysisResult, Demand } from '@/api/types';
import { askPrompts } from '@/features/analysis/ResultView';
import { disclaimerKey, resultBanners, warningChipKeys } from '@/features/analysis/disclaimers';
import { hearItItems } from '@/features/analysis/hearItMode';
import { blurryPageNumbers } from '@/features/scan/blurHints';
import { LANGUAGES } from '@/i18n/languages';
import { t } from '@/i18n/store';
import { BLUR_THRESHOLD, laplacianVariance, looksBlurry, rgbaToGray } from '@/lib/image';
import type { ResolvedVoice, Voice } from '@/lib/tts';
import type { CapturedPage } from '@/store/session';

import medicaidEn from '../../../assets/fixtures/medicaid_address_confirmation.result.en.json';
import { fallbackNotice, hasEnglishVoice, languageName } from './fallback';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

const base = (): AnalysisResult => JSON.parse(JSON.stringify(medicaidEn)) as AnalysisResult;
const voice = (language: string): Voice => ({ identifier: language, name: language, quality: 'Default', language }) as Voice;

describe('honest TTS fallback', () => {
  it('says which voice is used when the pack language has none', () => {
    const resolved: ResolvedVoice = { voice: voice('fa-IR'), usedFallbackTag: 'fa-IR', languageTag: 'fa-IR' };
    const line = fallbackNotice(resolved, 'prs', t);
    expect(languageName('fa-IR')).toBe(LANGUAGES.fa.name_native);
    expect(languageName('fa-AF')).toBe('دری');
    expect(line).toBe(t('tts.fallback_offer', { language: 'دری', fallback: LANGUAGES.fa.name_native }));
    // Pashto read with the Dari voice names Dari; a regional voice of the same language is silent.
    expect(fallbackNotice({ voice: voice('fa-AF'), usedFallbackTag: 'fa-AF', languageTag: 'fa-AF' }, 'ps', t)).toBe(
      t('tts.fallback_offer', { language: LANGUAGES.ps.name_native, fallback: 'دری' }),
    );
    expect(fallbackNotice({ voice: voice('es-MX'), usedFallbackTag: 'es-MX', languageTag: 'es-MX' }, 'es', t)).toBeNull();
  });

  it('is silent when the own voice (or no voice list) is used', () => {
    expect(fallbackNotice({ voice: voice('fa-AF'), usedFallbackTag: null, languageTag: 'fa-AF' }, 'prs', t)).toBeNull();
    expect(fallbackNotice({ voice: null, usedFallbackTag: null, languageTag: 'fa-AF' }, 'prs', t)).toBeNull();
    expect(fallbackNotice(null, 'prs', t)).toBeNull();
  });

  it('hides "Read aloud in English" only when a voice list exists without English', () => {
    expect(hasEnglishVoice({ voice: voice('en-US'), usedFallbackTag: null, languageTag: 'en-US' })).toBe(true);
    expect(hasEnglishVoice({ voice: null, usedFallbackTag: null, languageTag: 'en-US' })).toBe(true);
    expect(hasEnglishVoice({ voice: voice('es-US'), usedFallbackTag: 'es-US', languageTag: 'es-US' })).toBe(false);
    expect(hasEnglishVoice(null)).toBe(false);
  });
});

describe('hear-it mode order', () => {
  it('emergency first, footer last, unverified items never read', () => {
    const a = base();
    const u: Demand = { ...a.demands[0], id: 'u1', text: 'Pay a fee now', verified: false };
    a.unverified = [u];
    a.demands = [...a.demands, u];
    const items = hearItItems(a, t, 'en', true);
    expect(items[0].id).toBe('emergency');
    expect(items[0].text).toContain(t('emergency.911'));
    expect(items[items.length - 1].id).toBe('footer');
    expect(items.map((i) => i.text).join(' ')).not.toContain('Pay a fee now');
    expect(hearItItems(a, t, 'en', false)[0].id).not.toBe('emergency');
  });
});

describe('fixed-copy mapping', () => {
  it('maps disclaimer kinds, warning chips and banners from enums only', () => {
    expect(disclaimerKey('legal_information_only')).toBe('disclaimer.legal_information_only');
    expect(warningChipKeys(['phrasing_lint_unavailable', 'emergency_lexicon_unavailable', 'partial_pages'])).toEqual([
      'warning.checks_unavailable',
      'warning.partial_pages',
    ]);
    const a = base();
    a.model_meta = { ...a.model_meta, quality: 'degraded', demo: true };
    const keys = resultBanners(a, { machineTranslated: true, uiTag: 'prs' }).map((b) => b.key);
    expect(keys).toEqual(['banner.machine_translated', 'banner.degraded_model', 'banner.demo_sample']);
  });

  it('offers the first two questions_to_ask as S7 prompts', () => {
    expect(askPrompts({ questions_to_ask: ['A?', ' ', 'B?', 'C?'] })).toEqual(['A?', 'B?']);
    expect(askPrompts({ questions_to_ask: [] })).toEqual([]);
  });
});

describe('web blur hint', () => {
  const size = 32;
  const flat = new Array(size * size).fill(128);
  const edges = Array.from({ length: size * size }, (_, i) => ((Math.floor(i / size) + (i % size)) % 2 ? 255 : 0));

  it('flat pages score ~0 (blurry), sharp text-like edges score high', () => {
    expect(laplacianVariance(flat, size, size)).toBe(0);
    expect(laplacianVariance(edges, size, size)).toBeGreaterThan(BLUR_THRESHOLD * 100);
    expect(looksBlurry(0)).toBe(true);
    expect(looksBlurry(null)).toBe(false);
  });

  it('converts RGBA to luma and reports blurry page numbers in document order', () => {
    expect(Array.from(rgbaToGray([255, 255, 255, 255, 0, 0, 0, 255], 2, 1)).map(Math.round)).toEqual([255, 0]);
    const pages = [{ id: 'a' }, { id: 'b' }, { id: 'c' }] as CapturedPage[];
    expect(blurryPageNumbers(pages, { a: 500, b: 12, c: null })).toEqual([2]);
  });
});
