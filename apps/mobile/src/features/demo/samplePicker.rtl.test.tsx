// "Try a sample paper" sheet in an RTL pack: each row is mirrored (thumbnail at the start = right,
// chevron at the end = left and flipped), and on web the sheet pins `dir="ltr"` like `#root`
// (global.css) — the modal is portalled outside `#root`, where `<html dir="rtl">` would flip our
// `row-reverse` a second time and leave the rows unmirrored.

import { act, render } from '@testing-library/react-native';
import { Platform } from 'react-native';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { DemoFixture } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';
import { bootI18n } from '@/i18n/I18nProvider';
import { bundledPackFor, EN_PACK, useI18n } from '@/i18n/store';

import { resetSamplesCache } from './sampleCache';
import { SamplePickerSheet } from './SamplePicker';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

const BUNDLED: DemoFixture[] = [
  {
    id: 'medicaid_address_confirmation',
    kind: 'document',
    title_key: 'fixture.medicaid_address_confirmation',
    title_en: 'Medicaid address letter',
    pages: 1,
    thumbnail_url: '',
    available_target_languages: ['en'],
  } as unknown as DemoFixture,
];

// `@/api/offline` imports the synced `assets/fixtures` bundle, which jest cannot map (CL-033).
jest.mock('@/api/offline', () => ({
  listFixturesWithFallback: async () => ({ fixtures: BUNDLED, source: 'bundled' }),
  bundledFixtureThumbnail: () => 'bundled-thumb.png',
}));

function offlineClient(): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return new Proxy({ baseUrl: 'http://127.0.0.1:8031', fixturePageUrl: () => '' } as unknown as ApiClient, {
    get: (target, prop) => (prop in target ? target[prop as keyof ApiClient] : fail),
  });
}

function flat(style: unknown): Record<string, unknown> {
  return Object.assign({}, ...([style].flat(Infinity as 1).filter(Boolean) as object[]));
}

async function renderSheet() {
  return render(
    <AppProviders client={offlineClient()} staticMetrics>
      <SamplePickerSheet visible onClose={() => undefined} onPick={() => undefined} />
    </AppProviders>,
  );
}

describe('SamplePickerSheet direction', () => {
  const originalOS = Platform.OS;
  // The provider applies the saved language (English) once per session; do that first so the
  // pack set by the test stays active.
  beforeAll(() => bootI18n());
  beforeEach(() => resetSamplesCache());
  afterEach(async () => {
    Platform.OS = originalOS;
    await act(async () => {
      useI18n.getState().setPack(EN_PACK);
    });
  });

  it('mirrors the rows and the chevron in RTL; on web the sheet is pinned LTR like #root', async () => {
    const pack = bundledPackFor('prs');
    if (!pack) throw new Error('prs pack not bundled');
    useI18n.getState().setPack(pack);
    Platform.OS = 'web';
    const { findByTestId, getByTestId, toJSON } = await renderSheet();
    const row = await findByTestId('sample-medicaid_address_confirmation');
    expect(flat(row.props.style).flexDirection).toBe('row-reverse');
    expect(JSON.stringify(toJSON())).toContain('"scaleX":-1');
    expect(getByTestId('sample-picker-sheet-backdrop').props.dir).toBe('ltr');
  });

  it('keeps rows LTR in English and never sets a layout direction on native', async () => {
    Platform.OS = 'ios';
    const { findByTestId, getByTestId, toJSON } = await renderSheet();
    const row = await findByTestId('sample-medicaid_address_confirmation');
    expect(flat(row.props.style).flexDirection).toBe('row');
    expect(JSON.stringify(toJSON())).not.toContain('"scaleX":-1');
    expect(getByTestId('sample-picker-sheet-backdrop').props.dir).toBeUndefined();
  });
});
