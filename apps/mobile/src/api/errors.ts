// `ApiError` — the one error type every API call throws (BUILD_PLAN §4.2; owner WP4 after M0).
// Data-only on day 0: WP4 may extend it (e.g. `fromResponse`), never rename fields or methods.

import type { ErrorBody, ErrorCode, ErrorResponse } from '@/api/types';

export type ApiErrorCode = ErrorCode | 'network' | 'timeout';

export type ApiErrorDetails = Record<string, string | number | boolean>;

export interface ApiErrorInit {
  code: ApiErrorCode;
  status: number;
  /** Developer message (English). Defaults to the code. */
  message?: string;
  /** Pack key; defaults to `err.<code>` (every ErrorCode has one in en.json). */
  userMessageKey?: string;
  retryAfterSeconds?: number | null;
  keyExhausted?: boolean;
  requestId?: string | null;
  details?: ApiErrorDetails | null;
}

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number;
  readonly userMessageKey: string;
  readonly retryAfterSeconds: number | null;
  readonly keyExhausted: boolean;
  readonly requestId: string | null;
  readonly details: ApiErrorDetails | null;

  constructor(init: ApiErrorInit) {
    super(init.message ?? init.code);
    this.name = 'ApiError';
    this.code = init.code;
    this.status = init.status;
    this.userMessageKey = init.userMessageKey ?? `err.${init.code}`;
    this.retryAfterSeconds = init.retryAfterSeconds ?? null;
    this.keyExhausted = init.keyExhausted ?? false;
    this.requestId = init.requestId ?? null;
    this.details = init.details ?? null;
  }

  /** Build from a parsed non-2xx `ErrorResponse` body (API_CONTRACT §0.1). */
  static fromErrorResponse(
    status: number,
    body: ErrorResponse,
    opts: { retryAfterHeader?: string | null } = {},
  ): ApiError {
    const e: ErrorBody = body.error;
    const headerSeconds = opts.retryAfterHeader ? Number.parseInt(opts.retryAfterHeader, 10) : NaN;
    return new ApiError({
      code: e.code,
      status,
      message: e.message,
      userMessageKey: e.user_message_key,
      retryAfterSeconds:
        e.retry_after_seconds ?? (Number.isFinite(headerSeconds) ? headerSeconds : null),
      keyExhausted: e.key_exhausted,
      requestId: e.request_id,
      details: e.details ?? null,
    });
  }

  /** 429 `quota_exhausted`, or any error where every key slot is exhausted for today. */
  isQuotaExhausted(): boolean {
    return this.code === 'quota_exhausted' || this.keyExhausted;
  }

  /** 428 `consent_required` — the client must show S2 and resend with X-Consent-Version. */
  isConsentRequired(): boolean {
    return this.code === 'consent_required';
  }

  /** 403 `unpaid_tier_real_documents_disabled` — only sample papers work on this deployment. */
  isUnpaidBlocked(): boolean {
    return this.code === 'unpaid_tier_real_documents_disabled';
  }

  /** 422 `content_blocked` — the provider refused the content; the user can retry or try a sample. */
  isBlocked(): boolean {
    return this.code === 'content_blocked';
  }

  /** True for transport failures the client produced itself (no server response). */
  isOffline(): boolean {
    return this.code === 'network' || this.code === 'timeout';
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

// ---------------------------------------------------------------------------------------------
// WP4 extensions (BUILD_PLAN §4.2 allows additions; nothing above is renamed).

/** HTTP status → the contract's ErrorCode for that status when the body could not be parsed
 *  (API_CONTRACT §0.1 table). Ambiguous statuses pick the more common code. */
export function codeForStatus(status: number): ApiErrorCode {
  switch (status) {
    case 400:
      return 'invalid_request';
    case 401:
      return 'unauthorized';
    case 403:
      return 'unpaid_tier_real_documents_disabled';
    case 404:
      return 'not_found';
    case 409:
      return 'pack_version_mismatch';
    case 413:
      return 'payload_too_large';
    case 415:
      return 'unsupported_media_type';
    case 422:
      return 'content_blocked';
    case 428:
      return 'consent_required';
    case 429:
      return 'rate_limited';
    case 502:
      return 'model_output_invalid';
    case 503:
      return 'upstream_unavailable';
    default:
      return 'internal';
  }
}

/** A non-2xx response whose body was not a valid `ErrorResponse` (proxy page, empty body…). */
export function apiErrorFromStatus(
  status: number,
  opts: { retryAfterHeader?: string | null; requestId?: string | null } = {},
): ApiError {
  const seconds = opts.retryAfterHeader ? Number.parseInt(opts.retryAfterHeader, 10) : NaN;
  return new ApiError({
    code: codeForStatus(status),
    status,
    message: `HTTP ${status} without an error envelope`,
    retryAfterSeconds: Number.isFinite(seconds) ? seconds : null,
    requestId: opts.requestId ?? null,
  });
}

/** Transport failure produced by the client itself (no response). Key `err.network`. */
export function networkError(cause?: unknown): ApiError {
  const e = new ApiError({
    code: 'network',
    status: 0,
    message: cause instanceof Error ? cause.message : 'network request failed',
  });
  return e;
}

/** Client-side timeout (120/60/30 s per API_CONTRACT §0). Key `err.timeout`. */
export function timeoutError(timeoutMs: number): ApiError {
  return new ApiError({
    code: 'timeout',
    status: 0,
    message: `request aborted after ${timeoutMs} ms`,
    details: { timeout_ms: timeoutMs },
  });
}

/** Wrap anything thrown while calling the API so callers always receive an `ApiError`. */
export function toApiError(value: unknown): ApiError {
  if (value instanceof ApiError) return value;
  if (value instanceof Error && value.name === 'AbortError') {
    return new ApiError({ code: 'timeout', status: 0, message: value.message });
  }
  return networkError(value);
}

/** `{minutes}` placeholder for `err.quota_exhausted` / `err.rate_limited` / `err.upstream_unavailable`:
 *  ceil(retry_after_seconds / 60), minimum 1 (PRODUCT_SPEC §5.4). */
export function retryMinutes(error: ApiError): number {
  const s = error.retryAfterSeconds ?? 60;
  return Math.max(1, Math.ceil(s / 60));
}

export interface ErrorCopyLimits {
  max_pages?: number;
  max_pdf_pages?: number;
  max_pdf_bytes?: number;
}

/** Placeholder values for the `err.*` string of this error (PRODUCT_SPEC §5.4). */
export function errorMessageVars(
  error: ApiError,
  limits: ErrorCopyLimits | null | undefined,
): Record<string, string | number> {
  const vars: Record<string, string | number> = { minutes: retryMinutes(error) };
  if (limits?.max_pages != null) vars.max_pages = limits.max_pages;
  if (limits?.max_pdf_pages != null) vars.max_pdf_pages = limits.max_pdf_pages;
  if (limits?.max_pdf_bytes != null) vars.max_pdf_mb = Math.floor(limits.max_pdf_bytes / 1048576);
  for (const [k, v] of Object.entries(error.details ?? {})) {
    if (typeof v === 'string' || typeof v === 'number') vars[k] = v;
  }
  return vars;
}
