// S5 should-haves (PRODUCT_SPEC S5): the output-language chip (UI language by default; the sheet
// sets the result language before reading), the "I think this is a…" document-hint chips (sent as
// `document_hint`; none for a sample), the collapsed "Whose paper is this?" member picker (default
// Me; preselects the member when saving), the choices resetting for a new scan, and every page image
// labelled "Page {n} of {count}". New copy keys come from keys-2c-mobilescan.json, so the test pack
// carries English for them until the COPY merge.

import { act, fireEvent, render } from '@testing-library/react-native';

import type { ApiClient } from '@/api/client';
import { AppProviders } from '@/design/components/Providers';
import { currentRequestContext } from '@/features/analysis/useAnalyze';
import { EN_PACK, useI18n } from '@/i18n/store';
import type { Vault } from '@/storage/index';
import { type CapturedPage, useSession } from '@/store/session';

import { DOCUMENT_HINTS, documentHintKey, isNewScan, memberChoiceFor, PAGE_IMAGE_KEY, rememberMemberFor, useScanChoices } from './choices';
import { OUTPUT_LANGUAGE_KEY } from './ReviewOptions';
import { ReviewScreen } from './ReviewScreen';

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
    if (prop === 'fixturePageUrl') return (id: string, n: number) => `http://127.0.0.1:8045/v1/demo/fixtures/${id}/pages/${n}`;
    if (prop === 'baseUrl') return 'http://127.0.0.1:8045';
    return () => Promise.reject(new Error('offline'));
  },
});

const vault = {
  members: { list: async () => [{ id: 'm1', name: 'Layla', color: '#2E7D32', createdAt: '2026-10-01T00:00:00Z' }] },
} as unknown as Vault;

const STRINGS: Record<string, string> = {
  [PAGE_IMAGE_KEY]: 'Page {n} of {count}',
  [OUTPUT_LANGUAGE_KEY]: 'Explain it in: {language}',
  'review.output_language_title': 'Which language should I explain it in?',
  'review.hint.not_sure': 'Not sure',
  'review.hint.medical_bill': 'A medical bill',
};

function page(id: string): CapturedPage {
  return { id, uri: `file:///${id}.jpg`, mimeType: 'image/jpeg', width: 1200, height: 1600, rotation: 0, masks: [], source: 'camera' };
}

function testPack() {
  useI18n.getState().setPack({ ...EN_PACK, strings: { ...EN_PACK.strings, ...STRINGS } });
}

async function renderReview() {
  const screen = await render(
    <AppProviders client={client} vault={vault} staticMetrics>
      <ReviewScreen />
    </AppProviders>,
  );
  // The providers' first settings hydration may put the bundled pack back; re-apply the test pack.
  await act(async () => testPack());
  return screen;
}

beforeEach(() => {
  mockParams = {};
  useSession.getState().reset();
  useScanChoices.getState().reset();
  testPack();
});

afterAll(() => useI18n.getState().setPack(EN_PACK));

