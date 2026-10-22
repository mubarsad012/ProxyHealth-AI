// Collapsible section (moved from the template's components/ui/collapsible.tsx, BUILD_PLAN §5.5),
// rebuilt on the design system: vector chevron, no reanimated entering animation (reduce-motion
// safe), chevron mirrors in RTL, `aria-expanded` for screen readers.

import { type ReactNode, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Icon } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';

export interface CollapsibleProps {
  title: string;
  children: ReactNode;
  initiallyOpen?: boolean;
  /** On the heading button. */
  testID?: string;
}

export function Collapsible({ title, children, initiallyOpen = false, testID }: CollapsibleProps) {
  const [open, setOpen] = useState(initiallyOpen);
  const { colors } = useTheme();
  const dir = useDirection();
  return (
    <View>
      <Pressable
        testID={testID}
        role="button"
        aria-expanded={open}
        accessibilityState={{ expanded: open }}
        accessibilityLabel={title}
        hitSlop={size.hitSlop}
        onPress={() => setOpen((v) => !v)}
        style={({ pressed }) => [styles.heading, { flexDirection: dir.row, opacity: pressed ? 0.7 : 1 }]}>
        <Icon name={open ? 'chevron-down' : 'chevron-right'} color={colors.text} size={20} />
        <View style={styles.title}>
          <AppText weight="bold">{title}</AppText>
        </View>
      </Pressable>
      {open ? <View style={[styles.content, { backgroundColor: colors.surface }]}>{children}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  heading: {
    minHeight: size.minTouch,
    alignItems: 'center',
    gap: space.sm,
  },
  title: {
    flex: 1,
  },
  content: {
    marginTop: space.sm,
    padding: space.lg,
    borderRadius: radius.md,
    gap: space.sm,
  },
});
