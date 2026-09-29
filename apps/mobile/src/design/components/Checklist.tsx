// Persistent checkboxes (PRODUCT_SPEC S7 Card 3 / S11 prep checklist). State is owned by the caller
// (saved with the document via `vault.checklist`); rows are `role="checkbox"` with `aria-checked`.

import { Pressable, StyleSheet, View } from 'react-native';

import { Icon } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';

export interface ChecklistItem {
  id: string;
  text: string;
}

export interface ChecklistProps {
  items: ChecklistItem[];
  state: Record<string, boolean>;
  onToggle(id: string, checked: boolean): void;
}

export function Checklist({ items, state, onToggle }: ChecklistProps) {
  const { colors } = useTheme();
  const dir = useDirection();
  return (
    <View role="list" style={styles.list}>
      {items.map((item, i) => {
        const checked = Boolean(state[item.id]);
        return (
          <Pressable
            key={item.id}
            role="checkbox"
            aria-checked={checked}
            accessibilityState={{ checked }}
            accessibilityLabel={`${i + 1}. ${item.text}`}
            hitSlop={size.hitSlop}
            onPress={() => onToggle(item.id, !checked)}
            style={[styles.row, { flexDirection: dir.row }]}>
            <View
              style={[
                styles.box,
                { borderColor: checked ? colors.primary : colors.border, backgroundColor: checked ? colors.primary : 'transparent' },
              ]}>
              {checked ? <Icon name="check" size={20} color={colors.onPrimary} /> : null}
            </View>
            <View style={styles.text}>
              <AppText color={checked ? 'textMuted' : 'text'}>{item.text}</AppText>
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  list: {
    gap: space.sm,
  },
  row: {
    minHeight: size.minTouch,
    alignItems: 'center',
    gap: space.md,
  },
  box: {
    width: 32,
    height: 32,
    borderWidth: 2,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  text: {
    flex: 1,
  },
});
