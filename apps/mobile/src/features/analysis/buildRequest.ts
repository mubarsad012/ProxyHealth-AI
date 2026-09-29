// `AnalyzeRequest` construction (API_CONTRACT §3.5, D-19, D-21; BUILD_PLAN §5.6 step 2).
// * `include_page_thumbnails` is always explicit: true when `pages[0]` is a PDF, false for images.
// * Web burns masks into the JPEG on a canvas → `masks: []` and `masks_applied_client_side: true`.
//   Native sends normalised `masks[]` and the server burns them (Pillow) before inference.
// * Pages are compressed (1600 px, JPEG 0.8, rotation baked in) right before sending.

import type { AnalyzeRequest, DocumentType, PageInput, Platform as ClientPlatform } from '@/api/types';
import { compressPage } from '@/features/scan/compress';
import { burnMasksOnCanvas, normaliseMask, toDataUrl } from '@/lib/image';
import type { CapturedPage } from '@/store/session';

export interface RequestContext {
  targetLanguage: string;
  uiDirection: 'ltr' | 'rtl';
  platform: ClientPlatform;
  analysisId: string;
  demoSampleId: string | null;
  state: string | null;
  zip3: string | null;
  hideIdNumbers: boolean;
  preferences: { tone: 'plain' | 'formal'; calendarNotes: string[]; dateFormat: 'auto' | 'mdy' | 'dmy' };
  documentHint?: DocumentType | null;
}

export interface PreparedPages {
  inputs: PageInput[];
  /** Pages as sent (compressed, rotation baked, masks burned on web) — used for crops later. */
  display: CapturedPage[];
  masksAppliedClientSide: boolean;
}

/** Pure request builder (exported for tests). */
export function buildAnalyzeRequest(prepared: Pick<PreparedPages, 'inputs' | 'masksAppliedClientSide'>, ctx: RequestContext): AnalyzeRequest {
  const firstIsPdf = prepared.inputs[0]?.mime_type === 'application/pdf';
  return {
    pages: prepared.inputs,
    target_language: ctx.targetLanguage,
    ui_direction: ctx.uiDirection,
    state: ctx.state,
    zip3: ctx.zip3,
    document_hint: ctx.documentHint ?? null,
    preferences: {
      tone: ctx.preferences.tone,
      calendar_notes: ctx.preferences.calendarNotes,
      date_format: ctx.preferences.dateFormat,
    },
    demo_sample_id: ctx.demoSampleId,
    include_page_thumbnails: firstIsPdf,
    masks_applied_client_side: prepared.masksAppliedClientSide,
    hide_id_numbers: ctx.hideIdNumbers,
    client_platform: ctx.platform,
    analysis_id: ctx.analysisId,
  };
}

/** Compress every page and apply masks per platform (web: canvas burn; native: `masks[]`). */
export async function preparePages(pages: CapturedPage[], platform: ClientPlatform): Promise<PreparedPages> {
  const inputs: PageInput[] = [];
  const display: CapturedPage[] = [];
  let burned = false;
  for (const raw of pages) {
    const page = await compressPage(raw);
    const base64 = page.base64 ?? '';
    if (page.mimeType === 'application/pdf') {
      inputs.push({ data_base64: base64, mime_type: 'application/pdf', rotation: 0, masks: [] });
      display.push(page);
      continue;
    }
    const masks = page.masks.map(normaliseMask).filter((m): m is NonNullable<typeof m> => m !== null);
    if (platform === 'web' && masks.length) {
      const burnedB64 = await burnMasksOnCanvas(base64, masks);
      burned = true;
      inputs.push({ data_base64: burnedB64, mime_type: 'image/jpeg', rotation: 0, masks: [] });
      display.push({ ...page, base64: burnedB64, uri: toDataUrl(burnedB64), masks });
    } else {
      inputs.push({ data_base64: base64, mime_type: 'image/jpeg', rotation: 0, masks });
      display.push(page);
    }
  }
  return { inputs, display, masksAppliedClientSide: burned };
}
