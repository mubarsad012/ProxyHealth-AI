// S16 route (PRODUCT_SPEC S16): `/troubleshoot`, `?mode=scam_check` for "Is this a scam?".

import { useLocalSearchParams } from 'expo-router';

import { parseMode, TroubleshootScreen } from '@/features/troubleshoot';

export default function TroubleshootRoute() {
  const params = useLocalSearchParams<{ mode?: string }>();
  return <TroubleshootScreen initialMode={parseMode(params.mode)} />;
}
