// Page images and transcript blocks for crops (D-09, PRODUCT_SPEC S7/S8). Page images come from
// the session pages (as sent: compressed, upright, masks burned on web), from vault files, or from
// `page_thumbnails` (server-rasterised PDF pages). bboxes are normalised to the page image the
// server saw, so the crop math needs no rotation.

import type { AnalysisResult, TextBlock } from '@/api/types';
import { toDataUrl } from '@/lib/image';
import type { CapturedPage } from '@/store/session';

export interface PageImage {
  uri: string;
  width: number | null;
  height: number | null;
}

/** The image for 1-based `page`, or null (quote-only fallback). */
export function pageImageFor(analysis: AnalysisResult, pages: readonly CapturedPage[], page: number): PageImage | null {
  const text = analysis.original_text.find((p) => p.page === page);
  const thumb = analysis.page_thumbnails?.find((p) => p.page === page);
  if (thumb) {
    return { uri: toDataUrl(thumb.data_base64, thumb.mime_type || 'image/jpeg'), width: thumb.width, height: thumb.height };
  }
  const images = pages.filter((p) => p.mimeType !== 'application/pdf');
  const img = images[page - 1];
  if (!img) return null;
  return {
    uri: img.uri,
    width: text?.width ?? img.width ?? null,
    height: text?.height ?? img.height ?? null,
  };
}

export function allBlocks(analysis: Pick<AnalysisResult, 'original_text'>): TextBlock[] {
  return analysis.original_text.flatMap((p) => p.blocks);
}

export function blockById(analysis: Pick<AnalysisResult, 'original_text'>, id: string): TextBlock | null {
  for (const p of analysis.original_text) {
    const b = p.blocks.find((x) => x.id === id);
    if (b) return b;
  }
  return null;
}

/** Union bbox of the referenced blocks on one page (null when none has a bbox). */
export function unionBbox(analysis: Pick<AnalysisResult, 'original_text'>, spanIds: readonly string[], page?: number): number[] | null {
  let box: number[] | null = null;
  for (const id of spanIds) {
    const b = blockById(analysis, id);
    if (!b || !b.bbox || b.bbox.length !== 4) continue;
    if (page !== undefined && b.page !== page) continue;
    const [x0, y0, x1, y1] = b.bbox;
    box = box
      ? [Math.min(box[0], x0), Math.min(box[1], y0), Math.max(box[2], x1), Math.max(box[3], y1)]
      : [x0, y0, x1, y1];
  }
  return box;
}

/** The page a set of spans lives on (first block's page), else `fallback`. */
export function pageOfSpans(analysis: Pick<AnalysisResult, 'original_text'>, spanIds: readonly string[], fallback: number): number {
  for (const id of spanIds) {
    const b = blockById(analysis, id);
    if (b) return b.page;
  }
  return fallback;
}
