// Settings building blocks (PRODUCT_SPEC S17) shared by `(tabs)/settings.tsx` and WP6's
// `VaultAndDataSettings`: a titled section, a switch row with explanation, single-choice chips and a
// navigation row. All rows are ≥ 56 pt, mirror in RTL and carry roles/states for screen readers.

import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Switch, View } from 'react-native';

import { Icon } from '@/design/components/Icon';
import { AppText, Heading } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';

export function SettingsSection({ title, children, testID }: { title: string; children: ReactNode; testID?: string }) {
  const { colors } = useTheme();
  return (
    <View testID={testID} role="region" accessibilityLabel={title} style={[styles.section, { borderColor: colors.divider }]}>
      <Heading level={2}>{title}</Heading>
      <View style={styles.sectionBody}>{children}</View>
    </View>
  );
}

export interface SwitchRowProps {
  label: string;
  value: boolean;
  onChange(value: boolean): void;
  explanation?: string;
  disabled?: boolean;
  testID?: string;
}

export function SwitchRow({ label, value, onChange, explanation, disabled, testID }: SwitchRowProps) {
  const { colors } = useTheme();
  const dir = useDirection();
  return (
    <View style={styles.rowWrap}>
      <View style={[styles.row, { flexDirection: dir.row }]}>
        <View style={styles.flex}>
          <AppText>{label}</AppText>
        </View>
        <Switch
          testID={testID}
          value={value}
          onValueChange={onChange}
          disabled={disabled}
          accessibilityLabel={label}
          accessibilityHint={explanation}
          trackColor={{ true: colors.primary, false: colors.border }}
        />
      </View>
      {explanation ? (
        <AppText variant="caption" color="textMuted">
          {explanation}
        </AppText>
      ) : null}
    </View>
  );
}

export interface ChoiceChipsProps<T extends string | number> {
  label?: string;
  options: { value: T; label: string }[];
  value: T | null;
  onChange(value: T): void;
  testIDPrefix?: string;
}

export function ChoiceChips<T extends string | number>({ label, options, value, onChange, testIDPrefix }: ChoiceChipsProps<T>) {
  const { colors } = useTheme();
  const dir = useDirection();
  return (
    <View style={styles.rowWrap}>
      {label ? <AppText weight="bold">{label}</AppText> : null}
      <View role="radiogroup" accessibilityLabel={label} style={[styles.chips, { flexDirection: dir.row }]}>
        {options.map((o) => {
          const selected = o.value === value;
          return (
            <Pressable
              key={String(o.value)}
              testID={testIDPrefix ? `${testIDPrefix}-${o.value}` : undefined}
              role="radio"
              aria-checked={selected}
              accessibilityState={{ checked: selected, selected }}
              accessibilityLabel={o.label}
              hitSlop={size.hitSlop / 2}
              onPress={() => onChange(o.value)}
              style={[
                styles.chip,
                {
                  borderColor: selected ? colors.primary : colors.border,
                  backgroundColor: selected ? colors.secondary : colors.surface,
                  borderWidth: selected ? 3 : 1,
                },
              ]}>
              <AppText weight={selected ? 'bold' : 'regular'} align="center">
                {o.label}
              </AppText>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export interface ToggleChipProps {
  label: string;
  on: boolean;
  onPress(): void;
}

/** Multi-select chip (checkbox semantics), e.g. calendar notes. */
export function ToggleChip({ label, on, onPress }: ToggleChipProps) {
  const { colors } = useTheme();
  return (
    <Pressable
      role="checkbox"
      aria-checked={on}
      accessibilityState={{ checked: on }}
      accessibilityLabel={label}
      hitSlop={size.hitSlop / 2}
      onPress={onPress}
      style={[
        styles.chip,
        {
          borderColor: on ? colors.primary : colors.border,
          backgroundColor: on ? colors.secondary : colors.surface,
          borderWidth: on ? 3 : 1,
        },
      ]}>
      <AppText weight={on ? 'bold' : 'regular'} align="center">
        {label}
      </AppText>
    </Pressable>
  );
}

export interface LinkRowProps {
  label: string;
  value?: string;
  onPress(): void;
  testID?: string;
}

export function LinkRow({ label, value, onPress, testID }: LinkRowProps) {
  const { colors } = useTheme();
  const dir = useDirection();
  return (
    <Pressable
      testID={testID}
      role="button"
      accessibilityLabel={value ? `${label}, ${value}` : label}
      hitSlop={size.hitSlop / 2}
      onPress={onPress}
      style={({ pressed }) => [styles.row, styles.link, { flexDirection: dir.row, opacity: pressed ? 0.7 : 1, borderColor: colors.divider }]}>
      <View style={styles.flex}>
        <AppText weight="bold">{label}</AppText>
        {value ? (
          <AppText color="textMuted" align="auto">
            {value}
          </AppText>
        ) : null}
      </View>
      <Icon name="chevron-right" color={colors.textMuted} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  section: {
    gap: space.md,
    paddingVertical: space.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  sectionBody: {
    gap: space.lg,
  },
  flex: {
    flex: 1,
  },
  rowWrap: {
    gap: space.xs,
  },
  row: {
    minHeight: size.button,
    alignItems: 'center',
    gap: space.md,
  },
  link: {
    paddingHorizontal: space.md,
    borderWidth: 1,
    borderRadius: radius.md,
  },
  chips: {
    flexWrap: 'wrap',
    gap: space.sm,
  },
  chip: {
    minHeight: size.minTouch,
    justifyContent: 'center',
    paddingHorizontal: space.md,
    borderRadius: radius.pill,
  },
});
