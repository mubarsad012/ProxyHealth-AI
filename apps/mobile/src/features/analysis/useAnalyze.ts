// `useAnalyze` (ARCHITECTURE §3 features/analysis; PRODUCT_SPEC S6). Honest progress: the three
// steps advance on timers (0 / 6 / 18 s) and never claim completion early; tips at 20 s and 60 s;
// at least 1.5 s on screen even when the mock answers in 300 ms; Cancel aborts the request.

import { useCallback, useEffect, useRef, useState } from 'react';
import { AccessibilityInfo } from 'react-native';

import { useApi } from '@/api/config';
import type { ApiError } from '@/api/errors';
import { toApiError } from '@/api/errors';
import type { AnalysisResult } from '@/api/types';
import { t, useI18n } from '@/i18n/store';
import { newId } from '@/lib/ids';
import { platformName } from '@/lib/platform';
import { useSession } from '@/store/session';
import { useSettings } from '@/store/settings';

import type { RequestContext } from './buildRequest';
import { runAnalysis } from './runAnalysis';
import { rememberSampleOrigin } from './sampleOrigin';

export type AnalyzeStatus = 'idle' | 'running' | 'done' | 'unreadable' | 'error' | 'cancelled';

export interface AnalyzeState {
  status: AnalyzeStatus;
  /** 0..2 = step in progress; 3 = finished. */
  step: number;
  tipKey: 'reading.tip_long' | 'reading.tip_still' | null;
  error: ApiError | null;
  result: AnalysisResult | null;
  offlineSample: boolean;
}

export const STEP_TIMES_MS = [0, 6_000, 18_000] as const;
export const TIP_LONG_MS = 20_000;
export const TIP_STILL_MS = 60_000;
export const MIN_ON_SCREEN_MS = 1_500;

const initial: AnalyzeState = { status: 'idle', step: 0, tipKey: null, error: null, result: null, offlineSample: false };

/** The request context from settings + session + the active pack. */
export function currentRequestContext(analysisId: string = newId()): RequestContext {
  const settings = useSettings.getState();
  const session = useSession.getState();
  const pack = useI18n.getState().pack;
  return {
    targetLanguage: pack.tag,
    uiDirection: pack.direction,
    platform: platformName(),
    analysisId,
    demoSampleId: session.demoSampleId,
    state: settings.region.state,
    zip3: settings.region.zip3,
    hideIdNumbers: settings.hideIdNumbers,
    preferences: settings.preferences,
  };
}

/** Count of dates found, for `a11y.reading_finished`. */
export function datesFound(result: AnalysisResult): number {
  return result.demands.filter((d) => d.date !== null).length;
}

export function useAnalyze(): AnalyzeState & { start(): void; cancel(): void; reset(): void } {
  const client = useApi();
  const [state, setState] = useState<AnalyzeState>(initial);
  const controller = useRef<AbortController | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const runId = useRef(0);

  const clearTimers = useCallback(() => {
    for (const id of timers.current) clearTimeout(id);
    timers.current = [];
  }, []);

  useEffect(
    () => () => {
      runId.current += 1;
      controller.current?.abort();
      clearTimers();
    },
    [clearTimers],
  );

  const start = useCallback(() => {
    runId.current += 1;
    const mine = runId.current;
    controller.current?.abort();
    clearTimers();
    const ac = new AbortController();
    controller.current = ac;
    const startedAt = Date.now();
    setState({ ...initial, status: 'running' });
    STEP_TIMES_MS.forEach((ms, i) => {
      if (i > 0) timers.current.push(setTimeout(() => mine === runId.current && setState((s) => ({ ...s, step: i })), ms));
    });
    timers.current.push(setTimeout(() => mine === runId.current && setState((s) => ({ ...s, tipKey: 'reading.tip_long' })), TIP_LONG_MS));
    timers.current.push(setTimeout(() => mine === runId.current && setState((s) => ({ ...s, tipKey: 'reading.tip_still' })), TIP_STILL_MS));

    const session = useSession.getState();
    const ctx = currentRequestContext();
    void (async () => {
      try {
        const out = await runAnalysis({ client, pages: session.pages, ctx, signal: ac.signal });
        const wait = MIN_ON_SCREEN_MS - (Date.now() - startedAt);
        if (wait > 0) await new Promise((r) => setTimeout(r, wait));
        if (mine !== runId.current) return;
        clearTimers();
        if (!out.result.quality.readable) {
          setState((s) => ({ ...s, status: 'unreadable', step: 3, result: out.result }));
          return;
        }
        if (out.displayPages.length) useSession.getState().setPages(out.displayPages);
        if (ctx.demoSampleId) rememberSampleOrigin(out.result.analysis_id, ctx.demoSampleId);
        useSession.getState().setCurrentAnalysis(out.result);
        try {
          AccessibilityInfo.announceForAccessibility(t('a11y.reading_finished', { n: datesFound(out.result) }));
        } catch {
          // best-effort
        }
        setState((s) => ({ ...s, status: 'done', step: 3, result: out.result, offlineSample: out.offlineSample }));
      } catch (e) {
        if (mine !== runId.current) return;
        clearTimers();
        if (ac.signal.aborted) {
          setState((s) => ({ ...s, status: 'cancelled' }));
          return;
        }
        setState((s) => ({ ...s, status: 'error', error: toApiError(e) }));
      }
    })();
  }, [client, clearTimers]);

  const cancel = useCallback(() => {
    runId.current += 1;
    controller.current?.abort();
    clearTimers();
    setState((s) => ({ ...s, status: 'cancelled' }));
  }, [clearTimers]);

  const reset = useCallback(() => setState(initial), []);

  return { ...state, start, cancel, reset };
}
