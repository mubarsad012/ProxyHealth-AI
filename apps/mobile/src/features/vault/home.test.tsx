// WP6 lane 6A Home (S3) checks: first run shows the 72 pt CTA, the tiles and the trust footer with
// no next-date card, and the CTA opens S2 while consent is missing; a switched-on reminder within
// 30 days shows the next-date card (`useNextDate`), a saved date without one does not; offline shows
// the banner and the offline line and disables the troubleshoot tile; with consent the native CTA
// opens the camera screen, and "Pick a photo or PDF" offers photos or one PDF.

import { act, fireEvent, render } from '@testing-library/react-native';
import { router } from 'expo-router';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import HomeScreen from '@/app/(tabs)/index';
import { AppProviders } from '@/design/components/Providers';
import { useConsentDecision } from '@/features/onboarding/consentState';
import { toIsoDay } from '@/features/reminders/schedule';
import type { DocumentRow, Reminder, StoredDocument, Vault } from '@/storage/index';
import type { CapturedPage } from '@/store/session';
import { useSession } from '@/store/session';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), back: jest.fn(), replace: jest.fn(), canGoBack: () => false },
  useLocalSearchParams: () => ({}),
}));

let mockOnline = true;
jest.mock('@/lib/network', () => ({
  useOnline: () => ({ online: mockOnline, known: true }),
  isOnline: async () => mockOnline,
}));

const mockPickPdf = jest.fn(async (_e?: unknown): Promise<CapturedPage | null> => null);
const mockPickLibrary = jest.fn(async (_e?: unknown): Promise<CapturedPage[]> => []);
jest.mock('@/features/scan', () => ({
  usePickImage: () => ({
    pickFromLibrary: (e?: unknown) => mockPickLibrary(e),
    pickPdf: (e?: unknown) => mockPickPdf(e),
    takePhoto: async () => [],
  }),
  pagesAfterPick: (current: unknown[], picked: unknown[]) => ({ kind: 'ok', pages: [...current, ...picked] }),
}));

// Native-only notification wiring is covered in reminders.test.ts with injected fakes.
jest.mock('@/features/reminders/useReminderTapRouting', () => ({ useReminderTapRouting: () => undefined }));

// `@/api/offline` imports the synced `assets/fixtures` bundle, which jest cannot map (CL-033).
jest.mock('@/api/offline', () => ({
  listFixturesWithFallback: async () => ({ fixtures: [], source: 'bundled' }),
  bundledFixtureThumbnail: () => null,
}));

function offlineClient(): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return new Proxy({ baseUrl: 'http://127.0.0.1:8028', fixturePageUrl: () => '' } as unknown as ApiClient, {
    get: (target, prop) => (prop in target ? target[prop as keyof ApiClient] : fail),
  });
}

function fakeVault(rows: DocumentRow[] = [], reminders: Reminder[] = [], docs: StoredDocument[] = []): Vault {
  const none = () => Promise.resolve();
  return {
    init: none,
    members: { list: async () => [], add: jest.fn(), rename: none, remove: none },
    documents: {
      list: async () => [...rows],
      get: async (id: string) => docs.find((d) => d.id === id) ?? null,
      save: jest.fn(),
      move: none,
      remove: none,
      search: async () => [],
    },
    pages: { list: async () => [], uri: async () => null },
    checklist: { get: async () => ({}), set: none },
    reminders: { list: async () => [...reminders], add: jest.fn(), remove: none, setEnabled: none },
    consent: { get: async () => null, set: none, clear: none },
    wipeAll: none,
  } as unknown as Vault;
}

function inDays(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return toIsoDay(d);
}

async function renderHome(vault: Vault) {
  return render(
    <AppProviders client={offlineClient()} vault={vault} staticMetrics>
      <HomeScreen />
    </AppProviders>,
  );
}

function acceptConsent() {
  useConsentDecision.getState().set('accepted');
  useSession.getState().setConsent({
    consent_version: '2026-10-01',
    accepted_at: '2026-09-28T12:00:00.000Z',
    tier_seen: 'demo',
    platform: 'ios',
  });
}

beforeEach(() => {
  mockOnline = true;
  mockPickPdf.mockClear();
  mockPickLibrary.mockClear();
  jest.mocked(router.push).mockClear();
  useConsentDecision.getState().set('none');
  useSession.getState().setConsent(null);
});

