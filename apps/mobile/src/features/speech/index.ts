// Speech feature (ARCHITECTURE §3 `features/speech/`): honest fallback line, a speaker that shows
// it, and the sequential "Read all aloud" player used by hear-it mode.

import { useCallback, useState } from 'react';

import { usePackMeta, useT } from '@/i18n/useT';
import type { ResolvedVoice } from '@/lib/tts';

import { fallbackNotice } from './fallback';

export { fallbackNotice, hasEnglishVoice, languageName } from './fallback';
export { SpeakRow, type SpeakRowProps } from './SpeakRow';
export { useSequentialSpeech, type SequentialSpeech } from './sequential';

/** `onResolved` for `SpeakButton` + the notice to render under the speaker (or null). */
export function useTtsFallbackNotice(): { notice: string | null; onResolved(v: ResolvedVoice): void } {
  const t = useT();
  const meta = usePackMeta();
  const [notice, setNotice] = useState<string | null>(null);
  const onResolved = useCallback((v: ResolvedVoice) => setNotice(fallbackNotice(v, meta.tag, t)), [meta.tag, t]);
  return { notice, onResolved };
}
