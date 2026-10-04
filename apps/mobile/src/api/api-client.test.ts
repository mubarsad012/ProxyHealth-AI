// API client (BUILD_PLAN §5.5 step 4): headers, 428/403/429/422 → ApiError fields and
// user_message_key, the 304 pack path, timeout abort, network failure, envelope-less errors.

import { renderHook } from '@testing-library/react-native';

import { createClient, TIMEOUT_MS } from '@/api/client';
import { getClient, setClient } from '@/api/config';
import { ApiError, errorMessageVars, retryMinutes } from '@/api/errors';
import type { ErrorResponse } from '@/api/types';
import { useOnline } from '@/lib/network';
import { useSession } from '@/store/session';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

type FetchArgs = [string, RequestInit];

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

function envelope(code: string, extra: Partial<ErrorResponse['error']> = {}): ErrorResponse {
  return {
    error: {
      code: code as ErrorResponse['error']['code'],
      message: 'dev message',
      user_message_key: `err.${code}`,
      retry_after_seconds: null,
      key_exhausted: false,
      request_id: 'req-1',
      details: null,
      ...extra,
    },
  };
}

function setup(
  response: Response | (() => Promise<Response>),
  consent: string | null = '2026-10-04',
  refuseUnconsentedUploads = false,
) {
  const calls: FetchArgs[] = [];
  const fetchMock = jest.fn((url: string, init: RequestInit) => {
    calls.push([url, init]);
    return typeof response === 'function' ? response() : Promise.resolve(response);
  });
  const client = createClient({
    baseUrl: 'http://127.0.0.1:8026/',
    getConsentVersion: () => consent,
    refuseUnconsentedUploads,
    getInstallId: async () => 'install-123',
    appToken: 'tok',
    getLanguageTag: () => 'prs',
    fetch: fetchMock as unknown as typeof fetch,
    newRequestId: () => 'rid-1',
  });
  const header = (i: number, name: string) => new Headers(calls[i][1].headers).get(name);
  return { client, calls, header };
}

const analyzeReq = { pages: [], target_language: 'en' } as never;

describe('headers', () => {
  it('sends request id, install id, app token and language on every call', async () => {
    const { client, calls, header } = setup(jsonResponse(200, { status: 'ok' }));
    await client.health();
    expect(calls[0][0]).toBe('http://127.0.0.1:8026/health');
    expect(header(0, 'X-Request-Id')).toBe('rid-1');
    expect(header(0, 'X-Install-Id')).toBe('install-123');
    expect(header(0, 'X-App-Token')).toBe('tok');
    expect(header(0, 'Accept-Language')).toBe('prs');
    expect(header(0, 'X-Consent-Version')).toBeNull();
  });

  it('sends X-Consent-Version only on analyze / troubleshoot / chat', async () => {
    const { client, header } = setup(() => Promise.resolve(jsonResponse(200, {})));
    await client.analyze(analyzeReq);
    await client.troubleshoot({} as never);
    await client.chat({} as never);
    await client.matchResources({} as never);
    expect(header(0, 'X-Consent-Version')).toBe('2026-10-04');
    expect(header(1, 'X-Consent-Version')).toBe('2026-10-04');
    expect(header(2, 'X-Consent-Version')).toBe('2026-10-04');
    expect(header(3, 'X-Consent-Version')).toBeNull();
  });

  it('omits the install id before consent (CL-010)', async () => {
    const calls: FetchArgs[] = [];
    const client = createClient({
      baseUrl: 'http://x',
      getConsentVersion: () => null,
      getInstallId: async () => null,
      fetch: ((u: string, i: RequestInit) => {
        calls.push([u, i]);
        return Promise.resolve(jsonResponse(200, {}));
      }) as unknown as typeof fetch,
    });
    await client.getConfig();
    expect(new Headers(calls[0][1].headers).get('X-Install-Id')).toBeNull();
  });
});

