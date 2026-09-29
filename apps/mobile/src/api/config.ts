// API client singleton + `/v1/config` (ARCHITECTURE §3 "config.ts", PRODUCT_SPEC S0).
// The server config is cached in `kv` so the app can reason about the tier offline; when the
// server is unreachable and nothing is cached the tier is `'unknown'` (scan disabled, samples on).

import { createContext, createElement, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';

import { type ApiClient, createClient } from '@/api/client';
import { ApiError, toApiError } from '@/api/errors';
import type { ServerConfig } from '@/api/types';
import { useI18n } from '@/i18n/store';
import { getInstallId } from '@/lib/ids';
import { env } from '@/lib/platform';
import { consentStore } from '@/storage/consent';
import { kv, KV_KEYS } from '@/storage/kv';
import { currentConsentVersion, type UiTier, useSession } from '@/store/session';

let singleton: ApiClient | null = null;

/**
 * CL-010 (Apple 5.1.1(ii)): the install id is created lazily at consent, not at first launch.
 * Before any consent decision exists the header is simply omitted.
 */
export async function installIdForRequests(): Promise<string | null> {
  const existing = await kv.get(KV_KEYS.installId);
  if (existing) return existing;
  const decision = await consentStore.getDecision();
  if (decision === 'none') return null;
  return getInstallId();
}

export function getClient(): ApiClient {
  if (!singleton) {
    singleton = createClient({
      baseUrl: env.apiUrl,
      getConsentVersion: currentConsentVersion,
      getInstallId: installIdForRequests,
      appToken: env.appToken || undefined,
      getLanguageTag: () => useI18n.getState().tag,
    });
  }
  return singleton;
}

/** Tests / developer settings: swap the client (e.g. a new base URL). */
export function setClient(client: ApiClient | null): void {
  singleton = client;
}

const ApiContext = createContext<ApiClient | null>(null);

export function useApi(): ApiClient {
  return useContext(ApiContext) ?? getClient();
}

// --- server config -----------------------------------------------------------------------------

export async function loadCachedServerConfig(): Promise<ServerConfig | null> {
  const cached = await kv.getJSON<ServerConfig>(KV_KEYS.serverConfig);
  if (cached && typeof cached.data_use_tier === 'string') return cached;
  return null;
}

/** GET /v1/config, cache it and push it into the session store. Returns null when unreachable. */
export async function refreshServerConfig(client: ApiClient = getClient()): Promise<ServerConfig | null> {
  try {
    const config = await client.getConfig();
    await kv.setJSON(KV_KEYS.serverConfig, config);
    useSession.getState().setServerConfig(config);
    return config;
  } catch {
    return null;
  }
}

export interface ServerConfigState {
  config: ServerConfig | null;
  tier: UiTier;
  /** True while the first network attempt of this session is in flight. */
  loading: boolean;
  error: ApiError | null;
  /** True when `config` came from the device cache and the server has not answered yet. */
  cached: boolean;
  refresh(): Promise<ServerConfig | null>;
}

let firstFetch: Promise<ServerConfig | null> | null = null;

/** Starts the cached-then-network config load once per app session. */
export function ensureServerConfig(client: ApiClient = getClient()): Promise<ServerConfig | null> {
  if (!firstFetch) {
    firstFetch = (async () => {
      const cached = await loadCachedServerConfig();
      if (cached && !useSession.getState().serverConfig) {
        useSession.getState().setServerConfig(cached);
      }
      const fresh = await refreshServerConfig(client);
      if (!fresh && !cached) useSession.getState().setTier('unknown');
      return fresh ?? cached;
    })();
  }
  return firstFetch;
}

/** Forget the once-per-session config load ("Delete everything", tests). */
export function resetServerConfigSession(): void {
  firstFetch = null;
}

export const resetServerConfigForTests = resetServerConfigSession;

export function useServerConfig(): ServerConfigState {
  const client = useApi();
  const config = useSession((s) => s.serverConfig);
  const tier = useSession((s) => s.tier);
  const [loading, setLoading] = useState(() => !useSession.getState().serverConfig);
  const [error, setError] = useState<ApiError | null>(null);
  const [fresh, setFresh] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const c = await client.getConfig();
      await kv.setJSON(KV_KEYS.serverConfig, c);
      useSession.getState().setServerConfig(c);
      setFresh(true);
      setError(null);
      return c;
    } catch (e) {
      const err = toApiError(e);
      setError(err);
      if (!useSession.getState().serverConfig) useSession.getState().setTier('unknown');
      return null;
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    let cancelled = false;
    ensureServerConfig(client)
      .then((c) => {
        if (!cancelled) setFresh(Boolean(c));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  return { config, tier, loading, error, cached: Boolean(config) && !fresh, refresh };
}

/** Provides the client and kicks off the config load. Renders children immediately. */
export function ApiConfigProvider({ children, client }: { children: ReactNode; client?: ApiClient }) {
  const value = client ?? getClient();
  useEffect(() => {
    void ensureServerConfig(value);
  }, [value]);
  return createElement(ApiContext.Provider, { value }, children);
}
