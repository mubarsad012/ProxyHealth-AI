// Clerk feature (ARCHITECTURE §3 features/clerk; D-18): card view-model, the S10 screen and the
// 1.5 s long-press exit.

export { ClerkScreen, type ClerkScreenProps, splitGreeting } from './ClerkScreen';
export {
  type ClerkCard,
  clerkCardFromAnalysis,
  clerkCopyText,
  CLERK_HOLD_MS,
  CLERK_OWN_WORDS_MAX,
  CLERK_PRESETS,
  type ClerkNeed,
  type ClerkPreset,
  genericClerkCard,
  languageNameEn,
  needLines,
} from './clerkModel';
export { LongPressExit, type LongPressExitProps } from './LongPressExit';
