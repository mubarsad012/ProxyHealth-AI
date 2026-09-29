// S1b route (`/onboarding/adapting?q=<tag or typed name>&from=onboarding|settings`).

import { useLocalSearchParams } from 'expo-router';

import { AdaptingScreen } from '@/features/onboarding/AdaptingScreen';

export default function AdaptingRoute() {
  const { q, from } = useLocalSearchParams<{ q?: string; from?: string }>();
  return <AdaptingScreen query={typeof q === 'string' ? q : ''} from={from === 'settings' ? 'settings' : 'onboarding'} />;
}
