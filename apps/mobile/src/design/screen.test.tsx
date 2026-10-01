// Screen scaffold (PRODUCT_SPEC §5.7, COMPLIANCE_PRIVACY §5.2): the fixed header holds only back +
// the help link (which may wrap and never takes more than half the row), so at "Very large" / 200 %
// text a long title can no longer push the page content to zero height (the title is the first
// thing in the scroll body instead); the footer is capped at half the screen; the pack provenance
// banners appear on every screen, exactly once.

import { render } from '@testing-library/react-native';
import { PixelRatio, StyleSheet } from 'react-native';

import { Banner } from '@/design/components/Banner';
import { AppProviders } from '@/design/components/Providers';
import { Screen } from '@/design/components/Screen';
import { AppText } from '@/design/components/Text';
import type { LanguagePack } from '@/api/types';
import { EN_PACK, fromLanguagePack, t, useI18n } from '@/i18n/store';
import { useSession } from '@/store/session';
import { useSettings } from '@/store/settings';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), back: jest.fn(), replace: jest.fn(), canGoBack: () => true },
}));

const LONG_TITLE = 'Notice to Appear in immigration court on October 7, 2026';

function prs(overrides: Partial<LanguagePack> = {}) {
  return fromLanguagePack(
    {
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
      strings: {},
      fallback_keys: [],
      coverage: 1,
      machine_translated: true,
      reviewed_by: null,
      confidence: 'medium',
      generated_at: '2026-09-24T02:10:00Z',
      tts_tag: 'fa-AF',
      tts_fallback_tag: 'fa-IR',
      ...overrides,
    } as LanguagePack,
    'bundled',
  );
}

type Node = { parent: Node | null };

function isInside(node: Node, ancestor: Node): boolean {
  for (let n: Node | null = node; n; n = n.parent) if (n === ancestor) return true;
  return false;
}

afterEach(() => {
  useI18n.getState().setPack(EN_PACK);
  useSession.getState().setClerkMode(false);
  useSettings.getState().patch({ textSize: 'normal' });
  jest.restoreAllMocks();
});

describe('Screen header at large text', () => {
  it('keeps the title out of the fixed header (it scrolls with the page) at 200 % and "Very large"', async () => {
    jest.spyOn(PixelRatio, 'getFontScale').mockReturnValue(2);
    useSettings.getState().patch({ textSize: 'xl' });
    const { getByTestId, getByText } = await render(
      <AppProviders staticMetrics>
        <Screen back title={LONG_TITLE} footer={<AppText>Action bar</AppText>}>
          <AppText>Take a photo</AppText>
        </Screen>
      </AppProviders>,
    );
    const header = getByTestId('screen-header');
    const scroll = getByTestId('screen-scroll');
    const title = getByText(LONG_TITLE);
    expect(isInside(title, header)).toBe(false);
    expect(isInside(title, scroll)).toBe(true);
    expect(isInside(getByText('Take a photo'), scroll)).toBe(true);

    // The help link wraps inside at most half the row instead of squeezing everything else.
    const help = StyleSheet.flatten(getByTestId('screen-help-link').props.style);
    expect(help.flexShrink).toBe(1);
    expect(help.maxWidth).toBe('50%');
    // The fixed header has no height of its own and no text container is fixed-height.
    expect(StyleSheet.flatten(header.props.style).height).toBeUndefined();

    // The action bar never takes more than half the screen; it scrolls inside that half.
    const footer = getByTestId('screen-footer');
    expect(StyleSheet.flatten(footer.props.style).maxHeight).toBe('50%');
    expect(isInside(getByText('Action bar'), footer)).toBe(true);
  });

  it('renders no header bar when there is neither a back button nor the help link', async () => {
    const { queryByTestId, getByText } = await render(
      <AppProviders staticMetrics>
        <Screen hideHelpLink>
          <AppText>Emergency</AppText>
        </Screen>
      </AppProviders>,
    );
    expect(getByText('Emergency')).toBeTruthy();
    expect(queryByTestId('screen-header')).toBeNull();
  });
});

describe('pack provenance banners on every screen (COMPLIANCE_PRIVACY §5.2, D-25)', () => {
  it('shows the machine-translation banner on any screen while such a pack is active', async () => {
    useI18n.getState().setPack(prs());
    const { getAllByTestId, queryByTestId } = await render(
      <AppProviders staticMetrics>
        <Screen title="Home">
          <AppText>Tiles</AppText>
        </Screen>
      </AppProviders>,
    );
    expect(getAllByTestId('banner-machine_translation')).toHaveLength(1);
    expect(queryByTestId('banner-partial_pack')).toBeNull();
  });

  it('shows the partial-pack banner when some keys fell back to English', async () => {
    useI18n.getState().setPack(prs({ machine_translated: false, fallback_keys: ['home.title'] }));
    const { getAllByTestId, queryByTestId } = await render(
      <AppProviders staticMetrics>
        <Screen title="Help">
          <AppText>Help</AppText>
        </Screen>
      </AppProviders>,
    );
    expect(getAllByTestId('banner-partial_pack')).toHaveLength(1);
    expect(queryByTestId('banner-machine_translation')).toBeNull();
  });

  it('never shows the line twice when the screen renders it itself (S2 / S7)', async () => {
    useI18n.getState().setPack(prs({ fallback_keys: ['home.title'] }));
    const { getAllByTestId } = await render(
      <AppProviders staticMetrics>
        <Screen title="Result">
          <Banner kind="machine_translation" text={t('banner.machine_translated')} />
          <Banner kind="partial_pack" />
          {/* A different warning in the same colour is not the provenance line. */}
          <Banner kind="machine_translation" text={t('banner.degraded_model')} />
        </Screen>
      </AppProviders>,
    );
    expect(getAllByTestId('banner-machine_translation')).toHaveLength(2);
    expect(getAllByTestId('banner-partial_pack')).toHaveLength(1);
  });

  it('shows nothing for a reviewed, complete pack (English)', async () => {
    const { queryByTestId, getByText } = await render(
      <AppProviders staticMetrics>
        <Screen title="Home">
          <AppText>Tiles</AppText>
        </Screen>
      </AppProviders>,
    );
    expect(getByText('Tiles')).toBeTruthy();
    expect(queryByTestId('banner-machine_translation')).toBeNull();
    expect(queryByTestId('banner-partial_pack')).toBeNull();
  });

  it('shows neither the header nor the banner in clerk mode', async () => {
    useI18n.getState().setPack(prs());
    useSession.getState().setClerkMode(true);
    const { queryByTestId, getByText } = await render(
      <AppProviders staticMetrics>
        <Screen back>
          <AppText>Clerk card</AppText>
        </Screen>
      </AppProviders>,
    );
    expect(getByText('Clerk card')).toBeTruthy();
    expect(queryByTestId('banner-machine_translation')).toBeNull();
    expect(queryByTestId('screen-header')).toBeNull();
  });
});