describe('S5 options', () => {
  it('labels each page image "Page {n} of {count}"', async () => {
    useSession.getState().setPages([page('a'), page('b')]);
    const screen = await renderReview();
    expect(screen.getByLabelText('Page 1 of 2')).toBeTruthy();
    expect(screen.getByLabelText('Page 2 of 2')).toBeTruthy();
  });

  it('output-language chip: UI language by default; the sheet sets the result language', async () => {
    useSession.getState().setPages([page('a')]);
    const screen = await renderReview();
    expect(screen.getByTestId('review-output-language').props.accessibilityLabel).toBe('Explain it in: English');
    expect(currentRequestContext('x').targetLanguage).toBe('en');
    await act(async () => {
      fireEvent.press(screen.getByTestId('review-output-language'));
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId('output-language-es'));
    });
    expect(useScanChoices.getState().outputLanguage).toBe('es');
    expect(screen.getByTestId('review-output-language').props.accessibilityLabel).toBe('Explain it in: Español');
    const ctx = currentRequestContext('x');
    expect(ctx.targetLanguage).toBe('es');
    expect(ctx.uiDirection).toBe('ltr'); // the UI stays as it is
    // Choosing the UI language again stores "follow the UI".
    await act(async () => {
      fireEvent.press(screen.getByTestId('review-output-language'));
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId('output-language-en'));
    });
    expect(useScanChoices.getState().outputLanguage).toBeNull();
  });

  it('document-hint chips: ≤ 8 DocumentType values + "Not sure"; the choice goes in the request', async () => {
    expect(DOCUMENT_HINTS.length).toBeLessThanOrEqual(8);
    expect(documentHintKey(null)).toBe('review.hint.not_sure');
    useSession.getState().setPages([page('a')]);
    const screen = await renderReview();
    expect(screen.getByLabelText('Not sure')).toBeTruthy();
    await act(async () => {
      fireEvent.press(screen.getByLabelText('A medical bill'));
    });
    expect(currentRequestContext('x').documentHint).toBe('medical_bill');
    await act(async () => {
      fireEvent.press(screen.getByLabelText('Not sure'));
    });
    expect(currentRequestContext('x').documentHint).toBeNull();
  });

  it('"Whose paper is this?" is collapsed, lists the vault members with Me first, and remembers the pick', async () => {
    useSession.getState().setPages([page('a')]);
    const screen = await renderReview();
    expect(screen.queryByTestId('review-member-m1')).toBeNull();
    await act(async () => {
      fireEvent.press(screen.getByLabelText('Whose paper is this? (you can choose later)'));
    });
    expect(screen.getByTestId('review-member-me').props.accessibilityState.checked).toBe(true);
    await act(async () => {
      fireEvent.press(await screen.findByTestId('review-member-m1'));
    });
    expect(useScanChoices.getState().memberId).toBe('m1');
    rememberMemberFor('an-1', useScanChoices.getState().memberId);
    expect(memberChoiceFor('an-1')).toBe('m1');
    rememberMemberFor('an-1', null);
    expect(memberChoiceFor('an-1')).toBeNull();
  });

  it('a sample shows the language chip only (no hint, no member picker) and sends no hint', async () => {
    useScanChoices.getState().setDocumentHint('medical_bill');
    mockParams = { sample: 'medicaid_address_confirmation' };
    const screen = await renderReview();
    expect(screen.getByTestId('review-output-language')).toBeTruthy();
    expect(screen.queryByTestId('review-document-hint')).toBeNull();
    expect(screen.queryByTestId('review-whose-paper')).toBeNull();
    useScanChoices.getState().setDocumentHint('medical_bill');
    expect(currentRequestContext('x').documentHint).toBeNull();
  });
});

describe('choices reset for a new scan', () => {
  it('isNewScan: emptied, replaced, or another sample — not an added or reordered page', () => {
    const a = { pages: [{ id: 'a' }], demoSampleId: null };
    expect(isNewScan(a, { pages: [{ id: 'a' }, { id: 'b' }], demoSampleId: null })).toBe(false);
    expect(isNewScan({ pages: [{ id: 'a' }, { id: 'b' }], demoSampleId: null }, { pages: [{ id: 'b' }, { id: 'a' }], demoSampleId: null })).toBe(false);
    expect(isNewScan({ pages: [], demoSampleId: null }, a)).toBe(false);
    expect(isNewScan(a, { pages: [], demoSampleId: null })).toBe(true);
    expect(isNewScan(a, { pages: [{ id: 'z' }], demoSampleId: null })).toBe(true);
    expect(isNewScan(a, { pages: [{ id: 'a' }], demoSampleId: 'w2_form' })).toBe(true);
  });

  it('the store resets when the session starts another scan', () => {
    useSession.getState().setPages([page('a')]);
    useScanChoices.getState().setOutputLanguage('ar');
    useScanChoices.getState().setMemberId('m1');
    useSession.getState().setPages([page('a'), page('b')]);
    expect(useScanChoices.getState().outputLanguage).toBe('ar');
    useSession.getState().clearPages();
    expect(useScanChoices.getState()).toMatchObject({ outputLanguage: null, documentHint: null, memberId: null });
  });
});
