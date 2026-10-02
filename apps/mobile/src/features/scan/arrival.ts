// Compress each new page as soon as it arrives (native; PRODUCT_SPEC S5 "compressing (per-page
// shimmer ≤ 1 s)"). A camera shot or a picked photo / PDF lands in `Paths.cache/<Module>/`; S4 and
// S5 compress it right away (1600 px JPEG 0.8, `compress.ts`), which swaps the session's page to the
// compressed data and deletes the temp original — so "Your paper was not saved anywhere" is true
// from that moment, not only after the next cold start (the launch-time sweep stays as a backstop).
// Web keeps picked files in memory only, so this does nothing there.

import { useEffect, useMemo, useState } from 'react';
import { Platform } from 'react-native';

import { isCaptureTemp } from '@/lib/image';
import { type CapturedPage, useSession } from '@/store/session';

import { compressPage, isCompressed } from './compress';

/** Pages whose temp original still waits for compression (pure given `isTemp`; for tests). */
export function pagesToPrepare(pages: readonly CapturedPage[], isTemp: (uri: string) => boolean = isCaptureTemp): CapturedPage[] {
  return pages.filter((p) => isTemp(p.uri) && !isCompressed(p) && !failed.has(p.id));
}

/** Pages that could not be compressed are not retried on every render (the sweep removes them). */
const failed = new Set<string>();

export function forgetArrivalFailures(): void {
  failed.clear();
}

/** Start compressing every waiting page; resolves when all of them settled. */
export function prepareArrivedPages(pages: readonly CapturedPage[], onSettled?: (id: string) => void): Promise<void> {
  const todo = pagesToPrepare(pages);
  return Promise.all(
    todo.map((p) =>
      compressPage(p)
        .catch(() => {
          failed.add(p.id);
        })
        .finally(() => onSettled?.(p.id)),
    ),
  ).then(() => undefined);
}

/** S4/S5 hook: compresses arriving native pages; returns the ids still being prepared. */
export function useCompressOnArrival(): ReadonlySet<string> {
  const pages = useSession((s) => s.pages);
  // Re-render when a page fails (it then stops counting as "being prepared").
  const [failures, setFailures] = useState(0);
  const native = Platform.OS !== 'web';
  useEffect(() => {
    if (!native) return;
    let alive = true;
    void prepareArrivedPages(pages).then(() => {
      if (alive) setFailures(failed.size);
    });
    return () => {
      alive = false;
    };
  }, [native, pages]);
  return useMemo(
    () => new Set(native ? pagesToPrepare(pages).map((p) => p.id) : []),
    // `failures` changes when a page fails, so it stops counting as "being prepared".
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [native, pages, failures],
  );
}
