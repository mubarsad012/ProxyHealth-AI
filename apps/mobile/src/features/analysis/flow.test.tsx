// End-to-end flow at code level (BUILD_PLAN §5.6 Acceptance "full flow web against the mock API";
// a browser is not available to the build agents and the API package is mid-rewrite, so the real
// `createClient` runs against a mocked `fetch` that answers like `AI_PROVIDER=mock`):
//   sample → S6 Reading (three steps, ≥ 1.5 s) → `POST /v1/analyze` → S7 route → result cards;
//   web scan with hidden parts → the body on the wire has `masks_applied_client_side: true` and
//   empty `masks`; native keeps `masks[]`; before consent the app's real client guard
//   (`refuseUnconsentedUploads: true`, as `api/config.ts` builds it) sends NOTHING — S2 shows inline
//   and the one retry after consent is the first analyze call on the wire; a server 428 (a client
//   without the guard) is handled the same way;
//   an unreachable server on a real scan shows the network error with its next steps, and "Save to
//   read later" saves the pages to My papers as "Not read yet" (no in-memory queue).

import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import { router } from 'expo-router';

import { type ApiClient, createClient } from '@/api/client';
import { resetServerConfigSession, setClient } from '@/api/config';
import type { AnalysisResult, AnalyzeRequest, ServerConfig } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';
import { resetConsentState } from '@/features/onboarding/consentState';
import { consentThenRetry, ReadingScreen } from '@/features/scan/ReadingScreen';
import { samplePages } from '@/features/scan/samples';
import { EN_PACK, t, useI18n } from '@/i18n/store';
import type { StoredDocument, StoredPageInput, Vault } from '@/storage/index';
import { type CapturedPage, useSession } from '@/store/session';

import medicaidEn from '../../../assets/fixtures/medicaid_address_confirmation.result.en.json';
import { ResultView } from './ResultView';
import { runAnalysis } from './runAnalysis';
import { currentRequestContext } from './useAnalyze';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-router', () => ({
  router: { back: jest.fn(), replace: jest.fn(), push: jest.fn(), canGoBack: () => true },
  Stack: { Screen: () => null },
  useLocalSearchParams: () => ({}),
  useFocusEffect: () => undefined,
}));

// jest-expo's expo-crypto mock returns undefined ids; give each request a real-looking one.
let mockSeq = 0;
jest.mock('expo-crypto', () => ({
  ...jest.requireActual('expo-crypto'),
  randomUUID: () => {
    mockSeq += 1;
    return `00000000-0000-4000-8000-${String(mockSeq).padStart(12, '0')}`;
  },
}));

jest.mock('@/lib/image', () => {
  const actual = jest.requireActual('@/lib/image');
  return {
    ...actual,
    toJpegBase64: jest.fn(async () => ({ base64: 'SlBFRw==', width: 1200, height: 1600, byteLength: 4 })),
    burnMasksOnCanvas: jest.fn(async () => 'QlVSTkVE'),
  };
});

// jest-expo cannot load the bundled fixture map (`@/assets/*` path); serve the synced file.
jest.mock('@/api/offline', () => ({
  bundledFixture: () => ({ pages: 1 }),
  bundledFixtureResult: () => null,
}));

const API = 'http://127.0.0.1:8027';
const CONSENT = '2026-10-01';

function demoConfig(): ServerConfig {
  return {
    api_version: '0.1.0',
    contract_version: 1,
    provider: 'mock',
    data_use_tier: 'demo',
    models: { fast: 'gemini-3.5-flash-lite', pro: 'gemini-3.8-flash', pro_degraded_thinking: 'medium' },
    features: {
      real_documents_allowed: false,
      demo_samples: true,
      dynamic_language_packs: true,
      troubleshoot: true,
      chat: true,
      quicksheet_pdf: true,
      degraded_fallback: true,
      hide_parts_server_masking: true,
    },
    limits: {} as ServerConfig['limits'],
    consent_version: CONSENT,
    privacy_policy_url: 'https://proxyhealth.expo.app/privacy',
    base_pack_version: 'base',
    languages: [],
    taxonomy_version: 't',
    resource_db_version: 'r',
    rules_version: 'rv',
    key_slots: { total: 0, healthy: 0, cooling: 0, rpd_exhausted: 0, disabled: 0 },
    region_notice: 'us_only',
    server_time: '2026-09-27T00:00:00Z',
  } as ServerConfig;
}

