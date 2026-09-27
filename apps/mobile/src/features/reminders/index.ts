// Seam stub (BUILD_PLAN §4.2 / §5.0). Owner after M0: WP6. Keep every export name and signature.

import type { AnalysisResult, Demand } from '@/api/types';
import type { Reminder } from '@/storage';

export type ScheduleOutcome = 'scheduled' | 'ics' | 'denied' | 'not_eligible';

export interface RemindersApi {
  /** 7/3/1-day 9 am reminders on native; `.ics` on web; generic bodies unless opted in. */
  scheduleForDemand(
    analysis: AnalysisResult,
    demand: Demand,
    documentId?: string,
  ): Promise<ScheduleOutcome>;
  list(): Promise<Reminder[]>;
  remove(id: string): Promise<void>;
}

/** Day-0 stub: nothing is eligible and the list is empty. */
export function useReminders(): RemindersApi {
  return {
    scheduleForDemand: () => Promise.resolve('not_eligible'),
    list: () => Promise.resolve([]),
    remove: () => Promise.resolve(),
  };
}