describe('S3 Home', () => {
  it('first run: CTA, tiles, trust footer, no next-date card; the CTA opens consent', async () => {
    const { findByText, getByText, getByTestId, queryByTestId, queryByText } = await renderHome(fakeVault());
    expect(await findByText('Take a photo of a paper')).toBeTruthy();
    expect(getByText('Pick a photo or PDF')).toBeTruthy();
    expect(getByText('Stuck on a website?')).toBeTruthy();
    expect(getByText('Show the clerk')).toBeTruthy();
    // jest-expo runs as iOS: the D-22 interim line until iCloud-backup exclusion (COMPLIANCE_PRIVACY §10.2).
    expect(
      getByText(
        "Our server does not keep your paper. Papers you save stay on this phone, protected by your phone's own encryption. Turn on a phone passcode.",
      ),
    ).toBeTruthy();
    expect(queryByText(/stay only on this phone/)).toBeNull();
    expect(getByText('Scanning is off until you accept how your paper is handled. Tap to read it.')).toBeTruthy();
    expect(queryByTestId('home-next-date')).toBeNull();
    await act(async () => {
      fireEvent.press(getByTestId('home-scan-cta'));
    });
    expect(router.push).toHaveBeenCalledWith('/onboarding/consent');
  });

  it('returning: shows the next-date card for a switched-on reminder within 30 days', async () => {
    const row: DocumentRow = {
      id: 'an_medicaid',
      memberId: 'me',
      title: 'Medicaid letter',
      category: 'benefits',
      documentType: 'medicaid_renewal',
      createdAt: '2026-09-28T12:00:00.000Z',
      nextDateIso: inDays(5),
      pageCount: 1,
    };
    const doc = {
      id: 'an_medicaid',
      title: 'Medicaid letter',
      analysis: { demands: [{ id: 'd1', date: { value_iso: inDays(5) } }] },
    } as unknown as StoredDocument;
    const reminder: Reminder = {
      id: 'r1',
      documentId: 'an_medicaid',
      demandId: 'd1',
      fireAt: new Date(Date.now() + 2 * 86_400_000).toISOString(),
      notificationId: null,
      detailOptIn: false,
      enabled: true,
      label: 'Confirm your address',
    };
    const { findByTestId } = await renderHome(fakeVault([row], [reminder], [doc]));
    const card = await findByTestId('home-next-date');
    expect(card.props.accessibilityLabel).toContain('Medicaid letter');
    await act(async () => {
      fireEvent.press(card);
    });
    expect(router.push).toHaveBeenCalledWith('/reminders?doc=an_medicaid');
  });

  it('a saved date with no reminder shows no next-date card', async () => {
    const row: DocumentRow = {
      id: 'an_plain',
      memberId: 'me',
      title: 'Plain letter',
      category: 'benefits',
      documentType: 'medicaid_renewal',
      createdAt: '2026-09-28T12:00:00.000Z',
      nextDateIso: inDays(5),
      pageCount: 1,
    };
    const { findByText, queryByTestId } = await renderHome(fakeVault([row]));
    expect(await findByText('Take a photo of a paper')).toBeTruthy();
    expect(queryByTestId('home-next-date')).toBeNull();
  });

  it('ignores saved dates more than 30 days away', async () => {
    const row: DocumentRow = {
      id: 'an_far',
      memberId: 'me',
      title: 'Far away letter',
      category: 'benefits',
      documentType: 'medicaid_renewal',
      createdAt: '2026-09-28T12:00:00.000Z',
      nextDateIso: inDays(45),
      pageCount: 1,
    };
    const { findByText, queryByTestId } = await renderHome(fakeVault([row]));
    expect(await findByText('Take a photo of a paper')).toBeTruthy();
    expect(queryByTestId('home-next-date')).toBeNull();
  });

  it('offline: banner and offline line; troubleshoot is disabled', async () => {
    mockOnline = false;
    const { findByText, getByText, getByTestId } = await renderHome(fakeVault());
    expect(await findByText('No internet. Saved papers, quick sheets and reminders still work.')).toBeTruthy();
    expect(getByText('No internet. I can take the photo now and read it later.')).toBeTruthy();
    await act(async () => {
      fireEvent.press(getByTestId('home-tile-troubleshoot'));
    });
    expect(router.push).not.toHaveBeenCalledWith('/troubleshoot');
  });

  it('quota cooling (CL-039 field): the CTA stays tappable and says when to try again', async () => {
    const until = new Date(Date.now() + 10 * 60_000).toISOString();
    useSession.setState({ quotaCoolingUntil: until } as never);
    try {
      const { findByTestId } = await renderHome(fakeVault());
      const cta = await findByTestId('home-scan-cta');
      expect(cta.props.accessibilityLabel).toContain('The helper is busy. Try again at');
      await act(async () => {
        fireEvent.press(cta);
      });
      expect(router.push).toHaveBeenCalledWith('/onboarding/consent');
    } finally {
      await act(async () => {
        useSession.setState({ quotaCoolingUntil: null } as never);
      });
    }
  });

  it('with consent the native CTA opens the camera screen', async () => {
    acceptConsent();
    const { findByTestId } = await renderHome(fakeVault());
    await act(async () => {
      fireEvent.press(await findByTestId('home-scan-cta'));
    });
    expect(router.push).toHaveBeenCalledWith('/scan/capture');
  });
  it('"Pick a photo or PDF" offers photos or one PDF; a picked PDF opens the review screen', async () => {
    acceptConsent();
    const pdf: CapturedPage = {
      id: 'pg_pdf',
      uri: 'file:///letter.pdf',
      mimeType: 'application/pdf',
      rotation: 0,
      masks: [],
      source: 'pdf',
      byteLength: 1000,
    };
    mockPickPdf.mockResolvedValueOnce(pdf);
    const { findByTestId, getByText } = await renderHome(fakeVault());
    await act(async () => {
      fireEvent.press(await findByTestId('home-tile-pick'));
    });
    expect(getByText('Pick from photos')).toBeTruthy();
    await act(async () => {
      fireEvent.press(await findByTestId('home-pick-pdf'));
    });
    expect(mockPickPdf).toHaveBeenCalledTimes(1);
    expect(mockPickLibrary).not.toHaveBeenCalled();
    expect(useSession.getState().pages.map((p) => p.id)).toEqual(['pg_pdf']);
    expect(router.push).toHaveBeenCalledWith('/scan/review');
  });
});
