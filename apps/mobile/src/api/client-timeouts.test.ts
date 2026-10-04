// Client time limits (free-ai-providers §4.6): the API client waits as long as `/v1/config`
// `client_timeouts` says — a local model on `AI_PROVIDER=openai_compat` may need minutes — and
// falls back to the fixed 120/60/30 s when the server sent none.

import { createClient, TIMEOUT_BOUNDS_MS, TIMEOUT_MS, timeoutFor } from '@/api/client';
import { getClient, setClient } from '@/api/config';
import { ApiError } from '@/api/errors';
import type { ClientTimeouts, ServerConfig } from '@/api/types';
import { useSession } from '@/store/session';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

const LOCAL_LIMITS: ClientTimeouts = {
  analyze_s: 625,
  troubleshoot_s: 625,
  language_pack_s: 625,
  chat_s: 625,
  default_s: 30,
};

/** A fetch that never answers and rejects like the platform when its signal aborts. */
function hangingFetch(calls: string[]): typeof fetch {
  return ((url: string, init: RequestInit) => {
    calls.push(url);
    return new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => {
        const e = new Error('aborted');
        e.name = 'AbortError';
        reject(e);
      });
    });
  }) as unknown as typeof fetch;
}

type Outcome = { settled: false } | { settled: true; error: unknown };

function track(p: Promise<unknown>): () => Outcome {
  let outcome: Outcome = { settled: false };
  p.then(
    () => {
      outcome = { settled: true, error: null };
    },
    (error: unknown) => {
      outcome = { settled: true, error };
    },
  );
  return () => outcome;
}

describe('timeoutFor', () => {
  it('falls back to the fixed limits when the server sent none', () => {
    for (const limits of [null, undefined, {}]) {
      expect(timeoutFor('analyze', limits)).toBe(TIMEOUT_MS.analyze);
      expect(timeoutFor('troubleshoot', limits)).toBe(TIMEOUT_MS.troubleshoot);
      expect(timeoutFor('postPack', limits)).toBe(TIMEOUT_MS.postPack);
      expect(timeoutFor('chat', limits)).toBe(TIMEOUT_MS.default);
      expect(timeoutFor('default', limits)).toBe(TIMEOUT_MS.default);
    }
  });

  it('maps every ClientTimeouts field (seconds) to its request kind (ms)', () => {
    const limits: ClientTimeouts = { analyze_s: 400, troubleshoot_s: 300, language_pack_s: 200, chat_s: 100, default_s: 45 };
    expect(timeoutFor('analyze', limits)).toBe(400_000);
    expect(timeoutFor('troubleshoot', limits)).toBe(300_000);
    expect(timeoutFor('postPack', limits)).toBe(200_000);
    expect(timeoutFor('chat', limits)).toBe(100_000);
    expect(timeoutFor('default', limits)).toBe(45_000);
  });

  it('ignores unusable values and clamps the rest to TIMEOUT_BOUNDS_MS', () => {
    expect(timeoutFor('analyze', { analyze_s: 0 })).toBe(TIMEOUT_MS.analyze);
    expect(timeoutFor('analyze', { analyze_s: -5 })).toBe(TIMEOUT_MS.analyze);
    expect(timeoutFor('analyze', { analyze_s: Number.NaN })).toBe(TIMEOUT_MS.analyze);
    expect(timeoutFor('analyze', { analyze_s: '600' as unknown as number })).toBe(TIMEOUT_MS.analyze);
    expect(timeoutFor('analyze', { analyze_s: 1 })).toBe(TIMEOUT_BOUNDS_MS.min);
    expect(timeoutFor('analyze', { analyze_s: 24 * 3600 })).toBe(TIMEOUT_BOUNDS_MS.max);
  });
});

describe('createClient with server time limits', () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  const client = (limits: () => Partial<ClientTimeouts> | null | undefined, calls: string[]) =>
    createClient({
      baseUrl: 'http://x',
      getConsentVersion: () => '2026-10-01',
      getInstallId: async () => 'i',
      getTimeouts: limits,
      fetch: hangingFetch(calls),
    });

  it('a slow local analyze is not cut off at 120 s; it times out at the server limit', async () => {
    const calls: string[] = [];
    const outcome = track(client(() => LOCAL_LIMITS, calls).analyze({ pages: [], target_language: 'en' } as never));
    await jest.advanceTimersByTimeAsync(TIMEOUT_MS.analyze + 1_000);
    expect(calls).toEqual(['http://x/v1/analyze']);
    expect(outcome().settled).toBe(false);
    await jest.advanceTimersByTimeAsync(625_000 - TIMEOUT_MS.analyze);
    const done = outcome();
    expect(done.settled).toBe(true);
    expect(done.settled && done.error).toBeInstanceOf(ApiError);
    expect(done.settled && (done.error as ApiError).code).toBe('timeout');
    expect(done.settled && (done.error as ApiError).details).toEqual({ timeout_ms: 625_000 });
  });

  it('chat and language-pack posts use chat_s / language_pack_s; GETs keep default_s', async () => {
    const calls: string[] = [];
    const c = client(() => LOCAL_LIMITS, calls);
    const chat = track(c.chat({} as never));
    const pack = track(c.postPack({} as never));
    const rules = track(c.getRules());
    await jest.advanceTimersByTimeAsync(31_000);
    expect(rules().settled).toBe(true);
    expect(chat().settled).toBe(false);
    expect(pack().settled).toBe(false);
    await jest.advanceTimersByTimeAsync(625_000);
    expect(chat().settled && pack().settled).toBe(true);
  });

  it('no server limits (or a throwing getter) → the fixed 120 s analyze limit', async () => {
    for (const limits of [() => null, () => undefined, (): never => { throw new Error('boom'); }]) {
      const outcome = track(client(limits, []).analyze({ pages: [], target_language: 'en' } as never));
      await jest.advanceTimersByTimeAsync(TIMEOUT_MS.analyze - 1_000);
      expect(outcome().settled).toBe(false);
      await jest.advanceTimersByTimeAsync(2_000);
      expect(outcome().settled).toBe(true);
    }
  });

  it('an explicit per-call timeoutMs still wins', async () => {
    const outcome = track(client(() => LOCAL_LIMITS, []).analyze({ pages: [], target_language: 'en' } as never, { timeoutMs: 10_000 }));
    await jest.advanceTimersByTimeAsync(10_500);
    expect(outcome().settled).toBe(true);
  });
});

describe('the app client reads client_timeouts from the session config', () => {
  const realFetch = globalThis.fetch;
  beforeEach(() => {
    jest.useFakeTimers();
    useSession.getState().reset();
    setClient(null);
  });
  afterEach(() => {
    jest.useRealTimers();
    globalThis.fetch = realFetch;
    useSession.getState().reset();
    setClient(null);
  });

  it('uses /v1/config limits once the config is known', async () => {
    const calls: string[] = [];
    globalThis.fetch = hangingFetch(calls);
    useSession.getState().setServerConfig({ data_use_tier: 'local', client_timeouts: LOCAL_LIMITS } as ServerConfig);
    // A sample request is allowed before consent (CL-070), so the upload guard stays out of the way.
    const outcome = track(getClient().analyze({ pages: [], target_language: 'en', demo_sample_id: 'x' } as never));
    await jest.advanceTimersByTimeAsync(TIMEOUT_MS.analyze + 5_000);
    expect(calls).toHaveLength(1);
    expect(outcome().settled).toBe(false);
    await jest.advanceTimersByTimeAsync(625_000);
    expect(outcome().settled).toBe(true);
  });
});
