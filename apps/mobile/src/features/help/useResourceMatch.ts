// `useResourceMatch` (BUILD_PLAN §4.2 seam): POST /v1/resources/match with a per-document memory
// cache. A cached answer is returned at once (`cached: true`) and not re-fetched unless `refresh()`
// is called; on a network error the last list for this paper is kept (`help.offline_cached`).
// State is derived from the request key during render (no synchronous setState in effects).

import { useEffect, useState } from 'react';

import { useApi } from '@/api/config';
import { type ApiError, toApiError } from '@/api/errors';
import type { ResourceMatchRequest, ResourceMatchResponse } from '@/api/types';

import { cachedMatch, lastMatchForDocument, matchKey, rememberMatch } from './request';

export interface ResourceMatchState {
  data: ResourceMatchResponse | null;
  loading: boolean;
  error: ApiError | null;
  cached: boolean;
}

export interface ResourceMatchExtras {
  /** The request failed for lack of connectivity (network / timeout). */
  offline: boolean;
  /** Ask the server again, ignoring the cache. */
  refresh(): void;
}

export interface UseResourceMatchOptions {
  /** Cache the answer as "the last list for this paper" (analysis id). */
  documentId?: string | null;
}

interface Settled extends ResourceMatchState {
  key: string;
  nonce: number;
}

export function isOfflineError(error: ApiError | null): boolean {
  return error?.code === 'network' || error?.code === 'timeout';
}

export function useResourceMatch(
  req: ResourceMatchRequest | null,
  opts: UseResourceMatchOptions = {},
): ResourceMatchState & ResourceMatchExtras {
  const client = useApi();
  const key = req ? matchKey(req) : null;
  const documentId = opts.documentId ?? null;
  const [nonce, setNonce] = useState(0);
  const [settled, setSettled] = useState<Settled | null>(null);
  const hit = key ? cachedMatch(JSON.parse(key) as ResourceMatchRequest) : null;
  const useHit = Boolean(hit) && nonce === 0;
  const done = settled !== null && settled.key === key && settled.nonce === nonce;

  useEffect(() => {
    if (!key || useHit || done) return;
    const current = JSON.parse(key) as ResourceMatchRequest;
    let cancelled = false;
    client
      .matchResources(current)
      .then((res) => {
        rememberMatch(current, res, documentId);
        if (!cancelled) setSettled({ key, nonce, data: res, loading: false, error: null, cached: false });
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        const last = cachedMatch(current) ?? lastMatchForDocument(documentId);
        setSettled({ key, nonce, data: last, loading: false, error: toApiError(e), cached: Boolean(last) });
      });
    return () => {
      cancelled = true;
    };
  }, [client, key, nonce, useHit, done, documentId]);

  const refresh = () => setNonce((n) => n + 1);

  let state: ResourceMatchState;
  if (!key) state = { data: null, loading: false, error: null, cached: false };
  else if (done && settled) state = settled;
  else if (useHit) state = { data: hit, loading: false, error: null, cached: true };
  else state = { data: hit ?? (settled?.key === key ? settled.data : null), loading: true, error: null, cached: Boolean(hit) };
  return { ...state, offline: isOfflineError(state.error), refresh };
}
