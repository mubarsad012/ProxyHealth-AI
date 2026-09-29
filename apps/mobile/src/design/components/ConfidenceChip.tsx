// Confidence chip (PRODUCT_SPEC §5.6, D-09): high / medium / low carry words, not only colour; low
// adds the amber "Re-scan this part" action when a handler is given.

import { Pressable, StyleSheet, View } from 'react-native';

import type { Confidence } from '@/api/types';
import { Icon, type IconName } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import type { Palette } from '@/design/tokens';
import { radius, size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';

const LOOK: Record<Confidence, { icon: IconName; color: keyof Palette }> = {
  high: { icon: 'check', color: 'success' },
  medium: { icon: 'info', color: 'textMuted' },
  low: { icon: 'alert', color: 'warning' },
};

export interface ConfidenceChipProps {
  confidence: Confidence;
  onRescan?(): void;
}

export function ConfidenceChip({ confidence, onRescan }: ConfidenceChipProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const look = LOOK[confidence];
  const color = colors[look.color];
  const word = t(`confidence.${confidence}`);
  return (
    <View style={[styles.wrap, { flexDirection: dir.row }]}>
      <View
        accessible
        accessibilityRole="text"
        accessibilityLabel={word}
        style={[styles.chip, { borderColor: color, flexDirection: dir.row }]}>
        <Icon name={look.icon} color={color} size={18} />
        <AppText variant="caption" colorValue={color} weight="bold">
          {word}
        </AppText>
      </View>
      {confidence === 'low' && onRescan ? (
        <Pressable
          role="button"
          accessibilityLabel={t('btn.rescan_part')}
          hitSlop={size.hitSlop}
          onPress={onRescan}
          style={[styles.rescan, { borderColor: colors.warning }]}>
          <AppText variant="caption" weight="bold" color="warning">
            {t('btn.rescan_part')}
          </AppText>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: space.sm,
  },
  chip: {
    alignItems: 'center',
    gap: space.xs,
    paddingHorizontal: space.sm,
    paddingVertical: space.xxs,
    borderWidth: 1,
    borderRadius: radius.pill,
  },
  rescan: {
    minHeight: size.minTouch,
    justifyContent: 'center',
    paddingHorizontal: space.md,
    borderWidth: 2,
    borderRadius: radius.pill,
  },
});
