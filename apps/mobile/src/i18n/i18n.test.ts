// i18n runtime (BUILD_PLAN §5.5 step 4, ARCHITECTURE §3 tests): t() fallback + placeholders + the
// one-time missing-key report, direction derivation (row-reverse, native restart), digits as an
// additional line only, device-locale matching, the pack loader chain (bundled → cache → 304).

import { act, render } from '@testing-library/react-native';
import { createElement } from 'react';
import { I18nManager, Platform } from 'react-native';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { LanguagePack } from '@/api/types';
import { localizedDateLine, toLocalizedDigits } from '@/i18n/digits';
import { applyDirection, directionInfo, resetDirectionForTests } from '@/i18n/direction';
import { fontFamilyFor, lineHeightFor } from '@/i18n/fonts';
import { bootI18n, DirectionProvider, I18nProvider, resetI18nBootForTests } from '@/i18n/I18nProvider';
import { matchTagForLocale } from '@/i18n/locale';
import { cachePack, loadKnownPack, readCachedPack } from '@/i18n/packLoader';
import {
  BASE_STRINGS,
  EN_PACK,
  fromLanguagePack,
  interpolate,
  keyExists,
  missingKeysSoFar,
  onMissingKey,
  t,
  translate,
  useI18n,
} from '@/i18n/store';
import * as Speech from 'expo-speech';

import { chosenVoiceFor, resetVoicesForTests } from '@/lib/tts';
import { kv } from '@/storage/kv';
import { useSettings } from '@/store/settings';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

function prsPack(overrides: Partial<LanguagePack> = {}): LanguagePack {
  return {
    language_tag: 'prs',
    language_name_native: 'دری',
    language_name_en: 'Dari',
    direction: 'rtl',
    script: 'Arab',
    digit_system: 'persian',
    font_hint: 'NotoNaskhArabic',
    tier: 2,
    source: 'bundled',
    pack_version: 'base-1',
    etag: 'etag-1',
    strings: { 'app.name': 'پراکسی هلث', 'lang.title': 'کدام زبان؟' },
    fallback_keys: [],
    coverage: 1,
    machine_translated: true,
    reviewed_by: null,
    confidence: 'medium',
    generated_at: '2026-09-24T02:10:00Z',
    tts_tag: 'fa-AF',
    tts_fallback_tag: 'fa-IR',
    ...overrides,
  } as LanguagePack;
}

describe('t() and translate()', () => {
  afterEach(() => useI18n.getState().setPack(EN_PACK));

  it('uses the English base pack by default', () => {
    expect(t('app.name')).toBe('ProxyHealth AI');
    expect(t('langpack.adapting')).toBe('Adapting system environment to your language...');
  });

  it('fills placeholders and leaves unknown ones visible', () => {
    expect(t('urgency.days_until', { days: 20 })).toBe('In 20 days');
    expect(interpolate('Hi {name} {missing}', { name: 'A' })).toBe('Hi A {missing}');
  });

  it('falls back to English for keys the pack lacks', () => {
    useI18n.getState().setPack(fromLanguagePack(prsPack(), 'bundled'));
    expect(t('lang.title')).toBe('کدام زبان؟');
    expect(t('btn.continue')).toBe(BASE_STRINGS['btn.continue']);
  });

  it('returns the key and reports a missing key only once', () => {
    const seen: string[] = [];
    onMissingKey((k) => seen.push(k));
    expect(translate({}, 'nope.never_defined')).toBe('nope.never_defined');
    translate({}, 'nope.never_defined');
    expect(seen).toEqual(['nope.never_defined']);
    expect(missingKeysSoFar()).toContain('nope.never_defined');
    expect(keyExists('nope.never_defined')).toBe(false);
    expect(keyExists('err.network')).toBe(true);
    onMissingKey(null);
  });
});

