// On-device text-to-speech (D-26, BUILD_PLAN §4.2 "TTS"). expo-speech works on Android, iOS and
// web (browser SpeechSynthesis). Verified against https://docs.expo.dev/versions/v57.0.0/sdk/speech/ :
// `speak(text, {language, voice, rate, onDone, onStopped, onError})`, `stop()`,
// `getAvailableVoicesAsync() → Voice{identifier,name,language,quality}`, `maxSpeechInputLength`.
// Voices are chosen honestly: exact language → same base language → the seed's fallback tag →
// none. Whenever the chosen voice belongs to a different pack language than the one asked for (a
// Farsi `fa-IR` voice for Dari, CL-053), `usedFallbackTag` names it so the UI shows the honest line
// (`tts.fallback_offer`, D-26). When no voice exists for the language (or the device has none),
// NOTHING is spoken — except that a Latin-script language may fall back to a (reported) English
// voice: text in another script is never handed to an English voice, which would read Dari /
// Pashto / Arabic as silence or nonsense (`noVoice`, line `tts.no_voice`). Long text is spoken in
// sentence chunks.

import * as Speech from 'expo-speech';
import { create } from 'zustand';

import type { LanguageInfo } from '@/api/types';
import { LANGUAGES } from '@/i18n/languages';
import { useSettings } from '@/store/settings';

export type Voice = Speech.Voice;

interface SpeakingState {
  speaking: boolean;
  /** Identifies the utterance currently playing (SpeakButton compares its own id). */
  utteranceId: string | null;
  set(speaking: boolean, utteranceId: string | null): void;
}

const useSpeakingStore = create<SpeakingState>()((set) => ({
  speaking: false,
  utteranceId: null,
  set: (speaking, utteranceId) => set({ speaking, utteranceId }),
}));

export function useSpeaking(): boolean {
  return useSpeakingStore((s) => s.speaking);
}

export function useSpeakingId(): string | null {
  return useSpeakingStore((s) => s.utteranceId);
}

let voicesPromise: Promise<Voice[]> | null = null;

/** Browsers that never fire `voiceschanged` would otherwise keep expo-speech waiting forever. */
const VOICES_TIMEOUT_MS = 4000;

export function getVoices(): Promise<Voice[]> {
  if (!voicesPromise) {
    let timer: ReturnType<typeof setTimeout> | null = null;
    const timeout = new Promise<Voice[]>((resolve) => {
      timer = setTimeout(() => resolve([]), VOICES_TIMEOUT_MS);
    });
    const load = Speech.getAvailableVoicesAsync()
      .then((v) => (Array.isArray(v) ? v : []))
      .catch(() => [] as Voice[]);
    const p: Promise<Voice[]> = Promise.race([load, timeout]).then((v) => {
      if (timer) clearTimeout(timer);
      // An empty list (engine still starting, no voices yet) is not cached: ask again next time.
      if (!v.length && voicesPromise === p) voicesPromise = null;
      return v;
    });
    voicesPromise = p;
  }
  return voicesPromise;
}

/** Tests: forget the cached voice list. */
export function resetVoicesForTests(): void {
  voicesPromise = null;
}

function baseLang(tag: string): string {
  return tag.split(/[-_]/)[0].toLowerCase();
}

function pickForTag(voices: Voice[], tag: string): Voice | null {
  const exact = voices.filter((v) => v.language.replace('_', '-').toLowerCase() === tag.toLowerCase());
  const same = exact.length ? exact : voices.filter((v) => baseLang(v.language) === baseLang(tag));
  if (!same.length) return null;
  return same.find((v) => v.quality === Speech.VoiceQuality.Enhanced) ?? same[0];
}

export interface ResolvedVoice {
  voice: Voice | null;
  /** Set when the voice used belongs to a different pack language than the one asked for (per the
   *  language seed): e.g. `fa-IR` (Farsi) reading Dari. Null for the language's own voice, including
   *  a regional voice of the same language (`es-MX` for Spanish). */
  usedFallbackTag: string | null;
  /** The BCP-47 tag to pass as `language`. */
  languageTag: string;
  /** True when this device has no voice for the language nor its seed fallback (or no voices at
   *  all): `speak()` then says nothing and the UI shows `tts.no_voice`. */
  noVoice?: boolean;
}

function normTag(tag: string): string {
  return tag.replace(/_/g, '-');
}

function sameTag(a: string | null | undefined, b: string | null | undefined): boolean {
  return Boolean(a && b && a.toLowerCase() === b.toLowerCase());
}

/**
 * The seed language a BCP-47 tag belongs to: exact pack tag → exact `tts_tag` (so `fa-IR` is Persian
 * and `fa-AF` is Dari) → same base pack tag → same base `tts_tag`. Null when the seed has none.
 */
export function languageForTag(tag: string | null | undefined): LanguageInfo | null {
  if (!tag) return null;
  const t = normTag(tag);
  const all = Object.values(LANGUAGES);
  return (
    LANGUAGES[t] ??
    all.find((l) => sameTag(l.tag, t)) ??
    all.find((l) => sameTag(l.tts_tag, t)) ??
    all.find((l) => baseLang(l.tag) === baseLang(t)) ??
    all.find((l) => Boolean(l.tts_tag) && baseLang(l.tts_tag ?? '') === baseLang(t)) ??
    null
  );
}

