// Pack loading chain (D-25, ARCHITECTURE §3 "packLoader.ts"):
//   bundled (`packs/`) → device cache (`kv`, keyed tag|pack_version) → GET /v1/language-packs/{tag}
//   with `If-None-Match` → POST /v1/language-packs for tags the server has not generated yet and
//   for typed language names. The GET is only sent when the server can have the pack
//   (`shouldGetFirst`): a miss is a 404 the browser logs as a console error. A
//   `409 pack_version_mismatch` is retried once after the caller refreshes `/v1/config`. Nothing
//   here touches React.

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { LanguagePack, ServerConfig } from '@/api/types';
import {
  bundledPackFor,
  EN_PACK,
  fromLanguagePack,
  languageInfoFor,
  type LoadedPack,
} from '@/i18n/store';
import { kv, KV_KEYS } from '@/storage/kv';

export interface PackLoaderDeps {
  client: ApiClient;
  /** The server's `base_pack_version` when known (from `/v1/config`); null when offline. */
  basePackVersion(): string | null;
  /** Called once on 409 so the base version can be refreshed before the single retry. */
  onVersionMismatch?(): Promise<void>;
  /** `/v1/config` (provider + the languages the server bundles); null/absent while unknown. */
  serverConfig?(): Pick<ServerConfig, 'provider' | 'languages'> | null;
}

/** The server keeps a generated pack only at this coverage or more (api `packs/cache.py`). */
export const SERVER_CACHE_MIN_COVERAGE = 0.9;

/**
 * Whether to try `GET /v1/language-packs/{tag}` before POST. The GET answers only for a pack the
 * server bundles or kept from an earlier generation; any other tag is a 404 (an expected cache
 * miss, but browsers log it as a console error). POST returns the server's existing pack too, so
 * skipping the GET never loses a pack, it only skips the ETag revalidation. GET first when
 * `/v1/config` says the server bundles the tag (a server newer than this app build), or when we
 * hold a copy the server may also have kept: a real provider (the mock never keeps generated
 * packs) and coverage ≥ 0.9. With no config yet, GET only to revalidate a copy we hold.
 */
export function shouldGetFirst(
  tag: string,
  cached: LoadedPack | null,
  config: Pick<ServerConfig, 'provider' | 'languages'> | null,
): boolean {
  if (!config) return cached !== null;
  if (config.languages?.some((l) => l.tag === tag && l.bundled)) return true;
  if (!cached || config.provider === 'mock') return false;
  return cached.coverage >= SERVER_CACHE_MIN_COVERAGE;
}

interface CachedPackEnvelope {
  pack: LoadedPack;
  cachedAt: string;
}

function cacheKey(tag: string): string {
  return `${KV_KEYS.packPrefix}${tag}`;
}

export async function readCachedPack(tag: string): Promise<LoadedPack | null> {
  const env = await kv.getJSON<CachedPackEnvelope>(cacheKey(tag));
  if (!env || !env.pack || typeof env.pack.strings !== 'object') {
    if (env) await kv.remove(cacheKey(tag)); // corrupted → drop silently (S0 rule)
    return null;
  }
  return { ...env.pack, origin: 'cache' };
}

export async function cachePack(pack: LoadedPack): Promise<void> {
  if (pack.tag === 'en') return; // English is always bundled
  await kv.setJSON(cacheKey(pack.tag), {
    pack: { ...pack, origin: 'cache' },
    cachedAt: new Date().toISOString(),
  } satisfies CachedPackEnvelope);
  const index = (await kv.getJSON<string[]>(KV_KEYS.packIndex)) ?? [];
  if (!index.includes(pack.tag)) await kv.setJSON(KV_KEYS.packIndex, [...index, pack.tag]);
}

export async function cachedPackTags(): Promise<string[]> {
  return (await kv.getJSON<string[]>(KV_KEYS.packIndex)) ?? [];
}

export async function clearPackCache(): Promise<void> {
  await kv.removeByPrefix(KV_KEYS.packPrefix);
  await kv.remove(KV_KEYS.packIndex);
}

/** GET a known tag; `null` when the server has no pack for it (404) and a POST should follow. */
async function fetchKnownPack(
  tag: string,
  cached: LoadedPack | null,
  deps: PackLoaderDeps,
): Promise<LoadedPack | null> {
  const base = deps.basePackVersion();
  const res = await deps.client.getPack(tag, {
    etag: cached?.etag ?? null,
    packVersion: base,
  });
  if (res.status === 304) return cached ? { ...cached, origin: 'cache' } : null;
  return res.pack ? fromLanguagePack(res.pack, 'server') : null;
}

async function postPack(query: string, hintTag: string | null, deps: PackLoaderDeps): Promise<LoadedPack> {
  const base = deps.basePackVersion() ?? EN_PACK.pack_version ?? '';
  const req = { language_query: query, pack_version: base, hint_tag: hintTag };
  try {
    const pack: LanguagePack = await deps.client.postPack(req, {});
    return fromLanguagePack(pack, 'generated');
  } catch (e) {
    if (e instanceof ApiError && e.code === 'pack_version_mismatch' && deps.onVersionMismatch) {
      await deps.onVersionMismatch();
      const retry = { ...req, pack_version: deps.basePackVersion() ?? base };
      const pack: LanguagePack = await deps.client.postPack(retry, {});
      return fromLanguagePack(pack, 'generated');
    }
    throw e;
  }
}

export interface LoadOptions {
  /** Skip the network entirely (offline / startup): bundled or cached only. */
  offlineOnly?: boolean;
}

/**
 * Load the pack for a known BCP-47 tag. Never throws for bundled/cached tags; throws `ApiError`
 * only when the tag is neither bundled nor cached and the network fails.
 */
export async function loadKnownPack(tag: string, deps: PackLoaderDeps, opts: LoadOptions = {}): Promise<LoadedPack> {
  if (tag === 'en') return EN_PACK;
  const bundled = bundledPackFor(tag);
  if (bundled) return bundled;
  const cached = await readCachedPack(tag);
  const base = deps.basePackVersion();
  const cacheCurrent = cached && (!base || cached.pack_version === base);
  if (opts.offlineOnly) {
    if (cached) return cached;
    throw new ApiError({ code: 'network', status: 0, message: `pack ${tag} not available offline` });
  }
  try {
    let pack: LoadedPack | null = null;
    if (shouldGetFirst(tag, cached, deps.serverConfig?.() ?? null)) {
      try {
        pack = await fetchKnownPack(tag, cached, deps);
      } catch (e) {
        // The server dropped its copy (restart, new base version): generate it again below.
        if (!(e instanceof ApiError && e.code === 'not_found')) throw e;
      }
    }
    if (!pack) pack = await postPack(tag, languageInfoFor(tag).tag, deps);
    await cachePack(pack);
    return pack;
  } catch (e) {
    if (cached && (cacheCurrent || (e instanceof ApiError && e.isOffline()))) return cached;
    throw e;
  }
}

/** Typed language name (S1 "My language is not here" → S1b). Always needs the network. */
export async function requestTypedLanguage(
  query: string,
  deps: PackLoaderDeps,
  hintTag: string | null = null,
): Promise<LoadedPack> {
  const pack = await postPack(query.trim(), hintTag, deps);
  await cachePack(pack);
  return pack;
}
