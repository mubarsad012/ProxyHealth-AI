// S5 offline (Phase 2B finding 3): "Save to read later" saves the pages to My papers as "Not read
// yet" through the vault's own sheet — nothing goes into an in-memory queue that nobody reads — and
// "I will read it when internet is back" really starts reading once the connection returns. When
// the pages cannot be kept (Keep page images off, Hide ID numbers on, hidden parts, a PDF) the
// save option is not offered and a fixed line says why.
// New copy keys (`review.read_later_saved`, `review.waiting_for_internet`,
// `review.read_later_needs_keep_pages`, `review.read_later_unavailable`) are asserted through t(),
// so these tests hold before and after the en.json merge step.

import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import { router } from 'expo-router';

import type { ApiClient } from '@/api/client';
import { AppProviders } from '@/design/components/Providers';
import { EN_PACK, t, useI18n } from '@/i18n/store';
import type { StoredDocument, StoredPageInput, Vault } from '@/storage/index';
import { type CapturedPage, useSession } from '@/store/session';
import { useSettings } from '@/store/settings';

import { readLaterBlock } from './readLater';
import { ReviewScreen } from './ReviewScreen';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
jest.mock('expo-router', () => ({
  router: { back: jest.fn(), replace: jest.fn(), push: jest.fn(), canGoBack: () => true },
  Stack: { Screen: () => null },
  useLocalSearchParams: () => ({}),
}));
jest.mock('@/lib/image', () => ({
  ...jest.requireActual('@/lib/image'),
  toJpegBase64: jest.fn(async () => ({ base64: 'SlBFRw==', width: 1200, height: 1600, byteLength: 4 })),
}));
jest.mock('@/api/offline', () => ({ bundledFixture: () => ({ pages: 1 }), bundledFixtureResult: () => null }));
// jest-expo's expo-crypto mock returns undefined ids; the read-later document needs a real one.
let mockSeq = 0;
jest.mock('expo-crypto', () => ({
  ...jest.requireActual('expo-crypto'),
  randomUUID: () => {
    mockSeq += 1;
    return `00000000-0000-4000-8000-${String(mockSeq).padStart(12, '0')}`;
  },
}));

// Reachability the test can flip: every mounted `useOnline()` re-renders on `setMockOnline`.
let mockOnline = false;
const mockListeners = new Set<() => void>();
function setMockOnline(v: boolean) {
  mockOnline = v;
  for (const l of mockListeners) l();
}
jest.mock('@/lib/network', () => {
  const React = jest.requireActual<typeof import('react')>('react');
  return {
    useOnline: () => {
      const [, force] = React.useReducer((x: number) => x + 1, 0);
      React.useEffect(() => {
        mockListeners.add(force);
        return () => {
          mockListeners.delete(force);
        };
      }, []);
      return { online: mockOnline, known: true };
    },
    isOnline: async () => mockOnline,
  };
});

const client = new Proxy({} as ApiClient, {
  get: (_t, prop) => (prop === 'baseUrl' ? 'http://127.0.0.1:8033' : () => Promise.reject(new Error('offline'))),
});

