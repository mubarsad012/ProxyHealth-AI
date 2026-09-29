// Analysis feature (ARCHITECTURE §3 features/analysis; BUILD_PLAN §5.6 step 2): request building,
// the analyze hook, the S7 cards and the result view. Screens import from here.

export { buildAnalyzeRequest, preparePages, type PreparedPages, type RequestContext } from './buildRequest';
export { canRemind, DemandRow, DemandsCard, roleWord } from './cards/DemandsCard';
export { DetailsSection } from './cards/DetailsSection';
export { HelpPreview, whyLine } from './cards/HelpPreview';
export { GlossaryCard, QuestionsCard } from './cards/InfoCards';
export { PlanCard, usePlanChecks } from './cards/PlanCard';
export { redFlagText, RedFlagsCard, ScamCard, sortRedFlags, WarningChips } from './cards/SafetyCards';
export { FactRow, type ResultCardProps, type ResultHandlers } from './cards/shared';
export { showEnglishBody, SummaryCard } from './cards/SummaryCard';
export { disclaimerKey, resultBanners, WARNING_CHIP_KEYS, warningChipKeys } from './disclaimers';
export { hearItItems } from './hearItMode';
export { allBlocks, blockById, pageImageFor, pageOfSpans, unionBbox, type PageImage } from './pageImages';
export { ResultView, type ResultViewHandlers, type ResultViewProps } from './ResultView';
export { isAnalysisResult, runAnalysis, type RunAnalysisInput, type RunAnalysisOutput } from './runAnalysis';
export { UnverifiedSection } from './unverifiedSection';
export {
  type AnalyzeState,
  type AnalyzeStatus,
  currentRequestContext,
  datesFound,
  MIN_ON_SCREEN_MS,
  STEP_TIMES_MS,
  useAnalyze,
} from './useAnalyze';
export { drivingDemand, firstPrintedPhone, printedPhoneHref, urgencySpeech } from './urgencyCopy';
