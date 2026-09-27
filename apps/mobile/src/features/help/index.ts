// Seam stub (BUILD_PLAN §4.2 / §5.0). Owner after M0: WP6. Keep every export name and signature.

import type { ReactElement } from 'react';

import type { ApiError } from '@/api/errors';
import type { AnalysisResult, ResourceMatchRequest, ResourceMatchResponse } from '@/api/types';

export interface HelpForDocumentProps {
  analysis: AnalysisResult;
}

/** S11 Action Hub for one document. Day-0 stub renders nothing. */
export function HelpForDocument(_props: HelpForDocumentProps): ReactElement | null {
  return null;
}

export interface ResourceMatchState {
  data: ResourceMatchResponse | null;
  loading: boolean;
  error: ApiError | null;
  cached: boolean;
}

/** POST /v1/resources/match with per-document caching. Day-0 stub never loads. */
export function useResourceMatch(_req: ResourceMatchRequest | null): ResourceMatchState {
  return { data: null, loading: false, error: null, cached: false };
}
