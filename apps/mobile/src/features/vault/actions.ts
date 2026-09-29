// Vault write actions used by S12/S13 (PRODUCT_SPEC §9.3): delete a paper (the vault removes its
// files, checklist state, chat history and reminders and cancels their notifications), delete a
// member with all their papers ("Me" cannot be deleted), move papers, open a stored paper and
// turn a "read later" row back into pages for S5.

import { type Href, router } from 'expo-router';

import type { Vault } from '@/storage/index';
import type { CapturedPage } from '@/store/session';

import { isMe } from './members';
import { bumpVault } from './store';

export async function deleteDocument(vault: Vault, documentId: string): Promise<void> {
  await vault.documents.remove(documentId);
  bumpVault();
}

/** Per-member wipe: the member and every paper saved for them. */
export async function deleteMember(vault: Vault, memberId: string): Promise<boolean> {
  if (isMe(memberId)) return false;
  await vault.members.remove(memberId, true);
  bumpVault();
  return true;
}

export async function moveDocuments(vault: Vault, documentIds: string[], memberId: string): Promise<void> {
  for (const id of documentIds) await vault.documents.move(id, memberId);
  bumpVault();
}

/** S12 row tap → S7 from storage (WP5's `/result/<id>` reads it with `useDocument`). */
export function openStoredDocument(documentId: string): void {
  router.push(`/result/${encodeURIComponent(documentId)}` as Href);
}

/** Stored page files as capture pages (for `btn.read_now` on a "Not read yet" row). */
export async function readLaterPages(vault: Vault, documentId: string): Promise<CapturedPage[]> {
  const stored = await vault.pages.list(documentId);
  const out: CapturedPage[] = [];
  for (const p of stored) {
    const uri = await vault.pages.uri(p);
    if (!uri) continue;
    out.push({
      id: `${documentId}-p${p.page}`,
      uri,
      mimeType: 'image/jpeg',
      rotation: 0,
      masks: [],
      source: 'library',
    });
  }
  return out;
}
