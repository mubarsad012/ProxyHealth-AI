// Saved-paper helpers (PRODUCT_SPEC §9.2–§9.3, D-22): build the `StoredDocument` the vault writes
// when the user confirms "Whose paper is this?", titles, category words, list order and the
// optional "Hide ID numbers in saved copies" masking. Pure: no platform imports.
//
// Privacy rules applied here (literally true copy, §9.5–§9.6):
//   • "Keep page images" off → no page files AND `page_thumbnails` dropped from the stored JSON;
//   • "Hide ID numbers" on → A-numbers and USCIS receipt numbers masked in every stored string, and
//     no page images are kept (an image would still show the number);
//   • nothing is written until the caller passes the result to `vault.documents.save`.

import type { AnalysisResult, DocumentCategory } from '@/api/types';
import { nextStatedDate, toIsoDay } from '@/features/reminders/schedule';
import type { DocumentRow, StoredDocument, StoredPageInput } from '@/storage/index';
import type { CapturedPage } from '@/store/session';

type Translate = (key: string, vars?: Record<string, string | number>) => string;

export const CATEGORIES: readonly DocumentCategory[] = [
  'immigration',
  'court',
  'medical',
  'benefits',
  'housing',
  'school',
  'employment',
  'tax',
  'civic',
  'other',
];

export function categoryWord(category: DocumentCategory | string, t: Translate): string {
  const known = (CATEGORIES as readonly string[]).includes(category) ? category : 'other';
  return t(`vault.category.${known}`);
}

/** `summary.title`, else "{category} · {date}" (`vault.title_fallback`). */
export function documentTitle(analysis: AnalysisResult | null, t: Translate, now: Date): string {
  const title = analysis?.summary?.title?.trim();
  if (title) return title.slice(0, 160);
  if (analysis?.is_likely_scam) return t('vault.title_scam_check');
  return t('vault.title_fallback', {
    type: categoryWord(analysis?.category ?? 'other', t),
    date: toIsoDay(now),
  });
}

// A-numbers: "A123456789", "A-123-456-789", "A 12 345 678"; USCIS receipts: "IOE0912345678".
const A_NUMBER = /\bA[\s-]?(\d[\s-]?){7,8}\d\b/g;
const RECEIPT = /\b[A-Z]{3}\d{10}\b/g;

/** Keeps the last 3 digits so a person can still tell two papers apart. */
export function maskIdText(text: string): string {
  return text
    .replace(RECEIPT, (m) => `${m.slice(0, 3)}•••••••${m.slice(-3)}`)
    .replace(A_NUMBER, (m) => `A-•••-•••-${m.replace(/\D/g, '').slice(-3)}`);
}

const SKIP_KEYS = /(^id$|_id$|_ids$|^span_ids$|^data_base64$|^mime_type$|_url$|_key$|_keys$)/;

/** Deep copy with every free-text string masked (ids, keys and URLs are left alone). */
export function maskIdNumbers<T>(value: T, key = ''): T {
  if (typeof value === 'string') return (SKIP_KEYS.test(key) ? value : maskIdText(value)) as T;
  if (Array.isArray(value)) return value.map((v) => maskIdNumbers(v, key)) as T;
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) out[k] = maskIdNumbers(v, k);
    return out as T;
  }
  return value;
}

export interface BuildDocumentInput {
  /** Null for "Save to read later" (no analysis yet). */
  analysis: AnalysisResult | null;
  pages: CapturedPage[];
  memberId: string;
  keepPages: boolean;
  hideIds: boolean;
  now: Date;
  t: Translate;
  /** Required when `analysis` is null; otherwise the id is `analysis.analysis_id`. */
  documentId?: string;
}

function jpegBase64(page: CapturedPage): string | null {
  if (!page.base64) return null;
  if (page.mimeType !== 'image/jpeg') return null;
  return page.base64.replace(/^data:image\/jpeg;base64,/, '');
}

export function buildStoredDocument(input: BuildDocumentInput): { doc: StoredDocument; pages: StoredPageInput[] } {
  const { analysis, now, t } = input;
  const id = analysis?.analysis_id ?? input.documentId;
  if (!id) throw new Error('documentId required');
  const keepImages = input.keepPages && !input.hideIds;
  let stored: AnalysisResult | null = analysis ? { ...analysis } : null;
  if (stored && !keepImages) stored = { ...stored, page_thumbnails: null };
  if (stored && input.hideIds) stored = maskIdNumbers(stored);
  const thumbs = new Map<number, string>();
  for (const th of stored?.page_thumbnails ?? []) {
    if (th.mime_type === 'image/jpeg') thumbs.set(th.page, th.data_base64);
  }
  const pageInputs: StoredPageInput[] = [];
  if (keepImages) {
    input.pages.forEach((p, i) => {
      const base64 = jpegBase64(p);
      if (base64) pageInputs.push({ page: i + 1, base64Jpeg: base64, thumbBase64: thumbs.get(i + 1) });
    });
  }
  const title = documentTitle(stored, t, now);
  const doc: StoredDocument = {
    id,
    memberId: input.memberId,
    title: input.hideIds ? maskIdText(title) : title,
    category: stored?.category ?? 'other',
    documentType: stored?.document_type ?? 'unknown',
    createdAt: now.toISOString(),
    nextDateIso: nextStatedDate(stored, now),
    pageCount: input.pages.length || stored?.quality?.pages_received || 0,
    analysis: stored as AnalysisResult,
    keepPages: pageInputs.length > 0,
  };
  return { doc, pages: pageInputs };
}

/** S12 order: papers with an upcoming date first (soonest first), then newest first. */
export function sortRows<T extends Pick<DocumentRow, 'nextDateIso' | 'createdAt'>>(rows: T[], now: Date): T[] {
  const today = toIsoDay(now);
  const upcoming = (r: T) => (r.nextDateIso && r.nextDateIso.slice(0, 10) >= today ? r.nextDateIso.slice(0, 10) : null);
  return [...rows].sort((a, b) => {
    const da = upcoming(a);
    const db = upcoming(b);
    if (da && db && da !== db) return da < db ? -1 : 1;
    if (da && !db) return -1;
    if (!da && db) return 1;
    return a.createdAt < b.createdAt ? 1 : a.createdAt > b.createdAt ? -1 : 0;
  });
}

/** True for results made from a sample paper (`vault.sample_tag`). */
export function isSampleAnalysis(analysis: AnalysisResult | null | undefined): boolean {
  return Boolean(analysis?.model_meta?.demo);
}
