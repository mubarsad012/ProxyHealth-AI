// Typed fetch wrapper (BUILD_PLAN §4.2, API_CONTRACT §0, ARCHITECTURE §3.1 "API client").
// Headers: X-Request-Id, X-Install-Id, X-Consent-Version (analyze/troubleshoot/chat), X-App-Token,
// Accept-Language, If-None-Match. Timeouts 120/60/30 s via AbortController. Every non-2xx becomes
// an `ApiError`; transport failures become `code: 'network'`, aborts `code: 'timeout'`.

import { ApiError, apiErrorFromStatus, timeoutError, toApiError } from '@/api/errors';
import { useSession } from '@/store/session';
import type {
  AnalysisResult,
  AnalyzeRequest,
  ChatAnswer,
  ChatRequest,
  DemoFixture,
  ErrorResponse,
  FeedbackRequest,
  FeedbackResponse,
  HealthResponse,
  LanguagePack,
  LanguagePackRequest,
  Resource,
  ResourceList,
  ResourceMatchRequest,
  ResourceMatchResponse,
  RulesResponse,
  QuickSheetRequest,
  ServerConfig,
  TroubleshootRequest,
  TroubleshootResult,
} from '@/api/types';

export const TIMEOUT_MS = {
  analyze: 120_000,
  troubleshoot: 60_000,
  postPack: 60_000,
  default: 30_000,
} as const;

export interface CreateClientOptions {
  baseUrl: string;
  /** The accepted `consent_version`, or null when no consent record exists. */
  getConsentVersion(): string | null;
  /**
   * CL-070 defence in depth: refuse `/v1/analyze`, `/v1/troubleshoot` and `/v1/chat` client-side
   * (no network call, `ApiError('consent_required')`) while there is no consent version and the
   * request carries no `demo_sample_id`, so a screen that forgets its own consent gate still never
   * uploads a user's photo, screenshot or paper text before S2. On for the app's client
   * (`api/config.ts`); test clients that simulate the server's 428 may leave it off.
   */
  refuseUnconsentedUploads?: boolean;
  /** The install id (may resolve null before consent — CL-010; the header is then omitted). */
  getInstallId(): Promise<string | null>;
  appToken?: string;
  /** Active UI language for `Accept-Language` (error copy fallback on the server). */
  getLanguageTag?(): string | null;
  /** Injected for tests; defaults to the global fetch. */
  fetch?: typeof fetch;
  /** Injected for tests; defaults to `crypto.randomUUID` when available. */
  newRequestId?(): string;
}

export interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

export interface GetPackOptions {
  packVersion?: string | null;
  etag?: string | null;
}

export interface GetPackResult {
  /** `null` when the server answered 304 (the cached copy is still current). */
  pack: LanguagePack | null;
  status: 200 | 304;
  etag: string | null;
}

export interface ListResourcesQuery {
  tag?: string;
  state?: string;
  language?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

export interface ApiClient {
  baseUrl: string;
  health(opts?: RequestOptions): Promise<HealthResponse>;
  getConfig(opts?: RequestOptions): Promise<ServerConfig>;
  getPack(tag: string, opts?: GetPackOptions & RequestOptions): Promise<GetPackResult>;
  postPack(req: LanguagePackRequest, opts?: RequestOptions): Promise<LanguagePack>;
  analyze(req: AnalyzeRequest, opts?: RequestOptions): Promise<AnalysisResult>;
  troubleshoot(req: TroubleshootRequest, opts?: RequestOptions): Promise<TroubleshootResult>;
  chat(req: ChatRequest, opts?: RequestOptions): Promise<ChatAnswer>;
  matchResources(req: ResourceMatchRequest, opts?: RequestOptions): Promise<ResourceMatchResponse>;
  listResources(q?: ListResourcesQuery, opts?: RequestOptions): Promise<ResourceList>;
  getResource(id: string, opts?: RequestOptions): Promise<Resource>;
  getRules(opts?: RequestOptions): Promise<RulesResponse>;
  quicksheetPdf(req: QuickSheetRequest, opts?: RequestOptions): Promise<Blob | Uint8Array>;
  feedback(req: FeedbackRequest, opts?: RequestOptions): Promise<FeedbackResponse>;
  listFixtures(opts?: RequestOptions): Promise<DemoFixture[]>;
  fixturePageUrl(id: string, n: number): string;
}

const CONSENT_ROUTES = new Set(['/v1/analyze', '/v1/troubleshoot', '/v1/chat']);

function hasDemoSampleId(body: unknown): boolean {
  if (!body || typeof body !== 'object') return false;
  const id = (body as { demo_sample_id?: unknown }).demo_sample_id;
  return typeof id === 'string' && id.trim().length > 0;
}

/** The client-side refusal (same code and copy as the server's 428; nothing was sent). */
export function consentRequiredLocally(path: string): ApiError {
  return new ApiError({
    code: 'consent_required',
    status: 428,
    message: `${path} refused before sending: no consent version and no demo_sample_id (CL-070).`,
    userMessageKey: 'err.consent_required',
    details: { client_side: true },
  });
}

function fallbackRequestId(): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  return `${Date.now().toString(16)}-${Math.random().toString(16).slice(2, 10)}`;
}