type Call = { url: string; init: RequestInit; body: AnalyzeRequest | null };

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function mockResult(req: AnalyzeRequest): AnalysisResult {
  const base = JSON.parse(JSON.stringify(medicaidEn)) as AnalysisResult;
  return { ...base, analysis_id: req.analysis_id ?? base.analysis_id };
}

/** A fetch that answers like the mock API; `script` can override responses per call.
 *  `guard` builds the client like the app does (`refuseUnconsentedUploads: true`). */
function mockApi(script: ((call: Call, n: number) => Response | Promise<Response> | null) | null = null, guard = false) {
  const calls: Call[] = [];
  const fetchMock = jest.fn(async (url: string, init: RequestInit) => {
    const body = typeof init.body === 'string' ? (JSON.parse(init.body) as AnalyzeRequest) : null;
    const call = { url, init, body };
    calls.push(call);
    const scripted = script?.(call, calls.length);
    if (scripted) return scripted;
    if (url.endsWith('/v1/analyze') && body) return json(200, mockResult(body));
    if (url.endsWith('/v1/config')) return json(200, demoConfig());
    return json(404, { error: { code: 'not_found', message: 'x', user_message_key: 'err.not_found' } });
  });
  const client = createClient({
    baseUrl: API,
    getConsentVersion: () => useSession.getState().consent?.consent_version ?? null,
    getInstallId: async () => 'install-wp5',
    getLanguageTag: () => useI18n.getState().tag,
    fetch: fetchMock as unknown as typeof fetch,
    refuseUnconsentedUploads: guard,
  });
  setClient(client);
  const analyzeCalls = () => calls.filter((c) => c.url.endsWith('/v1/analyze'));
  const header = (i: number, name: string) => new Headers(analyzeCalls()[i].init.headers).get(name);
  return { client, calls, analyzeCalls, header };
}

function consentGiven() {
  useSession.getState().setConsent({ consent_version: CONSENT, accepted_at: '2026-09-27T10:00:00Z', tier_seen: 'demo', platform: 'web' });
}

async function renderReading(client: ApiClient, vault?: Vault) {
  return render(
    <AppProviders client={client} vault={vault} staticMetrics>
      <ReadingScreen />
    </AppProviders>,
  );
}

/** A vault that records `documents.save` (the read-later path). */
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

function webPage(patch: Partial<CapturedPage> = {}): CapturedPage {
  return {
    id: 'page_1',
    uri: 'blob:http://localhost/p1',
    mimeType: 'image/jpeg',
    rotation: 0,
    masks: [{ x0: 0.62, y0: 0.08, x1: 0.95, y1: 0.12 }],
    source: 'library',
    ...patch,
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  resetConsentState();
  resetServerConfigSession();
  useSession.getState().reset();
  useI18n.getState().setPack(EN_PACK);
});

afterAll(() => setClient(null));

