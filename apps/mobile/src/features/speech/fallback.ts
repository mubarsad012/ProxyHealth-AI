// Honest TTS fallback (D-26, ARCHITECTURE §3.1 "TTS wrapper"). `lib/tts.ts` (WP4) resolves the
// voice; this module turns the outcome into one fixed line and never claims a voice that is not
// there: `tts.no_voice` when the phone has no voice for the language at all (`noVoice`),
// `tts.fallback_offer` ("No {language} voice on this phone. Hear it in {fallback} or English?")
// when a related language's voice reads it, and `tts.fallback_offer_english` ("… Hear it in
// English?") when the fallback IS English, so the line never says "English or English".
// Language names come from the synced seed (`i18n/languages.ts`), in the UI pack's names.

import type { LanguageInfo } from '@/api/types';
import { LANGUAGES } from '@/i18n/languages';
import type { TFunction } from '@/i18n/useT';
import type { ResolvedVoice } from '@/lib/tts';

/** "No {language} voice on this phone. Hear it in English?" (keys-2c-mobilescan.json). */
export const FALLBACK_ENGLISH_KEY = 'tts.fallback_offer_english';

function baseTag(tag: string): string {
  return tag.toLowerCase().split(/[-_]/)[0];
}

function same(a: string | null | undefined, b: string | null | undefined): boolean {
  return Boolean(a && b && a.toLowerCase() === b.toLowerCase());
}

/**
 * The seed entry a BCP-47 tag belongs to: exact pack tag → exact `tts_tag` (so `fa-IR` is Persian
 * and `fa-AF` is Dari, not whichever `fa-*` comes first) → same base pack tag → same base `tts_tag`.
 */
export function languageEntryFor(tag: string | null | undefined): LanguageInfo | null {
  if (!tag) return null;
  const all = Object.values(LANGUAGES);
  return (
    LANGUAGES[tag] ??
    all.find((l) => same(l.tag, tag)) ??
    all.find((l) => same(l.tts_tag, tag)) ??
    all.find((l) => baseTag(l.tag) === baseTag(tag)) ??
    all.find((l) => baseTag(l.tts_tag ?? '') === baseTag(tag)) ??
    null
  );
}

/** Display name for a BCP-47 tag using the seed (native name), else the tag itself. */
export function languageName(tag: string | null | undefined): string {
  if (!tag) return '';
  return languageEntryFor(tag)?.name_native ?? tag;
}

/** The honest line, or null when the pack's own voice (or a regional voice of the same language)
 *  was used. Dari read with a Farsi (`fa-IR`) voice → "No دری voice on this phone. Hear it in
 *  فارسی or English?" (PRODUCT_SPEC J-A step 9). */
export function fallbackNotice(resolved: ResolvedVoice | null, packTag: string, t: TFunction): string | null {
  if (!resolved) return null;
  if (resolved.noVoice) return t('tts.no_voice', { language: languageName(packTag) });
  // `lib/tts` picks a same-base-language voice as the pack's "own" voice (a `fa-IR` voice for Dari's
  // `fa-AF`) without setting `usedFallbackTag` (CL-053 → WP4), so the voice's own language is checked
  // too: the line appears only when the seed maps that voice to a different pack language.
  const usedTag = resolved.usedFallbackTag ?? resolved.voice?.language.replace('_', '-') ?? null;
  if (!usedTag) return null;
  const own = LANGUAGES[packTag] ?? languageEntryFor(packTag);
  const used = languageEntryFor(usedTag);
  if (own && used && own.tag === used.tag) return null;
  if (!resolved.usedFallbackTag && (!own || !used)) return null;
  if (used?.tag === 'en' || baseTag(usedTag) === 'en') {
    return t(FALLBACK_ENGLISH_KEY, { language: own?.name_native ?? packTag });
  }
  return t('tts.fallback_offer', {
    language: own?.name_native ?? packTag,
    fallback: used?.name_native ?? usedTag,
  });
}

/** True when a voice exists for English (clerk card "Read aloud in English" is hidden otherwise). */
export function hasEnglishVoice(resolved: ResolvedVoice | null): boolean {
  if (!resolved || resolved.noVoice) return false;
  if (!resolved.voice) return true; // web / platforms without a voice list: the browser picks one
  return baseTag(resolved.voice.language) === 'en';
}
