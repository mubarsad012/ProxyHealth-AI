// Which sample paper produced which analysis (memory only, this app session; SEC-01). A request
// about an analysis — chat today — takes `demo_sample_id` from here, never from
// `session.demoSampleId`: that field can be left over from an earlier sample while a real saved
// paper is open, and a demo id makes the server skip the consent and unpaid-tier gates and use
// the pinned sample "today" (PRODUCT_SPEC §12.3). No entry → `null` → the server treats the paper
// as real, which is the safe side (a sample saved in an earlier session is then gated like one).

import type { AnalysisResult } from '@/api/types';

import { isSampleResult } from './disclaimers';

const origin = new Map<string, string>();

/** Record that `analysisId` is the result of `POST /v1/analyze` with `demo_sample_id=sampleId`. */
export function rememberSampleOrigin(analysisId: string, sampleId: string): void {
  if (analysisId && sampleId) origin.set(analysisId, sampleId);
}

/** The fixture id to send with requests about `a`: only for a sample result this session made. */
export function sampleIdForAnalysis(a: Pick<AnalysisResult, 'analysis_id' | 'model_meta' | 'warnings'>): string | null {
  if (!isSampleResult(a)) return null;
  return origin.get(a.analysis_id) ?? null;
}

/** Test hook / "Delete everything". */
export function forgetSampleOrigins(): void {
  origin.clear();
}
