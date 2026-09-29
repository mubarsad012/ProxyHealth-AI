// S2 route (`/onboarding/consent`). Android back equals "Not now" (COMPLIANCE_PRIVACY §4.2: no
// consent by backing out).

import { type Href, router, useFocusEffect } from 'expo-router';
import { useCallback } from 'react';
import { BackHandler } from 'react-native';

import { ConsentScreen, TABS_HREF } from '@/features/onboarding/ConsentScreen';
import { declineConsent, useConsentDecision } from '@/features/onboarding/consentState';

export default function ConsentRoute() {
  useFocusEffect(
    useCallback(() => {
      const sub = BackHandler.addEventListener('hardwareBackPress', () => {
        if (useConsentDecision.getState().decision !== 'accepted') {
          void declineConsent().then(() => router.replace(TABS_HREF as Href));
          return true;
        }
        return false;
      });
      return () => sub.remove();
    }, []),
  );
  return <ConsentScreen />;
}