function recordingVault() {
  const saved: { doc: StoredDocument; pages: StoredPageInput[] }[] = [];
  const none = () => Promise.resolve();
  const vault = {
    init: none,
    members: { list: async () => [], add: jest.fn(), rename: none, remove: none },
    documents: {
      list: async () => [],
      get: async () => null,
      save: jest.fn(async (doc: StoredDocument, pages: StoredPageInput[]) => {
        saved.push({ doc, pages });
      }),
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
  return { vault, saved };
}

function page(id: string, patch: Partial<CapturedPage> = {}): CapturedPage {
  return { id, uri: `file:///${id}.jpg`, mimeType: 'image/jpeg', width: 1200, height: 1600, rotation: 0, masks: [], source: 'camera', ...patch };
}

async function renderReview(vault: Vault) {
  return render(
    <AppProviders client={client} vault={vault} staticMetrics>
      <ReviewScreen />
    </AppProviders>,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  mockOnline = false;
  useSession.getState().reset();
  useI18n.getState().setPack(EN_PACK);
  useSettings.setState({ keepPageImages: true, hideIdNumbers: false });
});

describe('readLaterBlock', () => {
  const ok = { sample: false, keepPageImages: true, hideIdNumbers: false };
  it('is offered only when the saved row will hold the pages', () => {
    expect(readLaterBlock([page('a')], ok)).toBe('none');
    expect(readLaterBlock([page('a')], { ...ok, keepPageImages: false })).toBe('keep_pages_off');
    expect(readLaterBlock([page('a')], { ...ok, hideIdNumbers: true })).toBe('unsupported');
    expect(readLaterBlock([page('a', { masks: [{ x0: 0, y0: 0, x1: 0.5, y1: 0.5 }] })], ok)).toBe('unsupported');
    expect(readLaterBlock([page('a', { mimeType: 'application/pdf' })], ok)).toBe('unsupported');
    expect(readLaterBlock([page('a')], { ...ok, sample: true })).toBe('unsupported');
    expect(readLaterBlock([], ok)).toBe('unsupported');
  });
});

describe('<ReviewScreen> offline', () => {
  it('"Save to read later" saves the pages to My papers as "Not read yet" (no memory queue)', async () => {
    const { vault, saved } = recordingVault();
    useSession.getState().setPages([page('a'), page('b')]);
    const screen = await renderReview(vault);
    expect(screen.queryByTestId('review-read')).toBeNull();
    await act(async () => {
      fireEvent.press(screen.getByTestId('review-read-later'));
    });
    await waitFor(() => expect(screen.getByTestId('save-to-vault-sheet')).toBeTruthy());
    expect(saved).toHaveLength(0); // nothing is written before the sheet's Save
    await act(async () => {
      fireEvent.press(screen.getByTestId('save-to-vault-confirm'));
    });
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0].doc.analysis).toBeNull();
    expect(saved[0].doc.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(saved[0].doc.keepPages).toBe(true);
    expect(saved[0].pages.map((p) => p.page)).toEqual([1, 2]);
    expect(useSession.getState().offlineQueue).toEqual([]);
    expect(screen.getByTestId('review-message')).toHaveTextContent(t('review.read_later_saved'));
    // The old promise ("I saved the photo. I will read it when internet is back.") is gone.
    expect(screen.queryByText(t('capture.offline_queue'))).toBeNull();
  });

  it('"I will read it when internet is back" waits here, then starts reading when online', async () => {
    const { vault } = recordingVault();
    useSession.getState().setPages([page('a')]);
    const screen = await renderReview(vault);
    await act(async () => {
      fireEvent.press(screen.getByTestId('review-wait'));
    });
    expect(screen.getByTestId('review-waiting')).toHaveTextContent(t('review.waiting_for_internet'));
    expect(router.push).not.toHaveBeenCalled();
    await act(async () => {
      setMockOnline(true);
    });
    await waitFor(() => expect(router.push).toHaveBeenCalledWith('/scan/reading'));
    expect(router.push).toHaveBeenCalledTimes(1);
  });

  it('Keep page images off → no save option; the fixed line points to Settings; wait is primary', async () => {
    useSettings.setState({ keepPageImages: false });
    const { vault } = recordingVault();
    useSession.getState().setPages([page('a')]);
    const screen = await renderReview(vault);
    expect(screen.queryByTestId('review-read-later')).toBeNull();
    expect(screen.getByTestId('review-wait')).toBeTruthy();
    expect(screen.getByTestId('review-read-later-note')).toHaveTextContent(t('review.read_later_needs_keep_pages'));
  });

  it('hidden parts → no save option (the stored copy would lose the boxes)', async () => {
    const { vault } = recordingVault();
    useSession.getState().setPages([page('a', { masks: [{ x0: 0.1, y0: 0.1, x1: 0.4, y1: 0.2 }] })]);
    const screen = await renderReview(vault);
    expect(screen.queryByTestId('review-read-later')).toBeNull();
    expect(screen.getByTestId('review-read-later-note')).toHaveTextContent(t('review.read_later_unavailable'));
  });

  it('a sample can still be read offline (bundled recorded result)', async () => {
    const { vault } = recordingVault();
    useSession.getState().setDemoSampleId('medicaid_address_confirmation');
    useSession.getState().setPages([page('s1', { source: 'sample' })]);
    const screen = await renderReview(vault);
    expect(screen.getByTestId('review-read')).toBeTruthy();
  });
});