describe('direction', () => {
  const originalOS = Platform.OS;
  const manager = I18nManager as { isRTL: boolean };
  const originalIsRTL = manager.isRTL;
  beforeEach(() => resetDirectionForTests());
  afterEach(() => {
    Platform.OS = originalOS;
    manager.isRTL = originalIsRTL;
    resetDirectionForTests();
    useI18n.getState().setRestartPending(false);
  });

  it('flips rows with row-reverse when the layout engine is LTR', () => {
    expect(directionInfo('rtl', false)).toEqual({
      isRTL: true,
      row: 'row-reverse',
      textAlign: 'right',
      writingDirection: 'rtl',
      dir: 'rtl',
      alignStart: 'flex-end',
      alignEnd: 'flex-start',
    });
    expect(directionInfo('ltr', false).row).toBe('row');
  });

  it('does not double-flip once native I18nManager is already RTL', () => {
    expect(directionInfo('rtl', true).row).toBe('row');
    expect(directionInfo('ltr', true).row).toBe('row-reverse');
    // RN swaps left/right itself in an RTL layout, so textAlign follows the same rule as row.
    expect(directionInfo('rtl', true).textAlign).toBe('left');
    expect(directionInfo('ltr', true).textAlign).toBe('right');
    expect(directionInfo('ltr', false).textAlign).toBe('left');
    expect(directionInfo('rtl', true).writingDirection).toBe('rtl');
    expect(directionInfo('ltr', true).writingDirection).toBe('ltr');
  });

  it('native: re-forces RTL after a transient LTR call in the same session', () => {
    Platform.OS = 'ios';
    manager.isRTL = true;
    const allow = jest.spyOn(I18nManager, 'allowRTL').mockImplementation(() => undefined);
    const force = jest.spyOn(I18nManager, 'forceRTL').mockImplementation(() => undefined);
    try {
      expect(applyDirection('ltr', 'en')).toBe(true);
      expect(applyDirection('rtl', 'ar')).toBe(false);
      expect(force.mock.calls).toEqual([[false], [true]]);
      expect(useI18n.getState().restartPending).toBe(false);
      applyDirection('rtl', 'ar');
      expect(force).toHaveBeenCalledTimes(2);
    } finally {
      allow.mockRestore();
      force.mockRestore();
    }
  });

  it('native relaunch in Arabic keeps RTL for the next start (no LTR from the placeholder pack)', async () => {
    Platform.OS = 'ios';
    manager.isRTL = true;
    const allow = jest.spyOn(I18nManager, 'allowRTL').mockImplementation(() => undefined);
    const force = jest.spyOn(I18nManager, 'forceRTL').mockImplementation(() => undefined);
    resetI18nBootForTests();
    useI18n.setState({ pack: EN_PACK, tag: 'en', ready: false, restartPending: false });
    useSettings.setState({ languageTag: 'ar', languageDecided: true, hydrated: true });
    try {
      const inner = createElement(DirectionProvider, null, null);
      const { unmount } = await render(createElement(I18nProvider, null, inner));
      await act(async () => {
        await bootI18n();
      });
      expect(useI18n.getState().tag).toBe('ar');
      expect(force.mock.calls.filter(([v]) => v === false)).toEqual([]);
      expect(useI18n.getState().restartPending).toBe(false);
      await unmount();
    } finally {
      allow.mockRestore();
      force.mockRestore();
      resetI18nBootForTests();
      useSettings.getState().resetSettings();
      useI18n.setState({ pack: EN_PACK, tag: 'en', ready: false, restartPending: false });
    }
  });

  it('native: switching to RTL calls forceRTL and flags the restart prompt', () => {
    Platform.OS = 'ios';
    const allow = jest.spyOn(I18nManager, 'allowRTL').mockImplementation(() => undefined);
    const force = jest.spyOn(I18nManager, 'forceRTL').mockImplementation(() => undefined);
    const pending = applyDirection('rtl', 'prs');
    expect(allow).toHaveBeenCalledWith(true);
    expect(force).toHaveBeenCalledWith(true);
    expect(pending).toBe(I18nManager.isRTL !== true);
    expect(useI18n.getState().restartPending).toBe(pending);
    allow.mockRestore();
    force.mockRestore();
  });

  it('web: sets <html dir lang> and never asks for a restart', () => {
    Platform.OS = 'web';
    const attrs: Record<string, string> = {};
    const g = globalThis as { document?: unknown };
    const hadDocument = 'document' in g;
    const previous = g.document;
    g.document = { documentElement: { setAttribute: (k: string, v: string) => (attrs[k] = v) } };
    try {
      expect(applyDirection('rtl', 'prs')).toBe(false);
      expect(attrs).toEqual({ dir: 'rtl', lang: 'prs' });
      applyDirection('ltr', 'en');
      expect(attrs).toEqual({ dir: 'ltr', lang: 'en' });
    } finally {
      if (hadDocument) g.document = previous;
      else delete g.document;
    }
  });
});

describe('digits and fonts', () => {
  it('adds a Persian-digit date line without touching the verbatim value', () => {
    expect(localizedDateLine('2026-10-14', 'persian')).toBe('۱۴/۱۰/۲۰۲۶');
    expect(localizedDateLine('2026-10-14', 'persian', 'mdy')).toBe('۱۰/۱۴/۲۰۲۶');
    expect(localizedDateLine('2026-10-14', 'western')).toBeNull();
    expect(localizedDateLine('October 14', 'persian')).toBeNull();
    expect(toLocalizedDigits('A-123', 'eastern_arabic')).toBe('A-١٢٣');
  });

  it('maps font hints to the bundled families (Nastaliq line height 2.0)', () => {
    expect(fontFamilyFor('NotoNaskhArabic')).toBe('NotoNaskhArabic-Regular');
    expect(fontFamilyFor('NotoSans', 'bold')).toBe('NotoSans-Bold');
    expect(fontFamilyFor(null)).toBeUndefined();
    expect(lineHeightFor('NotoNastaliqUrdu', 26)).toBe(52);
  });
});

