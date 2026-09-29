// S1 route (`/onboarding/language`, also opened from S17 with `?from=settings`).

import { useLocalSearchParams } from 'expo-router';

import { LanguageScreen } from '@/features/onboarding/LanguageScreen';

export default function LanguageRoute() {
  const { from } = useLocalSearchParams<{ from?: string }>();
  return <LanguageScreen from={from === 'settings' ? 'settings' : 'onboarding'} />;
}
