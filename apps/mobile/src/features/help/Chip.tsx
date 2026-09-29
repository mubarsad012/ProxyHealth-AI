// Small read-only label chip (why-chips, cost badge, "Verified on", "EN"). Not a control.

import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import { type IconName, Icon } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';

export interface ChipProps {
  text: string;
  icon?: IconName;
  tone?: 'neutral' | 'success' | 'warning' | 'danger';
  /** Language of the chip text when it differs from the UI (e.g. "EN"). */
  lang?: string;
}

export function Chip({ text, icon, tone = 'neutral', lang }: ChipProps) {
  const { colors } = useTheme();
  const dir = useDirection();
  const color =
    tone === 'success' ? colors.success : tone === 'warning' ? colors.warning : tone === 'danger' ? colors.danger : colors.textMuted;
  return (
    <View style={[styles.chip, { borderColor: color, flexDirection: dir.row }]}>
      {icon ? <Icon name={icon} size={16} color={color} /> : null}
      <AppText variant="caption" colorValue={color} lang={lang}>
        {text}
      </AppText>
    </View>
  );
}

export function ChipRow({ children }: { children: ReactNode }) {
  const dir = useDirection();
  return <View style={[styles.row, { flexDirection: dir.row }]}>{children}</View>;
}

const styles = StyleSheet.create({
  chip: {
    alignItems: 'center',
    gap: space.xs,
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space.sm,
    paddingVertical: space.xxs,
    alignSelf: 'flex-start',
  },
  row: {
    flexWrap: 'wrap',
    gap: space.xs,
  },
});
