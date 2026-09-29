// 44×44 speaker button after every paragraph (D-26, PRODUCT_SPEC §5.1). Tapping it reads `text` in
// `lang` (pack tag) with on-device TTS; tapping again (or any other speaker) stops. The resolved
// voice is reported through `onResolved` so screens can show the honest fallback line
// (`tts.fallback_offer`, owned by features/speech).

import { useId } from 'react';
import { Pressable, StyleSheet } from 'react-native';

import { Icon } from '@/design/components/Icon';
import { useTheme } from '@/design/theme';
import { size } from '@/design/tokens';
import { useT } from '@/i18n/useT';
import { type ResolvedVoice, speak, stop, useSpeakingId } from '@/lib/tts';

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

  const onPress = () => {
    if (active) {
      void stop();
      return;
    }
    void speak(text, lang, id).then((v) => onResolved?.(v));
  };

  return (
    <Pressable
      role="button"
      accessibilityLabel={active ? t('btn.stop') : t('btn.read_aloud')}
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
          opacity: disabled ? 0.5 : 1,
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
