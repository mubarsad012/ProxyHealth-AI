// POLISH items 4 and 5: bidi isolation of mixed-direction copy (D-26) and native names for
// resource-only language tags. Tested with the bundled prs pack and an RTL pseudo pack ("⟦rhg⟧ " +
// English, as the mock serves for a Tier 3 language).

import { render } from '@testing-library/react-native';
import { StyleSheet, Text } from 'react-native';

import type { LanguagePack } from '@/api/types';
import { Bidi } from '@/design/components/Bidi';
import { AppText } from '@/design/components/Text';
import { languagesLine } from '@/features/help/format';

import {
  FSI,
  firstStrongDirection,
  isolateForLayout,
  isolateTemplateForLayout,
  LRI,
  PDI,
  resolveAuto,
  RLI,
  stripIsolates,
  strongDirection,
} from './bidi';
import { EXTRA_LANGUAGE_NAMES } from './languageNames';
import { LANGUAGE_TAGS } from './languages';
import { bundledPackFor, EN_PACK, fromLanguagePack, languageInfoFor, t, translate, useI18n } from './store';
import { translateForLayout, useBidiText, useT } from './useT';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

function pseudoRtlPack() {
  const strings = Object.fromEntries(Object.entries(EN_PACK.strings).map(([k, v]) => [k, `⟦rhg⟧ ${v}`]));
  return fromLanguagePack(
    {
      language_tag: 'rhg', language_name_native: 'Rohingya', language_name_en: 'Rohingya', direction: 'rtl',
      script: 'Rohg', digit_system: 'western', font_hint: null, tier: 3, source: 'generated',
      pack_version: 'test', etag: 'test', strings, fallback_keys: [], coverage: 1, machine_translated: true,
      reviewed_by: null, confidence: 'low', generated_at: '2026-09-29T00:00:00Z', tts_tag: null,
      tts_fallback_tag: 'my-MM',
    } as LanguagePack,
    'generated',
  );
}

afterEach(() => useI18n.getState().setPack(EN_PACK));

describe('direction helpers', () => {
  it('classify strong characters (Latin, Arabic script, Hanifi Rohingya, CJK, digits)', () => {
    expect(strongDirection('Need help now?')).toBe('ltr');
    expect(strongDirection('کاغذ این را نمی\u200cگوید.')).toBe('rtl');
    expect(strongDirection('به 911 زنگ بزنید')).toBe('rtl');
    expect(strongDirection('کد SMS را بنویسید')).toBe('mixed');
    expect(strongDirection('𐴀𐴁')).toBe('rtl'); // Hanifi Rohingya
    expect(strongDirection('中文 ខ្មែរ')).toBe('ltr');
    expect(strongDirection('2026-10-14 · 12')).toBe('neutral');
  });

  it('first strong direction skips isolated content (FSI / dir="auto" semantics)', () => {
    expect(firstStrongDirection('“Pay by October 14.”')).toBe('ltr');
    expect(firstStrongDirection('12 — دری')).toBe('rtl');
    expect(firstStrongDirection(`${LRI}Inova${PDI} نامه`)).toBe('rtl');
    expect(firstStrongDirection('...')).toBeNull();
    expect(resolveAuto('...', 'rtl')).toBe('rtl');
  });

  it('isolates only strings that run against the layout', () => {
    expect(isolateForLayout('⟦rhg⟧ Need help now?', 'rtl')).toBe(`${FSI}⟦rhg⟧ Need help now?${PDI}`);
    expect(isolateForLayout('Adapting system environment to your language...', 'rtl')).toBe(
      `${FSI}Adapting system environment to your language...${PDI}`,
    );
    expect(isolateForLayout('کاغذ این را نمی\u200cگوید.', 'rtl')).toBe('کاغذ این را نمی\u200cگوید.');
    expect(isolateForLayout('کد SMS را بنویسید', 'rtl')).toBe('کد SMS را بنویسید');
    expect(isolateForLayout('Need help now?', 'ltr')).toBe('Need help now?');
    expect(isolateForLayout('«الورقة لا تذكر ذلك.»', 'ltr')).toBe(`${FSI}«الورقة لا تذكر ذلك.»${PDI}`);
    const once = isolateForLayout('Call 211.', 'rtl');
    expect(isolateForLayout(once, 'rtl')).toBe(once); // never double-wrapped
    expect(stripIsolates(once)).toBe('Call 211.');
  });
});

