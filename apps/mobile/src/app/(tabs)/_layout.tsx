// Tabs group (D-27): one JS `Tabs` layout from expo-router on every platform — Home · My papers ·
// Get help · Settings — with the custom 64 pt icon + word tab bar (RTL order via useDirection,
// hidden in clerk mode). Screens: `index`, `papers`, `help` (WP6) and `settings` (WP4).
//
// S0 guard: `/` resolves to `(tabs)/index` as soon as WP6's Home exists, and deep links (`/papers`,
// `/settings`) land here too, so the same start-route rule as `src/app/index.tsx` runs here:
// first run → S1, no consent decision (or a stale one) → S2, otherwise the tabs.

import { type Href, Redirect } from 'expo-router';
import { Tabs } from 'expo-router/js-tabs';
import { useState } from 'react';
import { View } from 'react-native';

import { TabBar } from '@/design/components/TabBar';
import { useTheme } from '@/design/theme';
import { useStartRoute } from '@/features/onboarding/useStartRoute';
import { useUpcomingReminderCount } from '@/hooks/useUpcomingReminderCount';
import { useT } from '@/i18n/useT';

export default function TabsLayout() {
  const t = useT();
  const { colors } = useTheme();
  const [focusCount, setFocusCount] = useState(0);
  const upcoming = useUpcomingReminderCount(focusCount);
  const start = useStartRoute();
  if (!start) return <View style={{ flex: 1, backgroundColor: colors.background }} />;
  if (start !== '/(tabs)') return <Redirect href={start as Href} />;
  return (
    <Tabs
      tabBar={(props) => <TabBar {...props} />}
      screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: colors.background } }}
      screenListeners={{ focus: () => setFocusCount((n) => n + 1) }}>
      <Tabs.Screen name="index" options={{ title: t('tabs.home') }} />
      <Tabs.Screen
        name="papers"
        options={{ title: t('tabs.papers'), tabBarBadge: upcoming > 0 ? upcoming : undefined }}
      />
      <Tabs.Screen name="help" options={{ title: t('tabs.help') }} />
      <Tabs.Screen name="settings" options={{ title: t('tabs.settings') }} />
    </Tabs>
  );
}
