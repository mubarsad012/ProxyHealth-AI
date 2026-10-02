// Saved papers show their kept page images (PRODUCT_SPEC S7 "Data", S8 "States": `source.no_image`
// only when images kept is OFF in the vault) and speakers outside S7 show the honest TTS line in the
// language they actually read (D-26): S8 blocks in `detected_language`, the S19 card in the pack.

import { fireEvent, render, waitFor, within } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { AnalysisResult } from '@/api/types';
import SourceRoute from '@/app/result/[id]/source';
import { EmergencyCard } from '@/features/emergency';
import { FALLBACK_ENGLISH_KEY, fallbackNotice } from '@/features/speech';
import { LANGUAGES } from '@/i18n/languages';
import { bundledPackFor, EN_PACK, t, useI18n } from '@/i18n/store';
import { resetVoicesForTests } from '@/lib/tts';
import type { StoredDocument, StoredPage, Vault } from '@/storage/index';
import { StorageProvider } from '@/storage/StorageProvider';
import { useSession } from '@/store/session';

import inovaEn from '../../../assets/fixtures/inova_final_notice.result.en.json';
import { pageImageFor } from './pageImages';
import { loadStoredPages } from './storedPages';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

let mockParams: Record<string, string> = {};
jest.mock('expo-router', () => ({
  router: { back: jest.fn(), replace: jest.fn(), push: jest.fn(), canGoBack: () => true },
  useLocalSearchParams: () => mockParams,
  Stack: { Screen: () => null },
}));

let mockVoices: { identifier: string; name: string; quality: string; language: string }[] = [];
jest.mock('expo-speech', () => ({
  getAvailableVoicesAsync: () => Promise.resolve(mockVoices),
  speak: (_text: string, opts?: { onDone?: () => void }) => opts?.onDone?.(),
  stop: () => Promise.resolve(),
  isSpeakingAsync: () => Promise.resolve(false),
  maxSpeechInputLength: 4000,
  VoiceQuality: { Default: 'Default', Enhanced: 'Enhanced' },
}));

const METRICS = { frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };
const voice = (language: string) => ({ identifier: language, name: language, quality: 'Default', language });
const analysis = (): AnalysisResult => JSON.parse(JSON.stringify(inovaEn)) as AnalysisResult;

function fakeVault(doc: StoredDocument | null, stored: StoredPage[], uris: Record<string, string | null>): Vault {
  return {
    documents: { get: async (id: string) => (doc && doc.id === id ? doc : null) },
    pages: {
      list: async (documentId: string) => stored.filter((p) => p.documentId === documentId),
      uri: async (p: StoredPage) => uris[p.filePath] ?? null,
    },
  } as unknown as Vault;
}

function storedDoc(a: AnalysisResult, keepPages: boolean): StoredDocument {
  return {
    id: 'doc-1',
    memberId: 'me',
    title: a.summary.title,
    keepPages,
    pageCount: 1,
    analysis: a,
  } as unknown as StoredDocument;
}

const page = (n: number): StoredPage => ({ documentId: 'doc-1', page: n, filePath: `p${n}.jpg`, thumbPath: null });

beforeEach(() => {
  resetVoicesForTests();
  mockVoices = [];
  mockParams = {};
});

afterEach(() => {
  useI18n.getState().setPack(EN_PACK);
  useSession.getState().reset();
});

