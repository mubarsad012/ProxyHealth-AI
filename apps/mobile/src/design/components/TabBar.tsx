// JS tab bar for the `(tabs)` group (D-27, PRODUCT_SPEC §5.7): 64 pt, icon + word, labels capped at
// `maxFontSizeMultiplier={2}` (the only capped text in the app, D-28), order mirrored in RTL via
// `useDirection().row`, hidden in clerk mode. Works identically on iOS, Android and web.

import type { BottomTabBarProps } from 'expo-router/js-tabs';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Icon, type IconName } from '@/design/components/Icon';
import { useTextStyle } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { size, space, type as typeScale } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useSession } from '@/store/session';

export const TAB_ICONS: Record<string, IconName> = {
  index: 'home',
  papers: 'papers',
  help: 'help',
  settings: 'settings',
};

export function TabBar({ state, descriptors, navigation, insets }: BottomTabBarProps) {
  const { colors } = useTheme();
  const dir = useDirection();
  const clerkMode = useSession((s) => s.clerkMode);
  const labelStyle = useTextStyle('caption', 'bold');
  if (clerkMode) return null;
  return (
    <View
      role="tablist"
      style={[
        styles.bar,
        {
          flexDirection: dir.row,
          backgroundColor: colors.surfaceRaised,
          borderTopColor: colors.divider,
          paddingBottom: insets.bottom,
        },
      ]}>
      {state.routes.map((route, index) => {
        const { options } = descriptors[route.key];
        const label =
          typeof options.tabBarLabel === 'string' ? options.tabBarLabel : (options.title ?? route.name);
        const focused = state.index === index;
        const color = focused ? colors.primary : colors.textMuted;
        const onPress = () => {
          const event = navigation.emit({ type: 'tabPress', target: route.key, canPreventDefault: true });
          if (!focused && !event.defaultPrevented) navigation.navigate(route.name, route.params);
        };
        const badge = options.tabBarBadge;
        return (
          <Pressable
            key={route.key}
            testID={`tab-${route.name}`}
            role="tab"
            aria-selected={focused}
            accessibilityState={{ selected: focused }}
            accessibilityLabel={badge !== undefined ? `${label}, ${badge}` : label}
            onPress={onPress}
            onLongPress={() => navigation.emit({ type: 'tabLongPress', target: route.key })}
            style={[styles.tab, focused ? { borderTopColor: colors.primary } : null]}>
            <View style={styles.iconWrap}>
              <Icon name={TAB_ICONS[route.name] ?? 'info'} color={color} size={size.icon} />
              {badge !== undefined ? (
                <View style={[styles.badge, { backgroundColor: colors.danger }]}>
                  <Text maxFontSizeMultiplier={typeScale.tabLabelMaxFontSizeMultiplier} style={[styles.badgeText, { color: colors.onDanger }]}>
                    {String(badge)}
                  </Text>
                </View>
              ) : null}
            </View>
            <Text
              numberOfLines={2}
              maxFontSizeMultiplier={typeScale.tabLabelMaxFontSizeMultiplier}
              style={[labelStyle, styles.label, { color, writingDirection: dir.writingDirection }]}>
              {label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  tab: {
    flex: 1,
    minHeight: size.tabBar,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: space.xs,
    gap: space.xxs,
    borderTopWidth: 3,
    borderTopColor: 'transparent',
  },
  iconWrap: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: {
    textAlign: 'center',
  },
  badge: {
    position: 'absolute',
    top: -6,
    right: -14,
    minWidth: 20,
    paddingHorizontal: 4,
    borderRadius: 10,
    alignItems: 'center',
  },
  badgeText: {
    fontSize: 14,
    fontWeight: '700',
  },
});
