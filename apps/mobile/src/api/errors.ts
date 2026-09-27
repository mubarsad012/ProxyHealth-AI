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
