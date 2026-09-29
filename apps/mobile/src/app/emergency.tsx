// S19 — Emergency card (modal). Opened by "Need help now?" on every screen, by
// `AnalysisResult.safety.emergency`, by `ChatAnswer.safety.emergency` and by the `need.crisis`
// tile. Query: `?kinds=chest_pain,overdose` adds the fixed context line.

import { type Href, router, useLocalSearchParams } from 'expo-router';

import { Screen } from '@/design/components/Screen';
import { EmergencyCard } from '@/features/emergency';

export default function EmergencyRoute() {
  const params = useLocalSearchParams<{ kinds?: string }>();
  const kinds = (params.kinds ?? '')
    .split(',')
    .map((k) => k.trim())
    .filter(Boolean);
  const close = () => {
    if (router.canGoBack()) router.back();
    else router.replace('/' as Href);
  };
  return (
    <Screen back onBack={close} hideHelpLink testID="emergency-screen">
      <EmergencyCard
        kinds={kinds}
        triggered={kinds.length > 0}
        onClose={close}
        onMoreHelp={() => router.push('/help?emergency=1' as Href)}
      />
    </Screen>
  );
}
