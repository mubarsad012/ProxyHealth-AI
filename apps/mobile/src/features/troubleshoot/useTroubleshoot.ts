// Troubleshoot request state (PRODUCT_SPEC S16): two honest progress steps, typed errors, and the
// demo path — the sample screenshot `portal_file_too_large` is fetched from `/v1/demo/fixtures`
// and sent with `demo_sample_id`; with no server the recorded result is served from the bundle
// (sample only — a real screenshot is never faked, api/offline.ts).

import { useRef, useState } from 'react';

import type { ApiClient } from '@/api/client';
import { useApi } from '@/api/config';
import { type ApiError, toApiError } from '@/api/errors';
import type { PageInput, TroubleshootRequest, TroubleshootResult } from '@/api/types';
import { bytesToBase64 } from '@/features/quicksheet/base64';

// Relative on purpose: jest maps `@/` to `src/` only, so `@/assets/…` (and `@/api/offline`) do not
// resolve under jest (CL filed); Metro and tsc accept this path too.
import { fixtureAssets } from '../../../assets/fixtures';

import { SAMPLE_SCREENSHOT_ID } from './request';

export type TroubleshootStatus = 'idle' | 'loading' | 'done' | 'error';

export interface TroubleshootState {
  status: TroubleshootStatus;
  /** 0 = "Reading the screen", 1 = "Explaining". */
  step: 0 | 1;
  result: TroubleshootResult | null;
  error: ApiError | null;
  /** The result is the bundled recording of the sample (no server). */
  offlineSample: boolean;
}

export const IDLE_STATE: TroubleshootState = { status: 'idle', step: 0, result: null, error: null, offlineSample: false };
const STEP_MS = 2500;

export function isTroubleshootResult(value: unknown): value is TroubleshootResult {
  return Boolean(value) && typeof value === 'object' && 'screen_summary' in (value as object) && 'steps' in (value as object);
}

/** The sample screenshot as a `PageInput` (PNG from the demo endpoint). */
export async function fetchSampleScreenshot(client: ApiClient): Promise<PageInput> {
  const res = await fetch(client.fixturePageUrl(SAMPLE_SCREENSHOT_ID, 1));
  if (!res.ok) throw new Error(`sample ${res.status}`);
  const bytes = new Uint8Array(await res.arrayBuffer());
  return { mime_type: 'image/png', data_base64: bytesToBase64(bytes), masks: [], rotation: 0 };
}

/** The recorded sample result (exact language, else English); never used for a real screenshot. */
export function offlineSampleResult(language: string): TroubleshootResult | null {
  const results = fixtureAssets[SAMPLE_SCREENSHOT_ID]?.results ?? {};
  const raw = results[language] ?? results.en;
  return isTroubleshootResult(raw) ? raw : null;
}

export function useTroubleshoot() {
  const client = useApi();
  const [state, setState] = useState<TroubleshootState>(IDLE_STATE);
  const seq = useRef(0);

  const submit = async (req: TroubleshootRequest): Promise<void> => {
    const id = ++seq.current;
    setState({ ...IDLE_STATE, status: 'loading' });
    const timer = setTimeout(() => {
      if (seq.current === id) setState((s) => (s.status === 'loading' ? { ...s, step: 1 } : s));
    }, STEP_MS);
    try {
      const result = await client.troubleshoot(req);
      if (seq.current === id) setState({ status: 'done', step: 1, result, error: null, offlineSample: false });
    } catch (e) {
      if (seq.current !== id) return;
      const error = toApiError(e);
      const offline = error.code === 'network' || error.code === 'timeout';
      const recorded = req.demo_sample_id && offline ? offlineSampleResult(req.target_language) : null;
      setState(
        recorded
          ? { status: 'done', step: 1, result: recorded, error: null, offlineSample: true }
          : { status: 'error', step: 0, result: null, error, offlineSample: false },
      );
    } finally {
      clearTimeout(timer);
    }
  };

  /** Demo: send the sample screenshot; offline → the bundled recording. */
  const runSample = async (build: (screenshot: PageInput) => TroubleshootRequest, language: string): Promise<void> => {
    let screenshot: PageInput;
    try {
      screenshot = await fetchSampleScreenshot(client);
    } catch {
      const recorded = offlineSampleResult(language);
      seq.current += 1;
      setState(
        recorded
          ? { status: 'done', step: 1, result: recorded, error: null, offlineSample: true }
          : { ...IDLE_STATE, status: 'error', error: toApiError(new Error('network')) },
      );
      return;
    }
    await submit(build(screenshot));
  };

  const reset = () => {
    seq.current += 1;
    setState(IDLE_STATE);
  };

  return { ...state, submit, runSample, reset };
}
