// Honest voice choice (D-26, CL-053, PRODUCT_SPEC J-A step 9): a voice of another pack language is
// always reported as a fallback (a Farsi voice reading Dari), and when the phone has no voice for
// the language nothing is spoken — Dari/Pashto/Arabic text is never handed to an English voice.

import * as Speech from 'expo-speech';

import { resetVoicesForTests, resolveVoiceFrom, speak, ttsLanguageName, type Voice } from '@/lib/tts';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

const v = (language: string, identifier = language): Voice =>
  ({ identifier, name: identifier, language, quality: Speech.VoiceQuality.Default }) as Voice;

const EN_ONLY = [v('en-US', 'samantha')];

describe('resolveVoiceFrom', () => {
  it('reports a Farsi (fa-IR) voice for Dari as a fallback (CL-053)', () => {
    const r = resolveVoiceFrom([v('fa-IR', 'dariush')], 'prs');
    expect(r.voice?.identifier).toBe('dariush');
    expect(r.usedFallbackTag).toBe('fa-IR');
    expect(r.noVoice).toBeFalsy();
  });

  it('Dari with its own fa-AF voice is not a fallback; Pashto read by it is', () => {
    expect(resolveVoiceFrom([v('fa-AF')], 'prs').usedFallbackTag).toBeNull();
    const ps = resolveVoiceFrom([v('fa-AF')], 'ps');
    expect(ps.voice?.language).toBe('fa-AF');
    expect(ps.usedFallbackTag).toBe('fa-AF');
    // Pashto via its seed fallback, but only a Farsi voice exists: the tag names the real voice.
    expect(resolveVoiceFrom([v('fa-IR')], 'ps').usedFallbackTag).toBe('fa-IR');
  });

  it("a regional voice of the same language is the language's own voice (es-MX for Spanish, ur-IN for Urdu)", () => {
    expect(resolveVoiceFrom([v('es-MX')], 'es').usedFallbackTag).toBeNull();
    expect(resolveVoiceFrom([v('ur_IN')], 'ur').usedFallbackTag).toBeNull();
    expect(resolveVoiceFrom([v('en-GB')], 'en').usedFallbackTag).toBeNull();
  });

  it.each(['ar', 'prs', 'ps', 'fa', 'ur', 'am', 'my', 'rhg'])(
    '%s with only an English voice: no voice, never en-US',
    (lang) => {
      const r = resolveVoiceFrom(EN_ONLY, lang);
      expect(r.voice).toBeNull();
      expect(r.noVoice).toBe(true);
      expect(r.usedFallbackTag).toBeNull();
      expect(r.languageTag).not.toBe('en-US');
    },
  );

  it('a Latin-script language may fall back to an English voice, reported as a fallback', () => {
    const r = resolveVoiceFrom(EN_ONLY, 'es');
    expect(r.voice?.identifier).toBe('samantha');
    expect(r.usedFallbackTag).toBe('en-US');
    expect(r.noVoice).toBeFalsy();
    // English itself without an English voice: nothing to fall back to.
    expect(resolveVoiceFrom([v('es-US')], 'en').noVoice).toBe(true);
  });

  it('no voices at all (Android without a TTS engine) is reported, not hidden', () => {
    const r = resolveVoiceFrom([], 'ps');
    expect(r.noVoice).toBe(true);
    expect(r.voice).toBeNull();
  });

  it('names the language natively for the "no voice" line', () => {
    expect(ttsLanguageName('prs')).toBe('دری');
    expect(ttsLanguageName('xx-unknown')).toBe('xx-unknown');
  });
});

describe('speak()', () => {
  afterEach(() => {
    jest.restoreAllMocks();
    resetVoicesForTests();
  });

  it('says nothing when the phone has no voice for the language', async () => {
    jest.spyOn(Speech, 'getAvailableVoicesAsync').mockResolvedValue(EN_ONLY);
    const spoken = jest.spyOn(Speech, 'speak').mockImplementation(() => undefined);
    const r = await speak('اگر کسی در خطر است یا خیلی مریض است، به 911 زنگ بزنید.', 'prs', 'emergency');
    expect(r.noVoice).toBe(true);
    expect(spoken).not.toHaveBeenCalled();
  });

  it('speaks with the fallback voice and its own language tag when one exists', async () => {
    jest.spyOn(Speech, 'getAvailableVoicesAsync').mockResolvedValue([v('en-US', 'samantha'), v('fa-IR', 'dariush')]);
    const spoken = jest.spyOn(Speech, 'speak').mockImplementation((_text, opts) => opts?.onDone?.());
    const r = await speak('سلام.', 'prs', 'x');
    expect(r.usedFallbackTag).toBe('fa-IR');
    expect(spoken).toHaveBeenCalledWith('سلام.', expect.objectContaining({ voice: 'dariush', language: 'fa-IR' }));
  });
});
