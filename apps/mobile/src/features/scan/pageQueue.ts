// Page-list rules for S4/S5 (PRODUCT_SPEC S4 states): photos OR exactly one PDF, never both;
// at most `limits.max_pages` photos; a PDF over `limits.max_pdf_bytes` is refused before upload.

import type { ApiError } from '@/api/errors';
import type { Limits } from '@/api/types';
import { checkPdfSize } from '@/lib/pdf';
import type { CapturedPage } from '@/store/session';

import { DEFAULT_MAX_PAGES } from './pick';

export type PickOutcome =
  | { kind: 'ok'; pages: CapturedPage[] }
  | { kind: 'page_cap'; pages: CapturedPage[]; maxPages: number }
  | { kind: 'pdf_or_photos'; pages: CapturedPage[] }
  | { kind: 'too_large'; pages: CapturedPage[]; error: ApiError };

/** Merge newly picked pages into the current list (pure; exported for tests). */
export function pagesAfterPick(
  current: CapturedPage[],
  picked: CapturedPage[],
  limits: Pick<Limits, 'max_pages' | 'max_pdf_bytes'> | null,
): PickOutcome {
  if (!picked.length) return { kind: 'ok', pages: current };
  const pdfs = picked.filter((p) => p.mimeType === 'application/pdf');
  const hasPdf = current.some((p) => p.mimeType === 'application/pdf');
  if (pdfs.length) {
    if (current.length > 0 || picked.length > 1) return { kind: 'pdf_or_photos', pages: current };
    const tooLarge = checkPdfSize(pdfs[0].byteLength, limits);
    if (tooLarge) return { kind: 'too_large', pages: current, error: tooLarge };
    return { kind: 'ok', pages: [pdfs[0]] };
  }
  if (hasPdf) return { kind: 'pdf_or_photos', pages: current };
  const max = limits?.max_pages ?? DEFAULT_MAX_PAGES;
  const room = Math.max(0, max - current.length);
  const next = [...current, ...picked.slice(0, room)];
  if (picked.length > room || next.length >= max) return { kind: 'page_cap', pages: next, maxPages: max };
  return { kind: 'ok', pages: next };
}

/** Move a page one step earlier (-1) or later (+1) in document order. */
export function movePage(pages: CapturedPage[], id: string, delta: -1 | 1): CapturedPage[] {
  const i = pages.findIndex((p) => p.id === id);
  const j = i + delta;
  if (i < 0 || j < 0 || j >= pages.length) return pages;
  const next = pages.slice();
  [next[i], next[j]] = [next[j], next[i]];
  return next;
}