describe('kept page images of a saved paper', () => {
  it('loads stored page files at their page number; a gap stays a quote-only placeholder (CL-077)', async () => {
    const vault = fakeVault(null, [page(2), page(1), page(4)], { 'p1.jpg': 'file:///v/p1.jpg', 'p2.jpg': 'file:///v/p2.jpg', 'p4.jpg': 'file:///v/p4.jpg' });
    const pages = await loadStoredPages(vault, 'doc-1');
    expect(pages.map((p) => p.uri)).toEqual(['file:///v/p1.jpg', 'file:///v/p2.jpg', '', 'file:///v/p4.jpg']);
    expect(pages[0]).toMatchObject({ id: 'doc-1-p1', mimeType: 'image/jpeg', rotation: 0, masks: [] });
    // Page 1 was masked and not kept: page 2 keeps its own image, page 1 is quote-only.
    const missing = fakeVault(null, [page(1), page(2)], { 'p1.jpg': null, 'p2.jpg': 'file:///v/p2.jpg' });
    const slots = await loadStoredPages(missing, 'doc-1');
    expect(slots.map((p) => p.uri)).toEqual(['', 'file:///v/p2.jpg']);
    const a = analysis();
    delete (a as { page_thumbnails?: unknown }).page_thumbnails;
    expect(pageImageFor(a, slots, 1)).toBeNull();
    expect(pageImageFor(a, slots, 2)?.uri).toBe('file:///v/p2.jpg');
  });

  it('S8 shows the kept page image for a vault paper (no "not kept" line)', async () => {
    const a = analysis();
    delete (a as { page_thumbnails?: unknown }).page_thumbnails;
    mockParams = { id: 'doc-1' };
    const vault = fakeVault(storedDoc(a, true), [page(1)], { 'p1.jpg': 'file:///v/p1.jpg' });
    const { findByTestId, queryByText, toJSON } = await render(
      <SafeAreaProvider initialMetrics={METRICS}>
        <StorageProvider value={vault}>
          <SourceRoute />
        </StorageProvider>
      </SafeAreaProvider>,
    );
    await findByTestId('source-screen');
    await waitFor(() => expect(JSON.stringify(toJSON())).toContain('file:///v/p1.jpg'));
    expect(queryByText(t('source.no_image'))).toBeNull();
  });

  it('S8 says images were not kept only when keepPages is off', async () => {
    const a = analysis();
    delete (a as { page_thumbnails?: unknown }).page_thumbnails;
    mockParams = { id: 'doc-1' };
    const vault = fakeVault(storedDoc(a, false), [], {});
    const { findByText } = await render(
      <SafeAreaProvider initialMetrics={METRICS}>
        <StorageProvider value={vault}>
          <SourceRoute />
        </StorageProvider>
      </SafeAreaProvider>,
    );
    expect(await findByText(t('source.no_image'))).toBeTruthy();
  });
});

describe('honest TTS line outside S7', () => {
  it('names a different-language voice even when lib/tts did not flag a fallback (CL-053)', () => {
    const v = (language: string) => ({ voice: voice(language), usedFallbackTag: null, languageTag: language }) as never;
    expect(fallbackNotice(v('fa-IR'), 'prs', t)).toBe(t('tts.fallback_offer', { language: 'دری', fallback: LANGUAGES.fa.name_native }));
    expect(fallbackNotice(v('fa_AF'), 'prs', t)).toBeNull();
    expect(fallbackNotice(v('es-MX'), 'es', t)).toBeNull();
    expect(fallbackNotice(v('xx-YY'), 'xx', t)).toBeNull();
  });

  it('S8: a Spanish block read by an English voice says so, in the block language', async () => {
    mockVoices = [voice('en-US')];
    const a = analysis();
    a.detected_language = 'es';
    mockParams = { id: 'doc-1' };
    const vault = fakeVault(storedDoc(a, false), [], {});
    const { findByTestId, getByTestId } = await render(
      <SafeAreaProvider initialMetrics={METRICS}>
        <StorageProvider value={vault}>
          <SourceRoute />
        </StorageProvider>
      </SafeAreaProvider>,
    );
    await findByTestId('source-screen');
    const firstBlock = a.original_text[0].blocks[0];
    const speaker = within(getByTestId(`source-block-${firstBlock.id}`)).getAllByLabelText(t('btn.read_aloud'))[0];
    await fireEvent.press(speaker);
    const notice = await findByTestId('tts-fallback-notice');
    // The fallback IS English, so the line offers English once ("… Hear it in English?"), never
    // "Hear it in English or English?" (`tts.fallback_offer_english`, keys-2c-mobilescan.json).
    expect(notice).toHaveTextContent(t(FALLBACK_ENGLISH_KEY, { language: LANGUAGES.es.name_native }));
    expect(notice).not.toHaveTextContent(t('tts.fallback_offer', { language: LANGUAGES.es.name_native, fallback: 'English' }));
  });

  it('S19 opened from Home in Dari shows the Farsi-voice line up front', async () => {
    const pack = bundledPackFor('prs');
    if (pack) useI18n.getState().setPack(pack);
    mockVoices = [voice('fa-IR'), voice('en-US')];
    const { findByTestId } = await render(<EmergencyCard kinds={[]} onClose={jest.fn()} />);
    expect(await findByTestId('tts-fallback-notice')).toHaveTextContent(
      t('tts.fallback_offer', { language: 'دری', fallback: LANGUAGES.fa.name_native }),
    );
  });

  it('S19 stays silent when the pack voice exists', async () => {
    mockVoices = [voice('en-US')];
    const { findByTestId, queryByTestId } = await render(<EmergencyCard kinds={[]} onClose={jest.fn()} />);
    await findByTestId('emergency-card');
    await waitFor(() => expect(queryByTestId('tts-fallback-notice')).toBeNull());
  });
});
