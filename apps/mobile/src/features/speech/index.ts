// Speech feature (ARCHITECTURE §3 `features/speech/`): honest fallback line, a speaker that shows
// it, and the sequential "Read all aloud" player used by hear-it mode.

import { useCallback, useEffect, useState } from 'react';

import { usePackMeta, useT } from '@/i18n/useT';
import { resolveVoice, type ResolvedVoice } from '@/lib/tts';

import { fallbackNotice } from './fallback';

export { fallbackNotice, hasEnglishVoice, languageEntryFor, languageName } from './fallback';
export { SpeakRow, type SpeakRowProps } from './SpeakRow';
export { useSequentialSpeech, type SequentialSpeech } from './sequential';

/**
 * `onResolved` for `SpeakButton` + the notice to render under the speaker (or null). `lang` is the
 * language that speaker reads (e.g. `detected_language` for a paper's own words); defaults to the
 * UI pack.
 */
export function useTtsFallbackNotice(lang?: string): { notice: string | null; onResolved(v: ResolvedVoice): void } {
  const t = useT();
  const meta = usePackMeta();
  const speakLang = lang ?? meta.tag;
  const [notice, setNotice] = useState<string | null>(null);
  const onResolved = useCallback((v: ResolvedVoice) => setNotice(fallbackNotice(v, speakLang, t)), [speakLang, t]);
  return { notice, onResolved };
}

/**
 * The honest line for a screen whose speakers read in `lang` (S7 cards, "Read all aloud"): the
 * voice is resolved once up front, so the user learns before tapping that e.g. Dari will be read
 * with a Farsi voice. Null while resolving and when the pack's own voice exists.
 */
export function useVoiceNotice(lang: string): string | null {
  const t = useT();
  const [resolved, setResolved] = useState<ResolvedVoice | null>(null);
  useEffect(() => {
    let cancelled = false;
    void resolveVoice(lang)
      .then((v) => {
        if (!cancelled) setResolved(v);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [lang]);
  return fallbackNotice(resolved, lang, t);
}
