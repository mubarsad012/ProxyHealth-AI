// S6 on a slow test tier (LOCAL_AI.md §5): when `/v1/config` announces a long analyze budget (a
// local model, `client_timeouts.analyze_s` ≈ 625), the reading screen says a page takes minutes
// instead of "usually under a minute" and adds a 3-minute tip; Gemini and hosted test endpoints
// keep today's copy. The server's honest timeout keys render as themselves, and a key an older
// app does not know falls back to the error code's copy.

import { act, render } from '@testing-library/react-native';

import { type ApiClient, createClient } from '@/api/client';
import { resetServerConfigSession, setClient } from '@/api/config';
import { ApiError } from '@/api/errors';
import type { ClientTimeouts, ServerConfig } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';
import { ErrorState, errorCopyKey } from '@/design/components/States';
import { isSlowTier, TIP_SLOW_MS, TIP_STILL_MS } from '@/features/analysis/useAnalyze';
import { ReadingScreen } from '@/features/scan/ReadingScreen';
import { samplePages } from '@/features/scan/samples';
import { EN_PACK, t, useI18n } from '@/i18n/store';
import { useSession } from '@/store/session';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-router', () => ({
  router: { back: jest.fn(), replace: jest.fn(), push: jest.fn(), canGoBack: () => true },
  Stack: { Screen: () => null },
  useLocalSearchParams: () => ({}),
  useFocusEffect: () => undefined,
}));

// jest-expo cannot load the bundled fixture map (`@/assets/*` path).
jest.mock('@/api/offline', () => ({
  bundledFixture: () => ({ pages: 1 }),
  bundledFixtureResult: () => null,
}));

const SAMPLE = 'medicaid_address_confirmation';
const LOCAL: ClientTimeouts = { analyze_s: 625, troubleshoot_s: 625, language_pack_s: 625, chat_s: 625, default_s: 30 };
const HOSTED: ClientTimeouts = { analyze_s: 205, troubleshoot_s: 205, language_pack_s: 205, chat_s: 205, default_s: 30 };
const GEMINI: ClientTimeouts = { analyze_s: 120, troubleshoot_s: 60, language_pack_s: 60, chat_s: 30, default_s: 30 };

function config(timeouts: ClientTimeouts): ServerConfig {
  return {
    api_version: '0.1.0',
    contract_version: 1,
    provider: 'openai_compat',
    data_use_tier: 'local',
    features: { real_documents_allowed: true, demo_samples: true },
    limits: {},
    consent_version: '2026-10-04',
    client_timeouts: timeouts,
  } as unknown as ServerConfig;
}