describe('consent guard (CL-070 defence in depth)', () => {
  it('refuses analyze / troubleshoot / chat before consent without any network call', async () => {
    const { client, calls } = setup(jsonResponse(200, {}), null, true);
    for (const send of [
      () => client.analyze({ client_platform: 'web', pages: [{ mime_type: 'image/jpeg', data_base64: 'x' }] } as never),
      () => client.troubleshoot({ client_platform: 'web', screenshot: { mime_type: 'image/png', data_base64: 'x' } } as never),
      () => client.chat({ analysis: {}, question: 'What is this?' } as never),
    ]) {
      const err = (await send().catch((x: unknown) => x)) as ApiError;
      expect(err).toBeInstanceOf(ApiError);
      expect(err.isConsentRequired()).toBe(true);
      expect(err.userMessageKey).toBe('err.consent_required');
      expect(err.details).toEqual({ client_side: true });
    }
    expect(calls).toHaveLength(0);
  });

  it('lets sample requests (demo_sample_id) and ungated routes through before consent', async () => {
    const { client, calls, header } = setup(() => Promise.resolve(jsonResponse(200, {})), null, true);
    await client.analyze({ client_platform: 'web', pages: [], demo_sample_id: 'medicaid_address_confirmation' } as never);
    await client.troubleshoot({ client_platform: 'web', demo_sample_id: 'portal_login_error' } as never);
    await client.matchResources({} as never);
    await client.getConfig();
    expect(calls).toHaveLength(4);
    expect(header(0, 'X-Consent-Version')).toBeNull();
  });

  it('sends normally once consent is given', async () => {
    const { client, calls, header } = setup(jsonResponse(200, {}), '2026-10-04', true);
    await client.analyze(analyzeReq);
    expect(calls).toHaveLength(1);
    expect(header(0, 'X-Consent-Version')).toBe('2026-10-04');
  });

  it("the app's client has the guard on", async () => {
    useSession.getState().reset();
    const fetchSpy = jest.fn();
    const saved = globalThis.fetch;
    globalThis.fetch = fetchSpy as unknown as typeof fetch;
    try {
      setClient(null);
      const err = (await getClient().chat({ analysis: {}, question: 'x' } as never).catch((x: unknown) => x)) as ApiError;
      expect(err.isConsentRequired()).toBe(true);
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally {
      globalThis.fetch = saved;
      setClient(null);
    }
  });
});

describe('error mapping', () => {
  it('428 → consent_required', async () => {
    const { client } = setup(jsonResponse(428, envelope('consent_required')), null);
    const e = await client.analyze(analyzeReq).catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ApiError);
    const err = e as ApiError;
    expect(err.status).toBe(428);
    expect(err.isConsentRequired()).toBe(true);
    expect(err.userMessageKey).toBe('err.consent_required');
    expect(err.requestId).toBe('req-1');
  });

  it('403 → unpaid tier blocked', async () => {
    const { client } = setup(jsonResponse(403, envelope('unpaid_tier_real_documents_disabled')));
    const err = (await client.analyze(analyzeReq).catch((x: unknown) => x)) as ApiError;
    expect(err.isUnpaidBlocked()).toBe(true);
    expect(err.userMessageKey).toBe('err.unpaid_tier_real_documents_disabled');
  });

  it('429 quota_exhausted with Retry-After → minutes placeholder', async () => {
    const body = envelope('quota_exhausted', { key_exhausted: true, retry_after_seconds: 240, details: { tier: 'pro' } });
    const { client } = setup(jsonResponse(429, body, { 'Retry-After': '240' }));
    const err = (await client.analyze(analyzeReq).catch((x: unknown) => x)) as ApiError;
    expect(err.isQuotaExhausted()).toBe(true);
    expect(err.keyExhausted).toBe(true);
    expect(err.retryAfterSeconds).toBe(240);
    expect(retryMinutes(err)).toBe(4);
    expect(errorMessageVars(err, { max_pdf_bytes: 12582912 })).toMatchObject({ minutes: 4, max_pdf_mb: 12, tier: 'pro' });
  });

  it('429 quota_exhausted sets session.quotaCoolingUntil ≈ now + retry_after (CL-039); reset clears it', async () => {
    useSession.getState().reset();
    const before = Date.now();
    const body = envelope('quota_exhausted', { key_exhausted: true, retry_after_seconds: 240 });
    const { client } = setup(jsonResponse(429, body, { 'Retry-After': '240' }));
    await client.analyze(analyzeReq).catch(() => undefined);
    const until = Date.parse(useSession.getState().quotaCoolingUntil ?? '');
    expect(until).toBeGreaterThanOrEqual(before + 240_000);
    expect(until).toBeLessThanOrEqual(Date.now() + 240_000);
    useSession.getState().reset();
    expect(useSession.getState().quotaCoolingUntil).toBeNull();
  });

  it('429 rate_limited uses the Retry-After header when the body has no seconds', async () => {
    const { client } = setup(jsonResponse(429, envelope('rate_limited'), { 'Retry-After': '30' }));
    const err = (await client.chat({} as never).catch((x: unknown) => x)) as ApiError;
    expect(err.code).toBe('rate_limited');
    expect(err.isQuotaExhausted()).toBe(false);
    expect(err.retryAfterSeconds).toBe(30);
    expect(retryMinutes(err)).toBe(1);
  });

  it('422 content_blocked keeps details', async () => {
    const { client } = setup(jsonResponse(422, envelope('content_blocked', { details: { block_reason: 'spii' } })));
    const err = (await client.analyze(analyzeReq).catch((x: unknown) => x)) as ApiError;
    expect(err.isBlocked()).toBe(true);
    expect(err.userMessageKey).toBe('err.content_blocked');
    expect(err.details).toEqual({ block_reason: 'spii' });
  });

  it('a non-envelope error body maps by status', async () => {
    const { client } = setup(new Response('<html>bad gateway</html>', { status: 503, headers: { 'Retry-After': '60' } }));
    const err = (await client.getConfig().catch((x: unknown) => x)) as ApiError;
    expect(err.code).toBe('upstream_unavailable');
    expect(err.userMessageKey).toBe('err.upstream_unavailable');
    expect(err.retryAfterSeconds).toBe(60);
  });

  it('a transport failure becomes code network', async () => {
    const { client } = setup(() => Promise.reject(new TypeError('Network request failed')));
    const err = (await client.getConfig().catch((x: unknown) => x)) as ApiError;
    expect(err.code).toBe('network');
    expect(err.userMessageKey).toBe('err.network');
    expect(err.isOffline()).toBe(true);
  });
});

