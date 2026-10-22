// Web Home (S3): `banner.web_session_only` ("This paper is kept only while this tab is open…") shows
// only when there is a paper in the tab — a saved one, or an open unsaved real one. A fresh tab with
// no papers, an open sample, or keeping switched on shows no such line (CAC verifier, 2026-10-22).

import { render } from '@testing-library/react-native';
import type { ComponentType } from 'react';
import { Platform } from 'react-native';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { AnalysisResult } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';
import type { DocumentRow, Vault } from '@/storage/index';
import { useSession } from '@/store/session';
import { useSettings } from '@/store/settings';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), back: jest.fn(), replace: jest.fn(), canGoBack: () => false },
  useLocalSearchParams: () => ({}),
}));

jest.mock('@/lib/network', () => ({
  useOnline: () => ({ online: true, known: true }),
  isOnline: async () => true,
}));

jest.mock('@/features/scan', () => ({
  usePickImage: () => ({
    pickFromLibrary: async () => [],
    pickPdf: async () => null,
    takePhoto: async () => [],
  }),
  pagesAfterPick: (current: unknown[], picked: unknown[]) => ({ kind: 'ok', pages: [...current, ...picked] }),
}));

jest.mock('@/features/reminders/useReminderTapRouting', () => ({ useReminderTapRouting: () => undefined }));

jest.mock('@/api/offline', () => ({
  listFixturesWithFallback: async () => ({ fixtures: [], source: 'bundled' }),
  bundledFixtureThumbnail: () => null,
}));

const SESSION_ONLY = 'This paper is kept only while this tab is open. To keep it, turn on keeping in Settings.';
const originalOS = Platform.OS;
let HomeScreen: ComponentType;

function offlineClient(): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return new Proxy({ baseUrl: 'http://127.0.0.1:8028', fixturePageUrl: () => '' } as unknown as ApiClient, {
    get: (target, prop) => (prop in target ? target[prop as keyof ApiClient] : fail),
  });
}

function fakeVault(rows: DocumentRow[] = []): Vault {
  const none = () => Promise.resolve();
  return {
    init: none,
    members: { list: async () => [], add: jest.fn(), rename: none, remove: none },
    documents: {
      list: async () => [...rows],
      get: async () => null,
      save: jest.fn(),
      move: none,
      remove: none,
      search: async () => [],
    },
    pages: { list: async () => [], uri: async () => null },
    checklist: { get: async () => ({}), set: none },
    reminders: { list: async () => [], add: jest.fn(), remove: none, setEnabled: none },
    consent: { get: async () => null, set: none, clear: none },
    wipeAll: none,
  } as unknown as Vault;
}

const saved: DocumentRow = {
  id: 'an_saved',
  memberId: 'me',
  title: 'Saved letter',
  category: 'benefits',
  documentType: 'medicaid_renewal',
  createdAt: '2026-10-20T12:00:00.000Z',
  nextDateIso: null,
  pageCount: 1,
};

async function renderHome(rows: DocumentRow[] = []) {
  return render(
    <AppProviders client={offlineClient()} vault={fakeVault(rows)} staticMetrics>
      <HomeScreen />
    </AppProviders>,
  );
}

beforeAll(() => {
  // Home reads `Platform.OS` once at module load, so switch to web before requiring it.
  Platform.OS = 'web';
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  HomeScreen = require('@/app/(tabs)/index').default as ComponentType;
});

afterAll(() => {
  Platform.OS = originalOS;
});

beforeEach(() => {
  useSettings.setState({ webPersist: 'session' });
  useSession.getState().setCurrentAnalysis(null);
  useSession.getState().setDemoSampleId(null);
});

describe('S3 Home on web: the session-only line needs a paper', () => {
  it('a fresh tab with no papers shows no session-only line', async () => {
    const { findByText, queryByText } = await renderHome();
    expect(await findByText('Take a photo of a paper')).toBeTruthy();
    expect(queryByText(SESSION_ONLY)).toBeNull();
  });

  it('a saved paper kept in tab memory shows the line', async () => {
    const { findByText } = await renderHome([saved]);
    expect(await findByText(SESSION_ONLY)).toBeTruthy();
  });

  it('an open unsaved real paper shows the line; an open sample does not', async () => {
    useSession.getState().setCurrentAnalysis({ analysis_id: 'an_sample' } as unknown as AnalysisResult);
    useSession.getState().setDemoSampleId('medicaid_address_confirmation');
    const sample = await renderHome();
    expect(await sample.findByText('Take a photo of a paper')).toBeTruthy();
    expect(sample.queryByText(SESSION_ONLY)).toBeNull();
    await sample.unmount();

    useSession.getState().setDemoSampleId(null);
    const real = await renderHome();
    expect(await real.findByText(SESSION_ONLY)).toBeTruthy();
  });

  it('with keeping switched on a saved paper shows no session-only line', async () => {
    useSettings.setState({ webPersist: 'indexeddb' });
    const { findByText, queryByText } = await renderHome([saved]);
    expect(await findByText('Take a photo of a paper')).toBeTruthy();
    expect(queryByText(SESSION_ONLY)).toBeNull();
  });
});
