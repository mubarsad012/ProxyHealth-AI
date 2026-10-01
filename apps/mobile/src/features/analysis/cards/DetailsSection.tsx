// S7 item 11 — "Details and quotes" (collapsed): every demand, verified and unverified, as
// label · value as printed · confidence · "Found on page {page}" · crop; tap → S8.

import { StyleSheet, View } from 'react-native';

import { Collapsible } from '@/design/components/Collapsible';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { space } from '@/design/tokens';
import { useBidiText, useT } from '@/i18n/useT';

import { FactRow, type ResultCardProps, SourceText } from './shared';

export function DetailsSection(props: ResultCardProps) {
  const t = useT();
  const bt = useBidiText();
  const { colors } = useTheme();
  const all = [...props.analysis.demands, ...props.analysis.unverified];
  if (!all.length) return null;
  return (
    <View testID="card-details" role="region" accessibilityLabel={t('card.details')}>
      <Collapsible title={t('card.details')}>
        {all.map((d) => (
          <View key={`detail-${d.id}`} style={[styles.row, { borderTopColor: colors.divider }]}>
            <AppText lang={props.analysis.target_language} style={d.verified ? undefined : styles.struck}>
              {bt(d.text)}
            </AppText>
            <SourceText lang={props.analysis.detected_language} dir="ltr" weight="bold">
              {d.value_verbatim}
            </SourceText>
            <FactRow
              analysis={props.analysis}
              pages={props.pages}
              spanIds={d.span_ids}
              page={d.page}
              quote={d.source_quote}
              confidence={d.confidence}
              handlers={props.handlers}
            />
          </View>
        ))}
      </Collapsible>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    gap: space.xs,
    paddingTop: space.md,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  struck: {
    textDecorationLine: 'line-through',
  },
});
