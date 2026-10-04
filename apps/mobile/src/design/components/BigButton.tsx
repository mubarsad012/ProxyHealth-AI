// 56/72 pt buttons with icon + word (D-28). Every screen has exactly one 72 pt primary action.
// Labels are already-translated strings (callers use `t()`); no emoji; `hitSlop` 8; the row
// direction follows the pack (icon leads in both LTR and RTL). Height is a minimum, never fixed,
// so 200 % text still fits.

import type { GestureResponderEvent } from 'react-native';
import { Pressable, StyleSheet, View } from 'react-native';

import { Icon, type IconName } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size as sizes, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';

export type BigButtonVariant = 'primary' | 'secondary' | 'danger';

export interface BigButtonProps {
  label: string;
  icon?: IconName;
  /** Receives the press event so web pickers can run inside the gesture (BUILD_PLAN §1.1 rule 7). */
  onPress(e?: GestureResponderEvent): void;
  variant: BigButtonVariant;
  size: 56 | 72;
  disabled?: boolean;
  /**
   * Overrides what screen readers say instead of the visible label (+ sublabel), e.g. S11's
   * "Call {organization}, {digits grouped}" for a "Call 1-800-…" button (CL-076(a)). Keep the
   * visible words in it (WCAG 2.5.3 Label in Name).
   */
  accessibilityLabel?: string;
  accessibilityHint?: string;
  /** Optional second line under the label (e.g. `home.busy_until`). */
  sublabel?: string;
  testID?: string;
}

export function BigButton({
  label,
  icon,
  onPress,
  variant,
  size,
  disabled,
  accessibilityLabel,
  accessibilityHint,
  sublabel,
  testID,
}: BigButtonProps) {
  const { colors } = useTheme();
  const dir = useDirection();
  const palette =
    variant === 'primary'
      ? { bg: colors.primary, fg: colors.onPrimary, border: colors.primary }
      : variant === 'danger'
        ? { bg: colors.danger, fg: colors.onDanger, border: colors.danger }
        : { bg: colors.secondary, fg: colors.onSecondary, border: colors.border };
  return (
    <Pressable
      testID={testID}
      role="button"
      accessibilityLabel={accessibilityLabel || (sublabel ? `${label}. ${sublabel}` : label)}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: Boolean(disabled) }}
      disabled={disabled}
      hitSlop={sizes.hitSlop}
      onPress={(e) => onPress(e)}
      style={({ pressed }) => [
        styles.base,
        {
          minHeight: size,
          flexDirection: dir.row,
          backgroundColor: palette.bg,
          borderColor: palette.border,
          opacity: disabled ? 0.45 : pressed ? 0.85 : 1,
        },
      ]}>
      {icon ? <Icon name={icon} size={size === 72 ? sizes.iconLarge : sizes.icon} color={palette.fg} /> : null}
      <View style={styles.labels}>
        <AppText variant={size === 72 ? 'bodyLarge' : 'body'} weight="bold" colorValue={palette.fg} align="center">
          {label}
        </AppText>
        {sublabel ? (
          <AppText variant="caption" colorValue={palette.fg} align="center">
            {sublabel}
          </AppText>
        ) : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    alignSelf: 'stretch',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.md,
    paddingHorizontal: space.xl,
    paddingVertical: space.md,
    borderRadius: radius.md,
    borderWidth: 2,
  },
  labels: {
    flexShrink: 1,
    alignItems: 'center',
  },
});
