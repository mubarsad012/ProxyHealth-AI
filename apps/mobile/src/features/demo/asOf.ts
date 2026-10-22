// The fixed "today" of the sample papers on the client (PRODUCT_SPEC §12.3). The server computes a
// sample's dates, urgency and `days_until` as of `DEMO_AS_OF` (apps/api/proxyhealth_api/demo/as_of.py)
// and the result screen says so in one fixed line (`demo.as_of_note`, "…as if today were October 2,
// 2026"). Anything the app itself decides about a sample's dates — "Remind me" eligibility and fire
// times — uses the same day, never the device clock, or every sample date would read as passed a few
// weeks after it. The constant, the Python constant and the note change together (asOf.test.ts).

import type { AnalysisResult } from '@/api/types';

/** `DEMO_AS_OF` from apps/api/proxyhealth_api/demo/as_of.py, as a calendar day. */
export const DEMO_AS_OF_ISO = '2026-10-02';

/** The pack key of the fixed line shown on sample results that have dates. */
export const DEMO_AS_OF_NOTE = 'demo.as_of_note';

/** A sample paper (or any mock-mode result): the `demo_sample` warning or `model_meta.demo`. */
export function isSampleAnalysis(a: Pick<AnalysisResult, 'warnings' | 'model_meta'> | null | undefined): boolean {
  if (!a) return false;
  return (a.warnings ?? []).includes('demo_sample') || Boolean(a.model_meta?.demo);
}

/** "Now" for a sample: the as-of calendar day at the device's current local time of day. */
export function sampleNow(real: Date): Date {
  const [y, m, d] = DEMO_AS_OF_ISO.split('-').map(Number);
  return new Date(y, m - 1, d, real.getHours(), real.getMinutes(), real.getSeconds(), real.getMilliseconds());
}
