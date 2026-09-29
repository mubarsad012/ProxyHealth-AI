// Home tile (PRODUCT_SPEC S3): 56 pt minimum, icon + word + one-line explanation, optional badge.

import { Pressable, StyleSheet, View } from 'react-native';
import type { GestureResponderEvent } from 'react-native';

import { Icon, type IconName } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';

export interface TileProps {
  title: string;
  line: string;
  icon: IconName;
  /** Receives the press event (web pickers must run inside the gesture). */
  onPress(e?: GestureResponderEvent): void;
  disabled?: boolean;
  /** Small count or word shown at the end of the tile (e.g. reminders in the next 7 days). */
  badge?: string | number;
  accessibilityHint?: string;
  testID?: string;
}

export function Tile({ title, line, icon, onPress, disabled, badge, accessibilityHint, testID }: TileProps) {
  const { colors } = useTheme();
  const dir = useDirection();
  return (
    <Pressable
      testID={testID}
      role="button"
      accessibilityLabel={`${title}. ${line}`}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: Boolean(disabled) }}
      disabled={disabled}
      hitSlop={size.hitSlop}
      onPress={(e) => onPress(e)}
      style={({ pressed }) => [
        styles.tile,
        {
          flexDirection: dir.row,
          borderColor: colors.border,
          backgroundColor: pressed ? colors.secondary : colors.surface,
          opacity: disabled ? 0.5 : 1,
        },
      ]}>
      <Icon name={icon} size={size.iconLarge} color={colors.primary} />
      <View style={styles.text}>
        <AppText weight="bold">{title}</AppText>
        <AppText variant="caption" color="textMuted">
          {line}
        </AppText>
      </View>
      {badge !== undefined && badge !== null && badge !== '' ? (
        <View style={[styles.badge, { backgroundColor: colors.primary }]}>
          <AppText variant="caption" weight="bold" color="onPrimary" align="center">
            {String(badge)}
          </AppText>
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  tile: {
    minHeight: size.button,
    alignItems: 'center',
    gap: space.md,
    padding: space.lg,
    borderWidth: 1,
    borderRadius: radius.md,
  },
  text: {
    flex: 1,
    gap: space.xxs,
  },
  badge: {
    minWidth: 28,
    paddingHorizontal: space.sm,
    borderRadius: radius.pill,
  },
});