/** Native name for the "no voice" line (the seed's name, else the tag itself). */
export function ttsLanguageName(lang: string): string {
  return languageForTag(lang)?.name_native ?? lang;
}

/** Map a pack tag to a voice. Uses the seed's `tts_tag` / `tts_fallback_tag` (D-26). */
export function resolveVoiceFrom(voices: Voice[], lang: string): ResolvedVoice {
  const info = LANGUAGES[lang];
  const primary = info?.tts_tag ?? lang;
  const fallback = info?.tts_fallback_tag ?? null;
  const own = pickForTag(voices, primary) ?? (info?.tts_tag ? null : pickForTag(voices, lang));
  const chosen = own ?? (fallback ? pickForTag(voices, fallback) : null);
  const wanted = info ?? languageForTag(lang);
  if (!chosen) {
    // Last resort, Latin-script languages only (Spanish, Haitian Creole…): an English voice can
    // still sound the letters out, and it is reported as a fallback. Never for Arabic-script,
    // Ethiopic, Myanmar, Rohingya, CJK… text, which an English voice reads as silence or nonsense.
    const en = wanted?.script === 'Latn' && baseLang(primary) !== 'en' ? pickForTag(voices, 'en-US') ?? pickForTag(voices, 'en') : null;
    if (en) return { voice: en, usedFallbackTag: normTag(en.language), languageTag: normTag(en.language) };
    return { voice: null, usedFallbackTag: null, languageTag: primary, noVoice: true };
  }
  const voiceTag = normTag(chosen.language);
  const spoken = languageForTag(voiceTag);
  const otherLanguage = Boolean(wanted && spoken && wanted.tag !== spoken.tag);
  if (otherLanguage) return { voice: chosen, usedFallbackTag: voiceTag, languageTag: voiceTag };
  return { voice: chosen, usedFallbackTag: null, languageTag: own ? primary : voiceTag };
}

export async function resolveVoice(lang: string): Promise<ResolvedVoice> {
  return resolveVoiceFrom(await getVoices(), lang);
}

/** Split into sentence-sized chunks under the platform limit (Number.MAX_VALUE on iOS). */
export function chunkText(text: string, max: number = Speech.maxSpeechInputLength): string[] {
  const limit = Number.isFinite(max) && max > 0 ? Math.min(max, 3000) : 3000;
  const sentences = text.replace(/\s+/g, ' ').trim().split(/(?<=[.!?؟।။።])\s+/);
  const chunks: string[] = [];
  let current = '';
  for (const s of sentences) {
    if (!s) continue;
    if ((current + ' ' + s).trim().length > limit) {
      if (current) chunks.push(current.trim());
      if (s.length > limit) {
        for (let i = 0; i < s.length; i += limit) chunks.push(s.slice(i, i + limit));
        current = '';
      } else {
        current = s;
      }
    } else {
      current = current ? `${current} ${s}` : s;
    }
  }
  if (current) chunks.push(current.trim());
  return chunks;
}

let activeId = 0;

export async function stop(): Promise<void> {
  activeId += 1;
  useSpeakingStore.getState().set(false, null);
  try {
    await Speech.stop();
  } catch {
    // nothing to stop
  }
}

/**
 * The user's chosen voice, only when it speaks the same base language as `languageTag`.
 * A voice picked for another language (e.g. an English voice kept after switching to Arabic)
 * is ignored so the resolved voice for this language is used instead.
 */
export async function chosenVoiceFor(voiceId: string | null | undefined, languageTag: string): Promise<string | null> {
  if (!voiceId) return null;
  const chosen = (await getVoices()).find((v) => v.identifier === voiceId);
  if (!chosen) return null;
  return baseLang(chosen.language) === baseLang(languageTag) ? chosen.identifier : null;
}

/**
 * Speak `text` in `lang` (pack tag). Resolves when the whole text has been spoken or stopped.
 * Returns the resolution so callers can show the honest fallback line.
 */
export async function speak(text: string, lang: string, utteranceId?: string): Promise<ResolvedVoice> {
  await stop();
  const myId = activeId;
  const resolved = await resolveVoice(lang);
  const chunks = chunkText(text);
  if (!chunks.length || resolved.noVoice) return resolved;
  const rate = useSettings.getState().voiceRate;
  const voiceId = await chosenVoiceFor(useSettings.getState().voiceId, resolved.languageTag);
  useSpeakingStore.getState().set(true, utteranceId ?? null);
  for (const chunk of chunks) {
    if (myId !== activeId) break;
    await new Promise<void>((resolve) => {
      let settled = false;
      const done = () => {
        if (!settled) {
          settled = true;
          resolve();
        }
      };
      try {
        Speech.speak(chunk, {
          language: resolved.languageTag,
          voice: voiceId ?? resolved.voice?.identifier,
          rate,
          onDone: done,
          onStopped: done,
          onError: done,
        });
      } catch {
        done();
      }
    });
  }
  if (myId === activeId) useSpeakingStore.getState().set(false, null);
  return resolved;
}

export async function isSpeaking(): Promise<boolean> {
  try {
    return await Speech.isSpeakingAsync();
  } catch {
    return false;
  }
}