describe('useT in RTL packs', () => {
  it('prs: Dari strings come back unchanged', () => {
    const prs = bundledPackFor('prs')!;
    for (const key of ['home.need_help_now', 'langpack.adapting', 'chat.not_in_document', 'quicksheet.help']) {
      expect(translateForLayout(prs.strings, 'rtl', key)).toBe(translate(prs.strings, key));
    }
  });

  it('pseudo pack: all-LTR strings are FSI…PDI-wrapped; missing keys are not', () => {
    const pack = pseudoRtlPack();
    useI18n.getState().setPack(pack);
    expect(t('home.need_help_now')).toBe(`${FSI}⟦rhg⟧ ${EN_PACK.strings['home.need_help_now']}${PDI}`);
    expect(t('no.such.key')).toBe('no.such.key');
    expect(translateForLayout(pack.strings, 'ltr', 'home.need_help_now')).toBe(pack.strings['home.need_help_now']);
  });

  it('an all-LTR template stays isolated when an RTL variable is inserted (tts.fallback_offer)', () => {
    const pack = pseudoRtlPack();
    useI18n.getState().setPack(pack);
    const rhg = languageInfoFor('rhg').name_native; // Hanifi Rohingya script
    expect(t('tts.fallback_offer', { language: rhg, fallback: 'English' })).toBe(
      `${FSI}⟦rhg⟧ No ${rhg} voice on this phone. Hear it in English or English?${PDI}`,
    );
    // English fallback inside an RTL pack with a Dari name inserted (the Medicaid sample case).
    expect(translateForLayout({}, 'rtl', 'tts.fallback_offer', { language: 'دری', fallback: 'English' })).toBe(
      `${FSI}No دری voice on this phone. Hear it in English or English?${PDI}`,
    );
    // A template that starts with its RTL variable gets an explicit LRI (FSI would resolve RTL).
    expect(isolateTemplateForLayout('{name} voice', 'دری voice', 'rtl')).toBe(`${LRI}دری voice${PDI}`);
    // The Dari template with an English variable keeps the layout direction.
    const prs = bundledPackFor('prs')!;
    expect(translateForLayout(prs.strings, 'rtl', 'tts.fallback_offer', { language: rhg, fallback: 'English' })).toBe(
      translate(prs.strings, 'tts.fallback_offer', { language: rhg, fallback: 'English' }),
    );
    // Neutral templates fall back to the interpolated text; LTR layouts are untouched.
    expect(isolateTemplateForLayout('{count}', 'Seven', 'rtl')).toBe(`${FSI}Seven${PDI}`);
    expect(translateForLayout(pack.strings, 'ltr', 'tts.fallback_offer', { language: rhg, fallback: 'English' })).toBe(
      translate(pack.strings, 'tts.fallback_offer', { language: rhg, fallback: 'English' }),
    );
  });

  it('renders the isolated string inside the RTL paragraph', async () => {
    useI18n.getState().setPack(pseudoRtlPack());
    function Probe() {
      const tt = useT();
      const bt = useBidiText();
      return (
        <>
          <AppText>{tt('langpack.adapting')}</AppText>
          <AppText>{bt('Server text in English.')}</AppText>
        </>
      );
    }
    const { getByText } = await render(<Probe />);
    expect(getByText(`${FSI}⟦rhg⟧ ${EN_PACK.strings['langpack.adapting']}${PDI}`)).toBeTruthy();
    expect(getByText(`${FSI}Server text in English.${PDI}`)).toBeTruthy();
  });
});

describe('<Bidi dir="auto"> resolves the direction of plain text', () => {
  it('an English quote in a Dari layout is LTR-isolated with writingDirection ltr', async () => {
    useI18n.getState().setPack(bundledPackFor('prs')!);
    const { getByText } = await render(
      <Text>
        <Bidi dir="auto">“Pay by October 14.”</Bidi>
      </Text>,
    );
    const node = getByText(`${LRI}“Pay by October 14.”${PDI}`, { exact: false });
    expect(StyleSheet.flatten(node.props.style)).toMatchObject({ writingDirection: 'ltr' });
  });

  it('a Dari sender name is RTL-isolated; neutral text follows the layout', async () => {
    useI18n.getState().setPack(bundledPackFor('prs')!);
    const { getByText } = await render(
      <>
        <Bidi dir="auto" variant="body">
          اداره خدمات اجتماعی
        </Bidi>
        <Bidi dir="auto" variant="caption">
          12 · 34
        </Bidi>
      </>,
    );
    expect(getByText(`${RLI}اداره خدمات اجتماعی${PDI}`)).toBeTruthy();
    expect(getByText(`${RLI}12 · 34${PDI}`)).toBeTruthy();
  });
});

describe('language names for resource-only tags (item 4)', () => {
  it('zh, hmn and km have native and English names', () => {
    expect(languageInfoFor('zh')).toMatchObject({ name_native: '中文', name_en: 'Chinese', direction: 'ltr' });
    expect(languageInfoFor('hmn')).toMatchObject({ name_native: 'Hmoob', name_en: 'Hmong' });
    expect(languageInfoFor('km')).toMatchObject({ name_native: 'ខ្មែរ', name_en: 'Khmer' });
    expect(languageInfoFor('x-unknown').name_native).toBe('x-unknown');
  });

  it('the "Speaks:" line shows names, never raw tags', () => {
    const line = languagesLine(['en', 'es', 'zh', 'hmn', 'km'], (k, v) => translate(EN_PACK.strings, k, v));
    expect(line).toBe('Speaks: English, Español, 中文, Hmoob, ខ្មែរ');
  });

  it('names-only tags are never in the language grid seed', () => {
    for (const tag of Object.keys(EXTRA_LANGUAGE_NAMES)) expect(LANGUAGE_TAGS).not.toContain(tag);
  });
});
