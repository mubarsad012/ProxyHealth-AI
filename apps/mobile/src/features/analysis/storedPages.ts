// Kept page images of a saved paper (PRODUCT_SPEC S7 "Data": page images come from session.pages,
// vault files via `vault.pages.uri`, or `page_thumbnails`). Stored pages are numbered from the
// session index (`page: i + 1`, WP6 `buildStoredDocument`), and a page whose "Hide parts" boxes
// were not burned into its pixels is not stored, so a saved paper can have a gap (page 1 masked,
// pages 2-3 kept). `pageImageFor` indexes by position, so every stored page sits at index
// `page - 1` and a gap holds an empty-`uri` placeholder (`features/vault/pages.ts`
// `loadStoredPageSlots`, `isPageGap`): the later pages keep their images and the gap is quote-only
// (CL-077).

import { useEffect, useState } from 'react';

import { loadStoredPageSlots, useVaultVersion } from '@/features/vault';
import type { Vault } from '@/storage/index';
import { useVault } from '@/storage/StorageProvider';
import type { CapturedPage } from '@/store/session';

/** Stored page files as capture pages at index `page - 1`; a gap is an empty-`uri` placeholder. */
export function loadStoredPages(vault: Vault, documentId: string): Promise<CapturedPage[]> {
  return loadStoredPageSlots(vault, documentId);
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
