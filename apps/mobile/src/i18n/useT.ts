// `useT()` — the one way UI code reads copy (BUILD_PLAN §4.2; ARCHITECTURE §3 "useT.ts").
// English fallback and the one-time missing-key counter live in `store.ts`; this hook only
// subscribes to the active pack so components re-render when the language switches.

import { useCallback } from 'react';

import { type LoadedPack, translate, useI18n } from '@/i18n/store';

export type TFunction = (key: string, vars?: Record<string, string | number>) => string;

export function useT(): TFunction {
  const strings = useI18n((s) => s.pack.strings);
  return useCallback<TFunction>((key, vars) => translate(strings, key, vars), [strings]);
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