/** A client whose analyze call never answers (the model is still reading). */
function readingClient(timeouts: ClientTimeouts): ApiClient {
  const fetchMock = jest.fn((url: string, init: RequestInit) => {
    if (url.endsWith('/v1/config')) {
      return Promise.resolve(new Response(JSON.stringify(config(timeouts)), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return new Promise<Response>((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new Error('aborted')));
    });
  });
  const client = createClient({
    baseUrl: 'http://127.0.0.1:8028',
    getConsentVersion: () => '2026-10-04',
    getInstallId: async () => 'install-slow',
    getTimeouts: () => useSession.getState().serverConfig?.client_timeouts ?? null,
    fetch: fetchMock as unknown as typeof fetch,
  });
  setClient(client);
  return client;
}

async function renderReading(timeouts: ClientTimeouts) {
  useSession.getState().setServerConfig(config(timeouts));
  const client = readingClient(timeouts);
  useSession.getState().setDemoSampleId(SAMPLE);
  useSession.getState().setPages(samplePages(client, SAMPLE));
  return render(
    <AppProviders client={client} staticMetrics>
      <ReadingScreen />
    </AppProviders>,
  );
}

beforeEach(() => {
  resetServerConfigSession();
  useSession.getState().reset();
  useI18n.getState().setPack(EN_PACK);
});

afterEach(() => {
  jest.useRealTimers();
});

afterAll(() => setClient(null));

describe('slow tier detection', () => {
  it('counts only a budget of 5 minutes or more as slow', () => {
    expect(isSlowTier(LOCAL)).toBe(true);
    expect(isSlowTier(HOSTED)).toBe(false);
    expect(isSlowTier(GEMINI)).toBe(false);
    expect(isSlowTier(null)).toBe(false);
    expect(isSlowTier(undefined)).toBe(false);
    // A Gemini server on a small sleeping host announces a long budget but is no "slower AI".
    expect(isSlowTier({ analyze_s: 405 }, 'gemini')).toBe(false);
    expect(isSlowTier(LOCAL, 'openai_compat')).toBe(true);
  });
});

describe('reading screen copy', () => {
  it('says a page takes minutes on the local tier', async () => {
    const screen = await renderReading(LOCAL);
    expect(screen.getByText(t('reading.eta_slow'))).toBeTruthy();
    expect(screen.queryByText(t('reading.eta'))).toBeNull();
    await screen.unmount();
  });

  it('keeps "usually under a minute" on Gemini', async () => {
    const screen = await renderReading(GEMINI);
    expect(screen.getByText(t('reading.eta'))).toBeTruthy();
    expect(screen.queryByText(t('reading.eta_slow'))).toBeNull();
    await screen.unmount();
  });

  it('adds the 3-minute tip only on the slow tier', async () => {
    jest.useFakeTimers();
    const slow = await renderReading(LOCAL);
    await act(async () => {
      jest.advanceTimersByTime(TIP_STILL_MS);
    });
    expect(slow.getByText(t('reading.tip_still'))).toBeTruthy();
    await act(async () => {
      jest.advanceTimersByTime(TIP_SLOW_MS - TIP_STILL_MS);
    });
    expect(slow.getByText(t('reading.tip_slow'))).toBeTruthy();
    await slow.unmount();

    const hosted = await renderReading(HOSTED);
    await act(async () => {
      jest.advanceTimersByTime(TIP_SLOW_MS);
    });
    expect(hosted.getByText(t('reading.tip_still'))).toBeTruthy();
    expect(hosted.queryByText(t('reading.tip_slow'))).toBeNull();
    await hosted.unmount();
  });
});

describe('timeout error copy', () => {
  it("renders the server's err.ai_too_slow / err.ai_busy keys", () => {
    const slow = new ApiError({ code: 'upstream_unavailable', status: 503, userMessageKey: 'err.ai_too_slow' });
    expect(errorCopyKey(slow)).toBe('err.ai_too_slow');
    expect(t('err.ai_too_slow')).not.toBe('err.ai_too_slow');
    const busy = new ApiError({ code: 'upstream_unavailable', status: 503, userMessageKey: 'err.ai_busy' });
    expect(errorCopyKey(busy)).toBe('err.ai_busy');
  });

  it('shows no Retry countdown for err.ai_too_slow, but keeps it for other 503s', async () => {
    const client = readingClient(LOCAL);
    const slow = new ApiError({ code: 'upstream_unavailable', status: 503, userMessageKey: 'err.ai_too_slow', retryAfterSeconds: 30 });
    const tooSlow = await render(
      <AppProviders client={client} staticMetrics>
        <ErrorState error={slow} onRetry={jest.fn()} />
      </AppProviders>,
    );
    expect(tooSlow.getByText(t('btn.retry'))).toBeTruthy();
    expect(tooSlow.queryByText(`${t('btn.retry')} (0:30)`)).toBeNull();
    await tooSlow.unmount();

    const busy = new ApiError({ code: 'upstream_unavailable', status: 503, userMessageKey: 'err.ai_busy', retryAfterSeconds: 60 });
    const waiting = await render(
      <AppProviders client={client} staticMetrics>
        <ErrorState error={busy} onRetry={jest.fn()} />
      </AppProviders>,
    );
    expect(waiting.getByText(`${t('btn.retry')} (1:00)`)).toBeTruthy();
    await waiting.unmount();
  });

  it('falls back to the code copy for a key this app does not know', () => {
    const future = new ApiError({ code: 'upstream_unavailable', status: 503, userMessageKey: 'err.not_in_any_pack_yet' });
    expect(errorCopyKey(future)).toBe('err.upstream_unavailable');
  });
});
