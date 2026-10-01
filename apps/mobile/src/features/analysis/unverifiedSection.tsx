// S7 item 9 — "I saw these but could not confirm them on the page." (D-09). Items whose quote
// failed verification are shown struck through in grey with the verification note and a re-scan
// action. They NEVER get "Remind me" and never appear in the demands card.

import { StyleSheet, View } from 'react-native';

import { BigButton } from '@/design/components/BigButton';
import { Card } from '@/design/components/Card';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { space } from '@/design/tokens';
import { useBidiText, useT } from '@/i18n/useT';

import { type ResultCardProps, SourceText } from './cards/shared';

export function UnverifiedSection({ analysis, handlers }: ResultCardProps) {
  const t = useT();
  const bt = useBidiText();
  const { colors } = useTheme();
  const items = analysis.unverified;
  if (!items.length) return null;
  return (
    <Card
      id="card-unverified"
      headingKey="card.unverified"
      lang={analysis.target_language}
      speakText={items.map((d) => d.text).join('. ')}>
      {items.map((d) => (
        <View key={d.id} testID={`unverified-${d.id}`} style={[styles.row, { borderTopColor: colors.divider }]}>
          <AppText color="textMuted" style={styles.struck} lang={analysis.target_language}>
            {bt(d.text)}
          </AppText>
          <SourceText lang={analysis.detected_language} dir="ltr" style={{ ...styles.struck, color: colors.textMuted }}>
            {d.value_verbatim}
          </SourceText>
          {d.verification_note ? (
            <AppText variant="caption" color="textMuted">
              {d.verification_note}
            </AppText>
          ) : null}
        </View>
      ))}
      {handlers.onRescan ? (
        <BigButton label={t('btn.rescan_part')} icon="camera" variant="secondary" size={56} onPress={handlers.onRescan} />
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
  struck: {
    textDecorationLine: 'line-through',
  },
});