function joinUrl(base: string, path: string): string {
  return `${base.replace(/\/+$/, '')}${path}`;
}

function withQuery(path: string, q: Record<string, string | number | undefined>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null || v === '') continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length ? `${path}?${parts.join('&')}` : path;
}

/** Abort after `timeoutMs`, and also when the caller's own signal aborts. */
function timeoutSignal(
  timeoutMs: number,
  external?: AbortSignal,
): { signal: AbortSignal; clear(): void; timedOut(): boolean } {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onExternalAbort = () => controller.abort();
  if (external) {
    if (external.aborted) controller.abort();
    else external.addEventListener('abort', onExternalAbort, { once: true });
  }
  return {
    signal: controller.signal,
    clear: () => {
      clearTimeout(timer);
      external?.removeEventListener('abort', onExternalAbort);
    },
    timedOut: () => timedOut,
  };
}

async function parseErrorBody(res: Response): Promise<ErrorResponse | null> {
  try {
    const text = await res.text();
    if (!text) return null;
    const parsed: unknown = JSON.parse(text);
    if (
      parsed &&
      typeof parsed === 'object' &&
      'error' in parsed &&
      parsed.error &&
      typeof parsed.error === 'object' &&
      'code' in (parsed.error as object)
    ) {
      return parsed as ErrorResponse;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * CL-039: after a `quota_exhausted` error remember until when the helper is busy
 * (now + `retry_after_seconds`) so S3 can show `home.busy_until`. Memory only (session store).
 */
export function noteQuotaCooling(err: ApiError, now: number = Date.now()): void {
  if (!err.isQuotaExhausted()) return;
  const seconds = err.retryAfterSeconds;
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds <= 0) return;
  useSession.getState().setQuotaCoolingUntil(new Date(now + seconds * 1000).toISOString());
}

export function createClient(options: CreateClientOptions): ApiClient {
  const doFetch: typeof fetch = options.fetch ?? ((...args) => fetch(...args));
  const newRequestId = options.newRequestId ?? fallbackRequestId;

  async function buildHeaders(path: string, extra: Record<string, string>): Promise<Headers> {
    const headers = new Headers(extra);
    headers.set('Accept', 'application/json');
    headers.set('X-Request-Id', newRequestId());
    const installId = await options.getInstallId();
    if (installId) headers.set('X-Install-Id', installId);
    if (options.appToken) headers.set('X-App-Token', options.appToken);
    const lang = options.getLanguageTag?.();
    if (lang) headers.set('Accept-Language', lang);
    if (CONSENT_ROUTES.has(path)) {
      const consent = options.getConsentVersion();
      if (consent) headers.set('X-Consent-Version', consent);
    }
    return headers;
  }

  async function request(
    method: 'GET' | 'POST',
    path: string,
    body: unknown,
    opts: RequestOptions & { headers?: Record<string, string>; accept?: string } = {},
  ): Promise<Response> {
    const timeoutMs = opts.timeoutMs ?? TIMEOUT_MS.default;
    if (
      options.refuseUnconsentedUploads &&
      CONSENT_ROUTES.has(path) &&
      !options.getConsentVersion() &&
      !hasDemoSampleId(body)
    ) {
      throw consentRequiredLocally(path);
    }
    const headers = await buildHeaders(path, opts.headers ?? {});
    if (opts.accept) headers.set('Accept', opts.accept);
    if (body !== undefined) headers.set('Content-Type', 'application/json; charset=utf-8');
    const t = timeoutSignal(timeoutMs, opts.signal);
    let res: Response;
    try {
      res = await doFetch(joinUrl(options.baseUrl, path), {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: t.signal,
      });
    } catch (e) {
      t.clear();
      if (t.timedOut()) throw timeoutError(timeoutMs);
      throw toApiError(e);
    }
    t.clear();
    if (res.ok || res.status === 304) return res;
    const retryAfter = res.headers.get('Retry-After');
    const requestId = res.headers.get('X-Request-Id');
    const envelope = await parseErrorBody(res);
    const err = envelope
      ? ApiError.fromErrorResponse(res.status, envelope, { retryAfterHeader: retryAfter })
      : apiErrorFromStatus(res.status, { retryAfterHeader: retryAfter, requestId });
    noteQuotaCooling(err);
    throw err;
  }

  async function json<T>(res: Response): Promise<T> {
    try {
      return (await res.json()) as T;
    } catch (e) {
      throw new ApiError({
        code: 'internal',
        status: res.status,
        message: e instanceof Error ? e.message : 'invalid JSON body',
      });
    }
  }

  const get = async <T>(path: string, opts?: RequestOptions): Promise<T> =>
    json<T>(await request('GET', path, undefined, opts));
  const post = async <T>(path: string, body: unknown, opts?: RequestOptions): Promise<T> =>
    json<T>(await request('POST', path, body, opts));

  return {
    baseUrl: options.baseUrl,
    health: (opts) => get('/health', opts),
    getConfig: (opts) => get('/v1/config', opts),
    async getPack(tag, opts = {}) {
      const headers: Record<string, string> = {};
      if (opts.etag) headers['If-None-Match'] = opts.etag;
      const path = withQuery(`/v1/language-packs/${encodeURIComponent(tag)}`, {
        pack_version: opts.packVersion ?? undefined,
      });
      const res = await request('GET', path, undefined, { ...opts, headers });
      const etag = res.headers.get('ETag');
      if (res.status === 304) return { pack: null, status: 304, etag: etag ?? opts.etag ?? null };
      const pack = await json<LanguagePack>(res);
      return { pack, status: 200, etag: etag ?? pack.etag ?? null };
    },
    postPack: (req, opts) =>
      post('/v1/language-packs', req, { timeoutMs: TIMEOUT_MS.postPack, ...opts }),
    analyze: (req, opts) => post('/v1/analyze', req, { timeoutMs: TIMEOUT_MS.analyze, ...opts }),
    troubleshoot: (req, opts) =>
      post('/v1/troubleshoot', req, { timeoutMs: TIMEOUT_MS.troubleshoot, ...opts }),
    chat: (req, opts) => post('/v1/chat', req, opts),
    matchResources: (req, opts) => post('/v1/resources/match', req, opts),
    listResources: (q = {}, opts) =>
      get(
        withQuery('/v1/resources', {
          tag: q.tag,
          state: q.state,
          language: q.language,
          q: q.q,
          limit: q.limit,
          offset: q.offset,
        }),
        opts,
      ),
    getResource: (id, opts) => get(`/v1/resources/${encodeURIComponent(id)}`, opts),
    getRules: (opts) => get('/v1/rules', opts),
    async quicksheetPdf(req, opts) {
      const res = await request('POST', '/v1/quicksheet/pdf', req, {
        ...opts,
        accept: 'application/pdf',
      });
      if (typeof res.blob === 'function' && typeof Blob !== 'undefined') {
        try {
          return await res.blob();
        } catch {
          // fall through to bytes
        }
      }
      return new Uint8Array(await res.arrayBuffer());
    },
    feedback: (req, opts) => post('/v1/feedback', req, opts),
    listFixtures: (opts) => get('/v1/demo/fixtures', opts),
    fixturePageUrl: (id, n) =>
      joinUrl(options.baseUrl, `/v1/demo/fixtures/${encodeURIComponent(id)}/pages/${n}`),
  };
}
