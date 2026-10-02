// S5 choices for the paper being scanned (PRODUCT_SPEC S5 should-haves): the output-language chip
// (`null` = the UI language), the optional "I think this is a…" hint (`AnalyzeRequest.document_hint`,
// a tie-breaker only on the server) and the optional "Whose paper is this?" member (default Me),
// which preselects the member in "Save" on S7 and in "Save to read later". Memory only, like the
// scan session itself; the choices reset when a new scan starts (the page list is emptied or
// replaced by pages that share no id with the old list, or another sample is opened).

import { create } from 'zustand';

import type { DocumentType } from '@/api/types';
import { useSession } from '@/store/session';

/** "Page {n} of {count}" — the accessibility label of every page image on S4/S5 and the mask
 *  editor (keys-2c-mobilescan.json). */
export const PAGE_IMAGE_KEY = 'review.page_image';

/** The ≤ 8 common choices of the `review.document_hint` chip row (+ "Not sure" = null). */
export const DOCUMENT_HINTS: readonly DocumentType[] = [
  'medical_bill',
  'medicaid_renewal',
  'snap_notice',
  'uscis_receipt',
  'hearing_notice',
  'pay_or_quit',
  'utility_shutoff',
  'school_enrollment',
];

/** Chip label key for a hint (keys-2c-mobilescan.json); `null` is "Not sure". */
export function documentHintKey(hint: DocumentType | null): string {
  return hint ? `review.hint.${hint}` : 'review.hint.not_sure';
}

export interface ScanChoicesState {
  /** Output language for this paper; null follows the UI language. */
  outputLanguage: string | null;
  documentHint: DocumentType | null;
  /** Vault member for this paper; null = Me (the SaveToVaultSheet default). */
  memberId: string | null;
  setOutputLanguage(tag: string | null): void;
  setDocumentHint(hint: DocumentType | null): void;
  setMemberId(id: string | null): void;
  reset(): void;
}

const EMPTY = { outputLanguage: null, documentHint: null, memberId: null } as const;

export const useScanChoices = create<ScanChoicesState>()((set) => ({
  ...EMPTY,
  setOutputLanguage: (outputLanguage) => set({ outputLanguage }),
  setDocumentHint: (documentHint) => set({ documentHint }),
  setMemberId: (memberId) => set({ memberId }),
  reset: () => set({ ...EMPTY }),
}));

/** True when `next` starts a different scan than `prev` (pure; exported for tests). */
export function isNewScan(
  prev: { pages: readonly { id: string }[]; demoSampleId: string | null },
  next: { pages: readonly { id: string }[]; demoSampleId: string | null },
): boolean {
  if (next.demoSampleId !== prev.demoSampleId) return true;
  if (!next.pages.length) return prev.pages.length > 0;
  if (!prev.pages.length) return false;
  const old = new Set(prev.pages.map((p) => p.id));
  return !next.pages.some((p) => old.has(p.id));
}

useSession.subscribe((next, prev) => {
  if (next.pages === prev.pages && next.demoSampleId === prev.demoSampleId) return;
  if (isNewScan(prev, next)) useScanChoices.getState().reset();
});

// The member chosen on S5, kept per analysis so S7's "Save" preselects it (memory only).
const memberByAnalysis = new Map<string, string>();

export function rememberMemberFor(analysisId: string, memberId: string | null): void {
  if (memberId) memberByAnalysis.set(analysisId, memberId);
  else memberByAnalysis.delete(analysisId);
}

export function memberChoiceFor(analysisId: string | null | undefined): string | null {
  return analysisId ? (memberByAnalysis.get(analysisId) ?? null) : null;
}

export function forgetMemberChoices(): void {
  memberByAnalysis.clear();
}
