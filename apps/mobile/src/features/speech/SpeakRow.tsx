// A paragraph with its speaker (D-26: speaker button after every paragraph) and the honest TTS
// fallback line under it when the pack's own voice is missing.

import { type ReactNode, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { SpeakButton } from '@/design/components/SpeakButton';
import { AppText, type AppTextProps } from '@/design/components/Text';
import { space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { usePackMeta, useT } from '@/i18n/useT';
import type { ResolvedVoice } from '@/lib/tts';

import { fallbackNotice } from './fallback';

export interface SpeakRowProps {
  /** What the speaker reads. */
  text: string;
  /** Language of `text` (defaults to the UI pack). */
  lang?: string;
  /** Rendered content; defaults to `text` as body copy. */
  children?: ReactNode;
  textProps?: Omit<AppTextProps, 'children'>;
  testID?: string;
}

export function SpeakRow({ text, lang, children, textProps, testID }: SpeakRowProps) {
  const t = useT();
  const meta = usePackMeta();
  const dir = useDirection();
  const [notice, setNotice] = useState<string | null>(null);
  const speakLang = lang ?? meta.tag;
  const onResolved = (v: ResolvedVoice) => setNotice(fallbackNotice(v, speakLang, t));
  return (
    <View testID={testID} style={styles.wrap}>
      <View style={[styles.row, { flexDirection: dir.row }]}>
        <View style={styles.flex}>{children ?? <AppText {...textProps}>{text}</AppText>}</View>
        <SpeakButton text={text} lang={speakLang} onResolved={onResolved} />
      </View>
      {notice ? (
        <AppText variant="caption" color="textMuted" role="status">
          {notice}
        </AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: space.xs,
  },
  row: {
    alignItems: 'center',
    gap: space.md,
  },
  flex: {
    flex: 1,
  },
});
