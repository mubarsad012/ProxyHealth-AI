// "Save as proof" (`btn.save_evidence`, scam mode; PRODUCT_SPEC J-F, COMPLIANCE_PRIVACY): stores
// the screenshot in the on-device vault as `document_type: other_notice`, category `immigration`,
// titled `vault.title_scam_check`. Only on an explicit tap (D-22 opt-in); device only — the server
// never keeps it. The row has no analysis (like "Save to read later", PRODUCT_SPEC §9.3), so the
// model's text about the screen is not stored; the image is the proof.

import { type SavableDocument, toStoredDocument } from '@/features/vault/documents';
import { newDocumentId } from '@/lib/ids';
import type { StoredDocument, StoredPageInput, Vault } from '@/storage';
import { ME_MEMBER_ID } from '@/storage/rows';

import type { Screenshot } from './pick';

/** The vault stores JPEG pages only; the picker re-encodes to JPEG, the raw fallback may not. */
export function canSaveEvidence(shot: Screenshot | null): shot is Screenshot {
  return Boolean(shot && shot.mimeType === 'image/jpeg' && shot.base64);
}

export function buildEvidenceDocument(
  shot: Screenshot,
  opts: { title: string; now: Date; memberId?: string; id?: string },
): { doc: StoredDocument; pages: StoredPageInput[] } {
  const doc: SavableDocument = {
    id: opts.id ?? newDocumentId(),
    memberId: opts.memberId ?? ME_MEMBER_ID,
    title: opts.title,
    category: 'immigration',
    documentType: 'other_notice',
    createdAt: opts.now.toISOString(),
    nextDateIso: null,
    pageCount: 1,
    // No analysis is kept for a scam check (same shape as a "read later" row).
    analysis: null,
    keepPages: true,
  };
  const base64Jpeg = shot.base64.replace(/^data:image\/jpeg;base64,/, '');
  return { doc: toStoredDocument(doc), pages: [{ page: 1, base64Jpeg }] };
}

/** Save the screenshot to the vault; resolves the new document id. */
export async function saveScamEvidence(
  vault: Vault,
  shot: Screenshot,
  opts: { title: string; now?: Date; memberId?: string },
): Promise<string> {
  const { doc, pages } = buildEvidenceDocument(shot, { title: opts.title, now: opts.now ?? new Date(), memberId: opts.memberId });
  await vault.documents.save(doc, pages);
  return doc.id;
}
