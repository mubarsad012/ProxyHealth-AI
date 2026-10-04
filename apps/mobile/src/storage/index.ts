// Vault interface and storage types (BUILD_PLAN §4.2 verbatim; owner WP4).
// `vault` is the platform re-export (`vault.native.ts` / `vault.web.ts`, resolved by Metro).
// `StoredDocument.analysis` is null for "Save to read later" rows (PRODUCT_SPEC §9.3) even though
// the §4.2 type says `AnalysisResult`; readers must check it.

import type { AnalysisResult, DocumentCategory, DocumentType } from '@/api/types';

export interface Vault {
  init(): Promise<void>;
  members: {
    list(): Promise<Member[]>;
    add(input: { name: string; color: string }): Promise<Member>;
    rename(id: string, name: string): Promise<void>;
    /** S13 "Change color" (CL-036; beyond the §4.2 text). */
    recolor(id: string, color: string): Promise<void>;
    remove(id: string, wipeDocuments: boolean): Promise<void>;
  };
  documents: {
    list(memberId?: string): Promise<DocumentRow[]>;
    get(id: string): Promise<StoredDocument | null>;
    save(doc: StoredDocument, pages: StoredPageInput[]): Promise<void>;
    move(id: string, memberId: string): Promise<void>;
    remove(id: string): Promise<void>;
    search(q: string): Promise<DocumentRow[]>;
  };
  pages: {
    list(documentId: string): Promise<StoredPage[]>;
    uri(page: StoredPage): Promise<string | null>;
  };
  checklist: {
    get(documentId: string): Promise<Record<string, boolean>>;
    set(documentId: string, stepId: string, checked: boolean): Promise<void>;
  };
  reminders: {
    list(): Promise<Reminder[]>;
    add(r: Omit<Reminder, 'id'>): Promise<Reminder>;
    remove(id: string): Promise<void>;
    setEnabled(id: string, on: boolean): Promise<void>;
  };
  /** Thin wrapper over storage/kv.ts (AsyncStorage) — there is no sqlite consent table (D-22). */
  consent: {
    get(): Promise<ConsentRecord | null>;
    set(r: ConsentRecord): Promise<void>;
    clear(): Promise<void>;
  };
  wipeAll(): Promise<void>;
}

export type Member = { id: string; name: string; color: string; createdAt: string };

export type DocumentRow = {
  id: string;
  memberId: string;
  title: string;
  category: DocumentCategory;
  documentType: DocumentType;
  createdAt: string;
  nextDateIso: string | null;
  pageCount: number;
};

export type StoredDocument = DocumentRow & { analysis: AnalysisResult; keepPages: boolean };

export type StoredPageInput = { page: number; base64Jpeg: string; thumbBase64?: string };

export type StoredPage = {
  documentId: string;
  page: number;
  filePath: string;
  thumbPath: string | null;
};

export type Reminder = {
  id: string;
  documentId: string;
  demandId: string;
  fireAt: string;
  notificationId: string | null;
  detailOptIn: boolean;
  enabled: boolean;
  label: string;
};

export type ConsentRecord = {
  consent_version: string;
  accepted_at: string;
  tier_seen: 'paid' | 'unpaid' | 'mixed' | 'demo' | 'none' | 'local' | 'attested' | 'unknown';
  platform: 'ios' | 'android' | 'web';
  /**
   * Phase 3 (free-ai-providers §5.3): which AI the accepted S2 copy named when it named one —
   * `openai_compat|{vendor}|{model}` from `/v1/config` `ai_vendor_name` / `ai_model_label`.
   * Written only on `AI_PROVIDER=openai_compat` (absent for Gemini and the mock, so those records
   * keep the four-field shape of COMPLIANCE_PRIVACY §4.2). A different value re-shows S2.
   */
  ai_seen?: string;
};

/** Platform re-export: Metro resolves `./vault` to `vault.native.ts` (expo-sqlite + files) or
 *  `vault.web.ts` (memory, IndexedDB opt-in); `vault.d.ts` types it for tsc. */
export { vault, configureVault, cancelAllNotifications, type VaultConfig } from './vault';
