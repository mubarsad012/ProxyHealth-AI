// S7 items 12–13: "Words explained" (glossary; terms as printed, isolated) and "Questions you can
// ask them" (copy per row — on web the clipboard call is the first statement of the handler).

import * as Clipboard from 'expo-clipboard';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Bidi } from '@/design/components/Bidi';
import { Card } from '@/design/components/Card';
import { Icon } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';

import type { ResultCardProps } from './shared';

export function GlossaryCard({ analysis }: ResultCardProps) {
  const { colors } = useTheme();
  const terms = analysis.glossary;
  if (!terms.length) return null;
  return (
    <Card
      id="card-glossary"
      headingKey="card.glossary"
      lang={analysis.target_language}
      speakText={terms.map((g) => `${g.term_as_written}: ${g.explanation}`).join('. ')}>
      {terms.map((g, i) => (
        <View key={`g-${i}`} style={[styles.row, { borderTopColor: colors.divider }]}>
          <Bidi dir="auto" variant="body" weight="bold">
            {g.term_as_written}
          </Bidi>
          <AppText lang={analysis.target_language}>{g.explanation}</AppText>
        </View>
      ))}
    </Card>
  );
}

export function QuestionsCard({ analysis, handlers }: ResultCardProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const [copied, setCopied] = useState<number | null>(null);
  const qs = analysis.questions_to_ask;
  if (!qs.length) return null;
  return (
    <Card
      id="card-questions"
      headingKey="card.questions"
      lang={analysis.target_language}
      speakText={`${t('card.questions_sub')} ${qs.join(' ')}`}>
      <AppText color="textMuted">{t('card.questions_sub')}</AppText>
      {qs.map((q, i) => (
        <View key={`q-${i}`} style={[styles.qRow, { flexDirection: dir.row, borderTopColor: colors.divider }]}>
          <View style={styles.flex}>
            <AppText lang={analysis.target_language}>{q}</AppText>
          </View>
          <Pressable
            role="button"
            accessibilityLabel={t('btn.copy')}
            accessibilityHint={q}
            hitSlop={size.hitSlop}
            onPress={() => {
              void Clipboard.setStringAsync(q).then(() => setCopied(i));
            }}
            style={[styles.copy, { borderColor: colors.border, flexDirection: dir.row }]}>
            {copied === i ? <Icon name="check" size={18} color={colors.success} /> : null}
            <AppText variant="caption" weight="bold" color="link">
              {t('btn.copy')}
            </AppText>
          </Pressable>
        </View>
      ))}
      {handlers.onAsk ? (
        <Pressable role="button" accessibilityLabel={t('btn.ask')} onPress={() => handlers.onAsk?.()} style={styles.ask}>
          <AppText color="link" weight="bold">
            {t('btn.ask')}
          </AppText>
        </Pressable>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  row: {
    gap: space.xs,
    paddingTop: space.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  qRow: {
    alignItems: 'center',
    gap: space.sm,
    paddingTop: space.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  flex: {
    flex: 1,
  },
  copy: {
    minHeight: size.minTouch,
    minWidth: size.minTouch,
    justifyContent: 'center',
    alignItems: 'center',
    gap: space.xs,
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
  },
  ask: {
    minHeight: size.minTouch,
    justifyContent: 'center',
  },
});