describe('language packs', () => {
  it('sends If-None-Match and returns the 304 path without a body', async () => {
    const { client, calls, header } = setup(new Response(null, { status: 304, headers: { ETag: '"abc"' } }));
    const res = await client.getPack('prs', { etag: '"abc"', packVersion: 'v1' });
    expect(calls[0][0]).toBe('http://127.0.0.1:8026/v1/language-packs/prs?pack_version=v1');
    expect(header(0, 'If-None-Match')).toBe('"abc"');
    expect(res).toEqual({ pack: null, status: 304, etag: '"abc"' });
  });

  it('returns the pack and its ETag on 200', async () => {
    const pack = { language_tag: 'prs', etag: 'e1', strings: { 'app.name': 'x' } };
    const { client } = setup(jsonResponse(200, pack, { ETag: 'e1' }));
    const res = await client.getPack('prs');
    expect(res.status).toBe(200);
    expect(res.pack?.language_tag).toBe('prs');
    expect(res.etag).toBe('e1');
  });
});

describe('timeouts', () => {
  afterEach(() => jest.useRealTimers());

  it('aborts after the per-endpoint timeout and throws code timeout', async () => {
    jest.useFakeTimers();
    const calls: FetchArgs[] = [];
    const client = createClient({
      baseUrl: 'http://x',
      getConsentVersion: () => '1',
      getInstallId: async () => 'i',
      fetch: ((u: string, init: RequestInit) => {
        calls.push([u, init]);
        return new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => {
            const e = new Error('aborted');
            e.name = 'AbortError';
            reject(e);
          });
        });
      }) as unknown as typeof fetch,
    });
    const p = client.analyze(analyzeReq).catch((x: unknown) => x);
    await Promise.resolve();
    await Promise.resolve();
    jest.advanceTimersByTime(TIMEOUT_MS.analyze + 1);
    const err = (await p) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe('timeout');
    expect(err.userMessageKey).toBe('err.timeout');
    expect(TIMEOUT_MS).toEqual({ analyze: 120000, troubleshoot: 60000, postPack: 60000, default: 30000 });
  });
});

describe('module seams used by WP5/WP6 tests', () => {
  it('api/offline resolves the bundled fixtures under jest (CL-033)', () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const offline = require('@/api/offline') as typeof import('@/api/offline');
    expect(offline.bundledFixtures().length).toBeGreaterThan(0);
  });

  it('useOnline unmounts cleanly when the network listener has no remove() (CL-034)', async () => {
    const { unmount } = await renderHook(() => useOnline());
    await expect(unmount()).resolves.toBeUndefined();
  });
});
