// i18n runtime store (ARCHITECTURE §3, D-25): the active pack, its direction / digit system /
// font hint, loading state and the restart-pending flag for native RTL switches. zustand, not
// persisted (the chosen tag lives in `store/settings.ts`; cached packs live in `kv`).

import { create } from 'zustand';

import type { ApiError } from '@/api/errors';
import type { DigitSystem, Direction, LanguageInfo, LanguagePack, PackTier } from '@/api/types';
import { isolateTemplateForLayout, type LayoutDir } from '@/i18n/bidi';
import { extraLanguageInfo } from '@/i18n/languageNames';
import { LANGUAGES } from '@/i18n/languages';
import { bundledPacks } from '@/i18n/packs';

export type PackOrigin = 'bundled' | 'cache' | 'server' | 'generated';

/** The pack shape the UI consumes: `LanguagePack` (API_CONTRACT §3.3) flattened with the
 *  `LanguageInfo` fields a bundled pack does not carry. */
export interface LoadedPack {
  tag: string;
  name_native: string;
  name_en: string;
  direction: Direction;
  script: string | null;
  digit_system: DigitSystem;
  font_hint: string | null;
  tier: PackTier;
  origin: PackOrigin;
  pack_version: string | null;
  etag: string | null;
  strings: Record<string, string>;
  fallback_keys: string[];
  coverage: number;
  machine_translated: boolean;
  reviewed_by: string | null;
  tts_tag: string | null;
  tts_fallback_tag: string | null;
}

function isLanguagePackShaped(raw: unknown): raw is LanguagePack {
  return (
    !!raw &&
    typeof raw === 'object' &&
    'strings' in raw &&
    typeof (raw as { strings: unknown }).strings === 'object'
  );
}

/** Fallback metadata for a tag the seed does not know (typed languages, `x-` tags). */
export function unknownLanguageInfo(tag: string, name?: string): LanguageInfo {
  return {
    tag,
    name_native: name ?? tag,
    name_en: name ?? tag,
    direction: 'ltr',
    script: null,
    digit_system: 'western',
    font_hint: null,
    tier: 3,
    bundled: false,
    machine_translated: true,
    tts_tag: null,
    tts_fallback_tag: null,
  };
}

/** Seed info for `tag`; resource-only tags without a pack (zh, hmn, km…) get their names from
 *  `languageNames.ts` (never added to the language grid); anything else is "unknown". */
export function languageInfoFor(tag: string): LanguageInfo {
  return LANGUAGES[tag] ?? extraLanguageInfo(tag) ?? unknownLanguageInfo(tag);
}

/** Convert an API `LanguagePack` into the runtime shape. */
export function fromLanguagePack(pack: LanguagePack, origin: PackOrigin): LoadedPack {
  return {
    tag: pack.language_tag,
    name_native: pack.language_name_native,
    name_en: pack.language_name_en,
    direction: pack.direction,
    script: pack.script ?? null,
    digit_system: pack.digit_system,
    font_hint: pack.font_hint ?? null,
    tier: pack.tier,
    origin,
    pack_version: pack.pack_version,
    etag: pack.etag,
    strings: pack.strings,
    fallback_keys: pack.fallback_keys ?? [],
    coverage: pack.coverage,
    machine_translated: pack.machine_translated,
    reviewed_by: pack.reviewed_by ?? null,
    tts_tag: pack.tts_tag ?? null,
    tts_fallback_tag: pack.tts_fallback_tag ?? null,
  };
}

/** A bundled pack file is either the flat `en.json` map or a full `LanguagePack` dump (WP1). */
export function fromBundled(tag: string, raw: unknown): LoadedPack {
  if (isLanguagePackShaped(raw)) return { ...fromLanguagePack(raw, 'bundled'), origin: 'bundled' };
  const info = languageInfoFor(tag);
  const strings = (raw ?? {}) as Record<string, string>;
  return {
    tag,
    name_native: info.name_native,
    name_en: info.name_en,
    direction: info.direction,
    script: info.script ?? null,
    digit_system: info.digit_system,
    font_hint: info.font_hint ?? null,
    tier: info.tier,
    origin: 'bundled',
    pack_version: null,
    etag: null,
    strings,
    fallback_keys: [],
    coverage: 1,
    machine_translated: info.machine_translated,
    reviewed_by: null,
    tts_tag: info.tts_tag ?? null,
    tts_fallback_tag: info.tts_fallback_tag ?? null,
  };
}

