// 44×44 speaker button after every paragraph (D-26, PRODUCT_SPEC §5.1). Tapping it reads `text` in
// `lang` (pack tag) with on-device TTS; tapping again (or any other speaker) stops. The resolved
// voice is reported through `onResolved` so screens can show the honest fallback line
// (`tts.fallback_offer`, owned by features/speech). When the phone has no voice for `lang`,
// `lib/tts` speaks nothing (never an English voice for Dari/Pashto/Arabic text); the button then
// says so itself — it announces `tts.no_voice` and carries it as its label — so the tap is never
// met with unexplained silence.

import { useId, useState } from 'react';
import { AccessibilityInfo, Pressable, StyleSheet } from 'react-native';

import { Icon } from '@/design/components/Icon';
import { useTheme } from '@/design/theme';
import { size } from '@/design/tokens';
import { useT } from '@/i18n/useT';
import { type ResolvedVoice, speak, stop, ttsLanguageName, useSpeakingId } from '@/lib/tts';

export interface SpeakButtonProps {
  text: string;
  lang: string;
  onResolved?(voice: ResolvedVoice): void;
  /** Accessibility hint naming what will be read (e.g. the card heading). */
  accessibilityHint?: string;
}

export function SpeakButton({ text, lang, onResolved, accessibilityHint }: SpeakButtonProps) {
  const t = useT();
  const { colors } = useTheme();
  const id = useId();
  const speakingId = useSpeakingId();
  const active = speakingId === id;
  const disabled = text.trim().length === 0;
  const [noVoiceLine, setNoVoiceLine] = useState<string | null>(null);

  const onPress = () => {
    if (active) {
      void stop();
      return;
    }
    void speak(text, lang, id).then((v) => {
      const line = v.noVoice ? t('tts.no_voice', { language: ttsLanguageName(lang) }) : null;
      setNoVoiceLine(line);
      if (line) {
        try {
          AccessibilityInfo.announceForAccessibility(line);
        } catch {
          // best-effort
        }
      }
      onResolved?.(v);
    });
  };

  return (
    <Pressable
      role="button"
      accessibilityLabel={active ? t('btn.stop') : (noVoiceLine ?? t('btn.read_aloud'))}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled, busy: active }}
      disabled={disabled}
      hitSlop={size.hitSlop}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        {
          borderColor: colors.border,
          backgroundColor: active ? colors.primary : pressed ? colors.secondary : colors.surfaceRaised,
          opacity: disabled || noVoiceLine ? 0.5 : 1,
        },
      ]}>
      <Icon name={active ? 'stop' : 'speaker'} color={active ? colors.onPrimary : colors.primary} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    width: size.speakButton,
    height: size.speakButton,
    minWidth: size.speakButton,
    minHeight: size.speakButton,
    borderRadius: size.speakButton / 2,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
