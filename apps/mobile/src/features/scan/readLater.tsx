// "Save to read later" (PRODUCT_SPEC §5.4: "runs the save flow with `analysis_json = null`"; S5
// offline; S6 network / quota / upstream errors). The pages are saved to the vault through WP6's
// own `SaveToVaultSheet` (`readLaterId`) as a "Not read yet" paper whose row offers "Read it now"
// (S5 with those pages). Nothing is queued in memory any more: the old session queue had no
// reader and died with the app, so "I saved the photo. I will read it when internet is back." was
// never true (CL-064). It is offered only when the saved row will really hold the pages: images
// (a PDF has no stored page files), no hidden parts (the stored copy would lose the boxes), and
// Settings → "Keep page images" on with "Hide ID numbers" off (both decide whether images are kept).

import { type ReactNode, useState } from 'react';

import type { AnalysisResult } from '@/api/types';
import { SaveToVaultSheet } from '@/features/vault';
import { newId } from '@/lib/ids';
import type { CapturedPage } from '@/store/session';
import { useSettings } from '@/store/settings';

import { compressPage } from './compress';

/** Why "Save to read later" is not offered (`none` = it is). */
export type ReadLaterBlock = 'none' | 'keep_pages_off' | 'unsupported';

export function readLaterBlock(
  pages: readonly CapturedPage[],
  opts: { sample: boolean; keepPageImages: boolean; hideIdNumbers: boolean },
): ReadLaterBlock {
  if (!pages.length || opts.sample) return 'unsupported';
  if (pages.some((p) => p.mimeType === 'application/pdf' || p.masks.length > 0)) return 'unsupported';
  if (opts.hideIdNumbers) return 'unsupported';
  if (!opts.keepPageImages) return 'keep_pages_off';
  return 'none';
}

/** The fixed line shown when "Save to read later" is not offered. */
export function readLaterBlockKey(block: ReadLaterBlock): string | null {
  if (block === 'keep_pages_off') return 'review.read_later_needs_keep_pages';
  if (block === 'unsupported') return 'review.read_later_unavailable';
  return null;
}

export interface ReadLater {
  block: ReadLaterBlock;
  preparing: boolean;
  failed: boolean;
  /** Compress the pages to stored JPEGs, then open the save sheet. */
  start(): Promise<void>;
  /** The open sheet, or null. */
  sheet: ReactNode;
}

export function useReadLater(pages: readonly CapturedPage[], sample: boolean, onSaved: (documentId: string) => void): ReadLater {
  const keepPageImages = useSettings((s) => s.keepPageImages);
  const hideIdNumbers = useSettings((s) => s.hideIdNumbers);
  const block = readLaterBlock(pages, { sample, keepPageImages, hideIdNumbers });
  const [pending, setPending] = useState<{ id: string; pages: CapturedPage[] } | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [failed, setFailed] = useState(false);

  const start = async () => {
    if (block !== 'none' || preparing) return;
    setPreparing(true);
    setFailed(false);
    try {
      // The vault keeps JPEG base64 page files only (`documents.jpegBase64`).
      const jpeg = await Promise.all(pages.map((p) => compressPage(p)));
      setPending({ id: newId(), pages: jpeg });
    } catch {
      setFailed(true);
    } finally {
      setPreparing(false);
    }
  };

  const sheet = pending ? (
    <SaveToVaultSheet
      // With `readLaterId` the sheet saves `analysis: null` ("Not read yet"); its prop type predates that.
      analysis={null as unknown as AnalysisResult}
      readLaterId={pending.id}
      pages={pending.pages}
      onSaved={(documentId) => {
        setPending(null);
        onSaved(documentId);
      }}
      onCancel={() => setPending(null)}
    />
  ) : null;

  return { block, preparing, failed, start, sheet };
}
