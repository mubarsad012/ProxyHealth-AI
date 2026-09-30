// Kept page images of a saved paper (PRODUCT_SPEC S7 "Data": page images come from session.pages,
// vault files via `vault.pages.uri`, or `page_thumbnails`). Stored pages are numbered from the
// session index (`page: i + 1`, WP6 `buildStoredDocument`) and `pageImageFor` indexes by position,
// so only the run of pages 1..n without a gap is returned: a later page after a missing file falls
// back to quote-only rather than showing the wrong page.

import { useEffect, useState } from 'react';

import { useVaultVersion } from '@/features/vault';
import type { StoredPage, Vault } from '@/storage/index';
import { useVault } from '@/storage/StorageProvider';
import type { CapturedPage } from '@/store/session';

/** Stored page files as capture pages, in page order, stopping at the first gap. */
export async function loadStoredPages(vault: Vault, documentId: string): Promise<CapturedPage[]> {
  const stored: StoredPage[] = [...(await vault.pages.list(documentId))].sort((a, b) => a.page - b.page);
  const out: CapturedPage[] = [];
  for (const p of stored) {
    if (p.page !== out.length + 1) break;
    const uri = await vault.pages.uri(p);
    if (!uri) break;
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

const NONE: CapturedPage[] = [];

/** Page images for a vault document whose `keepPages` is on ([] otherwise or while loading). */
export function useStoredPages(documentId: string | null, keepPages: boolean): CapturedPage[] {
  const vault = useVault();
  const version = useVaultVersion((s) => s.version);
  const [state, setState] = useState<{ key: string; pages: CapturedPage[] }>({ key: '', pages: NONE });
  const key = documentId && keepPages ? documentId : '';
  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    loadStoredPages(vault, key)
      .then((pages) => {
        if (!cancelled) setState({ key, pages });
      })
      .catch(() => {
        if (!cancelled) setState({ key, pages: NONE });
      });
    return () => {
      cancelled = true;
    };
  }, [vault, key, version]);
  return key && state.key === key ? state.pages : NONE;
}
