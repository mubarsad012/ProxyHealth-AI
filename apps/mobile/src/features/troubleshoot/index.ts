// Troubleshoot (PRODUCT_SPEC S16, D-13). Owner: WP6 lane 6B. Rendered by `app/troubleshoot.tsx`
// (`?mode=scam_check` opens "Is this a scam?").

export { pickScreenshot, type Screenshot, toPageInput, toScreenshot } from './pick';
export {
  buildTroubleshootRequest,
  clampGoal,
  MAX_GOAL_CHARS,
  NotAnImageError,
  parseMode,
  PORTAL_HINTS,
  SAMPLE_SCREENSHOT_ID,
} from './request';
export { buildEvidenceDocument, canSaveEvidence, saveScamEvidence } from './evidence';
export {
  askPersonHref,
  CredentialGuard,
  EvidenceButton,
  type EvidenceControl,
  TroubleshootResultCards,
} from './ResultCards';
export { MAX_REPORT_RESOURCES, reportingResources, ScamReportResources } from './ScamReport';
export { TroubleshootScreen, type TroubleshootScreenProps } from './TroubleshootScreen';
export { offlineSampleResult, type TroubleshootState, useTroubleshoot } from './useTroubleshoot';
