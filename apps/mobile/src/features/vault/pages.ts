// Kept page images of a saved paper, by page NUMBER (PRODUCT_SPEC §9.2 `pages(document_id, page,
// file_path, …)`, D-19). `buildStoredDocument` numbers stored pages from the session index
// (`page: i + 1`) and skips a page whose "Hide parts" boxes are not burned into its pixels
// (native), so a saved paper can have a gap — e.g. page 1 masked, pages 2–3 kept. Consumers that
// index pages by position (`features/analysis/pageImages.ts` `pageImageFor`) must not shift the
// later pages into the gap, and must not drop them either:
//   `loadStoredPageSlots` keeps every stored page at index `page - 1`; a gap holds a placeholder
//   with an empty `uri` (`isPageGap`), which a viewer shows as quote-only. Trailing gaps are not
//   padded. Unreadable files are gaps too.

import type { StoredPage, Vault } from '@/storage/index';
import type { CapturedPage } from '@/store/session';

/** Sanity bound for a corrupt page number (the app never sends more than a few dozen pages). */
export const MAX_STORED_PAGE = 200;

export function isPageGap(page: Pick<CapturedPage, 'uri'>): boolean {
  return !page.uri;
}

function slot(documentId: string, n: number, uri: string): CapturedPage {
  return {
    id: `${documentId}-p${n}`,
    uri,
    mimeType: 'image/jpeg',
    rotation: 0,
    masks: [],
    source: 'library',
  };
}

/** Stored page files positioned by page number; gaps hold `isPageGap` placeholders. */
export async function loadStoredPageSlots(vault: Vault, documentId: string): Promise<CapturedPage[]> {
  const stored: StoredPage[] = [...(await vault.pages.list(documentId))].sort((a, b) => a.page - b.page);
  const out: CapturedPage[] = [];
  for (const p of stored) {
    if (!Number.isInteger(p.page) || p.page < 1 || p.page > MAX_STORED_PAGE || p.page <= out.length) continue;
    const uri = await vault.pages.uri(p);
    if (!uri) continue;
    while (out.length < p.page - 1) out.push(slot(documentId, out.length + 1, ''));
    out.push(slot(documentId, p.page, uri));
  }
  return out;
}
