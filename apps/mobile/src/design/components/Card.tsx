// Card = `role="region"` + heading + SpeakButton slot (D-28, PRODUCT_SPEC §5.1). Screen readers
// navigate by region; the heading text labels the region. `headingKey` is a pack key; `lang` is
// the language of the card body (defaults to the UI pack).

import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import { SpeakButton } from '@/design/components/SpeakButton';
import { Heading } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { usePackMeta, useT } from '@/i18n/useT';

export interface CardProps {
  headingKey: string;
  /** Placeholders for the heading string. */
  headingVars?: Record<string, string | number>;
  lang?: string;
  /** What the speaker reads (heading + body text). No speaker when omitted. */
  speakText?: string;
  children?: ReactNode;
  id: string;
  /** Visual emphasis (urgency / emergency cards pass a border colour). */
  accentColor?: string;
}

export function Card({ headingKey, headingVars, lang, speakText, children, id, accentColor }: CardProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const meta = usePackMeta();
  const heading = t(headingKey, headingVars);
  const speakLang = lang ?? meta.tag;
  return (
    <View
      nativeID={id}
      testID={id}
      role="region"
      accessibilityLabel={heading}
      style={[
        styles.card,
        { backgroundColor: colors.surface, borderColor: accentColor ?? colors.divider },
        accentColor ? styles.accent : null,
      ]}>
      <View style={[styles.header, { flexDirection: dir.row }]}>
        <View style={styles.headingText}>
          <Heading level={2}>{heading}</Heading>
        </View>
        {speakText ? (
          <SpeakButton text={`${heading}. ${speakText}`} lang={speakLang} accessibilityHint={heading} />
        ) : null}
      </View>
      <View style={styles.body}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.lg,
    borderWidth: 1,
    padding: space.lg,
    gap: space.md,
  },
  accent: {
    borderWidth: 3,
  },
  header: {
    alignItems: 'center',
    gap: space.md,
  },
  headingText: {
    flex: 1,
  },
  body: {
    gap: space.sm,
  },
});