/** The English base pack: always bundled, never machine translated (D-25). */
export const EN_PACK: LoadedPack = fromBundled('en', bundledPacks.en);

/** The base strings every lookup falls back to. */
export const BASE_STRINGS: Record<string, string> = EN_PACK.strings;

export function bundledPackFor(tag: string): LoadedPack | null {
  const raw = Object.prototype.hasOwnProperty.call(bundledPacks, tag) ? bundledPacks[tag] : null;
  return raw ? fromBundled(tag, raw) : null;
}

export interface I18nState {
  tag: string;
  pack: LoadedPack;
  loading: boolean;
  error: ApiError | null;
  /** Native only: `I18nManager` direction differs from the pack until the app restarts (D-26). */
  restartPending: boolean;
  /** True once the initial pack decision (settings or device locale) has been applied. */
  ready: boolean;
}

export interface I18nActions {
  setPack(pack: LoadedPack): void;
  setLoading(loading: boolean): void;
  setError(error: ApiError | null): void;
  setRestartPending(pending: boolean): void;
  setReady(ready: boolean): void;
}

export type I18nStore = I18nState & I18nActions;

export const useI18n = create<I18nStore>()((set) => ({
  tag: 'en',
  pack: EN_PACK,
  loading: false,
  error: null,
  restartPending: false,
  ready: false,
  setPack: (pack) => set({ pack, tag: pack.tag, error: null }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  setRestartPending: (restartPending) => set({ restartPending }),
  setReady: (ready) => set({ ready }),
}));

// --- string lookup ---------------------------------------------------------------------------

const PLACEHOLDER = /\{([a-zA-Z0-9_]+)\}/g;

export function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(PLACEHOLDER, (whole, name: string) => {
    const v = vars[name];
    return v === undefined || v === null ? whole : String(v);
  });
}

const reportedMissing = new Set<string>();
let missingListener: ((key: string) => void) | null = null;

/** One-time missing-key report hook (counts only — D-31). `features/feedback` may subscribe. */
export function onMissingKey(listener: ((key: string) => void) | null): void {
  missingListener = listener;
}

export function missingKeysSoFar(): string[] {
  return [...reportedMissing];
}

function reportMissing(key: string): void {
  if (reportedMissing.has(key)) return;
  reportedMissing.add(key);
  missingListener?.(key);
}

/** The template `translate` uses for `key`: the pack's own string, else English, else null. */
function templateFor(strings: Record<string, string>, key: string): string | null {
  const own = strings[key];
  if (typeof own === 'string' && own.length > 0) return own;
  const base = BASE_STRINGS[key];
  return typeof base === 'string' ? base : null;
}

/** Look up `key` in `strings`, then English, then return the key itself. */
export function translate(
  strings: Record<string, string>,
  key: string,
  vars?: Record<string, string | number>,
): string {
  const template = templateFor(strings, key);
  if (template !== null) return interpolate(template, vars);
  reportMissing(key);
  return key;
}

/**
 * `translate` plus the RTL isolation rule (D-26): in an RTL layout, copy whose template (the pack
 * string or its English fallback, placeholders removed) runs all left-to-right comes back
 * FSI/LRI…PDI-wrapped, whatever script the inserted variables use (`isolateTemplateForLayout`).
 * Missing keys (the key itself) are never wrapped. Pure; `useT`, `t` and tests share it.
 */
export function translateForLayout(
  strings: Record<string, string>,
  layout: LayoutDir,
  key: string,
  vars?: Record<string, string | number>,
): string {
  const text = translate(strings, key, vars);
  if (layout !== 'rtl') return text;
  const template = templateFor(strings, key);
  return template === null ? text : isolateTemplateForLayout(template, text, 'rtl');
}

/** Non-hook translation for code outside React (stores, TTS chunks, notifications). Same RTL
 *  isolation rule as `useT` (`translateForLayout`). */
export function t(key: string, vars?: Record<string, string | number>): string {
  const pack = useI18n.getState().pack;
  return translateForLayout(pack.strings, pack.direction, key, vars);
}

/** True when the active pack itself (not the English fallback) has this key. */
export function hasOwnKey(key: string): boolean {
  const s = useI18n.getState().pack.strings[key];
  return typeof s === 'string' && s.length > 0;
}

/** True when the active pack or the English base has this key (server-sent keys may be new). */
export function keyExists(key: string): boolean {
  return hasOwnKey(key) || typeof BASE_STRINGS[key] === 'string';
}
