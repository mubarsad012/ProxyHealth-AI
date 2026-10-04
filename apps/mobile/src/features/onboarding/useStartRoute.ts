// S0 redirect decision as a hook: waits for settings (AsyncStorage) and the consent record, uses the
// cached/fresh server config for the re-consent check, and returns the route once known.

import { useEffect } from 'react';

import { ensureServerConfig } from '@/api/config';
import { useSession } from '@/store/session';
import { useSettings, waitForSettings } from '@/store/settings';

import { aiSeenFor, startRoute, type StartRoute } from './consentModel';
import { loadConsent, useConsentDecision } from './consentState';

let configTried = false;

export function useStartRoute(): StartRoute | null {
  const hydrated = useSettings((s) => s.hydrated);
  const languageDecided = useSettings((s) => s.languageDecided);
  const loaded = useConsentDecision((s) => s.loaded);
  const decision = useConsentDecision((s) => s.decision);
  const record = useSession((s) => s.consent);
  const serverConfig = useSession((s) => s.serverConfig);
  const tier = useSession((s) => s.tier);

  useEffect(() => {
    void waitForSettings();
    void loadConsent();
    if (!configTried) {
      configTried = true;
      void ensureServerConfig();
    }
  }, []);

  if (!hydrated || !loaded) return null;
  return startRoute({
    languageDecided,
    decision,
    record,
    serverConsentVersion: serverConfig?.consent_version ?? null,
    tier,
    aiNow: serverConfig ? aiSeenFor(serverConfig) : undefined,
  });
}
