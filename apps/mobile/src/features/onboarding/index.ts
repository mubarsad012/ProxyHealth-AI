// Onboarding feature (ARCHITECTURE §3 `features/onboarding/`): S0 redirect, S1 language grid,
// S1b adapting, S2 consent view-model and screen, the in-app privacy notice, S18.

export { AdaptingScreen, type AdaptingScreenProps, STEP_TIMERS_MS } from './AdaptingScreen';
export {
  type AiCopyInput,
  aiSeenFor,
  consentView,
  type ConsentView,
  consentVars,
  namesOtherAi,
  startRoute,
  type StartRoute,
  tierCopy,
  type TierCopy,
  viewTier,
  type ViewTier,
} from './consentModel';
export { ConsentScreen, TABS_HREF, TABS_SAMPLE_HREF } from './ConsentScreen';
export {
  acceptConsent,
  declineConsent,
  loadConsent,
  previousRecord,
  resetConsentState,
  useConsentDecision,
  withdrawConsent,
} from './consentState';
export { gridLanguages, PINNED_FIRST, typedQueryUsable, withSuggestionFirst } from './languageGrid';
export { adaptingHref, afterLanguageHref, LanguageScreen } from './LanguageScreen';
export { NotFoundScreen } from './NotFoundScreen';
export { PrivacyNotice, PrivacyNoticeContent, privacyNoticeKeys } from './PrivacyNotice';
export { useStartRoute } from './useStartRoute';
