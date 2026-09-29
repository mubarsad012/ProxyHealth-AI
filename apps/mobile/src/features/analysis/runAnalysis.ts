// One analysis round trip (PRODUCT_SPEC S6, API_CONTRACT §3.5). Pure of React so it can be tested
// with a mocked client: prepare pages → build `AnalyzeRequest` → `client.analyze` (120 s timeout
// in the client) → result. Sample papers fall back to the bundled recorded result ONLY when the
// server is unreachable (D-29); a real scan is never faked.

import type { ApiClient } from '@/api/client';
import { ApiError, toApiError } from '@/api/errors';
import { bundledFixtureResult } from '@/api/offline';
import type { AnalysisResult, AnalyzeRequest, Platform as ClientPlatform } from '@/api/types';
import type { CapturedPage } from '@/store/session';

import { buildAnalyzeRequest, preparePages, type RequestContext } from './buildRequest';

export interface RunAnalysisInput {
  client: ApiClient;
  pages: CapturedPage[];
  ctx: RequestContext;
  signal?: AbortSignal;
  /** Test hook: observe the exact request that was sent. */
  onRequest?(req: AnalyzeRequest): void;
}

export interface RunAnalysisOutput {
  result: AnalysisResult;
  /** Pages as sent (compressed, masks burned on web); empty for sample papers. */
  displayPages: CapturedPage[];
  /** True when a bundled recorded sample result was used because the server was unreachable. */
  offlineSample: boolean;
}

export function isAnalysisResult(value: unknown): value is AnalysisResult {
  return Boolean(value && typeof value === 'object' && 'analysis_id' in value && 'demands' in value);
}

export async function runAnalysis({ client, pages, ctx, signal, onRequest }: RunAnalysisInput): Promise<RunAnalysisOutput> {
  const sample = ctx.demoSampleId;
  const prepared = sample
    ? { inputs: [], display: [] as CapturedPage[], masksAppliedClientSide: false }
    : await preparePages(pages, ctx.platform as ClientPlatform);
  if (signal?.aborted) throw new ApiError({ code: 'timeout', status: 0, message: 'aborted' });
  if (!sample && !prepared.inputs.length) {
    throw new ApiError({ code: 'invalid_request', status: 400, message: 'no pages' });
  }
  const req = buildAnalyzeRequest(prepared, ctx);
  onRequest?.(req);
  try {
    const result = await client.analyze(req, { signal });
    return { result, displayPages: prepared.display, offlineSample: false };
  } catch (e) {
    const err = toApiError(e);
    if (sample && err.code === 'network') {
      const recorded = bundledFixtureResult(sample, ctx.targetLanguage);
      if (recorded && isAnalysisResult(recorded.result)) {
        return { result: { ...recorded.result, analysis_id: ctx.analysisId }, displayPages: [], offlineSample: true };
      }
    }
    throw err;
  }
}
