// S8 view-model (PRODUCT_SPEC S8): pages, translation alignment and block selection. Pure; the
// screen renders it. Translation lines align by block order only when the server translated the
// full page (line count equals block count); otherwise the page translation is shown whole and
// unmatched blocks say "Not translated" when the translation is partial.

import type { AnalysisResult, PageText, TextBlock } from '@/api/types';

export type SourceMode = 'original' | 'both' | 'translation';

export interface SourceBlockRow {
  block: TextBlock;
  index: number;
  translation: string | null;
}

export interface SourcePageModel {
  page: number;
  blocks: SourceBlockRow[];
  /** Whole-page translation when lines could not be aligned to blocks. */
  pageTranslation: string | null;
  partial: boolean;
}

export function sourcePages(a: AnalysisResult): number[] {
  const nums = a.original_text.map((p) => p.page);
  return nums.length ? nums : [1];
}

export function sourcePageModel(a: AnalysisResult, page: number): SourcePageModel {
  const text: PageText | undefined = a.original_text.find((p) => p.page === page);
  const blocks = text?.blocks ?? [];
  const translated = a.translated_text.find((p) => p.page === page)?.text ?? null;
  const partial = a.warnings.includes('translation_partial');
  const lines = translated ? translated.split(/\n+/).map((l) => l.trim()).filter(Boolean) : [];
  const aligned = lines.length > 0 && lines.length === blocks.length;
  return {
    page,
    blocks: blocks.map((block, index) => ({ block, index, translation: aligned ? lines[index] : null })),
    pageTranslation: aligned ? null : translated,
    partial,
  };
}

/** The page to open for `?block=` / `?page=` (block wins; falls back to the first page). */
export function initialSourcePage(a: AnalysisResult, block?: string | null, page?: string | number | null): number {
  if (block) {
    for (const p of a.original_text) if (p.blocks.some((b) => b.id === block)) return p.page;
  }
  const n = Number(page);
  if (Number.isFinite(n) && a.original_text.some((p) => p.page === n)) return n;
  return sourcePages(a)[0];
}

/** "Block {i} on page {n}: {first 8 words}" (label built from real text, not model prose). */
export function blockLabel(row: SourceBlockRow, page: number): string {
  const words = row.block.text.split(/\s+/).slice(0, 8).join(' ');
  return `${row.index + 1} · ${page}: ${words}`;
}