describe('sample → reading → result (mock API over fetch)', () => {
  it('sends the sample request with consent, waits ≥ 1.5 s, stores the result and opens S7', async () => {
    const { client, analyzeCalls, header } = mockApi();
    consentGiven();
    useSession.getState().setDemoSampleId('medicaid_address_confirmation');
    useSession.getState().setPages(samplePages(client, 'medicaid_address_confirmation'));
    const started = Date.now();
    const screen = await renderReading(client);
    expect(screen.getByText(t('reading.step1'))).toBeTruthy();
    expect(screen.getByText(t('reading.trust_line'))).toBeTruthy();

    await waitFor(() => expect(router.replace).toHaveBeenCalled(), { timeout: 5000 });
    expect(Date.now() - started).toBeGreaterThanOrEqual(1400);
    const calls = analyzeCalls();
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe(`${API}/v1/analyze`);
    expect(header(0, 'X-Consent-Version')).toBe(CONSENT);
    expect(calls[0].body?.pages).toEqual([]);
    expect(calls[0].body?.demo_sample_id).toBe('medicaid_address_confirmation');
    expect(calls[0].body?.include_page_thumbnails).toBe(false);
    expect(calls[0].body?.analysis_id).toMatch(/^[0-9a-f-]{36}$/);

    const stored = useSession.getState().currentAnalysis;
    expect(stored?.analysis_id).toBe(calls[0].body?.analysis_id);
    expect(router.replace).toHaveBeenCalledWith(`/result/${encodeURIComponent(stored?.analysis_id ?? '')}`);

    // S7 renders the three cards with quotes and the urgency banner from the stored result.
    const result = await render(<ResultView analysis={stored as AnalysisResult} pages={[]} handlers={{}} />);
    expect(result.getByTestId('card-what-is-this')).toBeTruthy();
    expect(result.getByTestId('card-asking-for')).toBeTruthy();
    expect(result.getByTestId('card-plan')).toBeTruthy();
    for (const d of (stored as AnalysisResult).demands) {
      expect(result.getByTestId(`fact-${d.id}-crop`)).toBeTruthy();
    }
  }, 10_000);
});

describe('the analyze body on the wire (real client, mocked fetch)', () => {
  it('web with hidden parts: masks burned on canvas, masks: [] and masks_applied_client_side: true', async () => {
    const { client, calls } = mockApi();
    consentGiven();
    await runAnalysis({ client, pages: [webPage()], ctx: { ...currentRequestContext('a-web'), platform: 'web' } });
    const body = calls[0].body as AnalyzeRequest;
    expect(body.masks_applied_client_side).toBe(true);
    expect(body.pages?.[0]).toEqual({ data_base64: 'QlVSTkVE', mime_type: 'image/jpeg', rotation: 0, masks: [] });
    expect(body.client_platform).toBe('web');
    expect(body.analysis_id).toBe('a-web');
  });

  it('native keeps masks[] for the server to burn and never claims client-side masking', async () => {
    const { client, calls } = mockApi();
    consentGiven();
    await runAnalysis({ client, pages: [webPage({ uri: 'file:///p1.jpg', source: 'camera' })], ctx: { ...currentRequestContext('a-ios'), platform: 'ios' } });
    const body = calls[0].body as AnalyzeRequest;
    expect(body.masks_applied_client_side).toBe(false);
    expect(body.pages?.[0].masks).toEqual([{ x0: 0.62, y0: 0.08, x1: 0.95, y1: 0.12 }]);
  });
});