describe('device locale matching', () => {
  it('matches exact, alias, script and bare language tags', () => {
    expect(matchTagForLocale('es-MX')).toBe('es');
    expect(matchTagForLocale('fa-AF')).toBe('prs');
    expect(matchTagForLocale('zh-TW')).toBe('zh-Hant');
    expect(matchTagForLocale('zh-CN')).toBe('zh-Hans');
    expect(matchTagForLocale('pt-PT')).toBe('pt-BR');
    expect(matchTagForLocale('xx-YY')).toBeNull();
  });
});

describe('pack loader', () => {
  function client(getPack: ApiClient['getPack'], postPack?: ApiClient['postPack']): ApiClient {
    return { getPack, postPack: postPack ?? jest.fn() } as unknown as ApiClient;
  }

  beforeEach(async () => {
    await kv.clearAll();
  });

  it('serves English without the network', async () => {
    const getPack = jest.fn();
    const pack = await loadKnownPack('en', { client: client(getPack), basePackVersion: () => null });
    expect(pack).toBe(EN_PACK);
    expect(getPack).not.toHaveBeenCalled();
  });

  it('revalidates a cached pack with its ETag and keeps it on 304', async () => {
    await cachePack(fromLanguagePack(prsPack({ language_tag: 'x-test-ps' }), 'server'));
    const getPack = jest.fn(async () => ({ pack: null, status: 304 as const, etag: 'etag-1' }));
    const pack = await loadKnownPack('x-test-ps', { client: client(getPack), basePackVersion: () => 'base-1' });
    expect(getPack).toHaveBeenCalledWith('x-test-ps', { etag: 'etag-1', packVersion: 'base-1' });
    expect(pack.origin).toBe('cache');
    expect(pack.strings['lang.title']).toBe('کدام زبان؟');
  });

  it('falls back to the cached copy when offline', async () => {
    await cachePack(fromLanguagePack(prsPack({ language_tag: 'x-test-ur' }), 'server'));
    const getPack = jest.fn(async () => {
      throw new ApiError({ code: 'network', status: 0 });
    });
    const pack = await loadKnownPack('x-test-ur', { client: client(getPack), basePackVersion: () => 'base-2' });
    expect(pack.tag).toBe('x-test-ur');
  });

  it('POSTs for a tag the server has not generated (404 → generate)', async () => {
    const getPack = jest.fn(async () => {
      throw new ApiError({ code: 'not_found', status: 404 });
    });
    const postPack = jest.fn(async () => prsPack({ language_tag: 'rhg', source: 'generated', direction: 'rtl' }));
    const pack = await loadKnownPack('rhg', { client: client(getPack, postPack), basePackVersion: () => 'base-1' });
    expect(postPack).toHaveBeenCalledWith({ language_query: 'rhg', pack_version: 'base-1', hint_tag: 'rhg' }, {});
    expect(pack.origin).toBe('generated');
    expect((await readCachedPack('rhg'))?.tag).toBe('rhg');
  });

  it('drops a corrupted cache entry silently', async () => {
    await kv.set('ph:pack:x-test-vi', '{not json');
    expect(await readCachedPack('x-test-vi')).toBeNull();
    expect(await kv.get('ph:pack:x-test-vi')).toBeNull();
  });
});

describe('tts voice choice', () => {
  const voices = [
    { identifier: 'samantha', name: 'Samantha', language: 'en-US', quality: Speech.VoiceQuality.Default },
    { identifier: 'maged', name: 'Maged', language: 'ar-SA', quality: Speech.VoiceQuality.Default },
  ];

  beforeEach(() => {
    resetVoicesForTests();
    jest.spyOn(Speech, 'getAvailableVoicesAsync').mockResolvedValue(voices);
  });

  afterEach(() => {
    jest.restoreAllMocks();
    resetVoicesForTests();
  });

  it('keeps the chosen voice for its own language', async () => {
    expect(await chosenVoiceFor('samantha', 'en-US')).toBe('samantha');
  });

  it('ignores a voice chosen for another language after a language switch', async () => {
    expect(await chosenVoiceFor('samantha', 'ar-SA')).toBeNull();
  });

  it('ignores an unknown or empty voice id', async () => {
    expect(await chosenVoiceFor('gone', 'en-US')).toBeNull();
    expect(await chosenVoiceFor(null, 'en-US')).toBeNull();
  });
});
