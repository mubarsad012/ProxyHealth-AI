// Bidi isolation (D-26, PRODUCT_SPEC §5.2 rule 2): verbatim values keep their direction inside RTL
// text; digits are never localized or reversed; `{date}` in pack strings renders isolated.

import { render } from '@testing-library/react-native';
import { Text } from 'react-native';

import { Bidi, bidiWebProps, FSI, isolate, LRI, PDI, RLI, stripIsolates } from '@/design/components/Bidi';
import { Interpolated, splitTemplate } from '@/design/components/Interpolated';
import { fromLanguagePack, EN_PACK, useI18n } from '@/i18n/store';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

describe('isolate helpers', () => {
  it('wraps with LRI/RLI/FSI … PDI and strips them again', () => {
    expect(isolate('A-123-456-789')).toBe(`${LRI}A-123-456-789${PDI}`);
    expect(isolate('دری', 'rtl')).toBe(`${RLI}دری${PDI}`);
    expect(isolate('x', 'auto')).toBe(`${FSI}x${PDI}`);
    expect(stripIsolates(`Due ${LRI}October 14, 2026${PDI}.`)).toBe('Due October 14, 2026.');
  });

  it('web props carry dir + data-bidi (unicode-bidi: isolate via global.css)', () => {
    expect(bidiWebProps('ltr')).toEqual({ dir: 'ltr', 'data-bidi': 'ltr' });
  });
});

describe('<Bidi> on native', () => {
  it('isolates a plain value and keeps Western digits', async () => {
    const { getByText } = await render(
      <Text>
        <Bidi>(703) 555-0100</Bidi>
      </Text>,
    );
    expect(getByText(`${LRI}(703) 555-0100${PDI}`, { exact: false })).toBeTruthy();
  });

  it('isolates as a standalone styled text', async () => {
    const { getByText } = await render(<Bidi variant="body">$1,234.56</Bidi>);
    expect(getByText(`${LRI}$1,234.56${PDI}`)).toBeTruthy();
  });
});

describe('<Interpolated> keeps {date} LTR inside an RTL sentence', () => {
  it('splits the template around placeholders', () => {
    expect(splitTemplate('There is a date soon: {date}.', { date: 'October 14, 2026' })).toEqual([
      { kind: 'text', value: 'There is a date soon: ' },
      { kind: 'var', value: 'October 14, 2026', name: 'date' },
      { kind: 'text', value: '.' },
    ]);
  });

  it('renders the date isolated in an RTL pack', async () => {
    useI18n.getState().setPack(
      fromLanguagePack(
        {
          language_tag: 'ar',
          language_name_native: 'العربية',
          language_name_en: 'Arabic',
          direction: 'rtl',
          script: 'Arab',
          digit_system: 'eastern_arabic',
          font_hint: 'NotoNaskhArabic',
          tier: 1,
          source: 'bundled',
          pack_version: 'v',
          etag: 'e',
          strings: { 'urgency.high.date_soon': 'هناك تاريخ قريب: {date}.' },
          fallback_keys: [],
          coverage: 1,
          machine_translated: true,
          reviewed_by: null,
          confidence: 'medium',
          generated_at: '2026-09-24T00:00:00Z',
          tts_tag: 'ar-SA',
          tts_fallback_tag: null,
        } as never,
        'bundled',
      ),
    );
    const { getByText, unmount } = await render(
      <Interpolated template="هناك تاريخ قريب: {date}." vars={{ date: 'October 14, 2026' }} />,
    );
    // The printed English date stays verbatim (no digit localisation) inside isolate marks.
    expect(getByText(`${LRI}October 14, 2026${PDI}`, { exact: false })).toBeTruthy();
    await unmount();
    useI18n.getState().setPack(EN_PACK);
  });
});
