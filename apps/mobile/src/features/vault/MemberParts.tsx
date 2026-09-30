// Member building blocks: the initials avatar, a selectable member chip, the "Add someone" form
// (name ≤ 40 chars, 8 colour swatches, initials shown live) and a member picker sheet (move a
// paper, move all papers). Icon + word + colour, never colour alone; chips are ≥ 44 pt.

import { useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';

import { BigButton } from '@/design/components/BigButton';
import { Icon } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useScaled, useTheme } from '@/design/theme';
import { radius, size, space, type as typeScale } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';
import type { Member } from '@/storage/index';

import { cleanMemberName, initials, MEMBER_COLORS, MEMBER_NAME_MAX, memberName } from './members';
import { Sheet } from './Sheet';

export function Avatar({ name, color, big }: { name: string; color: string; big?: boolean }) {
  const { colors } = useTheme();
  const d = big ? 56 : 32;
  const letters = initials(name);
  return (
    <View
      importantForAccessibility="no-hide-descendants"
      accessibilityElementsHidden
      style={[styles.avatar, { width: d, height: d, borderRadius: d / 2, backgroundColor: color }]}>
      {letters ? (
        <AppText variant={big ? 'title' : 'caption'} weight="bold" colorValue="#FFFFFF" align="center">
          {letters}
        </AppText>
      ) : (
        <Icon name="people" size={big ? 28 : 18} color={colors.onPrimary} />
      )}
    </View>
  );
}

export interface MemberChipProps {
  member: Member;
  selected?: boolean;
  onPress(): void;
  testID?: string;
}

export function MemberChip({ member, selected, onPress, testID }: MemberChipProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const name = memberName(member, t);
  return (
    <Pressable
      testID={testID}
      role="radio"
      aria-checked={Boolean(selected)}
      accessibilityState={{ checked: Boolean(selected), selected: Boolean(selected) }}
      accessibilityLabel={name}
      hitSlop={size.hitSlop / 2}
      onPress={onPress}
      style={[
        styles.chip,
        {
          flexDirection: dir.row,
          borderColor: selected ? colors.primary : colors.border,
          borderWidth: selected ? 3 : 1,
          backgroundColor: selected ? colors.secondary : colors.surface,
        },
      ]}>
      <Avatar name={name} color={member.color} />
      <AppText weight={selected ? 'bold' : 'regular'}>{name}</AppText>
      {selected ? <Icon name="check" color={colors.primary} /> : null}
    </Pressable>
  );
}

export interface ColorSwatchesProps {
  value: string;
  onChange(color: string): void;
  /** Each swatch gets `${testID}-${index}`. */
  testID?: string;
}

/** The `member.color` ("Change color") label and the 8-swatch radiogroup (Add someone, S13). */
export function ColorSwatches({ value, onChange, testID = 'member-color' }: ColorSwatchesProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  return (
    <>
      <AppText weight="bold">{t('member.color')}</AppText>
      <View role="radiogroup" accessibilityLabel={t('member.color')} style={[styles.swatches, { flexDirection: dir.row }]}>
        {MEMBER_COLORS.map((c, i) => {
          const on = c.toLowerCase() === value.toLowerCase();
          return (
            <Pressable
              key={c}
              testID={`${testID}-${i}`}
              role="radio"
              aria-checked={on}
              accessibilityState={{ checked: on }}
              accessibilityLabel={`${t('member.color')} ${i + 1}`}
              hitSlop={size.hitSlop / 2}
              onPress={() => onChange(c)}
              style={[styles.swatch, { backgroundColor: c, borderColor: on ? colors.text : 'transparent' }]}>
              {on ? <Icon name="check" color="#FFFFFF" /> : null}
            </Pressable>
          );
        })}
      </View>
    </>
  );
}

export interface MemberFormProps {
  initialName?: string;
  initialColor: string;
  submitLabel: string;
  onSubmit(value: { name: string; color: string }): void;
  onCancel?(): void;
}

export function MemberForm({ initialName = '', initialColor, submitLabel, onSubmit, onCancel }: MemberFormProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const [name, setName] = useState(initialName);
  const scaled = useScaled();
  const [color, setColor] = useState(initialColor);
  const clean = cleanMemberName(name);
  return (
    <View style={styles.form}>
      <View style={[styles.row, { flexDirection: dir.row }]}>
        <Avatar name={clean} color={color} big />
        <TextInput
          testID="member-name-input"
          value={name}
          onChangeText={(v) => setName(v.slice(0, MEMBER_NAME_MAX))}
          maxLength={MEMBER_NAME_MAX}
          placeholder={t('member.name')}
          placeholderTextColor={colors.textMuted}
          accessibilityLabel={t('member.name')}
          autoCapitalize="words"
          style={[
            styles.input,
            {
              color: colors.text,
              borderColor: colors.border,
              textAlign: dir.textAlign,
              fontSize: scaled(typeScale.size.body),
            },
          ]}
        />
      </View>
      <ColorSwatches value={color} onChange={setColor} />
      <BigButton
        testID="member-form-submit"
        label={submitLabel}
        icon="check"
        variant="primary"
        size={56}
        disabled={clean.length === 0}
        onPress={() => onSubmit({ name: clean, color })}
      />
      {onCancel ? <BigButton label={t('btn.cancel')} variant="secondary" size={56} onPress={onCancel} /> : null}
    </View>
  );
}

export interface MemberPickerSheetProps {
  visible: boolean;
  title: string;
  members: Member[];
  excludeId?: string | null;
  onPick(memberId: string): void;
  onClose(): void;
}

/** "Move to another person": pick a member (the current one is left out). */
export function MemberPickerSheet({ visible, title, members, excludeId, onPick, onClose }: MemberPickerSheetProps) {
  const dir = useDirection();
  return (
    <Sheet visible={visible} title={title} onClose={onClose} testID="member-picker">
      <View role="radiogroup" style={[styles.swatches, { flexDirection: dir.row }]}>
        {members
          .filter((m) => m.id !== excludeId)
          .map((m) => (
            <MemberChip key={m.id} member={m} onPress={() => onPick(m.id)} testID={`move-to-${m.id}`} />
          ))}
      </View>
    </Sheet>
  );
}

const styles = StyleSheet.create({
  avatar: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  chip: {
    minHeight: size.minTouch,
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    borderRadius: radius.pill,
  },
  form: {
    gap: space.md,
  },
  row: {
    alignItems: 'center',
    gap: space.md,
  },
  input: {
    flex: 1,
    minHeight: size.button,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
  },
  swatches: {
    flexWrap: 'wrap',
    gap: space.sm,
  },
  swatch: {
    width: size.minTouch,
    height: size.minTouch,
    borderRadius: size.minTouch / 2,
    borderWidth: 3,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
