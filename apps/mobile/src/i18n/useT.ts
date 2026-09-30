// `useT()` — the one way UI code reads copy (BUILD_PLAN §4.2; ARCHITECTURE §3 "useT.ts").
// English fallback and the one-time missing-key counter live in `store.ts`; this hook only
// subscribes to the active pack so components re-render when the language switches.
//
// Bidi (D-26): in an RTL pack, copy whose template runs all left-to-right (an English fallback, a
// pseudo-localized "⟦rhg⟧ …" string) comes back FSI/LRI…PDI-wrapped (`translateForLayout` in
// `store.ts`), even when an RTL variable (a Dari language name) is inserted, so its punctuation
// stays at its own end inside the RTL paragraph. Missing keys (the key itself) are never wrapped.
// `useBidiText()` applies the strong-character rule (`isolateForLayout`) to server text.

import { useCallback } from 'react';

import { isolateForLayout } from '@/i18n/bidi';
import { type LoadedPack, translateForLayout, useI18n } from '@/i18n/store';

export type TFunction = (key: string, vars?: Record<string, string | number>) => string;

export { translateForLayout };

export function useT(): TFunction {
  const strings = useI18n((s) => s.pack.strings);
  const layout = useI18n((s) => s.pack.direction);
  return useCallback<TFunction>((key, vars) => translateForLayout(strings, layout, key, vars), [strings, layout]);
}

/**
 * For model / server text shown in the pack's layout (summary, demands, plan steps, chat answers):
 * text whose strong characters all run against the layout is FSI-isolated (e.g. a pseudo-translated
 * English sentence in an RTL pack, or an Arabic quote in an English one).
 */
export function useBidiText(): (text: string) => string {
  const layout = useI18n((s) => s.pack.direction);
  return useCallback((text: string) => isolateForLayout(text, layout), [layout]);
}

export interface PackMeta {
  tag: string;
  direction: LoadedPack['direction'];
  digitSystem: LoadedPack['digit_system'];
  fontHint: string | null;
  machineTranslated: boolean;
  /** Some keys fell back to English (`banner.partial_pack`). */
  partial: boolean;
  reviewedBy: string | null;
  ttsTag: string | null;
  ttsFallbackTag: string | null;
  nameNative: string;
  nameEn: string;
  tier: LoadedPack['tier'];
  origin: LoadedPack['origin'];
}

export function packMeta(pack: LoadedPack): PackMeta {
  return {
    tag: pack.tag,
    direction: pack.direction,
    digitSystem: pack.digit_system,
    fontHint: pack.font_hint,
    machineTranslated: pack.machine_translated,
    partial: pack.fallback_keys.length > 0,
    reviewedBy: pack.reviewed_by,
    ttsTag: pack.tts_tag,
    ttsFallbackTag: pack.tts_fallback_tag,
    nameNative: pack.name_native,
    nameEn: pack.name_en,
    tier: pack.tier,
    origin: pack.origin,
  };
}

/** The active pack's metadata the UI needs next to its strings (font, digits, banner flags).
 *  Selects the stable `pack` reference (zustand v5 selectors must not return fresh objects). */
export function usePackMeta(): PackMeta {
  const pack = useI18n((s) => s.pack);
  return packMeta(pack);
}

export { t } from '@/i18n/store';
