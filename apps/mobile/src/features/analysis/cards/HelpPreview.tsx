// S7 item 15 — "Get help nearby" preview: top 3 `resource_preview[]` rows (name as vetted in the
// resource DB, first "why" line, "Verified on {date}") + "See all help" → S11. Contacts come only
// from the vetted YAML DB via the server (never from the model). With no region set, the prompt
// `help.set_region_prompt` is shown instead.

import { Pressable, StyleSheet, View } from 'react-native';

import type { ResourceMatch } from '@/api/types';
import { Bidi } from '@/design/components/Bidi';
import { Card } from '@/design/components/Card';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { size, space } from '@/design/tokens';
import { keyExists } from '@/i18n/store';
import { useT, type TFunction } from '@/i18n/useT';
import { useSettings } from '@/store/settings';

import type { ResultCardProps } from './shared';

export function whyLine(m: ResourceMatch, t: TFunction): string | null {
  const key = m.why_keys[0];
  if (key && keyExists(key)) return t(key);
  return m.why[0] ?? null;
}

export interface HelpPreviewProps extends ResultCardProps {
  onSeeAll?(): void;
  onSetRegion?(): void;
}

export function HelpPreview({ analysis, onSeeAll, onSetRegion }: HelpPreviewProps) {
  const t = useT();
  const { colors } = useTheme();
  const region = useSettings((s) => s.region.state);
  const top = analysis.resource_preview.slice(0, 3);
  return (
    <Card id="card-help-preview" headingKey="card.help_preview">
      {top.map((m) => {
        const why = whyLine(m, t);
        return (
          <View key={m.resource.id} testID={`help-${m.resource.id}`} style={[styles.row, { borderTopColor: colors.divider }]}>
            <Bidi dir="auto" variant="body" weight="bold">
              {m.resource.name}
            </Bidi>
            {why ? <AppText>{why}</AppText> : null}
            <AppText variant="caption" color="textMuted">
              {t('resource.verified_on', { date: m.resource.verified_on })}
            </AppText>
          </View>
        );
      })}
      {!top.length && !region ? (
        <Pressable role="button" accessibilityLabel={t('help.set_region_prompt')} onPress={onSetRegion} style={styles.link}>
          <AppText color="link" weight="bold">
            {t('help.set_region_prompt')}
          </AppText>
        </Pressable>
      ) : null}
      {onSeeAll ? (
        <Pressable role="button" accessibilityLabel={t('help.see_all')} hitSlop={size.hitSlop} onPress={onSeeAll} style={styles.link}>
          <AppText color="link" weight="bold">
            {t('help.see_all')}
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
  link: {
    minHeight: size.minTouch,
    justifyContent: 'center',
  },
});
