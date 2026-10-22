// I18nProvider + DirectionProvider (ARCHITECTURE §3.1, D-25, D-26, PRODUCT_SPEC S0).
// Start-up: English is active immediately (bundled); once settings are read, the chosen tag's
// bundled pack is applied synchronously, else the device-cached pack, then the server copy is
// revalidated in the background (ETag). A corrupted/missing cache for a non-bundled tag falls back
// to English and announces `a11y.pack_reset`. Nothing here blocks rendering for more than the
// settings read.

import { type ReactNode, useEffect } from 'react';
import { AccessibilityInfo } from 'react-native';

import { ensureServerConfig } from '@/api/config';
import { applyDirection } from '@/i18n/direction';
import { activatePack, packLoaderDeps } from '@/i18n/language';
import { loadKnownPack, readCachedPack } from '@/i18n/packLoader';
import { bundledPackFor, EN_PACK, t, useI18n } from '@/i18n/store';
import { useSettings, waitForSettings } from '@/store/settings';

let bootPromise: Promise<void> | null = null;

/** Apply the persisted language once per app session (idempotent; exported for tests). */
export function bootI18n(): Promise<void> {
  if (!bootPromise) {
    bootPromise = (async () => {
      await waitForSettings();
      const { languageTag } = useSettings.getState();
      const tag = languageTag || 'en';
      if (tag === 'en') {
        activatePack(EN_PACK, { persist: false });
        useI18n.getState().setReady(true);
        return;
      }
      const bundled = bundledPackFor(tag);
      const cached = bundled ? null : await readCachedPack(tag);
      const first = bundled ?? cached;
      if (first) {
        activatePack(first, { persist: false });
      } else {
        activatePack(EN_PACK, { persist: false });
      }
      useI18n.getState().setReady(true);
      if (bundled) return;
      // Revalidate / fetch in the background; failures keep what we have. Wait for /v1/config
      // first: it says whether the server can have this pack at all (no GET that can only 404,
      // `shouldGetFirst`) and gives the current base pack version.
      try {
        await ensureServerConfig();
        const fresh = await loadKnownPack(tag, packLoaderDeps());
        if (useI18n.getState().tag === tag || !first) activatePack(fresh, { persist: false });
      } catch {
        if (!first) {
          try {
            AccessibilityInfo.announceForAccessibility(t('a11y.pack_reset'));
          } catch {
            // announce is best-effort
          }
        }
      }
    })();
  }
  return bootPromise;
}

/** Test hook. */
export function resetI18nBootForTests(): void {
  bootPromise = null;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    void bootI18n();
  }, []);
  return <>{children}</>;
}

/**
 * Keeps `<html dir lang>` (web) and I18nManager (native) in step with the active pack. Waits for
 * `ready`: before bootI18n has applied the saved pack the active pack is the placeholder English
 * one, and syncing that would force LTR for the next start on an RTL user's relaunch.
 */
export function DirectionProvider({ children }: { children: ReactNode }) {
  const direction = useI18n((s) => s.pack.direction);
  const tag = useI18n((s) => s.pack.tag);
  const ready = useI18n((s) => s.ready);
  useEffect(() => {
    if (!ready) return;
    applyDirection(direction, tag);
  }, [direction, tag, ready]);
  return <>{children}</>;
}