describe('S6 error rows', () => {
  it('no consent yet: the real client guard sends nothing, S2 shows inline, one analyze after consent', async () => {
    const { client, analyzeCalls } = mockApi(null, true);
    useSession.getState().setPages([webPage({ masks: [] })]);
    const screen = await renderReading(client);
    await waitFor(() => expect(screen.getByTestId('consent-screen')).toBeTruthy(), { timeout: 5000 });
    // Refused on the device: the page never left the phone before S2.
    expect(analyzeCalls()).toHaveLength(0);
    await waitFor(() => expect(screen.getByTestId('tier-badge-demo')).toBeTruthy());
    await act(async () => {
      fireEvent.press(screen.getByTestId('consent-continue'));
    });
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith(expect.stringMatching(/^\/result\//)), { timeout: 5000 });
    const calls = analyzeCalls();
    expect(calls).toHaveLength(1);
    expect(new Headers(calls[0].init.headers).get('X-Consent-Version')).toBe(CONSENT);
    expect(calls[0].body?.pages).toHaveLength(1);
  }, 15_000);

  it('server 428 (a client without the guard): shows S2 inline, then retries the same request once after consent', async () => {
    // Like the real server: `/v1/analyze` without `X-Consent-Version` → 428.
    const { client, analyzeCalls } = mockApi((call) =>
      call.url.endsWith('/v1/analyze') && new Headers(call.init.headers).get('X-Consent-Version') === null
        ? json(428, { error: { code: 'consent_required', message: 'x', user_message_key: 'err.consent_required', request_id: 'r1', details: null } })
        : null,
    );
    useSession.getState().setPages([webPage({ masks: [] })]);
    const screen = await renderReading(client);
    await waitFor(() => expect(screen.getByTestId('consent-screen')).toBeTruthy(), { timeout: 5000 });
    expect(analyzeCalls()).toHaveLength(1);
    await waitFor(() => expect(screen.getByTestId('tier-badge-demo')).toBeTruthy());
    await act(async () => {
      fireEvent.press(screen.getByTestId('consent-continue'));
    });
    await waitFor(() => expect(router.replace).toHaveBeenCalled(), { timeout: 5000 });
    const calls = analyzeCalls();
    expect(calls).toHaveLength(2);
    expect(new Headers(calls[1].init.headers).get('X-Consent-Version')).toBe(CONSENT);
    expect(calls[1].body?.pages).toEqual(calls[0].body?.pages);
    expect(router.replace).toHaveBeenCalledWith(expect.stringMatching(/^\/result\//));
  }, 15_000);

  it('428 decision helper: retry once only after acceptance; otherwise follow S2', () => {
    const retry = jest.fn();
    const navigate = jest.fn();
    expect(consentThenRetry({ href: '/(tabs)' as never, accepted: false, alreadyRetried: false, retry, navigate })).toBe('navigated');
    expect(consentThenRetry({ href: '/(tabs)?sample=1' as never, accepted: true, alreadyRetried: false, retry, navigate })).toBe('navigated');
    expect(consentThenRetry({ href: '/(tabs)' as never, accepted: true, alreadyRetried: false, retry, navigate })).toBe('retried');
    expect(consentThenRetry({ href: '/(tabs)' as never, accepted: true, alreadyRetried: true, retry, navigate })).toBe('navigated');
    expect(retry).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenCalledTimes(3);
  });

  it('network failure on a real scan: error copy with Retry, Save to read later, Call 211 and Try a sample', async () => {
    const { client } = mockApi((call) => (call.url.endsWith('/v1/analyze') ? Promise.reject(new TypeError('Failed to fetch')) : null));
    const { vault, saved } = recordingVault();
    consentGiven();
    useSession.getState().setPages([webPage({ masks: [] })]);
    const screen = await renderReading(client, vault);
    await waitFor(() => expect(screen.getByText(t('btn.retry'))).toBeTruthy(), { timeout: 5000 });
    expect(screen.getByText(t('btn.save_to_read_later'))).toBeTruthy();
    expect(screen.getByText(t('btn.try_sample'))).toBeTruthy();
    expect(screen.getAllByText(t('btn.call_211'))).toHaveLength(1);
    await act(async () => {
      fireEvent.press(screen.getByText(t('btn.save_to_read_later')));
    });
    // The vault's own "Whose paper is this?" sheet: nothing is written until Save.
    await waitFor(() => expect(screen.getByTestId('save-to-vault-sheet')).toBeTruthy());
    expect(saved).toHaveLength(0);
    await act(async () => {
      fireEvent.press(screen.getByTestId('save-to-vault-confirm'));
    });
    expect(saved).toHaveLength(1);
    expect(saved[0].doc.analysis).toBeNull(); // "Not read yet"
    expect(saved[0].pages).toHaveLength(1); // the page is kept, so "Read it now" can send it later
    expect(saved[0].pages[0].base64Jpeg).toBe('SlBFRw==');
    expect(useSession.getState().offlineQueue).toHaveLength(0); // no in-memory queue that nothing reads
    expect(router.replace).toHaveBeenCalledWith('/papers');
  }, 10_000);

  it('network failure with hidden parts: no "Save to read later" (the stored copy would lose the boxes)', async () => {
    const { client } = mockApi((call) => (call.url.endsWith('/v1/analyze') ? Promise.reject(new TypeError('Failed to fetch')) : null));
    consentGiven();
    useSession.getState().setPages([webPage()]);
    const screen = await renderReading(client);
    await waitFor(() => expect(screen.getByText(t('btn.retry'))).toBeTruthy(), { timeout: 5000 });
    expect(screen.queryByText(t('btn.save_to_read_later'))).toBeNull();
  }, 10_000);
});
