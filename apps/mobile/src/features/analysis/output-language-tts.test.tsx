// The S5 output-language chip can make `analysis.target_language` differ from the UI pack. The
// result's own words are then read with the target language's voice and the honest TTS line
// (D-26) is computed for that language: S7's up-front line and S8's translation speakers. UI
// English + chip Dari on a phone with a Farsi voice must say "No Dari voice … Farsi".

import { fireEvent, render, within } from '@testing-library/react-native';

import type { ApiClient } from '@/api/client';
import type { AnalysisResult } from '@/api/types';
import SourceRoute from '@/app/result/[id]/source';
import { AppProviders } from '@/design/components/Providers';
import { LANGUAGES } from '@/i18n/languages';
import { EN_PACK, t, useI18n } from '@/i18n/store';
import { resetVoicesForTests } from '@/lib/tts';
import type { StoredDocument, Vault } from '@/storage/index';
import { useSession } from '@/store/session';

import medicaidPrs from '../../../assets/fixtures/medicaid_address_confirmation.result.prs.json';
import { ResultScreen } from './ResultScreen';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

let mockParams: Record<string, string> = {};
jest.mock('expo-router', () => ({
  router: { back: jest.fn(), replace: jest.fn(), push: jest.fn(), canGoBack: () => true },
  useLocalSearchParams: () => mockParams,
  useFocusEffect: () => undefined,
  Stack: { Screen: () => null },
}));

let mockVoices: { identifier: string; name: string; quality: string; language: string }[] = [];
const mockSpoken: { text: string; language?: string }[] = [];
jest.mock('expo-speech', () => ({
  getAvailableVoicesAsync: () => Promise.resolve(mockVoices),
  speak: (text: string, opts?: { language?: string; onDone?: () => void }) => {
    mockSpoken.push({ text, language: opts?.language });
    opts?.onDone?.();
  },
  stop: () => Promise.resolve(),
  isSpeakingAsync: () => Promise.resolve(false),
  maxSpeechInputLength: 4000,
  VoiceQuality: { Default: 'Default', Enhanced: 'Enhanced' },
}));

jest.mock('@/lib/network', () => ({ useOnline: () => ({ online: false, known: true }), isOnline: async () => false }));

const voice = (language: string) => ({ identifier: language, name: language, quality: 'Default', language });
const dari = (): AnalysisResult => JSON.parse(JSON.stringify(medicaidPrs)) as AnalysisResult;
const DARI_ON_FARSI = () => t('tts.fallback_offer', { language: 'دری', fallback: LANGUAGES.fa.name_native });

const offline = new Proxy({} as ApiClient, {
  get: (_t, prop) => (prop === 'baseUrl' ? 'http://127.0.0.1:8045' : () => Promise.reject(new Error('offline'))),
});

function vaultWith(doc: StoredDocument | null): Vault {
  const none = () => Promise.resolve();
  return {
    members: { list: async () => [] },
    documents: { get: async (id: string) => (doc && doc.id === id ? doc : null), list: async () => [] },
    pages: { list: async () => [], uri: async () => null },
    reminders: { list: async () => [], add: jest.fn(), remove: none, setEnabled: none },
    checklist: { get: async () => ({}), set: none },
  } as unknown as Vault;
}

beforeEach(() => {
  resetVoicesForTests();
  mockVoices = [voice('fa-IR'), voice('en-US')];
  mockSpoken.length = 0;
  mockParams = {};
  useI18n.getState().setPack(EN_PACK);
});

afterEach(() => {
  useSession.getState().reset();
});

describe('UI English, output language Dari', () => {
  it('S7 shows the Dari-on-Farsi line up front (computed for target_language, not the UI pack)', async () => {
    const a = dari();
    expect(a.target_language).toBe('prs');
    useSession.getState().setCurrentAnalysis(a);
    const { findByTestId } = await render(
      <AppProviders client={offline} vault={vaultWith(null)} staticMetrics>
        <ResultScreen id={a.analysis_id} />
      </AppProviders>,
    );
    expect(await findByTestId('tts-fallback-notice')).toHaveTextContent(DARI_ON_FARSI());
  });

  it('S8 translation speakers read in target_language and say so', async () => {
    const a = dari();
    mockParams = { id: 'doc-1' };
    const doc = { id: 'doc-1', memberId: 'me', title: a.summary.title, keepPages: false, pageCount: 1, analysis: a } as unknown as StoredDocument;
    const { findByTestId, getByTestId } = await render(
      <AppProviders client={offline} vault={vaultWith(doc)} staticMetrics>
        <SourceRoute />
      </AppProviders>,
    );
    await findByTestId('source-screen');
    // The fixture's Dari translation is line-aligned with the blocks, so each block row has two
    // speakers: [0] the paper's own (English) words, [1] the Dari translation.
    const block = a.original_text[0].blocks[0];
    const speakers = within(getByTestId(`source-block-${block.id}`)).getAllByLabelText(t('btn.read_aloud'));
    expect(speakers).toHaveLength(2);
    await fireEvent.press(speakers[1]);
    expect(await findByTestId('tts-fallback-notice')).toHaveTextContent(DARI_ON_FARSI());
    expect(mockSpoken[mockSpoken.length - 1]?.language).toMatch(/^fa/);
  });
});
