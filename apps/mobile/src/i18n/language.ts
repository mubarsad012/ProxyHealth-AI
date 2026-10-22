// Language switching (ARCHITECTURE §3.1 "i18n runtime", BUILD_PLAN §4.2 `useLanguage`).
// switch = (1) load pack (bundled → cache → server; typed names → POST), (2) set it active so
// `useDirection()` flips rows immediately, (3) native: I18nManager sync + restart prompt, (4) web:
// `<html dir lang>`. The chosen tag is persisted in `store/settings.ts`.

import { useCallback } from 'react';

import { getClient, refreshServerConfig } from '@/api/config';
import type { ApiClient } from '@/api/client';
import { toApiError } from '@/api/errors';
import type { LanguageInfo } from '@/api/types';
import { applyDirection } from '@/i18n/direction';
import { LANGUAGES } from '@/i18n/languages';
import { cachedPackTags, loadKnownPack, type PackLoaderDeps, requestTypedLanguage } from '@/i18n/packLoader';
import { bundledPackFor, languageInfoFor, type LoadedPack, useI18n } from '@/i18n/store';
import { useSession } from '@/store/session';
import { useSettings } from '@/store/settings';

export function packLoaderDeps(client: ApiClient = getClient()): PackLoaderDeps {
  return {
    client,
    basePackVersion: () => useSession.getState().serverConfig?.base_pack_version ?? null,
    onVersionMismatch: async () => {
      await refreshServerConfig(client);
    },
    serverConfig: () => useSession.getState().serverConfig,
  };
}

/** Make `pack` the active UI pack and persist the choice. Returns true when a native restart is pending. */
export function activatePack(pack: LoadedPack, opts: { persist?: boolean } = {}): boolean {
  useI18n.getState().setPack(pack);
  if (opts.persist !== false) {
    useSettings.getState().patch({ languageTag: pack.tag, languageDecided: true });
  }
  return applyDirection(pack.direction, pack.tag);
}

/** True for tags the app can load without asking the server to resolve a typed name. */
export async function isKnownTag(tag: string): Promise<boolean> {
  if (Object.prototype.hasOwnProperty.call(LANGUAGES, tag)) return true;
  if (bundledPackFor(tag)) return true;
  return (await cachedPackTags()).includes(tag);
}

export interface SwitchResult {
  pack: LoadedPack;
  restartPending: boolean;
}

/**
 * Switch to a known tag or a typed language name. Throws `ApiError` (network, 422
 * `language_unresolved`, 429, 503, timeout) only when nothing bundled or cached can be used.
 */
export async function switchLanguage(
  tagOrQuery: string,
  opts: { client?: ApiClient; signal?: AbortSignal } = {},
): Promise<SwitchResult> {
  const deps = packLoaderDeps(opts.client);
  const query = tagOrQuery.trim();
  const i18n = useI18n.getState();
  i18n.setLoading(true);
  try {
    const pack = (await isKnownTag(query))
      ? await loadKnownPack(query, deps)
      : await requestTypedLanguage(query, deps, null);
    if (opts.signal?.aborted) return { pack: useI18n.getState().pack, restartPending: false };
    const restartPending = activatePack(pack);
    return { pack, restartPending };
  } catch (e) {
    useI18n.getState().setError(toApiError(e));
    throw e;
  } finally {
    useI18n.getState().setLoading(false);
  }
}

export interface UseLanguage {
  tag: string;
  info: LanguageInfo;
  /** The active runtime pack (`LanguagePack` flattened with `LanguageInfo`, see i18n/store.ts). */
  pack: LoadedPack;
  loading: boolean;
  switchTo(tagOrQuery: string): Promise<void>;
}

export function useLanguage(): UseLanguage {
  const pack = useI18n((s) => s.pack);
  const loading = useI18n((s) => s.loading);
  const switchTo = useCallback(async (tagOrQuery: string) => {
    await switchLanguage(tagOrQuery);
  }, []);
  const known = LANGUAGES[pack.tag];
  const info: LanguageInfo = known ?? {
    ...languageInfoFor(pack.tag),
    name_native: pack.name_native,
    name_en: pack.name_en,
    direction: pack.direction,
    script: pack.script,
    digit_system: pack.digit_system,
    font_hint: pack.font_hint,
    tier: pack.tier,
    machine_translated: pack.machine_translated,
    tts_tag: pack.tts_tag,
    tts_fallback_tag: pack.tts_fallback_tag,
  };
  return { tag: pack.tag, info, pack, loading, switchTo };
}
