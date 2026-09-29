// AnalyzeRequest construction (BUILD_PLAN §5.6 Acceptance; API_CONTRACT §3.5; D-19). With a mocked
// API client (the "api-client mock log"): web burns masks and sends `masks: []` +
// `masks_applied_client_side: true`; native sends normalised `masks[]`; PDFs set
// `include_page_thumbnails: true`; samples send `pages: []` + `demo_sample_id` and fall back to
// the bundled recorded result only when the server is unreachable.

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { AnalysisResult, AnalyzeRequest } from '@/api/types';
import type { CapturedPage } from '@/store/session';

import { buildAnalyzeRequest, preparePages, type RequestContext } from './buildRequest';
import { runAnalysis } from './runAnalysis';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('@/lib/image', () => {
  const actual = jest.requireActual('@/lib/image');
  return {
    ...actual,
    toJpegBase64: jest.fn(async () => ({ base64: 'SlBFRw==', width: 1200, height: 1600, byteLength: 4 })),
    burnMasksOnCanvas: jest.fn(async () => 'QlVSTkVE'),
  };
});

jest.mock('@/lib/pdf', () => {
  const actual = jest.requireActual('@/lib/pdf');
  return { ...actual, readPdfBase64: jest.fn(async () => ({ base64: 'JVBERi0=', byteLength: 5 })) };
});

// jest-expo maps `@/assets/*` to `src/assets` (only the first tsconfig path is used), so the real
// `api/offline` cannot load its fixture map under Jest; this stand-in serves the synced file.
jest.mock('@/api/offline', () => ({
  bundledFixtureResult: (id: string) =>
    id === 'medicaid_address_confirmation'
      ? { result: jest.requireActual('../../../assets/fixtures/medicaid_address_confirmation.result.en.json'), language: 'en' }
      : null,
}));

const image = jest.requireMock('@/lib/image') as { burnMasksOnCanvas: jest.Mock; toJpegBase64: jest.Mock };

function page(patch: Partial<CapturedPage> = {}): CapturedPage {
  return {
    id: 'page_1',
    uri: 'file:///tmp/p1.jpg',
    mimeType: 'image/jpeg',
    rotation: 0,
    masks: [{ x0: 0.62, y0: 0.08, x1: 0.95, y1: 0.12 }],
    source: 'camera',
    ...patch,
  };
}

function ctx(patch: Partial<RequestContext> = {}): RequestContext {
  return {
    targetLanguage: 'prs',
    uiDirection: 'rtl',
    platform: 'web',
    analysisId: 'a3f1c9e2-7b4d-4e0a-9c2b-5d6e7f8a9b0c',
    demoSampleId: null,
    state: 'VA',
    zip3: '223',
    hideIdNumbers: false,
    preferences: { tone: 'plain', calendarNotes: [], dateFormat: 'auto' },
    ...patch,
  };
}

function fakeClient(analyze: (req: AnalyzeRequest) => Promise<AnalysisResult>): { client: ApiClient; log: AnalyzeRequest[] } {
  const log: AnalyzeRequest[] = [];
  const client = {
    analyze: jest.fn(async (req: AnalyzeRequest) => {
      log.push(req);
      return analyze(req);
    }),
  } as unknown as ApiClient;
  return { client, log };
}

const okResult = (id: string) =>
  ({ analysis_id: id, demands: [], quality: { readable: true } }) as unknown as AnalysisResult;

beforeEach(() => jest.clearAllMocks());

