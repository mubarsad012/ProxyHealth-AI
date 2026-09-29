// Row ⇄ model mapping shared by the sqlite (native) and IndexedDB/memory (web) vaults.
// Pure functions: no platform imports, unit-tested in storage.native.test.ts.

import type { AnalysisResult, DocumentCategory, DocumentType } from '@/api/types';
import type { DocumentRow, Member, Reminder, StoredDocument, StoredPage } from '@/storage/index';

export const ME_MEMBER_ID = 'me';

export interface MemberDbRow {
  id: string;
  name: string;
  color: string;
  created_at: string;
}

export interface DocumentDbRow {
  id: string;
  member_id: string;
  title: string;
  category: string;
  document_type: string;
  analysis_json: string | null;
  created_at: string;
  next_date_iso: string | null;
  keep_pages: number;
  page_count: number;
}

export interface PageDbRow {
  document_id: string;
  page: number;
  file_path: string;
  thumb_path: string | null;
}

export interface ReminderDbRow {
  id: string;
  document_id: string;
  demand_id: string;
  fire_at: string;
  notification_id: string | null;
  detail_opt_in: number;
  enabled: number;
  label: string;
}

export function memberFromRow(r: MemberDbRow): Member {
  return { id: r.id, name: r.name, color: r.color, createdAt: r.created_at };
}

export function documentRowFromDb(r: DocumentDbRow): DocumentRow {
  return {
    id: r.id,
    memberId: r.member_id,
    title: r.title,
    category: r.category as DocumentCategory,
    documentType: r.document_type as DocumentType,
    createdAt: r.created_at,
    nextDateIso: r.next_date_iso,
    pageCount: r.page_count,
  };
}

/** `analysis_json` is null for "Save to read later" items (PRODUCT_SPEC §9.3). */
export function storedDocumentFromDb(r: DocumentDbRow): StoredDocument {
  let analysis: AnalysisResult | null = null;
  if (r.analysis_json) {
    try {
      analysis = JSON.parse(r.analysis_json) as AnalysisResult;
    } catch {
      analysis = null;
    }
  }
  return {
    ...documentRowFromDb(r),
    analysis: analysis as AnalysisResult,
    keepPages: r.keep_pages === 1,
  };
}

export function documentParams(doc: StoredDocument): (string | number | null)[] {
  return [
    doc.id,
    doc.memberId,
    doc.title,
    doc.category,
    doc.documentType,
    doc.analysis ? JSON.stringify(doc.analysis) : null,
    doc.createdAt,
    doc.nextDateIso,
    doc.keepPages ? 1 : 0,
    doc.pageCount,
  ];
}

export function pageFromRow(r: PageDbRow): StoredPage {
  return { documentId: r.document_id, page: r.page, filePath: r.file_path, thumbPath: r.thumb_path };
}

export function reminderFromRow(r: ReminderDbRow): Reminder {
  return {
    id: r.id,
    documentId: r.document_id,
    demandId: r.demand_id,
    fireAt: r.fire_at,
    notificationId: r.notification_id,
    detailOptIn: r.detail_opt_in === 1,
    enabled: r.enabled === 1,
    label: r.label,
  };
}

export function reminderParams(r: Reminder): (string | number | null)[] {
  return [r.id, r.documentId, r.demandId, r.fireAt, r.notificationId, r.detailOptIn ? 1 : 0, r.enabled ? 1 : 0, r.label];
}

/** Local substring search over the title, the sender as written, category and type words. */
export function documentMatches(doc: StoredDocument | DocumentRow, q: string): boolean {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  const analysis = 'analysis' in doc ? doc.analysis : null;
  const sender = analysis?.sender_as_written ?? '';
  const hay = [doc.title, sender, doc.category, doc.documentType.replace(/_/g, ' ')].join(' ').toLowerCase();
  return hay.includes(needle);
}

/** Newest first, the order S12 lists papers in. */
export function byCreatedDesc<T extends { createdAt: string }>(a: T, b: T): number {
  return a.createdAt < b.createdAt ? 1 : a.createdAt > b.createdAt ? -1 : 0;
}

export function pageFileName(page: number): string {
  return `page-${page}.jpg`;
}

export function thumbFileName(page: number): string {
  return `thumb-${page}.jpg`;
}
