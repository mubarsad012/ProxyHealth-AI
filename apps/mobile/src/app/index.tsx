// S0 redirect (PRODUCT_SPEC S0): no language → S1; no consent decision → S2; an accepted consent
// that no longer matches the server's version or tier → S2; else the tabs. While settings and the
// consent record load, the splash screen is still up (root layout gate), so nothing flashes.

import { type Href, Redirect } from 'expo-router';
import { View } from 'react-native';

import { useTheme } from '@/design/theme';
import { useStartRoute } from '@/features/onboarding/useStartRoute';

export default function Index() {
  const route = useStartRoute();
  const { colors } = useTheme();
  if (!route) return <View style={{ flex: 1, backgroundColor: colors.background }} />;
  return <Redirect href={route as Href} />;
}