describe('preparePages', () => {
  it('web burns masks on a canvas and sends masks: []', async () => {
    const out = await preparePages([page()], 'web');
    expect(image.burnMasksOnCanvas).toHaveBeenCalledTimes(1);
    expect(out.masksAppliedClientSide).toBe(true);
    expect(out.inputs).toEqual([{ data_base64: 'QlVSTkVE', mime_type: 'image/jpeg', rotation: 0, masks: [] }]);
  });

  it('native sends normalised masks[] and never burns', async () => {
    const out = await preparePages([page({ masks: [{ x0: 0.95, y0: 0.12, x1: 0.62, y1: 0.08 }] })], 'android');
    expect(image.burnMasksOnCanvas).not.toHaveBeenCalled();
    expect(out.masksAppliedClientSide).toBe(false);
    expect(out.inputs[0].masks).toEqual([{ x0: 0.62, y0: 0.08, x1: 0.95, y1: 0.12 }]);
  });

  it('bakes rotation into the JPEG and sends rotation 0', async () => {
    const out = await preparePages([page({ rotation: 90, masks: [] })], 'ios');
    expect(image.toJpegBase64).toHaveBeenCalledWith({ uri: 'file:///tmp/p1.jpg' }, { maxEdge: 1600, quality: 0.8, rotation: 90 });
    expect(out.inputs[0].rotation).toBe(0);
    expect(out.display[0].uri.startsWith('data:image/jpeg;base64,')).toBe(true);
  });
});

describe('buildAnalyzeRequest', () => {
  it('sets include_page_thumbnails explicitly per first page type', () => {
    const pdf = buildAnalyzeRequest(
      { inputs: [{ data_base64: 'x', mime_type: 'application/pdf', rotation: 0, masks: [] }], masksAppliedClientSide: false },
      ctx(),
    );
    expect(pdf.include_page_thumbnails).toBe(true);
    const img = buildAnalyzeRequest(
      { inputs: [{ data_base64: 'x', mime_type: 'image/jpeg', rotation: 0, masks: [] }], masksAppliedClientSide: false },
      ctx(),
    );
    expect(img.include_page_thumbnails).toBe(false);
    expect(img).toMatchObject({
      client_platform: 'web',
      target_language: 'prs',
      ui_direction: 'rtl',
      state: 'VA',
      zip3: '223',
      analysis_id: 'a3f1c9e2-7b4d-4e0a-9c2b-5d6e7f8a9b0c',
      preferences: { tone: 'plain', calendar_notes: [], date_format: 'auto' },
      hide_id_numbers: false,
      demo_sample_id: null,
    });
  });
});

describe('runAnalysis against a mocked client', () => {
  it('web request with hidden parts: masks_applied_client_side true and empty masks', async () => {
    const { client, log } = fakeClient(async (req) => okResult(req.analysis_id ?? ''));
    const out = await runAnalysis({ client, pages: [page()], ctx: ctx() });
    expect(log).toHaveLength(1);
    expect(log[0].masks_applied_client_side).toBe(true);
    expect(log[0].pages?.every((p) => (p.masks ?? []).length === 0)).toBe(true);
    expect(out.offlineSample).toBe(false);
  });

  it('PDF request asks for page thumbnails', async () => {
    const { client, log } = fakeClient(async (req) => okResult(req.analysis_id ?? ''));
    await runAnalysis({
      client,
      pages: [page({ mimeType: 'application/pdf', masks: [], source: 'pdf', uri: 'blob:x' })],
      ctx: ctx({ platform: 'android' }),
    });
    expect(log[0].include_page_thumbnails).toBe(true);
    expect(log[0].pages?.[0]).toEqual({ data_base64: 'JVBERi0=', mime_type: 'application/pdf', rotation: 0, masks: [] });
  });

  it('sample sends pages: [] with demo_sample_id and falls back to the bundled result offline', async () => {
    const { client, log } = fakeClient(async () => {
      throw new ApiError({ code: 'network', status: 0 });
    });
    const out = await runAnalysis({ client, pages: [], ctx: ctx({ demoSampleId: 'medicaid_address_confirmation', targetLanguage: 'en' }) });
    expect(log[0].pages).toEqual([]);
    expect(log[0].demo_sample_id).toBe('medicaid_address_confirmation');
    expect(out.offlineSample).toBe(true);
    expect(out.result.summary.title.length).toBeGreaterThan(0);
  });

  it('never fakes a real scan when offline', async () => {
    const { client } = fakeClient(async () => {
      throw new ApiError({ code: 'network', status: 0 });
    });
    await expect(runAnalysis({ client, pages: [page({ masks: [] })], ctx: ctx({ platform: 'ios' }) })).rejects.toMatchObject({
      code: 'network',
    });
  });
});
