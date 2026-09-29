// Honest TTS fallback (D-26, ARCHITECTURE §3.1 "TTS wrapper"). `lib/tts.ts` (WP4) resolves the
// voice; this module turns a fallback into the fixed line `tts.fallback_offer` ("No {language}
// voice on this phone. Hear it in {fallback} or English?") and never claims a voice that is not
// there. Language names come from the synced seed (`i18n/languages.ts`), in the UI pack's names.

import { LANGUAGES } from '@/i18n/languages';
import type { TFunction } from '@/i18n/useT';
import type { ResolvedVoice } from '@/lib/tts';

function baseTag(tag: string): string {
  return tag.toLowerCase().split(/[-_]/)[0];
}

/** Display name for a BCP-47 tag using the seed (native name first), else the tag itself. */
export function languageName(tag: string | null | undefined): string {
  if (!tag) return '';
  const exact = LANGUAGES[tag];
  if (exact) return exact.name_native;
  const base = baseTag(tag);
  const match = Object.values(LANGUAGES).find((l) => baseTag(l.tag) === base || baseTag(l.tts_tag ?? '') === base);
  return match?.name_native ?? tag;
}

/** The honest line, or null when the pack's own voice was used. */
export function fallbackNotice(resolved: ResolvedVoice | null, packTag: string, t: TFunction): string | null {
  if (!resolved || !resolved.usedFallbackTag) return null;
  const own = LANGUAGES[packTag];
  const fallback = resolved.usedFallbackTag;
  if (baseTag(fallback) === baseTag(own?.tts_tag ?? packTag)) return null;
  return t('tts.fallback_offer', {
    language: own?.name_native ?? languageName(packTag),
    fallback: languageName(fallback),
  });
}

/** True when a voice exists for English (clerk card "Read aloud in English" is hidden otherwise). */
export function hasEnglishVoice(resolved: ResolvedVoice | null): boolean {
  if (!resolved) return false;
  if (!resolved.voice) return true; // web / platforms without a voice list: the browser picks one
  return baseTag(resolved.voice.language) === 'en';
}
