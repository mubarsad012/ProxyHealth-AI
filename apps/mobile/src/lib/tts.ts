// On-device text-to-speech (D-26, BUILD_PLAN §4.2 "TTS"). expo-speech works on Android, iOS and
// web (browser SpeechSynthesis). Verified against https://docs.expo.dev/versions/v57.0.0/sdk/speech/ :
// `speak(text, {language, voice, rate, onDone, onStopped, onError})`, `stop()`,
// `getAvailableVoicesAsync() → Voice{identifier,name,language,quality}`, `maxSpeechInputLength`.
// Voices are chosen honestly: exact language → same base language → the seed's fallback tag →
// none (the UI then offers `tts.fallback_offer`). Long text is spoken in sentence chunks.

import * as Speech from 'expo-speech';
import { create } from 'zustand';

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

export function getVoices(): Promise<Voice[]> {
  if (!voicesPromise) {
    voicesPromise = Speech.getAvailableVoicesAsync()
      .then((v) => (Array.isArray(v) ? v : []))
      .catch(() => [] as Voice[]);
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
  /** The related-language tag actually used when the pack's own language has no voice. */
  usedFallbackTag: string | null;
  /** The BCP-47 tag to pass as `language` (voice may be null on platforms without a voice list). */
  languageTag: string;
}

/** Map a pack tag to a voice. Uses the seed's `tts_tag` / `tts_fallback_tag` (D-26). */
export function resolveVoiceFrom(voices: Voice[], lang: string): ResolvedVoice {
  const info = LANGUAGES[lang];
  const primary = info?.tts_tag ?? lang;
  const fallback = info?.tts_fallback_tag ?? null;
  const own = pickForTag(voices, primary) ?? (info?.tts_tag ? null : pickForTag(voices, lang));
  if (own) return { voice: own, usedFallbackTag: null, languageTag: primary };
  if (fallback) {
    const fb = pickForTag(voices, fallback);
    if (fb) return { voice: fb, usedFallbackTag: fallback, languageTag: fallback };
  }
  const en = pickForTag(voices, 'en-US') ?? pickForTag(voices, 'en');
  if (!voices.length) return { voice: null, usedFallbackTag: null, languageTag: primary };
  return { voice: en, usedFallbackTag: en ? 'en-US' : null, languageTag: en ? 'en-US' : primary };
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
  if (!chunks.length) return resolved;
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
