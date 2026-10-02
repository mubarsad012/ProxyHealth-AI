// Read-aloud honesty (D-26) and the fixed-copy helpers around the result (D-17): the fallback line
// names the missing language and the voice actually used, and is absent when the pack's own voice
// exists; hear-it mode reads the emergency card first and never reads unverified items as facts;
// banners come from enums only; the web blur hint is a Laplacian-variance threshold.

import type { AnalysisResult, Demand, RedFlag } from '@/api/types';
import { askPrompts } from '@/features/analysis/ResultView';
import { disclaimerKey, resultBanners, warningChipKeys } from '@/features/analysis/disclaimers';
import { hearItItems } from '@/features/analysis/hearItMode';
import { digitGroupedForSpeech } from '@/features/emergency/EmergencyCard';
import { blurryPageNumbers } from '@/features/scan/blurHints';
import { LANGUAGES } from '@/i18n/languages';
import { t } from '@/i18n/store';
import { BLUR_THRESHOLD, laplacianVariance, looksBlurry, rgbaToGray } from '@/lib/image';
import type { ResolvedVoice, Voice } from '@/lib/tts';
import type { CapturedPage } from '@/store/session';

import insuranceEn from '../../../assets/fixtures/insurance_denial_180d.result.en.json';
import medicaidEn from '../../../assets/fixtures/medicaid_address_confirmation.result.en.json';
import medicaidPrs from '../../../assets/fixtures/medicaid_address_confirmation.result.prs.json';
import { FALLBACK_ENGLISH_KEY, fallbackNotice, hasEnglishVoice, languageName } from './fallback';

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
    // `noVoice`: the phone has no English voice either, so the clerk button stays hidden.
    expect(hasEnglishVoice({ voice: null, usedFallbackTag: null, languageTag: 'en-US', noVoice: true })).toBe(false);
  });

  it('shows the tts.no_voice line when the phone has no voice for the language (noVoice)', () => {
    const line = fallbackNotice({ voice: null, usedFallbackTag: null, languageTag: 'ps-AF', noVoice: true }, 'ps', t);
    expect(line).toBe(t('tts.no_voice', { language: LANGUAGES.ps.name_native }));
    expect(fallbackNotice({ voice: null, usedFallbackTag: null, languageTag: 'fa-AF', noVoice: true }, 'prs', t)).toBe(
      t('tts.no_voice', { language: 'دری' }),
    );
  });

  it('an English fallback says "Hear it in English?" (never "English or English")', () => {
    const line = fallbackNotice({ voice: voice('en-US'), usedFallbackTag: 'en-US', languageTag: 'en-US' }, 'ht', t);
    expect(line).toBe(t(FALLBACK_ENGLISH_KEY, { language: LANGUAGES.ht.name_native }));
    expect(line).not.toBe(t('tts.fallback_offer', { language: LANGUAGES.ht.name_native, fallback: 'English' }));
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
    // Read digit-grouped ("call 9 1 1"), never as "nine hundred eleven".
    expect(items[0].text).toContain(digitGroupedForSpeech(t('emergency.911')));
    expect(items[0].text).toContain('9 1 1');
    expect(items[items.length - 1].id).toBe('footer');
    expect(items.map((i) => i.text).join(' ')).not.toContain('Pay a fee now');
    expect(hearItItems(a, t, 'en', false)[0].id).not.toBe('emergency');
  });
});

describe('hear-it mode languages (S5 output-language chip, D-26)', () => {
  const flag = (over: Partial<RedFlag>): RedFlag => ({
    fixed_copy_key: null,
    kind: 'other',
    page: 1,
    severity: 'medium',
    source_quote: null,
    span_ids: [],
    text: '',
    verified: true,
    ...over,
  });

  it('reads the model text in target_language and fixed copy in the UI pack', () => {
    // UI English, chip set to Dari: the Dari summary, demands and plan get the Dari voice.
    const a = JSON.parse(JSON.stringify(medicaidPrs)) as AnalysisResult;
    expect(a.target_language).toBe('prs');
    const items = hearItItems(a, t, 'en', false);
    const summary = items.filter((i) => i.id === 'summary');
    expect(summary).toEqual([
      { id: 'summary', lang: 'en', text: t('card.what_is_this') },
      { id: 'summary', lang: 'prs', text: `${a.summary.title}. ${a.summary.body}` },
    ]);
    expect(items.filter((i) => i.id === 'demands').map((i) => i.lang)).toEqual(['en', 'prs']);
    expect(items.filter((i) => i.id === 'plan').map((i) => i.lang)).toEqual(['en', 'prs']);
    for (const id of ['urgency', 'footer']) expect(items.find((i) => i.id === id)?.lang).toBe('en');
    // Every Persian-script part is read with the Dari voice, never the English one.
    for (const i of items) if (/[\u0600-\u06FF]/.test(i.text) && i.id !== 'urgency') expect(i.lang).toBe('prs');
  });

  it('one item per card when the paper language is the UI pack (unchanged output)', () => {
    const a = base();
    const items = hearItItems(a, t, 'en', false);
    expect(items.every((i) => i.lang === 'en')).toBe(true);
    expect(items.filter((i) => i.id === 'summary')).toEqual([
      { id: 'summary', lang: 'en', text: `${t('card.what_is_this')}. ${a.summary.title}. ${a.summary.body}` },
    ]);
    expect(new Set(items.map((i) => i.id)).size).toBe(items.length);
  });

  it('fixed red-flag notices stay in the UI pack; model flags use target_language', () => {
    const a = JSON.parse(JSON.stringify(medicaidPrs)) as AnalysisResult;
    a.red_flags = [
      flag({ kind: 'injection_suspected', severity: 'high', text: 'ignored' }),
      flag({ kind: 'urgency_pressure', text: 'متن مدل' }),
    ];
    const flags = hearItItems(a, t, 'en', false).filter((i) => i.id === 'red_flags');
    expect(flags).toEqual([
      { id: 'red_flags', lang: 'en', text: `${t('card.red_flags')}. ${t('warning.injection_masked')}` },
      { id: 'red_flags', lang: 'prs', text: 'متن مدل' },
    ]);
  });

  it('reads an estimated urgency date as the banner shows it, never the raw ISO day (CL-080(d))', () => {
    const a = JSON.parse(JSON.stringify(insuranceEn)) as AnalysisResult;
    expect(a.urgency.headline_key).toBe('urgency.medium.estimated');
    expect(a.urgency.headline_params?.date).toBe('2026-10-17');
    const urgency = hearItItems(a, t, 'en', false).find((i) => i.id === 'urgency');
    expect(urgency?.text).toContain('October 17, 2026');
    expect(urgency?.text).not.toContain('2026-10-17');
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
