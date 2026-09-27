// Seam stub (BUILD_PLAN §4.2 / §5.0). Owner after M0: WP5. Keep every export name and signature.

import type { ReactElement } from 'react';

import type { Safety } from '@/api/types';

export interface EmergencyCardProps {
  /** `Safety.emergency_kinds` values that drive which fixed rows are shown first. */
  kinds: string[];
  onClose(): void;
}

/** S19 fixed-copy emergency card (tel: links, 72 pt call buttons). Day-0 stub renders nothing. */
export function EmergencyCard(_props: EmergencyCardProps): ReactElement | null {
  return null;
}

export interface EmergencyTriggerState {
  /** True when the card should be shown before anything else on the screen. */
  triggered: boolean;
  kinds: string[];
}

/** Derive the emergency trigger from `AnalysisResult.safety` / `ChatAnswer.safety` (D-14: biased
 *  to over-trigger). Day-0 stub never triggers. */
export function useEmergencyTrigger(_safety: Safety | null): EmergencyTriggerState {
  return { triggered: false, kinds: [] };
}
