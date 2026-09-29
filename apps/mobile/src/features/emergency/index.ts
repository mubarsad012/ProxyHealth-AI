// Emergency seam (BUILD_PLAN §4.2 / §5.0; owner WP5). Keep every export name and signature.
// S19 fixed-copy card + the trigger derived from `AnalysisResult.safety` / `ChatAnswer.safety`.

import { useEffect, useRef } from 'react';
import { AccessibilityInfo } from 'react-native';

import type { Safety } from '@/api/types';
import { t } from '@/i18n/store';

export {
  EMERGENCY_ROWS,
  EmergencyCard,
  type EmergencyCardProps,
  emergencyKindWords,
  isDesktopWeb,
  openHref,
} from './EmergencyCard';

export interface EmergencyTriggerState {
  /** True when the card should be shown before anything else on the screen. */
  triggered: boolean;
  kinds: string[];
}

/** Pure derivation (D-14: biased to over-trigger — any kind counts even if the flag is off). */
export function emergencyTrigger(safety: Safety | null | undefined): EmergencyTriggerState {
  if (!safety) return { triggered: false, kinds: [] };
  const kinds = safety.emergency_kinds ?? [];
  return { triggered: Boolean(safety.emergency) || kinds.length > 0, kinds };
}

/** Derive the emergency trigger and announce `a11y.emergency_shown` once when it fires. */
export function useEmergencyTrigger(safety: Safety | null): EmergencyTriggerState {
  const state = emergencyTrigger(safety);
  const announced = useRef(false);
  useEffect(() => {
    if (!state.triggered || announced.current) return;
    announced.current = true;
    try {
      AccessibilityInfo.announceForAccessibility(t('a11y.emergency_shown'));
    } catch {
      // best-effort announcement
    }
  }, [state.triggered]);
  return state;
}
