// S5 Review pages (PRODUCT_SPEC S5): per-page actions, reorder in document order (controls appear
// only once their pack keys exist — CL-043 — so a raw key is never shown), sample mode hides the
// editing controls and shows the sample banner, and the primary CTA carries the page-count hint.

import { act, fireEvent, render } from '@testing-library/react-native';

import type { ApiClient } from '@/api/client';
import { AppProviders } from '@/design/components/Providers';
import { EN_PACK, t, useI18n } from '@/i18n/store';
import { type CapturedPage, useSession } from '@/store/session';

import { reorderAvailable, REORDER_KEYS, ReviewScreen } from './ReviewScreen';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

let mockParams: Record<string, string> = {};
jest.mock('expo-router', () => ({
  router: { back: jest.fn(), replace: jest.fn(), push: jest.fn(), canGoBack: () => true },
  Stack: { Screen: () => null },
  useLocalSearchParams: () => mockParams,
}));

jest.mock('@/lib/network', () => ({ useOnline: () => ({ online: true, known: true }), isOnline: async () => true }));

jest.mock('@/api/offline', () => ({ bundledFixture: () => ({ pages: 1 }), bundledFixtureResult: () => null }));

const client = new Proxy({} as ApiClient, {
  get: (_t, prop) => {
    if (prop === 'fixturePageUrl') return (id: string, n: number) => `http://127.0.0.1:8027/v1/demo/fixtures/${id}/pages/${n}`;
    if (prop === 'baseUrl') return 'http://127.0.0.1:8027';
    return () => Promise.reject(new Error('offline'));
  },
});

function page(id: string): CapturedPage {
  return { id, uri: `file:///${id}.jpg`, mimeType: 'image/jpeg', width: 1200, height: 1600, rotation: 0, masks: [], source: 'camera' };
}

async function renderReview() {
  return render(
    <AppProviders client={client} staticMetrics>
      <ReviewScreen />
    </AppProviders>,
  );
}

beforeEach(() => {
  mockParams = {};
  useSession.getState().reset();
  useI18n.getState().setPack(EN_PACK);
});

describe('<ReviewScreen>', () => {
  it('shows each page with its actions, removes a page and hints the page count on the CTA', async () => {
    useSession.getState().setPages([page('a'), page('b')]);
    const screen = await renderReview();
    expect(screen.getByTestId('review-page-1')).toBeTruthy();
    expect(screen.getByTestId('review-page-2')).toBeTruthy();
    expect(screen.getByTestId('review-read').props.accessibilityHint).toBe(t('review.read_hint', { n: 2 }));
    await act(async () => {
      fireEvent.press(screen.getAllByLabelText(t('review.remove'))[1]);
    });
    expect(useSession.getState().pages.map((p) => p.id)).toEqual(['a']);
    // Native: no canvas, so no blur hint is ever claimed.
    expect(screen.queryByTestId('review-blur-1')).toBeNull();
  });

  it('reorder controls stay hidden until their keys exist, then move pages in document order', async () => {
    useSession.getState().setPages([page('a'), page('b'), page('c')]);
    const hidden = await renderReview();
    if (!reorderAvailable()) {
      expect(hidden.queryByLabelText('Move up')).toBeNull();
      expect(hidden.queryByText(REORDER_KEYS.up)).toBeNull();
    }
    await hidden.unmount();

    useI18n.getState().setPack({ ...EN_PACK, strings: { ...EN_PACK.strings, [REORDER_KEYS.up]: 'Move up', [REORDER_KEYS.down]: 'Move down' } });
    expect(reorderAvailable()).toBe(true);
    const screen = await renderReview();
    // First page: only "Move down"; last page: only "Move up".
    expect(screen.getAllByLabelText('Move up')).toHaveLength(2);
    expect(screen.getAllByLabelText('Move down')).toHaveLength(2);
    await act(async () => {
      fireEvent.press(screen.getAllByLabelText('Move down')[0]);
    });
    expect(useSession.getState().pages.map((p) => p.id)).toEqual(['b', 'a', 'c']);
    await act(async () => {
      fireEvent(screen.getByTestId('review-page-3'), 'accessibilityAction', { nativeEvent: { actionName: 'moveUp' } });
    });
    expect(useSession.getState().pages.map((p) => p.id)).toEqual(['b', 'c', 'a']);
  });

  it('sample paper: banner, fixture pages from the API, no editing controls', async () => {
    mockParams = { sample: 'medicaid_address_confirmation' };
    const screen = await renderReview();
    expect(screen.getByText(t('banner.demo_sample'))).toBeTruthy();
    const s = useSession.getState();
    expect(s.demoSampleId).toBe('medicaid_address_confirmation');
    expect(s.pages[0].uri).toBe('http://127.0.0.1:8027/v1/demo/fixtures/medicaid_address_confirmation/pages/1');
    expect(screen.queryByLabelText(t('review.hide_parts'))).toBeNull();
    expect(screen.queryByLabelText(t('review.remove'))).toBeNull();
  });
});
